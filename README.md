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

# Set up your API key (required for evaluator agents)
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

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

## Examples

### Simple: optimize a LinkedIn post

No custom agents, no skills — just a draft post and a built-in panel.

```bash
# Create the project
autoforge init linkedin-post -p content-optimization --panel linkedin-professional
cd linkedin-post

# Write your draft
cat > content.md << 'EOF'
We just shipped a new feature that lets users do X. It took us 3 months
and we learned a lot along the way. Here's what we found.

First, the problem was harder than we thought...
EOF

# Write the brief so the driver agent knows what you're going for
cat > brief.md << 'EOF'
Audience: senior engineering leaders on LinkedIn.
Goal: establish thought leadership around solving hard infrastructure problems.
Tone: confident but not arrogant. Specific, not vague.
Length: 800-1200 words.
EOF

# Run 15 iterations — each one edits the post, 6 agents score it in
# parallel, and the change is kept only if the consensus score improves
autoforge run -n 15
```

That's it. The `linkedin-professional` panel uses 6 evaluator agents (audience-engagement, clarity-conciseness, strategic-thinking, evidence-based-reasoning, emotional-intelligence, creative-writing) weighted for what makes a good LinkedIn post. The driver agent reads their feedback each iteration and targets the weakest areas.

### Advanced: optimize a post that references your company's product

Say you're writing about your company's capabilities and you need the evaluators to actually know your product to score accuracy. You create a custom agent that has access to your knowledge base via a skill, and a custom panel that includes it.

```bash
# Create the project
autoforge init product-announcement -p content-optimization
cd product-announcement
mkdir -p .autoforge/agents .autoforge/panels
```

Create a custom evaluator agent that uses your company's knowledge base skill:

```yaml
# .autoforge/agents/product-accuracy.yaml
name: product-accuracy
description: Verifies claims against internal product knowledge base
model: sonnet
max_turns: 8

skill_dirs:
  - ~/repos/your-company-knowledge-base

skills:
  - your-product-knowledge

tools:
  - Read
  - Grep
  - Skill

system_prompt: |
  You are a product expert. Before scoring, use the product knowledge
  skill to verify every claim about the product's capabilities,
  architecture, and positioning. Flag anything inaccurate or misleading.

scoring_rubric: |
  0-2: Major factual errors about the product
  3-4: Several inaccuracies or unsupported claims
  5-6: Mostly accurate but vague or imprecise
  7-8: Accurate and specific
  9-10: Every claim verified, precise, and well-positioned
```

Create a custom panel that includes this agent alongside the built-in ones:

```yaml
# .autoforge/panels/product-launch.yaml
name: product-launch
description: Panel for product announcements requiring domain accuracy

members:
  - agent: product-accuracy
    weight: 0.30
  - agent: audience-engagement
    weight: 0.20
  - agent: strategic-thinking
    weight: 0.20
  - agent: clarity-conciseness
    weight: 0.15
  - agent: formal-writing
    weight: 0.15
```

Now run it:

```bash
# Write your draft and brief
cat > content.md << 'EOF'
Excited to announce that [Company] now supports full firmware
analysis across all major RTOS platforms...
EOF

cat > brief.md << 'EOF'
Audience: CISOs and security engineers.
Goal: announce new platform capability, drive demo requests.
Tone: authoritative, technical but accessible.
EOF

# Update project to use your custom panel
cat > .autoforge/project.yaml << 'EOF'
name: product-announcement
program: content-optimization
panel: product-launch
EOF

# Run — the product-accuracy agent will use the Skill tool to
# fact-check claims against your knowledge base before scoring
autoforge run -n 20 -m sonnet
```

The `product-accuracy` agent gets a full Claude Code session where it can invoke your knowledge base skill, read docs, and verify claims before scoring. All 5 agents run in parallel each iteration.

You could do the same thing with an MCP server instead of a skill. For example, if your product data lives in a database with an MCP interface:

```yaml
# .autoforge/agents/product-accuracy.yaml
name: product-accuracy
model: sonnet
tools: [Read, Grep]
mcp_servers:
  product-db:
    command: npx
    args: ["your-product-mcp-server"]
    env:
      API_KEY: "${PRODUCT_API_KEY}"
system_prompt: |
  You verify product claims using the product-db MCP server...
```

