# Validation Period Perturbation (Q1 vs Q2 2024)

**Generated (UTC):** 2026-11-11T04:33:54.949539+00:00
**Scope:** Validation-only robustness check on saved BTCUSDT 1h forecast grids (stride 4). No holdout data used; no tuning.

## Method
- Split each model's saved validation forecasts into Q1 (2024-01-01 <= t < 2024-04-01) and Q2 (2024-04-01 <= t < 2024-07-01).
- Scores computed from per-row Gaussian moments (`*_mu`, `*_var`): log score (higher better) and Gaussian CRPS (lower better). This matches the saved-moment scoring used in prior significance scripts.
- Uncertainty: stationary block bootstrap (Politis & Romano 1994), block length n^(1/3), 2000 replications, fixed seeds; 95% percentile CIs; two-sided p-values for H0: mean paired difference = 0.
- Caveats: sampled stride-4 grid, temporal dependence (effective n < n), non-stationarity and HMM EM convergence caveats from prior sessions remain.

## H2 filtered HMM (C1 primary) (C1)
Source: `research/forecasts/h2_validation_forecasts.csv` (n=1087)

| Period | n | Log score | CRPS | vs Unc log diff | vs EWMA log diff | vs Unc CRPS diff (base-model) | vs EWMA CRPS diff (base-model) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q1_2024 | 546 | 3.850483 | 2.899271e-03 | +0.129711 (p=0.000) | -0.021829 (p=0.367) | +1.462e-04 (p=0.000) | -4.495e-05 (p=0.024) |
| Q2_2024 | 541 | 3.994475 | 2.450728e-03 | +0.174025 (p=0.000) | +0.062120 (p=0.177) | +2.093e-04 (p=0.000) | -4.591e-05 (p=0.054) |

**Q2−Q1 point deltas (stability diagnostic):**
- Model log score: +0.143992; Model CRPS: -4.485427e-04
- Edge vs unconditional (log): +0.044314; vs EWMA (log): +0.083950
- Edge vs unconditional (CRPS, base-model): +6.316471e-05; vs EWMA: -9.611810e-07

## H3 higher-order Markov (C2 comparator) (C2)
Source: `research/forecasts/h3_higher_order_markov_validation.csv` (n=1087)

| Period | n | Log score | CRPS | vs Unc log diff | vs EWMA log diff | vs Unc CRPS diff (base-model) | vs EWMA CRPS diff (base-model) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q1_2024 | 546 | 3.763626 | 3.098259e-03 | +0.074359 (p=0.000) | -0.064116 (p=0.068) | +7.811e-05 (p=0.000) | -1.253e-04 (p=0.000) |
| Q2_2024 | 541 | 3.906723 | 2.525860e-03 | +0.099023 (p=0.001) | -0.074716 (p=0.117) | +1.006e-04 (p=0.000) | -1.539e-04 (p=0.000) |

**Q2−Q1 point deltas (stability diagnostic):**
- Model log score: +0.143097; Model CRPS: -5.723996e-04
- Edge vs unconditional (log): +0.024664; vs EWMA (log): -0.010600
- Edge vs unconditional (CRPS, base-model): +2.250359e-05; vs EWMA: -2.857189e-05

## Interpretation
- C1/HMM and C2/HOM both improve on raw point scores from Q1 to Q2 in this sample, but relative edges vs EWMA/unconditional are not uniformly stable across periods; subperiod bootstrap CIs/p-values reflect reduced effective sample size and should be read as robustness diagnostics, not confirmatory holdout evidence.
- This perturbation does not resolve cross-asset instability observed in ETHUSDT or non-stationarity (Chow p=0.0042); negative controls and further period/asset perturbations remain relevant pre-holdout robustness checks.
- No holdout evaluation performed.
