---
paths:
  - "src/autoforge/eval/**"
---

All evaluation code is async. Agent runner uses `asyncio.gather()` for parallel execution. All agents run via the Claude Code SDK and return text output parsed for SCORE/REASONING/WEAKNESS. Error handling always returns score=5.0 with error=True rather than raising — the loop must never crash from a single agent failure. The `on_score` callback is awaited (it's async) for live UI updates.
