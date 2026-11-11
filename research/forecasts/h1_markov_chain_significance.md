# H1 Markov Chain Validation Significance Analysis (Block Bootstrap)

**Generated:** 2026-11-11T02:03:16.294607+00:00

## T3 Evaluation Configuration (from saved artifacts)
- refit_every: 720
- eval_stride: 4
- train_end: 2023-12-31 00:00:00+00:00
- val_start: 2024-01-01 00:00:00+00:00
- val_end: 2024-06-30 00:00:00+00:00
- holdout_start: 2024-07-01 00:00:00+00:00

## Limitations of Evaluation Grid
- `eval_stride=4`: Only every 4th hourly bar evaluated (effective 4-hour cadence)
- `refit_every=720`: Model refit monthly; parameter estimates change only at refit points
- Non-fatal discretization instability possible on some refits
- Prior EDA showed train-vs-validation transition non-stationarity (Chow p=0.0042)
- **Validation-only results; not a locked-holdout evaluation**

## Block Bootstrap Methodology
- Stationary bootstrap (Politis & Romano 1994) with block length n^(1/3)
- 2000 bootstrap replications per comparison
- Paired differences computed per forecast observation
- 95% percentile confidence intervals
- Two-sided p-values from bootstrap distribution
- Effective sample size estimated via variance ratio

## Bootstrap Results: h1_markov_chain_validation_kmeans_k3

### Log Score (higher is better; positive diff = MC better)
### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)
**mc_vs_unc**:
- Mean difference: 3.020047e-05
- 95% CI: [-3.666691e-07, 5.655487e-05]
- p-value (two-sided): 0.0350
- Effective n: 248
- Block length: 10.28
- Significant at 5%: No

**mc_vs_ewma**:
- Mean difference: -1.928181e-04
- 95% CI: [-2.422942e-04, -1.403983e-04]
- p-value (two-sided): 0.0000
- Effective n: 486
- Block length: 10.28
- Significant at 5%: Yes

## Bootstrap Results: h1_markov_chain_validation_kmeans_k5

### Log Score (higher is better; positive diff = MC better)
### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)
**mc_vs_unc**:
- Mean difference: -5.750295e-06
- 95% CI: [-8.083441e-05, 5.807961e-05]
- p-value (two-sided): 0.8680
- Effective n: 180
- Block length: 10.28
- Significant at 5%: No

**mc_vs_ewma**:
- Mean difference: -2.287689e-04
- 95% CI: [-3.017174e-04, -1.651694e-04]
- p-value (two-sided): 0.0000
- Effective n: 319
- Block length: 10.28
- Significant at 5%: Yes

## Bootstrap Results: h1_markov_chain_validation_kmeans_k7

### Log Score (higher is better; positive diff = MC better)
### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)
**mc_vs_unc**:
- Mean difference: -2.003223e-05
- 95% CI: [-7.233976e-05, 2.724761e-05]
- p-value (two-sided): 0.4305
- Effective n: 219
- Block length: 10.28
- Significant at 5%: No

**mc_vs_ewma**:
- Mean difference: -2.430508e-04
- 95% CI: [-3.052640e-04, -1.818484e-04]
- p-value (two-sided): 0.0000
- Effective n: 379
- Block length: 10.28
- Significant at 5%: Yes

## Bootstrap Results: h1_markov_chain_validation_quantile_k3

### Log Score (higher is better; positive diff = MC better)
### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)
**mc_vs_unc**:
- Mean difference: -4.237109e-06
- 95% CI: [-1.819099e-05, 1.062256e-05]
- p-value (two-sided): 0.5450
- Effective n: 465
- Block length: 10.28
- Significant at 5%: No

**mc_vs_ewma**:
- Mean difference: -2.272557e-04
- 95% CI: [-2.810695e-04, -1.705679e-04]
- p-value (two-sided): 0.0000
- Effective n: 466
- Block length: 10.28
- Significant at 5%: Yes

## Bootstrap Results: h1_markov_chain_validation_quantile_k5

### Log Score (higher is better; positive diff = MC better)
### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)
**mc_vs_unc**:
- Mean difference: 9.521095e-06
- 95% CI: [-1.224697e-05, 3.145403e-05]
- p-value (two-sided): 0.4005
- Effective n: 249
- Block length: 10.28
- Significant at 5%: No

