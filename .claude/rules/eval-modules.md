---
paths:
  - "src/autoforge/eval/**"
---

All evaluation code is async. Agent runner uses `asyncio.gather()` for parallel execution. API-mode agents use forced `tool_choice` for structured output. SDK-mode agents parse text output. Error handling always returns score=5.0 with error=True rather than raising — the loop must never crash from a single agent failure. The `on_score` callback is awaited (it's async) for live UI updates.
