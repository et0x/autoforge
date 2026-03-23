---
description: "Project initialization, state management, git operations, iteration history, CLI commands for init/run/eval/status/history"
when_to_use: "When working on project setup, state persistence, git operations, CLI commands, or the optimization loop in engine.py"
user-invocable: true
---

# Project Setup, State, and CLI

## Project initialization (cli.py `init` command)

```bash
autoforge init <name> -p <program> [--panel <panel>] [-d <dir>]
```

**Important:** If a virtualenv is present, activate it first. Projects should be created in `projects/` (gitignored) to keep the repo root clean:

```bash
autoforge init <name> -p <program> -d projects/<name>
```

1. Creates `<dir>/.autoforge/` directory
2. Loads ProgramConfig to get defaults
3. Creates ProjectConfig with name, program, panel
4. Saves to `.autoforge/project.yaml`
5. Copies all files from the program directory (everything except `program.yaml`) into the project

## Project directory layout

```
my-project/
├── .autoforge/
│   ├── project.yaml             # ProjectConfig
│   ├── state.json               # ProjectState (written each iteration)
│   ├── history.jsonl            # Append-only, one IterationRecord per line
│   └── iterations/
│       ├── 001/scores.json      # Detailed per-agent scores
│       └── ...
├── content.md                   # Editable file(s)
├── brief.md                     # Read-only context
└── .git/                        # Created by engine on first run
```

## State management (state.py)

### ProjectState
```python
project_name: str
program_name: str
branch: str = ""               # e.g. "autoforge/my-project"
iteration: int = 0
best_score: float | None
best_iteration: int | None
direction: str                 # "minimize" or "maximize"
started_at: str | None
```

- `is_improvement(score)` — compares to best_score respecting direction
- `record(...)` — creates IterationRecord, updates best_score if improved
- `save(project_dir)` → writes `.autoforge/state.json`
- `load(project_dir)` → reads from state.json
- `append_history(project_dir, record)` → appends JSON line to history.jsonl
- `load_history(project_dir)` → returns list of IterationRecord
- `save_iteration_scores(project_dir, iteration, agent_scores, consensus)` → writes to `iterations/{iter:03d}/scores.json`

### IterationRecord
```python
iteration: int
timestamp: str                 # ISO format UTC
commit_hash: str | None
score: float
status: str                    # "baseline" | "keep" | "discard" | "crash"
description: str
duration_seconds: float
agent_scores: list[AgentScore] | None   # panel mode
raw_metrics: dict | None                # objective mode
```

### AgentScore
```python
agent: str, weight: float, score: float
reasoning: str, strengths: list[str], weaknesses: list[str]
error: bool
```

## Git operations (git_ops.py)

### GitOps class
- `__init__(working_dir, branch_prefix="autoforge")` — all git commands run in working_dir
- `init()` — `git init` + empty initial commit (if not already a repo)
- `create_branch(tag)` — creates/checks out `autoforge/<tag>`
- `commit(message, files)` — stages files (or -A), commits, returns 7-char short hash
- `revert_last()` — `git reset --hard HEAD~1`
- `get_diff()` — diff from HEAD~1
- `has_changes()` — checks `git status --porcelain`

### How the engine uses git
- On first run: `git init` + `create_branch(project_name)`
- After driver makes changes: `commit(description, editable_files)`
- If score improved: commit stays (branch advances)
- If not: `revert_last()` rolls back to previous state
- Branch tip always = best version of the work product

## The optimization loop (engine.py)

### OptimizationEngine.__init__
```python
(project_dir, project, program, ui, client?, model_override?)
```
- Sets direction from eval config
- Loads or creates ProjectState
- Creates PanelEvaluator if panel mode (with model_override)

### engine.run(max_iterations?, target_score?)

```
1. Git init + create branch
2. If iteration == 0:
   a. Run setup commands
   b. Run baseline evaluation
   c. Record "baseline"
3. Loop:
   a. Check break conditions (max_iterations, target_score)
   b. Build driver prompt (state + history + feedback)
   c. Run driver agent (sdk or api mode)
   d. Git commit the change
   e. Run evaluation (objective or panel)
   f. If improved: record "keep"
      If not: record "discard", git revert
   g. Save state
```

### Break conditions
- `max_iterations`: from CLI -n, project.yaml, or program YAML
- `target_score`: from CLI -t or project.yaml. Uses `_target_reached()` which respects direction.

## CLI commands

### `autoforge run [-n N] [-t SCORE] [-m MODEL] [-c CONTEXT] [-C FILE] [-s SKILL_DIR] [-d DIR]`
- `-c` / `--context`: ad-hoc context string, injected into driver + evaluator prompts. Repeatable.
- `-C` / `--context-file`: read context from a file. Repeatable.
- `-s` / `--skill-dir`: add skill directory for all agents (driver + evaluators). Repeatable.
- All flags are additive — merged with project.yaml `extra_context` and agent YAML `skill_dirs`.
- Context is built by `_build_extra_context()` in cli.py, then passed to engine.
- Skill dirs are passed as `extra_skill_dirs` to engine and PanelEvaluator.

### `autoforge eval [--agent NAME -f FILE] [-m MODEL] [-c CONTEXT] [-C FILE] [-s SKILL_DIR] [-d DIR]`
- Accepts the same context and skill flags as `run`
- Single agent test: loads agent, applies overrides, reads file, runs one evaluation
- Full panel test: loads project panel, applies overrides, reads editable files, runs panel evaluation

### `autoforge status [-d DIR]`
- Prints: project name, program, panel, iteration, best score, direction

### `autoforge history [-d DIR] [-n LAST]`
- Loads history.jsonl, displays Rich table with last N iterations

### `autoforge program list|show`
- Lists all programs from config resolution (project → user → built-in)

### `autoforge agent list|show`
- Lists all agent personas

### `autoforge panel list|show`
- Lists panels; `show` displays member weights with bar visualization

## UI (ui/progress.py)

### ProgressUI
- `show_header()` — project/program/eval info panel
- `show_baseline(score)` — initial score
- `start_iteration(n)` — rule separator
- `show_phase(text)` — "Driver thinking...", "Evaluating..."
- `show_proposal(desc)` — what the driver proposes
- `on_agent_score(score)` — live update as each evaluator finishes (shows bar + score + weight)
- `show_kept(iter, score, desc, best)` — green, with delta
- `show_discarded(iter, score, desc, best)` — dim red, with delta
- `show_complete(state)` / `show_target_reached(state, target)` — final summary + history table

### Theme colors (ui/console.py)
keep=green, discard=dim red, crash=bold red, baseline=cyan, score=yellow, agent=blue, phase=dim italic, header=bold white on dark_blue
