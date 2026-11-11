"""
Economic simulation module for validation-only dry-run scaffolding.

Implements the economic simulation gate (H5) per the pre-specified protocol
(research/specifications/holdout_evaluation_protocol.md) using validation
forecasts only. No holdout data is used for evaluation or tuning.

Key features:
- Signal-to-action mapping with predeclared no-trade region (theta)
- Fixed sizing / exposure rules
- Per-side cost accounting (base and stress cost models)
- Funding rate integration from processed features
- Gross vs net PnL computation
- Economic metrics with uncertainty estimates
- Baseline comparisons (no-trade, buy-and-hold, simple rules)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class CostModel:
    """Trading cost parameters (per-side, in basis points)."""
    taker_fee_bps: float
    half_spread_bps: float
    slippage_bps: float

    @property
    def per_side_bps(self) -> float:
        return self.taker_fee_bps + self.half_spread_bps + self.slippage_bps

    @property
    def round_trip_bps(self) -> float:
        return 2.0 * self.per_side_bps

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for economic simulation (frozen, no holdout tuning)."""
    # Signal threshold (theta) in bps - base case 0, sensitivity {2, 5}
    theta_bps: float = 0.0

    # Sizing
    notional_fraction: float = 0.10  # 10% of equity per trade
    max_gross_exposure: float = 1.0  # 100% max gross

    # Cost models
    cost_base: CostModel = CostModel(taker_fee_bps=5.0, half_spread_bps=1.0, slippage_bps=2.0)
    cost_stress: CostModel = CostModel(taker_fee_bps=10.0, half_spread_bps=2.0, slippage_bps=4.0)

    # Funding
    funding_source: str = "data/processed/features.parquet"

    # Execution convention: decision at t-1 close, fill at t open
    # Returns are computed as (close_t / open_t - 1) for the held period
    execution_convention: Literal["next_open"] = "next_open"

    # Baseline parameters
    buy_and_hold: bool = True
    momentum_lookback: int = 24  # hours
    momentum_threshold_bps: float = 0.0

    # Validation period
    val_start: str = "2024-01-01 00:00:00+00:00"
    val_end: str = "2024-06-30 23:00:00+00:00"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cost_base"] = self.cost_base.to_dict()
        d["cost_stress"] = self.cost_stress.to_dict()
        return d


@dataclass
class Trade:
    """Individual trade record."""
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    notional: float
    gross_pnl: float
    fee_cost: float
    spread_cost: float
    slippage_cost: float
    funding_cost: float
    net_pnl: float
    holding_hours: float


@dataclass
class EconomicMetrics:
    """Economic performance metrics."""
    # Returns
    gross_returns: np.ndarray
    net_returns_base: np.ndarray
    net_returns_stress: np.ndarray

    # Summary stats
    n_obs: int
    n_trades_base: int
    n_trades_stress: int

    # Annualized metrics (base costs)
    gross_cagr: float
    gross_vol: float
    gross_sharpe: float
    gross_sortino: float
    gross_calmar: float
    gross_max_dd: float

    net_cagr_base: float
    net_vol_base: float
    net_sharpe_base: float
    net_sortino_base: float
    net_calmar_base: float
    net_max_dd_base: float

    net_cagr_stress: float
    net_vol_stress: float
    net_sharpe_stress: float
    net_sortino_stress: float
    net_calmar_stress: float
    net_max_dd_stress: float

    # Trade stats (base)
    hit_rate_base: float
    payoff_ratio_base: float
    profit_factor_base: float
    expectancy_per_trade_base: float
    expectancy_per_bar_base: float
    tail_loss_base: float
    max_gross_exposure_base: float
    turnover_annualized_base: float
    avg_holding_hours_base: float
    time_in_market_base: float

    # Trade stats (stress)
    hit_rate_stress: float
    payoff_ratio_stress: float
    profit_factor_stress: float
    expectancy_per_trade_stress: float
    expectancy_per_bar_stress: float
    tail_loss_stress: float
    max_gross_exposure_stress: float
    turnover_annualized_stress: float
    avg_holding_hours_stress: float
    time_in_market_stress: float

    # Baseline comparisons
    excess_sharpe_vs_notrade_base: float
    excess_sharpe_vs_buyhold_base: float
    excess_sharpe_vs_momentum_base: float

    def to_dict(self) -> dict:
        return asdict(self)


