"""
Protocol-enforcing holdout evaluation runner (T5b/T5c).

Loads frozen protocol/manifest, enforces leakage/integrity controls, and
REFUSES execution by default. Holdout evaluation runs only with explicit
`--execute-holdout` and a matching protocol SHA256 hash.

When authorized, produces protocol-complete holdout artifacts:
- Forecast evaluation: log score/CRPS/PIT summaries and stationary block-bootstrap
  paired comparisons (C1/C2 vs B1/B2) with 95% CIs, p-values, effective n.
- Economic simulation: gross/net metrics for C1/C2 and B3/B4/B5 baselines under
  base/stress costs and predeclared theta sensitivity, with trade ledgers and
  returns series under research/economic/holdout/.
- Populated execution manifest and concise holdout reports.

Holdout period (frozen): 2024-07-01 00:00:00+00:00 .. 2025-12-31 23:00:00+00:00
Candidates: C1 filtered 3-state Gaussian HMM, C2 higher-order Markov (order 2, K=5)

This module must not modify AGENTS.md, MARKOV_RESEARCH_PROMPT.md, or .github/workflows/*.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = REPO_ROOT / "research" / "specifications" / "holdout_evaluation_protocol.md"
MANIFEST_TEMPLATE_PATH = REPO_ROOT / "research" / "specifications" / "holdout_evaluation_manifest_template.json"
DATA_PATH = REPO_ROOT / "data" / "processed" / "features.parquet"
RAW_MANIFEST_PATH = REPO_ROOT / "data" / "raw" / "manifest.json"
HOLDOUT_START = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")
HOLDOUT_END = pd.Timestamp("2025-12-31 23:00:00+00:00", tz="UTC")
TRAIN_END = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")  # bins/edges fit on training only
FORECAST_OUT_DIR = REPO_ROOT / "research" / "forecasts" / "holdout"
ECON_OUT_DIR = REPO_ROOT / "research" / "economic" / "holdout"

# Frozen C1 config (T4/H2)
C1_SEEDS: Tuple[int, ...] = (0, 1, 2)
C1_REFIT_EVERY = 720
C1_EVAL_STRIDE = 4
C1_N_STATES = 3
# Frozen C2 config (H3)
C2_ORDER = 2
C2_K = 5
C2_LAPLACE_ALPHA = 1.0
C2_MIN_PAIR_SAMPLES = 20
C2_EVAL_STRIDE = 4

# Predeclared economic config (protocol / validation dry-run aligned)
THETA_BPS_VALUES: Tuple[float, ...] = (0.0, 2.0, 5.0)
NOTIONAL_FRACTION = 0.10
MAX_GROSS_EXPOSURE = 1.0
COST_BASE = {"taker_fee_bps": 5.0, "half_spread_bps": 1.0, "slippage_bps": 2.0}
COST_STRESS = {"taker_fee_bps": 10.0, "half_spread_bps": 2.0, "slippage_bps": 4.0}
MOMENTUM_LOOKBACK = 24


class HoldoutAuthorizationError(RuntimeError):
    """Raised when holdout execution is not explicitly authorized."""


class HoldoutIntegrityError(ValueError):
    """Raised when a leakage/integrity control is violated."""


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_protocol_hash(protocol_path: Path = PROTOCOL_PATH) -> str:
    if not protocol_path.exists():
        raise FileNotFoundError(f"protocol not found: {protocol_path}")
    return compute_file_sha256(protocol_path)


def load_protocol_text(protocol_path: Path = PROTOCOL_PATH) -> str:
    return protocol_path.read_text(encoding="utf-8")


def load_manifest_template(path: Path = MANIFEST_TEMPLATE_PATH) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_git_sha(repo_root: Path = REPO_ROOT) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo_root), stderr=subprocess.DEVNULL, text=True
        )
        return out.strip()
    except Exception:
        return None


def verify_execution_authorized(
    execute_holdout: bool,
    provided_hash: Optional[str],
    protocol_path: Path = PROTOCOL_PATH,
) -> str:
    """Return protocol hash if explicitly authorized; otherwise raise."""
    expected = compute_protocol_hash(protocol_path)
    if not execute_holdout:
        raise HoldoutAuthorizationError(
            "Holdout execution refused: --execute-holdout not provided. "
            "This runner enforces a locked holdout and will not run by default."
        )
    if not provided_hash:
        raise HoldoutAuthorizationError(
            "Holdout execution refused: --protocol-hash is required with --execute-holdout."
        )
    if provided_hash.strip().lower() != expected.lower():
        raise HoldoutAuthorizationError(
            "Holdout execution refused: provided protocol hash does not match frozen protocol. "
            f"expected={expected} provided={provided_hash.strip().lower()}"
        )
    return expected


def validate_no_lookahead(
    target_timestamp: pd.Timestamp,
    history_end_timestamp: pd.Timestamp,
    holdout_start: pd.Timestamp = HOLDOUT_START,
    holdout_end: pd.Timestamp = HOLDOUT_END,
) -> None:
    """Enforce point-in-time constraints for a single forecast target."""
    if target_timestamp < holdout_start or target_timestamp > holdout_end:
        raise HoldoutIntegrityError(
            f"target {target_timestamp} outside holdout window [{holdout_start}, {holdout_end}]"
        )
    if history_end_timestamp >= target_timestamp:
        raise HoldoutIntegrityError(
            f"lookahead/leakage: history_end {history_end_timestamp} must be < target {target_timestamp}"
        )


def validate_holdout_window(df: pd.DataFrame, holdout_start: pd.Timestamp = HOLDOUT_START, holdout_end: pd.Timestamp = HOLDOUT_END) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    mask = (ts >= holdout_start) & (ts <= holdout_end)
    holdout_df = df.loc[mask].copy()
    if holdout_df.empty:
        raise HoldoutIntegrityError("no rows found in frozen holdout window")
    return holdout_df


def build_execution_manifest(
    template: Dict,
    protocol_hash: str,
    command: str,
    executed_utc: str,
    git_sha: Optional[str],
    features_sha256: Optional[str],
    raw_manifest_sha256: Optional[str],
    holdout_evaluated: bool,
    operator_notes: str = "",
    artifacts: Optional[Dict] = None,
) -> Dict:
    manifest = json.loads(json.dumps(template))  # deep copy
    manifest.setdefault("protocol", {})
    manifest["protocol"]["protocol_sha256"] = protocol_hash
    manifest.setdefault("data_provenance", {})
    manifest["data_provenance"]["features_sha256"] = features_sha256
    manifest["data_provenance"]["raw_manifest_sha256"] = raw_manifest_sha256
    manifest.setdefault("execution", {})
    manifest["execution"]["git_sha"] = git_sha
    manifest["execution"]["command"] = command
    manifest["execution"]["executed_utc"] = executed_utc
    manifest["execution"]["holdout_evaluated"] = bool(holdout_evaluated)
    manifest["execution"]["operator_notes"] = operator_notes
    if artifacts is not None:
        manifest["execution"]["artifacts"] = artifacts
    return manifest


# -------------------------
# Bootstrap / significance
# -------------------------

def _stationary_bootstrap_indices(n: int, block_length: float, n_bootstrap: int, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / max(1.0, float(block_length))
    indices = np.empty((n_bootstrap, n), dtype=int)
    for b in range(n_bootstrap):
        i = int(rng.integers(0, n))
        row = np.empty(n, dtype=int)
        for t in range(n):
            row[t] = i
            if rng.random() < p:
                i = int(rng.integers(0, n))
            else:
                i = (i + 1) % n
        indices[b] = row
    return indices


def bootstrap_paired_differences(
    diffs: np.ndarray,
    n_bootstrap: int = 2000,
    block_length: Optional[float] = None,
    rng_seed: int = 42,
    confidence: float = 0.95,
) -> Dict:
    diffs = np.asarray(diffs, dtype=float)
    n = len(diffs)
    if n == 0:
        return {"n": 0}
    if block_length is None:
        block_length = max(1.0, n ** (1.0 / 3.0))
    rng = np.random.default_rng(rng_seed)
    boot_idx = _stationary_bootstrap_indices(n, float(block_length), n_bootstrap, rng)
    boot_means = np.mean(diffs[boot_idx], axis=1)
    mean_diff = float(np.mean(diffs))
    alpha = 1.0 - confidence
    ci_lower = float(np.percentile(boot_means, 100 * alpha / 2))
    ci_upper = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    # centered bootstrap two-sided p-value for H0: mean=0
    centered = boot_means - np.mean(boot_means)
    p_val = float(np.mean(np.abs(centered) >= abs(mean_diff))) if np.any(np.isfinite(centered)) else float("nan")
    var_iid = float(np.var(diffs, ddof=1) / n) if n > 1 else 0.0
    var_boot = float(np.var(boot_means, ddof=1)) if n_bootstrap > 1 else 0.0
    eff_n = int(np.round(n * var_iid / max(var_boot, 1e-16))) if var_boot > 0 else n
    return {
        "n": int(n),
        "mean_difference": mean_diff,
        "median_difference": float(np.median(diffs)),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "confidence_level": confidence,
        "p_value_two_sided": p_val,
        "effective_sample_size": eff_n,
        "block_length": float(block_length),
        "n_bootstrap": int(n_bootstrap),
        "significant_at_05": bool(ci_lower > 0 or ci_upper < 0),
    }


def gaussian_cdf_from_scores(y: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    var = np.maximum(var, 1e-12)
    z = (y - mu) / np.sqrt(var)
    return 0.5 * (1.0 + erf_vec(z / math.sqrt(2.0)))


def erf_vec(x: np.ndarray) -> np.ndarray:
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-ax * ax)
    return sign * y


def compute_forecast_significance(rows: List[Dict], prefix: str, n_bootstrap: int = 2000) -> Dict:
    if not rows:
        return {"n": 0}
    y = np.array([r["y_true"] for r in rows], dtype=float)
    m_mu = np.array([r.get(f"{prefix}_mu", np.nan) for r in rows], dtype=float)
    m_var = np.array([r.get(f"{prefix}_var", np.nan) for r in rows], dtype=float)
    pit = gaussian_cdf_from_scores(y, m_mu, m_var)

    m_log = np.array([r[f"{prefix}_log"] for r in rows], dtype=float)
    unc_log = np.array([r["unc_log"] for r in rows], dtype=float)
    ewma_log = np.array([r["ewma_log"] for r in rows], dtype=float)
    m_crps = np.array([r[f"{prefix}_crps"] for r in rows], dtype=float)
    unc_crps = np.array([r["unc_crps"] for r in rows], dtype=float)
    ewma_crps = np.array([r["ewma_crps"] for r in rows], dtype=float)

    block_length = max(1.0, len(rows) ** (1.0 / 3.0))
    comparisons = {
        "log_score_model_minus_unconditional": bootstrap_paired_differences(m_log - unc_log, n_bootstrap=n_bootstrap, block_length=block_length),
        "log_score_model_minus_ewma": bootstrap_paired_differences(m_log - ewma_log, n_bootstrap=n_bootstrap, block_length=block_length),
        "crps_unconditional_minus_model": bootstrap_paired_differences(unc_crps - m_crps, n_bootstrap=n_bootstrap, block_length=block_length),
        "crps_ewma_minus_model": bootstrap_paired_differences(ewma_crps - m_crps, n_bootstrap=n_bootstrap, block_length=block_length),
    }
    # lower-is-better for CRPS: positive diff (baseline-model) means model better
    for k, v in comparisons.items():
        if "crps" in k and "n" in v and v["n"]:
            v["direction_note"] = "positive means model better (lower CRPS)"
        elif "log_score" in k and "n" in v and v["n"]:
            v["direction_note"] = "positive means model better (higher log score)"
    return {
        "n": int(len(rows)),
        "pit": {"mean": float(np.mean(pit)), "std": float(np.std(pit)), "ideal_mean": 0.5, "ideal_std": float(1 / math.sqrt(12))},
        "comparisons": comparisons,
        "block_length": float(block_length),
        "n_bootstrap": int(n_bootstrap),
    }


# -------------------------
# Data / forecast execution
# -------------------------

def _load_btc_returns(df: pd.DataFrame) -> pd.DataFrame:
    btc = df[df["symbol"] == "BTCUSDT"].copy()
    btc["timestamp"] = pd.to_datetime(btc["timestamp"], utc=True)
    btc = btc.sort_values("timestamp").reset_index(drop=True)
    btc = btc.dropna(subset=["close"]).copy()
    btc["returns"] = btc["close"].pct_change()
    btc = btc.dropna(subset=["returns"]).reset_index(drop=True)
    return btc


def _collect_holdout_targets(ts: pd.Series, eval_stride: int) -> List[int]:
    idx = np.where((ts >= HOLDOUT_START) & (ts <= HOLDOUT_END))[0]
    idx = idx[:: max(1, int(eval_stride))]
    return [int(i) for i in idx if i >= 1]


def run_c1_holdout_hmm(df: pd.DataFrame) -> Dict:
    """Run frozen C1 (filtered 3-state Gaussian HMM) on locked holdout. Point-in-time only."""
    from src.hmm_walkforward import (
        expanding_unconditional_params,
        ewma_forecast_params,
        filtered_state_probs,
        fit_ordered_hmm,
        forecast_next_from_filtered,
        gaussian_logpdf,
        gaussian_crps,
        mixture_logpdf,
        mixture_crps_grid,
    )

    btc = _load_btc_returns(df)
    ts = btc["timestamp"]
    returns = btc["returns"].to_numpy(dtype=float)
    target_indices = _collect_holdout_targets(ts, C1_EVAL_STRIDE)
    rows = []
    refits = []
    current_model = None
    last_refit_i = None

    for i in target_indices:
        target_ts = pd.Timestamp(ts.iloc[i])
        validate_no_lookahead(target_ts, pd.Timestamp(ts.iloc[i - 1]))
        history_end = i - 1
        need_refit = current_model is None or (history_end - (last_refit_i or 0)) >= C1_REFIT_EVERY
        if need_refit:
            train_slice = returns[: history_end + 1]
            if len(train_slice) < 500:
                continue
            current_model = fit_ordered_hmm(train_slice, seeds=C1_SEEDS)
            last_refit_i = history_end
            refits.append({
                "refit_at_index": int(history_end),
                "refit_timestamp": str(ts.iloc[history_end]),
                "train_size": int(history_end + 1),
                "log_likelihood": float(getattr(current_model, "train_log_likelihood_", np.nan)),
            })
        assert current_model is not None
        hist = returns[: history_end + 1]
        filt = filtered_state_probs(current_model, hist)[-1]
        next_probs, mix_means, mix_vars = forecast_next_from_filtered(current_model, filt)
        hmm_mu = float(np.sum(next_probs * mix_means))
        hmm_var = float(np.sum(next_probs * (mix_vars + mix_means ** 2)) - hmm_mu ** 2)
        hmm_var = max(hmm_var, 1e-12)
        unc_mu, unc_var = expanding_unconditional_params(hist)
        ewma_mu, ewma_var = ewma_forecast_params(hist, lam=0.94)
        y_true = float(returns[i])
        rows.append({
            "timestamp": str(target_ts),
            "y_true": y_true,
            "p_s0": float(next_probs[0]), "p_s1": float(next_probs[1]), "p_s2": float(next_probs[2]),
            "hmm_mu": hmm_mu, "hmm_var": hmm_var,
            "unc_mu": unc_mu, "unc_var": unc_var,
            "ewma_mu": ewma_mu, "ewma_var": ewma_var,
            "hmm_log": float(mixture_logpdf(y_true, next_probs, mix_means, mix_vars)),
            "unc_log": float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0]),
            "ewma_log": float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0]),
            "hmm_crps": float(mixture_crps_grid(y_true, next_probs, mix_means, mix_vars)),
            "unc_crps": float(gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))),
            "ewma_crps": float(gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))),
        })
    return {"model": "C1_hmm", "rows": rows, "refits": refits, "n": len(rows)}


def run_c2_holdout_hom(df: pd.DataFrame) -> Dict:
    """Run frozen C2 (higher-order Markov order 2, K=5) on locked holdout. Point-in-time only."""
    from src.higher_order_markov import (
        expanding_unconditional_params,
        ewma_forecast_params,
        fit_quantile_bins,
        assign_states,
        estimate_transition_counts_order2,
        transition_probs_from_counts_order2,
        state_conditional_params_order2,
        gaussian_logpdf,
        gaussian_crps,
        mixture_logpdf,
        mixture_crps_grid,
    )

    btc = _load_btc_returns(df)
    ts = btc["timestamp"]
    returns = btc["returns"].to_numpy(dtype=float)
    train_mask = ts <= TRAIN_END
    train_returns = returns[train_mask.to_numpy()]
    if len(train_returns) < 500:
        raise HoldoutIntegrityError("insufficient training data for C2 bin fitting")
    edges = fit_quantile_bins(train_returns, C2_K)  # train-fitted only
    all_states = assign_states(returns, edges)
    target_indices = _collect_holdout_targets(ts, C2_EVAL_STRIDE)
    target_indices = [i for i in target_indices if i >= 2]
    rows = []
    for i in target_indices:
        target_ts = pd.Timestamp(ts.iloc[i])
        validate_no_lookahead(target_ts, pd.Timestamp(ts.iloc[i - 1]))
        history_returns = returns[:i]
        history_states = all_states[:i]
        if len(history_returns) < 100:
            continue
        s_prev = int(history_states[i - 2])
        s_curr = int(history_states[i - 1])
        counts = estimate_transition_counts_order2(history_states, C2_K)
        trans = transition_probs_from_counts_order2(counts, alpha=C2_LAPLACE_ALPHA)
        next_probs = np.clip(trans[s_prev, s_curr].copy(), 1e-16, 1.0)
        next_probs = next_probs / next_probs.sum()
        unc_mu, unc_var = expanding_unconditional_params(history_returns)
        ewma_mu, ewma_var = ewma_forecast_params(history_returns)
        pair_means, pair_vars = state_conditional_params_order2(history_returns, history_states, C2_K, unc_mu, unc_var)
        state_means = pair_means[s_curr].copy()
        state_vars = pair_vars[s_curr].copy()
        hom_mu = float(np.sum(next_probs * state_means))
        hom_var = float(max(np.sum(next_probs * (state_vars + state_means ** 2)) - hom_mu ** 2, 1e-10))
        y_true = float(returns[i])
        rows.append({
            "timestamp": str(target_ts), "y_true": y_true,
            "s_prev": s_prev, "s_curr": s_curr,
            **{f"p_s{k}": float(next_probs[k]) for k in range(C2_K)},
            "hom_mu": hom_mu, "hom_var": hom_var,
            "unc_mu": unc_mu, "unc_var": unc_var,
            "ewma_mu": ewma_mu, "ewma_var": ewma_var,
            "hom_log": float(mixture_logpdf(y_true, next_probs, state_means, state_vars)),
            "unc_log": float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0]),
            "ewma_log": float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0]),
            "hom_crps": float(mixture_crps_grid(y_true, next_probs, state_means, state_vars)),
            "unc_crps": float(gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))),
            "ewma_crps": float(gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))),
        })
    return {"model": "C2_hom_order2_k5", "rows": rows, "n": len(rows), "bin_edges": edges.tolist()}


def _summary_metrics(rows: List[Dict], prefix: str) -> Dict:
    if not rows:
        return {"n_obs": 0}
    log_m = np.array([r[f"{prefix}_log"] for r in rows], dtype=float)
    unc_log = np.array([r["unc_log"] for r in rows], dtype=float)
    ewma_log = np.array([r["ewma_log"] for r in rows], dtype=float)
    crps_m = np.array([r[f"{prefix}_crps"] for r in rows], dtype=float)
    unc_crps = np.array([r["unc_crps"] for r in rows], dtype=float)
    ewma_crps = np.array([r["ewma_crps"] for r in rows], dtype=float)

    def s(a):
        return {"mean": float(np.mean(a)), "median": float(np.median(a)), "std": float(np.std(a))}

    return {
        "n_obs": len(rows),
        "log_score_higher_is_better": {prefix: s(log_m), "unconditional_gaussian": s(unc_log), "ewma_gaussian": s(ewma_log)},
        "crps_lower_is_better": {prefix: s(crps_m), "unconditional_gaussian": s(unc_crps), "ewma_gaussian": s(ewma_crps)},
    }


# -------------------------
# Economic simulation (holdout grids)
# -------------------------

def _cost_per_side(cost_model: Dict) -> float:
    return float(cost_model["taker_fee_bps"] + cost_model["half_spread_bps"] + cost_model["slippage_bps"])


def _prepare_econ_df(rows: List[Dict], mu_key: str, var_key: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df.rename(columns={mu_key: "model_mu", var_key: "model_var"})
    return df[["y_true", "model_mu", "model_var"]].copy()


def _align_funding(funding: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    if funding.empty:
        return np.zeros(len(index), dtype=float)
    hourly = funding / 8.0
    aligned = hourly.reindex(index, method="ffill").fillna(0.0)
    return aligned.to_numpy(dtype=float)


def run_economic_on_holdout_grid(
    econ_df: pd.DataFrame,
    funding_values: np.ndarray,
    theta_bps: float,
    cost_model: Dict,
    notional_fraction: float = NOTIONAL_FRACTION,
    max_gross_exposure: float = MAX_GROSS_EXPOSURE,
) -> Tuple[Dict, pd.DataFrame, pd.DataFrame]:
    from src.economic_simulation import compute_signal, apply_sizing, compute_costs, simulate_equity_curve, compute_metrics, CostModel

    if econ_df.empty:
        return {"n_obs": 0, "n_trades": 0}, pd.DataFrame(), pd.DataFrame()
    y_true = econ_df["y_true"].to_numpy(dtype=float)
    mu = econ_df["model_mu"].to_numpy(dtype=float)
    cm = CostModel(**cost_model)
    signal = compute_signal(mu, theta_bps, cm.per_side_bps)
    _, notional = apply_sizing(signal, 1.0, notional_fraction, max_gross_exposure)
    notional_change = np.zeros_like(notional)
    notional_change[0] = notional[0]
    if len(notional_change) > 1:
        notional_change[1:] = np.diff(notional)
    holding_hours = np.ones_like(y_true)
    fee_c, spread_c, slip_c, fund_c = compute_costs(notional_change, cm, funding_values[: len(y_true)], holding_hours)
    gross_eq, net_eq, gross_ret, net_ret, trade_info = simulate_equity_curve(
        y_true, signal, notional, fee_c, spread_c, slip_c, fund_c, 1.0
    )
    metrics = compute_metrics(net_ret, net_eq, trade_info.get("trades", []), fund_c, cm)
    metrics["theta_bps"] = float(theta_bps)
    metrics["cost_per_side_bps"] = float(cm.per_side_bps)
    metrics["cost_model"] = cost_model
    returns_df = pd.DataFrame({
        "timestamp": econ_df.index,
        "y_true": y_true,
        "gross_return": gross_ret,
        "net_return": net_ret,
        "position_notional": notional,
    }).set_index("timestamp")
    trade_rows = []
    for t in trade_info.get("trades", []):
        bar = int(t.get("bar", 0))
        trade_rows.append({
            "bar_index": bar,
            "timestamp": econ_df.index[bar] if 0 <= bar < len(econ_df.index) else None,
            "direction": t.get("direction"),
            "notional_change": t.get("notional_change"),
            "position_before": t.get("position_before"),
            "position_after": t.get("position_after"),
        })
    ledger_df = pd.DataFrame(trade_rows)
    return metrics, ledger_df, returns_df


def run_baselines_on_holdout_grid(
    econ_df: pd.DataFrame,
    funding_values: np.ndarray,
    cost_model: Dict,
    theta_bps_for_momentum: float = 0.0,
) -> Dict[str, Dict]:
    from src.economic_simulation import apply_sizing, compute_costs, simulate_equity_curve, compute_metrics, CostModel
    results: Dict[str, Dict] = {}
    if econ_df.empty:
        return results
    y_true = econ_df["y_true"].to_numpy(dtype=float)
    cm = CostModel(**cost_model)
    holding_hours = np.ones_like(y_true)
    fvals = funding_values[: len(y_true)]

    # B3 no-trade
    sig = np.zeros_like(y_true)
    _, notional = apply_sizing(sig, 1.0, NOTIONAL_FRACTION, MAX_GROSS_EXPOSURE)
    nc = np.zeros_like(notional)
    fee_c, spread_c, slip_c, fund_c = compute_costs(nc, cm, fvals, holding_hours)
    _, net_eq, _, net_ret, ti = simulate_equity_curve(y_true, sig, notional, fee_c, spread_c, slip_c, fund_c, 1.0)
    results["B3_notrade"] = compute_metrics(net_ret, net_eq, ti.get("trades", []), fund_c, cm)

    # B4 buy-hold
    sig = np.ones_like(y_true)
    _, notional = apply_sizing(sig, 1.0, NOTIONAL_FRACTION, MAX_GROSS_EXPOSURE)
    nc = np.zeros_like(notional); nc[0] = notional[0]
    fee_c, spread_c, slip_c, fund_c = compute_costs(nc, cm, fvals, holding_hours)
    _, net_eq, _, net_ret, ti = simulate_equity_curve(y_true, sig, notional, fee_c, spread_c, slip_c, fund_c, 1.0)
    results["B4_buyhold"] = compute_metrics(net_ret, net_eq, ti.get("trades", []), fund_c, cm)

    # B5 momentum (predeclared lookback)
    trailing = pd.Series(y_true).rolling(MOMENTUM_LOOKBACK, min_periods=1).sum().to_numpy()
    sig = np.sign(trailing)
    sig[trailing == 0] = 0
    _, notional = apply_sizing(sig, 1.0, NOTIONAL_FRACTION, MAX_GROSS_EXPOSURE)
    nc = np.zeros_like(notional); nc[0] = notional[0]
    if len(nc) > 1:
        nc[1:] = np.diff(notional)
    fee_c, spread_c, slip_c, fund_c = compute_costs(nc, cm, fvals, holding_hours)
    _, net_eq, _, net_ret, ti = simulate_equity_curve(y_true, sig, notional, fee_c, spread_c, slip_c, fund_c, 1.0)
    results["B5_momentum"] = compute_metrics(net_ret, net_eq, ti.get("trades", []), fund_c, cm)
    return results


def evaluate_economic_holdout(
    forecast_rows_by_model: Dict[str, List[Dict]],
    df_features: pd.DataFrame,
    output_dir: Path = ECON_OUT_DIR,
    theta_values: Sequence[float] = THETA_BPS_VALUES,
) -> Dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    # funding
    funding = pd.Series(dtype=float)
    try:
        btc = df_features[df_features["symbol"] == "BTCUSDT"].copy()
        btc["timestamp"] = pd.to_datetime(btc["timestamp"], utc=True)
        btc = btc.set_index("timestamp").sort_index()
        if "funding_rate" in btc.columns:
            funding = btc["funding_rate"].astype(float).dropna()
    except Exception:
        funding = pd.Series(dtype=float)

    econ_results: Dict = {"config": {
        "theta_bps_values": list(theta_values),
        "notional_fraction": NOTIONAL_FRACTION,
        "max_gross_exposure": MAX_GROSS_EXPOSURE,
        "cost_base": COST_BASE,
        "cost_stress": COST_STRESS,
        "momentum_lookback": MOMENTUM_LOOKBACK,
    }, "models": {}, "baselines": {}, "artifacts": {}}

    # Prepare grids
    grids = {
        "C1": _prepare_econ_df(forecast_rows_by_model.get("C1", []), "hmm_mu", "hmm_var"),
        "C2": _prepare_econ_df(forecast_rows_by_model.get("C2", []), "hom_mu", "hom_var"),
    }

    for model_id, grid in grids.items():
        econ_results["models"][model_id] = {}
        if grid.empty:
            continue
        fvals = _align_funding(funding, grid.index)
        for theta in theta_values:
            econ_results["models"][model_id][f"theta_{theta}bps"] = {}
            for cname, cmodel in [("base", COST_BASE), ("stress", COST_STRESS)]:
                metrics, ledger, rets = run_economic_on_holdout_grid(grid, fvals, theta, cmodel)
                tag = f"{model_id}_theta{theta}bps_{cname}"
                ledger_path = output_dir / f"{tag}_trades.csv"
                returns_path = output_dir / f"{tag}_returns.csv"
                ledger.to_csv(ledger_path, index=False)
                rets.to_csv(returns_path)
                econ_results["models"][model_id][f"theta_{theta}bps"][cname] = metrics
                econ_results["artifacts"][f"{tag}_trades"] = str(ledger_path)
                econ_results["artifacts"][f"{tag}_returns"] = str(returns_path)

    # Baselines on a common grid (use C1 grid if available else C2)
    base_grid = grids["C1"] if not grids["C1"].empty else grids["C2"]
    if not base_grid.empty:
        fvals = _align_funding(funding, base_grid.index)
        for cname, cmodel in [("base", COST_BASE), ("stress", COST_STRESS)]:
            econ_results["baselines"][cname] = run_baselines_on_holdout_grid(base_grid, fvals, cmodel)

    # Compact report
    report_path = output_dir / "holdout_economic_report.md"
    lines = [
        "# Holdout Economic Gate Evaluation (Authorized Run)",
        "",
        f"- Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Holdout: {HOLDOUT_START} to {HOLDOUT_END}",
        f"- Theta values (bps): {list(theta_values)}",
        "- Baselines: B3 no-trade, B4 buy-and-hold, B5 momentum (predeclared).",
        "",
    ]
    for model_id in ["C1", "C2"]:
        lines.append(f"## {model_id}")
        lines.append("")
        lines.append("| Theta (bps) | Cost | Net Sharpe | Net CAGR | Max DD | Hit Rate | Trades | Turnover (ann.) |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        mres = econ_results["models"].get(model_id, {})
        for theta in theta_values:
            for cname in ["base", "stress"]:
                met = mres.get(f"theta_{theta}bps", {}).get(cname, {})
                lines.append(
                    f"| {theta} | {cname} | {met.get('sharpe', 0):.3f} | {met.get('cagr', 0):.4f} | "
                    f"{met.get('max_dd', 0):.4f} | {met.get('hit_rate', 0):.3f} | {met.get('n_trades', 0)} | {met.get('turnover_annualized', 0):.2f} |"
                )
        lines.append("")
    (output_dir / "holdout_economic_results.json").write_text(json.dumps(econ_results, indent=2, default=str) + "\n", encoding="utf-8")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    econ_results["artifacts"]["economic_results_json"] = str(output_dir / "holdout_economic_results.json")
    econ_results["artifacts"]["economic_report_md"] = str(report_path)
    return econ_results


# -------------------------
# Authorized execution
# -------------------------

def execute_holdout(protocol_hash: str, command: str, protocol_path: Path = PROTOCOL_PATH,
                    manifest_template_path: Path = MANIFEST_TEMPLATE_PATH,
                    data_path: Path = DATA_PATH) -> Dict:
    """Execute authorized holdout evaluation for C1/C2 and write protocol-complete artifacts/manifest."""
    template = load_manifest_template(manifest_template_path)
    if not data_path.exists():
        raise FileNotFoundError(f"features data not found: {data_path}")
    df = pd.read_parquet(data_path)
    validate_holdout_window(df)

    FORECAST_OUT_DIR.mkdir(parents=True, exist_ok=True)
    ECON_OUT_DIR.mkdir(parents=True, exist_ok=True)

    c1 = run_c1_holdout_hmm(df)
    c2 = run_c2_holdout_hom(df)

    # Save forecast artifacts
    c1_df = pd.DataFrame(c1["rows"])
    c2_df = pd.DataFrame(c2["rows"])
    c1_csv = FORECAST_OUT_DIR / "c1_hmm_holdout_forecasts.csv"
    c2_csv = FORECAST_OUT_DIR / "c2_hom_holdout_forecasts.csv"
    c1_df.to_csv(c1_csv, index=False)
    c2_df.to_csv(c2_csv, index=False)

    c1_metrics = _summary_metrics(c1["rows"], "hmm")
    c2_metrics = _summary_metrics(c2["rows"], "hom")
    c1_sig = compute_forecast_significance(c1["rows"], "hmm", n_bootstrap=2000)
    c2_sig = compute_forecast_significance(c2["rows"], "hom", n_bootstrap=2000)
    significance_payload = {
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": protocol_hash,
        "c1": c1_sig,
        "c2": c2_sig,
        "notes": "Stationary block bootstrap (n^(1/3) block) paired comparisons vs unconditional/EWMA baselines on holdout forecast grid.",
    }
    significance_path = FORECAST_OUT_DIR / "holdout_forecast_significance.json"
    with open(significance_path, "w", encoding="utf-8") as f:
        json.dump(significance_payload, f, indent=2)

    metrics_payload = {
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": protocol_hash,
        "holdout_start": str(HOLDOUT_START),
        "holdout_end": str(HOLDOUT_END),
        "c1": {"metrics": c1_metrics, "significance": c1_sig, "refits": len(c1.get("refits", [])), "artifact": str(c1_csv)},
        "c2": {"metrics": c2_metrics, "significance": c2_sig, "artifact": str(c2_csv)},
    }
    metrics_path = FORECAST_OUT_DIR / "holdout_forecast_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)

    # Economic gate artifacts
    econ_payload = evaluate_economic_holdout({"C1": c1["rows"], "C2": c2["rows"]}, df, output_dir=ECON_OUT_DIR)

    executed_utc = datetime.now(timezone.utc).isoformat()
    git_sha = get_git_sha()
    features_sha = compute_file_sha256(data_path) if data_path.exists() else None
    raw_sha = compute_file_sha256(RAW_MANIFEST_PATH) if RAW_MANIFEST_PATH.exists() else None
    artifacts = {
        "c1_csv": str(c1_csv),
        "c2_csv": str(c2_csv),
        "forecast_metrics_json": str(metrics_path),
        "forecast_significance_json": str(significance_path),
        "forecast_report_md": str(FORECAST_OUT_DIR / "holdout_forecast_report.md"),
        "economic_results_json": str(ECON_OUT_DIR / "holdout_economic_results.json"),
        "economic_report_md": str(ECON_OUT_DIR / "holdout_economic_report.md"),
    }
    artifacts.update({k: v for k, v in econ_payload.get("artifacts", {}).items() if isinstance(v, str)})
    manifest = build_execution_manifest(
        template=template,
        protocol_hash=protocol_hash,
        command=command,
        executed_utc=executed_utc,
        git_sha=git_sha,
        features_sha256=features_sha,
        raw_manifest_sha256=raw_sha,
        holdout_evaluated=True,
        operator_notes="Authorized holdout execution completed by holdout_runner (forecast metrics/significance + economic gate artifacts).",
        artifacts=artifacts,
    )
    manifest_path = FORECAST_OUT_DIR / "holdout_execution_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Forecast report
    def _fmt_sig(sig: Dict, key: str) -> str:
        c = sig.get("comparisons", {}).get(key, {})
        if not c or c.get("n", 0) == 0:
            return "n/a"
        return f"mean={c['mean_difference']:.6g}, 95%CI=[{c['ci_lower']:.6g},{c['ci_upper']:.6g}], p={c['p_value_two_sided']:.4f}, eff_n={c['effective_sample_size']}"

    report_lines = [
        "# Holdout Forecast Evaluation (Authorized Run)",
        "",
        f"- Executed UTC: {executed_utc}",
        f"- Protocol SHA256: {protocol_hash}",
        f"- Git SHA: {git_sha}",
        f"- Holdout: {HOLDOUT_START} to {HOLDOUT_END}",
        f"- C1 forecasts: {c1['n']} -> {c1_csv}",
        f"- C2 forecasts: {c2['n']} -> {c2_csv}",
        f"- Metrics: {metrics_path}",
        f"- Significance: {significance_path}",
        f"- Manifest: {manifest_path}",
        "",
        "## C1 (HMM) paired comparisons",
        f"- Log score vs unconditional: {_fmt_sig(c1_sig, 'log_score_model_minus_unconditional')}",
        f"- Log score vs EWMA: {_fmt_sig(c1_sig, 'log_score_model_minus_ewma')}",
        f"- CRPS vs unconditional (baseline-model): {_fmt_sig(c1_sig, 'crps_unconditional_minus_model')}",
        f"- CRPS vs EWMA (baseline-model): {_fmt_sig(c1_sig, 'crps_ewma_minus_model')}",
        "",
        "## C2 (HOM) paired comparisons",
        f"- Log score vs unconditional: {_fmt_sig(c2_sig, 'log_score_model_minus_unconditional')}",
        f"- Log score vs EWMA: {_fmt_sig(c2_sig, 'log_score_model_minus_ewma')}",
        f"- CRPS vs unconditional (baseline-model): {_fmt_sig(c2_sig, 'crps_unconditional_minus_model')}",
        f"- CRPS vs EWMA (baseline-model): {_fmt_sig(c2_sig, 'crps_ewma_minus_model')}",
        "",
        "All forecasts generated with point-in-time expanding history, filtered inference for C1, and train-fitted bins for C2. Economic gate artifacts written under research/economic/holdout/.",
    ]
    (FORECAST_OUT_DIR / "holdout_forecast_report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {"manifest": manifest, "metrics": metrics_payload, "significance": significance_payload, "economic": econ_payload, "artifacts": artifacts}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Protocol-enforcing holdout evaluation runner (refuses by default)")
    p.add_argument("--execute-holdout", action="store_true", help="Explicitly authorize holdout execution (required)")
    p.add_argument("--protocol-hash", type=str, default=None, help="SHA256 of frozen protocol file (required with --execute-holdout)")
    p.add_argument("--protocol-path", type=Path, default=PROTOCOL_PATH, help="Path to frozen protocol markdown")
    p.add_argument("--manifest-template", type=Path, default=MANIFEST_TEMPLATE_PATH, help="Path to manifest template JSON")
    p.add_argument("--data-path", type=Path, default=DATA_PATH, help="Path to processed features parquet")
    p.add_argument("--print-protocol-hash", action="store_true", help="Print expected protocol hash and exit")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.print_protocol_hash:
        print(compute_protocol_hash(args.protocol_path))
        return 0
    try:
        protocol_hash = verify_execution_authorized(
            execute_holdout=args.execute_holdout,
            provided_hash=args.protocol_hash,
            protocol_path=args.protocol_path,
        )
    except (HoldoutAuthorizationError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        return 2

    command = " ".join([Path(sys.argv[0]).name] + (list(argv) if argv is not None else sys.argv[1:]))
    result = execute_holdout(
        protocol_hash=protocol_hash,
        command=command,
        protocol_path=args.protocol_path,
        manifest_template_path=args.manifest_template,
        data_path=args.data_path,
    )
    print(json.dumps({"status": "executed", "protocol_sha256": protocol_hash, "artifacts": result["artifacts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
