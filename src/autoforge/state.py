"""Project state management and iteration history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentScore(BaseModel):
    """Score from a single evaluator agent."""
    agent: str
    weight: float
    score: float
    reasoning: str = ""
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    error: bool = False


class IterationRecord(BaseModel):
    """Record of a single optimization iteration."""
    iteration: int
    timestamp: str
    commit_hash: Optional[str] = None
    score: float
    status: str  # "baseline", "keep", "discard", "crash"
    description: str = ""
    duration_seconds: float = 0.0

    # Panel evaluation details
    agent_scores: Optional[list[AgentScore]] = None

    # Objective evaluation details
    raw_metrics: Optional[dict[str, Any]] = None


class ProjectState(BaseModel):
    """Persistent state for a project's optimization run."""
    project_name: str
    program_name: str
    branch: str = ""
    iteration: int = 0
    best_score: Optional[float] = None
    best_iteration: Optional[int] = None
    direction: str = "minimize"  # "minimize" or "maximize"
    started_at: Optional[str] = None

    def is_improvement(self, new_score: float) -> bool:
        if self.best_score is None:
            return True
        if self.direction == "minimize":
            return new_score < self.best_score
        return new_score > self.best_score

    def record(
        self,
        iteration: int,
        score: float,
        status: str,
        description: str = "",
        commit_hash: str | None = None,
        duration_seconds: float = 0.0,
        agent_scores: list[AgentScore] | None = None,
        raw_metrics: dict[str, Any] | None = None,
    ) -> IterationRecord:
        """Create an iteration record and update state."""
        record = IterationRecord(
            iteration=iteration,
            timestamp=datetime.now(timezone.utc).isoformat(),
            commit_hash=commit_hash,
            score=score,
            status=status,
            description=description,
            duration_seconds=duration_seconds,
            agent_scores=agent_scores,
            raw_metrics=raw_metrics,
        )

        if status in ("keep", "baseline"):
            if self.is_improvement(score) or self.best_score is None:
                self.best_score = score
                self.best_iteration = iteration

        self.iteration = iteration
        return record

    # --- Persistence ---

    @classmethod
    def load(cls, project_dir: Path) -> "ProjectState":
        path = project_dir / ".autoforge" / "state.json"
        if not path.is_file():
            raise FileNotFoundError(f"No state file at {path}")
        with open(path) as f:
            return cls(**json.load(f))

    def save(self, project_dir: Path) -> None:
        path = project_dir / ".autoforge" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)

    @staticmethod
    def append_history(project_dir: Path, record: IterationRecord) -> None:
        """Append an iteration record to history.jsonl."""
        path = project_dir / ".autoforge" / "history.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(record.model_dump_json() + "\n")

    @staticmethod
    def load_history(project_dir: Path) -> list[IterationRecord]:
        """Load all iteration records from history.jsonl."""
        path = project_dir / ".autoforge" / "history.jsonl"
        if not path.is_file():
            return []
        records = []
        for line in path.read_text().strip().splitlines():
            if line:
                records.append(IterationRecord(**json.loads(line)))
        return records

    @staticmethod
    def save_iteration_scores(
        project_dir: Path,
        iteration: int,
        agent_scores: list[AgentScore],
        consensus_score: float,
    ) -> None:
        """Save detailed per-agent scores for an iteration."""
        idir = project_dir / ".autoforge" / "iterations" / f"{iteration:03d}"
        idir.mkdir(parents=True, exist_ok=True)
        data = {
            "iteration": iteration,
            "consensus_score": consensus_score,
            "agents": [s.model_dump() for s in agent_scores],
        }
        with open(idir / "scores.json", "w") as f:
            json.dump(data, f, indent=2)
