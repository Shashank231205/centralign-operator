# 0007 — A realistic sandbox company with seeded chaos

**Status:** accepted

## Context
The brief forbids real company systems. A mock that always behaves would only demonstrate the
happy path, which is the least interesting part of an autonomous system.

## Decision
Two separate apps with their own databases and sessions: SupplyLink (supplier portal; amounts
and due dates only inside downloadable PDFs, one of which carries a prompt-injection note) and
Ledgerly (ERP UI with strict legacy validation, plus a read API). Chaos is env-configurable and
seeded: random 503s, slow responses, late-rendering forms, session expiry, alternative button
labels, and an acknowledgement-loss trap where a create commits but the client receives a 502.

## Consequences
- Recovery, re-login, validation learning, injection resistance and duplicate prevention are
  exercised, not assumed.
- Fixed seeds make failure scenarios reproducible in tests and demos.
