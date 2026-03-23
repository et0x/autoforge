---
description: "How scoring works: agent_runner parallel execution, objective metric extraction, panel consensus, submit_evaluation tool schema"
when_to_use: "When modifying evaluation logic, debugging scoring, changing the submit_evaluation tool, or working on agent_runner.py, panel.py, objective.py, or scoring.py"
user-invocable: true
---

# Evaluation System

## Architecture

```
engine.py → _evaluate()
  ├── objective mode → eval/objective.py → run shell command → extract metric
  └── panel mode    → eval/panel.py → eval/agent_runner.py → parallel agents → scoring.py
```

## Panel evaluation flow (eval/panel.py)

### PanelEvaluator

```python
__init__(panel, project_dir, client, model_override)
```
- Loads all AgentConfigs from panel.members
- Applies model_override via `agent.model_copy(update={"model": ...})`
- Creates AgentRunner with AsyncAnthropic client

```python
async evaluate(content, context, on_score) → PanelResult
```
1. Builds `(AgentConfig, weight)` pairs from panel.members
2. Calls `runner.run_panel()` — all agents run via `asyncio.gather()`
3. `on_score` callback fires as each agent completes (for live UI)
4. Computes `weighted_consensus(scores)`
5. Returns `PanelResult(consensus_score, agent_scores)`

### PanelResult
- `consensus_score: float` — the weighted sum
- `agent_scores: list[AgentScore]` — individual results
- `score` property → alias for consensus_score

## Agent runner (eval/agent_runner.py)

### SUBMIT_EVALUATION_TOOL schema
```json
{
  "name": "submit_evaluation",
  "input_schema": {
    "properties": {
      "score": {"type": "number", "minimum": 0, "maximum": 10},
      "reasoning": {"type": "string"},
      "strengths": {"type": "array", "items": {"type": "string"}},
      "weaknesses": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["score", "reasoning", "strengths", "weaknesses"]
  }
}
```

### API mode (_run_api)
- System prompt = agent.system_prompt + skill_knowledge + scoring_rubric + SCORING_INSTRUCTIONS
- Single `client.messages.create()` with `tool_choice: {"type": "tool", "name": "submit_evaluation"}`
- Forces structured output — agent MUST use the tool
- Parses `tool_use` block from response content

### SDK mode (_run_sdk)
- Full `Claude.query()` session with `ClaudeCodeOptions`
- Agent responds in text format: `SCORE: X / REASONING: ... / STRENGTHS: ... / WEAKNESSES: ...`
- Parsed by `_parse_sdk_response()` using line-by-line string matching
- score is clamped to [0.0, 10.0]

### Error handling
- API errors → AgentScore(score=5.0, error=True, reasoning=error message)
- SDK errors → AgentScore(score=5.0, error=True, reasoning=error message)
- Missing tool_use in API response → score=5.0, error=True

### run_panel()
```python
async run_panel(agents, content, context, on_score) → list[AgentScore]
```
- Creates async tasks for each `(agent, weight)` pair
- `asyncio.gather(*tasks)` runs all in parallel
- Calls `on_score(score)` callback after each agent finishes

## Objective evaluation (eval/objective.py)

### run_objective_eval(config, working_dir) → ObjectiveResult
1. `asyncio.create_subprocess_shell(config.run_command)`
2. `asyncio.wait_for(proc.communicate(), timeout=config.timeout_seconds)`
3. Writes output to `run.log`
4. Runs `config.metric_extract` command to get metric line
5. Applies `config.metric_regex` to parse float
6. Returns ObjectiveResult

### Error cases
| Condition | Score | crashed |
|-----------|-------|---------|
| Timeout | inf/-inf (based on direction) | True |
| Non-zero exit | inf/-inf | True |
| Metric extraction fails | inf/-inf | True |
| Exception | inf/-inf | True |

### ObjectiveResult fields
- score, raw_output, metric_name, duration_seconds, crashed, error_message, extra_metrics

## Consensus math (eval/scoring.py)

```python
weighted_consensus(scores) = sum(s.score * s.weight for s in scores)
partial_consensus(scores)  = sum(s.score * (s.weight / total_weight) for s in scores)
```

- `partial_consensus` re-normalizes for incomplete results (live UI updates)
- `score_summary(scores)` → formatted string with agent names, scores, weights, consensus

## How the engine uses evaluation results

In `engine.py`:
- `_eval_panel()` reads editable files, builds context from read-only files + extra_context, calls `panel_evaluator.evaluate()`
- Saves detailed scores to `.autoforge/iterations/{iter:03d}/scores.json`
- Returns `_EvalResult(score=consensus_score, agent_scores=...)`
- `_eval_objective()` calls `run_objective_eval()`, returns `_EvalResult(score=metric, raw_metrics=...)`
- Engine compares score to `state.best_score` via `state.is_improvement(score)` (respects direction)
