# Agent handoff

**Repository:** `takenthatusernameis-collab/QUANT-MARKOV-PROCESS`
**Branch:** `main`
**Current phase:** `DISCOVERY_AND_METHOD_DESIGN` (validation-only cycle closed)
**Status:** `COMPLETE`
**Updated:** 2026-11-11 (session: prior task read and completed — **independently re-verified in this live environment** (`data/` present, all deps present); T5d-robustness-c artifacts, `research/final_decision_report.md`, and `AGENT_STOP` all present; holdout runner refused by default EXIT 2 (protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`); `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.19s**; decision remains `RESEARCH_MORE`; **no holdout executed, no new research task started, handoff/next-agent message refreshed**)

## Mission

Determine whether Markov-process-based representations can produce a statistically robust, executable-after-costs predictive edge in liquid cryptocurrency markets. The mandate is research-only. There is no approved live-trading or deployment path.

## Completed work

### Files created / updated (prior sessions)

1. `research/literature/markov-processes-in-finance.md` (575 lines) — Sourced literature and methodology review covering all six model families.
2. `research/specifications/initial-research-plan.md` (353 lines) — Falsifiable research plan with testable hypotheses, data contracts, validation protocol, and go/no-go criteria.
3. `src/data_ingestion.py` — Downloads Binance USDT-M perpetual klines (15m, 1h, 4h, 1d), funding rates (8h) from public S3; runs quality checks; writes manifest.json and features.parquet.
4. `tests/test_data_ingestion.py` — Automated verification of manifest, file hashes, row counts, date ranges, quality checks, and feature matrix.
5. `data/raw/manifest.json` — 10 entries with SHA256 hashes, row counts, date ranges, source URLs.
6. `data/processed/features.parquet` — 87,648 rows aligned to 1h base frequency with OHLCV, funding rate, and derived features.

### Task T2 completed (prior session): EDA & regime labeling (BTCUSDT 1h)

**Files created / modified**
- `src/eda_regime_analysis.py` — fixed for installed `hmmlearn` API (log-likelihood extraction via `model.score`, diagonal-covariance reorder via internal `_covars_`, robust std/log-likelihood reporting) and clarified that the plotted diagnostic is a posterior-vs-MAP proxy (not a true online filtered-vs-smoothed gap). Script now runs end-to-end on `data/processed/features.parquet`.
- `research/eda/regime_analysis.md` — EDA/regime report (training/validation/holdout split summary, HMM estimates, regime stats, transitions, sojourns, stationarity tests, diagnostics, figures index, implications).
- `research/eda/regime_analysis_results.json` — machine-readable results.
- `research/eda/hmm_model_train.pkl` — fitted 3-state Gaussian HMM (trained on BTCUSDT 1h returns through 2023-12-31, states ordered by mean return).
- `research/eda/figures/` — 11 figures (state time series train/full, transition heatmaps train/model/full, sojourn summaries train/full, regime return distributions train/full, posterior-vs-MAP diagnostic, rolling occupancy).

**Data / split (BTCUSDT 1h, from aligned features)**
- Total aligned rows: 87,648 (2021-01-01 00:00:00+00:00 to 2025-12-31 23:00:00+00:00); BTCUSDT full returns used: 43,823.
- Train: 26,256 returns (2021-01-01 00:00:00+00:00 to 2023-12-31 00:00:00+00:00).
- Validation: 4,344 returns (2024-01-01 00:00:00+00:00 to 2024-06-30 00:00:00+00:00).
- Holdout (locked, not analyzed beyond split metadata): 13,176 returns (2024-07-01 00:00:00+00:00 to 2025-12-31 23:00:00+00:00).

**Key findings (training period, 3-state Gaussian HMM, μ₁ < μ₂ < μ₃ constraint)**
- Model fit (multi-seed best): log-likelihood 100885.83. Means ≈ [-5.02e-4, 2.78e-6, 1.35e-4] with small diagonal variances as reported in `regime_analysis_results.json`/report.
- Regime-conditional moments (Viterbi path, train): State 0 (6.1%, 1603 obs) mean -0.000858, std 0.021087 (high-vol/negative tail); State 1 (49.2%, 12931) mean -0.000015, std 0.002494 (low-vol/near-zero); State 2 (44.6%, 11722) mean 0.000166, std 0.006747 (positive/moderate-vol).
- Persistence/sojourns (train): mean durations 5.1h (S0), 30.1h (S1), 17.1h (S2); empirical persistence 0.805/0.967/0.942. Model and empirical transition matrices saved in results.
- Stationarity (Chow-type LR on transition matrices): train first-half vs second-half LR=307.25 (df=6), p=0.0, reject constant matrix; train vs validation LR=18.97 (df=6), p=0.0042, reject. Evidence of regime/transition instability across periods.
- Posterior-vs-MAP diagnostic (proxy, not true online filtered-vs-smoothed): mean gap 0.1493, max 0.6012 — indicates material state uncertainty; true forward-only filtered inference must be implemented and evaluated in T4.

**Caveats / methodology notes**
- `hmmlearn` EM runs emitted "Model is not converging" warnings for some seeds; best-seed selection used. Convergence sensitivity and initialization robustness remain open (relevant to A4).
- Probabilities decoded via full-sequence `predict_proba`/`decode` in this EDA are not online-filtered forecasts; T4 must use expanding/rolling fit with forward (filtered) probabilities at decision time only.
- Holdout period was not used for fitting or evaluation.

### Task T4 completed (prior session): Walk-forward filtered HMM forecast validation (BTCUSDT 1h, validation only)

**Files created / modified**
- `src/hmm_walkforward.py` — expanding walk-forward pipeline: loads BTCUSDT 1h returns from `data/processed/features.parquet`; fits 3-state Gaussian HMM on history up to *t* only (multi-seed best log-likelihood, states ordered by mean μ₁<μ₂<μ₃); produces 1-step-ahead **filtered** state probabilities via forward posterior (`score_samples`) and mixture conditional return forecast for *t+1*; evaluates targets in validation window 2024-01-01 to 2024-06-30 only; holdout (>=2024-07-01) excluded by construction. Baselines: expanding unconditional Gaussian and EWMA Gaussian (RiskMetrics-style, λ=0.94). Reports log score, CRPS (grid CDF integration), PIT calibration diagnostic, model-dependent next-state Brier/log-loss diagnostic, and refit stability/occupancy summaries. Includes `eval_stride` and configurable refit cadence for bounded runtime.
- `tests/test_hmm_walkforward.py` — tests for ordered state means, filtered posterior simplex/shape, one-step transition forecast consistency, expanding-baseline no-future behavior, and validation-only/no-holdout leakage with bounded runtime config.
- `research/forecasts/h2_hmm_validation.md` — validation report (scope/leakage controls, metrics, baselines, refit stability, caveats).
- `research/forecasts/h2_hmm_validation_results.json` — machine-readable config, metrics, refit records, and samples.
- `research/forecasts/h2_validation_forecasts.csv` — per-forecast rows (timestamps, realized returns, HMM state probs, HMM/unc/EWMA moments).
- `research/forecasts/figures/h2_next_state_probs.png`, `research/forecasts/figures/h2_pit_hist.png`.

**Bounded run configuration used for saved artifacts** (runtime/convergence tradeoff; not holdout-tuned): `refit_every=720`, `seeds=[0,1,2]`, `eval_stride=4` over validation targets. EM emitted non-fatal "Model is not converging" warnings on some refits/seeds; best-seed selection by training log-likelihood applied per refit.

**Validation metrics (1,087 scored forecasts, 7 refits)**
- Log score mean (higher better): HMM mixture 4.01643 vs unconditional Gaussian 3.77038 vs EWMA Gaussian 3.90220.
- CRPS mean (lower better): HMM mixture 0.00259686 vs unconditional Gaussian 0.00285362 vs EWMA Gaussian 0.00263060.
- HMM PIT mean/std: 0.5105 / 0.2697 (uniform ideal ~0.5 / 0.289).
- Model-dependent next-state diagnostic (argmax filtered prob at *t+1* under refit model, not ground truth): Brier 0.22934, log loss 0.42197.
- Refit occupancy proxy mean [S0,S1,S2]=[0.0882, 0.4852, 0.4267] with small std across refits; state means varied modestly across refits (see JSON/report).

**Caveats / interpretation**
- Validation-only H2 groundwork; **not** a trading simulation and **not** a locked-holdout evaluation. Differences vs baselines are point estimates on the sampled validation grid (stride 4) and do **not** yet include block-bootstrap significance/FDR or sensitivity sweeps required by the research plan/gates.
- Prior EDA showed train-vs-validation transition non-stationarity (Chow p=0.0042); EM convergence/init sensitivity persists and may affect refit stability and forecast comparability.
- "Unconditional historical transition distribution" baseline is not yet implemented as a discrete-state Markov baseline in this run; unconditional/EWMA Gaussian return-distribution baselines were used for proper scoring.

### Task T4b completed (prior session): Block-bootstrap uncertainty and sensitivity for validation forecast scores (validation only)

**Files created / modified**
- `src/hmm_validation_significance.py` — block bootstrap analysis script using stationary bootstrap (Politis & Romano 1994) with n^(1/3) block length, 2000 replications. Computes paired score differences (HMM vs Unconditional, HMM vs EWMA) for log score and CRPS using Gaussian mixture scores from saved forecasts. Reports mean differences, 95% percentile CIs, two-sided p-values, effective sample sizes. Includes bounded sensitivity check (narrower validation sub-window Jan-Mar 2024, refit_every=1440, eval_stride=8).
- `tests/test_hmm_validation_significance.py` — 10 tests for bootstrap helpers: index generation determinism, shape/range checks, constant/auto block length, CI structure, significance detection, effective sample size reasonableness, no-future-leakage verification.
- `research/forecasts/h2_hmm_validation_significance.json` — machine-readable bootstrap results, sensitivity check deltas, T4 config echo.
- `research/forecasts/h2_hmm_validation_significance.md` — markdown report with methodology, results, interpretation notes.
- `research/forecasts/figures/h2_bootstrap_diffs.png` — histograms of paired differences with mean/zero lines.

**Bootstrap results (validation period, 1,087 forecasts, stride 4, block length ≈10.3)**

| Metric | Comparison | Mean Diff | 95% CI | p-value | Eff. n | Significant (5%) |
|--------|-----------|-----------|--------|---------|--------|------------------|
| Log score (↑ better) | HMM vs Unconditional | +0.1518 | [+0.1104, +0.1906] | 0.0000 | 677 | **Yes** (HMM better) |
| Log score (↑ better) | HMM vs EWMA | +0.01995 | [-0.0293, +0.0728] | 0.4365 | 1170 | No |
| CRPS (↓ better, diff = base - HMM) | HMM vs Unconditional | +1.78e-4 | [+1.34e-4, +2.19e-4] | 0.0000 | 576 | **Yes** (HMM better) |
| CRPS (↓ better, diff = base - HMM) | HMM vs EWMA | -4.54e-5 | [-7.63e-5, -1.20e-5] | 0.0060 | 633 | **Yes** (EWMA better) |

**Interpretation:**
- HMM significantly outperforms unconditional Gaussian on both log score and CRPS (p < 0.001).
- HMM does **not** significantly outperform EWMA Gaussian on log score (p = 0.44).
- EWMA Gaussian significantly outperforms HMM on CRPS (p = 0.006).
- Effective sample sizes (576–1170) are well below nominal n=1087 due to temporal dependence in score differences.
- Results use Gaussian approximation of HMM mixture (state-level mixture CRPS not available in saved CSV); this is a limitation.

**Sensitivity check (Jan–Mar 2024 sub-window):**
- Main config (refit_every=720, eval_stride=4): log_score=3.924, CRPS=0.002848, 541 forecasts, 4 refits
- Sensitivity config (refit_every=1440, eval_stride=8): log_score=3.865, CRPS=0.002995, 271 forecasts, 2 refits
- Deltas: log_score -0.059, CRPS +1.47e-4 (main config better on both metrics)
- Metrics are moderately sensitive to refit cadence and evaluation stride; not tuned on holdout.

**Caveats / blockers**
- Non-fatal EM "Model is not converging" warnings persist on some refits/seeds (same as T4).
- Train-vs-validation non-stationarity (Chow p=0.0042) from T2 remains a concern for parameter stability.
- Saved forecast CSV lacks state-level mixture parameters; bootstrap used Gaussian approximation of mixture moments.
- Validation-only results; holdout (>=2024-07-01) not used.

### Task T3 completed (this session): Finite-state Markov chain baseline (BTCUSDT 1h, validation only)

**Files created / modified**
- `src/markov_chain_baseline.py` — first-order finite-state Markov chain baseline: quantile-bin discretization (K=5) fitted on training returns only (<=2023-12-31), expanding transition-count estimation with Laplace smoothing, 1-step-ahead state probabilities and state-mixture return forecast for target *t* using history up to *t-1*; baselines unconditional expanding Gaussian and EWMA Gaussian (λ=0.94); log score/CRPS (mixture via grid integration), PIT, and stationary block-bootstrap significance (2000 reps, n^(1/3) block). Validation window 2024-01-01 to 2024-06-30 only; holdout (>=2024-07-01) excluded.
- `tests/test_markov_chain_baseline.py` — tests for quantile-bin determinism/range, state assignment, transition-count/probability validity (row-stochastic, smoothed), state-conditional fallback behavior, expanding-baseline no-future behavior, and validation-only/no-holdout walk-forward with bounded runtime config.
- `research/forecasts/h1_markov_chain_validation.json` — machine-readable config, metrics, bootstrap comparisons, and metadata.
- `research/forecasts/h1_markov_chain_validation.md` — markdown report.
- `research/forecasts/h1_markov_chain_validation.csv` — per-forecast rows (timestamps, realized returns, current state, next-state probabilities, MC/unc/EWMA moments).
- `research/forecasts/figures/h1_mc_next_state_probs.png`, `research/forecasts/figures/h1_mc_pit_hist.png`.

**Run configuration (bounded, not holdout-tuned):** K=5 quantile states, `eval_stride=4`, expanding refit per evaluated step (transition/state-conditional parameters from all history < target), Laplace α=1.0.

**Validation metrics (1,087 forecasts, stride 4)**
- Log score mean (higher better): MC mixture 3.82976 vs unconditional Gaussian 3.74821 vs EWMA Gaussian 3.90424.
- CRPS mean (lower better): MC mixture 0.00270785 vs unconditional Gaussian 0.00290269 vs EWMA Gaussian 0.00267385.
- MC PIT mean/std: 0.4988 / 0.2788.
- State occupancy at forecast times: [0.1849, 0.2263, 0.2052, 0.2061, 0.1776].

**Block-bootstrap significance (stationary bootstrap, 2000 reps, block length ≈10.28, validation grid)**
- Log score (MC − baseline, higher better): MC vs unconditional +0.08155, 95% CI [+0.00791, +0.15577], p=0.032, eff_n=558, significant@5% (MC better). MC vs EWMA −0.07447, 95% CI [−0.14881, +0.00591], p=0.060, eff_n=979, not significant.
- CRPS (baseline − MC, lower better): MC vs unconditional +1.948e-4, 95% CI [+1.407e-4, +2.475e-4], p=0.000, eff_n=366, significant@5% (MC better). MC vs EWMA −3.400e-5, 95% CI [−6.606e-5, −1.743e-6], p=0.039, eff_n=882, significant@5% (EWMA better).

**Caveats / interpretation**
- Validation-only H1 baseline; not a trading simulation and not a locked-holdout evaluation. Point estimates/significance are on the sampled validation grid (stride 4) and do not constitute final evidence.
- Discretization choice (K=5 quantiles, train-fitted edges) and Laplace smoothing affect forecasts; sensitivity across K/binning methods is not exhaustively re-swept in this run (other pre-existing H1 k-means/quantile artifacts exist under `research/forecasts/` from prior work but were not consolidated here).
- Direct aligned MC-vs-HMM mixture scoring was not fully computed against HMM state-mixture parameters because saved T4 CSV stores HMM mixture moments only; any moment-based comparison should be interpreted cautiously.
- Prior project-level caveats remain: EM convergence warnings in HMM fits and train-vs-validation transition non-stationarity (Chow p=0.0042).

### Task T3b completed (this session): H1 Markov chain sensitivity consolidation (validation only)

**Files created / modified**
- `research/forecasts/h1_mc_sensitivity_consolidation.md` — consolidation report comparing all 7 H1 configurations (canonical T3 Q5 expanding per-step + 6 legacy configs: quantile K=3,5,7 and k-means K=3,5,7) on log score, CRPS, PIT, and block-bootstrap significance.
- `research/forecasts/h1_mc_sensitivity_consolidation.json` — machine-readable consolidation data.
- `src/verify_h1_consolidation.py` — verification script that loads all artifacts and regenerates comparison tables.

**Configurations audited (all validation-only, BTCUSDT 1h, train ≤2023-12-31, val 2024-01 to 2024-06, holdout ≥2024-07 excluded):**
| Config | Discretization | K | Refit | Log Score (MC) | CRPS (MC) | vs Unc (log) | vs EWMA (log) |
|--------|---------------|---|-------|----------------|-----------|--------------|---------------|
| Canonical T3 | Quantile (train edges) | 5 | Expanding/step | 3.8298 | 0.002708 | **+0.0816** (p=0.032) | −0.0745 (p=0.060) |
| Legacy Q3 | Quantile | 3 | refit_every=720 | 3.7892 | 0.002755 | +0.00007 (p=0.985) | −0.1317 (p=0.000) |
| Legacy Q5 | Quantile | 5 | refit_every=720 | 3.8390 | 0.002685 | +0.0117 (p=0.116) | −0.1201 (p=0.000) |
| Legacy Q7 | Quantile | 7 | refit_every=720 | 3.8569 | 0.002683 | −0.0001 (p=0.994) | −0.1319 (p=0.000) |
| Legacy KM3 | K-means | 3 | refit_every=720 | **3.9319** | **0.002654** | **+0.0228** (p=0.020) | −0.1090 (p=0.0005) |
| Legacy KM5 | K-means | 5 | refit_every=720 | 3.9217 | 0.002677 | +0.0138 (p=0.502) | −0.1180 (p=0.0005) |
| Legacy KM7 | K-means | 7 | refit_every=720 | 3.9012 | 0.002672 | −0.0056 (p=0.738) | −0.1374 (p=0.0005) |

**Key findings:**
- K-means K=3 (Legacy KM3) achieves highest log score (3.9319) and lowest CRPS (0.002654); significantly beats unconditional on both (log p=0.020, CRPS p=0.035) but **significantly worse than EWMA on both** (log p=0.0005, CRPS p=0.000).
- Canonical T3 (Q5, expanding per-step): significantly beats unconditional on both (log p=0.032, CRPS p=0.000); does not significantly differ from EWMA on log score (p=0.060); EWMA significantly better on CRPS (p=0.039).
- Quantile binning: monotonic log score improvement with K (3→5→7) but no config significantly beats EWMA; all lose to EWMA on CRPS.
- EWMA Gaussian (λ=0.94) remains a strong baseline: never significantly beaten by any MC config on log score; significantly beats most on CRPS.
- T4 HMM (filtered, validation) outperforms all MC configs: log score 4.0164, CRPS 0.002597.

**Leakage controls (all configs):** Bin edges/centroids fitted on training only (≤2023-12-31); expanding history for transitions/state-conditionals; validation window strictly 2024-01 to 2024-06; holdout excluded by construction.

**Verification:** `PYTHONPATH=. python src/verify_h1_consolidation.py` regenerates all tables from saved artifacts. `PYTHONPATH=. python -m pytest -q` → 70 passed.

**Caveats:** Validation-only; no holdout tuning; legacy artifacts have separate provenance; canonical T3 bootstrap uses Gaussian approximation of MC mixture; effective sample sizes 366–1183 due to temporal dependence.

### Task T3c completed (prior session): Higher-order / state-augmented Markov chain baseline (validation only)

**Files created / modified**
- `src/higher_order_markov.py` — second-order Markov chain baseline: state pair X_t = (S_{t-1}, S_t) in {0..K-1}^2 (K^2=25 pairs for K=5); quantile-bin discretization fitted on training data only (<=2023-12-31); expanding transition counts P(S_t=j | S_{t-2}=a, S_{t-1}=b) with Laplace smoothing (alpha=1.0); pair-conditional Gaussian return distributions E[r_t | (S_{t-1}, S_t)=(b, j)]; 1-step-ahead filtered state probabilities and pair-mixture return forecast for target t using history up to t-1 only. Baselines: unconditional expanding Gaussian and EWMA Gaussian (lambda=0.94). Metrics: log score, CRPS (mixture via grid integration), PIT, stationary block-bootstrap significance (2000 reps, n^(1/3) block). Validation window 2024-01-01 to 2024-06-30 only; holdout (>=2024-07-01) excluded. Aligned comparison vs saved H1 canonical (Q5 expanding) mixture on identical timestamps and vs saved HMM (T4) where grids align.
- `tests/test_higher_order_markov.py` — tests for bin determinism/range, state assignment, order-2 transition-count/shape and row-stochasticity, pair-conditional fallback, expanding-unconditional no-future, and validation-only/no-holdout walk-forward with bounded runtime config.
- `research/forecasts/h3_higher_order_markov_validation.json` — machine-readable config, metrics, bootstrap comparisons (incl. aligned H1), metadata.
- `research/forecasts/h3_higher_order_markov_validation.md` — markdown report.
- `research/forecasts/h3_higher_order_markov_validation.csv` — per-forecast rows (timestamps, realized returns, s_prev/s_curr, next-state probs, pair-conditional moments, HOM/unc/EWMA moments).
- `research/forecasts/figures/h3_hom_next_state_probs.png`, `research/forecasts/figures/h3_hom_pit_hist.png`.

**Run configuration (bounded, not holdout-tuned):** order m=2, K=5 quantile states (train edges), 25 state-pairs, `eval_stride=4`, expanding refit per evaluated step, Laplace alpha=1.0, min pair samples 20 with global fallback.

**Validation metrics (1,087 forecasts, stride 4)**
- Log score mean (higher better): HOM mixture 3.85845 vs unconditional Gaussian 3.74821 vs EWMA Gaussian 3.90424.
- CRPS mean (lower better): HOM mixture 0.002687 vs unconditional Gaussian 0.002903 vs EWMA Gaussian 0.002674.
- HOM PIT mean/std: 0.4993 / 0.2799 (uniform ideal ~0.5 / 0.289).
- Pair occupancy spread across all 25 pairs (min ~0.024, max ~0.055), no fully empty pairs at forecast times.

**Block-bootstrap significance (stationary bootstrap, 2000 reps, block length ≈10.28, validation grid)**
- Log score (HOM − baseline, higher better): HOM vs unconditional +0.1102, 95% CI [+0.0370, +0.1814], p=0.002, eff_n=685, significant@5% (HOM better). HOM vs EWMA −0.0458, 95% CI [−0.1148, +0.0259], p=0.21, eff_n=1020, not significant.
- CRPS (baseline − HOM, lower better): HOM vs unconditional +2.15e-4, 95% CI [+1.61e-4, +2.70e-4], p=0.000, eff_n=435, significant@5% (HOM better). HOM vs EWMA −1.36e-5, 95% CI [−4.50e-5, +1.86e-5], p=0.41, eff_n=901, not significant.

**Aligned comparison with H1 (first-order MC, saved canonical grid, 1,087 identical timestamps)**
- Log score (HOM − H1): +0.0287, 95% CI [+0.0124, +0.0455], p=0.001, eff_n=1310, significant@5% (HOM better).
- CRPS (H1 − HOM): +2.04e-5, 95% CI [+6.2e-6, +3.53e-5], p=0.004, eff_n=1000, significant@5% (HOM better).
- HOM improves on H1 on both metrics; HOM is the best Markov-chain (non-latent) configuration on validation.

**Aligned comparison with HMM (T4): not computed**
- The saved HMM forecast grid (h2_validation_forecasts.csv) is offset by one hour (01:00, 05:00, ...) relative to the H1/H3 grid (00:00, 04:00, ...), so direct timestamp alignment would pair mismatched realized-return targets and was not computed. H2 reference metrics from the T4 report: log score 4.0164, CRPS 0.002597 — HMM remains the best model on validation.

**Caveats / interpretation**
- Validation-only H1-family baseline; not a trading simulation and not a locked-holdout evaluation. Point estimates/significance are on the sampled validation grid (stride 4).
- Order m=2 and K=5 quantile bins are design choices; state space K^2=25 with sparse pairs handled via Laplace smoothing + global-moment fallback.
- EWMA Gaussian remains a strong baseline: HOM not significantly different from EWMA on log score (p=0.21) or CRPS (p=0.41); EWMA CRPS point estimate marginally lower (0.002674 vs 0.002687).
- Prior project-level caveats remain: EM convergence warnings in HMM fits, train-vs-validation transition non-stationarity (Chow p=0.0042).

**Verification (prior):** `PYTHONPATH=. python src/higher_order_markov.py` regenerated artifacts; `PYTHONPATH=. python -m pytest -q` → 76 passed.

### Task T3d completed (prior session, verified): Semi-Markov / duration-dependent Markov chain baseline (validation only)

**Files present**
- `src/semi_markov_baseline.py` — semi-Markov chain baseline: K=5 quantile states (bin edges fitted on training returns only, <=2023-12-31); expanding embedded transition counts/probabilities with Laplace smoothing; expanding sojourn distributions per state (negative binomial, geometric fallback for sparse states); hazard-based 1-step-ahead state probabilities given current state and run duration at decision time *t-1*; state-mixture Gaussian return forecast for target *t* using expanding state-conditional moments. Baselines: unconditional expanding Gaussian and EWMA Gaussian (λ=0.94). Validation 2024-01-01 to 2024-06-30 only; holdout >=2024-07-01 excluded.
- `tests/test_semi_markov_baseline.py` — tests for bin determinism/range, state assignment, sojourn extraction/fitting shapes/fallbacks, hazard/transition probability stochasticity/bounds, transition counts/probabilities, state-conditional fallback, expanding-unconditional no-future, and validation-only/no-holdout walk-forward with bounded runtime config.
- `research/forecasts/h4_semi_markov_validation.json` — machine-readable config, metrics, bootstrap comparisons (incl. aligned H1/H3), metadata.
- `research/forecasts/h4_semi_markov_validation.md` — markdown report.
- `research/forecasts/h4_semi_markov_validation.csv` — per-forecast rows.
- `research/forecasts/figures/h4_sm_next_state_probs.png`, `research/forecasts/figures/h4_sm_pit_hist.png`, `research/forecasts/figures/h4_sm_duration_hist.png`.

**Run configuration (bounded, not holdout-tuned):** K=5, `eval_stride=4`, expanding refit per evaluated step, Laplace α=1.0, negative-binomial sojourns (geometric fallback), max_sojourn=200.

**Validation metrics (1,087 forecasts, stride 4)**
- Log score mean (higher better): Semi-Markov mixture 3.82976 vs unconditional Gaussian 3.74821 vs EWMA Gaussian 3.90424.
- CRPS mean (lower better): Semi-Markov mixture 0.00270785 vs unconditional Gaussian 0.00290269 vs EWMA Gaussian 0.00267385.
- Semi-Markov PIT mean/std: 0.49885 / 0.27875 (ideal uniform ~0.5 / 0.289).
- Duration at forecast times: mean 1.319h, median 1.0h, max 9h (duration dependence limited on this grid).

**Block-bootstrap significance (stationary bootstrap, 2000 reps, block length ≈10.28, validation grid)**
- Log score (SM − baseline, higher better): SM vs unconditional +0.08155, 95% CI [+0.00791, +0.15578], p=0.032, eff_n=558, significant@5% (SM better). SM vs EWMA −0.07448, 95% CI [−0.14881, +0.00591], p=0.060, eff_n=979, not significant.
- CRPS (baseline − SM, lower better): SM vs unconditional +1.948e-4, 95% CI [+1.407e-4, +2.475e-4], p=0.000, eff_n=366, significant@5% (SM better). SM vs EWMA −3.400e-5, 95% CI [−6.606e-5, −1.745e-6], p=0.039, eff_n=882, significant@5% (EWMA better).

**Aligned comparisons (saved validation grids, 1,087 timestamps)**
- SM vs H1 (canonical first-order MC): log score diff SM−H1 +0.04631, 95% CI [−0.02345, +0.11506], p=0.189, not significant; CRPS diff H1−SM +1.533e-4, 95% CI [+1.074e-4, +1.977e-4], p=0.000 (SM better on CRPS, log-score inconclusive). Note: SM and H1 log/CRPS means are nearly identical in saved metrics, suggesting minimal duration effect with this discretization/stride.
- SM vs H3 (higher-order/HOM): log score diff SM−H3 −0.00508, 95% CI [−0.06878, +0.06085], p=0.88, not significant; CRPS diff H3−SM +1.055e-4, 95% CI [+6.358e-5, +1.440e-4], p=0.000 (SM better on CRPS, log-score inconclusive). H3 remains better than SM on point log score (3.85845 vs 3.82976) but aligned bootstrap on log score is not significant.

**Caveats / interpretation**
- Validation-only H1-family (duration-dependent) baseline; not a trading simulation and not a locked-holdout evaluation. Forecasts on sampled validation grid (stride 4).
- Duration dependence appears weak on this 1h K=5 quantile state space (most run lengths short at stride/sample points); semi-Markov reduces to near-Markov behavior in effect.
- EWMA Gaussian remains a strong baseline (not beaten on log score; significantly better on CRPS). HMM (T4, log score 4.0164, CRPS 0.002597) remains best overall on validation; direct aligned SM-vs-HMM not recomputed here (HMM grid offset noted previously).
- Prior project-level caveats remain: train-vs-validation transition non-stationarity (Chow p=0.0042), EM convergence warnings in HMM fits.

**Verification (prior):** `PYTHONPATH=. python -m pytest -q` → **85 passed**. No holdout evaluation performed.

### Task T5-prep completed (this session): Holdout evaluation & economic simulation gate protocol (no holdout execution)

**Files created**
- `research/specifications/holdout_evaluation_protocol.md` — pre-specified, frozen-pre-execution protocol for locked holdout 2024-07-01 to 2025-12-31 (BTCUSDT 1h). Defines leakage/integrity controls (no holdout tuning/execution, point-in-time expanding refit, filtered-only inference, purge/embargo, no holdout-fitted bins/scalers), validation-evidence summary, and frozen candidates: **C1** filtered 3-state Gaussian HMM (T4 config: K=3 ordered means, multi-seed EM, refit_every=720, eval_stride=4, filtered forward) as primary and **C2** higher-order Markov (H3, order 2, K=5 train-fitted quantiles, expanding counts/Laplace, eval_stride=4) as non-latent comparator. Specifies baselines B1–B5, holdout forecast procedure/uncertainty (stationary block bootstrap, proper scores/CRPS/PIT), economic simulation mapping (edge vs cost with predeclared θ/no-trade, fixed sizing/exposure), base/stress cost model (plan-consistent ~10.6/21.2 bps round-trip, funding from processed data), forecast+economic metrics, gate criteria (H5 thresholds: net Sharpe >0.5, max DD <20%, positive expectancy p<0.1 HAC-aware, >100 trades, turnover <500%, beat best baseline by >0.25 Sharpe), decision mapping (`REJECT`/`RESEARCH_MORE`/`CANDIDATE_FOR_INDEPENDENT_CONFIRMATION`), predeclared robustness/red-team checks, artifact/provenance requirements, and explicit prohibitions (no live trading, no workflow/prompt edits, no smoothed probs, no post-hoc retuning).
- `research/specifications/holdout_evaluation_manifest_template.json` — machine-readable template capturing protocol/data provenance placeholders, frozen C1/C2 configs, baselines, cost model, metrics/uncertainty, gates, and execution fields (`holdout_evaluated: false`, hashes/command/git SHA null) for future recorded runs.

**Selection rationale (validation-only, not holdout-tuned):** C1 chosen as primary on strongest validation log score/CRPS (4.01643 / 0.00259686) and significant improvement vs unconditional, despite EM/non-stationarity caveats and no significant log-score edge vs EWMA; C2 chosen as best non-latent/transparent MC comparator (3.85845 / 0.002687) beating H1/H4 on key aligned comparisons. EWMA remains a strong baseline (esp. CRPS).

**Verification (this session):** `PYTHONPATH=. python -m pytest -q` → **85 passed in 29.90s** (sanity; no holdout evaluation performed). No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

### Task T5a completed (prior session): Validation-only economic/cost simulation dry-run scaffolding

**Files created / modified**
- `src/economic_simulation.py` — validation-only economic simulation module implementing the H5 economic gate protocol for dry-run on validation data. Includes:
  - `CostModel` dataclass for per-side cost accounting (taker fee, half-spread, slippage in bps)
  - `SimulationConfig` with frozen parameters (theta_bps, notional_fraction, max_gross_exposure, cost_base, cost_stress, funding source, execution convention)
  - Signal-to-action mapping: long if E[r] > θ + c_eff, short if E[r] < -θ - c_eff, flat otherwise (c_eff = cost per side)
  - Fixed fractional sizing with max gross exposure limit
  - Per-bar cost computation: fee/spread/slippage on turnover, funding pro-rata from processed data
  - Gross vs net equity curve simulation with trade tracking and P&L attribution
  - Comprehensive economic metrics: CAGR, vol, Sharpe, Sortino, Calmar, max DD, hit rate, payoff ratio, profit factor, expectancy, tail loss, turnover, holding time, time in market
  - Baseline simulations: B3 (no-trade), B4 (buy-and-hold), B5 (momentum with predeclared lookback)
  - Theta sensitivity sweep (θ ∈ {0, 2, 5} bps), base/stress cost variants
  - Reproducible artifact output under `research/economic/validation_dryrun/`
- `tests/test_economic_simulation.py` — 25 unit tests covering cost model properties, signal generation (threshold logic, no-trade region, theta sensitivity), sizing (notional fraction, max exposure), cost computation (zero turnover, proportional to turnover, funding), equity curve simulation (gross returns, net costs, trade detection), metrics computation (positive/negative returns, empty), funding alignment (forward fill), baseline simulations (no-trade, buy-hold, momentum), no-lookahead integration, gross vs net accounting separation.
- `research/economic/validation_dryrun/validation_dryrun_results.json` — machine-readable results for C1 (HMM) and C2 (HOM) across theta/cost combinations.
- `research/economic/validation_dryrun/validation_dryrun_report.md` — markdown summary report with configuration, results tables, baseline comparison, and gate criteria assessment.
- `research/economic/validation_dryrun/*_trades.csv` — per-configuration trade ledgers (empty in this run due to no trades generated).

**Run configuration (frozen, validation-only):** theta_bps ∈ {0.0, 2.0, 5.0}, notional_fraction=0.10, max_gross_exposure=1.0, cost_base={taker_fee_bps=5.0, half_spread_bps=1.0, slippage_bps=2.0} (8 bps/side, 16 bps round-trip), cost_stress={10.0, 2.0, 4.0} (16 bps/side, 32 bps round-trip), funding from `data/processed/features.parquet`, validation period 2024-01-01 to 2024-06-30.

**Key findings (validation dry-run, 1,087 forecasts per model):**
- **No trades generated** for either C1 (HMM) or C2 (HOM) under any theta/cost configuration.
- Forecast conditional means are too small to exceed cost thresholds: C1 max |μ| ≈ 3.17 bps, C2 max |μ| ≈ 6.79 bps; base cost threshold = 8 bps/side (θ=0); stress threshold = 16 bps/side.
- Baselines: B3 (no-trade) Sharpe=0.0; B4 (buy-hold) Sharpe=2.21 (C1 grid) / 1.70 (C2 grid); B5 (momentum, 24h lookback) Sharpe=10.76 / 10.76 with 127 trades.
- Gate criteria assessment (validation dry-run): Both C1 and C2 fail net Sharpe >0.5, positive expectancy, and trade count >100; both pass max DD <20% and turnover <500% (vacuously, zero trades).

**Interpretation:** The validation-period forecasts do not produce sufficient predictive edge to overcome conservative transaction costs at the 1h horizon. This is consistent with the forecast validation results where HMM beats unconditional but not EWMA on log score, and EWMA beats HMM on CRPS. The dry-run correctly reflects that statistical forecast skill (proper scores) does not directly translate to economic profitability after costs.

**Caveats / limitations:**
- Cost model uses explicit per-side accounting (16 bps round-trip base) per protocol; plan §8.2 cites ≈10.6 bps aggregate convention — sensitivity to lower costs not explored in this dry-run.
- Theta sensitivity only tested at {0, 2, 5} bps; negative theta (subsidized trading) not tested per protocol.
- Validation-period only; holdout not evaluated. Results do not constitute evidence for/against candidates.
- Momentum baseline (B5) achieves high Sharpe but with only 127 trades over 6 months; not directly comparable to model-based strategies which had zero trades.
- Funding costs applied pro-rata from historical series; minimal impact at zero trade count.

**Verification (prior session):**
- `PYTHONPATH=. python src/economic_simulation.py --theta 0.0 2.0 5.0 --notional-fraction 0.10` — **success**; generated `research/economic/validation_dryrun/` artifacts.
- `PYTHONPATH=. python -m pytest -q` → **110 passed in 29.70s** (85 prior + 25 new economic simulation tests)
- No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

### Task T5b completed (prior session): Protocol-enforcing holdout evaluation runner stub (refuses by default)

**Files created / modified**
- `src/holdout_runner.py` — protocol-enforcing holdout runner stub. Loads frozen protocol (`research/specifications/holdout_evaluation_protocol.md`) and manifest template (`research/specifications/holdout_evaluation_manifest_template.json`), computes/verifies protocol SHA256, and **refuses execution by default** unless `--execute-holdout` and matching `--protocol-hash` are provided. Enforces integrity controls (point-in-time/no-lookahead, holdout-window, expanding history, filtered-only C1, train-fitted C2 bins) and frozen configs.
- `tests/test_holdout_runner.py` — 12 unit tests covering refusal/hash/no-lookahead/manifest behavior.

**Verification:** `PYTHONPATH=. python src/holdout_runner.py` refused (EXIT 2); protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`; suite was 122 passed at T5b close. **Holdout not executed.**

### Task T5c completed (prior session): Extend authorized holdout runner with forecast bootstrap/significance and economic gate artifact wiring (no holdout execution)

**Files created / modified**
- `src/holdout_runner.py` — extended authorized execution path to produce protocol-complete artifact wiring while preserving default refusal and integrity checks:
  - Forecast evaluation: stationary block-bootstrap (n^(1/3), 2000 reps) paired comparisons for C1/C2 vs unconditional and EWMA baselines on log score and CRPS with 95% CIs, two-sided p-values, effective n, plus PIT summary/diagnostics (`holdout_forecast_significance.json`, `holdout_forecast_metrics.json`, `holdout_forecast_report.md`).
  - Economic simulation: integrates `src/economic_simulation.py` primitives (signal/cost/sizing/cost accounting/funding alignment, metrics) on holdout forecast grids for C1/C2 and baselines B3 (no-trade), B4 (buy-hold), B5 (momentum, predeclared lookback) under base/stress costs and theta sensitivity `{0,2,5}` bps; writes trade ledgers, returns series, `holdout_economic_results.json`, and `holdout_economic_report.md` under `research/economic/holdout/`.
  - Execution manifest: populates protocol hash, git SHA, command, timestamps, data hashes, artifact paths, and `holdout_evaluated: true` on authorized runs (`research/forecasts/holdout/holdout_execution_manifest.json`).
  - Refusal/authorization unchanged: requires `--execute-holdout` and matching `--protocol-hash` (expected `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`); point-in-time/no-lookahead, holdout-window, filtered-only C1, train-fitted C2 bins, and frozen configs preserved.
- `tests/test_holdout_runner_t5c.py` — 7 new unit tests (fixtures/mocked small data, no real holdout run): deterministic block-bootstrap significance behavior, paired-comparison output structure (CIs/p-values/effective n/PIT), execution-manifest artifact fields, economic holdout artifact generation on synthetic forecast grids (trade/returns/results/report), and continued refusal/hash enforcement.

**Commands/tests run and outcomes (prior session)**
- `PYTHONPATH=. python -m pytest -q --tb=no 2>&1 | tail -5` (baseline) → **122 passed in 29.77s**.
- `PYTHONPATH=. python -m pytest -q tests/test_holdout_runner.py tests/test_holdout_runner_t5c.py` → **19 passed in 1.58s** (12 existing + 7 new).
- `PYTHONPATH=. python src/holdout_runner.py; echo EXIT:$?` → **refused by default** (`Holdout execution refused: --execute-holdout not provided...`, `EXIT:2`).
- `PYTHONPATH=. python src/holdout_runner.py --print-protocol-hash` → `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`.
- `PYTHONPATH=. python -m pytest -q` → **129 passed in 30.46s** (122 prior + 7 new).

**Caveats / blockers**
- **Holdout not executed** (no explicit authorization provided). Authorized path is wired and unit-tested on fixtures only; real holdout outputs under `research/forecasts/holdout/` and `research/economic/holdout/` do not yet exist and must be generated only with explicit `--execute-holdout` + matching protocol hash.
- Forecast significance in the runner uses Gaussian-approximated PIT/moment-based scoring helpers consistent with saved per-row metrics (not a re-implementation of full mixture CDF PIT plots/figures); figure generation for holdout PIT/histograms remains a follow-up artifact step if required by protocol reporting.
- Purge/embargo is 1-step point-in-time (history < target, 1h horizon); any overlapping/multi-horizon labels require re-verification.
- Prior model caveats remain: HMM EM convergence/init sensitivity and train-vs-validation non-stationarity (Chow p=0.0042); validation dry-run (T5a) showed forecasts did not clear conservative costs at 1h.
- No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

---

### Task T5d completed (this session): Cross-family validation comparison memo (validation-only, no holdout execution)

**Files created**
- `research/forecasts/cross_family_validation_comparison.md` — comprehensive consolidation memo comparing all validation-period model families (H1–H4, HMM, EWMA/unconditional) with:
  - Point-estimate metrics table (log score, CRPS, PIT) across 11 model configurations
  - Block-bootstrap significance results for each family vs unconditional and EWMA baselines
  - Aligned model comparisons (HOM vs H1, SM vs H1/H3, etc.) on identical 1,087-timestamp grid
  - H1 sensitivity summary across 7 configurations (quantile K=3/5/7, k-means K=3/5/7, canonical T3)
  - Calibration (PIT) assessment for all models
  - Economic feasibility summary from T5a dry-run (zero trades, forecast means << cost thresholds)
  - Cross-cutting methodological issues table (non-stationarity, EM convergence, discretization arbitrariness, etc.)
  - Outstanding robustness/red-team checks predeclared in protocol (period/asset/state/cost perturbations, negative controls, FDR)
  - Forecast Validation Gate assessment per plan criteria
  - Economic Simulation Gate projection for holdout (high failure risk given validation results)
  - Recommendations for next steps (validation-only robustness checks, holdout execution conditions, research extensions)
  - Reproducibility index linking all artifacts to generators

**Commands/tests run and outcomes (this session)**
- `PYTHONPATH=. python -m pytest -q` → **129 passed in 30.32s** (all existing tests pass; no new tests added for memo artifact).

**Key consolidated findings:**
- **H2 HMM (filtered, 3-state) dominates** on validation: log score 4.0164, CRPS 0.002597 — significantly beats unconditional on both metrics (p<0.001) but **does not significantly beat EWMA on log score (p=0.44)**; EWMA significantly beats HMM on CRPS (p=0.006).
- **H3 HOM (2nd-order, K=5)** is best non-latent Markov chain: significantly improves on H1 canonical (log score +0.0287, p=0.001; CRPS -2.04e-5, p=0.004) but does not significantly differ from EWMA on either metric.
- **H4 Semi-Markov ≈ H1 Canonical**: near-identical metrics; duration dependence minimal at 1h K=5 stride-4 grid.
- **EWMA Gaussian (λ=0.94) is a strong baseline**: never significantly beaten by any MC config on log score; significantly beats most on CRPS.
- **H1 sensitivity**: K-means K=3 best MC variant but significantly worse than EWMA on both metrics; quantile binning monotonic in K but never beats EWMA.
- **Economic feasibility negative on validation**: max forecast |μ| ≈ 3–7 bps vs 8–16 bps/side cost threshold → zero trades, zero Sharpe for C1/C2.
- **Gate projection**: Both C1 (HMM) and C2 (HOM) likely to fail Economic Simulation Gate on holdout unless holdout regime structure yields substantially larger conditional means.

**No holdout executed.** No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

---

### Task T5d robustness completed (this session): ETHUSDT 1h asset-perturbation validation (no holdout execution)

**Files created / modified**
- `src/hmm_walkforward.py` — generalized `load_btc_returns` into `load_returns(symbol="BTCUSDT")` with backward-compat wrapper; added `symbol` field to `run_walkforward` config payload (default "BTCUSDT", existing BTC artifacts/tests unaffected).
- `src/hmm_walkforward_ethusdt.py` — ETHUSDT 1h walk-forward filtered HMM forecast validation driver: bounded config (refit_every=720, seeds=(0,1,2), eval_stride=4), validation window 2024-01-01 to 2024-06-30 only, holdout (>=2024-07-01) excluded by construction, no holdout tuning. Writes ETHUSDT-named artifacts.
- `tests/test_hmm_walkforward_ethusdt.py` — 4 tests: ETHUSDT symbol-only loading, backward-compat BTC loader, validation-only/no-holdout leakage + metrics + PIT range, expanding-history/no-future.
- `research/forecasts/h2_hmm_validation_ethusdt.{json,md,csv}` — machine-readable config/metrics, markdown report, per-forecast rows (1,087 forecasts).
- `research/forecasts/figures/h2_next_state_probs_ethusdt.png`, `h2_pit_hist_ethusdt.png`.

**Run configuration (bounded, not holdout-tuned):** ETHUSDT 1h, 3-state Gaussian HMM (diag), states ordered by mean (mu1<mu2<mu3), expanding refit every 720 bars, multi-seed best log-likelihood, filtered forward probabilities, eval_stride=4, train fitted <=2023-12-31, validation 2024-01-01 to 2024-06-30, holdout excluded.

**Validation metrics (1,087 forecasts, stride 4):**
- Log score mean (higher better): ETH HMM 3.7865 vs unconditional Gaussian 3.5308 vs EWMA Gaussian 3.6511 (HMM beats both baselines on ETHUSDT).
- CRPS mean (lower better): ETH HMM 0.003252 vs unconditional Gaussian 0.003583 vs EWMA Gaussian 0.003260 (HMM ≈ EWMA, both better than unconditional).
- ETH HMM PIT mean/std: 0.5070 / 0.2749 (ideal uniform ~0.5 / 0.289).

**Comparison to BTCUSDT validation (T4, same grid):** BTC HMM log score 4.0164 vs EWMA 3.9022 (not significantly different, p=0.44); EWMA CRPS 0.002631 significantly beats HMM 0.002597 (p=0.006). On ETHUSDT the HMM beats both baselines on log score point-estimate and is roughly tied with EWMA on CRPS — contrasting with BTCUSDT. The HMM forecast edge is therefore **not consistent across assets**, reinforcing the cross-family memo's robustness/non-stationarity concern. No bootstrap significance recomputed for ETHUSDT (point estimates only); period perturbation and negative-control robustness checks remain as follow-ups.

**Commands/tests run and outcomes (this session):**
- `PYTHONPATH=. python src/hmm_walkforward_ethusdt.py` — success; generated ETHUSDT artifacts above. Non-fatal "Model is not converging" warnings on some EM refits/seeds (consistent with T4).
- `PYTHONPATH=. python -m pytest -q` — **133 passed in 54.30s** (129 prior + 4 new ETHUSDT tests).
- No holdout executed. No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

---

### Task T5d-robustness-b completed (this session): Validation period perturbation Q1 vs Q2 for C1/C2 (no holdout execution)

**Files created**
- `src/validation_period_perturbation.py` — validation-only robustness script on saved BTCUSDT 1h forecast grids (stride 4, 1,087 forecasts each): splits validation window into Q1 (2024-01-01 <= t < 2024-04-01, n=546) and Q2 (2024-04-01 <= t < 2024-07-01, n=541), computes Gaussian-moment log scores/CRPS for C1 (HMM, `h2_validation_forecasts.csv`) and C2 (HOM, `h3_higher_order_markov_validation.csv`) vs unconditional/EWMA baselines, and reports stationary block-bootstrap (n^(1/3), 2000 reps, fixed seeds) 95% CIs and two-sided p-values for mean scores and paired differences plus Q2−Q1 stability deltas. No holdout data used; no model tuning.
- `tests/test_validation_period_perturbation.py` — 5 tests covering scoring helpers, stationary bootstrap indices/range, bootstrap CI sanity, Q1/Q2 split + score-frame behavior on saved HMM grid, and artifact/holdout-not-used assertions.
- `research/forecasts/period_perturbation_q1q2.json` — machine-readable Q1/Q2 metrics, bootstrap summaries, and stability deltas for C1/C2.
- `research/forecasts/period_perturbation_q1q2.md` — markdown report.

**Key findings (validation-only, point estimates with bootstrap diagnostics)**
- **C1/HMM:** Q1 log score 3.8505, CRPS 0.002899; Q2 log score 3.9945, CRPS 0.002451 (Q2 raw scores better). Paired-diff significance vs baselines is **period-unstable**: vs unconditional significant in Q1 (log +0.224, p=0.000; CRPS edge +2.26e-4, p=0.000) but not in Q2 (log +0.079, p=0.097; CRPS edge +1.29e-4, p=0.081); vs EWMA not significant on log in either period and EWMA significantly better on CRPS in Q1 (p=0.010) but not Q2 (p=0.233). Q2−Q1 edge deltas are negative vs both baselines on log/CRPS margins in this sample.
- **C2/HOM:** Q1 log score 3.7185, CRPS 0.002931; Q2 log score 3.9997, CRPS 0.002442 (Q2 raw scores better). Does **not** significantly beat unconditional on log in either subperiod (Q1 p=0.165, Q2 p=0.051) though CRPS edge vs unconditional is significant in both; vs EWMA not significant on log and significantly worse on CRPS in Q1 (p=0.026) / not significant in Q2 (p=0.383).
- **Interpretation:** Raw performance and relative edges vary materially between Q1 and Q2 on the sampled validation grid, consistent with prior train-vs-validation non-stationarity and cross-asset instability (ETHUSDT). Subperiod effective sample sizes are reduced; results are robustness diagnostics, not confirmatory/holdout evidence. Negative controls and any further perturbations remain relevant.

**Commands/tests run and outcomes (this session)**
- `PYTHONPATH=. python src/validation_period_perturbation.py` — **success**; wrote `research/forecasts/period_perturbation_q1q2.json` and `research/forecasts/period_perturbation_q1q2.md`.
- `PYTHONPATH=. python -m pytest -q tests/test_validation_period_perturbation.py` → **5 passed in 0.48s**.
- `PYTHONPATH=. python -m pytest -q` → **138 passed in 55.41s** (133 prior + 5 new).
- No holdout executed. No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

---

### Task T5d-robustness-c completed (this session): Negative controls for C1/C2 on saved validation grids (no holdout execution)

**Files created**
- `src/negative_controls.py` — red-team negative-control module (research prompt §7, §8 priority 7): compares real-model skill against two no-information controls on the saved BTCUSDT 1h validation grids (stride 4, 1,087 forecasts each, holdout excluded):
  - NC_A white noise: Gaussian N(0, sigma_y^2), pure no-information forecast.
  - NC_B target-shuffled: model (mu, var) moments paired with stationary-bootstrap resampled y_true (200 resamples averaged), destroying the genuine forecast->target relationship.
  - Stationary block bootstrap (block length n^(1/3), 2000 reps, 95% CI, two-sided p-values) on paired differences: real-vs-white-noise, real-vs-shuffled, shuffled-vs-white-noise.
- `tests/test_negative_controls.py` — 7 unit tests (scoring finiteness/ordering, bootstrap index shape/range, CI containment, white-noise shapes, shuffled shapes, saved-grid load + validation window, artifact/holdout-not-used assertions).
- `research/forecasts/negative_controls.json` — machine-readable point means and bootstrap paired-difference results for C1 and C2.
- `research/forecasts/negative_controls.md` — markdown report.

**Key findings (validation-only, point estimates + bootstrap diagnostics)**
- **C1/HMM:** real log score 3.922 vs white noise 3.848 → real significantly better (paired diff +0.0739, 95% CI [+0.028, +0.125], p=0.0025). Real vs target-shuffled log score significantly better (+0.185, p=0.000). CRPS: real vs white noise not significant (p=0.37); real vs shuffled not significant (p=0.196). Shuffled vs white noise log score borderline (p=0.033, shuffled slightly worse) — consistent with shuffling destroying genuine state information.
- **C2/HOM:** real vs target-shuffled log score significantly better (+0.101, p=0.0035) — genuine state information present. Real vs white noise log score not significant (p=0.37); CRPS real significantly *worse* than white noise (-5.9e-5, p=0.0005) — weak/negative economic signal consistent with validation dry-run zero trades. Shuffled vs white noise not significant on both metrics (p=0.198/0.284) — confirms shuffle removes information without spurious skill.
- **Interpretation:** C1/HMM carries real (log-score) information but CRPS edge over white noise is not significant; C2/HOM's edge is weak. Combined with T5a (zero trades after costs), T5d asset (ETHUSDT) and period (Q1/Q2) instability, the economic gate is unlikely to clear on holdout. Negative controls complete the validation-only robustness suite (period, asset, negative controls).

**Commands/tests run and outcomes (this session)**
- `PYTHONPATH=. python src/negative_controls.py` — **success**; wrote `research/forecasts/negative_controls.{json,md}`.
- `PYTHONPATH=. python -m pytest -q` → **145 passed in 54.83s** (138 prior + 7 new negative-control tests).
- No holdout executed. No changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. No `AGENT_STOP` created.

---

**Literature review** distinguishes six model families with primary references:

| Family | Key Primary Sources | Core Limitation for Trading |
|--------|---------------------|----------------------------|
| Finite-state Markov chains | Anderson & Goodman (1957) MLE; Kemeny & Snell (1976); Bauer & Vorkink (2011) | Discretization arbitrary; first-order often violated; sparse transitions; plug-in forecasts ignore estimation uncertainty |
| Higher-order / state-augmented | Raftery (1985) MTD; Bühlmann & Wyner (1999) VLMC | State-space explosion (K^m); MTD assumes additive lag structure; order selection inflates Type I error |
| Hidden Markov models | Baum et al. (1970) EM; Hamilton (1989); Cappé et al. (2005); Chib (1996) Bayesian | Label switching; regime collapse; initialization sensitivity; **smoothed vs. filtered confusion is #1 backtest trap** |
| Markov-switching AR/GARCH | Hamilton (1989); Hamilton & Susmel (1994); Gray (1996); Francq & Zakoïan (2001) | Path-dependent multi-step forecasts (K^h paths); parameter proliferation; non-standard asymptotics for K=1 vs K=2 |
| Semi-Markov / duration-dependent | Janssen & Manca (2006); Guédon (2003) HSMM; Yu (2010) | Need many completed spells for sojourn estimation; right-censoring; HSMM state expansion; identifiability vs. higher-order Markov |
| Markov decision processes | Puterman (1994); Bertsekas (2017); Sutton & Barto (2018); Bäuerle & Rieder (2011) | **Must explicitly define S, A, P, R, γ** — a chain + heuristic rule is NOT an MDP; transition model unknown; reward design subjective; policy instability |

**Cross-cutting methodological issues** documented with sources: state definition leakage (quantiles/clusters/HMM fit on full sample), non-stationarity (Pesaran & Timmermann 2002; Rossi 2013), multiple testing (Harvey et al. 2016; Bailey et al. 2017), walk-forward with purge/embargo (Lopez de Prado 2018), cost modeling (Almgren & Chriss 2001; crypto-specific frictions).

**Research plan** specifies 5 falsifiable hypotheses (H1–H5) with null/alternative, 7 observable state variables + 3 latent, 4 candidate horizons (15m, 1h, 4h, 24h), point-in-time universe rules for Binance BTC/ETH perps, 8 data-quality checks, 6 leakage controls, 5 statistical + 5 trading baselines, conservative cost model (10.6 bps round-trip base, 21.2 bps stress), expanding/rolling walk-forward with purge/embargo, block bootstrap uncertainty, red-team tests (period/asset/state/cost perturbations, negative controls, FDR correction), and two gates:

- **Forecast Validation Gate** (validation period): calibration/discrimination vs. baselines (p<0.05), state stability, regime persistence, robustness across sub-periods.
- **Economic Simulation Gate** (locked holdout): net Sharpe > 0.5, max DD < 20%, positive net expectancy (p<0.1), >100 trades, turnover < 500%, beats best baseline by >0.25 Sharpe.

Final decision mapping: `REJECT` / `RESEARCH_MORE` / `CANDIDATE_FOR_INDEPENDENT_CONFIRMATION` / `BLOCKED_NO_SAFE_WORK`.

---

### Commands/tests run and outcomes

- `mkdir -p research/literature research/specifications` — success (prior).
- `python src/data_ingestion.py` — success (prior).
- `python src/eda_regime_analysis.py` — **success** (prior session) after patching for `hmmlearn` API/covariance reorder; generated `research/eda/regime_analysis.md`, `research/eda/regime_analysis_results.json`, `research/eda/hmm_model_train.pkl`, and 11 figures in `research/eda/figures/`. Non-fatal "Model is not converging" warnings observed for some EM seeds.
- `python -m pytest -q tests/test_hmm_walkforward.py -k "ordered or filtered or forecast_next or expanding"` — **4 passed, 1 deselected** (prior session).
- `python src/hmm_walkforward.py` — **success** (prior session); generated `research/forecasts/h2_hmm_validation.md`, `research/forecasts/h2_hmm_validation_results.json`, `research/forecasts/h2_validation_forecasts.csv`, and figures in `research/forecasts/figures/` (1,087 validation forecasts, 7 refits). Non-fatal "Model is not converging" warnings observed on some EM refits/seeds.
- `python -m pytest -q tests/test_hmm_walkforward.py` — **5 passed** (prior session).
- `python -m pytest -q` — **54 passed in 11.61s** (prior session; includes existing tests + new HMM walk-forward tests).
- `PYTHONPATH=. python src/hmm_validation_significance.py` — **success** (prior session); generated `research/forecasts/h2_hmm_validation_significance.json`, `research/forecasts/h2_hmm_validation_significance.md`, `research/forecasts/figures/h2_bootstrap_diffs.png`. Non-fatal EM convergence warnings during sensitivity re-run.
- `PYTHONPATH=. python -m pytest -q tests/test_hmm_validation_significance.py` — **10 passed in 3.11s** (prior session).
- `PYTHONPATH=. python -m pytest -q` — **64 passed in 13.43s** (prior session; includes all existing + new bootstrap tests).
- `PYTHONPATH=. python -m pytest -q tests/test_markov_chain_baseline.py` — **6 passed** (this session).
- `PYTHONPATH=. python src/markov_chain_baseline.py` — **success** (this session); generated canonical T3 artifacts.
- `PYTHONPATH=. python -m pytest -q` — **70 passed in 18.56s** (this session; includes all existing + new MC baseline tests).
- `PYTHONPATH=. python src/verify_h1_consolidation.py` — **success** (this session); regenerated all consolidation tables from saved artifacts.
- `PYTHONPATH=. python src/higher_order_markov.py` — **success** (this session); generated `research/forecasts/h3_higher_order_markov_validation.{json,csv,md}`, CSV, and figures.
- `PYTHONPATH=. python -m pytest -q` — **76 passed in ~22s** (this session; 70 prior + 6 new HOM tests).
- `PYTHONPATH=. python -m pytest -q` — **85 passed in 29.90s** (this session; prior + T3d semi-Markov tests).
- `PYTHONPATH=. python src/economic_simulation.py --theta 0.0 2.0 5.0 --notional-fraction 0.10` — **success** (this session); generated `research/economic/validation_dryrun/` artifacts.
- `PYTHONPATH=. python -m pytest -q` — **110 passed in 29.70s** (this session; all tests including 25 new economic simulation tests).

- `PYTHONPATH=. python src/validation_period_perturbation.py` — **success** (this session); generated `research/forecasts/period_perturbation_q1q2.json` and `research/forecasts/period_perturbation_q1q2.md`.
- `PYTHONPATH=. python -m pytest -q tests/test_validation_period_perturbation.py` — **5 passed in 0.48s** (this session).
- `PYTHONPATH=. python -m pytest -q` — **138 passed in 55.41s** (this session; 133 prior + 5 new period-perturbation tests).

---

### Assumptions and unresolved questions

| # | Assumption / Question | Status |
|---|----------------------|--------|
| A1 | Binance public API provides complete, gap-free 15m klines for BTC/ETH 2021–2025 | **VERIFIED** — S3 dumps complete; missing_bars check passes for 15m/1h (FAIL for 4h/1d expected — gaps = intervals with no data) |
| A2 | Funding rate history available via API for full period | **VERIFIED** — 5478 rows per symbol (8h intervals) |
| A3 | Open interest history available via API for full period | **BLOCKED_EXTERNAL** — daily metrics files too numerous; skipped; feature column exists with NaN |
| A4 | 3-state HMM identifiable with ~3 years of 1h data | **PARTIALLY INFORMED** — model fits but EM convergence/init sensitivity observed and transition matrices non-stationary (Chow p<0.01); formal identifiability/simulation study still needed |
| A5 | MS-GARCH(1,1) 2-regime converges reliably with rolling 2.3-year windows | Simulation study needed |
| A6 | 10.6 bps round-trip cost conservative for $100k notional BTC/ETH perps | Validate with L2 data in T8 |
| A7 | 1.5-year holdout (2024-07 to 2025-12) sufficient for statistical power | Power analysis needed |
| A8 | No structural break in Binance perp contract specs during period | Verify contract history |
| Q1 | Include spot market data for lead-lag features? | Defer unless H1–H4 fail |
| Q2 | Test cross-sectional (multi-asset) Markov models? | Defer; single-asset first |
| Q3 | Is 15-minute horizon viable given cost structure? | T3 will test; likely fails net |

---

### Current session (2026-11-11): Prior task verified, handoff confirmed, no new work

**Prior task (T5d-robustness-c negative controls, per handoff) — verified complete**
- Artifacts present: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.json`, `research/forecasts/negative_controls.md`.
- `AGENT_STOP` present with cycle-close reason; `research/final_decision_report.md` present.
- Holdout runner refused by default: `PYTHONPATH=. python src/holdout_runner.py` → EXIT 2 (protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- `PYTHONPATH=. python -m pytest -q` → **145 passed in 55.00s**.

**Assessment:** Validation-only research cycle is complete. Evidence supports `RESEARCH_MORE` for the current C1/C2 candidate cycle (no net-after-cost edge on validation; C2 weak/negative vs white-noise on CRPS; C1 not robustly superior to EWMA and unstable across period/asset). Locked holdout not executed and not authorized. No safe, useful autonomous task remains under current instructions.

**Constraints respected:** no changes to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`; no credentials; no live trading; no holdout execution/tuning.

---

---

### Current session (2026-11-11): Prior handoff task read and completed (verification), handoff refreshed

**Prior task (from durable handoff):** read prior agent task and complete it — T5d-robustness-c negative controls, validation-only robustness closure, final decision report, and `AGENT_STOP`. **Status: completed/verified present; no additional implementation required.**

**Evidence checked (this session)**
- Required artifacts present: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.json`, `research/forecasts/negative_controls.md`, `research/final_decision_report.md`, `AGENT_STOP` (reason: validation-only cycle complete, `RESEARCH_MORE` for materially different approaches/cost assumptions, holdout not executed/authorized).
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**, protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 55.00s**.
- Git/repo state reviewed: recent checkpoint commits on `main`; uncommitted work limited to this handoff refresh (commit/push handled by workflow controller, not this agent).

**Assessment:** Cycle remains closed (`COMPLETE` / `RESEARCH_MORE`, C1/C2 validation-only). No safe, useful autonomous task remains while `AGENT_STOP` exists and no human authorization for continuation/holdout is recorded.

**Constraints respected:** no live trading; no credentials; no holdout execution/tuning; no edits to `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`; no new research task started.

---

### Current session (2026-11-11, fifth verification): Prior task read and completed — independently re-verified from a bare environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment note:** this sandbox was bare (no numpy/pandas/pytest/hmmlearn installed; `data/` absent because gitignored). Installed `requirements.txt` + `hmmlearn` and regenerated `data/` from Binance S3 (`PYTHONPATH=. python src/data_ingestion.py` → success, 87,648 rows, manifest hash `4f9e445663c85d1f`, features hash `e1ccfd7a06171371`) so the prior "145 passed" claim could be re-derived rather than trusted.
- Re-verified prior task closure (T5d-robustness-c negative controls, validation-only cycle close): `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**, protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.66s** (after data regeneration; the 21 failures seen before `data/` existed were `FileNotFoundError: data/processed/features.parquet`, i.e. data-absence, not code regressions).
- Git/repo state reviewed: recent checkpoint commits on `main`; uncommitted work limited to this handoff refresh (commit/push handled by workflow controller, not this agent).

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. Handoff refreshed with this verification and a clear initial task message for the next agent below. No new work started.

## Next single bounded task

**None — research cycle closed (`AGENT_STOP` present).**
- Do not start new tasks. See `AGENT_STOP`, `research/final_decision_report.md`, and this handoff.
- If and only if a human explicitly authorizes continuation, remove `AGENT_STOP`, record authorization/evidence/scope in this handoff, and begin only a materially different, predeclared, bounded task (or an authorized holdout execution per protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`). Do not tune on holdout outcomes.
- Do not modify `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`.

---

## Initial task message for next agent

Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, this handoff, `research/final_decision_report.md`, and `AGENT_STOP` before taking any action.

**Repo state (independently re-verified 2026-11-11 in this live environment):** `COMPLETE` / `RESEARCH_MORE` for current C1/C2 cycle (validation-only). All prior tasks through T5d-robustness-c (negative controls) are complete with required artifacts present. `AGENT_STOP` exists with the cycle-close reason. Holdout runner refuses by default: `PYTHONPATH=. python src/holdout_runner.py` → **EXIT 2** (protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`). Full tests pass: `PYTHONPATH=. python -m pytest -q` → **145 passed in 45.93s** (this environment has `data/` and all deps present; if a future sandbox is bare, run `pip install -r requirements.txt hmmlearn` and `PYTHONPATH=. python src/data_ingestion.py` first — without `data/`, 21 tests fail with `FileNotFoundError`). No holdout executed. Git working tree clean.

**Task:** **None while `AGENT_STOP` exists.** Do not start autonomous work.

**If (and only if) a human explicitly authorizes continuation:** remove `AGENT_STOP`, record the exact authorization, scope, and evidence in this handoff (and update status), then perform exactly one bounded, predeclared task consistent with that authorization — e.g. a materially different model/state/horizon hypothesis with falsifiable criteria, or an authorized locked-holdout run per protocol: `PYTHONPATH=. python src/holdout_runner.py --execute-holdout --protocol-hash 50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`. Do not tune on holdout outcomes, do not trade/deploy/use credentials, and do not edit `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`. Update this handoff with results, verification, blockers, and one next task or renewed stop.

---

### Current session (2026-11-11, sixth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** this sandbox has `data/` present (gitignored, regenerated in a prior session) and all deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with the cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 45.48s**.
- Git state: `main` up to date with `origin/main`; working tree clean; no uncommitted changes.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; the initial task message for the next agent below is confirmed current and accurate. No new work started.

### Current session (2026-11-11, seventh verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** this sandbox has `data/` present (gitignored, regenerated in a prior session) and all deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with the cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.19s**.
- Git state: `main` up to date with `origin/main`; working tree clean; no uncommitted changes.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; the initial task message for the next agent below is confirmed current and accurate. No new work started.

---

### Current session (2026-11-11, eighth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** this sandbox has `data/` present (gitignored) and all deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with the cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.43s**.
- Git state: `main` up to date with `origin/main`; working tree clean; no uncommitted changes.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; the initial task message for the next agent below is confirmed current and accurate. No new work started.

---

### Current session (2026-11-11, ninth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** this sandbox has `data/` present (gitignored) and all deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with the cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.06s**.
- Git state: `main` up to date with `origin/main`; working tree clean; no uncommitted changes.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; the initial task message for the next agent below is confirmed current and accurate. No new work started.

### Current session (2026-11-11, tenth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** this sandbox has `data/` present (gitignored) and all deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with the cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.48s**.
- Git state: `main` up to date with `origin/main`; working tree clean; no uncommitted changes.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; the initial task message for the next agent below is confirmed current and accurate. No new work started.


---

### Current session (2026-11-11, eleventh verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** `data/` present (gitignored) and deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 45.93s**.
- Git state: `main` up to date with `origin/main`; working tree clean aside from this handoff update.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; initial task message for the next agent below confirmed current and accurate. No new work started.

### Current session (2026-11-11, twelfth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** `data/` present (gitignored) and deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.06s**.
- Git state: `main` up to date with `origin/main`; working tree clean aside from this handoff update.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; initial task message for the next agent below confirmed current and accurate. No new work started.

### Current session (2026-11-11, thirteenth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** `data/` present (gitignored) and deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed**.
- Git state: `main` up to date with `origin/main`; working tree clean aside from this handoff update.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; initial task message for the next agent below confirmed current and accurate. No new work started.

### Current session (2026-11-11, fourteenth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** `data/` present (gitignored) and deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 46.69s**.
- Git state: `main` up to date with `origin/main`; working tree clean aside from this handoff update.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; initial task message for the next agent below confirmed current and accurate. No new work started.

### Current session (2026-11-11, fifteenth verification): Prior task read and completed — re-verified in this live environment

**Task (from durable handoff):** "Read the prior agent task from the durable handoff and complete it. Then update the handoff and write a clear initial task message for the next agent."

**Actions taken:**
- Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, `research_state/agent_handoff.md`, `research/final_decision_report.md`, and `AGENT_STOP`.
- **Environment check:** `data/` present (gitignored) and deps present (`pytest`, `numpy`, `pandas`, `hmmlearn`) — no re-install or data regeneration needed this session.
- Re-verified prior task closure: `src/negative_controls.py`, `tests/test_negative_controls.py`, `research/forecasts/negative_controls.{json,md}`, `research/final_decision_report.md`, and `AGENT_STOP` all present with cycle-close reason.
- Holdout protocol enforcement: `PYTHONPATH=. python src/holdout_runner.py` → refused by default (**EXIT 2**; protocol hash `50aa8a4feff29de41a03c0d63e998d6b15f12ccd979825800d02c7dbe4166062`).
- Full test suite: `PYTHONPATH=. python -m pytest -q` → **145 passed in 45.38s**.
- Git state: `main` up to date with `origin/main`; working tree clean; no uncommitted changes.

**Result:** Prior task already complete; cycle status remains `COMPLETE` / `RESEARCH_MORE`. No new implementation required. Handoff refreshed with this verification; initial task message for the next agent below confirmed current and accurate. No new work started.

## Stop rule

When the research has no remaining high-value, safe task, or the agreed research cycle has been completed, write `AGENT_STOP` with the reason and set this handoff status to `COMPLETE` or `BLOCKED_NO_SAFE_WORK`. Do not create a STOP marker merely because one data provider is unavailable if useful independent literature or methodology work remains.
