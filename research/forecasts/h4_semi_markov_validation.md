# H1 Semi-Markov / Duration-Dependent Baseline (BTCUSDT 1h, Validation)

**Generated:** 2026-11-11T02:47:04.310161+00:00
**Model:** Semi-Markov chain with negative binomial sojourn distributions, K=5 states
**Discretization:** Quantile bins fitted on training returns only (<= 2023-12-31 00:00:00+00:00); edges fixed for validation forecasts
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Forecasts:** 1087 (eval_stride=4)

## Scope and leakage controls
- Expanding history up to time t-1 used to estimate transition counts/probabilities, sojourn distributions, and state-conditional return moments; target is t in validation window.
- Bin edges computed from training-period returns only; no holdout data used.
- Laplace smoothing applied to transition probabilities.
- Sojourn distributions fitted on expanding history; negative binomial (geometric fallback for sparse states).
- Hazard rate computed from fitted sojourn distribution; embedded transition matrix from Laplace-smoothed counts.

## State occupancy at forecast times
- [0.18491260349586017, 0.22631094756209752, 0.20515179392824287, 0.20607175712971482, 0.17755289788408463]

## Duration statistics at forecast times
- Mean duration: 1.3h
- Median duration: 1.0h
- Max duration: 9h

## Forecast metrics (validation)
### Log score (mean, higher is better)
- semi_markov_mixture: 3.829762 (median 4.378947427898695, std 1.216734401110758)
- unconditional_gaussian: 3.748211 (median 3.9802943078754707, std 0.9434928098198987)
- ewma_gaussian: 3.904237 (median 4.204800121229517, std 1.5329232343527013)
### CRPS (mean, lower is better)
- semi_markov_mixture: 2.707851e-03 (median 0.0016566302877911287, std 0.0030682454005044233)
- unconditional_gaussian: 2.902689e-03 (median 0.00196859522966986, std 0.0028057227660281594)
- ewma_gaussian: 2.673853e-03 (median 0.0017223000922270979, std 0.0029868857215599592)
### PIT (SM mixture): mean=0.4988487302906906, std=0.2787537357888254 (ideal uniform mean 0.5, std ~0.289)

## Block-bootstrap significance (stationary bootstrap)
### log_score_higher_better_diff_sm_minus_baseline
- sm_vs_unconditional: mean_diff=0.0815507, 95% CI=[0.007912205051998635, 0.15577516876697625], p=0.032, eff_n=558, significant@5%=True
- sm_vs_ewma: mean_diff=-0.074475, 95% CI=[-0.14880628135278526, 0.005914503829277425], p=0.06, eff_n=979, significant@5%=False
### crps_lower_better_diff_baseline_minus_sm
- sm_vs_unconditional: mean_diff=0.000194838, 95% CI=[0.00014067605232768695, 0.0002474557165983504], p=0.0, eff_n=366, significant@5%=True
- sm_vs_ewma: mean_diff=-3.39982e-05, 95% CI=[-6.605889558581292e-05, -1.7445866997167014e-06], p=0.039, eff_n=882, significant@5%=True
### aligned_h1_comparison
- log_score_diff_sm_minus_h1: mean_diff=0.0463063, 95% CI=[-0.023450210874833878, 0.11505686180305993], p=0.1885, eff_n=573, significant@5%=False
- crps_diff_h1_minus_sm: mean_diff=0.000153317, 95% CI=[0.00010743911292468649, 0.00019770916639541474], p=0.0, eff_n=407, significant@5%=True
### aligned_h3_comparison
- log_score_diff_sm_minus_h3: mean_diff=-0.00508387, 95% CI=[-0.06878372987665338, 0.060847194988353503], p=0.88, eff_n=660, significant@5%=False
- crps_diff_h3_minus_sm: mean_diff=0.000105525, 95% CI=[6.357696733790254e-05, 0.00014396019239072095], p=0.0, eff_n=584, significant@5%=True

## Artifacts
- `research/forecasts/h4_semi_markov_validation.json`
- `research/forecasts/h4_semi_markov_validation.csv`
- `research/forecasts/figures/h4_sm_next_state_probs.png`
- `research/forecasts/figures/h4_sm_pit_hist.png`
- `research/forecasts/figures/h4_sm_duration_hist.png`

## Caveats
- Validation-only baseline; no holdout evaluation. K=5 quantile bins and negative binomial sojourn are design choices.
- Sojourn distributions estimated from expanding history; sparse states fall back to geometric (Markov).
- H1/H3/HMM comparisons use saved validation CSV moment approximations; interpret cautiously.
- EM non-convergence warnings and train-vs-validation non-stationarity (prior Chow p=0.0042) remain project-level concerns.
