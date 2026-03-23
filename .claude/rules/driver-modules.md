---
paths:
  - "src/autoforge/driver/**"
---

The driver agent is the one that edits the work product. In SDK mode it runs via `Claude.query()` with `permission_mode="bypassPermissions"`. In API mode, file writes go through `_apply_file_outputs()` which enforces the `editable_files` whitelist — never write to files outside that list. The prompt builder in `prompt_builder.py` assembles 9 sections; the per-agent feedback section is critical because it's what makes the optimization loop converge.
