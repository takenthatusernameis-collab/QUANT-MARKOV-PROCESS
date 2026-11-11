# Final research decision report — Quant Markov Process

**Repository:** `takenthatusernameis-collab/QUANT-MARKOV-PROCESS`
**Branch:** `main`
**Date:** 2026-11-11
**Phase:** `DISCOVERY_AND_METHOD_DESIGN` (validation-only cycle closed)
**Decision:** `RESEARCH_MORE` (no holdout executed; not a trading/deployment authorization)

## Scope and mandate
Research-only evaluation of Markov-process-based representations for liquid crypto (BTCUSDT/ETHUSDT 1h, Binance USDT-M perp public data). No live trading, no credentials, no workflow/prompt/guideline edits, no locked holdout execution (runner refused by default; no explicit in-session authorization received).

## Evidence summary (validation-only)

### Forecast validation (BTCUSDT 1h, 2024-01-01 to 2024-06-30, holdout excluded)
- **C1 Filtered 3-state Gaussian HMM (T4):** log score 4.0164, CRPS 0.002597 vs unconditional 3.7704/0.002854 and EWMA 3.9022/0.002631. Significantly beats unconditional on both (bootstrap p<0.001) but **not** EWMA on log score (p=0.44); EWMA significantly better on CRPS (p=0.006).
- **C2 Higher-order Markov (H3, best non-latent MC):** log score 3.8585, CRPS 0.002687. Significantly better than H1 canonical and unconditional on aligned comparisons but **not significantly different from EWMA** on log score or CRPS.
- **Baselines/models:** EWMA Gaussian (λ=0.94) strong across configs; semi-Markov ≈ first-order MC (minimal duration effect); H1 sensitivity (K/binning) does not overturn EWMA dominance.
- **Calibration:** PIT means ~0.50 with near-uniform spread on reported models (diagnostic, not sufficient for economic edge).

### Economic feasibility (T5a validation dry-run)
- Frozen signal/cost protocol (base ~16 bps round-trip, stress ~32 bps, θ∈{0,2,5} bps, fixed sizing): **zero trades** for C1/C2 in all tested configurations (max |forecast μ| ~3–7 bps << cost thresholds).
- Baselines: no-trade Sharpe 0.0; buy-and-hold positive in period; momentum generated trades (not comparable). Gate criteria (Sharpe/DD/expectancy/trade count/turnover/baseline margin) not satisfied by C1/C2.

### Robustness / red-team (validation-only)
- **Period perturbation Q1 vs Q2 (BTCUSDT, C1/C2):** material instability in raw scores and paired-diff significance vs baselines across subperiods; C1 edges vs unconditional not stable in Q2; C2 not significant vs unconditional on log in either subperiod.
- **Asset perturbation ETHUSDT (C1 HMM):** point estimates beat unconditional/EWMA on log score and tie EWMA on CRPS (contrast with BTC), indicating forecast edge **not consistent across assets**; bootstrap significance not recomputed.
- **Negative controls (C1/C2, saved BTCUSDT grids):** C1 significantly beats white-noise and target-shuffled on log score (p=0.0025/p=0.000) but CRPS edge vs white noise not significant (p=0.37). C2 significantly beats shuffled on log score (p=0.0035) but shows **no significant log-score edge vs white noise (p=0.37) and significantly worse CRPS than white noise (p=0.0005)**; shuffled vs white noise not significant for C2. Confirms limited/fragile skill, especially for C2.

### Methodological caveats
- HMM EM non-convergence warnings/init sensitivity on some refits; train-vs-validation transition non-stationarity (Chow p=0.0042).
- Discretization/state-definition choices material (H1 sensitivity); bootstrap used Gaussian/moment approximations consistent with saved artifacts where mixture components unavailable.
- Effective sample sizes reduced by temporal dependence; multiple comparisons not exhaustively FDR-controlled across all historical variants.

## Decision

**`RESEARCH_MORE`** — not `REJECT` of the entire Markov research program, but current C1/C2 candidates on the tested 1h BTCUSDT/ETHUSDT validation design do **not** demonstrate robust, executable-after-costs predictive edge. Locked holdout evaluation is **not executed** (and should not be run without explicit authorization and a justified, predeclared rationale given current evidence).

**Rationale:** (1) Economic gate highly unlikely to clear given zero-trade validation dry-run and forecast magnitudes below conservative costs. (2) Statistical skill is fragile: C1 not reliably better than EWMA and unstable across period/asset; C2 weak vs white-noise/CRPS. (3) Predeclared validation/robustness evidence is sufficient to pause this candidate cycle without consuming holdout.

## Recommended next work (if continued, no prompt/workflow changes)
- Generate **materially different** hypotheses/model families or state representations (e.g. alternative horizons/instruments with justified cost models, feature/state definitions fitted point-in-time with sensitivity, or models targeting volatility/liquidity states rather than small mean returns) only with falsifiable predeclared criteria.
- Revisit cost/decision mapping only if supported by defensible microstructure evidence; do not lower costs or retune thresholds to rescue candidates.
- If a genuinely new candidate passes validation and robustness gates, design/authorize a single frozen holdout evaluation per protocol.

## Artifacts (key)
- Handoff: `research_state/agent_handoff.md`
- Literature/plan: `research/literature/markov-processes-in-finance.md`, `research/specifications/initial-research-plan.md`, `research/specifications/holdout_evaluation_protocol.md`
- EDA/HMM: `research/eda/*`, `research/forecasts/h2_hmm_validation*`
- MC baselines: `research/forecasts/h1_*`, `h3_*`, `h4_*`, `cross_family_validation_comparison.md`
- Robustness: `research/forecasts/h2_hmm_validation_ethusdt.*`, `research/forecasts/period_perturbation_q1q2.*`, `research/forecasts/negative_controls.*`
- Economic dry-run: `research/economic/validation_dryrun/*`
- Holdout runner (refusal enforced): `src/holdout_runner.py`

**Stop:** `AGENT_STOP` created with reason; no further autonomous research tasks started.
