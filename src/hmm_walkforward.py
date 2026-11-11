#!/usr/bin/env python3
"""
Task T4 (H2 groundwork): Walk-forward filtered HMM forecast validation (validation only).

- BTCUSDT 1h returns from data/processed/features.parquet
- 3-state Gaussian HMM, states ordered by mean return (mu1 < mu2 < mu3)
- Expanding walk-forward: refit on data up to t, forecast t+1
- Filtered (forward) state probabilities only; no smoothed probabilities
- Validation window evaluated: 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00
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

try:
    from hmmlearn.hmm import GaussianHMM
except Exception as e:  # pragma: no cover
    raise SystemExit(f"hmmlearn is required: {e}")

DATA_PATH = Path("data/processed/features.parquet")
OUT_DIR = Path("research/forecasts")
FIG_DIR = OUT_DIR / "figures"

TRAIN_END = pd.Timestamp("2023-12-31 00:00:00", tz="UTC")
VAL_START = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
VAL_END = pd.Timestamp("2024-06-30 00:00:00", tz="UTC")
HOLDOUT_START = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")

N_STATES = 3
DEFAULT_REFIT_EVERY = 168  # 1 week of hourly bars
DEFAULT_SEEDS = (0, 1, 2, 3, 4)
DEFAULT_RUN_REFIT_EVERY = 720  # monthly cadence for reproducible runtime in this environment


@dataclass
class ForecastResult:
    timestamp: pd.Timestamp
    y_true: float
    hmm_state_probs_next: np.ndarray
    hmm_mix_means: np.ndarray
    hmm_mix_vars: np.ndarray
    hmm_mu: float
    hmm_var: float
    unc_mu: float
    unc_var: float
    ewma_mu: float
    ewma_var: float
    realized_state: Optional[int]
    hmm_log: float = 0.0
    unc_log: float = 0.0
    ewma_log: float = 0.0
    hmm_crps: float = 0.0
    unc_crps: float = 0.0
    ewma_crps: float = 0.0


def load_btc_returns(path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df["symbol"] == "BTCUSDT"].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    # returns column exists; first is NaN
    df = df[["timestamp", "returns"]].copy()
    df = df.dropna(subset=["returns"]).reset_index(drop=True)
    return df


def split_indices(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    ts = df["timestamp"]
    train_idx = np.where(ts <= TRAIN_END)[0]
    val_idx = np.where((ts >= VAL_START) & (ts <= VAL_END))[0]
    holdout_idx = np.where(ts >= HOLDOUT_START)[0]
    return {"train": train_idx, "val": val_idx, "holdout": holdout_idx}


def reorder_hmm_by_mean(model: GaussianHMM) -> GaussianHMM:
    means = model.means_.reshape(-1)
    order = np.argsort(means)
    model.startprob_ = model.startprob_[order]
    model.startprob_ = model.startprob_ / model.startprob_.sum()
    model.transmat_ = model.transmat_[order][:, order]
    model.transmat_ = model.transmat_ / model.transmat_.sum(axis=1, keepdims=True)
    model.means_ = model.means_[order]
    if hasattr(model, "_covars_"):
        model._covars_ = model._covars_[order]
    else:
        cov = np.array(model.covars_)
        if cov.ndim == 3:
            model.covars_ = cov[order, :, :]
        elif cov.ndim == 2:
            model.covars_ = cov[order, :]
        else:
            model.covars_ = cov[order]
    return model


def fit_ordered_hmm(returns: np.ndarray, seeds: Tuple[int, ...] = DEFAULT_SEEDS,
                    n_states: int = N_STATES) -> GaussianHMM:
    X = np.asarray(returns, dtype=float).reshape(-1, 1)
    if len(X) < 100:
        raise ValueError("insufficient data for HMM fit")
    best_model = None
    best_score = -np.inf
    for seed in seeds:
        try:
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="diag",
                n_iter=200,
                tol=1e-3,
                random_state=int(seed),
                init_params="stmc",
                params="stmc",
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(X)
            score = float(model.score(X))
            if np.isfinite(score) and score > best_score:
                best_score = score
                best_model = model
        except Exception:
            continue
    if best_model is None:
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=200,
            tol=1e-2,
            random_state=42,
            init_params="stmc",
            params="stmc",
        )
        model.fit(X)
        best_model = model
        best_score = float(model.score(X))
    best_model = reorder_hmm_by_mean(best_model)
    best_model.train_log_likelihood_ = float(best_score)
    return best_model


def model_state_params(model: GaussianHMM) -> Tuple[np.ndarray, np.ndarray]:
    means = model.means_.reshape(-1)
    if hasattr(model, "covars_"):
        cov = np.array(model.covars_)
        if cov.ndim == 3:
            vars_ = cov[:, 0, 0]
        elif cov.ndim == 2:
            vars_ = cov[:, 0]
        else:
            vars_ = cov.reshape(-1)
    else:
        vars_ = np.array(getattr(model, "_covars_")).reshape(-1)
    vars_ = np.maximum(vars_, 1e-12)
    return means.astype(float), vars_.astype(float)


def filtered_state_probs(model: GaussianHMM, returns: np.ndarray) -> np.ndarray:
    X = np.asarray(returns, dtype=float).reshape(-1, 1)
    _, post = model.score_samples(X)
    post = np.asarray(post, dtype=float)
    post = np.clip(post, 1e-16, 1.0)
    post = post / post.sum(axis=1, keepdims=True)
    return post


def forecast_next_from_filtered(model: GaussianHMM, filtered_t: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    A = np.asarray(model.transmat_, dtype=float)
    A = A / A.sum(axis=1, keepdims=True)
    next_probs = filtered_t @ A
    next_probs = np.clip(next_probs, 1e-16, 1.0)
    next_probs = next_probs / next_probs.sum()
    means, vars_ = model_state_params(model)
    return next_probs, means, vars_


def gaussian_logpdf(y: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    var = np.maximum(var, 1e-12)
    return -0.5 * (np.log(2 * np.pi * var) + (y - mu) ** 2 / var)


def mixture_logpdf(y: float, probs: np.ndarray, means: np.ndarray, vars_: np.ndarray) -> float:
    log_comp = gaussian_logpdf(np.array([y]), means, vars_) + np.log(np.clip(probs, 1e-16, 1.0))
    m = np.max(log_comp)
    return float(m + np.log(np.sum(np.exp(log_comp - m))))


def gaussian_crps(y: float, mu: float, sigma: float) -> float:
    # Gneiting & Raftery closed form for Normal
    if sigma <= 1e-12:
        return float(abs(y - mu))
    from math import erf, sqrt, pi
    z = (y - mu) / sigma
    phi = (1.0 / sqrt(2 * pi)) * math.exp(-0.5 * z * z)
    Phi = 0.5 * (1.0 + erf(z / sqrt(2)))
    return float(sigma * (z * (2 * Phi - 1) + 2 * phi - 1 / sqrt(pi)))


def mixture_crps_grid(y: float, probs: np.ndarray, means: np.ndarray, vars_: np.ndarray) -> float:
    # Numerical CRPS via CDF integration over adaptive grid
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
    # vectorized erf approximation (Abramowitz-Stegun 7.1.26)
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
    # RiskMetrics-style EWMA variance on returns, mean = expanding mean
    if len(history) == 0:
        return 0.0, 1e-6
    mu = float(np.mean(history))
    r = history - mu
    if len(r) == 1:
        var = float(r[0] ** 2 + 1e-8)
    else:
        var = float(np.var(r, ddof=1))
        for x in r[-500:]:  # limit work but keep long memory effect reasonable
            var = lam * var + (1 - lam) * float(x ** 2)
    var = max(var, 1e-10)
    return mu, var


def brier_score_state(probs: np.ndarray, realized_state: int, n_states: int = N_STATES) -> float:
    y = np.zeros(n_states)
    y[int(realized_state)] = 1.0
    return float(np.sum((probs - y) ** 2))


def state_log_loss(probs: np.ndarray, realized_state: int) -> float:
    p = float(np.clip(probs[int(realized_state)], 1e-16, 1.0))
    return float(-np.log(p))


def run_walkforward(
    df: pd.DataFrame,
    refit_every: int = DEFAULT_REFIT_EVERY,
    seeds: Tuple[int, ...] = DEFAULT_SEEDS,
    val_start: pd.Timestamp = VAL_START,
    val_end: pd.Timestamp = VAL_END,
    eval_stride: int = 1,
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

    results: List[ForecastResult] = []
    refit_records = []
    current_model = None
    last_refit_i = None

    for i in val_idx:
        if i + 1 >= len(df):
            break
        target_ts = timestamps.iloc[i + 1]
        if target_ts >= HOLDOUT_START:
            break
        # fit on data up to i (inclusive), forecast i+1; never uses future
        need_refit = current_model is None or (i - (last_refit_i or 0)) >= refit_every
        if need_refit:
            train_slice = returns[: i + 1]
            current_model = fit_ordered_hmm(train_slice, seeds=seeds)
            last_refit_i = i
            means_m, vars_m = model_state_params(current_model)
            refit_records.append({
                "refit_at_index": int(i),
                "refit_timestamp": str(timestamps.iloc[i]),
                "train_size": int(i + 1),
                "log_likelihood": float(getattr(current_model, "train_log_likelihood_", np.nan)),
                "transmat": np.asarray(current_model.transmat_, dtype=float).tolist(),
                "means": means_m.tolist(),
                "vars": vars_m.tolist(),
                "stationary_like_occupancy_proxy": np.mean(filtered_state_probs(current_model, train_slice), axis=0).tolist(),
            })

        assert current_model is not None
        hist = returns[: i + 1]
        filt = filtered_state_probs(current_model, hist)[-1]
        next_probs, mix_means, mix_vars = forecast_next_from_filtered(current_model, filt)
        hmm_mu = float(np.sum(next_probs * mix_means))
        hmm_var = float(np.sum(next_probs * (mix_vars + mix_means ** 2)) - hmm_mu ** 2)
        hmm_var = max(hmm_var, 1e-12)

        unc_mu, unc_var = expanding_unconditional_params(hist)
        ewma_mu, ewma_var = ewma_forecast_params(hist, lam=0.94)

        # realized state under current refit model using filtered probs up to t+1 (diagnostic; model-dependent)
        filt_t1 = filtered_state_probs(current_model, returns[: i + 2])[-1]
        realized_state = int(np.argmax(filt_t1))

        y_true = float(returns[i + 1])
        hmm_log = mixture_logpdf(y_true, next_probs, mix_means, mix_vars)
        unc_log = float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0])
        ewma_log = float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0])
        hmm_crps = mixture_crps_grid(y_true, next_probs, mix_means, mix_vars)
        unc_crps = gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))
        ewma_crps = gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))
        results.append(ForecastResult(
            timestamp=target_ts,
            y_true=y_true,
            hmm_state_probs_next=next_probs,
            hmm_mix_means=mix_means,
            hmm_mix_vars=mix_vars,
            hmm_mu=hmm_mu,
            hmm_var=hmm_var,
            unc_mu=unc_mu,
            unc_var=unc_var,
            ewma_mu=ewma_mu,
            ewma_var=ewma_var,
            realized_state=realized_state,
            hmm_log=hmm_log,
            unc_log=unc_log,
            ewma_log=ewma_log,
            hmm_crps=hmm_crps,
            unc_crps=unc_crps,
            ewma_crps=ewma_crps,
        ))

    metrics = compute_metrics(results)
    stability = summarize_refits(refit_records)
    payload = {
        "config": {
            "symbol": "BTCUSDT",
            "frequency": "1h",
            "n_states": N_STATES,
            "refit_every": int(refit_every),
            "seeds": list(seeds),
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


def row_to_dict(r: ForecastResult) -> Dict:
    return {
        "timestamp": str(r.timestamp),
        "y_true": r.y_true,
        "hmm_state_probs_next": r.hmm_state_probs_next.tolist(),
        "hmm_mix_means": r.hmm_mix_means.tolist(),
        "hmm_mix_vars": r.hmm_mix_vars.tolist(),
        "hmm_mu": r.hmm_mu,
        "hmm_var": r.hmm_var,
        "unc_mu": r.unc_mu,
        "unc_var": r.unc_var,
        "ewma_mu": r.ewma_mu,
        "ewma_var": r.ewma_var,
        "realized_state_diagnostic": r.realized_state,
        "hmm_log": r.hmm_log,
        "unc_log": r.unc_log,
        "ewma_log": r.ewma_log,
        "hmm_crps": r.hmm_crps,
        "unc_crps": r.unc_crps,
        "ewma_crps": r.ewma_crps,
    }


def compute_metrics(results: List[ForecastResult]) -> Dict:
    hmm_log = np.array([r.hmm_log for r in results], dtype=float)
    unc_log = np.array([r.unc_log for r in results], dtype=float)
    ewma_log = np.array([r.ewma_log for r in results], dtype=float)
    hmm_crps = np.array([r.hmm_crps for r in results], dtype=float)
    unc_crps = np.array([r.unc_crps for r in results], dtype=float)
    ewma_crps = np.array([r.ewma_crps for r in results], dtype=float)
    brier = []
    slog = []
    pit_hmm = []
    for r in results:
        if r.realized_state is not None:
            brier.append(brier_score_state(r.hmm_state_probs_next, r.realized_state))
            slog.append(state_log_loss(r.hmm_state_probs_next, r.realized_state))
        # PIT for HMM mixture CDF
        cdf = 0.0
        for p, m, v in zip(r.hmm_state_probs_next, r.hmm_mix_means, r.hmm_mix_vars):
            s = math.sqrt(max(v, 1e-12))
            z = (r.y_true - m) / s
            cdf += float(p) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        pit_hmm.append(float(np.clip(cdf, 0.0, 1.0)))

    def stats(arr):
        a = np.asarray(arr, dtype=float)
        return {"mean": float(np.mean(a)), "median": float(np.median(a)), "std": float(np.std(a))}

    pit = np.asarray(pit_hmm)
    pit_hist, pit_edges = np.histogram(pit, bins=10, range=(0, 1), density=True)
    return {
        "log_score_higher_is_better": {
            "hmm_mixture": stats(hmm_log),
            "unconditional_gaussian": stats(unc_log),
            "ewma_gaussian": stats(ewma_log),
        },
        "crps_lower_is_better": {
            "hmm_mixture": stats(hmm_crps),
            "unconditional_gaussian": stats(unc_crps),
            "ewma_gaussian": stats(ewma_crps),
        },
        "state_probability_diagnostic_model_dependent": {
            "brier_lower_is_better": stats(brier) if brier else None,
            "log_loss_lower_is_better": stats(slog) if slog else None,
            "note": "Realized state is argmax filtered prob at t+1 under each refit model; diagnostic only, not ground truth.",
        },
        "pit_hmm": {
            "mean": float(np.mean(pit)) if len(pit) else None,
            "std": float(np.std(pit)) if len(pit) else None,
            "hist_density": pit_hist.tolist() if len(pit) else [],
            "bin_edges": pit_edges.tolist() if len(pit) else [],
        },
        "n_obs": int(len(hmm_log)),
    }


def summarize_refits(refits: List[Dict]) -> Dict:
    if not refits:
        return {}
    occ = np.array([r["stationary_like_occupancy_proxy"] for r in refits], dtype=float)
    means = np.array([r["means"] for r in refits], dtype=float)
    trans = np.array([r["transmat"] for r in refits], dtype=float)
    return {
        "n_refits": len(refits),
        "occupancy_proxy_mean": occ.mean(axis=0).tolist(),
        "occupancy_proxy_std": occ.std(axis=0).tolist(),
        "state_means_across_refits_mean": means.mean(axis=0).tolist(),
        "state_means_across_refits_std": means.std(axis=0).tolist(),
        "transmat_mean": trans.mean(axis=0).tolist(),
        "transmat_std": trans.std(axis=0).tolist(),
    }


def save_outputs(payload: Dict, results: List[ForecastResult], refits: List[Dict], out_dir: Path = OUT_DIR) -> None:
    fig_dir = out_dir / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "h2_hmm_validation_results.json", "w") as f:
        json.dump(payload, f, indent=2)

    # compact forecast table
    rows = []
    for r in results:
        rows.append({
            "timestamp": r.timestamp,
            "y_true": r.y_true,
            "p_s0": float(r.hmm_state_probs_next[0]),
            "p_s1": float(r.hmm_state_probs_next[1]),
            "p_s2": float(r.hmm_state_probs_next[2]),
            "hmm_mu": r.hmm_mu,
            "hmm_var": r.hmm_var,
            "unc_mu": r.unc_mu,
            "unc_var": r.unc_var,
            "ewma_mu": r.ewma_mu,
            "ewma_var": r.ewma_var,
            "hmm_log": r.hmm_log,
            "unc_log": r.unc_log,
            "ewma_log": r.ewma_log,
            "hmm_crps": r.hmm_crps,
            "unc_crps": r.unc_crps,
            "ewma_crps": r.ewma_crps,
        })
    pd.DataFrame(rows).to_csv(out_dir / "h2_validation_forecasts.csv", index=False)

    if plt is not None and results:
        ts = [r.timestamp for r in results]
        p = np.array([r.hmm_state_probs_next for r in results])
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(ts, p[:, 0], label="P(S0)", linewidth=0.8)
        ax.plot(ts, p[:, 1], label="P(S1)", linewidth=0.8)
        ax.plot(ts, p[:, 2], label="P(S2)", linewidth=0.8)
        ax.set_title("HMM 1-step-ahead filtered state probabilities (validation)")
        ax.set_ylabel("Probability")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(fig_dir / "h2_next_state_probs.png", dpi=150)
        plt.close(fig)

        pit = []
        for r in results:
            cdf = 0.0
            for pr, m, v in zip(r.hmm_state_probs_next, r.hmm_mix_means, r.hmm_mix_vars):
                s = math.sqrt(max(v, 1e-12))
                z = (r.y_true - m) / s
                cdf += float(pr) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            pit.append(cdf)
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.hist(pit, bins=10, range=(0, 1), density=True, alpha=0.8, color="#4c78a8")
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
        ax.set_title("HMM mixture PIT (validation)")
        ax.set_xlabel("PIT")
        ax.set_ylabel("Density")
        fig.tight_layout()
        fig.savefig(fig_dir / "h2_pit_hist.png", dpi=150)
        plt.close(fig)

    write_markdown_report(payload, out_dir / "h2_hmm_validation.md")


def write_markdown_report(payload: Dict, path: Path) -> None:
    m = payload["metrics"]
    c = payload["config"]
    counts = payload["counts"]
    stab = payload.get("refit_stability", {})
    lines = []
    lines.append("# H2 Walk-forward Filtered HMM Forecast Validation (BTCUSDT 1h)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Symbol/Freq:** {c['symbol']} / {c['frequency']}")
    lines.append(f"**Validation window:** {c['val_start']} to {c['val_end']} (holdout >= {c['holdout_start']} excluded)")
    lines.append(f"**Model:** {c['n_states']}-state Gaussian HMM (diag), states ordered by mean; refit every {c['refit_every']} bars on expanding history; eval_stride={c.get('eval_stride',1)}; seeds={c['seeds']}")
    lines.append("")
    lines.append("## Scope and leakage controls")
    lines.append("- Expanding fit uses returns up to time *t* only; forecast targets *t+1* in validation window.")
    lines.append("- Filtered probabilities computed via forward algorithm (`score_samples`/forward posterior) on history up to *t*; no smoothed/Viterbi full-sample decoding used for forecasts.")
    lines.append("- Locked holdout period (>= 2024-07-01) not used for fitting, selection, or evaluation in this run.")
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
    for k in ["hmm_mixture", "unconditional_gaussian", "ewma_gaussian"]:
        lines.append(f"- {k}: {ls[k]['mean']:.6f} (median {ls[k]['median']:.6f})")
    lines.append("")
    lines.append("### CRPS (mean, lower is better)")
    for k in ["hmm_mixture", "unconditional_gaussian", "ewma_gaussian"]:
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
    pit = m.get("pit_hmm", {})
    lines.append("### Calibration diagnostic")
    lines.append(f"- HMM mixture PIT mean={pit.get('mean')} std={pit.get('std')} (ideal uniform: mean 0.5, std ~0.289)")
    lines.append("")
    lines.append("## Refitting stability / regime occupancy proxy")
    if stab:
        lines.append(f"- Refits: {stab.get('n_refits')}")
        lines.append(f"- Mean occupancy proxy across refits: {stab.get('occupancy_proxy_mean')}")
        lines.append(f"- Occupancy proxy std across refits: {stab.get('occupancy_proxy_std')}")
        lines.append(f"- State mean estimates mean across refits: {stab.get('state_means_across_refits_mean')}")
        lines.append(f"- State mean estimates std across refits: {stab.get('state_means_across_refits_std')}")
    else:
        lines.append("- No refit stability summary available.")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("- `research/forecasts/h2_hmm_validation_results.json`")
    lines.append("- `research/forecasts/h2_validation_forecasts.csv`")
    lines.append("- `research/forecasts/figures/h2_next_state_probs.png`")
    lines.append("- `research/forecasts/figures/h2_pit_hist.png`")
    lines.append("")
    lines.append("## Interpretation notes")
    lines.append("- Validation-only H2 groundwork; not a trading backtest and not a final holdout evaluation.")
    lines.append("- Non-stationarity observed in prior EDA (Chow tests) may affect parameter/refit stability; see refit summaries.")
    lines.append("- Realized HMM states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison here.")
    path.write_text("\n".join(lines) + "\n")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load_btc_returns(DATA_PATH)
    # coarse cadence/stride keep runtime bounded in this environment while preserving expanding, filtered, validation-only evaluation
    out = run_walkforward(df, refit_every=720, seeds=(0, 1, 2), eval_stride=4)
    save_outputs(out["payload"], out["results"], out["refits"], OUT_DIR)
    print(json.dumps({
        "validation_forecasts": out["payload"]["counts"]["validation_forecasts"],
        "refits": out["payload"]["counts"]["refits"],
        "log_score_means": out["payload"]["metrics"]["log_score_higher_is_better"],
        "crps_means": out["payload"]["metrics"]["crps_lower_is_better"],
    }, indent=2))


if __name__ == "__main__":
    main()