def load_forecast_csv(path: Path) -> pd.DataFrame:
    """Load forecast CSV and ensure timestamp index."""
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df


def load_funding_rates(path: Path, symbol: str = "BTCUSDT") -> pd.Series:
    """Load funding rate series from features parquet."""
    df = pd.read_parquet(path)
    df = df[df["symbol"] == symbol].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    funding = df["funding_rate"].astype(float)
    funding = funding[funding.notna()]
    return funding


def align_funding_to_forecasts(
    funding: pd.Series,
    forecast_index: pd.DatetimeIndex,
    horizon_hours: int = 1
) -> pd.Series:
    """
    Align funding rates to forecast timestamps.
    Funding is 8h; we pro-rate to the 1h holding period.
    """
    # Funding rate is typically quoted as 8h rate; scale to 1h
    funding_hourly = funding / 8.0

    # Reindex to forecast timestamps, forward fill (funding known at decision time)
    aligned = funding_hourly.reindex(forecast_index, method="ffill")
    # Fill any remaining NaN with 0 and flag
    n_missing = aligned.isna().sum()
    aligned = aligned.fillna(0.0)
    return aligned


def compute_signal(
    forecast_mu: np.ndarray,
    theta_bps: float,
    cost_per_side_bps: float
) -> np.ndarray:
    """
    Compute trading signal from forecast mean.

    Long if E[r] > theta + c_eff
    Short if E[r] < -theta - c_eff
    Flat otherwise

    c_eff = cost per side in decimal (round-trip / 2)
    """
    c_eff = cost_per_side_bps / 10000.0  # bps to decimal
    threshold = theta_bps / 10000.0 + c_eff

    signal = np.zeros_like(forecast_mu)
    signal[forecast_mu > threshold] = 1
    signal[forecast_mu < -threshold] = -1
    return signal


