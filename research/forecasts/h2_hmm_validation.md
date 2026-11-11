# H2 Walk-forward Filtered HMM Forecast Validation (BTCUSDT 1h)

**Generated:** 2026-11-11T01:36:35.383116+00:00
**Symbol/Freq:** BTCUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 3-state Gaussian HMM (diag), states ordered by mean; refit every 720 bars on expanding history; eval_stride=4; seeds=[0, 1, 2]

## Scope and leakage controls
- Expanding fit uses returns up to time *t* only; forecast targets *t+1* in validation window.
- Filtered probabilities computed via forward algorithm (`score_samples`/forward posterior) on history up to *t*; no smoothed/Viterbi full-sample decoding used for forecasts.
- Locked holdout period (>= 2024-07-01) not used for fitting, selection, or evaluation in this run.

## Baselines
- **Unconditional Gaussian:** expanding mean/variance of historical returns up to *t*.
- **EWMA Gaussian (RiskMetrics-style):** expanding mean with EWMA variance (lambda=0.94) on demeaned returns up to *t*.

## Forecast metrics (validation)
Observations: 1087 | Refits: 7

### Log score (mean, higher is better)
- hmm_mixture: 4.016432 (median 4.261447)
- unconditional_gaussian: 3.770382 (median 3.987600)
- ewma_gaussian: 3.902195 (median 4.193351)

### CRPS (mean, lower is better)
- hmm_mixture: 2.596856e-03 (median 1.640606e-03)
- unconditional_gaussian: 2.853621e-03 (median 1.928974e-03)
- ewma_gaussian: 2.630603e-03 (median 1.707313e-03)

### State-probability diagnostic (model-dependent realized state)
- Realized state is argmax filtered prob at t+1 under each refit model; diagnostic only, not ground truth.
- Brier (next-state, diagnostic): 0.229344
- Log loss (next-state, diagnostic): 0.421971

### Calibration diagnostic
- HMM mixture PIT mean=0.5104984105264514 std=0.269660028727823 (ideal uniform: mean 0.5, std ~0.289)

## Refitting stability / regime occupancy proxy
- Refits: 7
- Mean occupancy proxy across refits: [0.08818334159388372, 0.48516185383615845, 0.426654804569958]
- Occupancy proxy std across refits: [0.001084737208056562, 0.0033168810507717885, 0.002342667380926817]
- State mean estimates mean across refits: [-0.0004653136383011773, 9.791534677459225e-06, 0.00014105033427299553]
- State mean estimates std across refits: [2.9067191861646824e-05, 4.308271282703458e-06, 5.652436837482035e-06]

## Artifacts
- `research/forecasts/h2_hmm_validation_results.json`
- `research/forecasts/h2_validation_forecasts.csv`
- `research/forecasts/figures/h2_next_state_probs.png`
- `research/forecasts/figures/h2_pit_hist.png`

## Interpretation notes
- Validation-only H2 groundwork; not a trading backtest and not a final holdout evaluation.
- Non-stationarity observed in prior EDA (Chow tests) may affect parameter/refit stability; see refit summaries.
- Realized HMM states are model-dependent diagnostics, not observable ground truth; proper scoring on return distribution is the primary comparison here.
