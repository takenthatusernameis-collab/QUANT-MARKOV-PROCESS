# Holdout Evaluation & Economic Simulation Gate Protocol (Pre-specified)

**Status:** FROZEN_PRE_EXECUTION (protocol document only; no holdout evaluation executed)
**Date:** 2026-11-11
**Scope:** Locked holdout **2024-07-01 00:00:00+00:00 to 2025-12-31 23:00:00+00:00** (BTCUSDT 1h), per `research/specifications/initial-research-plan.md` §9.1 and `research_state/agent_handoff.md`.
**Purpose:** Define a concrete, point-in-time, reproducible procedure for (1) holdout forecast validation and (2) economic simulation gate (H5) without using holdout for tuning, selection, or parameter fitting.

## 1. Leakage and integrity controls (mandatory)

- **No holdout execution under this protocol yet.** This document freezes intent/config; any runner implementation must refuse to write holdout results unless explicitly invoked under a recorded, unchanged protocol hash/manifest.
- **No tuning on holdout.** Model family choice, state definitions, hyperparameters, refit cadence, evaluation stride, thresholds, cost parameters, and strategy rules are fixed from validation evidence only.
- **Point-in-time only.** At each decision time *t*, use information available at or before *t* (completed bars only). No future bars, no full-sample normalization, no holdout-fitted bins/scalers/clusters/regime labels.
- **Filtered probabilities only.** For HMM/latent models, use forward/filtered state probabilities at decision time; **smoothed** (future-using) probabilities are prohibited for forecasts or trading decisions.
- **Expanding/rolling refit as specified.** All estimators (bins/edges where applicable, transition/count models, state-conditional moments, HMM parameters) are fit on history strictly prior to each target/decision as defined below.
- **Purge/embargo.** For 1h horizon, purge 1h and embargo 1h at boundaries (plan §9.3); no label/target overlap with training history used for the forecast.
- **Universe/data contract.** BTCUSDT USDT-M perpetual, Binance public data, 1h aligned features from `data/processed/features.parquet` / manifest `data/raw/manifest.json` (SHA256s recorded therein). No silent provider switching.

## 2. Validation evidence basis (selection inputs only)

All numbers below are **validation-only** (2024-01-01 to 2024-06-30), stride-4 sampled grids where stated, holdout excluded. Sources: `research_state/agent_handoff.md`, T4/H2 `research/forecasts/h2_hmm_validation.md|.json`, H1 `research/forecasts/h1_markov_chain_validation.md|.json`, H3 `research/forecasts/h3_higher_order_markov_validation.md|.json`, H4 `research/forecasts/h4_semi_markov_validation.md|.json`, consolidation `research/forecasts/h1_mc_sensitivity_consolidation.md|.json`, significance `research/forecasts/h2_hmm_validation_significance.md|.json`.

| Model (validation) | Log score ↑ | CRPS ↓ | PIT mean/std | Notes |
|---|---:|---:|---:|---|
| HMM 3-state Gaussian, filtered (T4, H2) | **4.01643** | **0.00259686** | 0.5105 / 0.2697 | Best point scores; significantly > unconditional (log/CRPS, p<0.001); not significantly > EWMA on log (p=0.44); EWMA better on CRPS (p=0.006). EM convergence warnings/non-stationarity caveats. |
| Higher-order Markov (H3, order 2, K=5) | 3.85845 | 0.002687 | 0.4993 / 0.2799 | Best non-latent MC; > H1 aligned (p<=0.004); not significantly different from EWMA. |
| Semi-Markov (H4, K=5) | 3.82976 | 0.00270785 | 0.49885 / 0.27875 | Weak duration effect; ≈H1. |
| First-order MC canonical (H1, Q5) | 3.82976 | 0.00270785 | 0.4988 / 0.2788 | Baseline discrete chain. |
| EWMA Gaussian (λ=0.94) | 3.90220–3.90424* | 0.00263060–0.00267385* | — | Strong baseline (*grid/config-dependent in saved runs). |
| Unconditional Gaussian | ~3.748–3.770 | ~0.002854–0.002903 | — | Naive baseline. |

