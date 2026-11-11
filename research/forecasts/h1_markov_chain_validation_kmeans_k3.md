# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, K=3, kmeans)

**Generated:** 2026-11-11T01:57:59.837560+00:00
**Symbol/Freq:** BTCUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 3-state first-order Markov chain (kmeans discretization); refit every 720 bars on expanding history; eval_stride=4

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
- markov_chain_mixture: 3.931890 (median 4.426636)
- unconditional_gaussian: 3.770382 (median 3.987600)
- ewma_gaussian: 3.902195 (median 4.193351)

### CRPS (mean, lower is better)
- markov_chain_mixture: 2.653992e-03 (median 1.550517e-03)
- unconditional_gaussian: 2.853621e-03 (median 1.928974e-03)
- ewma_gaussian: 2.630603e-03 (median 1.707313e-03)

### State-probability diagnostic (model-dependent realized state)
- Realized state is argmax predicted prob at t+1 under each refit model; diagnostic only, not ground truth.
- Brier (next-state, diagnostic): 0.080173
- Log loss (next-state, diagnostic): 0.246578

### Calibration diagnostic
- Markov chain mixture PIT mean=0.5174434799202949 std=0.2776932811713377 (ideal uniform: mean 0.5, std ~0.289)

## Refitting stability / regime occupancy proxy
- Refits: 6
- State mean estimates mean across refits: [-0.01289829949483849, -0.00014489488572685895, 0.011236396147352798]
- State mean estimates std across refits: [0.00012144762158296456, 1.6734798226707808e-05, 0.0001116890930170366]
- State variance estimates mean across refits: [6.264114277744979e-05, 7.2278283265861545e-06, 5.024618709263697e-05]
- State variance estimates std across refits: [9.57762112927654e-07, 7.254741500009781e-08, 1.0621811794773202e-06]
- Mean state counts across refits: [2752.6666666666665, 22507.666666666668, 3515.6666666666665]

## Artifacts
- `research/forecasts/h1_markov_chain_validation_kmeans_k3_results.json`
- `research/forecasts/h1_markov_chain_validation_kmeans_k3_forecasts.csv`
- `research/forecasts/figures/h1_markov_chain_validation_kmeans_k3_next_state_probs.png`
- `research/forecasts/figures/h1_markov_chain_validation_kmeans_k3_pit_hist.png`

## Interpretation notes
- Validation-only H1 groundwork; not a trading backtest and not a final holdout evaluation.
- Discretization method and state count are hyperparameters; sensitivity to these should be evaluated.
- Realized Markov states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison.
