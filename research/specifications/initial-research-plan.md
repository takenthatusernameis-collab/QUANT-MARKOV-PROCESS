# Initial Research Plan: Markov Processes in Liquid Cryptocurrency Markets

**Status:** Draft
**Date:** 2026-11-10
**Purpose:** Falsifiable research plan with testable hypotheses, data contracts, validation protocol, and explicit go/no-go criteria. Companion to `research/literature/markov-processes-in-finance.md`.

---

## 1. Testable Hypotheses

### H1: Finite-State Markov Chain Forecast Skill
> **H1:** A discrete-state Markov chain with states defined by realized volatility and return quantiles (fit on training data only) produces out-of-sample 1-step-ahead state transition forecasts that are better calibrated and more discriminating than the unconditional historical transition distribution, at the 15-minute, 1-hour, 4-hour, and 24-hour horizons, for BTC-USDT and ETH-USDT perpetual futures on Binance.

- **Null (H1₀):** Markov chain transition forecasts are indistinguishable from unconditional historical transitions (calibration and discrimination metrics not significantly better).
- **Alternative (H1₁):** Markov chain forecasts show statistically significant improvement in Brier score, log-loss, and/or transition-matrix calibration at one or more horizons.

### H2: Hidden Markov Model Regime Forecast Skill
> **H2:** A 3-state Gaussian HMM (with regime identification constraint μ₁ < μ₂ < μ₃ on mean returns) estimated via Bayesian MCMC produces filtered regime probabilities that yield out-of-sample conditional return distribution forecasts superior to a single-regime GARCH(1,1) and a rolling-window historical distribution, at 1-hour and 4-hour horizons.

- **Null (H2₀):** HMM conditional forecasts are not significantly better than baselines in CRPS, log-score, or directional accuracy.
- **Alternative (H2₁):** HMM forecasts show significant improvement in at least one proper scoring rule.

### H3: Markov-Switching GARCH Volatility Forecast Skill
> **H3:** A 2-regime MS-GARCH(1,1) model produces 1-step-ahead volatility forecasts with lower MSE and better coverage of 95% prediction intervals than a single-regime GARCH(1,1) and a RiskMetrics EWMA, for 1-hour and 4-hour horizons.

- **Null (H3₀):** MS-GARCH volatility forecasts are not significantly more accurate than baselines.
- **Alternative (H3₁):** MS-GARCH shows significant improvement in MSE and/or interval coverage.

### H4: Duration-Dependent Transition Skill
> **H4:** A semi-Markov model with Weibull sojourn distributions produces more accurate residual-duration forecasts and duration-conditioned transition probabilities than a first-order Markov chain, for regimes identified by HMM (H2).

- **Null (H4₀):** Duration dependence adds no predictive value beyond first-order Markov.
- **Alternative (H4₁):** Semi-Markov model significantly improves duration forecasts (CRPS) and/or transition forecasts conditioned on duration.

### H5: Economic Significance After Costs
> **H5:** A trading strategy derived from the best-performing Markov model (H1–H4) generates positive net expected returns after all trading frictions (fees, spread, slippage, funding, turnover), with a net Sharpe ratio > 0.5 and maximum drawdown < 20%, over a locked holdout period.

- **Null (H5₀):** No Markov-model-derived strategy has positive net expectancy after costs on the holdout.
- **Alternative (H5₁):** At least one strategy meets the net Sharpe > 0.5, max DD < 20% criteria on the holdout.

---

## 2. Plausible State Variables

### 2.1 Directly Observable (for Finite-State Chains)

