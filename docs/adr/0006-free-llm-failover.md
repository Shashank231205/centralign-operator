# 0006 — Free LLM backends behind a failover router

**Status:** accepted

## Context
The prototype runs on free tiers (Groq, Gemini) plus a local model (Ollama). Free tiers rate
limit aggressively, and native tool-calling support differs between them.

## Decision
One OpenAI-compatible HTTP adapter serves all three. A router tries backends in configured
order; each has a distributed token bucket, a concurrency cap and a circuit breaker. A 429
fails over immediately; other transient errors get one quick retry first. Structured output is
enforced by the application: JSON schema in the prompt, Pydantic validation, and repair turns
that feed validation errors back. Deterministic calls (understanding, first plan) are cached by
model chain + prompt version + inputs.

## Consequences
- Any OpenAI-compatible endpoint (including paid models) is a configuration change.
- Behaviour is consistent across backends because validation doesn't depend on provider features.
- Smaller local models are slower and less accurate; they are the last resort, not the default.
