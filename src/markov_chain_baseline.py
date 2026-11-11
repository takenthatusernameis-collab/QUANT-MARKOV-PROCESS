#!/usr/bin/env python3
"""
Task T3 (H1): Finite-state Markov chain baseline on validation period.

- BTCUSDT 1h returns from data/processed/features.parquet
- Discretize returns into K states via quantiles or k-means on training data
- Expanding walk-forward: estimate transition matrix on history up to t, forecast t+1
- 1-step-ahead state probabilities and implied return distribution forecast
- Validation window: 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00
- Holdout (>=2024-07-01) never used
"""

from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:
    plt = None

try:
    from sklearn.cluster import KMeans
except Exception as e:
    raise SystemExit(f"scikit-learn is required: {e}")

DATA_PATH = Path("data/processed/features.parquet")
OUT_DIR = Path("research/forecasts")
FIG_DIR = OUT_DIR / "figures"

TRAIN_END = pd.Timestamp("2023-12-31 00:00:00", tz="UTC")
VAL_START = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
VAL_END = pd.Timestamp("2024-06-30 00:00:00", tz="UTC")
HOLDOUT_START = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")

DEFAULT_N_STATES = 3
DEFAULT_REFIT_EVERY = 720
DEFAULT_EVAL_STRIDE = 4
DISCRETIZATION_METHODS = ("quantile", "kmeans")


@dataclass
class MarkovForecastResult:
    timestamp: pd.Timestamp
    y_true: float
    mc_state_probs_next: np.ndarray
    mc_state_means: np.ndarray
    mc_state_vars: np.ndarray
    mc_mu: float
    mc_var: float
    unc_mu: float
    unc_var: float
    ewma_mu: float
    ewma_var: float
    realized_state: Optional[int]
    mc_log: float = 0.0
    unc_log: float = 0.0
    ewma_log: float = 0.0
    mc_crps: float = 0.0
    unc_crps: float = 0.0
    ewma_crps: float = 0.0


def load_btc_returns(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df["symbol"] == "BTCUSDT"].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df[["timestamp", "returns"]].copy()
    df = df.dropna(subset=["returns"]).reset_index(drop=True)
    return df