## 3. Frozen candidate selection (holdout candidates, validation-evidence only)

### 3.1 Primary forecast candidate: **C1 — Filtered 3-state Gaussian HMM (T4/H2 configuration)**
- **Rationale:** Highest validation log score and lowest CRPS among evaluated models; significant improvement over unconditional on both proper scores; PIT near-uniform mean; interpretable regime probabilities (diagnostic) with expanding filtered inference already implemented (`src/hmm_walkforward.py`).
- **Frozen config (must match T4 artifacts unless a documented, validation-equivalent runner is required for holdout mechanics):** K=3 states ordered by mean (μ₁<μ₂<μ₃), Gaussian emissions (diagonal cov as in implementation), `hmmlearn` EM multi-seed best-by-train-loglik, **expanding** history up to *t* only, **1-step-ahead filtered** posterior via forward pass, decision/target grid consistent with 1h horizon and evaluation stride **4** bars for comparability to validation (or full 1h grid if predeclared here as sensitivity — see §7; primary reported metrics use stride 4), `refit_every=720` bars, `seeds=[0,1,2]` as in T4 bounded run. Any deviation requires written justification showing no holdout information used; default is to reproduce T4 mechanics.
- **Caveats carried forward:** EM non-convergence warnings on some refits; train-vs-validation transition non-stationarity (Chow p=0.0042, EDA). These are risk factors, not license to retune.

### 3.2 Secondary/robustness comparator (non-latent): **C2 — Higher-order Markov chain H3 (order 2, K=5 quantile)**
- **Rationale:** Best non-latent chain on validation (beats H1/H4 aligned on key comparisons; stronger than canonical first-order MC) with transparent expanding-count estimation and no EM initialization sensitivity.
- **Frozen config:** order m=2, K=5 quantile states with **bin edges fitted on training only (<=2023-12-31)**, K²=25 pairs, expanding transition counts with Laplace α=1.0, min pair samples 20 with global fallback, pair/state-conditional Gaussian moments from expanding history < target, `eval_stride=4`, 1h horizon (`src/higher_order_markov.py` logic).

### 3.3 Baselines (always reported, same grid/cost assumptions where applicable)
- **B1:** Expanding unconditional Gaussian return distribution (history < target).
- **B2:** EWMA Gaussian (RiskMetrics-style, λ=0.94).
- **B3:** No-signal / no-trade (economic only).
- **B4:** Buy-and-hold BTCUSDT perp exposure benchmark (economic only; define funding/roll treatment explicitly in runner spec before execution).
- **B5:** Simple momentum/trend and volatility-state rules per plan §7.2 (economic; parameters predeclared, not optimized on holdout) — to be implemented as fixed-rule baselines in simulation scaffolding prior to holdout run.

## 4. Holdout forecast-evaluation procedure (point-in-time)

**Holdout period:** 2024-07-01 00:00:00+00:00 ≤ target time t ≤ 2025-12-31 23:00:00+00:00.
**History available:** all data from 2021-01-01 up to t-1 (completed bars), with expanding refit schedule identical in form to validation (no peeking).
**Targets:** 1-step-ahead (1h) realized return/state outcomes aligned to completed candles.

For each evaluated target t on the predeclared grid:
1. Build training/estimation sample = all returns/features with timestamps < t (and respecting purge/embargo at any internal boundary if applicable).
2. Fit/update model parameters using only that sample (expanding). For C1, run multi-seed EM on history ≤ t-1 (or as per T4) and select best by training log-likelihood; compute **filtered** state probs at t-1 and forecast distribution for r_t.
3. Record forecast artifacts: timestamp, realized return, predicted state probs/moments/mixture params as applicable, baseline forecasts, and refit metadata.
4. Compute proper scoring metrics after all forecasts generated (no interim tuning): mean log score, CRPS (mixture-aware where possible; document approximation if any), PIT values/diagnostics, calibration summaries.

