---
description: "Program YAML schema, creating new programs, template files, driver config, eval modes"
when_to_use: "When creating or modifying program templates, configuring driver agents, or setting up objective vs panel evaluation"
user-invocable: true
---

# Programs

A program defines what is being optimized, what files are editable, how to evaluate, and how the driver agent behaves. Programs are YAML files in `library/programs/`.

## ProgramConfig fields (src/autoforge/config.py)

```yaml
name: str                          # required
description: str                   # default ""
version: str                       # default "1.0"

# File access
editable_files: list[str]          # required, glob patterns the driver can modify
read_only_files: list[str]         # default [], context files the driver can read

# Evaluation mode
eval_mode: "objective" | "panel"   # required
objective:                         # required if eval_mode is "objective"
  run_command: str                 # shell command to execute
  metric_extract: str              # command to extract metric (e.g. grep)
  metric_name: str                 # default "score"
  metric_regex: str                # default r"[\d.]+" — regex to parse float
  direction: "minimize"|"maximize" # default "minimize"
  timeout_seconds: int             # default 600
  setup_command: str | null        # one-time setup, default null
default_panel: str | null          # panel name, required if eval_mode is "panel"
panel_eval:                        # optional override
  panel: str
  target_files: list[str]
  context_files: list[str]

# Driver agent configuration
driver_instructions: str           # default "" — the "program.md" equivalent
driver_model: str                  # default "sonnet" — short name or full model ID
driver_mode: "sdk" | "api"        # default "sdk"
driver_tools: list[str]            # default ["Read","Edit","Write","Glob","Grep","Bash"]
driver_mcp_servers: dict           # default {} — MCP server configs
driver_skill_dirs: list[str]       # default [] — directories with skills
driver_max_turns: int | null       # default null (unlimited)

# Loop behavior
simplicity_criterion: bool         # default true — prefer simpler changes
max_iterations: int | null         # default null (run forever)
never_stop: bool                   # default true

# Setup
setup_commands: list[str]          # default [] — run once at start
# Template files: any files in the program directory (besides program.yaml) are
# automatically copied into the project on `autoforge init`. No config needed.
```

## Validation rules

- If `eval_mode: objective`, the `objective` block is required.
- If `eval_mode: panel`, either `default_panel` or `panel_eval.panel` is required.
- Validated by `_check_eval_config` model_validator in ProgramConfig.

## Built-in programs

### content-optimization
- Edits `content.md`, reads `brief.md`
- Panel mode with `linkedin-professional` default panel
- Driver mode: `api` (single-turn, text in/out)
- max_iterations: 50

### ml-training
- Edits `train.py`, reads `prepare.py`
- Objective mode: runs `uv run train.py`, extracts `val_bpb`, minimizes
- Driver mode: `sdk` (full Claude Code session for code editing)
- Template files: `train.py`, `prepare.py` (in `library/programs/ml-training/`, copied on init)
- never_stop: true

## Program directory structure

Each program is a directory under `library/programs/`:

```
library/programs/
├── content-optimization/
│   └── program.yaml
└── ml-training/
    ├── program.yaml     # the config (required)
    ├── train.py          # template file (copied on init)
    └── prepare.py        # template file (copied on init)
```

`program.yaml` is the config. Everything else in the directory is copied into the project on `autoforge init`. No need to list template files explicitly — any file that isn't `program.yaml` gets copied.

## Creating a new program

1. Create a directory: `library/programs/my-program/` (or `~/.autoforge/library/programs/my-program/` for global, or `<project>/.autoforge/programs/my-program/` for project-local)
2. Add `program.yaml` with editable_files, eval_mode, and driver_instructions at minimum
3. Add any template files that should be copied into projects on init
4. For objective mode: define the run_command, metric_extract, and direction
5. For panel mode: set default_panel to an existing panel name

Config resolution also supports flat files (`<name>.yaml`) for simple programs with no template files.

## Driver modes

- **sdk**: Full Claude Code session via `Claude.query()`. The driver can read files, run bash, use MCPs, invoke skills. Best for code editing (ml-training).
- **api**: Single Anthropic API call. File contents are included in the prompt, modified contents are parsed from the response using `FILE:` blocks. Best for text content (content-optimization).
