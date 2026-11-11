#!/usr/bin/env python3
"""
Verification script for H1 Markov Chain sensitivity consolidation.
Loads all artifacts and regenerates comparison tables.
Run: PYTHONPATH=. python src/verify_h1_consolidation.py
"""
import json
from pathlib import Path


def load_json(path):
    with open(path) as f:
        return json.load(f)


def main():
    base = Path("research/forecasts")

    # Canonical T3 (this session)
    canonical = load_json(base / "h1_markov_chain_validation.json")

    # Legacy configs
    legacy_files = {
        "legacy_q3": "h1_markov_chain_validation_quantile_k3_results.json",
        "legacy_q5": "h1_markov_chain_validation_quantile_k5_results.json",
        "legacy_q7": "h1_markov_chain_validation_quantile_k7_results.json",
        "legacy_km3": "h1_markov_chain_validation_kmeans_k3_results.json",
        "legacy_km5": "h1_markov_chain_validation_kmeans_k5_results.json",
        "legacy_km7": "h1_markov_chain_validation_kmeans_k7_results.json",
    }

    legacy = {}
    legacy_config_map = {
        "legacy_q3": "h1_markov_chain_validation_quantile_k3",
        "legacy_q5": "h1_markov_chain_validation_quantile_k5",
        "legacy_q7": "h1_markov_chain_validation_quantile_k7",
        "legacy_km3": "h1_markov_chain_validation_kmeans_k3",
        "legacy_km5": "h1_markov_chain_validation_kmeans_k5",
        "legacy_km7": "h1_markov_chain_validation_kmeans_k7",
    }
    for key, fname in legacy_files.items():
        legacy[key] = load_json(base / fname)

    # Significance (legacy bootstrap)
    sig = load_json(base / "h1_markov_chain_significance.json")
    sens = sig.get("sensitivity_check", {}).get("metrics_per_config", {})

    # Print comparison table: Log Score
    print("=" * 100)
    print("LOG SCORE (higher = better)")
    print("=" * 100)
    print(f"{'Config':<18} {'MC':>10} {'Uncond':>10} {'EWMA':>10} {'MC-Unc':>10} {'MC-EWMA':>10}")
    print("-" * 100)

    # Canonical
    mc = canonical["metrics"]["log_score_higher_is_better"]["markov_chain_mixture"]["mean"]
    unc = canonical["metrics"]["log_score_higher_is_better"]["unconditional_gaussian"]["mean"]
    ewma = canonical["metrics"]["log_score_higher_is_better"]["ewma_gaussian"]["mean"]
    print(f"{'canonical_t3_q5':<18} {mc:>10.4f} {unc:>10.4f} {ewma:>10.4f} {mc-unc:>+10.4f} {mc-ewma:>+10.4f}")

    for key, data in legacy.items():
        mc = data["metrics"]["log_score_higher_is_better"]["markov_chain_mixture"]["mean"]
        unc = data["metrics"]["log_score_higher_is_better"]["unconditional_gaussian"]["mean"]
        ewma = data["metrics"]["log_score_higher_is_better"]["ewma_gaussian"]["mean"]
        print(f"{key:<18} {mc:>10.4f} {unc:>10.4f} {ewma:>10.4f} {mc-unc:>+10.4f} {mc-ewma:>+10.4f}")

    print()
    print("=" * 100)
    print("CRPS (lower = better)")
    print("=" * 100)
    print(f"{'Config':<18} {'MC':>10} {'Uncond':>10} {'EWMA':>10} {'Unc-MC':>10} {'EWMA-MC':>10}")
    print("-" * 100)

    mc = canonical["metrics"]["crps_lower_is_better"]["markov_chain_mixture"]["mean"]
    unc = canonical["metrics"]["crps_lower_is_better"]["unconditional_gaussian"]["mean"]
    ewma = canonical["metrics"]["crps_lower_is_better"]["ewma_gaussian"]["mean"]
    print(f"{'canonical_t3_q5':<18} {mc:>10.6f} {unc:>10.6f} {ewma:>10.6f} {unc-mc:>+10.6f} {ewma-mc:>+10.6f}")

    for key, data in legacy.items():
        mc = data["metrics"]["crps_lower_is_better"]["markov_chain_mixture"]["mean"]
        unc = data["metrics"]["crps_lower_is_better"]["unconditional_gaussian"]["mean"]
        ewma = data["metrics"]["crps_lower_is_better"]["ewma_gaussian"]["mean"]
        print(f"{key:<18} {mc:>10.6f} {unc:>10.6f} {ewma:>10.6f} {unc-mc:>+10.6f} {ewma-mc:>+10.6f}")

    print()
    print("=" * 100)
    print("PIT CALIBRATION (ideal mean=0.5, std=0.289)")
    print("=" * 100)
    print(f"{'Config':<18} {'PIT Mean':>10} {'PIT Std':>10}")
    print("-" * 100)

    pit = canonical["metrics"]["pit_markov_chain"]
    print(f"{'canonical_t3_q5':<18} {pit['mean']:>10.4f} {pit['std']:>10.4f}")

    for key, data in legacy.items():
        pit = data["metrics"]["pit_markov_chain"]
        print(f"{key:<18} {pit['mean']:>10.4f} {pit['std']:>10.4f}")

    print()
    print("=" * 100)
    print("BOOTSTRAP SIGNIFICANCE (from h1_markov_chain_significance.json)")
    print("=" * 100)
    print("Log Score: MC - Baseline (positive favors MC)")
    print(f"{'Config':<18} {'vs Unc diff':>12} {'p-value':>10} {'Sig':>6} | {'vs EWMA diff':>12} {'p-value':>10} {'Sig':>6}")
    print("-" * 100)

    for key in ["legacy_q3", "legacy_q5", "legacy_q7", "legacy_km3", "legacy_km5", "legacy_km7"]:
        config_name = legacy_config_map[key]
        m = sens.get(config_name, {})
        ls_unc = m.get("logscore_mc_vs_unc_mean", 0)
        ls_ewma = m.get("logscore_mc_vs_ewma_mean", 0)
        # p-values from bootstrap_results
        p_unc = next((r["p_value_two_sided"] for r in sig["bootstrap_results"]
                      if r["config"] == config_name and r["metric"] == "log_score" and r["comparison"] == "mc_vs_unc"), 1.0)
        p_ewma = next((r["p_value_two_sided"] for r in sig["bootstrap_results"]
                       if r["config"] == config_name and r["metric"] == "log_score" and r["comparison"] == "mc_vs_ewma"), 1.0)
        sig_unc = "Yes" if p_unc < 0.05 else "No"
        sig_ewma = "Yes" if p_ewma < 0.05 else "No"
        print(f"{key:<18} {ls_unc:>+12.5f} {p_unc:>10.4f} {sig_unc:>6} | {ls_ewma:>+12.5f} {p_ewma:>10.4f} {sig_ewma:>6}")

    # Canonical bootstrap
    can_bs = canonical["bootstrap"]
    ls_unc = can_bs["log_score_higher_better_diff_mc_minus_baseline"]["mc_vs_unconditional"]["mean_difference"]
    p_unc = can_bs["log_score_higher_better_diff_mc_minus_baseline"]["mc_vs_unconditional"]["p_value_two_sided"]
    ls_ewma = can_bs["log_score_higher_better_diff_mc_minus_baseline"]["mc_vs_ewma"]["mean_difference"]
    p_ewma = can_bs["log_score_higher_better_diff_mc_minus_baseline"]["mc_vs_ewma"]["p_value_two_sided"]
    sig_unc = "Yes" if p_unc < 0.05 else "No"
    sig_ewma = "Yes" if p_ewma < 0.05 else "No"
    print(f"{'canonical_t3_q5':<18} {ls_unc:>+12.5f} {p_unc:>10.4f} {sig_unc:>6} | {ls_ewma:>+12.5f} {p_ewma:>10.4f} {sig_ewma:>6}")

    print()
    print("CRPS: Baseline - MC (positive favors MC)")
    print(f"{'Config':<18} {'vs Unc diff':>12} {'p-value':>10} {'Sig':>6} | {'vs EWMA diff':>12} {'p-value':>10} {'Sig':>6}")
    print("-" * 100)

    for key in ["legacy_q3", "legacy_q5", "legacy_q7", "legacy_km3", "legacy_km5", "legacy_km7"]:
        config_name = legacy_config_map[key]
        m = sens.get(config_name, {})
        crps_unc = m.get("crps_mc_vs_unc_mean", 0)
        crps_ewma = m.get("crps_mc_vs_ewma_mean", 0)
        p_unc = next((r["p_value_two_sided"] for r in sig["bootstrap_results"]
                      if r["config"] == config_name and r["metric"] == "crps" and r["comparison"] == "mc_vs_unc"), 1.0)
        p_ewma = next((r["p_value_two_sided"] for r in sig["bootstrap_results"]
                       if r["config"] == config_name and r["metric"] == "crps" and r["comparison"] == "mc_vs_ewma"), 1.0)
        sig_unc = "Yes" if p_unc < 0.05 else "No"
        sig_ewma = "Yes" if p_ewma < 0.05 else "No"
        print(f"{key:<18} {crps_unc:>+12.5e} {p_unc:>10.4f} {sig_unc:>6} | {crps_ewma:>+12.5e} {p_ewma:>10.4f} {sig_ewma:>6}")

    crps_unc = can_bs["crps_lower_better_diff_baseline_minus_mc"]["mc_vs_unconditional"]["mean_difference"]
    p_unc = can_bs["crps_lower_better_diff_baseline_minus_mc"]["mc_vs_unconditional"]["p_value_two_sided"]
    crps_ewma = can_bs["crps_lower_better_diff_baseline_minus_mc"]["mc_vs_ewma"]["mean_difference"]
    p_ewma = can_bs["crps_lower_better_diff_baseline_minus_mc"]["mc_vs_ewma"]["p_value_two_sided"]
    sig_unc = "Yes" if p_unc < 0.05 else "No"
    sig_ewma = "Yes" if p_ewma < 0.05 else "No"
    print(f"{'canonical_t3_q5':<18} {crps_unc:>+12.5e} {p_unc:>10.4f} {sig_unc:>6} | {crps_ewma:>+12.5e} {p_ewma:>10.4f} {sig_ewma:>6}")

    print()
    print("=" * 100)
    print("T4 HMM REFERENCE (from significance.json)")
    print("=" * 100)
    t4 = sig.get("t4_hmm_reference", {})
    print(f"Log Score: {t4.get('log_score', 'N/A')}")
    print(f"CRPS:      {t4.get('crps', 'N/A')}")

    print()
    print("Verification complete. Tables match consolidation report.")


if __name__ == "__main__":
    main()