# 0001 — Custom agent runtime instead of an agent framework

**Status:** accepted

## Context
The assessment is about autonomy, reliability and verification, and about being able to explain
every decision the agent makes. Frameworks (LangChain, CrewAI, LangGraph) give a fast start but
hide the loop, checkpointing and error handling behind abstractions I would have to work around
for durable pauses, payload-bound approvals and independent verification.

## Decision
A small explicit state machine (`agent/runtime`) drives the run. Each status has one handler;
every transition is checked against an allow-list, checkpointed, and emitted as an event.
LLM calls are four typed stages with versioned prompt files.

## Consequences
- The whole loop is ~400 lines that can be read, debugged and modified live.
- Durable resume, approvals and idempotency are first-class rather than bolted on.
- I own features a framework would provide (tool schemas, structured output repair); they are
  small and tested.
