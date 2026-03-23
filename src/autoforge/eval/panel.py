"""Panel evaluation orchestration — load agents, fan out, aggregate."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from anthropic import AsyncAnthropic

from autoforge.config import AgentConfig, PanelConfig
from autoforge.eval.agent_runner import AgentRunner
from autoforge.eval.scoring import weighted_consensus
from autoforge.state import AgentScore


class PanelResult:
    """Result of a panel evaluation."""

    def __init__(self, consensus_score: float, agent_scores: list[AgentScore]):
        self.consensus_score = consensus_score
        self.agent_scores = agent_scores

    @property
    def score(self) -> float:
        return self.consensus_score


class PanelEvaluator:
    """Orchestrates panel-based evaluation."""

    def __init__(
        self,
        panel: PanelConfig,
        project_dir: Path | None = None,
        client: AsyncAnthropic | None = None,
        model_override: str | None = None,
        extra_skill_dirs: list[str] | None = None,
    ):
        self.panel = panel
        self.project_dir = project_dir
        self.runner = AgentRunner(client)

        # Load all agent configs, applying overrides
        self.agents: dict[str, AgentConfig] = {}
        for member in panel.members:
            agent = AgentConfig.load(member.agent, project_dir)
            updates: dict[str, Any] = {}
            if model_override:
                updates["model"] = model_override
            if extra_skill_dirs:
                updates["skill_dirs"] = agent.skill_dirs + extra_skill_dirs
            if updates:
                agent = agent.model_copy(update=updates)
            self.agents[member.agent] = agent

    async def evaluate(
        self,
        content: str,
        context: str = "",
        on_score: Any = None,
    ) -> PanelResult:
        """Run all panel agents in parallel, return weighted consensus.

        Args:
            content: The content to evaluate
            context: Additional context (brief, extra_context, etc.)
            on_score: Optional async callback(AgentScore) for live UI updates
        """
        agent_weight_pairs = [
            (self.agents[m.agent], m.weight)
            for m in self.panel.members
        ]

        scores = await self.runner.run_panel(
            agents=agent_weight_pairs,
            content=content,
            context=context,
            on_score=on_score,
        )

        consensus = weighted_consensus(scores)

        return PanelResult(
            consensus_score=consensus,
            agent_scores=scores,
        )