**Statistical uncertainty:** stationary block bootstrap on paired score differences vs baselines (default 2000 reps, block length ≈ n^(1/3) or predeclared fixed), 95% percentile CIs, two-sided p-values, effective sample size estimates; report per comparison. Multiple-comparison awareness (FDR) required if >2 primary comparisons are tested (§7).

## 5. Economic simulation gate procedure (H5)

Economic simulation is run **only after** forecast artifacts for holdout are produced under §4 (or in the same frozen runner pass). It maps forecasts to actions with a **no-trade region** and fixed sizing/risk rules.

### 5.1 Signal-to-action mapping (predeclared, no optimization on holdout)
- **Primary mapping (C1/C2, directional research probe):** derive expected 1h return/edge from model conditional mean (mixture mean) vs cost-adjusted threshold. Enter/hold long if E[r_t|F_{t-1}] > θ + c_eff; short if < -θ - c_eff; else flat (no-trade).
- **Frozen thresholds:** θ = 0 bps (base case, edge must exceed costs) and a sensitivity band θ ∈ {2, 5} bps reported as predeclared robustness only (not for "pass" selection). **No threshold chosen by holdout performance.**
- **Sizing:** fixed notional fraction of equity (e.g. 10% notional, no leverage > 1x for base case) with max gross exposure 100%; positions marked-to-market each bar; fractional sizing allowed in simulation abstraction but must respect min-notional/tick realism in assumptions.
- **Execution timing:** decision at close of bar t-1, fill assumption at open/close convention of bar t as specified in implementation (must be consistent and documented; default: next-bar open proxy with slippage/half-spread applied). No intrabar lookahead.

### 5.2 Trading frictions and cost model (base and stress)
Per plan §8.1–8.2 (Binance USDT-M perps, conservative taker):

| Component | Base | Stress (2×) |
|---|---:|---:|
| Taker fee (per side) | 5.0 bps | 10.0 bps |
| Half-spread (per side) | 1.0 bps | 2.0 bps |
| Slippage / impact (per side, ~$100k BTC/ETH) | 2.0 bps | 4.0 bps |
| **Total round-trip (ex funding)** | **≈ 16.0 bps** (2 sides × 8 bps) / plan §8.2 reports ≈10.6 bps aggregate convention — **implementation must use explicit per-side accounting and document the exact formula**; default adopt plan: 0.05% fee + 1 bps spread + 2 bps slippage per trade side as applicable → round-trip ≈10.6 bps, stress ≈21.2 bps | ≈21.2 bps |
| Funding (8h, applied pro-rata to holding periods) | use historical funding series from `data/processed/features.parquet` when available at decision time; else assume 0 and flag | 2× \|funding\| |

- Turnover, minimum notional (5 USDT), tick/lot realism noted; capacity sensitivity via stress costs.
- Report **gross and net** PnL separately; net includes fees+spread+slippage+funding.

### 5.3 Economic metrics (report all, as applicable)
- Net/gross: CAGR (annualized), volatility (annualized), Sharpe, Sortino, Calmar, max drawdown (peak-to-trough).
- Trade/exposure: hit rate, payoff ratio, profit factor, expectancy (net, per trade and per bar), tail loss, max leverage/gross exposure, turnover (annualized), trade count, avg holding time, time in market.
- Baseline-relative: excess vs B3/B4/B5 and vs no-trade cost drag.
- Uncertainty: HAC/Newey-West or block-bootstrap CIs for mean net returns/Sharpe where feasible; report sample size/trade count.

## 6. Gate criteria and decision mapping

### 6.1 Forecast validation gate (holdout)
A candidate's holdout forecast performance is considered supportive only if (predeclared):
- Proper scores (log score and/or CRPS) improve over B1 with uncertainty not overlapping zero harm in the adverse direction under bootstrap CI (and p < 0.05 where tested), and are competitive with B2 (no material degradation without explanation).
- PIT/calibration diagnostics show no gross miscalibration; state/probability behavior stable enough for interpretation.
- Results reported for C1 and C2; failure of one does not erase the other's measured outcome but informs decision.

