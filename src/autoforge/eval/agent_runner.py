"""Run evaluator agents in parallel via the Claude Code SDK."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from autoforge.config import AgentConfig, resolve_model
from autoforge.state import AgentScore

# ---------------------------------------------------------------------------
# Scoring instructions appended to every evaluator agent's system prompt
# ---------------------------------------------------------------------------

SCORING_INSTRUCTIONS = """
## Instructions
You are evaluating content for quality. You have access to tools — use them
if you need to research, fact-check, read files, or gather additional context
before scoring.

Use the full decimal range (e.g. 6.3, 7.5, 8.2) — do NOT round to whole numbers.
A 7.4 is meaningfully different from a 7.0.

Calibration anchors:
  5.0 = adequate, meets minimum expectations
  7.0 = good, polished and effective
  9.0 = exceptional, best-in-class

When you are ready to score, respond with your evaluation in this exact format:

SCORE: <number 0.0-10.0, use decimals>
REASONING: <1-2 sentence explanation>
WEAKNESS: <the single most impactful thing to improve — be specific and actionable>
""".strip()


class AgentRunner:
    """Runs evaluator agents in parallel via the Claude Code SDK."""

    async def run_evaluator(
        self,
        agent: AgentConfig,
        content: str,
        context: str = "",
        weight: float = 1.0,
    ) -> AgentScore:
        """Run a single evaluator agent via the Claude Code SDK, returning its score."""
        from claude_code_sdk import query as claude_query, ClaudeCodeOptions
        from autoforge.driver.driver import _build_mcp_servers

        system_parts = [agent.system_prompt]
        if agent.scoring_rubric:
            system_parts.append(f"\n## Scoring Rubric\n{agent.scoring_rubric}")
        system_parts.append(f"\n{SCORING_INSTRUCTIONS}")

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
            async for message in claude_query(prompt=prompt, options=options):
                if hasattr(message, "result") and message.result:
                    result_text = message.result
                elif hasattr(message, "content") and isinstance(message.content, list):
                    for block in message.content:
                        if hasattr(block, "text"):
                            result_text = block.text

            return self._parse_response(result_text, agent.name, weight)

        except Exception as e:
            return AgentScore(
                agent=agent.name,
                weight=weight,
                score=5.0,
                reasoning=f"Agent error: {e}",
                error=True,
            )

    def _parse_response(self, text: str, agent_name: str, weight: float) -> AgentScore:
        """Parse SCORE/REASONING/WEAKNESS from agent text output."""
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
            elif line.startswith("WEAKNESS:") or line.startswith("WEAKNESSES:"):
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
        """Run all agents in a panel concurrently via asyncio.gather."""
        async def _run_one(agent: AgentConfig, weight: float) -> AgentScore:
            score = await self.run_evaluator(agent, content, context, weight)
            if on_score is not None:
                await on_score(score)
            return score

        tasks = [_run_one(agent, weight) for agent, weight in agents]
        return await asyncio.gather(*tasks)
