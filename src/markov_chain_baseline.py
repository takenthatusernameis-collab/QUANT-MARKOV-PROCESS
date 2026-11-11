#!/usr/bin/env python3
"""
Task T3 (H1): Finite-state Markov chain baseline (validation only).

- BTCUSDT 1h returns from data/processed/features.parquet
- Discretize returns into K states using quantile bins fitted on training data only
- Expanding transition matrix estimated from history up to t
- 1-step-ahead state probabilities and implied return distribution forecast for t+1
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
except Exception:  # pragma: no cover
    plt = None

DATA_PATH = Path("data/processed/features.parquet")
OUT_DIR = Path("research/forecasts")
FIG_DIR = OUT_DIR / "figures"

TRAIN_END = pd.Timestamp("2023-12-31 00:00:00", tz="UTC")
VAL_START = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
VAL_END = pd.Timestamp("2024-06-30 00:00:00", tz="UTC")
HOLDOUT_START = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")

DEFAULT_K = 5
DEFAULT_EVAL_STRIDE = 4
MIN_STATE_SAMPLES = 20
LAPLACE_ALPHA = 1.0


@dataclass
class MCForecastResult:
    timestamp: pd.Timestamp
    y_true: float
    state_t: int
    next_state_probs: np.ndarray
    state_means: np.ndarray
    state_vars: np.ndarray
    mc_mu: float
    mc_var: float
    unc_mu: float
    unc_var: float
    ewma_mu: float
    ewma_var: float
    hmm_mix_mu: Optional[float] = None
    hmm_mix_var: Optional[float] = None


def load_btc_returns(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df["symbol"] == "BTCUSDT"].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df = df[["timestamp", "returns"]].copy()
    df = df.dropna(subset=["returns"]).reset_index(drop=True)
    return df


def gaussian_logpdf(y: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    var = np.maximum(var, 1e-12)
    return -0.5 * (np.log(2 * np.pi * var) + (y - mu) ** 2 / var)


def mixture_logpdf(y: float, probs: np.ndarray, means: np.ndarray, vars_: np.ndarray) -> float:
    log_comp = gaussian_logpdf(np.array([y]), means, vars_) + np.log(np.clip(probs, 1e-16, 1.0))
    m = np.max(log_comp)
    return float(m + np.log(np.sum(np.exp(log_comp - m))))


def gaussian_crps(y: float, mu: float, sigma: float) -> float:
    if sigma <= 1e-12:
        return float(abs(y - mu))
    z = (y - mu) / sigma
    phi = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z)
    Phi = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return float(sigma * (z * (2 * Phi - 1) + 2 * phi - 1 / math.sqrt(math.pi)))


def erf_vec(x: np.ndarray) -> np.ndarray:
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-ax * ax)
    return sign * y


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
        return mu, float(max(r[0] ** 2, 1e-10))
    # initialize with sample variance
    var = float(np.var(r, ddof=1)) if len(r) > 1 else float(r[0] ** 2)
    for x in r:
        var = lam * var + (1.0 - lam) * float(x ** 2)
    return mu, float(max(var, 1e-10))


def fit_quantile_bins(train_returns: np.ndarray, k: int) -> np.ndarray:
    """Return k-1 interior bin edges fitted on training data only."""
    quantiles = np.linspace(0, 1, k + 1)[1:-1]
    edges = np.quantile(train_returns, quantiles)
    # ensure strictly increasing edges
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = np.nextafter(edges[i - 1], np.inf)
    return edges


def assign_states(returns: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.digitize(returns, edges, right=False).astype(int)


def estimate_transition_counts(states: np.ndarray, k: int) -> np.ndarray:
    counts = np.zeros((k, k), dtype=float)
    if len(states) < 2:
        return counts
    s_from = states[:-1]
    s_to = states[1:]
    for a, b in zip(s_from, s_to):
        if 0 <= a < k and 0 <= b < k:
            counts[a, b] += 1.0
    return counts


def transition_probs_from_counts(counts: np.ndarray, alpha: float = LAPLACE_ALPHA) -> np.ndarray:
    smoothed = counts + alpha
    row_sums = smoothed.sum(axis=1, keepdims=True)
    return smoothed / np.maximum(row_sums, 1e-12)


def state_conditional_params(history_returns: np.ndarray, history_states: np.ndarray, k: int,
                              global_mu: float, global_var: float,
                              min_samples: int = MIN_STATE_SAMPLES) -> Tuple[np.ndarray, np.ndarray]:
    means = np.zeros(k, dtype=float)
    vars_ = np.zeros(k, dtype=float)
    for s in range(k):
        vals = history_returns[history_states == s]
        if len(vals) >= min_samples:
            means[s] = float(np.mean(vals))
            v = float(np.var(vals, ddof=1)) if len(vals) > 1 else float(np.var(vals))
            vars_[s] = max(v, 1e-10)
        elif len(vals) >= 2:
            # shrink toward global with small-sample variance floor
            means[s] = float(np.mean(vals))
            v = float(np.var(vals, ddof=1))
            vars_[s] = max(v, global_var * 0.5, 1e-10)
        elif len(vals) == 1:
            means[s] = float(vals[0])
            vars_[s] = max(global_var, 1e-10)
        else:
            means[s] = global_mu
            vars_[s] = max(global_var, 1e-10)
    return means, vars_


def load_hmm_forecasts(path: Path = OUT_DIR / "h2_validation_forecasts.csv") -> Optional[pd.DataFrame]:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[["timestamp", "hmm_mu", "hmm_var", "unc_mu", "unc_var", "ewma_mu", "ewma_var"]].copy()


def run_markov_chain_walkforward(
    df: pd.DataFrame,
    k: int = DEFAULT_K,
    eval_stride: int = DEFAULT_EVAL_STRIDE,
    train_end: pd.Timestamp = TRAIN_END,
    val_start: pd.Timestamp = VAL_START,
    val_end: pd.Timestamp = VAL_END,
) -> Dict:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    rets = df["returns"].astype(float).to_numpy()

    train_mask = ts <= train_end
    val_mask = (ts >= val_start) & (ts <= val_end)
    train_returns = rets[train_mask.to_numpy()]
    if len(train_returns) < 500:
        raise ValueError("insufficient training data")

    edges = fit_quantile_bins(train_returns, k)
    all_states = assign_states(rets, edges)

    val_idx = np.where(val_mask.to_numpy())[0]
    val_idx = val_idx[:: max(1, int(eval_stride))]
    # need at least one prior observation for t
    val_idx = val_idx[val_idx >= 1]

    hmm_df = load_hmm_forecasts()
    hmm_lookup = {}
    if hmm_df is not None:
        for _, row in hmm_df.iterrows():
            hmm_lookup[pd.Timestamp(row["timestamp"])] = (float(row["hmm_mu"]), float(row["hmm_var"]))

    results: List[MCForecastResult] = []
    for t_idx in val_idx:
        target_ts = pd.Timestamp(ts.iloc[t_idx])
        if target_ts > val_end or target_ts >= HOLDOUT_START:
            continue
        history_returns = rets[:t_idx]  # up to t-1 inclusive? history for forecasting t uses info up to t-1 state/obs
        history_states = all_states[:t_idx]
        if len(history_returns) < 100:
            continue
        # current state is state at t-1 (last observed before target)
        state_t = int(all_states[t_idx - 1])
        counts = estimate_transition_counts(history_states, k)
        trans = transition_probs_from_counts(counts)
        next_probs = trans[state_t].copy()
        next_probs = np.clip(next_probs, 1e-16, 1.0)
        next_probs = next_probs / next_probs.sum()

        unc_mu, unc_var = expanding_unconditional_params(history_returns)
        ewma_mu, ewma_var = ewma_forecast_params(history_returns)
        state_means, state_vars = state_conditional_params(history_returns, history_states, k, unc_mu, unc_var)

        mc_mu = float(np.sum(next_probs * state_means))
        mc_var = float(np.sum(next_probs * (state_vars + state_means ** 2)) - mc_mu ** 2)
        mc_var = max(mc_var, 1e-10)

        hmm_mv = hmm_lookup.get(target_ts)
        results.append(MCForecastResult(
            timestamp=target_ts,
            y_true=float(rets[t_idx]),
            state_t=state_t,
            next_state_probs=next_probs,
            state_means=state_means,
            state_vars=state_vars,
            mc_mu=mc_mu,
            mc_var=mc_var,
            unc_mu=unc_mu,
            unc_var=unc_var,
            ewma_mu=ewma_mu,
            ewma_var=ewma_var,
            hmm_mix_mu=hmm_mv[0] if hmm_mv else None,
            hmm_mix_var=hmm_mv[1] if hmm_mv else None,
        ))

    payload = build_payload(results, edges, k, eval_stride, train_end, val_start, val_end)
    return {"results": results, "payload": payload, "edges": edges}


def compute_metrics(results: List[MCForecastResult]) -> Dict:
    if not results:
        return {}
    y = np.array([r.y_true for r in results], dtype=float)
    mc_log = np.array([mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results])
    unc_log = np.array([float(gaussian_logpdf(np.array([r.y_true]), np.array([r.unc_mu]), np.array([r.unc_var]))[0]) for r in results])
    ewma_log = np.array([float(gaussian_logpdf(np.array([r.y_true]), np.array([r.ewma_mu]), np.array([r.ewma_var]))[0]) for r in results])
    mc_crps = np.array([mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results])
    unc_crps = np.array([gaussian_crps(r.y_true, r.unc_mu, math.sqrt(r.unc_var)) for r in results])
    ewma_crps = np.array([gaussian_crps(r.y_true, r.ewma_mu, math.sqrt(r.ewma_var)) for r in results])

    def summ(arr):
        return {"mean": float(np.mean(arr)), "median": float(np.median(arr)), "std": float(np.std(arr))}

    # PIT for MC mixture
    pit = []
    for r in results:
        cdf = 0.0
        for pr, m, v in zip(r.next_state_probs, r.state_means, r.state_vars):
            s = math.sqrt(max(v, 1e-12))
            z = (r.y_true - m) / s
            cdf += float(pr) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        pit.append(min(max(cdf, 0.0), 1.0))
    pit = np.array(pit)
    hist, bin_edges = np.histogram(pit, bins=10, range=(0, 1), density=True)

    metrics = {
        "log_score_higher_is_better": {
            "markov_chain_mixture": summ(mc_log),
            "unconditional_gaussian": summ(unc_log),
            "ewma_gaussian": summ(ewma_log),
        },
        "crps_lower_is_better": {
            "markov_chain_mixture": summ(mc_crps),
            "unconditional_gaussian": summ(unc_crps),
            "ewma_gaussian": summ(ewma_crps),
        },
        "pit_markov_chain": {
            "mean": float(np.mean(pit)),
            "std": float(np.std(pit)),
            "hist_density": hist.tolist(),
            "bin_edges": bin_edges.tolist(),
        },
        "n_obs": int(len(results)),
    }

    # comparison vs HMM on aligned timestamps where HMM available
    aligned = [r for r in results if r.hmm_mix_mu is not None and r.hmm_mix_var is not None]
    if aligned:
        hmm_log = np.array([float(gaussian_logpdf(np.array([r.y_true]), np.array([r.hmm_mix_mu]), np.array([r.hmm_mix_var]))[0]) for r in aligned])
        hmm_crps = np.array([gaussian_crps(r.y_true, r.hmm_mix_mu, math.sqrt(r.hmm_mix_var)) for r in aligned])
        mc_log_a = np.array([mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned])
        mc_crps_a = np.array([mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned])
        metrics["aligned_with_hmm"] = {
            "n_obs": int(len(aligned)),
            "note": "HMM scores computed from saved T4 mixture moments (Gaussian approximation in saved CSV context not applicable; here using T4 saved hmm_mu/hmm_var). MC uses state-mixture distribution.",
            "log_score_higher_is_better": {
                "markov_chain_mixture": summ(mc_log_a),
                "hmm_mixture_moments_gaussian": summ(hmm_log),
            },
            "crps_lower_is_better": {
                "markov_chain_mixture": summ(mc_crps_a),
                "hmm_mixture_moments_gaussian": summ(hmm_crps),
            },
        }
    return metrics


def stationary_bootstrap_indices(n: int, block_length: float, n_bootstrap: int, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / block_length
    indices = np.empty((n_bootstrap, n), dtype=int)
    for b in range(n_bootstrap):
        i = int(rng.integers(0, n))
        for t in range(n):
            indices[b, t] = i
            if rng.random() < p:
                i = int(rng.integers(0, n))
            else:
                i = (i + 1) % n
    return indices


def bootstrap_mean_diff(diffs: np.ndarray, n_bootstrap: int = 2000, seed: int = 42) -> Dict:
    n = len(diffs)
    if n == 0:
        return {}
    block_length = max(1.0, n ** (1.0 / 3.0))
    rng = np.random.default_rng(seed)
    boot_idx = stationary_bootstrap_indices(n, block_length, n_bootstrap, rng)
    boot_means = diffs[boot_idx].mean(axis=1)
    mean_diff = float(np.mean(diffs))
    ci_lo = float(np.percentile(boot_means, 2.5))
    ci_hi = float(np.percentile(boot_means, 97.5))
    centered = boot_means - np.mean(boot_means)
    p_val = float(np.mean(np.abs(centered) >= abs(mean_diff)))
    var_iid = float(np.var(diffs, ddof=1) / n) if n > 1 else 0.0
    var_boot = float(np.var(boot_means, ddof=1)) if n_bootstrap > 1 else 0.0
    eff_n = int(round(n * var_iid / max(var_boot, 1e-16))) if var_boot > 0 else n
    return {
        "mean_difference": mean_diff,
        "ci_95": [ci_lo, ci_hi],
        "p_value_two_sided": p_val,
        "block_length": float(block_length),
        "n_bootstrap": int(n_bootstrap),
        "effective_sample_size": eff_n,
        "n_obs": n,
        "significant_at_05": bool(ci_lo > 0 or ci_hi < 0),
    }


def compute_bootstrap_comparisons(results: List[MCForecastResult]) -> Dict:
    if not results:
        return {}
    # MC vs unconditional/EWMA (Gaussian baselines) on all results
    mc_log = np.array([mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results])
    unc_log = np.array([float(gaussian_logpdf(np.array([r.y_true]), np.array([r.unc_mu]), np.array([r.unc_var]))[0]) for r in results])
    ewma_log = np.array([float(gaussian_logpdf(np.array([r.y_true]), np.array([r.ewma_mu]), np.array([r.ewma_var]))[0]) for r in results])
    mc_crps = np.array([mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results])
    unc_crps = np.array([gaussian_crps(r.y_true, r.unc_mu, math.sqrt(r.unc_var)) for r in results])
    ewma_crps = np.array([gaussian_crps(r.y_true, r.ewma_mu, math.sqrt(r.ewma_var)) for r in results])

    out = {
        "log_score_higher_better_diff_mc_minus_baseline": {
            "mc_vs_unconditional": bootstrap_mean_diff(mc_log - unc_log),
            "mc_vs_ewma": bootstrap_mean_diff(mc_log - ewma_log),
        },
        "crps_lower_better_diff_baseline_minus_mc": {
            "mc_vs_unconditional": bootstrap_mean_diff(unc_crps - mc_crps),
            "mc_vs_ewma": bootstrap_mean_diff(ewma_crps - mc_crps),
        },
    }
    aligned = [r for r in results if r.hmm_mix_mu is not None and r.hmm_mix_var is not None]
    if aligned:
        hmm_log = np.array([float(gaussian_logpdf(np.array([r.y_true]), np.array([r.hmm_mix_mu]), np.array([r.hmm_mix_var]))[0]) for r in aligned])
        hmm_crps = np.array([gaussian_crps(r.y_true, r.hmm_mix_mu, math.sqrt(r.hmm_mix_var)) for r in aligned])
        mc_log_a = np.array([mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned])
        mc_crps_a = np.array([mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned])
        out["aligned_hmm_comparison"] = {
            "n_obs": len(aligned),
            "note": "MC mixture vs HMM Gaussian-moment approximation from saved T4 CSV (hmm_mu/hmm_var). Interpret cautiously: HMM is a state mixture in T4 proper scoring; this comparison uses saved moment summary.",
            "log_score_diff_mc_minus_hmm": bootstrap_mean_diff(mc_log_a - hmm_log),
            "crps_diff_hmm_minus_mc": bootstrap_mean_diff(hmm_crps - mc_crps_a),
        }
    return out


def build_payload(results: List[MCForecastResult], edges: np.ndarray, k: int, eval_stride: int,
                  train_end: pd.Timestamp, val_start: pd.Timestamp, val_end: pd.Timestamp) -> Dict:
    metrics = compute_metrics(results)
    boot = compute_bootstrap_comparisons(results)
    # state occupancy over forecast times
    if results:
        states = np.array([r.state_t for r in results])
        occ = np.bincount(states, minlength=k) / len(states)
    else:
        occ = np.zeros(k)
    return {
        "config": {
            "symbol": "BTCUSDT",
            "frequency": "1h",
            "k_states": int(k),
            "discretization": "quantile_bins_fit_on_train",
            "bin_edges_train": edges.tolist(),
            "eval_stride": int(eval_stride),
            "laplace_alpha": float(LAPLACE_ALPHA),
            "min_state_samples_for_params": int(MIN_STATE_SAMPLES),
            "train_end": str(train_end),
            "val_start": str(val_start),
            "val_end": str(val_end),
            "holdout_start": str(HOLDOUT_START),
        },
        "counts": {"validation_forecasts": len(results)},
        "state_occupancy_at_forecast_times": occ.tolist(),
        "metrics": metrics,
        "bootstrap": boot,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_outputs(results: List[MCForecastResult], payload: Dict, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "h1_markov_chain_validation.json", "w") as f:
        json.dump(payload, f, indent=2)

    rows = []
    for r in results:
        row = {
            "timestamp": r.timestamp,
            "y_true": r.y_true,
            "state_t": r.state_t,
            "mc_mu": r.mc_mu,
            "mc_var": r.mc_var,
            "unc_mu": r.unc_mu,
            "unc_var": r.unc_var,
            "ewma_mu": r.ewma_mu,
            "ewma_var": r.ewma_var,
        }
        for i, p in enumerate(r.next_state_probs):
            row[f"p_next_s{i}"] = float(p)
        for i, m in enumerate(r.state_means):
            row[f"state_mean_s{i}"] = float(m)
        for i, v in enumerate(r.state_vars):
            row[f"state_var_s{i}"] = float(v)
        if r.hmm_mix_mu is not None:
            row["hmm_mu"] = r.hmm_mix_mu
            row["hmm_var"] = r.hmm_mix_var
        rows.append(row)
    pd.DataFrame(rows).to_csv(out_dir / "h1_markov_chain_validation.csv", index=False)

    if plt is not None and results:
        ts = [r.timestamp for r in results]
        probs = np.array([r.next_state_probs for r in results])
        fig, ax = plt.subplots(figsize=(12, 4))
        for i in range(probs.shape[1]):
            ax.plot(ts, probs[:, i], label=f"P(next=S{i})", linewidth=0.8)
        ax.set_title(f"Markov chain 1-step-ahead state probabilities (K={payload['config']['k_states']}, validation)")
        ax.set_ylabel("Probability")
        ax.legend(loc="upper right", ncol=min(5, probs.shape[1]))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_dir / "h1_mc_next_state_probs.png", dpi=150)
        plt.close(fig)

        pit = []
        for r in results:
            cdf = 0.0
            for pr, m, v in zip(r.next_state_probs, r.state_means, r.state_vars):
                s = math.sqrt(max(v, 1e-12))
                z = (r.y_true - m) / s
                cdf += float(pr) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            pit.append(cdf)
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(pit, bins=10, range=(0, 1), density=True, alpha=0.8, color="#54a24b")
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
        ax.set_title("Markov chain mixture PIT (validation)")
        ax.set_xlabel("PIT")
        ax.set_ylabel("Density")
        fig.tight_layout()
        fig.savefig(fig_dir / "h1_mc_pit_hist.png", dpi=150)
        plt.close(fig)

    write_markdown_report(payload, out_dir / "h1_markov_chain_validation.md")


def write_markdown_report(payload: Dict, path: Path) -> None:
    c = payload["config"]
    m = payload.get("metrics", {})
    b = payload.get("bootstrap", {})
    lines = []
    lines.append("# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, Validation)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Model:** First-order finite-state Markov chain, K={c['k_states']} states")
    lines.append(f"**Discretization:** Quantile bins fitted on training returns only (<= {c['train_end']}); edges fixed for validation forecasts")
    lines.append(f"**Validation window:** {c['val_start']} to {c['val_end']} (holdout >= {c['holdout_start']} excluded)")
    lines.append(f"**Forecasts:** {payload['counts']['validation_forecasts']} (eval_stride={c['eval_stride']})")
    lines.append("")
    lines.append("## Scope and leakage controls")
    lines.append("- Expanding history up to time *t-1* used to estimate transition counts/probabilities and state-conditional return moments; target is *t* in validation window.")
    lines.append("- Bin edges computed from training-period returns only; no holdout data used.")
    lines.append("- Laplace smoothing applied to transition probabilities.")
    lines.append("")
    lines.append("## State occupancy at forecast times")
    lines.append(f"- {payload.get('state_occupancy_at_forecast_times')}")
    lines.append("")
    ls = m.get("log_score_higher_is_better", {})
    cr = m.get("crps_lower_is_better", {})
    lines.append("## Forecast metrics (validation)")
    if ls:
        lines.append("### Log score (mean, higher is better)")
        for k, v in ls.items():
            if isinstance(v, dict) and "mean" in v:
                lines.append(f"- {k}: {v['mean']:.6f} (median {v.get('median')}, std {v.get('std')})")
    if cr:
        lines.append("### CRPS (mean, lower is better)")
        for k, v in cr.items():
            if isinstance(v, dict) and "mean" in v:
                lines.append(f"- {k}: {v['mean']:.6e} (median {v.get('median')}, std {v.get('std')})")
    pit = m.get("pit_markov_chain", {})
    if pit:
        lines.append(f"### PIT (MC mixture): mean={pit.get('mean')}, std={pit.get('std')} (ideal uniform mean 0.5, std ~0.289)")
    lines.append("")
    aligned = m.get("aligned_with_hmm")
    if aligned:
        lines.append("## Aligned comparison with HMM forecasts (saved T4 grid)")
        lines.append(f"- n_obs={aligned.get('n_obs')}. {aligned.get('note')}")
        a_ls = aligned.get("log_score_higher_is_better", {})
        a_cr = aligned.get("crps_lower_is_better", {})
        for k, v in a_ls.items():
            if isinstance(v, dict):
                lines.append(f"- log_score {k}: {v.get('mean')}")
        for k, v in a_cr.items():
            if isinstance(v, dict):
                lines.append(f"- crps {k}: {v.get('mean')}")
        lines.append("")
    lines.append("## Block-bootstrap significance (stationary bootstrap)")
    for section, comps in b.items():
        lines.append(f"### {section}")
        if isinstance(comps, dict):
            for name, res in comps.items():
                if isinstance(res, dict) and "mean_difference" in res:
                    lines.append(f"- {name}: mean_diff={res['mean_difference']:.6g}, 95% CI={res['ci_95']}, p={res['p_value_two_sided']}, eff_n={res.get('effective_sample_size')}, significant@5%={res.get('significant_at_05')}")
                elif isinstance(res, dict):
                    for sub, r2 in res.items():
                        if isinstance(r2, dict) and "mean_difference" in r2:
                            lines.append(f"- {name}.{sub}: mean_diff={r2['mean_difference']:.6g}, 95% CI={r2['ci_95']}, p={r2['p_value_two_sided']}, eff_n={r2.get('effective_sample_size')}, significant@5%={r2.get('significant_at_05')}")
        lines.append("")
    lines.append("## Artifacts")
    lines.append("- `research/forecasts/h1_markov_chain_validation.json`")
    lines.append("- `research/forecasts/h1_markov_chain_validation.csv`")
    lines.append("- `research/forecasts/figures/h1_mc_next_state_probs.png`")
    lines.append("- `research/forecasts/figures/h1_mc_pit_hist.png`")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- Validation-only baseline; no holdout evaluation. Discretization and K are design choices (sensitivity to K/binning not exhaustively swept).")
    lines.append("- HMM comparison uses saved T4 mixture-moment Gaussian approximation from CSV where applicable; interpret aligned HMM-vs-MC scores cautiously.")
    lines.append("- EM non-convergence warnings and train-vs-validation non-stationarity (prior Chow p=0.0042) remain project-level concerns.")
    path.write_text("\n".join(lines) + "\n")


def main():
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load_btc_returns(DATA_PATH)
    out = run_markov_chain_walkforward(df, k=DEFAULT_K, eval_stride=DEFAULT_EVAL_STRIDE)
    save_outputs(out["results"], out["payload"], out_dir)
    print(json.dumps({
        "validation_forecasts": out["payload"]["counts"]["validation_forecasts"],
        "k": out["payload"]["config"]["k_states"],
        "log_score_means": out["payload"]["metrics"].get("log_score_higher_is_better", {}),
        "crps_means": out["payload"]["metrics"].get("crps_lower_is_better", {}),
    }, indent=2))


if __name__ == "__main__":
    main()
