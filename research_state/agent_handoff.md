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

## First task

Read `MARKOV_RESEARCH_PROMPT.md` before beginning; it defines the project-specific model scope and research standards.

Produce a sourced literature and methodology review in `research/literature/markov-processes-in-finance.md` and a companion falsifiable research plan in `research/specifications/initial-research-plan.md`.

The review should distinguish:
- finite-state Markov chains and higher-order chains;
- hidden Markov models and latent-regime switching;
- Markov-switching autoregressive/volatility models;
- semi-Markov and duration-dependent models;
- Markov decision processes, only where actions and rewards are explicitly modelled.

For each family, explain the mathematical assumptions, what it can forecast, key limitations, minimum data requirements, practical estimation options, and the principal ways a trading backtest can be fooled. Use primary papers or credible academic references where possible; include title, authors, publication year, and a working source link. Clearly separate sourced findings from the agent's interpretation.

The research plan must define testable hypotheses, plausible state variables, candidate forecast horizons, point-in-time universe needs, data-quality requirements, leakage controls, baselines, trading-friction assumptions, walk-forward design, uncertainty tests, and explicit go/no-go criteria. Do not start broad parameter optimization or inspect a final holdout while this design is being established.

## Required next-session handoff

Update this file with:
1. the exact files changed;
2. concise findings and sources;
3. commands/tests actually run and their actual outcomes;
4. assumptions or unresolved questions;
5. the next single bounded task.

## Stop rule

When the research has no remaining high-value, safe task, or the agreed research cycle has been completed, write `AGENT_STOP` with the reason and set this handoff status to `COMPLETE` or `BLOCKED_NO_SAFE_WORK`. Do not create a STOP marker merely because one data provider is unavailable if useful independent literature or methodology work remains.
