"""Run evaluator agents in parallel — supports both single-turn API and multi-turn SDK modes."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from anthropic import AsyncAnthropic

from autoforge.config import AgentConfig, resolve_model
from autoforge.state import AgentScore

# ---------------------------------------------------------------------------
# Structured scoring tool — forces agents to return structured output
# ---------------------------------------------------------------------------

SUBMIT_EVALUATION_TOOL: dict[str, Any] = {
    "name": "submit_evaluation",
    "description": (
        "Submit your evaluation score and reasoning. "
        "Score from 0.0 (terrible) to 10.0 (exceptional). "
        "5.0 = adequate, 7.0 = good, 9.0 = excellent. "
        "Do not be overly generous."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "minimum": 0,
                "maximum": 10,
                "description": "Your evaluation score (0-10)",
            },
            "reasoning": {
                "type": "string",
                "description": "2-3 sentence explanation of the score",
            },
            "strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific strengths observed",
            },
            "weaknesses": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific weaknesses or areas for improvement",
            },
        },
        "required": ["score", "reasoning", "strengths", "weaknesses"],
    },
}

SCORING_INSTRUCTIONS = """
## Instructions
You are evaluating content for quality. You MUST use the submit_evaluation tool
to return your score (0-10) and reasoning. Be specific about strengths and
weaknesses. Calibrate carefully:
  0-2: Fundamentally flawed
  3-4: Below standard, significant issues
  5-6: Adequate, meets minimum expectations
  7-8: Good, polished and effective
  9-10: Exceptional, best-in-class
""".strip()

SDK_SCORING_INSTRUCTIONS = """
## Instructions
You are evaluating content for quality. You have access to tools — use them
if you need to research, fact-check, read files, or gather additional context
before scoring.

When you are ready to score, respond with your evaluation in this exact format:

SCORE: <number 0-10>
REASONING: <2-3 sentence explanation>
STRENGTHS: <comma-separated list>
WEAKNESSES: <comma-separated list>

Calibrate carefully:
  0-2: Fundamentally flawed
  3-4: Below standard, significant issues
  5-6: Adequate, meets minimum expectations
  7-8: Good, polished and effective
  9-10: Exceptional, best-in-class
