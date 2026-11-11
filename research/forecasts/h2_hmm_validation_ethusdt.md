# H2 Walk-forward Filtered HMM Forecast Validation (ETHUSDT 1h — asset perturbation robustness)

**Generated:** 2026-11-11T04:28:49.616360+00:00
**Symbol/Freq:** ETHUSDT / 1h
**Validation window:** 2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00 (holdout >= 2024-07-01 00:00:00+00:00 excluded)
**Model:** 3-state Gaussian HMM (diag), states ordered by mean; refit every 720 bars on expanding history; eval_stride=4; seeds=[0, 1, 2]

## Purpose
- Asset-perturbation robustness check of the C1 filtered-HMM candidate on ETHUSDT 1h over the same validation grid as BTCUSDT.
- Validation-only; not a trading backtest and not a final holdout evaluation. No holdout used; no config tuning on any outcome.

## Scope and leakage controls
- Expanding fit uses ETHUSDT returns up to time *t* only; forecast targets *t+1* in validation window.
- Filtered probabilities computed via forward algorithm on history up to *t*; no smoothed/Viterbi full-sample decoding used for forecasts.
- Locked holdout period (>= 2024-07-01) not used for fitting, selection, or evaluation.

## Baselines
- **Unconditional Gaussian:** expanding mean/variance of historical ETHUSDT returns up to *t*.
- **EWMA Gaussian (RiskMetrics-style):** expanding mean with EWMA variance (lambda=0.94) on demeaned returns up to *t*.

## Forecast metrics (validation)
Observations: 1087 | Refits: 7

### Log score (mean, higher is better)
- hmm_mixture: 3.786546 (median 4.010690)
- unconditional_gaussian: 3.530783 (median 3.743450)
- ewma_gaussian: 3.651098 (median 4.038874)

### CRPS (mean, lower is better)
- hmm_mixture: 3.252190e-03 (median 2.072020e-03)
- unconditional_gaussian: 3.583067e-03 (median 2.471743e-03)
- ewma_gaussian: 3.260433e-03 (median 2.061837e-03)

### Calibration diagnostic
- HMM mixture PIT mean=0.5069635305390694 std=0.274851674726682 (ideal uniform: mean 0.5, std ~0.289)

## Artifacts
- `research/forecasts/h2_hmm_validation_ethusdt_results.json`
- `research/forecasts/h2_hmm_validation_ethusdt.csv`
- `research/forecasts/figures/h2_next_state_probs_ethusdt.png`
- `research/forecasts/figures/h2_pit_hist_ethusdt.png`

## Interpretation notes
- Compare against BTCUSDT validation (research/forecasts/h2_hmm_validation_results.json): HMM log score 4.01643, CRPS 0.00259686; EWMA log score 3.90220, CRPS 0.00263060.
- A material drop in ETHUSDT log score/CRPS relative to BTCUSDT would indicate the HMM edge is symbol-specific, not robust across assets.
