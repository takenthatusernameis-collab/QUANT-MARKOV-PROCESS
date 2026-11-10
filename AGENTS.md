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
9. **Keep research instructions human-managed.** Kilo may propose revisions in `research_state/prompt_evolution.md`; it must not edit `AGENTS.md`, files matching `*_GUIDELINES.md` or `*_RESEARCH_PROMPT.md`, or `.github/workflows/*` unless the user explicitly authorizes that exact change. The exact NQ-ORB workflow copy explicitly keeps `.github/workflows/*` maintainer-managed, but does not enforce the other instruction-file restrictions in its controller code; follow this rule as an agent instruction.
10. **Respect stop conditions.** Check for `AGENT_STOP` before starting work and between tasks. If the research cycle is complete or no safe, useful task remains, create that marker with a reason, mark the durable handoff complete, and do not start another task. The exact NQ-ORB workflow does not interpret `AGENT_STOP` as a controller-level cancellation switch, so the agent itself must obey the marker.

## Project-specific research specification

The complete Markov research specification—including model-family scope, research questions, mathematical and data contracts, validation protocol, baselines, trading costs, discovery priorities, deliverables, and completion gates—lives in `MARKOV_RESEARCH_PROMPT.md`.

Treat that file as the authoritative written prompt for project-specific research. Keep those specifications out of `.github/workflows/main.yml`; the workflow must remain the unchanged general-purpose NQ-ORB workflow copy. Changes to the research prompt are text-guidance changes, not workflow-code changes.

## Kilo session protocol

At the start of each session:

1. Read this file and `MARKOV_RESEARCH_PROMPT.md`.
2. Read `research_state/agent_handoff.md`, recent research artifacts, and the current Git history/status.
3. Verify the current task is still relevant; do not trust stale handoff claims without rechecking.
4. Complete one bounded task, test it, and preserve the evidence.
5. Update the handoff with completed work, exact verification status, blockers, and one next task.

Do not commit or push from inside Kilo. The GitHub Actions controller stages changes, manages checkpoints, pushes to `main`, and verifies the remote SHA. The copied NQ-ORB workflow provides `GITHUB_TOKEN` and `GH_TOKEN` in the worker step environment; do not read, print, or use those values. Do not create or modify workflow files.
