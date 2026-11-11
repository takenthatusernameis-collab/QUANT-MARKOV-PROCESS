# Agent handoff

**Repository:** `takenthatusernameis-collab/QUANT-MARKOV-PROCESS`
**Branch:** `main`
**Current phase:** `DISCOVERY_AND_METHOD_DESIGN`
**Status:** `READY`
**Updated:** 2026-11-10

## Mission

Determine whether Markov-process-based representations can produce a statistically robust, executable-after-costs predictive edge in liquid cryptocurrency markets. The mandate is research-only. There is no approved live-trading or deployment path.

## What exists

The repository was initialized on 2026-11-10. It contains the research mandate, agent boundaries, and this handoff. No strategy, dataset, backtest, or performance result has been established. Do not infer otherwise.

## Completed work

### Files created

1. `research/literature/markov-processes-in-finance.md` (575 lines) — Sourced literature and methodology review covering all six model families.
2. `research/specifications/initial-research-plan.md` (353 lines) — Falsifiable research plan with testable hypotheses, data contracts, validation protocol, and go/no-go criteria.

### Concise findings and sources

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

- `mkdir -p research/literature research/specifications` — directories created successfully.
- Two markdown files written and verified (575 + 353 lines).
- No code execution or data fetching performed yet (literature/methodology phase only).

### Assumptions and unresolved questions

| # | Assumption / Question | Status |
|---|----------------------|--------|
| A1 | Binance public API provides complete, gap-free 15m klines for BTC/ETH 2021–2025 | To verify in T1 |
| A2 | Funding rate history available via API for full period | To verify in T1 |
| A3 | Open interest history available via API for full period | To verify in T1 |
| A4 | 3-state HMM identifiable with ~3 years of 1h data | Simulation study needed |
| A5 | MS-GARCH(1,1) 2-regime converges reliably with rolling 2.3-year windows | Simulation study needed |
| A6 | 10.6 bps round-trip cost conservative for $100k notional BTC/ETH perps | Validate with L2 data in T8 |
| A7 | 1.5-year holdout (2024-07 to 2025-12) sufficient for statistical power | Power analysis needed |
| A8 | No structural break in Binance perp contract specs during period | Verify contract history |
| Q1 | Include spot market data for lead-lag features? | Defer unless H1–H4 fail |
| Q2 | Test cross-sectional (multi-asset) Markov models? | Defer; single-asset first |
| Q3 | Is 15-minute horizon viable given cost structure? | T3 will test; likely fails net |

## Next single bounded task

**Task T1: Data Ingestion & Manifest** (from research plan Section 15)

- Fetch Binance USDT-M perpetual klines (15m, 1h, 4h, 1d) for BTCUSDT, ETHUSDT from 2021-01-01 to 2025-12-31.
- Fetch funding rate (8h) and open interest (1h) for same.
- Run all data-quality checks (Plan Section 5.1).
- Produce `data/raw/manifest.json` with source, row counts, date ranges, SHA256 hashes.
- Produce `data/processed/features.parquet` with aligned, validated OHLCV + funding + OI.
- **Verification:** Automated test script asserts all quality checks pass; manifest matches independent spot check.

---

## Stop rule

When the research has no remaining high-value, safe task, or the agreed research cycle has been completed, write `AGENT_STOP` with the reason and set this handoff status to `COMPLETE` or `BLOCKED_NO_SAFE_WORK`. Do not create a STOP marker merely because one data provider is unavailable if useful independent literature or methodology work remains.