| Variable | Construction | Horizons | Rationale |
|----------|-------------|----------|-----------|
| **Realized volatility (RV)** | σ²_t = Σ_{i=1}^n (r_{t,i})² over n sub-periods (e.g., 96×15m for 24h RV) | 15m, 1h, 4h, 24h | Captures volatility regime; mean-reverting; directly observable |
| **Return quantile** | q_t = quantile(r_t | rolling window) | 15m, 1h, 4h, 24h | Captures directional regime; nonparametric |
| **Volatility change** | Δσ_t = RV_t - RV_{t-1} | 1h, 4h, 24h | Volatility momentum/mean-reversion signal |
| **Volume relative to rolling median** | vol_t / median(vol_{t-L:t}) | 1h, 4h, 24h | Liquidity/participation regime |
| **Funding rate (perps)** | 8-hour funding rate, interpolated to horizon | 4h, 24h | Basis/carry regime; mean-reverting |
| **Basis (perps - spot)** | log(perp_price / spot_price) | 4h, 24h | Arbitrage/leverage regime |
| **Open interest change** | ΔOI_t / OI_{t-1} | 4h, 24h | Positioning regime |

### 2.2 Latent (for HMM / MS Models)

| Variable | Emission Distribution | Regime Interpretation |
|----------|----------------------|----------------------|
| **Log returns** | Gaussian / Student-t | Mean/variance regimes (bull/bear/crash) |
| **Realized volatility** | Gamma / Log-normal | Volatility regimes (low/med/high) |
| **Multivariate (returns + RV)** | Multivariate t | Joint return-volatility regimes |

**Selection rule:** Start with univariate returns for HMM (H2) and RV for MS-GARCH (H3). Multivariate only if univariate fails and data supports it.

---

## 3. Candidate Forecast Horizons

| Horizon | Decision Frequency | Holding Period | Rationale |
|---------|-------------------|----------------|-----------|
| **15-minute** | 15 min | 15 min | High-frequency microstructure; tests Markov property at noise-dominated scale |
| **1-hour** | 1 hour | 1 hour | Intraday trend/mean-reversion; liquid; feasible for execution |
| **4-hour** | 4 hours | 4 hours | Funding-cycle aligned (perps); regime-persistent |
| **24-hour** | Daily | 24 hours | Swing trading; lower turnover; daily risk management |

**Primary focus:** 1-hour and 4-hour for initial validation (balance of signal-to-noise and execution feasibility). 15-minute as stress test. 24-hour for lower-turnover confirmation.

---

## 4. Point-in-Time Universe Needs

### 4.1 Instruments
- **Primary:** BTC-USDT and ETH-USDT linear perpetual futures on Binance (highest liquidity, longest history).
- **Secondary (if data permits):** SOL-USDT, BNB-USDT, XRP-USDT perps on Binance.
- **Spot reference:** BTC-USDT, ETH-USDT spot on Binance (for basis calculation).

### 4.2 Universe Construction Rules
1. **Listing date:** Instrument enters universe on first day with ≥ 90% candle completeness.
2. **Delisting:** Instrument exits on last day before delisting announcement or volume drops below 10% of 30-day median for 5 consecutive days.
3. **No look-ahead:** Universe at time t uses only instruments listed and active as of t.
4. **Manifest:** Record instrument, venue, contract type, quote currency, listing/delisting dates, and data source hash for each experiment.

### 4.3 Data Source
- **Primary:** Binance public REST API (klines, funding rate, open interest, order book snapshots).
- **Backup:** Binance public data dumps (data.binance.vision) for historical completeness.
- **Verification:** Cross-check first/last timestamps, row counts, and OHLCV consistency against alternative source (e.g., CoinAPI free tier) for overlapping periods.

---

## 5. Data-Quality Requirements

### 5.1 Pre-Processing Checks (Automated, Logged)
| Check | Threshold | Action on Failure |
|-------|-----------|-------------------|
| Monotonic timestamps | 0 violations | Quarantine segment; interpolate if < 3 consecutive missing |
| Timezone consistency | All UTC | Convert; log conversion |
| Duplicate timestamps | 0 duplicates | Keep first; log count |
| OHLCV consistency | O,H,L,C ∈ [L,H]; V ≥ 0 | Flag; impute from neighboring exchange if available |
| Missing bars | < 1% per month | Forward-fill only for features; never for labels/targets |
| Gaps > 1 hour | 0 tolerated | Split into separate segments; no interpolation across gaps |
| Outlier returns | \|r\| > 10σ (rolling 100) | Winsorize at 99.9th percentile; log original |
| Funding rate availability | ≥ 95% of 8h intervals | If < 95%, exclude funding features for that period |

