# Research prompt evolution ledger

Record proposed changes to the research mandate here. Do not edit `AGENTS.md` or files matching `*_GUIDELINES.md` / `*_RESEARCH_PROMPT.md` autonomously.

For each proposal record:
- observed failure or ambiguity;
- evidence from a run, test, data artifact, or review;
- whether the cause is a prompt gap, implementation defect, data/provider limitation, or methodology limitation;
- exact proposed wording and expected effect;
- regression cases that would demonstrate the improvement;
- whether the proposal is pending human review or was accepted.

Do not revise the prompt merely because a session found an implementation bug, a transient provider failure, or an inconvenient research result. Prompt changes must address demonstrated instruction gaps and must not weaken statistical, data, or authorization safeguards.

---

## PE-001 — Quiescence rule for a persistent `AGENT_STOP` (pending human review, 2026-11-13T11:15:15Z)

**Observed failure / ambiguity:** The session operating protocol (`AGENTS.md` §"Kilo session protocol" and `MARKOV_RESEARCH_PROMPT.md` §9) tells every session to "complete one bounded task" and to update the handoff. With `AGENT_STOP` present, the only available bounded task is "re-verify the stop state". Sessions have executed that task ~50 times over ~20 hours, appending a new near-identical checkpoint each time. The handoff grew from ~146 to ~259 lines, of which ~40 blocks were duplicates, degrading the clarity of the next-agent task message without adding evidence.

**Evidence:** `git log -p research_state/agent_handoff.md` shows repeated single-paragraph additions with identical content (2026-11-12T14:28:55Z–2026-11-13T10:39:09Z); `research_state/workflow_run_diagnostics.jsonl` records ~11 recurring scheduled runs whose only visible edit signal is the handoff checkpoint paragraph. This session compacted those blocks into one entry and a per-HEAD table, recovering readability with no information loss (all 131 distinct short SHAs retained, verified by `comm`).

**Cause:** instruction gap — the protocol has no rule for an unchanged, stop-respecting repository state.

**Proposed wording (addition to `MARKOV_RESEARCH_PROMPT.md` §9, step 6, or equivalent `AGENTS.md` text):**
> "If the repository state (stop marker presence and reason, frozen protocol hash, HEAD ancestry, protected-file diff, and verification results) is unchanged from the most recent handoff checkpoint, do not append a new checkpoint. Refresh the existing entry in place and record `NO_NEW_INFORMATION` with the timestamp. Append a new entry only when a checkpoint-eligible fact changed (new HEAD with different content, protocol change, authorized scope change, new evidence, or a blocked/completed task)."

**Expected effect:** bounded handoff growth under a persistent stop; cheaper sessions; a next-agent message that stays readable; no change to stop, authorization, or holdout safeguards.

**Regression cases that would demonstrate the improvement:** (a) after `AGENT_STOP` removal with recorded authorization, a new checkpoint **must** be appended; (b) a protocol-hash change **must** produce a new entry; (c) two consecutive no-change sessions must produce one entry, not two.

---

## PE-002 — Provision or classify runtime verification failures (pending human review, 2026-11-13T11:15:15Z)

**Observed failure / ambiguity:** Many scheduled sessions could not execute runtime verification, and some reported results as "carried forward" for many consecutive sessions. This session found the scratch venv `/home/runner/work/_temp/kilo-tmp/qmp-venv` missing entirely and had to rebuild it from `requirements.txt`.

**Evidence:** `research_state/workflow_run_diagnostics.jsonl` excerpts show `ModuleNotFoundError: No module named 'numpy'` in runs 42969266625, 43031156682, and 43355795203; handoff entries at 2026-11-13T07:25:09Z–07:29:57Z and 05:21:21Z–06:35:51Z record "not executable (missing numpy/pytest)" and "tests carried forward". The venv is under `/home/runner/work/_temp/`, which is ephemeral across runner machines.

**Cause:** environment / process gap — the verification step has no dependency provisioning and no required failure classification, and the handoff protocol permits indefinite carry-forward of unverified results.

**Proposed wording (addition to the session operating protocol):**
> "Before any verification command, ensure a virtual environment with `requirements.txt` installed exists at a stable path, or create one. If provisioning or execution fails, do not report results as verified or carry them forward indefinitely: record `BLOCKED_ENVIRONMENT` with the exact command and error, and mark dependent claims as unverified in this session."

**Expected effect:** each session either produces real runtime evidence or an explicit, classified environment block; unverified carry-forward no longer silently masquerades as verification.

**Regression cases:** (a) a session with deps present must run and report guard EXIT codes and test counts; (b) a session with provisioning failure must write `BLOCKED_ENVIRONMENT` and must not state pass counts it did not observe.