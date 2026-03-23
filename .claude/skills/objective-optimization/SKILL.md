---
description: "Objective optimization: ML training, benchmarks, or any problem with a numeric metric. Covers the run-command-extract-metric pipeline, crash handling, timeouts, and writing new objective programs."
when_to_use: "When setting up ML training optimization, creating objective programs, debugging metric extraction, or working with the ml-training program"
user-invocable: true
---

# Objective Optimization

For problems with a hard numeric metric — ML training loss, benchmark scores, latency, test pass rates — autoforge uses **objective mode**: run a command, extract a number, compare to the previous best.

## How it works

```
Driver edits train.py
  → git commit
  → shell: "uv run train.py > run.log 2>&1"
  → shell: 'grep "^val_bpb:" run.log'
  → regex: extract float
  → compare to best_score
  → keep or revert
```

No evaluator agents involved. The score comes from the command output.

## ObjectiveEvalConfig fields

```yaml
objective:
  run_command: str            # shell command to execute (stdout captured)
  metric_extract: str         # shell command to extract the metric line from output
  metric_name: str            # name for display (default: "score")
  metric_regex: str           # regex to parse a float from metric_extract output
                              # default: '[\d.]+' (first number found)
  direction: minimize|maximize  # default: "minimize"
  timeout_seconds: int        # kill if exceeds this (default: 600)
  setup_command: str|null     # one-time setup before first run (default: null)
```

## Execution pipeline (eval/objective.py)

### run_objective_eval(config, working_dir) → ObjectiveResult

1. **Run command**: `asyncio.create_subprocess_shell(config.run_command, cwd=working_dir)`
   - stdout and stderr are merged (STDOUT)
   - Output is captured in memory

2. **Timeout enforcement**: `asyncio.wait_for(proc.communicate(), timeout=config.timeout_seconds)`
   - If exceeded: `proc.kill()`, returns crashed=True, score=inf (minimize) or -inf (maximize)

3. **Write log**: Full output saved to `working_dir/run.log`

4. **Check exit code**: Non-zero → crashed=True, error_message includes last 20 lines of output

5. **Extract metric**: Runs `config.metric_extract` as a shell command (10s timeout)
   - Applies `config.metric_regex` to the output
   - Parses the first match as a float
   - If extraction fails → crashed=True

6. **Return ObjectiveResult**: score, raw_output, metric_name, duration_seconds, crashed, error_message

### Crash handling

Every failure mode returns a valid ObjectiveResult with `crashed=True` and a worst-possible score:
- direction=minimize → score=inf (guaranteed to not be an "improvement")
- direction=maximize → score=-inf

This means the engine always gets a score to compare — it never crashes from a failed evaluation. The crashed iteration is recorded as status="discard" and the driver gets feedback about what went wrong.

### Setup

`run_setup(config, working_dir)` runs `config.setup_command` once before the first evaluation. Returns True if exit code is 0. Used for one-time data downloads, dependency installs, etc.

## The built-in ml-training program

### What it does
- **Editable**: `train.py` — contains GPT model, MuonAdamW optimizer, training loop, all hyperparameters
- **Read-only**: `prepare.py` — data loading, BPE tokenizer, `evaluate_bpb()` function (the ground truth metric)
- **Metric**: `val_bpb` (validation bits per byte) — lower is better, vocab-size-independent
- **Time budget**: 5 minutes wall-clock training per iteration
- **Driver mode**: SDK (full Claude Code session — the driver needs to read/edit complex Python code and reason about architecture)

### Metric extraction chain
```yaml
run_command: "uv run train.py > run.log 2>&1"
metric_extract: 'grep "^val_bpb:" run.log'
```
train.py prints `val_bpb: 0.9832` at the end of training. grep extracts that line. The default regex `[\d.]+` parses `0.9832`.

### Template files
`train.py` and `prepare.py` live in `library/programs/ml-training/` alongside `program.yaml`. They're automatically copied into the project on `autoforge init --program ml-training`. The originals come from karpathy/autoresearch.

### What the driver can change
Everything in train.py: model architecture (GPTConfig), attention (CausalSelfAttention with RoPE, Flash Attention 3, value embeddings), MLP, optimizer (Muon for matrices, AdamW for embeddings/scalars), all hyperparameters (DEPTH, ASPECT_RATIO, HEAD_DIM, learning rates, batch size, warmup/warmdown ratios, weight decay).

### What's fixed
prepare.py is read-only: MAX_SEQ_LEN=2048, TIME_BUDGET=300s, EVAL_TOKENS, VOCAB_SIZE=8192, validation shard, the evaluate_bpb() function itself.

## Writing a new objective program

Example: optimizing a benchmark score.

```yaml
name: code-benchmark
description: Optimize code generation benchmark score
version: "1.0"

editable_files:
  - "solution.py"

read_only_files:
  - "problem.md"
  - "test_cases.py"

eval_mode: objective
objective:
  run_command: "python test_cases.py solution.py > run.log 2>&1"
  metric_extract: 'grep "^score:" run.log'
  metric_name: score
  metric_regex: '[\d.]+'
  direction: maximize
  timeout_seconds: 120

driver_model: sonnet
driver_mode: sdk
driver_instructions: |
  You are optimizing solution.py to maximize the benchmark score.
  Read problem.md for the problem statement and test_cases.py to
  understand what's being measured. Make one focused change per iteration.

simplicity_criterion: true
```

The key requirements for any objective program:
1. **run_command** must produce deterministic output containing the metric
2. **metric_extract** must isolate the metric line (grep, awk, tail, etc.)
3. **metric_regex** must match a parseable float in that line
4. The command must exit cleanly (exit code 0) on success
5. Set **timeout_seconds** appropriately — the process is killed if it exceeds this
6. Set **direction** correctly — "minimize" for loss/error, "maximize" for accuracy/score

## How the engine handles objective results

In `engine.py._eval_objective()`:
1. Calls `run_objective_eval(config, project_dir)`
2. Wraps result in `_EvalResult(score=result.score, raw_metrics={metric_name: score})`
3. Engine compares to `state.best_score` via `state.is_improvement(score)` which respects direction
4. If crashed: score is inf/-inf, so it's guaranteed to be "not an improvement" → discard

The raw_metrics dict is stored in the IterationRecord so you can extract additional metrics later if your run_command outputs multiple values.
