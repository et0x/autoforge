---
description: "Agent persona YAML schema, panel composition with weights, SDK vs API mode, skills/MCPs/tools for agents"
when_to_use: "When creating or modifying evaluator agents, configuring panels, setting up skills or MCPs for agents, or tuning agent weights"
user-invocable: true
---

# Agents and Panels

## AgentConfig fields (src/autoforge/config.py)

```yaml
name: str                      # required
description: str               # default ""
model: str                     # default "haiku" — short name or full model ID
temperature: float             # default 0.3
max_tokens: int                # default 2048

system_prompt: str             # required — the agent's persona and evaluation criteria
scoring_rubric: str            # default "" — appended to system prompt, guides 0-10 scale

# Execution mode
mode: "api" | "sdk"           # default "api"
  # api: single API call, forced structured output via submit_evaluation tool
  # sdk: multi-turn Claude Code session with tools, MCPs, skills

# SDK-mode only
tools: list[str]               # default [] — e.g. ["Read","Grep","Skill","WebSearch"]
mcp_servers: dict[str, dict]   # default {} — MCP server configs
skill_dirs: list[str]          # default [] — directories containing skills
skills: list[str]              # default [] — filter to specific skill names
max_turns: int                 # default 10 — prevents runaway agents
```

### Property: `is_agentic` → True when `mode == "sdk"`

## Agent execution flow

### API mode (default, fast, cheap)
1. System prompt = agent.system_prompt + skill_knowledge (if skill_dirs set) + scoring_rubric + SCORING_INSTRUCTIONS
2. User message = context + content to evaluate
3. Single `client.messages.create()` with `tool_choice: {"type": "tool", "name": "submit_evaluation"}`
4. Response is forced structured output: `{score, reasoning, strengths, weaknesses}`
5. On error: returns score=5.0 with error=True

### SDK mode (powerful, multi-turn)
1. Launches full Claude Code session via `Claude.query()`
2. Agent can take up to `max_turns` turns, using tools to research before scoring
3. skill_dirs are passed as `add_dirs` to ClaudeCodeOptions (skills become discoverable)
4. "Skill" tool is auto-added to allowed_tools if skill_dirs is set
5. mcp_servers are converted to McpStdioServerConfig/McpHttpServerConfig
6. Agent returns text with `SCORE: / REASONING: / STRENGTHS: / WEAKNESSES:` format
7. Parsed by `_parse_sdk_response()` in agent_runner.py

### Skill loading for API-mode agents
When an API-mode agent has `skill_dirs` configured, `load_skill_content()` from `skills.py` reads the SKILL.md files + referenced docs and injects them into the system prompt as `## Skill Knowledge`. The `skills` list filters which skills to load. `max_total_chars` defaults to 100,000.

## PanelConfig fields (src/autoforge/config.py)

```yaml
name: str                      # required
description: str               # default ""
members:                       # required
  - agent: str                 # agent name (resolved via config resolution)
    weight: float              # 0.0-1.0, all weights must sum to 1.0
min_score: float               # default 0.0
max_score: float               # default 10.0
```

### Validation: weights must sum to 1.0 (±0.01 tolerance)

## Consensus scoring (src/autoforge/eval/scoring.py)

- `weighted_consensus(scores)` = `Σ(score_i × weight_i)` — final consensus
- `partial_consensus(scores)` — re-normalizes weights for completed agents only (used for live UI)
- Errored agents are included with their fallback score (5.0)

## Model override

The `--model` CLI flag applies to ALL agents (driver + evaluators). In PanelEvaluator.__init__, each agent config is copied with `agent.model_copy(update={"model": model_override})`.

Precedence: CLI `--model` > project.yaml `driver_model` > program YAML `driver_model` > agent YAML `model`

## Built-in agents (10)

All use `mode: api`, `model: haiku`, `temperature: 0.3`:
- formal-writing, technical-accuracy, strategic-thinking
- national-security-language, evidence-based-reasoning, audience-engagement
- clarity-conciseness, creative-writing, data-driven-analysis, emotional-intelligence

## Built-in panels (4)

| Panel | Agents | Top weight |
|-------|--------|-----------|
| linkedin-professional | 6 agents | audience-engagement (0.25) |
| government-stakeholders | 6 agents | national-security-language (0.25) |
| technical-blog | 5 agents | technical-accuracy + clarity (0.25 each) |
| executive-summary | 5 agents | strategic-thinking + clarity (0.25 each) |

## Creating custom agents/panels

Place YAML files in:
- `<project>/.autoforge/agents/` or `<project>/.autoforge/panels/` — project-local (highest priority)
- `~/.autoforge/library/agents/` or `~/.autoforge/library/panels/` — user-global
- `library/agents/` or `library/panels/` — built-in (lowest priority)

Panels can mix built-in and custom agents. SDK-mode and API-mode agents run in parallel in the same panel via `asyncio.gather()`.

## MCP server config format

```yaml
mcp_servers:
  server-name:
    type: stdio              # or "http"/"sse"
    command: npx             # for stdio
    args: ["server-package"] # for stdio
    env:                     # for stdio
      API_KEY: "${VAR}"
    url: https://...         # for http/sse
    headers:                 # for http/sse
      Authorization: "..."
```

Converted to `McpStdioServerConfig` or `McpHttpServerConfig` by `_build_mcp_servers()` in `driver/driver.py`.
