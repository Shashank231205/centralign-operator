# 0003 — Independent verification against systems of record

**Status:** accepted

## Context
"The form said saved" is not proof. Agents that self-report success are the main source of
silent failures, and retries after lost acknowledgements cause duplicates.

## Decision
The planner must emit machine-checkable success criteria (HTTP JSON checks against read APIs,
file checks compared to a source system), with `{{facts.x}}` placeholders filled from what the
run discovered. The verifier re-reads the systems fresh and evaluates every criterion in code,
normalising numbers and dates across formats. On failure: one targeted repair (re-plan), then
fail with evidence. The same check runs before every write as an idempotency guard.

## Consequences
- Completion means the outcome exists in the system of record, independently confirmed.
- Duplicate writes after retries, resumes or lost acknowledgements are prevented by design.
- Tasks need some readable source of truth; the procedures name one per task type.
