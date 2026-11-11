# Negative Controls for C1/HMM and C2/HOM (Validation Only)

**Generated (UTC):** 2026-11-11T04:39:46.965635+00:00
**Scope:** Validation-only red-team robustness check on saved BTCUSDT 1h forecast grids.
No holdout data used; no model tuning performed.

## Method
- Real model: saved mixture-moment Gaussian log score / CRPS on the saved validation grid.
- NC_A white noise: Gaussian N(0, sigma_y^2), pure no-information forecast.
- NC_B target-shuffled: model moments paired with stationary-bootstrap resampled y_true,
  destroying the genuine forecast->target relationship (n_shuffle resamples averaged).
- Uncertainty: stationary block bootstrap (Politis & Romano 1994), block length n^(1/3),
  2000 replications, 95% percentile CIs, two-sided p-values for H0: mean paired difference = 0.
- Interpretation: a genuine edge should beat both negative controls significantly; the
  shuffled-vs-white-noise comparison should be ~0 / not significant, confirming the shuffle
  removes information without injecting spurious skill.

## H2 filtered HMM (C1 primary) (C1)
Source: `research/forecasts/h2_validation_forecasts.csv` (n=1087, 2024-01-01 01:00:00+00:00 to 2024-06-30 01:00:00+00:00)

| Control | Log score mean | CRPS mean |
|---|---:|---:|
| Real model | 3.922148 | 2.676031e-03 |
| White noise (NC_A) | 3.848257 | 2.690418e-03 |
| Target-shuffled (NC_B) | 3.737331 | 2.819525e-03 |
| Unconditional baseline | 3.770382 | 2.853621e-03 |
| EWMA baseline | 3.902195 | 2.630603e-03 |

### Paired-difference block bootstrap (mean diff, 95% CI, p-value, eff. n)
| Comparison | Direction | Mean diff | 95% CI | p-value | Eff. n | Significant @5% |
|---|---|---:|---:|---:|---:|---|
| real_minus_white_noise_log | real > white noise (log) | +7.389030e-02 | [+2.845997e-02, +1.250388e-01] | 0.0025 | 952 | Yes |
| real_minus_white_noise_crps | real > white noise (CRPS) | +1.438720e-05 | [-1.796779e-05, +4.777061e-05] | 0.3705 | 1155 | No |
| real_minus_shuffled_log | real > shuffled (log) | +1.848168e-01 | [+1.021657e-01, +2.599267e-01] | 0.0000 | 513 | Yes |
| real_minus_shuffled_crps | real > shuffled (CRPS) | +1.434940e-04 | [-1.019625e-04, +3.528065e-04] | 0.1960 | 498 | No |
| shuffled_minus_white_noise_log | shuffled ~ white noise (log) | -1.109265e-01 | [-2.076305e-01, +1.485610e-04] | 0.0330 | 624 | No |
| shuffled_minus_white_noise_crps | shuffled ~ white noise (CRPS) | -1.291069e-04 | [-3.452516e-04, +1.278482e-04] | 0.2625 | 563 | No |

## H3 higher-order Markov (C2 comparator) (C2)
Source: `research/forecasts/h3_higher_order_markov_validation.csv` (n=1087, 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00)

| Control | Log score mean | CRPS mean |
|---|---:|---:|
| Real model | 3.834846 | 2.813376e-03 |
| White noise (NC_A) | 3.808353 | 2.754347e-03 |
| Target-shuffled (NC_B) | 3.733504 | 2.898432e-03 |
| Unconditional baseline | 3.748211 | 2.902689e-03 |
| EWMA baseline | 3.904237 | 2.673853e-03 |

### Paired-difference block bootstrap (mean diff, 95% CI, p-value, eff. n)
| Comparison | Direction | Mean diff | 95% CI | p-value | Eff. n | Significant @5% |
|---|---|---:|---:|---:|---:|---|
| real_minus_white_noise_log | real > white noise (log) | +2.649212e-02 | [-2.697503e-02, +8.686568e-02] | 0.3665 | 1104 | No |
| real_minus_white_noise_crps | real > white noise (CRPS) | -5.902929e-05 | [-9.086666e-05, -2.596743e-05] | 0.0005 | 987 | Yes |
| real_minus_shuffled_log | real > shuffled (log) | +1.013418e-01 | [+3.380904e-02, +1.650485e-01] | 0.0035 | 555 | Yes |
| real_minus_shuffled_crps | real > shuffled (CRPS) | +8.505610e-05 | [-1.649691e-04, +3.158976e-04] | 0.4845 | 502 | No |
| shuffled_minus_white_noise_log | shuffled ~ white noise (log) | -7.484966e-02 | [-1.826711e-01, +4.097457e-02] | 0.1980 | 765 | No |
| shuffled_minus_white_noise_crps | shuffled ~ white noise (CRPS) | -1.440854e-04 | [-3.960856e-04, +1.229695e-04] | 0.2835 | 532 | No |

## Interpretation
- A real predictive edge should show significant positive paired differences vs both negative controls.
- The shuffled-vs-white-noise comparison being ~0 / not significant confirms the target shuffle removes
  information without creating spurious skill.
- Results are validation-period diagnostics on a stride-4 sampled grid; they are not holdout evidence.
- No holdout evaluation performed.