### 5.2 Feature Engineering Contract
- **All transformations fit on training window only:** Rolling quantiles, means, stds, PCA, clustering, HMM parameters.
- **Expanding window:** Initial training = first 70% of data; validation = next 15%; holdout = final 15% (locked).
- **Rolling re-estimation:** Every 30 days (or 1000 bars for 15m), refit state definitions and model parameters using only data up to that point.
- **No global scaling:** No feature standardized on full sample.

### 5.3 Data Manifest (Per Experiment)
- Source endpoint, query parameters, retrieval timestamp
- Row count, date range, instrument list
- SHA256 hash of raw CSV/Parquet
- Preprocessing log (rows dropped, imputed, winsorized)
- Content hash of final feature matrix

---

## 6. Leakage Controls

| Leakage Vector | Control |
|----------------|---------|
| **State definition (quantiles, clusters, HMM params)** | Fit exclusively on training window; expanding/rolling only |
| **Label construction (future returns for supervision)** | Labels defined at t+h; model at t never sees t+1..t+h |
| **Parameter selection (K, m, horizon)** | Pre-specified in this plan; no optimization on validation/holdout |
| **Feature normalization** | Rolling statistics only; no full-sample mean/std |
| **Regime labeling (HMM smoothed probs)** | **Never used for trading simulation**; only filtered/online probs |
| **Universe construction** | Point-in-time; no future listings/delistings |
| **Cost model parameters** | Fixed ex-ante from historical analysis (see Section 9); not fit to strategy PnL |

---

## 7. Baselines

### 7.1 Statistical Baselines (Forecast Evaluation)
| Baseline | Description |
|----------|-------------|
| **Unconditional transition/return distribution** | Historical frequency over training window |
| **Single-regime GARCH(1,1)** | Standard volatility forecast |
| **RiskMetrics EWMA (λ=0.94)** | Industry standard vol forecast |
| **Rolling historical mean/vol (window=100)** | Naive adaptive benchmark |
| **Randomized/label-shuffled negative control** | Permute state labels 100×; compute null distribution of metrics |

### 7.2 Trading Baselines (Economic Evaluation)
| Baseline | Description |
|----------|-------------|
| **Buy-and-hold (BTC/ETH)** | Long-only perpetual; marks to market |
| **No-signal / no-trade** | Zero position always; measures cost drag of trading |
| **Simple momentum** | Sign(r_{t-1}) position; 1-hour horizon |
| **Volatility-state rule** | Long when RV < median(RV); flat otherwise |
| **Random forest / gradient boosting (non-Markov)** | Same features, non-sequential model; tests if Markov structure adds value |

**Baseline requirement:** All baselines use identical cost model, universe, walk-forward design, and evaluation metrics.

---

## 8. Trading-Friction Assumptions

### 8.1 Per-Trade Costs (Binance USDT-M Perps, 2024–2025 typical)
| Cost Component | Assumption | Source |
|----------------|------------|--------|
| **Maker fee** | 0.02% (0.0002) | Binance VIP 0 |
| **Taker fee** | 0.05% (0.0005) | Binance VIP 0 |
| **Spread (half-spread cost)** | 1.0 bps (0.0001) for BTC/ETH; 2.5 bps for alts | Median 1-min quoted spread |
| **Slippage (market order, $100k notional)** | 2.0 bps (0.0002) BTC/ETH; 5 bps alts | Almgren-Chriss calibration on Binance L2 data |
| **Funding (8h)** | ±0.01% per 8h (avg \|funding\|) | Historical median |
| **Borrow/short availability** | Perps: always available; no borrow cost beyond funding | Contract spec |
| **Minimum notional** | 5 USDT | Exchange rule |
| **Tick size** | 0.1 USDT (BTC), 0.01 USDT (ETH) | Exchange rule |
| **Lot size** | 0.001 BTC, 0.01 ETH | Exchange rule |