""".strip()


class AgentRunner:
    """Runs evaluator agents in parallel via the Anthropic API or Claude Code SDK."""

    def __init__(self, client: AsyncAnthropic | None = None):
        self.client = client or AsyncAnthropic()

    async def run_evaluator(
        self,
        agent: AgentConfig,
        content: str,
        context: str = "",
        weight: float = 1.0,
    ) -> AgentScore:
        """Run a single evaluator agent, returning its score.

        Routes to API mode (single-turn) or SDK mode (multi-turn with tools/MCPs)
        based on agent.mode.
        """
        if agent.is_agentic:
            return await self._run_sdk(agent, content, context, weight)
        else:
            return await self._run_api(agent, content, context, weight)

    # --- API mode: single-turn, forced tool_choice ---

    async def _run_api(
        self,
        agent: AgentConfig,
        content: str,
        context: str,
        weight: float,
    ) -> AgentScore:
        """Single-turn evaluation via raw Anthropic API with forced structured output.

        If the agent has skill_dirs configured, skill knowledge is loaded and
        injected into the system prompt so the agent has that context even
        without interactive skill invocation.
        """
        system_parts = [agent.system_prompt]

        # Inject skill knowledge for API-mode agents
        if agent.skill_dirs:
            from autoforge.skills import load_skill_content
            skill_knowledge = load_skill_content(
                agent.skill_dirs,
                filter_names=agent.skills or None,
            )
            if skill_knowledge:
                system_parts.append(f"\n## Skill Knowledge\n\n{skill_knowledge}")

        if agent.scoring_rubric:
            system_parts.append(f"\n## Scoring Rubric\n{agent.scoring_rubric}")
        system_parts.append(f"\n{SCORING_INSTRUCTIONS}")
        system_prompt = "\n".join(system_parts)

        user_parts = []
        if context:
            user_parts.append(f"## Context\n{context}\n")
        user_parts.append(f"## Content to Evaluate\n\n{content}")
        user_message = "\n".join(user_parts)

        try:
            response = await self.client.messages.create(
                model=resolve_model(agent.model),
                max_tokens=agent.max_tokens,
                temperature=agent.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                tools=[SUBMIT_EVALUATION_TOOL],
                tool_choice={"type": "tool", "name": "submit_evaluation"},
            )
            return self._parse_api_response(response, agent.name, weight)

        except Exception as e:
            return AgentScore(
                agent=agent.name,
                weight=weight,
                score=5.0,
                reasoning=f"Agent error: {e}",
                error=True,
            )

    def _parse_api_response(self, response: Any, agent_name: str, weight: float) -> AgentScore:
        """Extract structured score from the API response."""
        for block in response.content:
            if block.type == "tool_use" and block.name == "submit_evaluation":
                inp = block.input
                return AgentScore(
                    agent=agent_name,
                    weight=weight,
                    score=float(inp["score"]),
                    reasoning=inp.get("reasoning", ""),
                    strengths=inp.get("strengths", []),
                    weaknesses=inp.get("weaknesses", []),
                )

        return AgentScore(
            agent=agent_name,
            weight=weight,
            score=5.0,
            reasoning="Agent did not use the submit_evaluation tool",
            error=True,
        )

    # --- SDK mode: multi-turn agentic with tools, MCPs, etc. ---

    async def _run_sdk(
        self,
        agent: AgentConfig,
        content: str,
        context: str,
        weight: float,
    ) -> AgentScore:
        """Multi-turn evaluation via Claude Code SDK.

        The agent can take multiple turns, use tools (Read, Grep, Bash, WebSearch, etc.),
        call MCP servers, and do research before scoring.
        """
        from claude_code_sdk import Claude, ClaudeCodeOptions
        from autoforge.driver.driver import _build_mcp_servers

        system_parts = [agent.system_prompt]
        if agent.scoring_rubric:
            system_parts.append(f"\n## Scoring Rubric\n{agent.scoring_rubric}")
        system_parts.append(f"\n{SDK_SCORING_INSTRUCTIONS}")

        prompt_parts = []
        if context:
            prompt_parts.append(f"## Context\n{context}\n")
        prompt_parts.append(f"## Content to Evaluate\n\n{content}")
        prompt = "\n".join(prompt_parts)

        tools = agent.tools or ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]

        # If agent has skills, ensure the Skill tool is available
        if agent.skill_dirs and "Skill" not in tools:
            tools.append("Skill")

        options = ClaudeCodeOptions(
            model=resolve_model(agent.model),
            append_system_prompt="\n".join(system_parts),
            allowed_tools=tools,
            permission_mode="bypassPermissions",
            max_turns=agent.max_turns,
        )

        # Wire skill directories as add_dirs so Claude Code discovers them
        if agent.skill_dirs:
            from autoforge.skills import resolve_skill_dirs
            resolved = resolve_skill_dirs(agent.skill_dirs)
            if resolved:
                options.add_dirs = [str(d) for d in resolved]

        if agent.mcp_servers:
            options.mcp_servers = _build_mcp_servers(agent.mcp_servers)

        try:
            result_text = ""
            async for message in Claude.query(prompt=prompt, options=options):
                if hasattr(message, "content") and isinstance(message.content, str):
                    result_text = message.content

            return self._parse_sdk_response(result_text, agent.name, weight)

        except Exception as e:
            return AgentScore(
                agent=agent.name,
                weight=weight,
                score=5.0,
                reasoning=f"SDK agent error: {e}",
                error=True,
            )

    def _parse_sdk_response(self, text: str, agent_name: str, weight: float) -> AgentScore:
        """Parse SCORE/REASONING/STRENGTHS/WEAKNESSES from SDK agent text output."""
        score = 5.0
        reasoning = ""
        strengths: list[str] = []
        weaknesses: list[str] = []

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("SCORE:"):
                try:
                    score = float(re.search(r"[\d.]+", line.split(":", 1)[1]).group())  # type: ignore
                    score = max(0.0, min(10.0, score))
                except (ValueError, AttributeError):
                    pass
            elif line.startswith("REASONING:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.startswith("STRENGTHS:"):
                raw = line.split(":", 1)[1].strip()
                strengths = [s.strip() for s in raw.split(",") if s.strip()]
            elif line.startswith("WEAKNESSES:"):
                raw = line.split(":", 1)[1].strip()
                weaknesses = [s.strip() for s in raw.split(",") if s.strip()]

        return AgentScore(
            agent=agent_name,
            weight=weight,
            score=score,
            reasoning=reasoning or text[:200],
            strengths=strengths,
            weaknesses=weaknesses,
        )

    # --- Panel orchestration ---

    async def run_panel(
        self,
        agents: list[tuple[AgentConfig, float]],  # (agent_config, weight)
        content: str,
        context: str = "",
        on_score: Any = None,  # callback(AgentScore) for live UI updates
    ) -> list[AgentScore]:
        """Run all agents in a panel concurrently.

        Supports mixed panels: some agents may be API mode (fast, single-turn)
        while others are SDK mode (multi-turn with tools/MCPs).
        All run in parallel via asyncio.gather.
        """
        async def _run_one(agent: AgentConfig, weight: float) -> AgentScore:
            score = await self.run_evaluator(agent, content, context, weight)
            if on_score is not None:
                await on_score(score)
            return score

        tasks = [_run_one(agent, weight) for agent, weight in agents]
        return await asyncio.gather(*tasks)
