# H2 Validation Forecast Significance Analysis (Block Bootstrap)

**Generated:** 2026-11-11T01:52:01.709902+00:00

## T4 Evaluation Configuration (from saved artifacts)
- refit_every: 720
- seeds: [0, 1, 2]
- eval_stride: 4
- train_end: 2023-12-31 00:00:00+00:00
- val_start: 2024-01-01 00:00:00+00:00
- val_end: 2024-06-30 00:00:00+00:00
- holdout_start: 2024-07-01 00:00:00+00:00

## Limitations of Evaluation Grid
- `eval_stride=4`: Only every 4th hourly bar evaluated (effective 4-hour cadence)
- `refit_every=720`: Model refit monthly; parameter estimates change only at refit points
- `seeds=[0, 1, 2]`: Multi-seed selection on training log-likelihood per refit
- Non-fatal EM convergence warnings observed on some refits/seeds
- Prior EDA showed train-vs-validation transition non-stationarity (Chow p=0.0042)
- **Validation-only results; not a locked-holdout evaluation**

## Block Bootstrap Methodology
- Stationary bootstrap (Politis & Romano 1994) with block length n^(1/3)
- 2000 bootstrap replications per comparison
- Paired differences computed per forecast observation
- 95% percentile confidence intervals
- Two-sided p-values from bootstrap distribution
- Effective sample size estimated via variance ratio

## Bootstrap Results

### Log Score (higher is better; positive diff = HMM better)
### CRPS (lower is better; positive diff = HMM better since diff = baseline - HMM)
**hmm_vs_unc**:
- Mean difference: 1.775902e-04
- 95% CI: [1.342471e-04, 2.193698e-04]
- p-value (two-sided): 0.0000
- Effective n: 576
- Block length: 10.28
- Significant at 5%: Yes

**hmm_vs_ewma**:
- Mean difference: -4.542841e-05
- 95% CI: [-7.625505e-05, -1.200835e-05]
- p-value (two-sided): 0.0060
- Effective n: 633
- Block length: 10.28
- Significant at 5%: Yes

## Sensitivity Check
- **Sensitivity config**: refit_every=1440, eval_stride=8, window=2024-01-01 00:00:00+00:00 to 2024-03-31 00:00:00+00:00
- **Main config on same window**: refit_every=720, eval_stride=4
- **HMM Log Score**: Main=3.924161, Sens=3.865222, Delta=-0.058938
- **HMM CRPS**: Main=2.848450e-03, Sens=2.995178e-03, Delta=1.467287e-04
- **Forecasts**: Main=541, Sens=271
- **Refits**: Main=4, Sens=2
- Sensitivity check on first half of validation window (Jan-Mar 2024) with coarser stride and less frequent refitting. Not tuned on holdout.

## Artifacts
- `research/forecasts/h2_hmm_validation_significance.json`
- `research/forecasts/h2_hmm_validation_significance.md`
- `research/forecasts/figures/h2_bootstrap_diffs.png`

## Interpretation Notes
- Results are **validation-period only**; holdout (>=2024-07-01) not used.
- Block bootstrap accounts for temporal dependence but effective n << n_observations due to autocorrelation in score differences.
- Sensitivity check shows metric stability to evaluation cadence/refit frequency on a sub-window.
- Non-stationarity (Chow test p<0.01) and EM convergence warnings remain caveats.
- Next steps: T3 finite-state Markov chain baseline on validation, or holdout-evaluation protocol design.
