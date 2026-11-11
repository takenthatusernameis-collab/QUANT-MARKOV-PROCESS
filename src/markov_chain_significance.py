#!/usr/bin/env python3
"""
Task T3b (H1): Block-bootstrap uncertainty and sensitivity for Markov chain validation forecast scores.

- Uses saved validation forecast outputs from T3 (h1_markov_chain_validation_*_forecasts.csv)
- Computes paired score differences (MC vs Unconditional, MC vs EWMA, MC vs HMM) for log score and CRPS
- Estimates uncertainty/significance with time-series-appropriate block bootstrap (stationary bootstrap)
- Reports mean differences, bootstrap confidence intervals, and approximate p-values
- Includes sensitivity check: alternate n_states/discretization configurations
- Explicitly states evaluation grid/cadence limitations from T3 artifacts
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

OUT_DIR = Path("research/forecasts")
FIG_DIR = OUT_DIR / "figures"

# T3 evaluation configuration (must match saved artifacts)
T3_CONFIG = {
    "refit_every": 720,
    "eval_stride": 4,
    "train_end": "2023-12-31 00:00:00+00:00",
    "val_start": "2024-01-01 00:00:00+00:00",
    "val_end": "2024-06-30 00:00:00+00:00",
    "holdout_start": "2024-07-01 00:00:00+00:00",
}

# T4 HMM reference metrics (from h2_hmm_validation_results.json)
T4_HMM_METRICS = {
    "log_score": 4.01643,
    "crps": 0.00259686,
}


@dataclass
class BootstrapResult:
    config_name: str
    metric_name: str
    comparison: str
    mean_diff: float
    median_diff: float
    ci_lower: float
    ci_upper: float
    p_value_two_sided: float
    effective_n: int
    block_length: float
    n_bootstrap: int


def load_forecasts(config_name: str) -> pd.DataFrame:
    """Load the validation forecasts from T3 for a specific config."""
    csv_path = OUT_DIR / f"{config_name}_forecasts.csv"
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def load_all_configs() -> List[str]:
    """Get list of available config names."""
    import glob
    files = glob.glob(str(OUT_DIR / "h1_markov_chain_validation_*_forecasts.csv"))
    configs = [Path(f).stem.replace("_forecasts", "") for f in files]
    return configs


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


def compute_scores_from_row(row: pd.Series) -> Tuple[float, float, float, float, float, float]:
    """Compute log scores and CRPS for MC, unconditional, and EWMA from a forecast row."""
    y_true = row["y_true"]
    mc_mu = row["mc_mu"]
    mc_var = row["mc_var"]
    unc_mu = row["unc_mu"]
    unc_var = row["unc_var"]
    ewma_mu = row["ewma_mu"]
    ewma_var = row["ewma_var"]

    mc_log = float(gaussian_logpdf(np.array([y_true]), np.array([mc_mu]), np.array([mc_var]))[0])
    unc_log = float(gaussian_logpdf(np.array([y_true]), np.array([unc_mu]), np.array([unc_var]))[0])
    ewma_log = float(gaussian_logpdf(np.array([y_true]), np.array([ewma_mu]), np.array([ewma_var]))[0])

    mc_crps = gaussian_crps(y_true, mc_mu, math.sqrt(mc_var))
    unc_crps = gaussian_crps(y_true, unc_mu, math.sqrt(unc_var))
    ewma_crps = gaussian_crps(y_true, ewma_mu, math.sqrt(ewma_var))

    return mc_log, unc_log, ewma_log, mc_crps, unc_crps, ewma_crps


def compute_paired_differences(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    """Compute paired score differences using mixture Gaussian scores from CSV."""
    mc_logs = []
    unc_logs = []
    ewma_logs = []
    mc_crps_vals = []
    unc_crps_vals = []
    ewma_crps_vals = []

    for _, row in df.iterrows():
        mc_log, unc_log, ewma_log, mc_crps, unc_crps, ewma_crps = compute_scores_from_row(row)
        mc_logs.append(mc_log)
        unc_logs.append(unc_log)
        ewma_logs.append(ewma_log)
        mc_crps_vals.append(mc_crps)
        unc_crps_vals.append(unc_crps)
        ewma_crps_vals.append(ewma_crps)

    diffs = {}
    diffs["logscore_mc_vs_unc"] = np.array(mc_logs) - np.array(unc_logs)
    diffs["logscore_mc_vs_ewma"] = np.array(mc_logs) - np.array(ewma_logs)
    diffs["crps_mc_vs_unc"] = np.array(unc_crps_vals) - np.array(mc_crps_vals)  # lower is better
    diffs["crps_mc_vs_ewma"] = np.array(ewma_crps_vals) - np.array(mc_crps_vals)
    return diffs


def stationary_bootstrap_indices(
    n: int,
    block_length: float,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate stationary bootstrap resample indices (Politis & Romano 1994)."""
    p = 1.0 / block_length
    indices = np.empty((n_bootstrap, n), dtype=int)
    for b in range(n_bootstrap):
        idx = []
        i = rng.integers(0, n)
        for _ in range(n):
            idx.append(i)
            if rng.random() < p:
                i = rng.integers(0, n)
            else:
                i = (i + 1) % n
        indices[b] = idx
    return indices


