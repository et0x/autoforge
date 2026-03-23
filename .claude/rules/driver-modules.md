---
paths:
  - "src/autoforge/driver/**"
---

The driver agent is the one that edits the work product. It runs via `Claude.query()` with `permission_mode="bypassPermissions"`. The prompt builder in `prompt_builder.py` assembles 9 sections; the per-agent feedback section is critical because it's what makes the optimization loop converge.