### 6.2 Economic simulation gate (H5, holdout)
Per plan §11.2 (evaluated on locked holdout, net of all costs, base cost case primary):
- Net Sharpe > 0.5 (annualized)
- Max drawdown < 20%
- Positive net expectancy (mean net return > 0; HAC-aware test p < 0.1)
- Trade count > 100
- Annualized turnover < 500%
- Net Sharpe exceeds best simple baseline (B3/B4/B5) by > 0.25

Stress-cost case (2×) must be reported; failure under stress is a robustness concern.

### 6.3 Final decision mapping (research-only)
- **`CANDIDATE_FOR_INDEPENDENT_CONFIRMATION`**: ≥1 candidate passes Economic Gate on holdout under base costs with robustness checks not contradicting (per plan §11.3). **Not** permission to trade/deploy; no access to further locked data implied.
- **`RESEARCH_MORE`**: forecast skill present but economic gate fails, or mixed/fragile evidence warrants new predeclared hypotheses (different states/horizons/cost-aware mappings) — must be specified before any new evaluation.
- **`REJECT`**: candidates fail forecast and/or economic gates with negative/unstable evidence across predeclared checks.
- **`BLOCKED_NO_SAFE_WORK`**: required data/artifacts unavailable and no independent safe research task remains.

## 7. Predeclared robustness / red-team checks (run only as specified)

- **Cost stress:** base and 2× (and optionally 5× as sensitivity) per §5.2.
- **Subperiods:** split holdout into contiguous halves (2024-07-01–2025-03-31, 2025-04-01–2025-12-31) and report metrics per subperiod (descriptive; small-sample uncertainty acknowledged).
- **Baselines:** B1–B5 on identical timestamps/costs.
- **Grid sensitivity (descriptive only):** full 1h grid vs stride-4 grid if computed — must not be used to select the "better" result; primary remains stride-4 for comparability.
- **Negative controls (if feasible in runner):** label-shuffled / randomized signal baseline to confirm pipeline integrity.
- **No post-hoc parameter changes.** Any discovered issue is documented as a limitation/failure, not "fixed" by retuning on holdout.

## 8. Artifacts and reproducibility requirements (for future execution)

When holdout evaluation is executed under this protocol, produce:
- `research/forecasts/holdout/` (or equivalent predeclared path): per-model forecast CSVs, metrics JSON, bootstrap/significance JSON/MD, PIT/calibration figures, and an execution manifest (git SHA, protocol doc hash, data manifest hashes, seeds, command, timestamps).
- `research/economic/holdout/`: trade ledger/returns series, gross/net metrics JSON/MD, equity/drawdown figures, cost-stress tables, baseline comparisons.
- A short holdout report citing this protocol and listing any deviations (deviations => results non-confirmatory).

## 9. Explicit prohibitions

- No live trading, order placement, account access, or credentials (per `AGENTS.md`).
- No modification of `AGENTS.md`, `MARKOV_RESEARCH_PROMPT.md`, or `.github/workflows/*`.
- No HMM smoothed probabilities for decisions/forecasts.
- No holdout inspection used to choose C1 vs C2 parameters, thresholds, or cost assumptions.

## 10. Provenance (key artifact paths)

- Plan: `research/specifications/initial-research-plan.md`
- Data: `data/raw/manifest.json`, `data/processed/features.parquet`
- EDA/HMM fit (train): `research/eda/regime_analysis.md`, `research/eda/hmm_model_train.pkl`
- H1: `research/forecasts/h1_markov_chain_validation.*`, `research/forecasts/h1_mc_sensitivity_consolidation.*`
- H2/HMM: `research/forecasts/h2_hmm_validation.*`, `research/forecasts/h2_hmm_validation_significance.*`, `research/forecasts/h2_validation_forecasts.csv`
- H3: `research/forecasts/h3_higher_order_markov_validation.*`
- H4: `research/forecasts/h4_semi_markov_validation.*`
- Code: `src/hmm_walkforward.py`, `src/markov_chain_baseline.py`, `src/higher_order_markov.py`, `src/semi_markov_baseline.py`, `src/hmm_validation_significance.py`

---
*End of pre-specified protocol. Execution on holdout is not performed in this session.*
