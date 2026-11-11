#!/usr/bin/env python3
"""
Task T5d-robustness-c: Negative controls for C1/HMM and C2/HOM on saved validation grids.

Generates no-information negative-control forecasts and compares real-model skill
against them using a stationary block bootstrap. No holdout data is used; no model
tuning is performed.

Negative controls (research prompt §7, §8 priority 7 red-team):
  NC_A white_noise:  Gaussian N(0, sigma_y^2) -- pure no-information forecast
                     (mu fixed at 0, variance = sample variance of validation returns).
  NC_B target_shuffled: model forecast moments (mu, var) paired with a stationary-
                        bootstrap resampled y_true, which destroys the genuine
                        forecast->target relationship while preserving the forecast
                        marginal distribution and target temporal structure.

Comparisons (stationary block bootstrap, block length n^(1/3), 2000 replications):
  - real model vs white noise            (log score, CRPS)  -> expect real > control
  - real model vs target-shuffled model  (log score, CRPS)  -> expect real > control
  - target-shuffled vs white noise       (log score, CRPS)  -> expect ~0 / not significant

Outputs:
  research/forecasts/negative_controls.json
  research/forecasts/negative_controls.md
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

HMM_CSV = Path("research/forecasts/h2_validation_forecasts.csv")
HOM_CSV = Path("research/forecasts/h3_higher_order_markov_validation.csv")
OUT_JSON = Path("research/forecasts/negative_controls.json")
OUT_MD = Path("research/forecasts/negative_controls.md")

VAL_START = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
VAL_END = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")

N_SHUFFLE = 200          # stationary-bootstrap target resamples for the negative control
N_BOOTSTRAP = 2000       # block-bootstrap replications per paired comparison
SEED = 42


def gaussian_logpdf(y: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    var = np.maximum(np.asarray(var, dtype=float), 1e-12)
    mu = np.asarray(mu, dtype=float)
    y = np.asarray(y, dtype=float)
    return -0.5 * (np.log(2.0 * np.pi * var) + (y - mu) ** 2 / var)


def gaussian_crps(y: float, mu: float, var: float) -> float:
    sigma = math.sqrt(max(float(var), 1e-12))
    if sigma <= 1e-12:
        return float(abs(y - mu))
    z = (y - mu) / sigma
    phi = (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * z * z)
    Phi = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return float(sigma * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / math.sqrt(math.pi)))


def stationary_bootstrap_indices(n: int, block_length: float, n_draws: int, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / max(float(block_length), 1.0)
    indices = np.empty((n_draws, n), dtype=int)
    for b in range(n_draws):
        i = int(rng.integers(0, n))
        for t in range(n):
            indices[b, t] = i
            if rng.random() < p:
                i = int(rng.integers(0, n))
            else:
                i = (i + 1) % n
    return indices


@dataclass
class BootSummary:
    mean: float
    ci_lower: float
    ci_upper: float
    p_value_two_sided: float
    effective_sample_size: int
    block_length: float
    n_bootstrap: int
    n_obs: int


def bootstrap_mean(values: np.ndarray, n_bootstrap: int = N_BOOTSTRAP, seed: int = SEED,
                   block_length: float | None = None) -> BootSummary:
    vals = np.asarray(values, dtype=float)
    n = len(vals)
    if block_length is None:
        block_length = max(1.0, n ** (1.0 / 3.0))
    rng = np.random.default_rng(seed)
    idx = stationary_bootstrap_indices(n, block_length, n_bootstrap, rng)
    boot_means = np.mean(vals[idx], axis=1)
    mean = float(np.mean(vals))
    ci_lower = float(np.percentile(boot_means, 2.5))
    ci_upper = float(np.percentile(boot_means, 97.5))
    centered = boot_means - np.mean(boot_means)
    p_value = float(np.mean(np.abs(centered) >= abs(mean)))
    var_iid = float(np.var(vals, ddof=1) / n) if n > 1 else 0.0
    var_boot = float(np.var(boot_means, ddof=1)) if n_bootstrap > 1 else 0.0
    eff_n = int(np.round(n * var_iid / max(var_boot, 1e-16))) if var_boot > 0 else n
    return BootSummary(mean, ci_lower, ci_upper, p_value, eff_n, float(block_length), n_bootstrap, n)


def load_model_grid(csv_path: Path, model_prefix: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    ts = pd.to_datetime(df["timestamp"], utc=True)
    df = df[(ts >= VAL_START) & (ts < VAL_END)].copy()
    df["timestamp"] = ts[(ts >= VAL_START) & (ts < VAL_END)].to_numpy()
    y = df["y_true"].to_numpy(dtype=float)
    mu = df[f"{model_prefix}_mu"].to_numpy(dtype=float)
    var = df[f"{model_prefix}_var"].to_numpy(dtype=float)
    out = pd.DataFrame({
        "timestamp": df["timestamp"].to_numpy(),
        "y_true": y,
        "model_mu": mu,
        "model_var": var,
        "unc_mu": df["unc_mu"].to_numpy(dtype=float),
        "unc_var": df["unc_var"].to_numpy(dtype=float),
        "ewma_mu": df["ewma_mu"].to_numpy(dtype=float),
        "ewma_var": df["ewma_var"].to_numpy(dtype=float),
    })
    out["model_log_score"] = gaussian_logpdf(y, mu, var)
    out["model_crps"] = [gaussian_crps(yy, m, v) for yy, m, v in zip(y, mu, var)]
    out["unc_log_score"] = gaussian_logpdf(y, out["unc_mu"].to_numpy(), out["unc_var"].to_numpy())
    out["unc_crps"] = [gaussian_crps(yy, m, v) for yy, m, v in zip(y, out["unc_mu"].to_numpy(), out["unc_var"].to_numpy())]
    out["ewma_log_score"] = gaussian_logpdf(y, out["ewma_mu"].to_numpy(), out["ewma_var"].to_numpy())
    out["ewma_crps"] = [gaussian_crps(yy, m, v) for yy, m, v in zip(y, out["ewma_mu"].to_numpy(), out["ewma_var"].to_numpy())]
    return out


def white_noise_scores(y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict]:
    var_y = float(np.var(y, ddof=1))
    mu_wn = np.zeros_like(y)
    var_wn = np.full_like(y, max(var_y, 1e-12))
    log_score = gaussian_logpdf(y, mu_wn, var_wn)
    crps = np.array([gaussian_crps(yy, 0.0, var_y) for yy in y])
    return log_score, crps, {"mu": 0.0, "var": var_y}


def target_shuffled_scores(model_mu: np.ndarray, model_var: np.ndarray, y: np.ndarray,
                           n_shuffle: int = N_SHUFFLE, seed: int = SEED) -> Tuple[np.ndarray, np.ndarray]:
    """Model log score / CRPS against stationary-bootstrap resampled targets.

    Returns mean-over-shuffles score at each time step (shape (n,)). Destroying the
    forecast->target alignment yields the no-information negative control.
    """
    n = len(y)
    rng = np.random.default_rng(seed)
    block_length = max(1.0, n ** (1.0 / 3.0))
    idx = stationary_bootstrap_indices(n, block_length, n_shuffle, rng)
    y_shuffled = y[idx]  # (n_shuffle, n)

    log_scores = np.empty((n_shuffle, n))
    crps_vals = np.empty((n_shuffle, n))
    for b in range(n_shuffle):
        yb = y_shuffled[b]
        log_scores[b] = gaussian_logpdf(yb, model_mu, model_var)
        crps_vals[b] = np.array([gaussian_crps(yy, m, v) for yy, m, v in zip(yb, model_mu, model_var)])

    return np.mean(log_scores, axis=0), np.mean(crps_vals, axis=0)


def paired_bootstrap(diff: np.ndarray, n_bootstrap: int = N_BOOTSTRAP, seed: int = SEED) -> BootSummary:
    return bootstrap_mean(diff, n_bootstrap=n_bootstrap, seed=seed)


def analyze_model(name: str, candidate: str, csv_path: Path, model_prefix: str) -> Dict:
    df = load_model_grid(csv_path, model_prefix)
    y = df["y_true"].to_numpy(dtype=float)
    n = int(len(df))

    # Negative controls
    wn_log, wn_crps, wn_params = white_noise_scores(y)
    sh_log, sh_crps = target_shuffled_scores(
        df["model_mu"].to_numpy(), df["model_var"].to_numpy(), y, n_shuffle=N_SHUFFLE, seed=SEED
    )

    # Point means
    point = {
        "real_model": {
            "log_score_mean": float(df["model_log_score"].mean()),
            "crps_mean": float(df["model_crps"].mean()),
        },
        "white_noise": {
            "log_score_mean": float(wn_log.mean()),
            "crps_mean": float(wn_crps.mean()),
            "mu": wn_params["mu"],
            "var": wn_params["var"],
        },
        "target_shuffled": {
            "log_score_mean": float(sh_log.mean()),
            "crps_mean": float(sh_crps.mean()),
            "n_shuffle_resamples": int(N_SHUFFLE),
        },
        "unc_baseline": {
            "log_score_mean": float(df["unc_log_score"].mean()),
            "crps_mean": float(df["unc_crps"].mean()),
        },
        "ewma_baseline": {
            "log_score_mean": float(df["ewma_log_score"].mean()),
            "crps_mean": float(df["ewma_crps"].mean()),
        },
    }

    # Paired differences over time, then block-bootstrap significance
    diffs = {
        "real_minus_white_noise_log": df["model_log_score"].to_numpy() - wn_log,
        "real_minus_white_noise_crps": wn_crps - df["model_crps"].to_numpy(),  # >0 real better
        "real_minus_shuffled_log": df["model_log_score"].to_numpy() - sh_log,
        "real_minus_shuffled_crps": sh_crps - df["model_crps"].to_numpy(),  # >0 real better
        "shuffled_minus_white_noise_log": sh_log - wn_log,
        "shuffled_minus_white_noise_crps": wn_crps - sh_crps,
    }
    boot = {k: asdict(paired_bootstrap(v)) for k, v in diffs.items()}

    return {
        "model": name,
        "candidate": candidate,
        "source_csv": str(csv_path),
        "n_forecasts": n,
        "time_start": str(df["timestamp"].min()),
        "time_end": str(df["timestamp"].max()),
        "holdout_used": False,
        "method": {
            "scores": "gaussian_moment_log_score_and_crps",
            "bootstrap": "stationary_block_bootstrap",
            "block_length_rule": "n^(1/3)",
            "n_bootstrap": int(N_BOOTSTRAP),
            "n_shuffle_resamples": int(N_SHUFFLE),
            "ci": "percentile_95",
        },
        "white_noise_params": wn_params,
        "point_means": point,
        "paired_differences": boot,
    }


def render_md(report: Dict) -> str:
    lines: List[str] = []
    lines.append("# Negative Controls for C1/HMM and C2/HOM (Validation Only)")
    lines.append("")
    lines.append(f"**Generated (UTC):** {report['generated_utc']}")
    lines.append("**Scope:** Validation-only red-team robustness check on saved BTCUSDT 1h forecast grids.")
    lines.append("No holdout data used; no model tuning performed.")
    lines.append("")
    lines.append("## Method")
    lines.append("- Real model: saved mixture-moment Gaussian log score / CRPS on the saved validation grid.")
    lines.append("- NC_A white noise: Gaussian N(0, sigma_y^2), pure no-information forecast.")
    lines.append("- NC_B target-shuffled: model moments paired with stationary-bootstrap resampled y_true,")
    lines.append("  destroying the genuine forecast->target relationship (n_shuffle resamples averaged).")
    lines.append("- Uncertainty: stationary block bootstrap (Politis & Romano 1994), block length n^(1/3),")
    lines.append("  2000 replications, 95% percentile CIs, two-sided p-values for H0: mean paired difference = 0.")
    lines.append("- Interpretation: a genuine edge should beat both negative controls significantly; the")
    lines.append("  shuffled-vs-white-noise comparison should be ~0 / not significant, confirming the shuffle")
    lines.append("  removes information without injecting spurious skill.")
    lines.append("")
    for m in report["models"]:
        lines.append(f"## {m['model']} ({m['candidate']})")
        lines.append(f"Source: `{m['source_csv']}` (n={m['n_forecasts']}, {m['time_start']} to {m['time_end']})")
        lines.append("")
        pm = m["point_means"]
        lines.append("| Control | Log score mean | CRPS mean |")
        lines.append("|---|---:|---:|")
        lines.append(f"| Real model | {pm['real_model']['log_score_mean']:.6f} | {pm['real_model']['crps_mean']:.6e} |")
        lines.append(f"| White noise (NC_A) | {pm['white_noise']['log_score_mean']:.6f} | {pm['white_noise']['crps_mean']:.6e} |")
        lines.append(f"| Target-shuffled (NC_B) | {pm['target_shuffled']['log_score_mean']:.6f} | {pm['target_shuffled']['crps_mean']:.6e} |")
        lines.append(f"| Unconditional baseline | {pm['unc_baseline']['log_score_mean']:.6f} | {pm['unc_baseline']['crps_mean']:.6e} |")
        lines.append(f"| EWMA baseline | {pm['ewma_baseline']['log_score_mean']:.6f} | {pm['ewma_baseline']['crps_mean']:.6e} |")
        lines.append("")
        lines.append("### Paired-difference block bootstrap (mean diff, 95% CI, p-value, eff. n)")
        lines.append("| Comparison | Direction | Mean diff | 95% CI | p-value | Eff. n | Significant @5% |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        pd_ = m["paired_differences"]
        rows = [
            ("real_minus_white_noise_log", "real > white noise (log)", "log score"),
            ("real_minus_white_noise_crps", "real > white noise (CRPS)", "CRPS"),
            ("real_minus_shuffled_log", "real > shuffled (log)", "log score"),
            ("real_minus_shuffled_crps", "real > shuffled (CRPS)", "CRPS"),
            ("shuffled_minus_white_noise_log", "shuffled ~ white noise (log)", "log score"),
            ("shuffled_minus_white_noise_crps", "shuffled ~ white noise (CRPS)", "CRPS"),
        ]
        for key, direction, _metric in rows:
            r = pd_[key]
            sig = "Yes" if (r["ci_lower"] > 0 or r["ci_upper"] < 0) else "No"
            lines.append(
                f"| {key} | {direction} | {r['mean']:+.6e} | [{r['ci_lower']:+.6e}, {r['ci_upper']:+.6e}] | "
                f"{r['p_value_two_sided']:.4f} | {r['effective_sample_size']} | {sig} |"
            )
        lines.append("")
    lines.append("## Interpretation")
    lines.append("- A real predictive edge should show significant positive paired differences vs both negative controls.")
    lines.append("- The shuffled-vs-white-noise comparison being ~0 / not significant confirms the target shuffle removes")
    lines.append("  information without creating spurious skill.")
    lines.append("- Results are validation-period diagnostics on a stride-4 sampled grid; they are not holdout evidence.")
    lines.append("- No holdout evaluation performed.")
    return "\n".join(lines) + "\n"


def main() -> Dict:
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "validation_only",
        "holdout_used": False,
        "method": {
            "scores": "gaussian_moment_log_score_and_crps",
            "bootstrap": "stationary_block_bootstrap",
            "block_length_rule": "n^(1/3)",
            "n_bootstrap": int(N_BOOTSTRAP),
            "n_shuffle_resamples": int(N_SHUFFLE),
            "ci": "percentile_95",
        },
        "models": [
            analyze_model("H2 filtered HMM (C1 primary)", "C1", HMM_CSV, "hmm"),
            analyze_model("H3 higher-order Markov (C2 comparator)", "C2", HOM_CSV, "hom"),
        ],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2))
    OUT_MD.write_text(render_md(report))
    print(json.dumps({
        "wrote": [str(OUT_JSON), str(OUT_MD)],
        "models": [m["model"] for m in report["models"]],
    }, indent=2))
    return report


if __name__ == "__main__":
    main()