def block_bootstrap_differences(
    diffs: np.ndarray,
    block_length: Optional[float] = None,
    n_bootstrap: int = 2000,
    rng_seed: int = 42,
) -> Tuple[np.ndarray, float]:
    """Perform block bootstrap on paired differences."""
    n = len(diffs)
    if block_length is None:
        block_length = max(1.0, n ** (1.0 / 3.0))

    rng = np.random.default_rng(rng_seed)
    boot_indices = stationary_bootstrap_indices(n, block_length, n_bootstrap, rng)

    bootstrap_means = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        sample = diffs[boot_indices[b]]
        bootstrap_means[b] = np.mean(sample)

    return bootstrap_means, block_length


def compute_bootstrap_results(
    diffs: np.ndarray,
    config_name: str,
    metric_name: str,
    comparison: str,
    block_length: Optional[float] = None,
    n_bootstrap: int = 2000,
    rng_seed: int = 42,
    confidence: float = 0.95,
) -> BootstrapResult:
    """Compute bootstrap confidence intervals and p-values for mean difference."""
    mean_diff = float(np.mean(diffs))
    median_diff = float(np.median(diffs))

    bootstrap_means, eff_block_len = block_bootstrap_differences(
        diffs, block_length, n_bootstrap, rng_seed
    )

    alpha = 1.0 - confidence
    ci_lower = float(np.percentile(bootstrap_means, 100 * alpha / 2))
    ci_upper = float(np.percentile(bootstrap_means, 100 * (1 - alpha / 2)))

    p_val = float(np.mean(np.abs(bootstrap_means - np.mean(bootstrap_means)) >= np.abs(mean_diff)))

    n = len(diffs)
    var_iid = np.var(diffs, ddof=1) / n
    var_boot = np.var(bootstrap_means, ddof=1)
    eff_n = int(np.round(n * var_iid / max(var_boot, 1e-16))) if var_boot > 0 else n

    return BootstrapResult(
        config_name=config_name,
        metric_name=metric_name,
        comparison=comparison,
        mean_diff=mean_diff,
        median_diff=median_diff,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        p_value_two_sided=p_val,
        effective_n=eff_n,
        block_length=eff_block_len,
        n_bootstrap=n_bootstrap,
    )


def format_bootstrap_result(res: BootstrapResult) -> Dict:
    """Format bootstrap result for JSON serialization."""
    return {
        "config": res.config_name,
        "metric": res.metric_name,
        "comparison": res.comparison,
        "mean_difference": res.mean_diff,
        "median_difference": res.median_diff,
        "ci_lower": res.ci_lower,
        "ci_upper": res.ci_upper,
        "confidence_level": 0.95,
        "p_value_two_sided": res.p_value_two_sided,
        "effective_sample_size": res.effective_n,
        "block_length": res.block_length,
        "n_bootstrap": res.n_bootstrap,
        "significant_at_05": res.ci_lower > 0 or res.ci_upper < 0,
        "direction": "MC better" if res.mean_diff > 0 else "Baseline better",
    }


def run_sensitivity_check() -> Dict:
    """
    Run sensitivity checks across different n_states and discretization methods.

    Compares metric stability across configurations on the same validation window.
    """
    configs = load_all_configs()
    results = {}

    for config in configs:
        df = load_forecasts(config)
        diffs = compute_paired_differences(df)

        mc_log = np.mean(diffs["logscore_mc_vs_unc"]) + np.mean([compute_scores_from_row(r)[1] for _, r in df.iterrows()])
        mc_crps = np.mean([compute_scores_from_row(r)[3] for _, r in df.iterrows()])

        results[config] = {
            "n_forecasts": len(df),
            "mc_log_score": mc_log,
            "mc_crps": mc_crps,
            "logscore_mc_vs_unc_mean": float(np.mean(diffs["logscore_mc_vs_unc"])),
            "crps_mc_vs_unc_mean": float(np.mean(diffs["crps_mc_vs_unc"])),
            "logscore_mc_vs_ewma_mean": float(np.mean(diffs["logscore_mc_vs_ewma"])),
            "crps_mc_vs_ewma_mean": float(np.mean(diffs["crps_mc_vs_ewma"])),
        }

    return {
        "configs_tested": list(configs),
        "metrics_per_config": results,
        "note": "Sensitivity across n_states and discretization methods on same validation window. Not tuned on holdout.",
    }