### Objective: optimize ML training (the original autoresearch use case)

For problems with a hard numeric metric, no evaluator panel is needed — autoforge runs a command, extracts the number, and compares.

```bash
# Create the project — this copies train.py and prepare.py from the template
autoforge init ml-experiment -p ml-training
cd ml-experiment

# Download data and train tokenizer (one-time)
uv run prepare.py

# Run — the driver agent modifies train.py, trains for 5 min, extracts
# val_bpb, and keeps changes that lower it. Runs until you stop it.
autoforge run
```

That's it. The `ml-training` program uses objective mode:

```yaml
eval_mode: objective
objective:
  run_command: "uv run train.py > run.log 2>&1"
  metric_extract: 'grep "^val_bpb:" run.log'
  direction: minimize
  timeout_seconds: 600
```

The driver agent gets a full Claude Code session so it can read, reason about, and edit the training code. Everything in `train.py` is fair game — model architecture, optimizer hyperparameters, batch size, scheduling. `prepare.py` is read-only.

Each iteration takes ~5.5 minutes (5 min training + overhead). You can leave it running overnight and wake up to a log of experiments.

### Writing your own objective program

Any problem where you can produce a number works. Here's a benchmark optimization example:

```yaml
# library/programs/my-benchmark.yaml (or .autoforge/programs/ for project-local)
name: my-benchmark
editable_files: ["solution.py"]
read_only_files: ["problem.md"]
eval_mode: objective
objective:
  run_command: "python run_benchmark.py > run.log 2>&1"
  metric_extract: 'grep "^score:" run.log'
  direction: maximize
  timeout_seconds: 120
driver_model: sonnet
driver_instructions: |
  Optimize solution.py to maximize the benchmark score.
  Read problem.md for the problem description.
```

Requirements:
- **run_command** must produce output containing the metric and exit 0 on success
- **metric_extract** must isolate the line with the number (grep, awk, etc.)
- The default regex `[\d.]+` parses the first float it finds
- If the command crashes or times out, the iteration is automatically discarded

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
    driver.py            # Driver agent (Claude Code SDK)
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

Each evaluator agent has a persona, model, and scoring rubric. All agents run via the Claude Code SDK and can use tools, MCPs, and skills.

```yaml
name: formal-writing
description: Expert in formal, professional writing quality
model: haiku
system_prompt: |
  You are an expert in formal and professional writing...
scoring_rubric: |
  0-2: Unprofessional
  5-6: Adequate
  9-10: Publication-ready
```

Agents that need external knowledge can configure tools, skills, and MCPs:

```yaml
name: product-expert
model: sonnet
max_turns: 8
tools: [Read, Grep, Skill, WebSearch]
skill_dirs: [~/repos/company-knowledge-base]
skills: [product-knowledge]
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
autoforge run [-n N] [-t score] [-m model] [-c context] [-C file] [-s skill_dir]
autoforge eval [--agent <name> -f <file>] [-m model] [-c context] [-C file] [-s skill_dir]
autoforge status
autoforge history [-n last]
autoforge program list|show <name>
autoforge agent list|show <name>
autoforge panel list|show <name>
```

### Ad-hoc context and skills

You don't need to edit YAML files to give agents extra information. Use CLI flags:

```bash
# Inject context into all agent prompts (driver + evaluators)
autoforge run -c "This post is about Executive Order 14028 on cybersecurity"

# Read context from a file
autoforge run -C exec-order-summary.md

# Combine multiple sources
autoforge run \
  -c "Audience: federal CISOs attending RSA 2026" \
  -C executive-order.md \
  -C company-talking-points.md

# Add skill directories for all agents at runtime
autoforge run -s ~/repos/my-knowledge-base

# Everything composes
autoforge run -n 15 -m opus \
  -c "The executive order can be found at https://whitehouse.gov/eo-14028" \
  -C background.md \
  -s ~/repos/company-knowledge
```

All flags are additive — they merge with whatever is in `project.yaml` and agent configs. `-c` and `-C` are appended to `extra_context`. `-s` is appended to each agent's `skill_dirs`.

The `eval` command accepts the same flags for one-shot testing:

```bash
autoforge eval -c "Written for a government audience" -C policy-context.md
autoforge eval --agent formal-writing -f content.md -c "This is a policy memo"
```

## License

MIT
