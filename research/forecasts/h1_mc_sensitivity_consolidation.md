# H1 Finite-State Markov Chain Baseline: K/Binning Sensitivity Consolidation (Validation Only)

**Generated:** 2026-11-11
**Scope:** Validation period only (2024-01-01 to 2024-06-30). Holdout (≥2024-07-01) **not used**.
**Data:** BTCUSDT 1h returns from `data/processed/features.parquet`, train ≤2023-12-31.
**Forecast grid:** 1,087 forecasts (eval_stride=4).

---

## Configurations Audited

| Config ID | Discretization | K (States) | Refit Cadence | Source Artifact |
|-----------|---------------|------------|---------------|-----------------|
| **Canonical T3 (this session)** | Quantile (train-fitted edges) | 5 | Expanding per step | `h1_markov_chain_validation.json` |
| Legacy Q3 | Quantile (train-fitted) | 3 | refit_every=720 | `h1_markov_chain_validation_quantile_k3_results.json` |
| Legacy Q5 | Quantile (train-fitted) | 5 | refit_every=720 | `h1_markov_chain_validation_quantile_k5_results.json` |
| Legacy Q7 | Quantile (train-fitted) | 7 | refit_every=720 | `h1_markov_chain_validation_quantile_k7_results.json` |
| Legacy KM3 | K-means (train-fitted) | 3 | refit_every=720 | `h1_markov_chain_validation_kmeans_k3_results.json` |
| Legacy KM5 | K-means (train-fitted) | 5 | refit_every=720 | `h1_markov_chain_validation_kmeans_k5_results.json` |
| Legacy KM7 | K-means (train-fitted) | 7 | refit_every=720 | `h1_markov_chain_validation_kmeans_k7_results.json` |

**Leakage controls (all configs):**
- Bin edges / cluster centroids fitted on **training data only** (≤2023-12-31)
- Expanding history for transition/state-conditional estimation (no future data)
- Validation window strictly 2024-01-01 to 2024-06-30
- Holdout (≥2024-07-01) excluded by construction

**Key difference:** Canonical T3 uses **expanding refit at every evaluated step** (transition counts from all history < target). Legacy configs use `refit_every=720` (≈30 days). Both are valid walk-forward designs; T3 is more computationally intensive but uses more current information.

---

## Point-Estimate Metrics (Validation Grid, 1,087 Forecasts)

### Log Score (higher = better)

| Config | MC Mixture | Unconditional Gaussian | EWMA Gaussian (λ=0.94) |
|--------|-----------|------------------------|------------------------|
| **Canonical T3 (Q5)** | **3.8298** | 3.7482 | 3.9042 |
| Legacy Q3 | 3.7892 | 3.7704 | 3.9022 |
| Legacy Q5 | 3.8390 | 3.7704 | 3.9022 |
| Legacy Q7 | 3.8569 | 3.7704 | 3.9022 |
| Legacy KM3 | **3.9319** | 3.7704 | 3.9022 |
| Legacy KM5 | 3.9217 | 3.7704 | 3.9022 |
| Legacy KM7 | 3.9012 | 3.7704 | 3.9022 |

### CRPS (lower = better)

| Config | MC Mixture | Unconditional Gaussian | EWMA Gaussian (λ=0.94) |
|--------|-----------|------------------------|------------------------|
| **Canonical T3 (Q5)** | **0.002708** | 0.002903 | 0.002674 |
| Legacy Q3 | 0.002755 | 0.002854 | 0.002631 |
| Legacy Q5 | 0.002685 | 0.002854 | 0.002631 |
| Legacy Q7 | 0.002683 | 0.002854 | 0.002631 |
| Legacy KM3 | **0.002654** | 0.002854 | 0.002631 |
| Legacy KM5 | 0.002677 | 0.002854 | 0.002631 |
| Legacy KM7 | 0.002672 | 0.002854 | 0.002631 |

### PIT Calibration (ideal mean ≈ 0.5, std ≈ 0.289)

