# H1 Higher-Order / State-Augmented Markov Chain Baseline (BTCUSDT 1h, Validation)

**Generated:** 2026-11-11T02:33:08.517935+00:00
**Model:** Second-order Markov chain, state pair X_{t} = (S_{t-1}, S_{t}), K=5 states, 25 pairs
**Discretization:** Quantile bins fitted on training returns only (<= 2023-12-31 00:00:00+00:00); edges fixed for validation forecasts
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Forecasts:** 1087 (eval_stride=4)

## Scope and leakage controls
- Expanding history up to time t-1 used to estimate order-2 transition counts/probs and pair-conditional return moments; target is t in validation window.
- Transition P(S_t=j | S_{t-2}, S_{t-1}) estimated from (S_{u-1}, S_u) -> S_{u+1} counts in history only.
- Pair-conditional return E[r_t | (S_{t-1}, S_t)=(S_{t-1}, j)] estimated from history returns with the same pair.
- Bin edges computed from training-period returns only; no holdout data used.
- Laplace smoothing applied to transition probabilities.

## Pair occupancy at forecast times
- [[0.03955841766329347, 0.03035878564857406, 0.02483900643974241, 0.040478380864765406, 0.04139834406623735], [0.03403863845446182, 0.046918123275068994, 0.045998160073597055, 0.04415823367065318, 0.027598896044158234], [0.03955841766329347, 0.045998160073597055, 0.05519779208831647, 0.050597976080956765, 0.025758969641214352], [0.027598896044158234, 0.051517939282428704, 0.04967801287948482, 0.04139834406623735, 0.04231830726770929], [0.04415823367065318, 0.051517939282428704, 0.029438822447102116, 0.029438822447102116, 0.040478380864765406]]

## Forecast metrics (validation)
### Log score (mean, higher is better)
- higher_order_markov_mixture: 3.858447 (median 4.334735681234001, std 1.1615740195697337)
- unconditional_gaussian: 3.748211 (median 3.9802943078754707, std 0.9434928098198987)
- ewma_gaussian: 3.904237 (median 4.204800121229517, std 1.5329232343527013)
### CRPS (mean, lower is better)
- higher_order_markov_mixture: 2.687487e-03 (median 0.0017398210355191956, std 0.0030131582407935025)
- unconditional_gaussian: 2.902689e-03 (median 0.00196859522966986, std 0.0028057227660281594)
- ewma_gaussian: 2.673853e-03 (median 0.0017223000922270979, std 0.0029868857215599592)
### PIT (HOM mixture): mean=0.49929238783816604, std=0.27989345715193514 (ideal uniform mean 0.5, std ~0.289)

## Block-bootstrap significance (stationary bootstrap)
### log_score_higher_better_diff_hom_minus_baseline
- hom_vs_unconditional: mean_diff=0.110236, 95% CI=[0.03696223876776857, 0.18142137311518278], p=0.002, eff_n=685, significant@5%=True
- hom_vs_ewma: mean_diff=-0.0457897, 95% CI=[-0.11483510177792185, 0.025907242590919234], p=0.2125, eff_n=1020, significant@5%=False

### crps_lower_better_diff_baseline_minus_hom
- hom_vs_unconditional: mean_diff=0.000215202, 95% CI=[0.00016132711379770545, 0.0002701554841748738], p=0.0, eff_n=435, significant@5%=True
- hom_vs_ewma: mean_diff=-1.3634e-05, 95% CI=[-4.503268682573613e-05, 1.8636517628235802e-05], p=0.412, eff_n=901, significant@5%=False

### aligned_h1_comparison
- log_score_diff_hom_minus_h1: mean_diff=0.0286837, 95% CI=[0.01235175778219728, 0.045481738536162344], p=0.001, eff_n=1310, significant@5%=True
- crps_diff_h1_minus_hom: mean_diff=2.03635e-05, 95% CI=[6.246010614749736e-06, 3.530306418116527e-05], p=0.004, eff_n=1000, significant@5%=True

## Artifacts
- `research/forecasts/h3_higher_order_markov_validation.json`
- `research/forecasts/h3_higher_order_markov_validation.csv`
- `research/forecasts/figures/h3_hom_next_state_probs.png`
- `research/forecasts/figures/h3_hom_pit_hist.png`

## Caveats
- Validation-only baseline; no holdout evaluation. K=5 quantile bins and order m=2 are design choices (state space K^2=25; sparse pairs handled via Laplace + global fallback).
- HMM comparison uses saved T4 mixture-moment Gaussian approximation from CSV; the saved HMM forecast grid is offset by one hour relative to the H1/H3 grid (01:00 vs 00:00), so a direct timestamp-aligned HOM-vs-HMM comparison was not computed; H2 reference metrics are in the T4 validation report (log score 4.0164, CRPS 0.002597).
- H1 comparison reconstructs the H1 mixture from saved CSV components on identical timestamps.
- EM non-convergence warnings and train-vs-validation non-stationarity (prior Chow p=0.0042) remain project-level concerns.
