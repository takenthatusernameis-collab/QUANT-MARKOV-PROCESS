# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, K=7, quantile)

**Generated:** 2026-11-11T01:57:56.782953+00:00
**Symbol/Freq:** BTCUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 7-state first-order Markov chain (quantile discretization); refit every 720 bars on expanding history; eval_stride=4

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
- markov_chain_mixture: 3.856930 (median 4.193542)
- unconditional_gaussian: 3.770382 (median 3.987600)
- ewma_gaussian: 3.902195 (median 4.193351)

### CRPS (mean, lower is better)
- markov_chain_mixture: 2.683120e-03 (median 1.670660e-03)
- unconditional_gaussian: 2.853621e-03 (median 1.928974e-03)
- ewma_gaussian: 2.630603e-03 (median 1.707313e-03)

### State-probability diagnostic (model-dependent realized state)
- Realized state is argmax predicted prob at t+1 under each refit model; diagnostic only, not ground truth.
- Brier (next-state, diagnostic): 0.760040
- Log loss (next-state, diagnostic): 1.633793

### Calibration diagnostic
- Markov chain mixture PIT mean=0.5115886307428279 std=0.270778068859891 (ideal uniform: mean 0.5, std ~0.289)

## Refitting stability / regime occupancy proxy
- Refits: 6
- State mean estimates mean across refits: [-0.01046211193574634, -0.003152509500754935, -0.0012240104890490293, 5.2503677997443604e-05, 0.0013315219482403758, 0.003278357422463438, 0.010354252904256409]
- State mean estimates std across refits: [7.520690882498707e-05, 1.944341515372615e-05, 6.222271359582471e-06, 3.785577090326024e-06, 1.0588962950011816e-05, 1.9524962814562572e-05, 7.773837160943874e-05]
- State variance estimates mean across refits: [5.404569329082003e-05, 6.087056971600762e-07, 1.6462597397857713e-07, 1.2668338837518245e-07, 1.6846436057749237e-07, 6.009323187067149e-07, 4.754609082039136e-05]
- State variance estimates std across refits: [7.763218863780735e-07, 1.250764755793645e-08, 2.049799293810719e-09, 1.5433641265331853e-09, 2.1582080299533134e-09, 1.0988069535889015e-08, 9.271556822765835e-07]
- Mean state counts across refits: [4111.166666666667, 4110.666666666667, 4110.666666666667, 4110.833333333333, 4110.666666666667, 4110.666666666667, 4111.333333333333]

## Artifacts
- `research/forecasts/h1_markov_chain_validation_quantile_k7_results.json`
- `research/forecasts/h1_markov_chain_validation_quantile_k7_forecasts.csv`
- `research/forecasts/figures/h1_markov_chain_validation_quantile_k7_next_state_probs.png`
- `research/forecasts/figures/h1_markov_chain_validation_quantile_k7_pit_hist.png`

## Interpretation notes
- Validation-only H1 groundwork; not a trading backtest and not a final holdout evaluation.
- Discretization method and state count are hyperparameters; sensitivity to these should be evaluated.
- Realized Markov states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison.
