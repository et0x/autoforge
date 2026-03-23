# autoforge

[karpathy/autoresearch](https://github.com/karpathy/autoresearch) proved that an AI agent can run an optimization loop overnight and wake you up with better results. But it's built for one problem (ML training), one metric (val_bpb), and one program.md — and when you want to start fresh on a new problem, the git history from your last run is in the way.

Autoforge is a rebuild of that idea into a general-purpose framework. It adds three things autoresearch doesn't have: **project isolation** so you can switch between problems cleanly, **swappable programs** so the optimization loop isn't hardcoded to ML training, and **weighted expert panels** so you can optimize subjective work (writing, content, strategy) where there's no single metric — just a group of AI evaluators whose opinions you weight and combine into a score.

## How it works

```
                         ┌─────────────────────┐
                         │   Driver Agent    │
                         │  (proposes changes)  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │     Evaluation (parallel)      │
                    │                                │
                    │  Agent A ──► score (w: 0.25)   │
                    │  Agent B ──► score (w: 0.20)   │
                    │  Agent C ──► score (w: 0.20)   │
                    │  Agent D ──► score (w: 0.15)   │
                    │  Agent E ──► score (w: 0.10)   │
                    │  Agent F ──► score (w: 0.10)   │
                    │                                │
                    │  Consensus = Σ(weight × score) │
                    └───────────────┬───────────────┘
                                    │
                              ┌─────┴─────┐
                              │ Improved?  │
                              └─────┬─────┘
                             yes/       \no
                            keep      revert
                              │         │
                              └────┬────┘
                                   │
                                 repeat
```

1. A **driver agent** reads the current state + feedback from the last evaluation and makes one focused change
2. A **panel of evaluator agents** scores the result in parallel — each from their own expert perspective
3. Scores are combined into a single **weighted consensus** number
4. If the score improved: **keep**. If not: **revert**
5. Repeat until you hit `max_iterations`, `target_score`, or stop it manually

For objective problems (ML training), step 2 is replaced by running a command and extracting a metric.

## Quick start

```bash
# Install
uv sync

# See what's available
autoforge program list
autoforge agent list
autoforge panel list

# Create a project
autoforge init my-post \
  --program content-optimization \
  --panel linkedin-professional

# Add your content
cd my-post
echo "Your draft post here..." > content.md
echo "Audience: senior tech leaders. Goal: thought leadership." > brief.md

# Run optimization
autoforge run
autoforge run -n 20                    # limit to 20 iterations
autoforge run -t 8.5                   # stop at score 8.5
autoforge run -m opus                  # override model for all agents

# One-shot evaluation (no optimization loop)
autoforge eval
autoforge eval --agent formal-writing -f content.md
```

## Project structure

```
src/autoforge/
  cli.py                 # Typer CLI
  config.py              # Pydantic models for all YAML configs
  engine.py              # The optimization loop
  state.py               # Project state + iteration history (JSONL)
  git_ops.py             # Git branch/commit/revert per project
  skills.py              # Skill discovery and loading
  eval/
    objective.py         # Run command, extract metric
    panel.py             # Fan out to agent panel, aggregate scores
    agent_runner.py      # Run evaluator agents in parallel
    scoring.py           # Weighted consensus math
  driver/
    driver.py            # Driver agent (Claude Code SDK or raw API)
    prompt_builder.py    # Build driver prompt from state + feedback
  ui/
    console.py           # Rich console
    progress.py          # Live terminal display

library/
  programs/              # Optimization program templates
  agents/                # Evaluator agent personas (system prompts)
  panels/                # Weighted agent compositions
```

## Three config types

Everything is defined in YAML files. The framework ships with built-in templates and you can create your own.

### Programs

A program defines what is being optimized and how to evaluate it.

```yaml
name: content-optimization
editable_files: ["content.md"]
read_only_files: ["brief.md"]
eval_mode: panel
default_panel: linkedin-professional
driver_model: sonnet
driver_instructions: |
  You are optimizing written content. Make targeted improvements
  based on the evaluation feedback. One focused change per iteration.
```

For objective metrics (ML training, benchmarks):

```yaml
eval_mode: objective
objective:
  run_command: "uv run train.py > run.log 2>&1"
  metric_extract: 'grep "^val_bpb:" run.log'
  direction: minimize
  timeout_seconds: 600
```

### Agents

Each evaluator agent has a persona, model, and scoring rubric.

```yaml
name: formal-writing
description: Expert in formal, professional writing quality
model: haiku
mode: api           # "api" (single-turn, fast) or "sdk" (multi-turn, tools)
system_prompt: |
  You are an expert in formal and professional writing...
scoring_rubric: |
  0-2: Unprofessional
  5-6: Adequate
  9-10: Publication-ready
```

SDK-mode agents can use tools, MCPs, and skills:

```yaml
name: netrise-expert
model: sonnet
mode: sdk
max_turns: 8
tools: [Read, Grep, Skill, WebSearch]
skill_dirs: [~/repos/netrise-knowledge-claude-skills]
skills: [netrise-knowledge-base]
mcp_servers:
  browser:
    command: npx
    args: ["@anthropic/mcp-browser"]
```

### Panels

A panel is a weighted set of agents. Weights must sum to 1.0.

```yaml
name: government-stakeholders
members:
  - agent: national-security-language
    weight: 0.25
  - agent: formal-writing
    weight: 0.20
  - agent: strategic-thinking
    weight: 0.20
  - agent: evidence-based-reasoning
    weight: 0.15
  - agent: technical-accuracy
    weight: 0.10
  - agent: audience-engagement
    weight: 0.10
```

## Built-in library

**Programs:** `ml-training`, `content-optimization`

**Agents:** `formal-writing`, `technical-accuracy`, `strategic-thinking`, `national-security-language`, `evidence-based-reasoning`, `audience-engagement`, `clarity-conciseness`, `creative-writing`, `data-driven-analysis`, `emotional-intelligence`

**Panels:** `government-stakeholders`, `linkedin-professional`, `technical-blog`, `executive-summary`

## Config resolution

Configs are resolved in priority order:

1. Project-local: `<project>/.autoforge/<kind>/<name>.yaml`
2. User-global: `~/.autoforge/library/<kind>/<name>.yaml`
3. Built-in: `library/<kind>/<name>.yaml`

This lets you override built-in templates per-project or globally.

## Project isolation

Each project gets its own `.autoforge/` directory with independent state. The framework repo stays clean — no git history pollution when switching between problems.

```
my-project/
  .autoforge/
    project.yaml         # which program, panel, overrides
    state.json           # current iteration, best score
    history.jsonl        # append-only iteration log
    iterations/          # per-iteration agent scores
  content.md             # the work product
  brief.md               # the goal
```

## CLI reference

```
autoforge init <name> -p <program> [--panel <panel>]
autoforge run [-n iterations] [-t target] [-m model]
autoforge eval [--agent <name> -f <file>]
autoforge status
autoforge history
autoforge program list|show <name>
autoforge agent list|show <name>
autoforge panel list|show <name>
```

## Agent execution modes

| Mode | Evaluator | Driver | Multi-turn | Tools/MCPs/Skills |
|------|-----------|-----------|------------|-------------------|
| `api` | Single API call, forced structured output | Content in prompt, edits in response | No | No (skill knowledge injected into prompt) |
| `sdk` | Full Claude Code session | Full Claude Code session | Yes | Yes |

API mode is fast and cheap (haiku). SDK mode is powerful (sonnet/opus) — agents can read files, search the web, invoke skills, and use MCPs before making their decision.

## License

MIT