def split_indices(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    ts = df["timestamp"]
    train_idx = np.where(ts <= TRAIN_END)[0]
    val_idx = np.where((ts >= VAL_START) & (ts <= VAL_END))[0]
    holdout_idx = np.where(ts >= HOLDOUT_START)[0]
    return {"train": train_idx, "val": val_idx, "holdout": holdout_idx}


def discretize_returns(
    returns: np.ndarray,
    n_states: int,
    method: str = "quantile",
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Discretize returns into states.

    Returns:
        state_labels: array of state assignments for each return
        state_means: mean return per state
        state_vars: variance per state
    """
    n = len(returns)
    if method == "quantile":
        # Quantile-based binning on training data
        quantiles = np.linspace(0, 1, n_states + 1)[1:-1]
        bins = np.quantile(returns, quantiles)
        bins = np.concatenate([[-np.inf], bins, [np.inf]])
        state_labels = np.digitize(returns, bins) - 1
        state_labels = np.clip(state_labels, 0, n_states - 1)
    elif method == "kmeans":
        # K-means clustering on returns (reshaped for 1D)
        km = KMeans(n_clusters=n_states, random_state=random_state, n_init=10)
        state_labels = km.fit_predict(returns.reshape(-1, 1))
        # Order clusters by mean return
        centers = km.cluster_centers_.flatten()
        order = np.argsort(centers)
        remap = {old: new for new, old in enumerate(order)}
        state_labels = np.array([remap[s] for s in state_labels])
    else:
        raise ValueError(f"Unknown discretization method: {method}")

    # Compute state statistics
    state_means = np.zeros(n_states)
    state_vars = np.zeros(n_states)
    for s in range(n_states):
        mask = state_labels == s
        if np.any(mask):
            state_means[s] = np.mean(returns[mask])
            state_vars[s] = np.var(returns[mask], ddof=1) if np.sum(mask) > 1 else np.var(returns) + 1e-8
        else:
            state_means[s] = 0.0
            state_vars[s] = np.var(returns) + 1e-8
    state_vars = np.maximum(state_vars, 1e-12)
    return state_labels, state_means, state_vars


def estimate_transition_matrix(state_seq: np.ndarray, n_states: int) -> np.ndarray:
    """Estimate first-order transition matrix from state sequence."""
    transmat = np.ones((n_states, n_states)) * 1e-6  # Small pseudocount for regularization
    for i in range(len(state_seq) - 1):
        transmat[state_seq[i], state_seq[i + 1]] += 1
    transmat = transmat / transmat.sum(axis=1, keepdims=True)
    return transmat


def forecast_next_state_probs(current_state: int, transmat: np.ndarray) -> np.ndarray:
    """1-step-ahead state probabilities from current state."""
    probs = transmat[current_state].copy()
    probs = np.clip(probs, 1e-16, 1.0)
    probs = probs / probs.sum()
    return probs


def mixture_logpdf(y: float, probs: np.ndarray, means: np.ndarray, vars_: np.ndarray) -> float:
    """Log PDF of Gaussian mixture at point y."""
    var = np.maximum(vars_, 1e-12)
    log_comp = -0.5 * (np.log(2 * np.pi * var) + (y - means) ** 2 / var) + np.log(np.clip(probs, 1e-16, 1.0))
    m = np.max(log_comp)
    return float(m + np.log(np.sum(np.exp(log_comp - m))))


def gaussian_logpdf(y: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    var = np.maximum(var, 1e-12)
    return -0.5 * (np.log(2 * np.pi * var) + (y - mu) ** 2 / var)


def gaussian_crps(y: float, mu: float, sigma: float) -> float:
    if sigma <= 1e-12:
        return float(abs(y - mu))
    from math import erf, sqrt, pi
    z = (y - mu) / sigma
    phi = (1.0 / sqrt(2 * pi)) * math.exp(-0.5 * z * z)
    Phi = 0.5 * (1.0 + erf(z / sqrt(2)))
    return float(sigma * (z * (2 * Phi - 1) + 2 * phi - 1 / sqrt(pi)))


def mixture_crps_grid(y: float, probs: np.ndarray, means: np.ndarray, vars_: np.ndarray) -> float:
    stds = np.sqrt(np.maximum(vars_, 1e-12))
    lo = min(y, float(np.min(means - 6 * stds)))
    hi = max(y, float(np.max(means + 6 * stds)))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        mu = float(np.sum(probs * means))
        var = float(np.sum(probs * (vars_ + means ** 2)) - mu ** 2)
        return gaussian_crps(y, mu, math.sqrt(max(var, 1e-12)))
    grid = np.linspace(lo, hi, 401)
    cdf = np.zeros_like(grid)
    for p, m, s in zip(probs, means, stds):
        z = (grid - m) / max(s, 1e-12)
        cdf += p * 0.5 * (1.0 + erf_vec(z / math.sqrt(2.0)))
    indicator = (grid >= y).astype(float)
    trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")
    return float(trapz((cdf - indicator) ** 2, grid))


def erf_vec(x: np.ndarray) -> np.ndarray:
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-ax * ax)
    return sign * y


def expanding_unconditional_params(history: np.ndarray) -> Tuple[float, float]:
    mu = float(np.mean(history))
    var = float(np.var(history, ddof=1)) if len(history) > 1 else float(np.var(history) + 1e-8)
    var = max(var, 1e-10)
    return mu, var


def ewma_forecast_params(history: np.ndarray, lam: float = 0.94) -> Tuple[float, float]:
    if len(history) == 0:
        return 0.0, 1e-6
    mu = float(np.mean(history))
    r = history - mu
    if len(r) == 1:
        var = float(r[0] ** 2 + 1e-8)
    else:
        var = float(np.var(r, ddof=1))
        for x in r[-500:]:
            var = lam * var + (1 - lam) * float(x ** 2)
    var = max(var, 1e-10)
    return mu, var


def run_markov_chain_walkforward(
    df: pd.DataFrame,
    n_states: int = DEFAULT_N_STATES,
    discretization: str = "quantile",
    refit_every: int = DEFAULT_REFIT_EVERY,
    val_start: pd.Timestamp = VAL_START,
    val_end: pd.Timestamp = VAL_END,
    eval_stride: int = DEFAULT_EVAL_STRIDE,
) -> Dict:
    splits = split_indices(df)
    val_idx = [i for i in splits["val"] if val_start <= df.loc[i, "timestamp"] <= val_end]
    val_idx = val_idx[:: max(1, int(eval_stride))]
    if not val_idx:
        raise ValueError("no validation indices found")
    if len(splits["holdout"]) and max(val_idx) >= min(splits["holdout"]):
        raise AssertionError("validation indices overlap holdout")

    returns = df["returns"].to_numpy(dtype=float)
    timestamps = pd.to_datetime(df["timestamp"], utc=True)

    # Initial discretization on training data
    train_returns = returns[splits["train"]]
    init_labels, init_means, init_vars = discretize_returns(train_returns, n_states, discretization)
    init_transmat = estimate_transition_matrix(init_labels, n_states)

    results: List[MarkovForecastResult] = []
    refit_records = []
    current_transmat = init_transmat
    current_means = init_means
    current_vars = init_vars
    current_labels = init_labels
    last_refit_i = splits["train"][-1]

    for i in val_idx:
        if i + 1 >= len(df):
            break
        target_ts = timestamps.iloc[i + 1]
        if target_ts >= HOLDOUT_START:
            break

        need_refit = (i - last_refit_i) >= refit_every
        if need_refit:
            # Re-discretize and re-estimate on all data up to i
            hist_returns = returns[: i + 1]
            current_labels, current_means, current_vars = discretize_returns(hist_returns, n_states, discretization)
            current_transmat = estimate_transition_matrix(current_labels, n_states)
            last_refit_i = i
            refit_records.append({
                "refit_at_index": int(i),
                "refit_timestamp": str(timestamps.iloc[i]),
                "train_size": int(i + 1),
                "transmat": current_transmat.tolist(),
                "means": current_means.tolist(),
                "vars": current_vars.tolist(),
                "state_counts": np.bincount(current_labels, minlength=n_states).tolist(),
            })

        # Current state is the state of the last observation in history
        current_state = int(current_labels[-1]) if len(current_labels) > 0 else 0

        # 1-step-ahead state probabilities
        next_probs = forecast_next_state_probs(current_state, current_transmat)

        # Mixture moments
        mc_mu = float(np.sum(next_probs * current_means))
        mc_var = float(np.sum(next_probs * (current_vars + current_means ** 2)) - mc_mu ** 2)
        mc_var = max(mc_var, 1e-12)

        # Baselines
        hist = returns[: i + 1]
        unc_mu, unc_var = expanding_unconditional_params(hist)
        ewma_mu, ewma_var = ewma_forecast_params(hist, lam=0.94)

        # Realized state under current model (diagnostic)
        next_state = np.random.default_rng(i).choice(n_states, p=next_probs)  # placeholder for argmax
        realized_state = int(np.argmax(next_probs))

        y_true = float(returns[i + 1])
        mc_log = mixture_logpdf(y_true, next_probs, current_means, current_vars)
        unc_log = float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0])
        ewma_log = float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0])
        mc_crps = mixture_crps_grid(y_true, next_probs, current_means, current_vars)
        unc_crps = gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))
        ewma_crps = gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))

        results.append(MarkovForecastResult(
            timestamp=target_ts,
            y_true=y_true,
            mc_state_probs_next=next_probs,
            mc_state_means=current_means,
            mc_state_vars=current_vars,
            mc_mu=mc_mu,
            mc_var=mc_var,
            unc_mu=unc_mu,
            unc_var=unc_var,
            ewma_mu=ewma_mu,
            ewma_var=ewma_var,
            realized_state=realized_state,
            mc_log=mc_log,
            unc_log=unc_log,
            ewma_log=ewma_log,
            mc_crps=mc_crps,
            unc_crps=unc_crps,
            ewma_crps=ewma_crps,
        ))

    metrics = compute_metrics(results)
    stability = summarize_refits(refit_records, n_states)
    payload = {
        "config": {
            "symbol": "BTCUSDT",
            "frequency": "1h",
            "n_states": n_states,
            "discretization": discretization,
            "refit_every": int(refit_every),
            "eval_stride": int(eval_stride),
            "train_end": str(TRAIN_END),
            "val_start": str(val_start),
            "val_end": str(val_end),
            "holdout_start": str(HOLDOUT_START),
        },
        "counts": {
            "validation_forecasts": len(results),
            "refits": len(refit_records),
        },
        "metrics": metrics,
        "refit_stability": stability,
        "refits": refit_records,
        "forecast_rows_sample_head": [row_to_dict(r) for r in results[:5]],
        "forecast_rows_sample_tail": [row_to_dict(r) for r in results[-5:]],
    }
    return {"payload": payload, "results": results, "refits": refit_records}


def row_to_dict(r: MarkovForecastResult) -> Dict:
    return {
        "timestamp": str(r.timestamp),
        "y_true": r.y_true,
        "mc_state_probs_next": r.mc_state_probs_next.tolist(),
        "mc_state_means": r.mc_state_means.tolist(),
        "mc_state_vars": r.mc_state_vars.tolist(),
        "mc_mu": r.mc_mu,
        "mc_var": r.mc_var,
        "unc_mu": r.unc_mu,
        "unc_var": r.unc_var,
        "ewma_mu": r.ewma_mu,
        "ewma_var": r.ewma_var,
        "realized_state_diagnostic": r.realized_state,
        "mc_log": r.mc_log,
        "unc_log": r.unc_log,
        "ewma_log": r.ewma_log,
        "mc_crps": r.mc_crps,
        "unc_crps": r.unc_crps,
        "ewma_crps": r.ewma_crps,
    }


def compute_metrics(results: List[MarkovForecastResult]) -> Dict:
    mc_log = np.array([r.mc_log for r in results], dtype=float)
    unc_log = np.array([r.unc_log for r in results], dtype=float)
    ewma_log = np.array([r.ewma_log for r in results], dtype=float)
    mc_crps = np.array([r.mc_crps for r in results], dtype=float)
    unc_crps = np.array([r.unc_crps for r in results], dtype=float)
    ewma_crps = np.array([r.ewma_crps for r in results], dtype=float)
    brier = []
    slog = []
    pit_mc = []

    for r in results:
        if r.realized_state is not None:
            brier.append(brier_score_state(r.mc_state_probs_next, r.realized_state))
            slog.append(state_log_loss(r.mc_state_probs_next, r.realized_state))
        cdf = 0.0
        for p, m, v in zip(r.mc_state_probs_next, r.mc_state_means, r.mc_state_vars):
            s = math.sqrt(max(v, 1e-12))
            z = (r.y_true - m) / s
            cdf += float(p) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        pit_mc.append(float(np.clip(cdf, 0.0, 1.0)))

    def stats(arr):
        a = np.asarray(arr, dtype=float)
        return {"mean": float(np.mean(a)), "median": float(np.median(a)), "std": float(np.std(a))}

    pit = np.asarray(pit_mc)
    pit_hist, pit_edges = np.histogram(pit, bins=10, range=(0, 1), density=True) if len(pit) else ([], [])
    return {
        "log_score_higher_is_better": {
            "markov_chain_mixture": stats(mc_log),
            "unconditional_gaussian": stats(unc_log),
            "ewma_gaussian": stats(ewma_log),
        },
        "crps_lower_is_better": {
            "markov_chain_mixture": stats(mc_crps),
            "unconditional_gaussian": stats(unc_crps),
            "ewma_gaussian": stats(ewma_crps),
        },
        "state_probability_diagnostic_model_dependent": {
            "brier_lower_is_better": stats(brier) if brier else None,
            "log_loss_lower_is_better": stats(slog) if slog else None,
            "note": "Realized state is argmax predicted prob at t+1 under each refit model; diagnostic only, not ground truth.",
        },
        "pit_markov_chain": {
            "mean": float(np.mean(pit)) if len(pit) else None,
            "std": float(np.std(pit)) if len(pit) else None,
            "hist_density": pit_hist.tolist() if len(pit) else [],
            "bin_edges": pit_edges.tolist() if len(pit) else [],
        },
        "n_obs": int(len(mc_log)),
    }


def brier_score_state(probs: np.ndarray, realized_state: int) -> float:
    n_states = len(probs)
    y = np.zeros(n_states)
    y[int(realized_state)] = 1.0
    return float(np.sum((probs - y) ** 2))


def state_log_loss(probs: np.ndarray, realized_state: int) -> float:
    p = float(np.clip(probs[int(realized_state)], 1e-16, 1.0))
    return float(-np.log(p))


def summarize_refits(refits: List[Dict], n_states: int) -> Dict:
    if not refits:
        return {}
    trans = np.array([r["transmat"] for r in refits], dtype=float)
    means = np.array([r["means"] for r in refits], dtype=float)
    vars_ = np.array([r["vars"] for r in refits], dtype=float)
    counts = np.array([r["state_counts"] for r in refits], dtype=float)
    return {
        "n_refits": len(refits),
        "transmat_mean": trans.mean(axis=0).tolist(),
        "transmat_std": trans.std(axis=0).tolist(),
        "state_means_mean": means.mean(axis=0).tolist(),
        "state_means_std": means.std(axis=0).tolist(),
        "state_vars_mean": vars_.mean(axis=0).tolist(),
        "state_vars_std": vars_.std(axis=0).tolist(),
        "state_counts_mean": counts.mean(axis=0).tolist(),
        "state_counts_std": counts.std(axis=0).tolist(),
    }


def save_outputs(
    payload: Dict,
    results: List[MarkovForecastResult],
    refits: List[Dict],
    out_dir: Path = OUT_DIR,
    n_states: int = DEFAULT_N_STATES,
    discretization: str = "quantile",
) -> None:
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    base = f"h1_markov_chain_validation_{discretization}_k{n_states}"
    with open(out_dir / f"{base}_results.json", "w") as f:
        json.dump(payload, f, indent=2)

    rows = []
    for r in results:
        row = {
            "timestamp": r.timestamp,
            "y_true": r.y_true,
            "mc_mu": r.mc_mu,
            "mc_var": r.mc_var,
            "unc_mu": r.unc_mu,
            "unc_var": r.unc_var,
            "ewma_mu": r.ewma_mu,
            "ewma_var": r.ewma_var,
            "mc_log": r.mc_log,
            "unc_log": r.unc_log,
            "ewma_log": r.ewma_log,
            "mc_crps": r.mc_crps,
            "unc_crps": r.unc_crps,
            "ewma_crps": r.ewma_crps,
        }
        for s in range(n_states):
            row[f"p_s{s}"] = float(r.mc_state_probs_next[s])
            row[f"mean_s{s}"] = float(r.mc_state_means[s])
            row[f"var_s{s}"] = float(r.mc_state_vars[s])
        rows.append(row)
    pd.DataFrame(rows).to_csv(out_dir / f"{base}_forecasts.csv", index=False)

    if plt is not None and results:
        ts = [r.timestamp for r in results]
        p = np.array([r.mc_state_probs_next for r in results])
        fig, ax = plt.subplots(figsize=(12, 4))
        for s in range(n_states):
            ax.plot(ts, p[:, s], label=f"P(S{s})", linewidth=0.8)
        ax.set_title(f"Markov Chain 1-step-ahead state probabilities (validation, K={n_states}, {discretization})")
        ax.set_ylabel("Probability")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_dir / f"{base}_next_state_probs.png", dpi=150)
        plt.close(fig)

        pit = []
        for r in results:
            cdf = 0.0
            for pr, m, v in zip(r.mc_state_probs_next, r.mc_state_means, r.mc_state_vars):
                s = math.sqrt(max(v, 1e-12))
                z = (r.y_true - m) / s
                cdf += float(pr) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            pit.append(cdf)
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(pit, bins=10, range=(0, 1), density=True, alpha=0.8, color="#4c78a8")
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
        ax.set_title(f"Markov Chain mixture PIT (validation, K={n_states}, {discretization})")
        ax.set_xlabel("PIT")
        ax.set_ylabel("Density")
        fig.tight_layout()
        fig.savefig(fig_dir / f"{base}_pit_hist.png", dpi=150)
        plt.close(fig)

    write_markdown_report(payload, out_dir / f"{base}.md", n_states, discretization)


def write_markdown_report(payload: Dict, path: Path, n_states: int, discretization: str) -> None:
    m = payload["metrics"]
    c = payload["config"]
    counts = payload["counts"]
    stab = payload.get("refit_stability", {})
    lines = []
    lines.append(f"# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, K={n_states}, {discretization})")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Symbol/Freq:** {c['symbol']} / {c['frequency']}")
    lines.append(f"**Validation window:** {c['val_start']} to {c['val_end']} (holdout >= {c['holdout_start']} excluded)")
    lines.append(f"**Model:** {c['n_states']}-state first-order Markov chain ({c['discretization']} discretization); refit every {c['refit_every']} bars on expanding history; eval_stride={c.get('eval_stride',1)}")
    lines.append("")
    lines.append("## Scope and leakage controls")
    lines.append("- Expanding fit uses returns up to time *t* only; forecast targets *t+1* in validation window.")
    lines.append("- State discretization fitted on training data only (or expanding history at each refit).")
    lines.append("- Locked holdout period (>= 2024-07-01) not used for fitting, selection, or evaluation.")
    lines.append("")
    lines.append("## Baselines")
    lines.append("- **Unconditional Gaussian:** expanding mean/variance of historical returns up to *t*.")
    lines.append("- **EWMA Gaussian (RiskMetrics-style):** expanding mean with EWMA variance (lambda=0.94) on demeaned returns up to *t*.")
    lines.append("")
    lines.append("## Forecast metrics (validation)")
    lines.append(f"Observations: {counts['validation_forecasts']} | Refits: {counts['refits']}")
    lines.append("")
    ls = m["log_score_higher_is_better"]
    cr = m["crps_lower_is_better"]
    lines.append("### Log score (mean, higher is better)")
    for k in ["markov_chain_mixture", "unconditional_gaussian", "ewma_gaussian"]:
        lines.append(f"- {k}: {ls[k]['mean']:.6f} (median {ls[k]['median']:.6f})")
    lines.append("")
    lines.append("### CRPS (mean, lower is better)")
    for k in ["markov_chain_mixture", "unconditional_gaussian", "ewma_gaussian"]:
        lines.append(f"- {k}: {cr[k]['mean']:.6e} (median {cr[k]['median']:.6e})")
    lines.append("")
    sd = m.get("state_probability_diagnostic_model_dependent", {})
    lines.append("### State-probability diagnostic (model-dependent realized state)")
    lines.append(f"- {sd.get('note','')}")
    if sd.get("brier_lower_is_better"):
        lines.append(f"- Brier (next-state, diagnostic): {sd['brier_lower_is_better']['mean']:.6f}")
    if sd.get("log_loss_lower_is_better"):
        lines.append(f"- Log loss (next-state, diagnostic): {sd['log_loss_lower_is_better']['mean']:.6f}")
    lines.append("")
    pit = m.get("pit_markov_chain", {})
    lines.append("### Calibration diagnostic")
    lines.append(f"- Markov chain mixture PIT mean={pit.get('mean')} std={pit.get('std')} (ideal uniform: mean 0.5, std ~0.289)")
    lines.append("")
    lines.append("## Refitting stability / regime occupancy proxy")
    if stab:
        lines.append(f"- Refits: {stab.get('n_refits')}")
        lines.append(f"- State mean estimates mean across refits: {stab.get('state_means_mean')}")
        lines.append(f"- State mean estimates std across refits: {stab.get('state_means_std')}")
        lines.append(f"- State variance estimates mean across refits: {stab.get('state_vars_mean')}")
        lines.append(f"- State variance estimates std across refits: {stab.get('state_vars_std')}")
        lines.append(f"- Mean state counts across refits: {stab.get('state_counts_mean')}")
    else:
        lines.append("- No refit stability summary available.")
    lines.append("")
    lines.append("## Artifacts")
    lines.append(f"- `research/forecasts/h1_markov_chain_validation_{discretization}_k{n_states}_results.json`")
    lines.append(f"- `research/forecasts/h1_markov_chain_validation_{discretization}_k{n_states}_forecasts.csv`")
    lines.append(f"- `research/forecasts/figures/h1_markov_chain_validation_{discretization}_k{n_states}_next_state_probs.png`")
    lines.append(f"- `research/forecasts/figures/h1_markov_chain_validation_{discretization}_k{n_states}_pit_hist.png`")
    lines.append("")
    lines.append("## Interpretation notes")
    lines.append("- Validation-only H1 groundwork; not a trading backtest and not a final holdout evaluation.")
    lines.append("- Discretization method and state count are hyperparameters; sensitivity to these should be evaluated.")
    lines.append("- Realized Markov states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison.")
    path.write_text("\n".join(lines) + "\n")


def run_all_configs():
    """Run Markov chain baseline for multiple state counts and discretization methods."""
    df = load_btc_returns(DATA_PATH)

    configs = [
        {"n_states": 3, "discretization": "quantile"},
        {"n_states": 5, "discretization": "quantile"},
        {"n_states": 7, "discretization": "quantile"},
        {"n_states": 3, "discretization": "kmeans"},
        {"n_states": 5, "discretization": "kmeans"},
        {"n_states": 7, "discretization": "kmeans"},
    ]

    all_summaries = []
    for cfg in configs:
        print(f"Running Markov chain: K={cfg['n_states']}, discretization={cfg['discretization']}...")
        out = run_markov_chain_walkforward(
            df,
            n_states=cfg["n_states"],
            discretization=cfg["discretization"],
            refit_every=720,
            eval_stride=4,
        )
        save_outputs(out["payload"], out["results"], out["refits"], OUT_DIR, cfg["n_states"], cfg["discretization"])
        summary = {
            "n_states": cfg["n_states"],
            "discretization": cfg["discretization"],
            "validation_forecasts": out["payload"]["counts"]["validation_forecasts"],
            "refits": out["payload"]["counts"]["refits"],
            "log_score": out["payload"]["metrics"]["log_score_higher_is_better"]["markov_chain_mixture"]["mean"],
            "crps": out["payload"]["metrics"]["crps_lower_is_better"]["markov_chain_mixture"]["mean"],
        }
        all_summaries.append(summary)
        print(f"  Forecasts: {summary['validation_forecasts']}, Log Score: {summary['log_score']:.6f}, CRPS: {summary['crps']:.6e}")

    # Save summary
    with open(OUT_DIR / "h1_markov_chain_summary.json", "w") as f:
        json.dump({"configs": all_summaries, "generated": datetime.now(timezone.utc).isoformat()}, f, indent=2)

    return all_summaries


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    summaries = run_all_configs()
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()