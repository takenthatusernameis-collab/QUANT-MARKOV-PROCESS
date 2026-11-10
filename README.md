# Quant Markov Process Research

A research-only laboratory for testing whether Markov, hidden-Markov, regime-switching, and semi-Markov models reveal robust, tradable structure in liquid crypto markets.

## Research boundary

- Research, simulation, and reproducible backtests only. No live orders, account access, exchange credentials, or deployment.
- Prefer free, public, exchange-available data. Never silently replace unavailable real data with synthetic data.
- Separate model discovery, parameter selection, validation, and any eventual confirmatory evaluation. Do not inspect or tune against a locked final holdout.
- Include realistic trading frictions: fees, spread, slippage, funding, borrow/short constraints, turnover, and minimum order sizes where relevant.
- Preserve negative results and report uncertainty. A positive backtest is not proof of an edge.

## Start here

1. Read [AGENTS.md](AGENTS.md) for repository-wide research and engineering constraints.
2. Read [KILO_RESEARCH_PROMPT.md](KILO_RESEARCH_PROMPT.md) for the research mandate and required methodology.
3. Read [research_state/agent_handoff.md](research_state/agent_handoff.md) for the current phase and next bounded task.
4. Review existing research artifacts before starting a new experiment.

## Kilo workflow

The Kilo General Agent Loop is scheduled every five minutes; each activation has a 355-minute safety cutoff, bounded sequential sessions, an idle watchdog, completed-run diagnostics, retry/backoff, and controller-owned checkpoints with remote SHA verification. It can also be started manually from **Actions → Kilo General Agent Loop**. Use the `diagnostics_only` option to run controller tests and refresh diagnostics without starting Kilo. Workflow-file pushes run validation only and never launch the worker. The controller does not expose the repository write token to Kilo and does not allow the agent to edit workflow definitions or protected research instructions.

Create `research_state/STOP` with a concise reason to stop future research sessions. The scheduled workflow will then exit before starting Kilo. Remove that marker in a reviewed commit to resume.

## Research outputs

Keep durable work under `research/` and `research_state/`. Every experiment should record its hypothesis, data provenance, point-in-time universe, state definition, model specification, walk-forward design, friction model, metrics, uncertainty, reproducibility details, and decision. Use `NOT_RUN`, `BLOCKED`, and `NOT_VERIFIED` honestly; never imply that an unexecuted test passed.
