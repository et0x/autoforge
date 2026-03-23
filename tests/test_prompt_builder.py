"""Tests for the driver prompt builder."""

import pytest
from pathlib import Path

from autoforge.config import ProgramConfig
from autoforge.driver.prompt_builder import build_driver_prompt
from autoforge.state import AgentScore, IterationRecord, ProjectState


@pytest.fixture
def workspace(tmp_dir):
    (tmp_dir / "content.md").write_text("This is the content to optimize.")
    (tmp_dir / "brief.md").write_text("Audience: testers. Goal: quality.")
    return tmp_dir


@pytest.fixture
def program():
    return ProgramConfig(
        name="test",
        editable_files=["content.md"],
        read_only_files=["brief.md"],
        eval_mode="panel",
        default_panel="test-panel",
        driver_instructions="Improve the content based on evaluator feedback.",
        simplicity_criterion=True,
    )


@pytest.fixture
def state():
    s = ProjectState(project_name="test", program_name="test", direction="maximize")
    s.record(0, 5.0, "baseline", "initial")
    return s


class TestBuildDriverPrompt:
    def test_contains_instructions(self, program, state, workspace):
        prompt = build_driver_prompt(program, state, [], workspace)
        assert "Improve the content based on evaluator feedback" in prompt

    def test_contains_current_state(self, program, state, workspace):
        prompt = build_driver_prompt(program, state, [], workspace)
        assert "Best score: 5.0" in prompt
        assert "higher is better" in prompt

    def test_contains_file_contents(self, program, state, workspace):
        prompt = build_driver_prompt(program, state, [], workspace)
        assert "This is the content to optimize" in prompt
        assert "Audience: testers" in prompt

    def test_contains_constraints(self, program, state, workspace):
        prompt = build_driver_prompt(program, state, [], workspace)
        assert "content.md" in prompt
        assert "DO NOT EDIT" in prompt  # read-only files marked
        assert "simpler changes" in prompt  # simplicity criterion

    def test_contains_extra_context(self, program, state, workspace):
        prompt = build_driver_prompt(program, state, [], workspace, extra_context="Focus on clarity.")
        assert "Focus on clarity" in prompt

    def test_contains_history(self, program, state, workspace):
        history = [
            IterationRecord(iteration=0, timestamp="t", score=5.0, status="baseline", description="initial"),
            IterationRecord(iteration=1, timestamp="t", score=5.5, status="keep", description="improved opening"),
            IterationRecord(iteration=2, timestamp="t", score=5.3, status="discard", description="tried bullets"),
        ]
        prompt = build_driver_prompt(program, state, history, workspace)
        assert "improved opening" in prompt
        assert "tried bullets" in prompt
        assert "baseline" in prompt

    def test_contains_agent_feedback(self, program, state, workspace):
        scores = [
            AgentScore(agent="formal-writing", weight=0.5, score=7.0,
                       reasoning="Good structure", strengths=["Clear"], weaknesses=["Wordy"]),
            AgentScore(agent="engagement", weight=0.5, score=6.0,
                       reasoning="Needs hook", strengths=["Topic"], weaknesses=["Weak opening"]),
        ]
        history = [
            IterationRecord(iteration=1, timestamp="t", score=6.5, status="keep",
                            description="last change", agent_scores=scores),
        ]
        prompt = build_driver_prompt(program, state, history, workspace)
        assert "formal-writing" in prompt
        assert "Good structure" in prompt
        assert "Wordy" in prompt
        assert "Weak opening" in prompt
        assert "weight: 0.50" in prompt

    def test_task_instructions(self, program, state, workspace):
        prompt = build_driver_prompt(program, state, [], workspace)
        assert "single focused improvement" in prompt
        assert "SHORT description" in prompt