def apply_sizing(
    signal: np.ndarray,
    equity: float,
    notional_fraction: float,
    max_gross_exposure: float,
    current_position: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply fixed fractional sizing with exposure limits.

    Returns (target_notional, actual_notional) where actual respects max exposure.
    """
    target_notional = signal * equity * notional_fraction
    gross_exposure = np.abs(target_notional)

    # Scale down if exceeding max gross exposure
    scale = np.minimum(1.0, max_gross_exposure * equity / np.maximum(gross_exposure, 1e-10))
    actual_notional = target_notional * scale

    return target_notional, actual_notional


def compute_costs(
    notional_change: np.ndarray,
    cost_model: CostModel,
    funding_rate: np.ndarray,
    holding_hours: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute per-bar costs.

    Returns (fee_cost, spread_cost, slippage_cost, funding_cost) in decimal returns.
    """
    # Trading costs on notional change (turnover)
    turnover = np.abs(notional_change)
    fee_cost = turnover * (cost_model.taker_fee_bps / 10000.0)
    spread_cost = turnover * (cost_model.half_spread_bps / 10000.0)
    slippage_cost = turnover * (cost_model.slippage_bps / 10000.0)

    # Funding cost: pro-rata for holding period
    # funding_rate is already scaled to 1h
    funding_cost = np.abs(notional_change) * funding_rate * holding_hours

    return fee_cost, spread_cost, slippage_cost, funding_cost


def simulate_equity_curve(
    returns: np.ndarray,
    signal: np.ndarray,
    notional: np.ndarray,
    fee_cost: np.ndarray,
    spread_cost: np.ndarray,
    slippage_cost: np.ndarray,
    funding_cost: np.ndarray,
    initial_equity: float = 1.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Simulate equity curve given returns, signal, notional, and costs.

    Returns (gross_equity, net_equity, gross_returns, net_returns, trade_info)
    """
    n = len(returns)
    gross_equity = np.zeros(n + 1)
    net_equity = np.zeros(n + 1)
    gross_equity[0] = initial_equity
    net_equity[0] = initial_equity

    # Position at start of period i is notional[i-1] (or 0 for i=0)
    # But for bar 0, we assume position is established at the open
    # So position for period 0 = notional[0]
    position = notional[0] if n > 0 else 0.0
    trades = []

    # Track initial position as a trade if non-zero
    if n > 0 and abs(notional[0]) > 1e-10:
        trades.append({
            "bar": 0,
            "direction": np.sign(notional[0]),
            "notional_change": notional[0],
            "position_before": 0.0,
            "position_after": notional[0],
            "entry_bar": 0,
        })

    for i in range(n):
        # Gross P&L from position held during period i
        gross_pnl = position * returns[i]
        gross_equity[i + 1] = gross_equity[i] + gross_pnl

        # Net P&L after costs
        net_pnl = gross_pnl - fee_cost[i] - spread_cost[i] - slippage_cost[i] - funding_cost[i]
        net_equity[i + 1] = net_equity[i] + net_pnl

        # Track trades (position changes for next period)
        if i < n - 1:
            notional_change = notional[i + 1] - notional[i]
            if abs(notional_change) > 1e-10:
                direction = np.sign(notional_change) if notional_change != 0 else 0
                if direction != 0:
                    # Calculate P&L for this trade (approximate: position * return during holding)
                    # We'll compute this later when we have the full path
                    trades.append({
                        "bar": i + 1,
                        "direction": direction,
                        "notional_change": notional_change,
                        "position_before": position,
                        "position_after": notional[i + 1],
                        "entry_bar": i + 1,
                        "entry_price": 1.0,  # placeholder, will compute P&L post-hoc
                    })

        # Update position for next period
        if i < n - 1:
            position = notional[i + 1]

    gross_returns = np.diff(gross_equity) / gross_equity[:-1]
    net_returns = np.diff(net_equity) / net_equity[:-1]

    # Post-process trades to add P&L
    # For each trade, find the exit bar (next trade or end) and compute P&L
    processed_trades = []
    for idx, t in enumerate(trades):
        entry_bar = t["bar"]
        direction = t["direction"]
        position_size = t["position_after"]

        # Find exit bar
        if idx + 1 < len(trades):
            exit_bar = trades[idx + 1]["bar"]
        else:
            exit_bar = n  # end of simulation

        # Compute P&L as position * cumulative return from entry to exit
        if entry_bar < exit_bar and entry_bar < n:
            cum_return = np.prod(1 + gross_returns[entry_bar:exit_bar]) - 1
            pnl = position_size * cum_return
        else:
            pnl = 0.0

        t_copy = t.copy()
        t_copy["pnl"] = pnl
        t_copy["exit_bar"] = exit_bar
        processed_trades.append(t_copy)

    trade_info = {
        "n_trades": len(processed_trades),
        "trades": processed_trades
    }

    return gross_equity[1:], net_equity[1:], gross_returns, net_returns, trade_info


def compute_metrics(
    returns: np.ndarray,
    equity: np.ndarray,
    trades: list,
    funding_cost: np.ndarray,
    cost_model: CostModel,
    annualization_factor: float = 24 * 365  # 1h bars
) -> dict:
    """Compute comprehensive economic metrics."""
    n = len(returns)
    if n == 0:
        return {}

    # Basic stats
    mean_ret = np.mean(returns)
    std_ret = np.std(returns, ddof=1) if n > 1 else 0.0

    # Annualized
    cagr = (1 + mean_ret) ** annualization_factor - 1 if mean_ret > -1 else -1
    vol = std_ret * np.sqrt(annualization_factor)
    sharpe = (mean_ret / std_ret * np.sqrt(annualization_factor)) if std_ret > 0 else 0.0

    # Sortino (downside deviation)
    downside_returns = returns[returns < 0]
    downside_std = np.std(downside_returns, ddof=1) if len(downside_returns) > 1 else 0.0
    sortino = (mean_ret / downside_std * np.sqrt(annualization_factor)) if downside_std > 0 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = np.min(dd)

    # Calmar
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

    # Trade stats
    n_trades = len(trades)
    if n_trades > 0:
        trade_pnls = [t.get("pnl", 0) for t in trades]
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        hit_rate = len(wins) / n_trades if n_trades > 0 else 0.0
        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0
        payoff_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float('inf')
        expectancy_per_trade = np.mean(trade_pnls)
        tail_loss = np.percentile(trade_pnls, 5) if n_trades >= 20 else np.min(trade_pnls)
    else:
        hit_rate = payoff_ratio = profit_factor = expectancy_per_trade = tail_loss = 0.0

    expectancy_per_bar = mean_ret

    # Exposure and turnover
    max_gross_exposure = np.max(np.abs(np.diff(equity) / equity[:-1])) if n > 1 else 0.0
    total_turnover = np.sum(np.abs(np.diff(equity) / equity[:-1])) if n > 1 else 0.0
    turnover_annualized = total_turnover / n * annualization_factor if n > 0 else 0.0

    # Holding time (approximate)
    avg_holding_hours = n / n_trades if n_trades > 0 else 0.0
    time_in_market = n_trades / n if n > 0 else 0.0

    return {
        "n_obs": n,
        "n_trades": n_trades,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_dd": max_dd,
        "hit_rate": hit_rate,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor if profit_factor != float('inf') else 1e6,
        "expectancy_per_trade": expectancy_per_trade,
        "expectancy_per_bar": expectancy_per_bar,
        "tail_loss": tail_loss,
        "max_gross_exposure": max_gross_exposure,
        "turnover_annualized": turnover_annualized,
        "avg_holding_hours": avg_holding_hours,
        "time_in_market": time_in_market,
    }


def run_economic_simulation(
    forecast_df: pd.DataFrame,
    funding_series: pd.Series,
    config: SimulationConfig,
    model_name: str,
    cost_variant: Literal["base", "stress"] = "base"
) -> tuple[EconomicMetrics, pd.DataFrame]:
    """
    Run full economic simulation for a forecast DataFrame.

    Returns (metrics, trade_ledger_df)
    """
    cost_model = config.cost_base if cost_variant == "base" else config.cost_stress

    # Extract forecast data
    y_true = forecast_df["y_true"].values
    forecast_mu = forecast_df["hmm_mu"].values if "hmm_mu" in forecast_df.columns else forecast_df["hom_mu"].values
    forecast_var = forecast_df["hmm_var"].values if "hmm_var" in forecast_df.columns else forecast_df["hom_var"].values

    # Align funding
    funding_aligned = align_funding_to_forecasts(funding_series, forecast_df.index)
    funding_values = funding_aligned.values

    # Signal generation
    signal = compute_signal(forecast_mu, config.theta_bps, cost_model.per_side_bps)

    # Sizing
    equity = 1.0  # normalized
    _, notional = apply_sizing(signal, equity, config.notional_fraction, config.max_gross_exposure)

    # Compute notional changes (turnover)
    notional_change = np.zeros_like(notional)
    notional_change[0] = notional[0]  # initial position
    notional_change[1:] = np.diff(notional)

    # Costs
    holding_hours = np.ones_like(y_true)  # 1h per bar
    fee_cost, spread_cost, slippage_cost, funding_cost = compute_costs(
        notional_change, cost_model, funding_values, holding_hours
    )

    # Simulate
    gross_equity, net_equity, gross_returns, net_returns, trade_info = simulate_equity_curve(
        y_true, signal, notional, fee_cost, spread_cost, slippage_cost, funding_cost, equity
    )

    # Compute metrics for gross and net
    gross_metrics = compute_metrics(gross_returns, gross_equity, trade_info["trades"], funding_cost, cost_model)
    net_metrics = compute_metrics(net_returns, net_equity, trade_info["trades"], funding_cost, cost_model)

    # Build trade ledger
    trade_rows = []
    for t in trade_info["trades"]:
        trade_rows.append({
            "bar_index": t["bar"],
            "timestamp": forecast_df.index[t["bar"]],
            "direction": t["direction"],
            "notional_change": t["notional_change"],
            "position_before": t["position_before"],
            "position_after": t["position_after"],
        })
    trade_ledger = pd.DataFrame(trade_rows)

    # Build metrics object
    metrics = EconomicMetrics(
        gross_returns=gross_returns,
        net_returns_base=net_returns if cost_variant == "base" else np.zeros_like(net_returns),
        net_returns_stress=net_returns if cost_variant == "stress" else np.zeros_like(net_returns),
        n_obs=gross_metrics["n_obs"],
        n_trades_base=gross_metrics["n_trades"] if cost_variant == "base" else 0,
        n_trades_stress=gross_metrics["n_trades"] if cost_variant == "stress" else 0,
        gross_cagr=gross_metrics["cagr"],
        gross_vol=gross_metrics["vol"],
        gross_sharpe=gross_metrics["sharpe"],
        gross_sortino=gross_metrics["sortino"],
        gross_calmar=gross_metrics["calmar"],
        gross_max_dd=gross_metrics["max_dd"],
        net_cagr_base=net_metrics["cagr"] if cost_variant == "base" else 0.0,
        net_vol_base=net_metrics["vol"] if cost_variant == "base" else 0.0,
        net_sharpe_base=net_metrics["sharpe"] if cost_variant == "base" else 0.0,
        net_sortino_base=net_metrics["sortino"] if cost_variant == "base" else 0.0,
        net_calmar_base=net_metrics["calmar"] if cost_variant == "base" else 0.0,
        net_max_dd_base=net_metrics["max_dd"] if cost_variant == "base" else 0.0,
        net_cagr_stress=net_metrics["cagr"] if cost_variant == "stress" else 0.0,
        net_vol_stress=net_metrics["vol"] if cost_variant == "stress" else 0.0,
        net_sharpe_stress=net_metrics["sharpe"] if cost_variant == "stress" else 0.0,
        net_sortino_stress=net_metrics["sortino"] if cost_variant == "stress" else 0.0,
        net_calmar_stress=net_metrics["calmar"] if cost_variant == "stress" else 0.0,
        net_max_dd_stress=net_metrics["max_dd"] if cost_variant == "stress" else 0.0,
        hit_rate_base=net_metrics["hit_rate"] if cost_variant == "base" else 0.0,
        payoff_ratio_base=net_metrics["payoff_ratio"] if cost_variant == "base" else 0.0,
        profit_factor_base=net_metrics["profit_factor"] if cost_variant == "base" else 0.0,
        expectancy_per_trade_base=net_metrics["expectancy_per_trade"] if cost_variant == "base" else 0.0,
        expectancy_per_bar_base=net_metrics["expectancy_per_bar"] if cost_variant == "base" else 0.0,
        tail_loss_base=net_metrics["tail_loss"] if cost_variant == "base" else 0.0,
        max_gross_exposure_base=net_metrics["max_gross_exposure"] if cost_variant == "base" else 0.0,
        turnover_annualized_base=net_metrics["turnover_annualized"] if cost_variant == "base" else 0.0,
        avg_holding_hours_base=net_metrics["avg_holding_hours"] if cost_variant == "base" else 0.0,
        time_in_market_base=net_metrics["time_in_market"] if cost_variant == "base" else 0.0,
        hit_rate_stress=net_metrics["hit_rate"] if cost_variant == "stress" else 0.0,
        payoff_ratio_stress=net_metrics["payoff_ratio"] if cost_variant == "stress" else 0.0,
        profit_factor_stress=net_metrics["profit_factor"] if cost_variant == "stress" else 0.0,
        expectancy_per_trade_stress=net_metrics["expectancy_per_trade"] if cost_variant == "stress" else 0.0,
        expectancy_per_bar_stress=net_metrics["expectancy_per_bar"] if cost_variant == "stress" else 0.0,
        tail_loss_stress=net_metrics["tail_loss"] if cost_variant == "stress" else 0.0,
        max_gross_exposure_stress=net_metrics["max_gross_exposure"] if cost_variant == "stress" else 0.0,
        turnover_annualized_stress=net_metrics["turnover_annualized"] if cost_variant == "stress" else 0.0,
        avg_holding_hours_stress=net_metrics["avg_holding_hours"] if cost_variant == "stress" else 0.0,
        time_in_market_stress=net_metrics["time_in_market"] if cost_variant == "stress" else 0.0,
        excess_sharpe_vs_notrade_base=0.0,  # Will be filled by comparison
        excess_sharpe_vs_buyhold_base=0.0,
        excess_sharpe_vs_momentum_base=0.0,
    )

    return metrics, trade_ledger


def run_baseline_simulations(
    forecast_df: pd.DataFrame,
    funding_series: pd.Series,
    config: SimulationConfig,
    cost_variant: Literal["base", "stress"] = "base"
) -> dict[str, EconomicMetrics]:
    """
    Run baseline simulations (B3 no-trade, B4 buy-and-hold, B5 momentum).
    """
    cost_model = config.cost_base if cost_variant == "base" else config.cost_stress
    y_true = forecast_df["y_true"].values

    # Align funding
    funding_aligned = align_funding_to_forecasts(funding_series, forecast_df.index)
    funding_values = funding_aligned.values
    holding_hours = np.ones_like(y_true)

    results = {}

    # B3: No-trade (flat)
    signal_notrade = np.zeros_like(y_true)
    _, notional_notrade = apply_sizing(signal_notrade, 1.0, config.notional_fraction, config.max_gross_exposure)
    notional_change_notrade = np.zeros_like(notional_notrade)
    fee_c, spread_c, slippage_c, funding_c = compute_costs(
        notional_change_notrade, cost_model, funding_values, holding_hours
    )
    gross_eq, net_eq, gross_ret, net_ret, trade_info = simulate_equity_curve(
        y_true, signal_notrade, notional_notrade, fee_c, spread_c, slippage_c, funding_c, 1.0
    )
    metrics = compute_metrics(net_ret, net_eq, trade_info["trades"], funding_c, cost_model)
    results["B3_notrade"] = metrics

    # B4: Buy-and-hold (always long 100% notional fraction)
    signal_buyhold = np.ones_like(y_true)
    _, notional_buyhold = apply_sizing(signal_buyhold, 1.0, config.notional_fraction, config.max_gross_exposure)
    notional_change_buyhold = np.zeros_like(notional_buyhold)
    notional_change_buyhold[0] = notional_buyhold[0]
    fee_c, spread_c, slippage_c, funding_c = compute_costs(
        notional_change_buyhold, cost_model, funding_values, holding_hours
    )
    gross_eq, net_eq, gross_ret, net_ret, trade_info = simulate_equity_curve(
        y_true, signal_buyhold, notional_buyhold, fee_c, spread_c, slippage_c, funding_c, 1.0
    )
    metrics = compute_metrics(net_ret, net_eq, trade_info["trades"], funding_c, cost_model)
    results["B4_buyhold"] = metrics

    # B5: Simple momentum (sign of trailing return)
    lookback = config.momentum_lookback
    trailing_ret = pd.Series(y_true).rolling(lookback, min_periods=1).sum().values
    signal_momentum = np.sign(trailing_ret)
    signal_momentum[trailing_ret == 0] = 0
    _, notional_momentum = apply_sizing(signal_momentum, 1.0, config.notional_fraction, config.max_gross_exposure)
    notional_change_momentum = np.zeros_like(notional_momentum)
    notional_change_momentum[0] = notional_momentum[0]
    notional_change_momentum[1:] = np.diff(notional_momentum)
    fee_c, spread_c, slippage_c, funding_c = compute_costs(
        notional_change_momentum, cost_model, funding_values, holding_hours
    )
    gross_eq, net_eq, gross_ret, net_ret, trade_info = simulate_equity_curve(
        y_true, signal_momentum, notional_momentum, fee_c, spread_c, slippage_c, funding_c, 1.0
    )
    metrics = compute_metrics(net_ret, net_eq, trade_info["trades"], funding_c, cost_model)
    results["B5_momentum"] = metrics

    return results


def compute_excess_sharpe(metrics: EconomicMetrics, baseline_metrics: dict) -> EconomicMetrics:
    """Add excess Sharpe vs baselines to metrics object."""
    metrics.excess_sharpe_vs_notrade_base = metrics.net_sharpe_base - baseline_metrics["B3_notrade"].get("sharpe", 0)
    metrics.excess_sharpe_vs_buyhold_base = metrics.net_sharpe_base - baseline_metrics["B4_buyhold"].get("sharpe", 0)
    metrics.excess_sharpe_vs_momentum_base = metrics.net_sharpe_base - baseline_metrics["B5_momentum"].get("sharpe", 0)
    return metrics


def run_validation_dryrun(
    config: Optional[SimulationConfig] = None,
    theta_sensitivity: list[float] = None,
    output_dir: Path = Path("research/economic/validation_dryrun")
) -> dict:
    """
    Main entry point for validation-only economic simulation dry-run.

    Runs simulations for C1 (HMM) and C2 (Higher-order Markov) on validation period
    with base and stress costs, plus theta sensitivity.
    """
    if config is None:
        config = SimulationConfig()

    if theta_sensitivity is None:
        theta_sensitivity = [0.0, 2.0, 5.0]  # bps

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load validation forecasts
    c1_path = Path("research/forecasts/h2_validation_forecasts.csv")
    c2_path = Path("research/forecasts/h3_higher_order_markov_validation.csv")

    c1_df = load_forecast_csv(c1_path)
    c2_df = load_forecast_csv(c2_path)

    # Filter to validation period (already aligned, but ensure)
    val_start = pd.Timestamp(config.val_start)
    val_end = pd.Timestamp(config.val_end)
    c1_df = c1_df[(c1_df.index >= val_start) & (c1_df.index <= val_end)]
    c2_df = c2_df[(c2_df.index >= val_start) & (c2_df.index <= val_end)]

    # Load funding rates
    funding = load_funding_rates(Path(config.funding_source))

    results = {
        "config": config.to_dict(),
        "theta_sensitivity_bps": theta_sensitivity,
        "models": {},
        "baselines": {},
    }

    for model_id, model_df in [("C1_hmm", c1_df), ("C2_hom", c2_df)]:
        results["models"][model_id] = {}
        for theta in theta_sensitivity:
            # Create new config with updated theta, preserving CostModel objects
            config_theta = SimulationConfig(
                theta_bps=theta,
                notional_fraction=config.notional_fraction,
                max_gross_exposure=config.max_gross_exposure,
                cost_base=config.cost_base,
                cost_stress=config.cost_stress,
                funding_source=config.funding_source,
                execution_convention=config.execution_convention,
                buy_and_hold=config.buy_and_hold,
                momentum_lookback=config.momentum_lookback,
                momentum_threshold_bps=config.momentum_threshold_bps,
                val_start=config.val_start,
                val_end=config.val_end,
            )
            results["models"][model_id][f"theta_{theta}bps"] = {}

            for cost_variant in ["base", "stress"]:
                metrics, trade_ledger = run_economic_simulation(
                    model_df, funding, config_theta, model_id, cost_variant
                )

                # Run baselines for comparison
                baselines = run_baseline_simulations(model_df, funding, config_theta, cost_variant)
                metrics = compute_excess_sharpe(metrics, baselines)

                # Save trade ledger
                ledger_path = output_dir / f"{model_id}_theta{theta}bps_{cost_variant}_trades.csv"
                trade_ledger.to_csv(ledger_path, index=False)

                # Store metrics
                results["models"][model_id][f"theta_{theta}bps"][cost_variant] = metrics.to_dict()

                # Store baselines (only once per theta/cost)
                if model_id == "C1_hmm":
                    key = f"theta_{theta}bps_{cost_variant}"
                    results["baselines"][key] = {k: v for k, v in baselines.items()}

    # Save results JSON
    results_path = output_dir / "validation_dryrun_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Generate markdown report
    report_path = output_dir / "validation_dryrun_report.md"
    generate_report(results, report_path)

    return results


def generate_report(results: dict, output_path: Path) -> None:
    """Generate markdown report from simulation results."""
    lines = [
        "# Validation-Only Economic Simulation Dry-Run Report",
        "",
        f"**Generated:** {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"**Protocol:** research/specifications/holdout_evaluation_protocol.md",
        f"**Scope:** Validation period 2024-01-01 to 2024-06-30 (BTCUSDT 1h)",
        f"**Status:** DRY-RUN ONLY — No holdout evaluation performed",
        "",
        "## Configuration",
        "",
        f"- Theta sensitivity (bps): {results['theta_sensitivity_bps']}",
        f"- Notional fraction: {results['config']['notional_fraction']}",
        f"- Max gross exposure: {results['config']['max_gross_exposure']}",
        f"- Base cost round-trip: {results['config']['cost_base']['taker_fee_bps'] + results['config']['cost_base']['half_spread_bps'] + results['config']['cost_base']['slippage_bps']:.1f} bps per side = {results['config']['cost_base']['taker_fee_bps']*2 + results['config']['cost_base']['half_spread_bps']*2 + results['config']['cost_base']['slippage_bps']*2:.1f} bps round-trip",
        f"- Stress cost round-trip: {results['config']['cost_stress']['taker_fee_bps']*2 + results['config']['cost_stress']['half_spread_bps']*2 + results['config']['cost_stress']['slippage_bps']*2:.1f} bps round-trip",
        "",
        "## Results Summary",
        "",
    ]

    for model_id, theta_results in results["models"].items():
        lines.append(f"### {model_id}")
        lines.append("")
        lines.append("| Theta (bps) | Cost | Net Sharpe | Net CAGR | Max DD | Hit Rate | Trade Count | Turnover (ann.) | Excess vs No-Trade | Excess vs BuyHold |")
        lines.append("|-------------|------|------------|----------|--------|----------|-------------|-----------------|-------------------|-------------------|")

        for theta_key, cost_results in theta_results.items():
            for cost_variant, metrics in cost_results.items():
                lines.append(
                    f"| {theta_key.replace('theta_', '').replace('bps', '')} | {cost_variant} | "
                    f"{metrics.get('net_sharpe_base' if cost_variant == 'base' else 'net_sharpe_stress', 0):.3f} | "
                    f"{metrics.get('net_cagr_base' if cost_variant == 'base' else 'net_cagr_stress', 0):.4f} | "
                    f"{metrics.get('net_max_dd_base' if cost_variant == 'base' else 'net_max_dd_stress', 0):.4f} | "
                    f"{metrics.get('hit_rate_base' if cost_variant == 'base' else 'hit_rate_stress', 0):.3f} | "
                    f"{metrics.get('n_trades_base' if cost_variant == 'base' else 'n_trades_stress', 0)} | "
                    f"{metrics.get('turnover_annualized_base' if cost_variant == 'base' else 'turnover_annualized_stress', 0):.1f} | "
                    f"{metrics.get('excess_sharpe_vs_notrade_base', 0):.3f} | "
                    f"{metrics.get('excess_sharpe_vs_buyhold_base', 0):.3f} |"
                )
        lines.append("")

    # Baselines summary
    lines.append("## Baseline Comparison (Theta=0, Base Costs)")
    lines.append("")
    lines.append("| Baseline | Net Sharpe | Net CAGR | Max DD | Trade Count |")
    lines.append("|----------|------------|----------|--------|-------------|")

    base_key = "theta_0.0bps_base"
    if base_key in results["baselines"]:
        for name, metrics in results["baselines"][base_key].items():
            lines.append(f"| {name} | {metrics.get('sharpe', 0):.3f} | {metrics.get('cagr', 0):.4f} | {metrics.get('max_dd', 0):.4f} | {metrics.get('n_trades', 0)} |")

    lines.append("")
    lines.append("## Gate Criteria Assessment (Validation Dry-Run)")
    lines.append("")
    lines.append("| Criterion | Threshold | C1 (HMM) | C2 (HOM) | Pass? |")
    lines.append("|-----------|-----------|----------|----------|-------|")

    c1_base = results["models"]["C1_hmm"]["theta_0.0bps"]["base"]
    c2_base = results["models"]["C2_hom"]["theta_0.0bps"]["base"]

    checks = [
        ("Net Sharpe > 0.5", 0.5, c1_base["net_sharpe_base"], c2_base["net_sharpe_base"]),
        ("Max DD < 20%", -0.20, c1_base["net_max_dd_base"], c2_base["net_max_dd_base"]),
        ("Positive expectancy (per bar)", 0.0, c1_base["expectancy_per_bar_base"], c2_base["expectancy_per_bar_base"]),
        ("Trade count > 100", 100, c1_base["n_trades_base"], c2_base["n_trades_base"]),
        ("Turnover < 500%", 5.0, c1_base["turnover_annualized_base"], c2_base["turnover_annualized_base"]),
    ]

    for name, threshold, c1_val, c2_val in checks:
        if name == "Max DD < 20%":
            c1_pass = c1_val > threshold  # max_dd is negative, so > -0.2 means less drawdown
            c2_pass = c2_val > threshold
        elif name == "Turnover < 500%":
            c1_pass = c1_val < threshold
            c2_pass = c2_val < threshold
        else:
            c1_pass = c1_val > threshold
            c2_pass = c2_val > threshold

        lines.append(f"| {name} | {threshold} | {c1_val:.3f} {'✓' if c1_pass else '✗'} | {c2_val:.3f} {'✓' if c2_pass else '✗'} | {'C1' if c1_pass else ''}{' C2' if c2_pass else ''} |")

    lines.append("")
    lines.append("---")
    lines.append("*This is a validation-only dry-run. No holdout evaluation has been performed.*")
    lines.append("*Results do not constitute evidence for or against any candidate.*")

    output_path.write_text("\n".join(lines))


def main():
    """CLI entry point for validation dry-run."""
    import argparse

    parser = argparse.ArgumentParser(description="Validation-only economic simulation dry-run")
    parser.add_argument("--theta", type=float, nargs="+", default=[0.0, 2.0, 5.0], help="Theta sensitivity in bps")
    parser.add_argument("--output", type=Path, default=Path("research/economic/validation_dryrun"), help="Output directory")
    parser.add_argument("--notional-fraction", type=float, default=0.10, help="Notional fraction per trade")
    args = parser.parse_args()

    config = SimulationConfig(
        theta_bps=0.0,  # Will be overridden per sensitivity run
        notional_fraction=args.notional_fraction,
    )

    run_validation_dryrun(config, theta_sensitivity=args.theta, output_dir=args.output)
    print(f"Validation dry-run complete. Results in {args.output}")


if __name__ == "__main__":
    main()