**mc_vs_ewma**:
- Mean difference: -2.134975e-04
- 95% CI: [-2.631332e-04, -1.606975e-04]
- p-value (two-sided): 0.0000
- Effective n: 492
- Block length: 10.28
- Significant at 5%: Yes

## Bootstrap Results: h1_markov_chain_validation_quantile_k7

### Log Score (higher is better; positive diff = MC better)
### CRPS (lower is better; positive diff = MC better since diff = baseline - MC)
**mc_vs_unc**:
- Mean difference: -1.011749e-05
- 95% CI: [-4.235796e-05, 2.225583e-05]
- p-value (two-sided): 0.5500
- Effective n: 223
- Block length: 10.28
- Significant at 5%: No

**mc_vs_ewma**:
- Mean difference: -2.331361e-04
- 95% CI: [-2.882547e-04, -1.757684e-04]
- p-value (two-sided): 0.0000
- Effective n: 436
- Block length: 10.28
- Significant at 5%: Yes

## Sensitivity Check Across Configurations
- **Configs tested**: h1_markov_chain_validation_kmeans_k3, h1_markov_chain_validation_quantile_k7, h1_markov_chain_validation_quantile_k3, h1_markov_chain_validation_kmeans_k7, h1_markov_chain_validation_kmeans_k5, h1_markov_chain_validation_quantile_k5

### h1_markov_chain_validation_kmeans_k3
- Forecasts: 1087
- MC Log Score: 3.793231
- MC CRPS: 2.823421e-03
- Log Score vs Unconditional: 0.022849
- CRPS vs Unconditional: 3.020047e-05
- Log Score vs EWMA: -0.108965
- CRPS vs EWMA: -1.928181e-04

### h1_markov_chain_validation_quantile_k7
- Forecasts: 1087
- MC Log Score: 3.770301
- MC CRPS: 2.863739e-03
- Log Score vs Unconditional: -0.000080
- CRPS vs Unconditional: -1.011749e-05
- Log Score vs EWMA: -0.131894
- CRPS vs EWMA: -2.331361e-04

### h1_markov_chain_validation_quantile_k3
- Forecasts: 1087
- MC Log Score: 3.770453
- MC CRPS: 2.857858e-03
- Log Score vs Unconditional: 0.000071
- CRPS vs Unconditional: -4.237109e-06
- Log Score vs EWMA: -0.131743
- CRPS vs EWMA: -2.272557e-04

### h1_markov_chain_validation_kmeans_k7
- Forecasts: 1087
- MC Log Score: 3.764754
- MC CRPS: 2.873653e-03
- Log Score vs Unconditional: -0.005628
- CRPS vs Unconditional: -2.003223e-05
- Log Score vs EWMA: -0.137442
- CRPS vs EWMA: -2.430508e-04

### h1_markov_chain_validation_kmeans_k5
- Forecasts: 1087
- MC Log Score: 3.784185
- MC CRPS: 2.859372e-03
- Log Score vs Unconditional: 0.013804
- CRPS vs Unconditional: -5.750295e-06
- Log Score vs EWMA: -0.118010
- CRPS vs EWMA: -2.287689e-04

### h1_markov_chain_validation_quantile_k5
- Forecasts: 1087
- MC Log Score: 3.782110
- MC CRPS: 2.844100e-03
- Log Score vs Unconditional: 0.011728
- CRPS vs Unconditional: 9.521095e-06
- Log Score vs EWMA: -0.120086
- CRPS vs EWMA: -2.134975e-04

## Comparison with T4 HMM (reference, same validation window)
- T4 HMM Log Score: 4.016430
- T4 HMM CRPS: 2.596860e-03

## Artifacts
- `research/forecasts/h1_markov_chain_significance.json`
- `research/forecasts/h1_markov_chain_significance.md`
- `research/forecasts/figures/h1_bootstrap_diffs_*.png`

## Interpretation Notes
- Results are **validation-period only**; holdout (>=2024-07-01) not used.
- Block bootstrap accounts for temporal dependence but effective n << n_observations due to autocorrelation in score differences.
- Sensitivity check shows metric variation across n_states and discretization methods.
- Non-stationarity (Chow test p<0.01) remains a caveat.
- Next steps: T3b higher-order/state-augmented baseline, or holdout-evaluation protocol design.
