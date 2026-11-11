#!/usr/bin/env python3
"""
Task T5d robustness (validation-only, asset perturbation): ETHUSDT 1h walk-forward
filtered HMM forecast validation (validation only).

- ETHUSDT 1h returns from data/processed/features.parquet (symbol column)
- 3-state Gaussian HMM, states ordered by mean return (mu1 < mu2 < mu3)
- Expanding walk-forward: refit on data up to t, forecast t+1
- Filtered (forward) state probabilities only; no smoothed probabilities
- Validation window evaluated: 2024-01-01 to 2024-06-30 only
- Holdout (>=2024-07-01) excluded by construction; no holdout tuning

This is an asset-perturbation robustness check of the C1 filtered-HMM candidate
on a second liquid symbol (ETHUSDT) over the same validation grid as BTCUSDT.
Results are compared qualitatively to the BTCUSDT validation metrics; no
holdout is executed and no configs are tuned on any outcome.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    plt = None

from src.hmm_walkforward import (
    DATA_PATH,
    OUT_DIR,
    FIG_DIR,
    VAL_START,
    VAL_END,
    HOLDOUT_START,
    DEFAULT_SEEDS,
    load_returns,
    run_walkforward,
    row_to_dict,
    write_markdown_report,
)

SYMBOL = "ETHUSDT"
REFIT_EVERY = 720
SEEDS = (0, 1, 2)
EVAL_STRIDE = 4

RESULTS_JSON = OUT_DIR / "h2_hmm_validation_ethusdt_results.json"
FORECAST_CSV = OUT_DIR / "h2_hmm_validation_ethusdt.csv"
REPORT_MD = OUT_DIR / "h2_hmm_validation_ethusdt.md"
PROB_FIG = FIG_DIR / "h2_next_state_probs_ethusdt.png"
PIT_FIG = FIG_DIR / "h2_pit_hist_ethusdt.png"


def save_forecast_csv(results, path: Path) -> None:
    rows = []
    for r in results:
        rows.append({
            "timestamp": r.timestamp,
            "symbol": SYMBOL,
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
    pd.DataFrame(rows).to_csv(path, index=False)


def write_ethusdt_report(payload, path: Path) -> None:
    m = payload["metrics"]
    c = payload["config"]
    counts = payload["counts"]
    ls = m["log_score_higher_is_better"]
    cr = m["crps_lower_is_better"]
    pit = m.get("pit_hmm", {})
    lines = []
    lines.append("# H2 Walk-forward Filtered HMM Forecast Validation (ETHUSDT 1h — asset perturbation robustness)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Symbol/Freq:** {c['symbol']} / {c['frequency']}")
    lines.append(f"**Validation window:** {c['val_start']} to {c['val_end']} (holdout >= {c['holdout_start']} excluded)")
    lines.append(f"**Model:** {c['n_states']}-state Gaussian HMM (diag), states ordered by mean; refit every {c['refit_every']} bars on expanding history; eval_stride={c.get('eval_stride',1)}; seeds={c['seeds']}")
    lines.append("")
    lines.append("## Purpose")
    lines.append("- Asset-perturbation robustness check of the C1 filtered-HMM candidate on ETHUSDT 1h over the same validation grid as BTCUSDT.")
    lines.append("- Validation-only; not a trading backtest and not a final holdout evaluation. No holdout used; no config tuning on any outcome.")
    lines.append("")
    lines.append("## Scope and leakage controls")
    lines.append("- Expanding fit uses ETHUSDT returns up to time *t* only; forecast targets *t+1* in validation window.")
    lines.append("- Filtered probabilities computed via forward algorithm on history up to *t*; no smoothed/Viterbi full-sample decoding used for forecasts.")
    lines.append("- Locked holdout period (>= 2024-07-01) not used for fitting, selection, or evaluation.")
    lines.append("")
    lines.append("## Baselines")
    lines.append("- **Unconditional Gaussian:** expanding mean/variance of historical ETHUSDT returns up to *t*.")
    lines.append("- **EWMA Gaussian (RiskMetrics-style):** expanding mean with EWMA variance (lambda=0.94) on demeaned returns up to *t*.")
    lines.append("")
    lines.append("## Forecast metrics (validation)")
    lines.append(f"Observations: {counts['validation_forecasts']} | Refits: {counts['refits']}")
    lines.append("")
    lines.append("### Log score (mean, higher is better)")
    for k in ["hmm_mixture", "unconditional_gaussian", "ewma_gaussian"]:
        lines.append(f"- {k}: {ls[k]['mean']:.6f} (median {ls[k]['median']:.6f})")
    lines.append("")
    lines.append("### CRPS (mean, lower is better)")
    for k in ["hmm_mixture", "unconditional_gaussian", "ewma_gaussian"]:
        lines.append(f"- {k}: {cr[k]['mean']:.6e} (median {cr[k]['median']:.6e})")
    lines.append("")
    lines.append("### Calibration diagnostic")
    lines.append(f"- HMM mixture PIT mean={pit.get('mean')} std={pit.get('std')} (ideal uniform: mean 0.5, std ~0.289)")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("- `research/forecasts/h2_hmm_validation_ethusdt_results.json`")
    lines.append("- `research/forecasts/h2_hmm_validation_ethusdt.csv`")
    lines.append("- `research/forecasts/figures/h2_next_state_probs_ethusdt.png`")
    lines.append("- `research/forecasts/figures/h2_pit_hist_ethusdt.png`")
    lines.append("")
    lines.append("## Interpretation notes")
    lines.append("- Compare against BTCUSDT validation (research/forecasts/h2_hmm_validation_results.json): HMM log score 4.01643, CRPS 0.00259686; EWMA log score 3.90220, CRPS 0.00263060.")
    lines.append("- A material drop in ETHUSDT log score/CRPS relative to BTCUSDT would indicate the HMM edge is symbol-specific, not robust across assets.")
    path.write_text("\n".join(lines) + "\n")


def save_figures(results) -> None:
    if plt is None or not results:
        return
    ts = [r.timestamp for r in results]
    p = np.array([r.hmm_state_probs_next for r in results])
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(ts, p[:, 0], label="P(S0)", linewidth=0.8)
    ax.plot(ts, p[:, 1], label="P(S1)", linewidth=0.8)
    ax.plot(ts, p[:, 2], label="P(S2)", linewidth=0.8)
    ax.set_title("HMM 1-step-ahead filtered state probabilities (ETHUSDT validation)")
    ax.set_ylabel("Probability")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(PROB_FIG, dpi=150)
    plt.close(fig)

    pit = []
    for r in results:
        cdf = 0.0
        for pr, mm, v in zip(r.hmm_state_probs_next, r.hmm_mix_means, r.hmm_mix_vars):
            s = math.sqrt(max(v, 1e-12))
            z = (r.y_true - mm) / s
            cdf += float(pr) * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        pit.append(float(np.clip(cdf, 0.0, 1.0)))
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(pit, bins=10, range=(0, 1), density=True, alpha=0.8, color="#4c78a8")
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1)
    ax.set_title("HMM mixture PIT (ETHUSDT validation)")
    ax.set_xlabel("PIT")
    ax.set_ylabel("Density")
    fig.tight_layout()
    fig.savefig(PIT_FIG, dpi=150)
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load_returns(SYMBOL, DATA_PATH)
    out = run_walkforward(df, refit_every=REFIT_EVERY, seeds=SEEDS, eval_stride=EVAL_STRIDE, symbol=SYMBOL)
    payload = out["payload"]
    results = out["results"]

    with open(RESULTS_JSON, "w") as f:
        json.dump(payload, f, indent=2)
    save_forecast_csv(results, FORECAST_CSV)
    write_ethusdt_report(payload, REPORT_MD)
    save_figures(results)

    ls = payload["metrics"]["log_score_higher_is_better"]
    cr = payload["metrics"]["crps_lower_is_better"]
    print(json.dumps({
        "symbol": SYMBOL,
        "validation_forecasts": payload["counts"]["validation_forecasts"],
        "refits": payload["counts"]["refits"],
        "log_score_hmm": ls["hmm_mixture"]["mean"],
        "log_score_unc": ls["unconditional_gaussian"]["mean"],
        "log_score_ewma": ls["ewma_gaussian"]["mean"],
        "crps_hmm": cr["hmm_mixture"]["mean"],
        "crps_unc": cr["unconditional_gaussian"]["mean"],
        "crps_ewma": cr["ewma_gaussian"]["mean"],
        "pit_mean": payload["metrics"]["pit_hmm"]["mean"],
        "pit_std": payload["metrics"]["pit_hmm"]["std"],
    }, indent=2))


if __name__ == "__main__":
    main()