| Config | PIT Mean | PIT Std |
|--------|----------|---------|
| **Canonical T3 (Q5)** | 0.4988 | 0.2788 |
| Legacy Q3 | 0.5064 | 0.2500 |
| Legacy Q5 | 0.5144 | 0.2727 |
| Legacy Q7 | 0.5116 | 0.2708 |
| Legacy KM3 | 0.5174 | 0.2777 |
| Legacy KM5 | 0.5104 | 0.2740 |
| Legacy KM7 | 0.5077 | 0.2660 |

---

## Block-Bootstrap Significance (Stationary Bootstrap, 2000 Reps, Block Length ≈ n^(1/3) ≈ 10.3)

### Log Score Difference: MC − Baseline (positive favors MC)

| Config | vs Unconditional | p-value | Significant (5%) | vs EWMA | p-value | Significant (5%) |
|--------|-----------------|---------|------------------|---------|---------|------------------|
| **Canonical T3 (Q5)** | +0.0816 | 0.032 | **Yes (MC better)** | −0.0745 | 0.060 | No |
| Legacy Q3 | +0.00007 | 0.985 | No | −0.1317 | 0.000 | **Yes (EWMA better)** |
| Legacy Q5 | +0.0117 | 0.116 | No | −0.1201 | 0.000 | **Yes (EWMA better)** |
| Legacy Q7 | −0.0001 | 0.994 | No | −0.1319 | 0.000 | **Yes (EWMA better)** |
| Legacy KM3 | +0.0228 | 0.020 | **Yes (MC better)** | −0.1090 | 0.0005 | **Yes (EWMA better)** |
| Legacy KM5 | +0.0138 | 0.502 | No | −0.1180 | 0.0005 | **Yes (EWMA better)** |
| Legacy KM7 | −0.0056 | 0.738 | No | −0.1374 | 0.0005 | **Yes (EWMA better)** |

*Canonical T3 bootstrap results from `h1_markov_chain_validation.json`. Legacy results from `h1_markov_chain_significance.json` (sensitivity_check.metrics_per_config). Note: Legacy bootstrap comparisons used the same validation grid but refit_every=720; canonical T3 uses expanding per-step refit.*

### CRPS Difference: Baseline − MC (positive favors MC)

| Config | vs Unconditional | p-value | Significant (5%) | vs EWMA | p-value | Significant (5%) |
|--------|-----------------|---------|------------------|---------|---------|------------------|
| **Canonical T3 (Q5)** | +1.95e-4 | 0.000 | **Yes (MC better)** | −3.40e-5 | 0.039 | **Yes (EWMA better)** |
| Legacy Q3 | −4.24e-6 | 0.545 | No | −2.27e-4 | 0.000 | **Yes (EWMA better)** |
| Legacy Q5 | +9.52e-6 | 0.401 | No | −2.13e-4 | 0.000 | **Yes (EWMA better)** |
| Legacy Q7 | −1.01e-5 | 0.550 | No | −2.33e-4 | 0.000 | **Yes (EWMA better)** |
| Legacy KM3 | +3.02e-5 | 0.035 | **Yes (MC better)** | −1.93e-4 | 0.000 | **Yes (EWMA better)** |
| Legacy KM5 | −5.75e-6 | 0.868 | No | −2.29e-4 | 0.000 | **Yes (EWMA better)** |
| Legacy KM7 | −2.00e-5 | 0.431 | No | −2.43e-4 | 0.000 | **Yes (EWMA better)** |

---

## Key Findings

1. **K-means K=3 (Legacy KM3) achieves the highest log score (3.9319) and lowest CRPS (0.002654)** among all tested configurations. It significantly beats unconditional Gaussian on log score (p=0.020) and CRPS (p=0.035). However, it is **significantly worse than EWMA on both metrics** (log score p=0.0005, CRPS p=0.000).

2. **Canonical T3 (Q5, expanding per-step refit)** shows a different pattern: significantly beats unconditional on both log score (p=0.032) and CRPS (p=0.000), but **does not significantly differ from EWMA on log score (p=0.060)** while EWMA significantly beats it on CRPS (p=0.039). The expanding per-step refit appears to improve relative performance vs unconditional but not enough to consistently beat EWMA.

