# 0004 — Policy-driven, payload-bound human approvals

**Status:** accepted

## Context
An AI employee must ask for help only when needed, and approvals must be meaningful: a human
approves *specific data*, not the model's description of what it intends to do.

## Decision
Tools assess each action before execution (risk, system, exact payload). Rules in
`company_context/policies.yaml` decide allow / require approval / forbid by evaluating
conditions on that payload (e.g. `amount > 5000`, `contact_email exists`, `status == paid`).
An approval becomes a single-use grant bound to the system and payload (or the approver's
edited values). The run pauses durably and resumes on any worker; when the agent redoes the
steps, the matching write passes without asking again. Rejections become feedback for the agent
and are stored in company memory.

## Consequences
- Approval survives worker restarts and fresh browser sessions.
- Edits are enforced: a write that doesn't match the edited payload asks again.
- Policies are company data, changeable without code.
