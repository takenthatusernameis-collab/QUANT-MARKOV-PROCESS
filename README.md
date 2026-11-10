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
2. Read [MARKOV_RESEARCH_GUIDELINES.md](MARKOV_RESEARCH_GUIDELINES.md) for the research mandate and required methodology.
3. Read [research_state/agent_handoff.md](research_state/agent_handoff.md) for the current phase and next bounded task.
4. Review existing research artifacts before starting a new experiment.

## Kilo workflow

The `.github/workflows/main.yml` file is an exact copy of the workflow at `takenthatusernameis-collab/NQ-ORB` (source blob SHA `e364e841c85cc5c8a2d075a56929650394604c98`). Its supporting controller helper and four regression-test files are also copied byte-for-byte from that repository.

The Kilo General Agent Loop is scheduled every five minutes, with a 355-minute activation cutoff, an idle watchdog, sequential worker sessions, bounded transient retries, completed-run diagnostics, recovery artifacts, and controller-verified checkpoint persistence. It can be started manually from **Actions → Kilo General Agent Loop**. The `diagnostics_only` option runs controller tests and refreshes diagnostics without starting Kilo. Workflow-file pushes run validation/diagnostics only and do not launch the worker.

Exact parity includes the source workflow's `GITHUB_TOKEN`/`GH_TOKEN` worker environment and its checkpoint behavior. Repository instructions prohibit the agent from reading, printing, or using credentials. The controller explicitly keeps workflow definitions maintainer-managed; other research-instruction restrictions are specified in the repository guidance and are not additional workflow modifications.

`AGENT_STOP` is a project-level agent instruction marker, not a GitHub Actions controller switch in this exact NQ-ORB workflow. The worker must respect it when read from the project handoff/instructions; it does not cancel an already-running workflow activation.

## Research outputs

Keep durable work under `research/` and `research_state/`. Every experiment should record its hypothesis, data provenance, point-in-time universe, state definition, model specification, walk-forward design, friction model, metrics, uncertainty, reproducibility details, and decision. Use `NOT_RUN`, `BLOCKED`, and `NOT_VERIFIED` honestly; never imply that an unexecuted test passed.