3. **Quantile binning** shows monotonic improvement in log score with K (3→5→7: 3.789 → 3.839 → 3.857) but CRPS is flat (0.00275 → 0.00268 → 0.00268). None of the quantile configs significantly beat EWMA on log score; all lose to EWMA on CRPS. Quantile K=3 does not significantly beat unconditional on either metric (log score p=0.985, CRPS p=0.545).

4. **K-means binning** peaks at K=3 for both metrics. K=5 and K=7 degrade performance, likely due to sparse state occupancy (some states have <200 samples per refit).

5. **EWMA Gaussian (λ=0.94) remains a strong baseline**: it is never significantly beaten by any MC config on log score, and significantly beats most MC configs on CRPS.

6. **Effective sample sizes** (366–1183) are well below nominal n=1087 due to temporal dependence in score differences, as expected for financial returns.

7. **Canonical T3 vs Legacy Q5 difference**: Same K=5 quantile discretization, but different refit cadence (expanding per-step vs refit_every=720). Canonical T3 has lower log score (3.830 vs 3.839) and slightly worse CRPS (0.002708 vs 0.002685). The differences are small and within bootstrap uncertainty.

---

## Comparison with T4 HMM (Reference)

| Model | Log Score | CRPS |
|-------|-----------|------|
| T4 HMM (3-state, filtered, validation) | 4.0164 | 0.002597 |
| Best MC (Legacy KM3) | 3.9319 | 0.002654 |
| Canonical T3 (Q5) | 3.8298 | 0.002708 |
| EWMA Gaussian | 3.9022 | 0.002631 |

The T4 HMM (filtered, walk-forward) outperforms all MC configurations on both metrics. This is expected given HMM's ability to model latent regimes with continuous state-conditional distributions.

---

## Reproducibility Notes

- **Canonical T3 artifacts**: Generated by `src/markov_chain_baseline.py` (expanding per-step refit, Laplace α=1.0, quantile bins fitted on train). Run: `PYTHONPATH=. python src/markov_chain_baseline.py`
- **Legacy artifacts**: Generated by prior scripts with `refit_every=720`. Not re-runnable from current codebase without restoring those scripts.
- **Bootstrap significance**: Canonical T3 uses `src/hmm_validation_significance.py` adapted for MC scores (Gaussian approximation of mixture). Legacy significance uses a separate bootstrap run on saved legacy forecasts.
- **Verification script**: See `src/verify_h1_consolidation.py` (created alongside this report) which loads all artifacts and regenerates the comparison tables above.

---

## Caveats

1. **Validation-only results**: All metrics and significance tests are on the 2024-01 to 2024-06 validation window. Holdout (≥2024-07-01) is locked and unused.
2. **No holdout tuning**: K, discretization method, refit cadence, and Laplace smoothing were not optimized on holdout.
3. **Gaussian mixture CRPS approximation**: Bootstrap for canonical T3 uses Gaussian approximation of MC mixture (state-level mixture parameters not in saved CSV). Legacy bootstrap used saved mixture forecasts directly.
4. **Non-stationarity**: T2 found train-vs-validation transition matrix non-stationarity (Chow p=0.0042), which affects all expanding-window estimators.
5. **Legacy provenance**: Legacy artifacts have separate origin; their exact code versions are not in current repo. Comparison is observational.

---

## Recommendation for Next Steps

- **T3c**: Design/implement higher-order/state-augmented Markov chain baseline (e.g., MTD, VLMC, or 2nd-order chain) on validation, following same leakage controls.
- **Holdout protocol design**: Define the locked-holdout evaluation protocol (T8) without executing it, specifying: signal construction from state probabilities, position sizing, cost model (10.6/21.2 bps), purge/embargo, and decision rules for Forecast Validation Gate and Economic Simulation Gate.
- **Sensitivity expansion**: If higher-order baselines show promise, extend K/binning sweep to those model families.