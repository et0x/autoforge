"""Tests for state management and iteration history."""

import json
from pathlib import Path

import pytest

from autoforge.state import AgentScore, IterationRecord, ProjectState


class TestAgentScore:
    def test_create(self):
        s = AgentScore(agent="test", weight=0.5, score=7.5, reasoning="Good")
        assert s.agent == "test"
        assert s.score == 7.5
        assert s.error is False

    def test_error_score(self):
        s = AgentScore(agent="test", weight=0.5, score=5.0, error=True, reasoning="Failed")
        assert s.error is True


class TestProjectState:
    def test_create_defaults(self):
        state = ProjectState(project_name="p", program_name="prog")
        assert state.iteration == 0
        assert state.best_score is None
        assert state.direction == "minimize"

    def test_is_improvement_minimize(self):
        state = ProjectState(project_name="p", program_name="prog", direction="minimize")
        assert state.is_improvement(5.0) is True  # no best yet
        state.best_score = 5.0
        assert state.is_improvement(4.0) is True
        assert state.is_improvement(5.0) is False
        assert state.is_improvement(6.0) is False

    def test_is_improvement_maximize(self):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")
        state.best_score = 5.0
        assert state.is_improvement(6.0) is True
        assert state.is_improvement(5.0) is False
        assert state.is_improvement(4.0) is False

    def test_record_updates_best(self):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")
        rec = state.record(0, 5.0, "baseline", "initial")
        assert state.best_score == 5.0
        assert state.best_iteration == 0
        assert rec.iteration == 0
        assert rec.status == "baseline"

    def test_record_keeps_best_on_discard(self):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")
        state.record(0, 5.0, "baseline", "initial")
        state.record(1, 4.0, "discard", "worse")  # discard doesn't update best
        assert state.best_score == 5.0
        assert state.best_iteration == 0

    def test_save_and_load(self, tmp_dir):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")
        state.record(0, 5.0, "baseline", "initial")
        state.save(tmp_dir)

        loaded = ProjectState.load(tmp_dir)
        assert loaded.project_name == "p"
        assert loaded.best_score == 5.0
        assert loaded.iteration == 0

    def test_load_missing(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            ProjectState.load(tmp_dir)

    def test_history_append_and_load(self, tmp_dir):
        state = ProjectState(project_name="p", program_name="prog")

        rec1 = state.record(0, 5.0, "baseline", "initial")
        ProjectState.append_history(tmp_dir, rec1)

        rec2 = state.record(1, 4.5, "keep", "improved")
        ProjectState.append_history(tmp_dir, rec2)

        history = ProjectState.load_history(tmp_dir)
        assert len(history) == 2
        assert history[0].status == "baseline"
        assert history[1].status == "keep"
        assert history[1].score == 4.5

    def test_history_empty(self, tmp_dir):
        history = ProjectState.load_history(tmp_dir)
        assert history == []

    def test_save_iteration_scores(self, tmp_dir):
        scores = [
            AgentScore(agent="a", weight=0.6, score=7.0, reasoning="good"),
            AgentScore(agent="b", weight=0.4, score=8.0, reasoning="great"),
        ]
        ProjectState.save_iteration_scores(tmp_dir, 1, scores, 7.4)

        path = tmp_dir / ".autoforge" / "iterations" / "001" / "scores.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["consensus_score"] == 7.4
        assert len(data["agents"]) == 2


class TestIterationRecord:
    def test_with_agent_scores(self):
        scores = [AgentScore(agent="a", weight=1.0, score=7.0)]
        rec = IterationRecord(
            iteration=1,
            timestamp="2026-03-23T00:00:00Z",
            score=7.0,
            status="keep",
            description="test",
            agent_scores=scores,
        )
        assert rec.agent_scores[0].score == 7.0

    def test_serialization_roundtrip(self):
        rec = IterationRecord(
            iteration=1,
            timestamp="2026-03-23T00:00:00Z",
            score=7.0,
            status="keep",
            description="test change",
        )
        json_str = rec.model_dump_json()
        loaded = IterationRecord(**json.loads(json_str))
        assert loaded.score == 7.0
        assert loaded.description == "test change"
