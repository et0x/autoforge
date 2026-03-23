---
paths:
  - "library/**/*.yaml"
---

YAML config files are validated by Pydantic models in `src/autoforge/config.py`. Panel weights must sum to 1.0. Agent `mode` must be "api" or "sdk". Program `eval_mode` must be "objective" or "panel". All fields have defaults except `name`, `system_prompt` (agents), `editable_files` and `eval_mode` (programs), and `members` (panels).
