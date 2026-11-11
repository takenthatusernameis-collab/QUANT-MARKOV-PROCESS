# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, K=7, kmeans)

**Generated:** 2026-11-11T01:58:07.980495+00:00
**Symbol/Freq:** BTCUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 7-state first-order Markov chain (kmeans discretization); refit every 720 bars on expanding history; eval_stride=4

## Scope and leakage controls
- Expanding fit uses returns up to time *t* only; forecast targets *t+1* in validation window.
- State discretization fitted on training data only (or expanding history at each refit).
- Locked holdout period (>= 2024-07-01) not used for fitting, selection, or evaluation.

## Baselines
- **Unconditional Gaussian:** expanding mean/variance of historical returns up to *t*.
- **EWMA Gaussian (RiskMetrics-style):** expanding mean with EWMA variance (lambda=0.94) on demeaned returns up to *t*.

## Forecast metrics (validation)
Observations: 1087 | Refits: 6

### Log score (mean, higher is better)
- markov_chain_mixture: 3.901247 (median 4.034824)
- unconditional_gaussian: 3.770382 (median 3.987600)
- ewma_gaussian: 3.902195 (median 4.193351)

### CRPS (mean, lower is better)
- markov_chain_mixture: 2.672384e-03 (median 1.735739e-03)
- unconditional_gaussian: 2.853621e-03 (median 1.928974e-03)
- ewma_gaussian: 2.630603e-03 (median 1.707313e-03)

### State-probability diagnostic (model-dependent realized state)
- Realized state is argmax predicted prob at t+1 under each refit model; diagnostic only, not ground truth.
- Brier (next-state, diagnostic): 0.403523
- Log loss (next-state, diagnostic): 0.814014

### Calibration diagnostic
- Markov chain mixture PIT mean=0.507746430836811 std=0.26604803056889065 (ideal uniform: mean 0.5, std ~0.289)

## Refitting stability / regime occupancy proxy
- Refits: 6
- State mean estimates mean across refits: [-0.03616023171503784, -0.015100792759502537, -0.00539498918259243, -0.0003743138796450756, 0.003971619600430943, 0.011813986964744902, 0.0288731015921372]
- State mean estimates std across refits: [0.0010168109765702669, 0.00040575077562874935, 0.0001577323600908722, 5.8849215674157073e-05, 8.255035532425446e-05, 0.00013094132538795451, 0.00019170883351268242]
- State variance estimates mean across refits: [0.0001427134284416326, 1.5244856107786587e-05, 3.8097283276557124e-06, 1.5786714361080422e-06, 2.6893996186807597e-06, 1.0218107100324009e-05, 0.00010562277132992314]
- State variance estimates std across refits: [5.379843417659262e-06, 8.416058541044797e-07, 1.5389612924354594e-07, 4.1726999283368834e-08, 5.783176735093633e-08, 1.5327156388944913e-07, 1.5732733511389545e-06]
- Mean state counts across refits: [169.66666666666666, 1208.8333333333333, 5082.666666666667, 13375.166666666666, 6807.0, 1828.5, 304.1666666666667]

## Artifacts
- `research/forecasts/h1_markov_chain_validation_kmeans_k7_results.json`
- `research/forecasts/h1_markov_chain_validation_kmeans_k7_forecasts.csv`
- `research/forecasts/figures/h1_markov_chain_validation_kmeans_k7_next_state_probs.png`
- `research/forecasts/figures/h1_markov_chain_validation_kmeans_k7_pit_hist.png`

## Interpretation notes
- Validation-only H1 groundwork; not a trading backtest and not a final holdout evaluation.
- Discretization method and state count are hyperparameters; sensitivity to these should be evaluated.
- Realized Markov states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison.
