# 0002 — Accessibility-style DOM snapshots over screenshots for observation

**Status:** accepted

## Context
The operator must observe web apps reliably with free-tier models. Vision-based computer use is
general but slow, expensive and imprecise for clicking; free models handle text far better.

## Decision
After every browser action, a script tags visible interactive elements with stable refs
(`[e7]`), captures form metadata (method, action, current field values), alerts, headings and
tables, and waits for the page to settle (element count stable). The model acts by ref.
Screenshots are still taken — as evidence for humans, not as model input.

## Consequences
- Precise, cheap actions; validation messages and status codes are visible as text.
- Form metadata lets policy see exactly what a submit would send before it is sent.
- Canvas-heavy or desktop apps are out of scope; a vision fallback is listed under next steps.
