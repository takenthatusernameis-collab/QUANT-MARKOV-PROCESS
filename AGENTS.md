# Agent instructions — Quant Markov Process

These rules apply to every agent, script, notebook, and contributor.

## Repository purpose

This is a research-only quantitative laboratory. The default research domain is liquid cryptocurrency spot and linear perpetual markets, using public, retail-accessible data. Treat that domain as a starting scope, not as evidence that any strategy is viable.

## Non-negotiable boundaries

1. **No live trading.** Do not place orders, connect to user accounts, deploy trading bots, or implement unattended execution against an exchange.
2. **No credentials.** Do not request, read, print, store, or commit API keys, tokens, passwords, wallet material, or private account data. If a data source requires credentials, mark it `BLOCKED_EXTERNAL` and find a public alternative.
3. **Real data only for empirical claims.** Synthetic data may be used for unit tests and explicitly labelled simulations only. Never silently substitute synthetic data for missing market observations or use it to support profitability claims.
4. **No paid-data dependency by default.** Prefer free public exchange endpoints and transparent open datasets. Explain any unavoidable paid/proprietary dependency before using it.
5. **No look-ahead or survivorship leakage.** Use only information available at the decision timestamp. Cross-sectional universes must be point-in-time where possible; do not backfill today's market-cap rankings into history.
6. **Protect holdouts.** Keep discovery, model selection, validation, and confirmatory evaluation distinct. Record the split and freeze candidate definitions before any final holdout access. If a valid independent holdout protocol is not yet defined, do not claim confirmatory evidence.
7. **No performance theatre.** Never present gross returns as net returns, ignore fees/funding/slippage, hide failed experiments, or promote an in-sample winner as a validated strategy.
8. **Keep the work auditable.** Record data provenance, timestamps, hashes where practical, model/state definitions, parameters, code version, commands, tests, and honest result status.
9. **Do not rewrite protected instructions.** Kilo may propose revisions in `research_state/prompt_evolution.md`; it must not edit `AGENTS.md`, files matching `*_GUIDELINES.md` or `*_RESEARCH_PROMPT.md`, or `.github/workflows/*`. The repository-agnostic controller protects these instruction-file conventions and workflow definitions before checkpointing.
10. **Respect stop conditions.** Check for `AGENT_STOP` before starting work and between tasks. If the research cycle is complete or no safe, useful task remains, create that marker with a reason and stop. Do not keep running sessions merely to consume the workflow budget.

## Research and implementation discipline

- Start with a falsifiable hypothesis and a written mathematical specification.
- Distinguish a Markov chain, a hidden Markov model, a Markov-switching time-series model, a semi-Markov process, and a Markov decision process. Do not use these names interchangeably.
- Test whether the chosen state representation is sufficiently Markovian. If relevant memory remains, investigate higher-order state, duration dependence, or alternative model families rather than hiding the problem.
- Use chronological walk-forward evaluation, training-only preprocessing, purging/embargo where labels overlap, and robust uncertainty estimates.
- Compare against simple, relevant baselines and negative controls. Report net-of-friction results and sensitivity to conservative costs.
- Prefer small, interpretable experiments over indiscriminate parameter grids. Log every attempted hypothesis, including null and failed results.
- Before changing an established candidate, preserve the old specification and explain the reason for the change.
- Do not claim tests, data retrieval, or external verification occurred unless a command or source confirms it. Use `NOT_RUN`, `BLOCKED`, `NOT_VERIFIED`, and `FAILED` accurately.

## Kilo session protocol

At the start of each session:

1. Read this file and `MARKOV_RESEARCH_GUIDELINES.md`.
2. Read `research_state/agent_handoff.md`, recent research artifacts, and the current Git history/status.
3. Verify the current task is still relevant; do not trust stale handoff claims without rechecking.
4. Complete one bounded task, test it, and preserve the evidence.
5. Update the handoff with completed work, exact verification status, blockers, and one next task.

Do not commit or push from inside Kilo. The GitHub Actions controller stages safe files, checkpoints them, pushes to `main`, and verifies the remote SHA. Do not create or modify workflow files.
