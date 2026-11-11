#!/usr/bin/env python3
"""
Task T3d (H1): Semi-Markov / duration-dependent Markov baseline (validation only).

- BTCUSDT 1h returns from data/processed/features.parquet
- Discretize returns into K states using quantile bins fitted on training data only (<= 2023-12-31)
- Estimate state-conditional sojourn time distributions from expanding history
- 1-step-ahead state probabilities using hazard rate / duration-dependent transitions
- State-conditional return distribution E[r_t | S_t = j] Gaussian per state
- Validation window: 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00
- Holdout (>=2024-07-01) never used
- Baselines: unconditional expanding Gaussian, EWMA Gaussian (lambda=0.94)
- Metrics: log score, CRPS (mixture via grid integration), PIT, block-bootstrap
  significance (stationary bootstrap, 2000 reps, n^(1/3) block)
- Aligned comparison with H1 (first-order MC), H3 (higher-order MC), and H2 (HMM)
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

from scipy import stats as scipy_stats

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
MAX_SOJOURN = 200  # cap sojourn times for stability


@dataclass
class SMForecastResult:
    timestamp: pd.Timestamp
    y_true: float
    state_curr: int
    duration_curr: int
    next_state_probs: np.ndarray  # P(S_{t} = j | S_{t-1}=state_curr, duration=duration_curr)
    state_means: np.ndarray  # E[r_t | S_t = j]
    state_vars: np.ndarray
    sm_mu: float
    sm_var: float
    unc_mu: float
    unc_var: float
    ewma_mu: float
    ewma_var: float
    hmm_mix_mu: Optional[float] = None
    hmm_mix_var: Optional[float] = None
    h1_mix_mu: Optional[float] = None
    h1_mix_var: Optional[float] = None
    h3_mix_mu: Optional[float] = None
    h3_mix_var: Optional[float] = None


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
    var = float(np.var(r, ddof=1)) if len(r) > 1 else float(r[0] ** 2)
    for x in r:
        var = lam * var + (1.0 - lam) * float(x ** 2)
    return mu, float(max(var, 1e-10))


def fit_quantile_bins(train_returns: np.ndarray, k: int) -> np.ndarray:
    """Return k-1 interior bin edges fitted on training data only."""
    quantiles = np.linspace(0, 1, k + 1)[1:-1]
    edges = np.quantile(train_returns, quantiles)
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = np.nextafter(edges[i - 1], np.inf)
    return edges


def assign_states(returns: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return np.digitize(returns, edges, right=False).astype(int)


def compute_sojourns(states: np.ndarray, k: int, max_sojourn: int = MAX_SOJOURN) -> Dict[int, np.ndarray]:
    """
    Compute empirical sojourn time distributions for each state.
    Returns dict mapping state -> array of sojourn lengths (capped at max_sojourn).
    """
    sojourns_by_state = {s: [] for s in range(k)}
    if len(states) == 0:
        return sojourns_by_state
    curr_state = states[0]
    duration = 1
    for s in states[1:]:
        if s == curr_state:
            duration += 1
        else:
            sojourns_by_state[curr_state].append(min(duration, max_sojourn))
            curr_state = s
            duration = 1
    # add final sojourn (right-censored, but we include it)
    sojourns_by_state[curr_state].append(min(duration, max_sojourn))
    return {s: np.array(v, dtype=int) for s, v in sojourns_by_state.items()}


def fit_sojourn_distributions(sojourns_by_state: Dict[int, np.ndarray]) -> Dict[int, Dict]:
    """
    Fit a negative binomial distribution to sojourn times for each state.
    Negative binomial is a good discrete analog of gamma/Weibull for duration modeling.
    Returns dict state -> {'r': r, 'p': p, 'mean': mean, 'var': var, 'n_samples': n}
    """
    fitted = {}
    for s, sojs in sojourns_by_state.items():
        n = len(sojs)
        if n < 5:
            # Too few samples: fall back to geometric (memoryless = Markov)
            mean_dur = max(1.0, float(np.mean(sojs)) if n > 0 else 1.0)
            p = 1.0 / mean_dur
            r = 1.0
            fitted[s] = {'r': r, 'p': float(p), 'mean': mean_dur, 'var': mean_dur * (1 - p) / p if p > 0 else mean_dur, 'n_samples': n}
        else:
            mean_dur = float(np.mean(sojs))
            var_dur = float(np.var(sojs, ddof=1))
            if var_dur <= mean_dur + 1e-6:
                # Under/equi-dispersed: geometric
                p = 1.0 / mean_dur
                r = 1.0
            else:
                # Over-dispersed: negative binomial
                # Var = mean + mean^2 / r  =>  r = mean^2 / (var - mean)
                r = max(0.5, mean_dur ** 2 / max(var_dur - mean_dur, 1e-6))
                p = r / (r + mean_dur)
            fitted[s] = {'r': float(r), 'p': float(p), 'mean': mean_dur, 'var': var_dur, 'n_samples': n}
    return fitted


def hazard_and_transition_probs(
    state_curr: int,
    duration: int,
    fitted_sojourns: Dict[int, Dict],
    trans_probs: np.ndarray,
    k: int
) -> np.ndarray:
    """
    Compute P(S_t = j | S_{t-1}=state_curr, duration=d) using hazard rate.

    For a semi-Markov process:
    - If we're in state i with elapsed duration d, the probability of staying in i
      is 1 - h_i(d) where h_i(d) = P(T = d | T >= d) is the hazard rate.
    - The probability of transitioning to j != i is h_i(d) * P_{ij} where P_{ij}
      is the embedded transition matrix (conditional on leaving state i).
    """
    fit = fitted_sojourns.get(state_curr, {'r': 1.0, 'p': 1.0})
    r = fit['r']
    p = fit['p']

    # Hazard rate h(d) = P(T = d | T >= d)
    if r == 1.0:
        # Geometric: constant hazard = p
        hazard = p
    else:
        # Negative binomial hazard
        # PMF: P(T = d) = C(d + r - 1, d) * p^r * (1-p)^d
        # Survival: P(T >= d) = 1 - CDF(d-1)
        # Hazard = PMF(d) / Survival(d-1)
        try:
            pmf = scipy_stats.nbinom.pmf(duration, r, p)
            sf = scipy_stats.nbinom.sf(duration - 1, r, p)  # P(T >= d)
            hazard = float(pmf / max(sf, 1e-12)) if sf > 0 else 1.0
        except Exception:
            hazard = p
    hazard = min(max(hazard, 0.0), 1.0)

    # Embedded transition matrix: P(j | leave i) = trans_probs[i, j] / (1 - trans_probs[i, i])
    stay_prob = trans_probs[state_curr, state_curr]
    if stay_prob >= 1.0 - 1e-10:
        # Absorbing state (shouldn't happen with Laplace smoothing, but guard)
        next_probs = np.zeros(k)
        next_probs[state_curr] = 1.0
        return next_probs

    leave_prob = 1.0 - stay_prob
    embedded = trans_probs[state_curr].copy()
    embedded[state_curr] = 0.0
    embedded_sum = embedded.sum()
    if embedded_sum > 0:
        embedded = embedded / embedded_sum
    else:
        # Uniform over other states
        embedded = np.ones(k) / (k - 1)
        embedded[state_curr] = 0.0

    # Semi-Markov transition probabilities
    next_probs = np.zeros(k)
    next_probs[state_curr] = 1.0 - hazard
    for j in range(k):
        if j != state_curr:
            next_probs[j] = hazard * embedded[j]

    # Normalize
    next_probs = np.clip(next_probs, 1e-16, 1.0)
    next_probs = next_probs / next_probs.sum()
    return next_probs


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
    return df[["timestamp", "hmm_mu", "hmm_var"]].copy()


def load_h1_forecasts(path: Path = OUT_DIR / "h1_markov_chain_validation.csv") -> Optional[Dict[pd.Timestamp, Dict]]:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    k_cols = [c for c in df.columns if c.startswith("p_next_s")]
    mean_cols = [c for c in df.columns if c.startswith("state_mean_s")]
    var_cols = [c for c in df.columns if c.startswith("state_var_s")]
    k_cols.sort()
    mean_cols.sort()
    var_cols.sort()
    lookup: Dict[pd.Timestamp, Dict] = {}
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        lookup[ts] = {
            "probs": np.array([float(row[c]) for c in k_cols], dtype=float),
            "means": np.array([float(row[c]) for c in mean_cols], dtype=float),
            "vars": np.array([float(row[c]) for c in var_cols], dtype=float),
        }
    return lookup


def load_h3_forecasts(path: Path = OUT_DIR / "h3_higher_order_markov_validation.csv") -> Optional[Dict[pd.Timestamp, Dict]]:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    k_cols = [c for c in df.columns if c.startswith("p_next_s")]
    mean_cols = [c for c in df.columns if c.startswith("pair_mean_s")]
    var_cols = [c for c in df.columns if c.startswith("pair_var_s")]
    k_cols.sort()
    mean_cols.sort()
    var_cols.sort()
    lookup: Dict[pd.Timestamp, Dict] = {}
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        lookup[ts] = {
            "probs": np.array([float(row[c]) for c in k_cols], dtype=float),
            "means": np.array([float(row[c]) for c in mean_cols], dtype=float),
            "vars": np.array([float(row[c]) for c in var_cols], dtype=float),
        }
    return lookup


def run_semi_markov_walkforward(
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

    h1_lookup = load_h1_forecasts()
    h3_lookup = load_h3_forecasts()

    results: List[SMForecastResult] = []
    for t_idx in val_idx:
        target_ts = pd.Timestamp(ts.iloc[t_idx])
        if target_ts > val_end or target_ts >= HOLDOUT_START:
            continue
        history_returns = rets[:t_idx]  # r_0..r_{t-1}
        history_states = all_states[:t_idx]  # s_0..s_{t-1}
        if len(history_returns) < 100:
            continue

        # Current state is state at t-1
        state_curr = int(all_states[t_idx - 1])
        # Compute duration of current state at time t-1
        duration = 1
        for s in reversed(history_states[:-1]):
            if s == state_curr:
                duration += 1
            else:
                break

        # Estimate transition counts and probs from history up to t-1
        counts = estimate_transition_counts(history_states, k)
        trans = transition_probs_from_counts(counts)

        # Estimate sojourn distributions from history
        sojourns = compute_sojourns(history_states, k)
        fitted_sojourns = fit_sojourn_distributions(sojourns)

        # Semi-Markov next state probabilities
        next_probs = hazard_and_transition_probs(state_curr, duration, fitted_sojourns, trans, k)

        unc_mu, unc_var = expanding_unconditional_params(history_returns)
        ewma_mu, ewma_var = ewma_forecast_params(history_returns)
        state_means, state_vars = state_conditional_params(history_returns, history_states, k, unc_mu, unc_var)

        sm_mu = float(np.sum(next_probs * state_means))
        sm_var = float(np.sum(next_probs * (state_vars + state_means ** 2)) - sm_mu ** 2)
        sm_var = max(sm_var, 1e-10)

        hmm_mv = hmm_lookup.get(target_ts)
        h1_comp = h1_lookup.get(target_ts)
        h3_comp = h3_lookup.get(target_ts)

        results.append(SMForecastResult(
            timestamp=target_ts,
            y_true=float(rets[t_idx]),
            state_curr=state_curr,
            duration_curr=duration,
            next_state_probs=next_probs,
            state_means=state_means,
            state_vars=state_vars,
            sm_mu=sm_mu,
            sm_var=sm_var,
            unc_mu=unc_mu,
            unc_var=unc_var,
            ewma_mu=ewma_mu,
            ewma_var=ewma_var,
            hmm_mix_mu=hmm_mv[0] if hmm_mv else None,
            hmm_mix_var=hmm_mv[1] if hmm_mv else None,
            h1_mix_mu=None,  # filled below if needed
            h1_mix_var=None,
            h3_mix_mu=None,
            h3_mix_var=None,
        ))

    # Fill H1/H3 comparison data for aligned timestamps
    for r in results:
        if h1_comp := h1_lookup.get(r.timestamp):
            r.h1_mix_mu = float(np.sum(h1_comp["probs"] * h1_comp["means"]))
            r.h1_mix_var = float(np.sum(h1_comp["probs"] * (h1_comp["vars"] + h1_comp["means"] ** 2)) - r.h1_mix_mu ** 2)
        if h3_comp := h3_lookup.get(r.timestamp):
            r.h3_mix_mu = float(np.sum(h3_comp["probs"] * h3_comp["means"]))
            r.h3_mix_var = float(np.sum(h3_comp["probs"] * (h3_comp["vars"] + h3_comp["means"] ** 2)) - r.h3_mix_mu ** 2)

    payload = build_payload(results, edges, k, eval_stride, train_end, val_start, val_end)
    return {"results": results, "payload": payload, "edges": edges}


def compute_metrics(results: List[SMForecastResult]) -> Dict:
    if not results:
        return {}

    sm_log = np.array(
        [mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results]
    )
    unc_log = np.array(
        [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.unc_mu]), np.array([r.unc_var]))[0]) for r in results]
    )
    ewma_log = np.array(
        [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.ewma_mu]), np.array([r.ewma_var]))[0]) for r in results]
    )
    sm_crps = np.array(
        [mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results]
    )
    unc_crps = np.array([gaussian_crps(r.y_true, r.unc_mu, math.sqrt(r.unc_var)) for r in results])
    ewma_crps = np.array([gaussian_crps(r.y_true, r.ewma_mu, math.sqrt(r.ewma_var)) for r in results])

    def summ(arr):
        return {"mean": float(np.mean(arr)), "median": float(np.median(arr)), "std": float(np.std(arr))}

    # PIT for SM mixture
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
            "semi_markov_mixture": summ(sm_log),
            "unconditional_gaussian": summ(unc_log),
            "ewma_gaussian": summ(ewma_log),
        },
        "crps_lower_is_better": {
            "semi_markov_mixture": summ(sm_crps),
            "unconditional_gaussian": summ(unc_crps),
            "ewma_gaussian": summ(ewma_crps),
        },
        "pit_semi_markov": {
            "mean": float(np.mean(pit)),
            "std": float(np.std(pit)),
            "hist_density": hist.tolist(),
            "bin_edges": bin_edges.tolist(),
        },
        "n_obs": int(len(results)),
    }

    # Duration statistics
    durations = np.array([r.duration_curr for r in results])
    states = np.array([r.state_curr for r in results])
    metrics["duration_stats"] = {
        "mean_duration": float(np.mean(durations)),
        "median_duration": float(np.median(durations)),
        "max_duration": int(np.max(durations)),
        "duration_by_state": {int(s): {"mean": float(np.mean(durations[states == s])),
                                        "count": int(np.sum(states == s))}
                              for s in range(max(states) + 1) if np.any(states == s)},
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


def compute_bootstrap_comparisons(results: List[SMForecastResult]) -> Dict:
    if not results:
        return {}
    sm_log = np.array(
        [mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results]
    )
    unc_log = np.array(
        [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.unc_mu]), np.array([r.unc_var]))[0]) for r in results]
    )
    ewma_log = np.array(
        [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.ewma_mu]), np.array([r.ewma_var]))[0]) for r in results]
    )
    sm_crps = np.array(
        [mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in results]
    )
    unc_crps = np.array([gaussian_crps(r.y_true, r.unc_mu, math.sqrt(r.unc_var)) for r in results])
    ewma_crps = np.array([gaussian_crps(r.y_true, r.ewma_mu, math.sqrt(r.ewma_var)) for r in results])

    out = {
        "log_score_higher_better_diff_sm_minus_baseline": {
            "sm_vs_unconditional": bootstrap_mean_diff(sm_log - unc_log),
            "sm_vs_ewma": bootstrap_mean_diff(sm_log - ewma_log),
        },
        "crps_lower_better_diff_baseline_minus_sm": {
            "sm_vs_unconditional": bootstrap_mean_diff(unc_crps - sm_crps),
            "sm_vs_ewma": bootstrap_mean_diff(ewma_crps - sm_crps),
        },
    }

    # Aligned H1 comparison
    aligned_h1 = [r for r in results if r.h1_mix_mu is not None and r.h1_mix_var is not None]
    if aligned_h1:
        h1_log = np.array(
            [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.h1_mix_mu]), np.array([r.h1_mix_var]))[0]) for r in aligned_h1]
        )
        h1_crps = np.array([gaussian_crps(r.y_true, r.h1_mix_mu, math.sqrt(r.h1_mix_var)) for r in aligned_h1])
        sm_log_a = np.array(
            [mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned_h1]
        )
        sm_crps_a = np.array(
            [mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned_h1]
        )
        out["aligned_h1_comparison"] = {
            "n_obs": int(len(aligned_h1)),
            "note": "SM vs saved H1 canonical (Q5 expanding) Gaussian-moment approximation on identical timestamps.",
            "log_score_diff_sm_minus_h1": bootstrap_mean_diff(sm_log_a - h1_log),
            "crps_diff_h1_minus_sm": bootstrap_mean_diff(h1_crps - sm_crps_a),
        }

    # Aligned H3 comparison
    aligned_h3 = [r for r in results if r.h3_mix_mu is not None and r.h3_mix_var is not None]
    if aligned_h3:
        h3_log = np.array(
            [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.h3_mix_mu]), np.array([r.h3_mix_var]))[0]) for r in aligned_h3]
        )
        h3_crps = np.array([gaussian_crps(r.y_true, r.h3_mix_mu, math.sqrt(r.h3_mix_var)) for r in aligned_h3])
        sm_log_a = np.array(
            [mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned_h3]
        )
        sm_crps_a = np.array(
            [mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned_h3]
        )
        out["aligned_h3_comparison"] = {
            "n_obs": int(len(aligned_h3)),
            "note": "SM vs saved H3 (order-2 MC) Gaussian-moment approximation on identical timestamps.",
            "log_score_diff_sm_minus_h3": bootstrap_mean_diff(sm_log_a - h3_log),
            "crps_diff_h3_minus_sm": bootstrap_mean_diff(h3_crps - sm_crps_a),
        }

    # Aligned HMM comparison
    aligned_hmm = [r for r in results if r.hmm_mix_mu is not None and r.hmm_mix_var is not None]
    if aligned_hmm:
        hmm_log = np.array(
            [float(gaussian_logpdf(np.array([r.y_true]), np.array([r.hmm_mix_mu]), np.array([r.hmm_mix_var]))[0]) for r in aligned_hmm]
        )
        hmm_crps = np.array([gaussian_crps(r.y_true, r.hmm_mix_mu, math.sqrt(r.hmm_mix_var)) for r in aligned_hmm])
        sm_log_a = np.array(
            [mixture_logpdf(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned_hmm]
        )
        sm_crps_a = np.array(
            [mixture_crps_grid(r.y_true, r.next_state_probs, r.state_means, r.state_vars) for r in aligned_hmm]
        )
        out["aligned_hmm_comparison"] = {
            "n_obs": int(len(aligned_hmm)),
            "note": "SM vs saved HMM (T4) Gaussian-moment approximation on identical timestamps.",
            "log_score_diff_sm_minus_hmm": bootstrap_mean_diff(sm_log_a - hmm_log),
            "crps_diff_hmm_minus_sm": bootstrap_mean_diff(hmm_crps - sm_crps_a),
        }

    return out


def build_payload(results: List[SMForecastResult], edges: np.ndarray, k: int, eval_stride: int,
                  train_end: pd.Timestamp, val_start: pd.Timestamp, val_end: pd.Timestamp) -> Dict:
    metrics = compute_metrics(results)
    boot = compute_bootstrap_comparisons(results)
    if results:
        states = np.array([r.state_curr for r in results])
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
            "max_sojourn": int(MAX_SOJOURN),
            "sojourn_distribution": "negative_binomial",
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


def save_outputs(results: List[SMForecastResult], payload: Dict, out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "h4_semi_markov_validation.json", "w") as f:
        json.dump(payload, f, indent=2)

    k = payload["config"]["k_states"]
    rows = []
    for r in results:
        row = {
            "timestamp": r.timestamp,
            "y_true": r.y_true,
            "state_curr": r.state_curr,
            "duration_curr": r.duration_curr,
            "sm_mu": r.sm_mu,
            "sm_var": r.sm_var,
            "unc_mu": r.unc_mu,
            "unc_var": r.unc_var,
            "ewma_mu": r.ewma_mu,
            "ewma_var": r.ewma_var,
        }
        for i in range(k):
            row[f"p_next_s{i}"] = float(r.next_state_probs[i])
            row[f"state_mean_s{i}"] = float(r.state_means[i])
            row[f"state_var_s{i}"] = float(r.state_vars[i])
        if r.hmm_mix_mu is not None:
            row["hmm_mu"] = r.hmm_mix_mu
            row["hmm_var"] = r.hmm_mix_var
        rows.append(row)
    pd.DataFrame(rows).to_csv(out_dir / "h4_semi_markov_validation.csv", index=False)

    if plt is not None and results:
        ts = [r.timestamp for r in results]
        probs = np.array([r.next_state_probs for r in results])
        fig, ax = plt.subplots(figsize=(12, 4))
        for j in range(probs.shape[1]):
            ax.plot(ts, probs[:, j], label=f"P(next=S{j})", linewidth=0.8)
        ax.set_title(f"Semi-Markov 1-step-ahead state probs (K={k}, validation)")
        ax.set_ylabel("Probability")
        ax.legend(loc="upper right", ncol=min(5, probs.shape[1]))
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_dir / "h4_sm_next_state_probs.png", dpi=150)
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
        ax.set_title("Semi-Markov mixture PIT (validation)")
        ax.set_xlabel("PIT")
        ax.set_ylabel("Density")
        fig.tight_layout()
        fig.savefig(fig_dir / "h4_sm_pit_hist.png", dpi=150)
        plt.close(fig)

        # Duration histogram
        durations = [r.duration_curr for r in results]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(durations, bins=min(30, max(durations)), alpha=0.8, color="#3a7bd5", edgecolor="black")
        ax.set_title("Current state duration at forecast times (validation)")
        ax.set_xlabel("Duration (hours)")
        ax.set_ylabel("Frequency")
        fig.tight_layout()
        fig.savefig(fig_dir / "h4_sm_duration_hist.png", dpi=150)
        plt.close(fig)

    write_markdown_report(payload, out_dir / "h4_semi_markov_validation.md")


def write_markdown_report(payload: Dict, path: Path) -> None:
    c = payload["config"]
    m = payload.get("metrics", {})
    b = payload.get("bootstrap", {})
    lines = []
    lines.append("# H1 Semi-Markov / Duration-Dependent Baseline (BTCUSDT 1h, Validation)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Model:** Semi-Markov chain with negative binomial sojourn distributions, K={c['k_states']} states")
    lines.append(f"**Discretization:** Quantile bins fitted on training returns only (<= {c['train_end']}); edges fixed for validation forecasts")
    lines.append(f"**Validation window:** {c['val_start']} to {c['val_end']} (holdout >= {c['holdout_start']} excluded)")
    lines.append(f"**Forecasts:** {payload['counts']['validation_forecasts']} (eval_stride={c['eval_stride']})")
    lines.append("")
    lines.append("## Scope and leakage controls")
    lines.append("- Expanding history up to time t-1 used to estimate transition counts/probabilities, sojourn distributions, and state-conditional return moments; target is t in validation window.")
    lines.append("- Bin edges computed from training-period returns only; no holdout data used.")
    lines.append("- Laplace smoothing applied to transition probabilities.")
    lines.append("- Sojourn distributions fitted on expanding history; negative binomial (geometric fallback for sparse states).")
    lines.append("- Hazard rate computed from fitted sojourn distribution; embedded transition matrix from Laplace-smoothed counts.")
    lines.append("")
    lines.append("## State occupancy at forecast times")
    lines.append(f"- {payload.get('state_occupancy_at_forecast_times')}")
    lines.append("")
    if "duration_stats" in m:
        ds = m["duration_stats"]
        lines.append("## Duration statistics at forecast times")
        lines.append(f"- Mean duration: {ds.get('mean_duration', 0):.1f}h")
        lines.append(f"- Median duration: {ds.get('median_duration', 0):.1f}h")
        lines.append(f"- Max duration: {ds.get('max_duration', 0)}h")
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
    pit = m.get("pit_semi_markov", {})
    if pit:
        lines.append(f"### PIT (SM mixture): mean={pit.get('mean')}, std={pit.get('std')} (ideal uniform mean 0.5, std ~0.289)")
    lines.append("")
    for key in ["aligned_h1_comparison", "aligned_h3_comparison", "aligned_hmm_comparison"]:
        aligned = m.get(key)
        if aligned:
            name = key.replace("_", " ").title()
            lines.append(f"## Aligned comparison with {name}")
            lines.append(f"- n_obs={aligned.get('n_obs')}. {aligned.get('note')}")
            a_ls = aligned.get("log_score_diff_sm_minus_h1") or aligned.get("log_score_diff_sm_minus_h3") or aligned.get("log_score_diff_sm_minus_hmm")
            if a_ls and isinstance(a_ls, dict):
                lines.append(f"- log_score diff: mean_diff={a_ls.get('mean_difference'):.6g}, 95% CI={a_ls.get('ci_95')}, p={a_ls.get('p_value_two_sided')}, eff_n={a_ls.get('effective_sample_size')}")
            a_cr = aligned.get("crps_diff_h1_minus_sm") or aligned.get("crps_diff_h3_minus_sm") or aligned.get("crps_diff_hmm_minus_sm")
            if a_cr and isinstance(a_cr, dict):
                lines.append(f"- crps diff: mean_diff={a_cr.get('mean_difference'):.6g}, 95% CI={a_cr.get('ci_95')}, p={a_cr.get('p_value_two_sided')}, eff_n={a_cr.get('effective_sample_size')}")
            lines.append("")
    lines.append("## Block-bootstrap significance (stationary bootstrap)")
    for section, comps in b.items():
        lines.append(f"### {section}")
        if isinstance(comps, dict):
            for name, res in comps.items():
                if isinstance(res, dict) and "mean_difference" in res:
                    lines.append(
                        f"- {name}: mean_diff={res['mean_difference']:.6g}, 95% CI={res['ci_95']}, "
                        f"p={res['p_value_two_sided']}, eff_n={res.get('effective_sample_size')}, significant@5%={res.get('significant_at_05')}"
                    )
    lines.append("")
    lines.append("## Artifacts")
    lines.append("- `research/forecasts/h4_semi_markov_validation.json`")
    lines.append("- `research/forecasts/h4_semi_markov_validation.csv`")
    lines.append("- `research/forecasts/figures/h4_sm_next_state_probs.png`")
    lines.append("- `research/forecasts/figures/h4_sm_pit_hist.png`")
    lines.append("- `research/forecasts/figures/h4_sm_duration_hist.png`")
    lines.append("")
    lines.append("## Caveats")
    lines.append("- Validation-only baseline; no holdout evaluation. K=5 quantile bins and negative binomial sojourn are design choices.")
    lines.append("- Sojourn distributions estimated from expanding history; sparse states fall back to geometric (Markov).")
    lines.append("- H1/H3/HMM comparisons use saved validation CSV moment approximations; interpret cautiously.")
    lines.append("- EM non-convergence warnings and train-vs-validation non-stationarity (prior Chow p=0.0042) remain project-level concerns.")
    path.write_text("\n".join(lines) + "\n")


def main():
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load_btc_returns(DATA_PATH)
    out = run_semi_markov_walkforward(df, k=DEFAULT_K, eval_stride=DEFAULT_EVAL_STRIDE)
    save_outputs(out["results"], out["payload"], out_dir)
    print(
        json.dumps(
            {
                "validation_forecasts": out["payload"]["counts"]["validation_forecasts"],
                "k": out["payload"]["config"]["k_states"],
                "log_score_means": out["payload"]["metrics"].get("log_score_higher_is_better", {}),
                "crps_means": out["payload"]["metrics"].get("crps_lower_is_better", {}),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()