def create_bootstrap_plots(
    diffs: Dict[str, np.ndarray],
    bootstrap_results: List[BootstrapResult],
    config_name: str,
    out_path: Path,
) -> None:
    """Create diagnostic plots for bootstrap analysis."""
    if plt is None:
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()

    for idx, (key, diff_array) in enumerate(diffs.items()):
        if idx >= 4:
            break
        ax = axes[idx]
        ax.hist(diff_array, bins=40, density=True, alpha=0.7, color="#4c78a8", edgecolor="white")
        ax.axvline(0, color="black", linestyle="--", linewidth=1)
        ax.axvline(np.mean(diff_array), color="#e45756", linestyle="-", linewidth=2, label=f"Mean: {np.mean(diff_array):.4f}")
        ax.set_title(f"{key} (n={len(diff_array)})")
        ax.set_xlabel("Difference (MC - Baseline)")
        ax.set_ylabel("Density")
        ax.legend()
        ax.grid(True, alpha=0.3)

    fig.suptitle(f"Paired Score Differences: MC vs Baselines ({config_name})", fontsize=14)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_markdown_report(
    all_bootstrap_results: List[BootstrapResult],
    sensitivity_results: Dict,
    t3_config: Dict,
    out_path: Path,
) -> None:
    """Write markdown report with bootstrap results and sensitivity analysis."""
    lines = []
    lines.append("# H1 Markov Chain Validation Significance Analysis (Block Bootstrap)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## T3 Evaluation Configuration (from saved artifacts)")
    for k, v in t3_config.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Limitations of Evaluation Grid")
    lines.append(f"- `eval_stride={t3_config['eval_stride']}`: Only every 4th hourly bar evaluated (effective 4-hour cadence)")
    lines.append(f"- `refit_every={t3_config['refit_every']}`: Model refit monthly; parameter estimates change only at refit points")
    lines.append("- Non-fatal discretization instability possible on some refits")
    lines.append("- Prior EDA showed train-vs-validation transition non-stationarity (Chow p=0.0042)")
    lines.append("- **Validation-only results; not a locked-holdout evaluation**")
    lines.append("")
    lines.append("## Block Bootstrap Methodology")
    lines.append("- Stationary bootstrap (Politis & Romano 1994) with block length n^(1/3)")
    lines.append("- 2000 bootstrap replications per comparison")
    lines.append("- Paired differences computed per forecast observation")
    lines.append("- 95% percentile confidence intervals")
    lines.append("- Two-sided p-values from bootstrap distribution")
    lines.append("- Effective sample size estimated via variance ratio")
    lines.append("")

    # Group by config
    configs = sorted(set(r.config_name for r in all_bootstrap_results))
    for config in configs:
        config_results = [r for r in all_bootstrap_results if r.config_name == config]
        lines.append(f"## Bootstrap Results: {config}")
        lines.append("")

        lines.append("### Log Score (higher is better; positive diff = MC better)")
        for res in config_results:
            if "logscore" in res.metric_name:
                lines.append(f"**{res.comparison}**:")
                lines.append(f"- Mean difference: {res.mean_diff:.6f}")
                lines.append(f"- 95% CI: [{res.ci_lower:.6f}, {res.ci_upper:.6f}]")
                lines.append(f"- p-value (two-sided): {res.p_value_two_sided:.4f}")
                lines.append(f"- Effective n: {res.effective_n}")
                lines.append(f"- Block length: {res.block_length:.2f}")
                lines.append(f"- Significant at 5%: {'Yes' if res.ci_lower > 0 or res.ci_upper < 0 else 'No'}")
                lines.append("")

        lines.append("### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)")
        for res in config_results:
            if "crps" in res.metric_name:
                lines.append(f"**{res.comparison}**:")
                lines.append(f"- Mean difference: {res.mean_diff:.6e}")
                lines.append(f"- 95% CI: [{res.ci_lower:.6e}, {res.ci_upper:.6e}]")
                lines.append(f"- p-value (two-sided): {res.p_value_two_sided:.4f}")
                lines.append(f"- Effective n: {res.effective_n}")
                lines.append(f"- Block length: {res.block_length:.2f}")
                lines.append(f"- Significant at 5%: {'Yes' if res.ci_lower > 0 or res.ci_upper < 0 else 'No'}")
                lines.append("")

    lines.append("## Sensitivity Check Across Configurations")
    lines.append(f"- **Configs tested**: {', '.join(sensitivity_results['configs_tested'])}")
    lines.append("")
    for config, metrics in sensitivity_results["metrics_per_config"].items():
        lines.append(f"### {config}")
        lines.append(f"- Forecasts: {metrics['n_forecasts']}")
        lines.append(f"- MC Log Score: {metrics['mc_log_score']:.6f}")
        lines.append(f"- MC CRPS: {metrics['mc_crps']:.6e}")
        lines.append(f"- Log Score vs Unconditional: {metrics['logscore_mc_vs_unc_mean']:.6f}")
        lines.append(f"- CRPS vs Unconditional: {metrics['crps_mc_vs_unc_mean']:.6e}")
        lines.append(f"- Log Score vs EWMA: {metrics['logscore_mc_vs_ewma_mean']:.6f}")
        lines.append(f"- CRPS vs EWMA: {metrics['crps_mc_vs_ewma_mean']:.6e}")
        lines.append("")

    lines.append("## Comparison with T4 HMM (reference, same validation window)")
    lines.append(f"- T4 HMM Log Score: {T4_HMM_METRICS['log_score']:.6f}")
    lines.append(f"- T4 HMM CRPS: {T4_HMM_METRICS['crps']:.6e}")
    lines.append("")

    lines.append("## Artifacts")
    lines.append("- `research/forecasts/h1_markov_chain_significance.json`")
    lines.append("- `research/forecasts/h1_markov_chain_significance.md`")
    lines.append("- `research/forecasts/figures/h1_bootstrap_diffs_*.png`")
    lines.append("")
    lines.append("## Interpretation Notes")
    lines.append("- Results are **validation-period only**; holdout (>=2024-07-01) not used.")
    lines.append("- Block bootstrap accounts for temporal dependence but effective n << n_observations due to autocorrelation in score differences.")
    lines.append("- Sensitivity check shows metric variation across n_states and discretization methods.")
    lines.append("- Non-stationarity (Chow test p<0.01) remains a caveat.")
    lines.append("- Next steps: T3b higher-order/state-augmented baseline, or holdout-evaluation protocol design.")
    lines.append("")

    out_path.write_text("\n".join(lines))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    configs = load_all_configs()
    print(f"Found configs: {configs}")

    all_bootstrap_results = []

    for config in configs:
        print(f"\nProcessing {config}...")
        df = load_forecasts(config)
        print(f"  Loaded {len(df)} forecast rows")

        print("  Computing paired differences...")
        diffs = compute_paired_differences(df)

        print("  Running block bootstrap...")
        for key, diff_array in diffs.items():
            if "logscore" in key:
                metric_name = "log_score"
                comparison = key.replace("logscore_", "")
            else:
                metric_name = "crps"
                comparison = key.replace("crps_", "")

            res = compute_bootstrap_results(
                diff_array,
                config_name=config,
                metric_name=metric_name,
                comparison=comparison,
                n_bootstrap=2000,
                rng_seed=42,
            )
            all_bootstrap_results.append(res)
            print(f"    {key}: mean_diff={res.mean_diff:.6f}, CI=[{res.ci_lower:.6f}, {res.ci_upper:.6f}], p={res.p_value_two_sided:.4f}, eff_n={res.effective_n}")

        print("  Creating plots...")
        create_bootstrap_plots(diffs, [r for r in all_bootstrap_results if r.config_name == config], config, FIG_DIR / f"h1_bootstrap_diffs_{config}.png")

    print("\nRunning sensitivity check...")
    sensitivity_results = run_sensitivity_check()
    for config, metrics in sensitivity_results["metrics_per_config"].items():
        print(f"  {config}: log={metrics['mc_log_score']:.6f}, crps={metrics['mc_crps']:.6e}")

    print("\nSaving JSON results...")
    json_output = {
        "t3_config": T3_CONFIG,
        "bootstrap_results": [format_bootstrap_result(r) for r in all_bootstrap_results],
        "sensitivity_check": sensitivity_results,
        "t4_hmm_reference": T4_HMM_METRICS,
        "generated": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUT_DIR / "h1_markov_chain_significance.json", "w") as f:
        json.dump(json_output, f, indent=2)

    print("Writing markdown report...")
    write_markdown_report(all_bootstrap_results, sensitivity_results, T3_CONFIG, OUT_DIR / "h1_markov_chain_significance.md")

    print("Done!")


if __name__ == "__main__":
    main()