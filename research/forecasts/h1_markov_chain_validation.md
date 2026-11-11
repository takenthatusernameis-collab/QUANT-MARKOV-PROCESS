# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, Validation)

**Generated:** 2026-11-11T02:16:27.672693+00:00
**Model:** First-order finite-state Markov chain, K=5 states
**Discretization:** Quantile bins fitted on training returns only (<= 2023-12-31 00:00:00+00:00); edges fixed for validation forecasts
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Forecasts:** 1087 (eval_stride=4)

## Scope and leakage controls
- Expanding history up to time *t-1* used to estimate transition counts/probabilities and state-conditional return moments; target is *t* in validation window.
- Bin edges computed from training-period returns only; no holdout data used.
- Laplace smoothing applied to transition probabilities.

## State occupancy at forecast times
- [0.18491260349586017, 0.22631094756209752, 0.20515179392824287, 0.20607175712971482, 0.17755289788408463]

## Forecast metrics (validation)
### Log score (mean, higher is better)
- markov_chain_mixture: 3.829763 (median 4.378909952024257, std 1.216734463852296)
- unconditional_gaussian: 3.748211 (median 3.9802943078754707, std 0.9434928098198987)
- ewma_gaussian: 3.904237 (median 4.204800121229517, std 1.5329232343527013)
### CRPS (mean, lower is better)
- markov_chain_mixture: 2.707850e-03 (median 0.0016566191712709712, std 0.0030682496754000214)
- unconditional_gaussian: 2.902689e-03 (median 0.00196859522966986, std 0.0028057227660281594)
- ewma_gaussian: 2.673853e-03 (median 0.0017223000922270979, std 0.0029868857215599592)
### PIT (MC mixture): mean=0.4988485163739538, std=0.2787534984730712 (ideal uniform mean 0.5, std ~0.289)

## Block-bootstrap significance (stationary bootstrap)
### log_score_higher_better_diff_mc_minus_baseline
- mc_vs_unconditional: mean_diff=0.0815524, 95% CI=[0.007913742942308148, 0.1557736942920929], p=0.032, eff_n=558, significant@5%=True
- mc_vs_ewma: mean_diff=-0.0744734, 95% CI=[-0.1488072261638776, 0.005914462508276421], p=0.06, eff_n=979, significant@5%=False

### crps_lower_better_diff_baseline_minus_mc
- mc_vs_unconditional: mean_diff=0.000194839, 95% CI=[0.00014067769959886007, 0.00024745516975812514], p=0.0, eff_n=366, significant@5%=True
- mc_vs_ewma: mean_diff=-3.39974e-05, 95% CI=[-6.60590132296682e-05, -1.7432750753951906e-06], p=0.039, eff_n=882, significant@5%=True

## Artifacts
- `research/forecasts/h1_markov_chain_validation.json`
- `research/forecasts/h1_markov_chain_validation.csv`
- `research/forecasts/figures/h1_mc_next_state_probs.png`
- `research/forecasts/figures/h1_mc_pit_hist.png`

## Caveats
- Validation-only baseline; no holdout evaluation. Discretization and K are design choices (sensitivity to K/binning not exhaustively swept).
- HMM comparison uses saved T4 mixture-moment Gaussian approximation from CSV where applicable; interpret aligned HMM-vs-MC scores cautiously.
- EM non-convergence warnings and train-vs-validation non-stationarity (prior Chow p=0.0042) remain project-level concerns.
