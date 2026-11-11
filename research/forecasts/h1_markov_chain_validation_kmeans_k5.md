# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, K=5, kmeans)

**Generated:** 2026-11-11T01:58:03.638477+00:00
**Symbol/Freq:** BTCUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 5-state first-order Markov chain (kmeans discretization); refit every 720 bars on expanding history; eval_stride=4

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
- markov_chain_mixture: 3.921701 (median 4.064106)
- unconditional_gaussian: 3.770382 (median 3.987600)
- ewma_gaussian: 3.902195 (median 4.193351)

### CRPS (mean, lower is better)
- markov_chain_mixture: 2.676843e-03 (median 1.808946e-03)
- unconditional_gaussian: 2.853621e-03 (median 1.928974e-03)
- ewma_gaussian: 2.630603e-03 (median 1.707313e-03)

### State-probability diagnostic (model-dependent realized state)
- Realized state is argmax predicted prob at t+1 under each refit model; diagnostic only, not ground truth.
- Brier (next-state, diagnostic): 0.252526
- Log loss (next-state, diagnostic): 0.559685

### Calibration diagnostic
- Markov chain mixture PIT mean=0.5103636334281281 std=0.2740026344262454 (ideal uniform: mean 0.5, std ~0.289)

## Refitting stability / regime occupancy proxy
- Refits: 6
- State mean estimates mean across refits: [-0.0232654419065591, -0.006831690819666791, -0.00014953337091724037, 0.006049581218256289, 0.020924954448577077]
- State mean estimates std across refits: [0.000288917348177365, 0.00012285181413260892, 3.838848432956791e-05, 8.107901726440345e-05, 0.0001678372434385999]
- State variance estimates mean across refits: [9.714357657998513e-05, 8.208316397579565e-06, 2.7147867977426146e-06, 6.869320580108928e-06, 7.917253124442891e-05]
- State variance estimates std across refits: [1.7814078826081216e-06, 1.8968973052080027e-07, 4.7245184184025554e-08, 1.1145333485255071e-07, 1.7843335636870542e-06]
- Mean state counts across refits: [674.3333333333334, 4835.833333333333, 16684.833333333332, 5764.5, 816.5]

## Artifacts
- `research/forecasts/h1_markov_chain_validation_kmeans_k5_results.json`
- `research/forecasts/h1_markov_chain_validation_kmeans_k5_forecasts.csv`
- `research/forecasts/figures/h1_markov_chain_validation_kmeans_k5_next_state_probs.png`
- `research/forecasts/figures/h1_markov_chain_validation_kmeans_k5_pit_hist.png`

## Interpretation notes
- Validation-only H1 groundwork; not a trading backtest and not a final holdout evaluation.
- Discretization method and state count are hyperparameters; sensitivity to these should be evaluated.
- Realized Markov states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison.
