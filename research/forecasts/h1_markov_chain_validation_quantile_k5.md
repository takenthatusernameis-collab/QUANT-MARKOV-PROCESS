# H1 Finite-State Markov Chain Baseline (BTCUSDT 1h, K=5, quantile)

**Generated:** 2026-11-11T01:57:55.436002+00:00
**Symbol/Freq:** BTCUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 5-state first-order Markov chain (quantile discretization); refit every 720 bars on expanding history; eval_stride=4

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
- markov_chain_mixture: 3.839049 (median 4.377042)
- unconditional_gaussian: 3.770382 (median 3.987600)
- ewma_gaussian: 3.902195 (median 4.193351)

### CRPS (mean, lower is better)
- markov_chain_mixture: 2.684786e-03 (median 1.642644e-03)
- unconditional_gaussian: 2.853621e-03 (median 1.928974e-03)
- ewma_gaussian: 2.630603e-03 (median 1.707313e-03)

### State-probability diagnostic (model-dependent realized state)
- Realized state is argmax predicted prob at t+1 under each refit model; diagnostic only, not ground truth.
- Brier (next-state, diagnostic): 0.698179
- Log loss (next-state, diagnostic): 1.366825

### Calibration diagnostic
- Markov chain mixture PIT mean=0.5143848197793658 std=0.2726600700886436 (ideal uniform: mean 0.5, std ~0.289)

## Refitting stability / regime occupancy proxy
- Refits: 6
- State mean estimates mean across refits: [-0.008609756855935484, -0.00189161194438575, 5.1703701769360636e-05, 0.0020085604560979723, 0.008567377567100978]
- State mean estimates std across refits: [6.13659069560979e-05, 1.0301807788516245e-05, 3.806128961462942e-06, 1.3932382935477934e-05, 6.0617185587624694e-05]
- State variance estimates mean across refits: [4.723464681144155e-05, 5.110703406023597e-07, 2.477674927761984e-07, 5.228767665710215e-07, 4.198371875013428e-05]
- State variance estimates std across refits: [6.870268556370365e-07, 6.815027454933407e-09, 2.8169071744892762e-09, 6.417396171323894e-09, 8.240628384804785e-07]
- Mean state counts across refits: [5755.0, 5755.0, 5756.0, 5754.0, 5756.0]

## Artifacts
- `research/forecasts/h1_markov_chain_validation_quantile_k5_results.json`
- `research/forecasts/h1_markov_chain_validation_quantile_k5_forecasts.csv`
- `research/forecasts/figures/h1_markov_chain_validation_quantile_k5_next_state_probs.png`
- `research/forecasts/figures/h1_markov_chain_validation_quantile_k5_pit_hist.png`

## Interpretation notes
- Validation-only H1 groundwork; not a trading backtest and not a final holdout evaluation.
- Discretization method and state count are hyperparameters; sensitivity to these should be evaluated.
- Realized Markov states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison.
