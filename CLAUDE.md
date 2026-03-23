# Autoforge

Autonomous optimization framework. Iteratively improves a work product by having a **driver agent** propose changes and a **panel of evaluator agents** score them in parallel, keeping changes that improve the weighted consensus score.

## Stack

Python 3.10+. Pydantic models for config. Typer CLI. Rich terminal UI. Anthropic API for evaluators. Claude Code SDK for driver and SDK-mode evaluators. YAML configs for programs, agents, and panels.

## Package layout

- `src/autoforge/` — all source code, installed as `autoforge` package
- `library/` — built-in YAML templates (programs, agents, panels) + ML template files
- `projects/` — user project directories (gitignored), created by `autoforge init`
- CLI entry point: `autoforge` (mapped to `autoforge.cli:app`)

## Running CLI commands

If a virtualenv is present, activate it before running `autoforge` commands. Projects should be created inside `projects/` (gitignored) to avoid polluting the repo root:

```bash
autoforge init <name> -d projects/<name> [--program ...] [--panel ...]
```

## Key concepts

- **Program** — defines what to optimize and how to evaluate (YAML in `library/programs/`)
- **Agent** — evaluator persona with system prompt and scoring rubric (YAML in `library/agents/`)
- **Panel** — weighted set of agents whose scores combine into consensus (YAML in `library/panels/`)
- **Project** — user's working directory with `.autoforge/` state, created by `autoforge init`
- **Driver** — the agent that reads evaluator feedback and proposes the next change (`src/autoforge/driver/`)

## Config resolution

Project-local `.autoforge/<kind>/` > user-global `~/.autoforge/library/<kind>/` > built-in `library/<kind>/`.

## Critical conventions

- All config models are Pydantic v2 (`BaseModel` with `model_validator`, `model_copy`, `model_dump`)
- Model names can be short (`haiku`, `sonnet`, `opus`) or full IDs — `resolve_model()` in config.py handles mapping
- Panel weights must sum to 1.0
- `--model` CLI flag overrides all agent models (driver + evaluators)
- `--context` / `--context-file` inject ad-hoc info into all prompts without editing YAML
- `--skill-dir` adds skill directories to all agents at runtime
- All CLI flags are additive — they merge with project.yaml and agent configs, never replace
- Project state lives in `.autoforge/` (gitignored), never pollutes framework repo
- Evaluator agents default to API mode (single-turn, cheap). SDK mode is opt-in per agent for tools/MCPs/skills.

## Skills for deeper context

- `/programs` — program YAML schema, creating new programs, template files
- `/agents-panels` — agent YAML schema, panel composition, weights, SDK vs API mode, skills/MCPs
- `/evaluation` — how scoring works, agent_runner internals, objective vs panel evaluation
- `/driver` — driver agent prompt building, SDK vs API mode, how feedback flows
- `/project-setup` — project init, state management, git operations, iteration history
- `/objective-optimization` — ML training, benchmarks, or anything with a numeric metric: the run→extract→compare pipeline, crash handling, writing new objective programs
- `/create-agent` — interactive workflow: asks questions, generates agent YAML with system prompt and rubric
- `/create-panel` — interactive workflow: asks about audience/goals, selects agents, assigns weights, generates panel YAML
