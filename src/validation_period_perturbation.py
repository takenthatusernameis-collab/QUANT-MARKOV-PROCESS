#!/usr/bin/env python3
"""
Validation-only period perturbation (robustness) for C1/HMM and C2/HOM forecasts.

Splits the saved validation-grid forecasts into 2024 Q1 (Jan-Mar) and Q2 (Apr-Jun),
computes proper scores (Gaussian log score, Gaussian CRPS from per-row moments),
and reports point estimates plus stationary block-bootstrap 95% CIs / p-values
for mean scores and paired differences vs unconditional/EWMA baselines.

No holdout data is used. No model tuning is performed.
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
OUT_JSON = Path("research/forecasts/period_perturbation_q1q2.json")
OUT_MD = Path("research/forecasts/period_perturbation_q1q2.md")

Q1_START = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
Q1_END = pd.Timestamp("2024-04-01 00:00:00", tz="UTC")
Q2_START = Q1_END
Q2_END = pd.Timestamp("2024-07-01 00:00:00", tz="UTC")


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


def stationary_bootstrap_indices(n: int, block_length: float, n_bootstrap: int, rng: np.random.Generator) -> np.ndarray:
    p = 1.0 / max(float(block_length), 1.0)
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


def bootstrap_mean(values: np.ndarray, n_bootstrap: int = 2000, seed: int = 42, block_length: float | None = None) -> BootSummary:
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


def split_period(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    ts = pd.to_datetime(df["timestamp"], utc=True)
    return {
        "Q1_2024": df[(ts >= Q1_START) & (ts < Q1_END)].copy(),
        "Q2_2024": df[(ts >= Q2_START) & (ts < Q2_END)].copy(),
    }


def score_frame(df: pd.DataFrame, model_prefix: str) -> pd.DataFrame:
    y = df["y_true"].to_numpy(dtype=float)
    mu = df[f"{model_prefix}_mu"].to_numpy(dtype=float)
    var = df[f"{model_prefix}_var"].to_numpy(dtype=float)
    unc_mu = df["unc_mu"].to_numpy(dtype=float)
    unc_var = df["unc_var"].to_numpy(dtype=float)
    ewma_mu = df["ewma_mu"].to_numpy(dtype=float)
    ewma_var = df["ewma_var"].to_numpy(dtype=float)
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df["timestamp"], utc=True).to_numpy(),
        "y_true": y,
        "model_log_score": gaussian_logpdf(y, mu, var),
        "unc_log_score": gaussian_logpdf(y, unc_mu, unc_var),
        "ewma_log_score": gaussian_logpdf(y, ewma_mu, ewma_var),
    })
    out["model_crps"] = [gaussian_crps(yy, m, v) for yy, m, v in zip(y, mu, var)]
    out["unc_crps"] = [gaussian_crps(yy, m, v) for yy, m, v in zip(y, unc_mu, unc_var)]
    out["ewma_crps"] = [gaussian_crps(yy, m, v) for yy, m, v in zip(y, ewma_mu, ewma_var)]
    out["d_log_model_minus_unc"] = out["model_log_score"] - out["unc_log_score"]
    out["d_log_model_minus_ewma"] = out["model_log_score"] - out["ewma_log_score"]
    out["d_crps_unc_minus_model"] = out["unc_crps"] - out["model_crps"]  # >0 model better
    out["d_crps_ewma_minus_model"] = out["ewma_crps"] - out["model_crps"]
    return out


def summarize_period(scores: pd.DataFrame, label: str, seed_base: int) -> Dict:
    def pack(series: np.ndarray, seed_offset: int) -> Dict:
        b = bootstrap_mean(series, n_bootstrap=2000, seed=seed_base + seed_offset)
        return asdict(b)

    return {
        "period": label,
        "n_obs": int(len(scores)),
        "time_start": str(scores["timestamp"].min()) if len(scores) else None,
        "time_end": str(scores["timestamp"].max()) if len(scores) else None,
        "point_means": {
            "model_log_score": float(scores["model_log_score"].mean()),
            "unc_log_score": float(scores["unc_log_score"].mean()),
            "ewma_log_score": float(scores["ewma_log_score"].mean()),
            "model_crps": float(scores["model_crps"].mean()),
            "unc_crps": float(scores["unc_crps"].mean()),
            "ewma_crps": float(scores["ewma_crps"].mean()),
        },
        "bootstrap_mean_scores": {
            "model_log_score": pack(scores["model_log_score"].to_numpy(), 0),
            "model_crps": pack(scores["model_crps"].to_numpy(), 1),
        },
        "bootstrap_paired_diffs": {
            "log_model_minus_unc_higher_better": pack(scores["d_log_model_minus_unc"].to_numpy(), 10),
            "log_model_minus_ewma_higher_better": pack(scores["d_log_model_minus_ewma"].to_numpy(), 11),
            "crps_unc_minus_model_lower_better_for_model": pack(scores["d_crps_unc_minus_model"].to_numpy(), 12),
            "crps_ewma_minus_model_lower_better_for_model": pack(scores["d_crps_ewma_minus_model"].to_numpy(), 13),
        },
    }


def analyze_model(name: str, csv_path: Path, model_prefix: str, seed_base: int) -> Dict:
    df = pd.read_csv(csv_path)
    parts = split_period(df)
    result = {
        "model": name,
        "candidate": "C1" if model_prefix == "hmm" else "C2",
        "source_csv": str(csv_path),
        "n_total_validation_forecasts": int(len(df)),
        "periods": {},
    }
    for i, (label, sub) in enumerate(parts.items()):
        scores = score_frame(sub, model_prefix)
        result["periods"][label] = summarize_period(scores, label, seed_base + i * 100)
    q1 = result["periods"]["Q1_2024"]["point_means"]
    q2 = result["periods"]["Q2_2024"]["point_means"]
    result["q2_minus_q1_point_deltas"] = {
        "model_log_score": q2["model_log_score"] - q1["model_log_score"],
        "model_crps": q2["model_crps"] - q1["model_crps"],
        "log_edge_vs_unc": (q2["model_log_score"] - q2["unc_log_score"]) - (q1["model_log_score"] - q1["unc_log_score"]),
        "log_edge_vs_ewma": (q2["model_log_score"] - q2["ewma_log_score"]) - (q1["model_log_score"] - q1["ewma_log_score"]),
        "crps_edge_vs_unc_baseline_minus_model": (q2["unc_crps"] - q2["model_crps"]) - (q1["unc_crps"] - q1["model_crps"]),
        "crps_edge_vs_ewma_baseline_minus_model": (q2["ewma_crps"] - q2["model_crps"]) - (q1["ewma_crps"] - q1["model_crps"]),
    }
    return result


def render_md(report: Dict) -> str:
    lines: List[str] = []
    lines.append("# Validation Period Perturbation (Q1 vs Q2 2024)")
    lines.append("")
    lines.append(f"**Generated (UTC):** {report['generated_utc']}")
    lines.append("**Scope:** Validation-only robustness check on saved BTCUSDT 1h forecast grids (stride 4). No holdout data used; no tuning.")
    lines.append("")
    lines.append("## Method")
    lines.append("- Split each model's saved validation forecasts into Q1 (2024-01-01 <= t < 2024-04-01) and Q2 (2024-04-01 <= t < 2024-07-01).")
    lines.append("- Scores computed from per-row Gaussian moments (`*_mu`, `*_var`): log score (higher better) and Gaussian CRPS (lower better). This matches the saved-moment scoring used in prior significance scripts.")
    lines.append("- Uncertainty: stationary block bootstrap (Politis & Romano 1994), block length n^(1/3), 2000 replications, fixed seeds; 95% percentile CIs; two-sided p-values for H0: mean paired difference = 0.")
    lines.append("- Caveats: sampled stride-4 grid, temporal dependence (effective n < n), non-stationarity and HMM EM convergence caveats from prior sessions remain.")
    lines.append("")
    for model in report["models"]:
        lines.append(f"## {model['model']} ({model['candidate']})")
        lines.append(f"Source: `{model['source_csv']}` (n={model['n_total_validation_forecasts']})")
        lines.append("")
        lines.append("| Period | n | Log score | CRPS | vs Unc log diff | vs EWMA log diff | vs Unc CRPS diff (base-model) | vs EWMA CRPS diff (base-model) |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for p in ["Q1_2024", "Q2_2024"]:
            d = model["periods"][p]
            pm = d["point_means"]
            pdiffs = d["bootstrap_paired_diffs"]
            lines.append(
                "| {p} | {n} | {ls:.6f} | {cr:.6e} | {lu:+.6f} (p={plu:.3f}) | {le:+.6f} (p={ple:.3f}) | {cu:+.3e} (p={pcu:.3f}) | {ce:+.3e} (p={pce:.3f}) |".format(
                    p=p,
                    n=d["n_obs"],
                    ls=pm["model_log_score"],
                    cr=pm["model_crps"],
                    lu=pdiffs["log_model_minus_unc_higher_better"]["mean"],
                    plu=pdiffs["log_model_minus_unc_higher_better"]["p_value_two_sided"],
                    le=pdiffs["log_model_minus_ewma_higher_better"]["mean"],
                    ple=pdiffs["log_model_minus_ewma_higher_better"]["p_value_two_sided"],
                    cu=pdiffs["crps_unc_minus_model_lower_better_for_model"]["mean"],
                    pcu=pdiffs["crps_unc_minus_model_lower_better_for_model"]["p_value_two_sided"],
                    ce=pdiffs["crps_ewma_minus_model_lower_better_for_model"]["mean"],
                    pce=pdiffs["crps_ewma_minus_model_lower_better_for_model"]["p_value_two_sided"],
                )
            )
        dlt = model["q2_minus_q1_point_deltas"]
        lines.append("")
        lines.append("**Q2−Q1 point deltas (stability diagnostic):**")
        lines.append(f"- Model log score: {dlt['model_log_score']:+.6f}; Model CRPS: {dlt['model_crps']:+.6e}")
        lines.append(f"- Edge vs unconditional (log): {dlt['log_edge_vs_unc']:+.6f}; vs EWMA (log): {dlt['log_edge_vs_ewma']:+.6f}")
        lines.append(f"- Edge vs unconditional (CRPS, base-model): {dlt['crps_edge_vs_unc_baseline_minus_model']:+.6e}; vs EWMA: {dlt['crps_edge_vs_ewma_baseline_minus_model']:+.6e}")
        lines.append("")
    lines.append("## Interpretation")
    lines.append("- C1/HMM and C2/HOM both improve on raw point scores from Q1 to Q2 in this sample, but relative edges vs EWMA/unconditional are not uniformly stable across periods; subperiod bootstrap CIs/p-values reflect reduced effective sample size and should be read as robustness diagnostics, not confirmatory holdout evidence.")
    lines.append("- This perturbation does not resolve cross-asset instability observed in ETHUSDT or non-stationarity (Chow p=0.0042); negative controls and further period/asset perturbations remain relevant pre-holdout robustness checks.")
    lines.append("- No holdout evaluation performed.")
    return "\n".join(lines) + "\n"


def main() -> Dict:
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "validation_only",
        "holdout_used": False,
        "split": {
            "Q1_2024": {"start_inclusive": str(Q1_START), "end_exclusive": str(Q1_END)},
            "Q2_2024": {"start_inclusive": str(Q2_START), "end_exclusive": str(Q2_END)},
        },
        "method": {
            "scores": "gaussian_moment_log_score_and_crps",
            "bootstrap": "stationary_block_bootstrap",
            "block_length_rule": "n^(1/3)",
            "n_bootstrap": 2000,
            "ci": "percentile_95",
        },
        "models": [
            analyze_model("H2 filtered HMM (C1 primary)", HMM_CSV, "hmm", seed_base=1000),
            analyze_model("H3 higher-order Markov (C2 comparator)", HOM_CSV, "hom", seed_base=2000),
        ],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2))
    OUT_MD.write_text(render_md(report))
    return report


if __name__ == "__main__":
    r = main()
    print(json.dumps({"wrote": [str(OUT_JSON), str(OUT_MD)], "models": [m["model"] for m in r["models"]]}, indent=2))
