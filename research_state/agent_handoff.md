# Agent handoff

**Repository:** `takenthatusernameis-collab/QUANT-MARKOV-PROCESS`
**Branch:** `main`
**Current phase:** `DISCOVERY_AND_METHOD_DESIGN`
**Status:** `READY`
**Updated:** 2026-11-11 (T4 H2 groundwork added)

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

### Task T4 completed (this session): Walk-forward filtered HMM forecast validation (BTCUSDT 1h, validation only)

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

### Concise findings and sources (prior)

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

### Commands/tests run and outcomes

- `mkdir -p research/literature research/specifications` — success (prior).
- `python src/data_ingestion.py` — success (prior).
- `python src/eda_regime_analysis.py` — **success** (prior session) after patching for `hmmlearn` API/covariance reorder; generated `research/eda/regime_analysis.md`, `research/eda/regime_analysis_results.json`, `research/eda/hmm_model_train.pkl`, and 11 figures in `research/eda/figures/`. Non-fatal "Model is not converging" warnings observed for some EM seeds.
- `python -m pytest -q tests/test_hmm_walkforward.py -k "ordered or filtered or forecast_next or expanding"` — **4 passed, 1 deselected** (this session).
- `python src/hmm_walkforward.py` — **success** (this session); generated `research/forecasts/h2_hmm_validation.md`, `research/forecasts/h2_hmm_validation_results.json`, `research/forecasts/h2_validation_forecasts.csv`, and figures in `research/forecasts/figures/` (1,087 validation forecasts, 7 refits). Non-fatal "Model is not converging" warnings observed on some EM refits/seeds.
- `python -m pytest -q tests/test_hmm_walkforward.py` — **5 passed** (this session).
- `python -m pytest -q` — **54 passed in 11.61s** (this session; includes existing tests + new HMM walk-forward tests).

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

## Next single bounded task

**Task T4b (H2): Block-bootstrap uncertainty and sensitivity for validation forecast scores (validation only)**

- Using saved validation forecast outputs (`research/forecasts/h2_validation_forecasts.csv` and/or `research/forecasts/h2_hmm_validation_results.json`), implement a reproducible analysis script (e.g. `src/hmm_validation_significance.py`) that computes paired score differences (HMM mixture vs unconditional Gaussian, HMM vs EWMA Gaussian) for log score and CRPS and estimates uncertainty/significance with a time-series-appropriate block bootstrap on the validation period only (no holdout).
- Report mean differences, bootstrap confidence intervals, and approximate p-values/effective sample-size notes; explicitly state the evaluation grid/cadence used in saved artifacts (`refit_every=720`, `seeds=[0,1,2]`, `eval_stride=4`) and its limitations.
- Add a small sensitivity check feasible within runtime: rerun walk-forward on a narrower validation sub-window or alternate `refit_every`/`eval_stride` configuration (bounded) and compare metric deltas; do not tune on holdout.
- Add focused automated tests for bootstrap/statistic helpers (deterministic with fixed RNG, no leakage). Save report/artifacts under `research/forecasts/` (e.g. `h2_hmm_validation_significance.md/json`).
- Run `python -m pytest -q` and update this handoff with exact commands, outcomes, blockers (EM convergence/non-stationarity), and one next task.

---

## Initial task message for next agent

Read `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, and this handoff. T4 groundwork is complete: `src/hmm_walkforward.py`, `tests/test_hmm_walkforward.py`, and validation-only artifacts in `research/forecasts/` (`h2_hmm_validation.md/json/csv`, figures). Saved run: 1,087 validation forecasts (eval_stride=4), 7 refits (720-bar), seeds [0,1,2]; mean log score HMM 4.016 vs unconditional 3.770 vs EWMA 3.902 and mean CRPS HMM 0.002597 vs unconditional 0.002854 vs EWMA 0.002631 (point estimates only). Holdout >= 2024-07-01 was not used. Caveats: non-fatal EM non-convergence warnings on some refits, train-vs-validation non-stationarity from T2, and "realized state" diagnostics are model-dependent.

Your bounded task is **T4b**: quantify uncertainty/significance and basic sensitivity of the validation forecast comparison without touching the holdout. Add a reproducible analysis (preferably using existing `research/forecasts/h2_validation_forecasts.csv`) with block-bootstrap CIs/p-values for paired log-score/CRPS differences (HMM vs unconditional, HMM vs EWMA), run one bounded sensitivity configuration if feasible, add tests for the new statistic/bootstrap logic, save artifacts under `research/forecasts/`, run `python -m pytest -q`, and update this handoff with findings, exact verification, blockers, and one next task (e.g. implement T3 finite-state Markov chain baseline on validation or design holdout-evaluation protocol without executing it).

## Stop rule

When the research has no remaining high-value, safe task, or the agreed research cycle has been completed, write `AGENT_STOP` with the reason and set this handoff status to `COMPLETE` or `BLOCKED_NO_SAFE_WORK`. Do not create a STOP marker merely because one data provider is unavailable if useful independent literature or methodology work remains.