### 8.2 Cost Model Implementation
- **Default:** Taker execution (conservative) → fee = 0.05%, spread = 1 bps, slippage = 2 bps → **total round-trip ≈ 10.6 bps** for BTC/ETH.
- **Stress test:** 2× spread, 2× slippage, 2× fees → **total round-trip ≈ 21.2 bps**.
- **Funding:** Applied every 8h based on position sign and funding rate at that timestamp.
- **Turnover:** Measured as Σ \|Δposition\| / 2 per period; reported alongside returns.
- **Net return calculation:** Gross PnL - Σ(costs) - funding cashflows.

---

## 9. Walk-Forward Design

### 9.1 Chronological Splits
```
Total data: 2021-01-01 to 2025-12-31 (5 years, ~1.8M 15m bars for BTC)
├── Training (expanding):     2021-01-01 → 2023-12-31  (70%, ~3 years)
├── Validation (model select): 2024-01-01 → 2024-06-30  (15%, 6 months)
└── Holdout (locked):          2024-07-01 → 2025-12-31  (15%, 1.5 years) — NOT INSPECTED until final report
```

### 9.2 Re-Estimation Schedule
| Horizon | Re-fit Frequency | Window Type |
|---------|-----------------|-------------|
| 15m | Every 1,000 bars (~10 days) | Rolling 500,000 bars (~5 years max) |
| 1h | Every 500 bars (~21 days) | Rolling 20,000 bars (~2.3 years) |
| 4h | Every 200 bars (~33 days) | Rolling 10,000 bars (~4.5 years) |
| 24h | Every 60 bars (~60 days) | Rolling 2,500 bars (~6.8 years) |

**Expanding window for initial training; rolling window thereafter.** Window size chosen to balance parameter stability and adaptation.

### 9.3 Purging and Embargo
- **Purge:** Remove training observations where label horizon overlaps with validation/test period. For horizon h, purge h bars before each validation/test boundary.
- **Embargo:** Additional gap of h bars after purge before validation/test starts.
- **Implementation:** For 1-hour horizon, purge 1 hour + embargo 1 hour = 2 hours gap at each boundary.

### 9.4 Evaluation Points
- **Development (training + validation):** Used for model selection (K, m, features, horizon). Metrics: Brier score, log-loss, CRPS, calibration plots.
- **Holdout:** Single frozen evaluation. **No model changes after holdout evaluation begins.** Metrics: All forecast metrics + full economic simulation.

---

## 10. Uncertainty Tests

### 10.1 Statistical Uncertainty
| Test | Method |
|------|--------|
| **Transition matrix confidence intervals** | Dirichlet posterior (α=1) or bootstrap (block bootstrap, block=10×horizon) |
| **Forecast metric confidence intervals** | Block bootstrap (1000 resamples) on validation/holdout periods |
| **Effective sample size** | ESS = N / (1 + 2Σρ_k) for autocorrelated metrics |
| **Parameter sensitivity** | Re-estimate with ±10% data perturbations; report metric range |

### 10.2 Robustness Tests (Red-Team)
| Test | Description |
|------|-------------|
| **Period splitting** | Evaluate on bull (2021), bear (2022), sideways (2023), volatile (2024) sub-periods separately |
| **Asset splitting** | Train on BTC, test on ETH (and vice versa); test on alts if data permits |
| **State definition perturbation** | Quantile bins: 3, 4, 5, 6 states; clusters: K=3,4,5; economic thresholds ±10% |
| **Horizon perturbation** | Evaluate at 30m, 2h, 6h, 12h (not pre-specified) as sensitivity only |
| **Cost stress** | 2×, 5×, 10× base cost model |
| **Negative controls** | Label-shuffled transitions; random state assignments; constant forecast |
| **Multiple testing correction** | Benjamini-Hochberg FDR across all model-variant-horizon-asset combinations tried |

