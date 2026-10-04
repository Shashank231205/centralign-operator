# 0005 — Queue-based execution with checkpoints

**Status:** accepted

## Context
Runs take minutes, pause for humans for hours, and must survive deploys and crashes.

## Decision
`POST /tasks` persists the run and enqueues it (202). arq workers execute runs under a Redis
lock. The runtime checkpoints the full `RunState` (JSONB) after every transition; arq retries a
killed job, and the worker resumes from the checkpoint. If every LLM backend is down, the job is
deferred instead of failed. Live progress reaches clients via Redis pub/sub and SSE, replaying
the audit log first so reconnects never miss events.

## Consequences
- API latency is independent of agent work; throughput scales with worker count.
- At most one step is repeated after a crash, and writes are guarded by the idempotency check.
- Browser state is not persisted (session cookies are not stored at rest); a resumed run signs
  in again, which the agent handles as a normal observation.
