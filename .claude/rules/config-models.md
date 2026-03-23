---
paths:
  - "src/autoforge/config.py"
---

All config models are Pydantic v2 BaseModel. Use `model_validator(mode="after")` for cross-field validation. Use `model_copy(update={...})` for creating modified copies (e.g. model override). Use `Field(default_factory=...)` for mutable defaults. Short model names (haiku/sonnet/opus) are mapped to full IDs by `resolve_model()` at the bottom of this file — always pass through resolve_model before hitting the API.