### 10.3 Diagnostics
- **State occupancy:** Report time spent in each state; flag states < 1% occupancy.
- **Transition counts:** Report N_{ij}; flag cells < 10 counts.
- **Regime persistence:** Expected duration 1/(1-P_{ii}); compare to empirical.
- **Forecast calibration:** Reliability diagrams for state probabilities and return quantiles.
- **Filtered vs. smoothed gap:** For HMM, report difference; large gap → real-time usability concern.

---

## 11. Explicit Go/No-Go Criteria

### 11.1 Forecast Validation Gate (Before Economic Simulation)
A model family passes to economic simulation **only if** on the **validation period**:

| Criterion | Threshold |
|-----------|-----------|
| **Calibration** | Brier score / log-loss significantly better than unconditional baseline (p < 0.05, block bootstrap) |
| **Discrimination** | CRPS or log-score significantly better than single-regime GARCH / rolling historical (p < 0.05) |
| **State stability** | No state < 1% occupancy; no transition cell < 10 counts in validation |
| **Regime persistence** | Filtered regime probabilities not switching > 50% of periods (avoids flickering) |
| **Robustness** | Skill persists across ≥ 2 of 3 sub-periods (bull/bear/sideways) |

**If NO model family passes:** STOP. Document negative result. Do not proceed to economic simulation.

### 11.2 Economic Simulation Gate (Holdout Evaluation)
A strategy is a **CANDIDATE_FOR_INDEPENDENT_CONFIRMATION** **only if** on the **locked holdout**:

| Criterion | Threshold |
|-----------|-----------|
| **Net Sharpe ratio** | > 0.5 (annualized, net of all costs) |
| **Maximum drawdown** | < 20% (net, peak-to-trough) |
| **Positive net expectancy** | Mean net daily return > 0 (t-test p < 0.1 vs. zero, HAC standard errors) |
| **Trade count** | > 100 trades (avoids lucky few-trade outcomes) |
| **Turnover** | Annualized turnover < 500% (capacity check) |
| **Baseline dominance** | Net Sharpe > best baseline (buy-and-hold, momentum, no-trade) by > 0.25 |

**If NO strategy passes:** Result = `REJECT` for that model family. Document and move to next family or new hypothesis.

### 11.3 Final Decision Mapping
| Outcome | Action |
|---------|--------|
| ≥1 strategy passes Economic Gate | `CANDIDATE_FOR_INDEPENDENT_CONFIRMATION` — freeze code, data, plan; request independent replication |
| All families fail Forecast Gate | `REJECT` — Markov structure not predictive at tested horizons/assets |
| Some pass Forecast Gate but all fail Economic Gate | `RESEARCH_MORE` — predictive but not economically exploitable; test new state variables, horizons, cost models |
| Data insufficient for any test | `BLOCKED_NO_SAFE_WORK` — create AGENT_STOP |

---

## 12. Implementation Sequence (Bounded Tasks)

