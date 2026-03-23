---
description: "Driver agent prompt building, how evaluator feedback flows into the next iteration"
when_to_use: "When modifying the driver agent, changing how prompts are built, or working on driver/driver.py or driver/prompt_builder.py"
user-invocable: true
---

# Driver Agent

The driver agent reads evaluation feedback and proposes the next change to the work product. It is the agent that actually edits files.

## Execution (driver/driver.py)

### `run_driver_sdk()`
- Full Claude Code session via `claude_query()`
- `ClaudeCodeOptions`: model, cwd=workspace, allowed_tools, permission_mode="bypassPermissions"
- Can use tools: Read, Edit, Write, Glob, Grep, Bash (defaults)
- Can invoke skills if `skill_dirs` provided (auto-adds "Skill" to allowed_tools, passes dirs as `add_dirs`)
- Can use MCPs if `mcp_servers` provided (converted via `_build_mcp_servers()`)
- `max_turns` limits agent turns
- Captures final text message as description of change

## Prompt structure (driver/prompt_builder.py)

`build_driver_prompt()` assembles these sections in order:

### 1. Optimization Instructions
From `program.driver_instructions`. This is the "program.md" equivalent — tells the driver what it's optimizing and how to approach it.

### 2. Current State
```
- Iteration: {N+1}
- Best score: {best_score} (iteration {best_iteration})
- Direction: {higher/lower} is better
```

### 3. Additional Context
From `project.extra_context` — audience, goals, constraints set by the user.

### 4. Recent History (last 10 iterations)
```
Iter    Score  Status    Description
───    ──────  ────────  ──────────────
  1    5.2000  baseline  Initial baseline
  2    5.8000  keep      Restructured opening
  3    5.6000  discard   Tried bullet points
```

### 5. Feedback from Last Evaluation
Per-agent breakdown sorted by weight (highest first):
```
**national-security-language** (7.5, w=0.25): The revised executive summary demonstrates strong...
  → Fix: Section 3 lacks specific policy recommendations
```

This is what makes the loop work — the driver sees exactly which evaluator scored what, why, and what they want improved. It can strategically target the highest-weighted evaluator's weaknesses.

### 6. Editable Files
Full contents of all files matching `program.editable_files` glob patterns.

### 7. Read-Only Context Files
Full contents of `program.read_only_files`, marked with `(DO NOT EDIT)`.

### 8. Constraints
- Which files are editable vs read-only
- Simplicity criterion (if enabled): "Prefer simpler changes"
- "Make ONE focused change per iteration"

### 9. Task Instructions
```
1. Review the current state, history, and feedback
2. Decide on a single focused improvement to try
3. Edit the editable file(s) to implement your change
4. Respond with a SHORT description (one line) of what you changed
```

## Model precedence for driver

CLI `--model` > project.yaml `driver_model` > program YAML `driver_model`

Resolved in engine.py:
```python
model = self.model_override or self.project.driver_model or self.program.driver_model
```

## MCP server conversion

`_build_mcp_servers(raw_dict)` converts YAML config dicts to SDK types:
- `type: stdio` → `McpStdioServerConfig(command, args, env)`
- `type: http` or `sse` → `McpHttpServerConfig(type="http", url, headers)`