| Task | Description | Deliverable | Depends On |
|------|-------------|-------------|------------|
| **T1: Data Ingestion & Manifest** | Fetch Binance klines, funding, OI for BTC/ETH perps (2021-2025); validate; produce data manifest | `data/raw/manifest.json`, `data/processed/features.parquet` | — |
| **T2: Feature Engineering & State Definition** | Build expanding-window quantile bins, clusters, HMM-ready features; unit tests for leakage | `research/specifications/feature-contract.md`, `src/features/` | T1 |
| **T3: Finite-State Chain Implementation** | MLE + Bayesian Dirichlet transition estimation; walk-forward forecasting; validation metrics | `src/models/markov_chain.py`, `results/forecast_validation/markov_chain/` | T2 |
| **T4: HMM Implementation** | Bayesian MCMC (PyMC/Stan) or MLE with multiple starts; filtered probabilities; validation | `src/models/hmm.py`, `results/forecast_validation/hmm/` | T2 |
| **T5: MS-GARCH Implementation** | 2-regime MS-GARCH via MLE (Kim filter); volatility forecast validation | `src/models/ms_garch.py`, `results/forecast_validation/ms_garch/` | T2 |
| **T6: Semi-Markov / Duration Model** | Weibull sojourn MLE on HMM regimes; duration forecast validation | `src/models/semi_markov.py`, `results/forecast_validation/semi_markov/` | T4 |
| **T7: Forecast Validation Gate Review** | Aggregate metrics; apply go/no-go criteria; document pass/fail per family | `results/forecast_validation/GATE_REVIEW.md` | T3–T6 |
| **T8: Cost Model & Execution Simulator** | Vectorized backtest engine with all frictions; unit tests vs. manual calc | `src/backtest/executor.py`, `src/backtest/cost_model.py` | T1 |
| **T9: Strategy Mapping & Economic Simulation** | For each passing family: forecast → signal → position → PnL; walk-forward on holdout | `src/strategies/`, `results/economic_simulation/` | T7 (PASS), T8 |
| **T10: Red-Team & Robustness** | Period/asset/state/cost perturbations; negative controls; multiple testing correction | `results/red_team/` | T9 |
| **T11: Final Decision Report** | Apply Economic Gate; produce `REJECT` / `RESEARCH_MORE` / `CANDIDATE` report | `results/FINAL_DECISION.md` | T10 |

---

## 13. Reproducibility Requirements

1. **Code versioning:** All code in `src/` with `requirements.txt` / `pyproject.toml` pinned versions.
2. **Experiment manifests:** Each run logs git SHA, config hash, data manifest hash, random seeds.
3. **Random seeds:** Fixed per experiment; reported in manifest.
4. **Compute environment:** Dockerfile or conda env.yml for exact reproduction.
5. **Results storage:** All outputs in `results/` with subdirectories per experiment; no overwriting.
6. **Holdout lock:** Holdout data hash recorded at start; holdout evaluation script cannot be modified after first holdout run.

---

## 14. Assumptions and Unresolved Questions

| # | Assumption / Question | Status |
|---|----------------------|--------|
| A1 | Binance public API provides complete, gap-free 15m klines for BTC/ETH 2021–2025 | To verify in T1 |
| A2 | Funding rate history available via API for full period | To verify in T1 |
| A3 | Open interest history available via API for full period | To verify in T1 |
| A4 | 3-state HMM is identifiable with ~3 years of 1h data | Simulation study needed |
| A5 | MS-GARCH(1,1) 2-regime converges reliably with rolling 2.3-year windows | Simulation study needed |
| A6 | 10.6 bps round-trip cost is conservative for $100k notional BTC/ETH perps | Validate with L2 data in T8 |
| A7 | 1.5-year holdout (2024-07 to 2025-12) is sufficient for statistical power | Power analysis needed |
| A8 | No structural break in Binance perp contract specs during period | Verify contract history |
| Q1 | Should we include spot market data for lead-lag features? | Defer unless H1–H4 fail |
| Q2 | Should we test cross-sectional (multi-asset) Markov models? | Defer; single-asset first |
| Q3 | Is 15-minute horizon viable given cost structure? | T3 will test; likely fails net |

---

## 15. Next Single Bounded Task

**Task T1: Data Ingestion & Manifest**
- Fetch Binance USDT-M perpetual klines (15m, 1h, 4h, 1d) for BTCUSDT, ETHUSDT from 2021-01-01 to 2025-12-31.
- Fetch funding rate (8h) and open interest (1h) for same.
- Run all data-quality checks (Section 5.1).
- Produce `data/raw/manifest.json` with source, row counts, date ranges, SHA256 hashes.
- Produce `data/processed/features.parquet` with aligned, validated OHLCV + funding + OI.
- **Verification:** Automated test script asserts all quality checks pass; manifest matches independent spot check.

---

**End of Initial Research Plan**

*This plan is falsifiable: every hypothesis has a null, a validation gate, and a holdout gate. No parameter optimization on holdout. All state definitions fit on training data only. Costs modeled conservatively. Red-team tests specified ex-ante.*