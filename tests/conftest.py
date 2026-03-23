"""Shared fixtures for autoforge tests."""

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_dir(tmp_path):
    """A temporary directory for test files."""
    return tmp_path


@pytest.fixture
def sample_agent_yaml(tmp_dir):
    """Write a sample agent YAML and return its path."""
    agents_dir = tmp_dir / "library" / "agents"
    agents_dir.mkdir(parents=True)
    data = {
        "name": "test-agent",
        "description": "A test evaluator",
        "model": "haiku",
        "temperature": 0.3,
        "max_tokens": 1024,
        "system_prompt": "You are a test evaluator. Score content on a 0-10 scale.",
        "scoring_rubric": "0-5: bad\n6-10: good",
    }
    path = agents_dir / "test-agent.yaml"
    path.write_text(yaml.dump(data))
    return path


@pytest.fixture
def sample_panel_yaml(tmp_dir, sample_agent_yaml):
    """Write a sample panel YAML and return its path."""
    panels_dir = tmp_dir / "library" / "panels"
    panels_dir.mkdir(parents=True)
    data = {
        "name": "test-panel",
        "description": "A test panel",
        "members": [
            {"agent": "test-agent", "weight": 0.6},
            {"agent": "test-agent", "weight": 0.4},
        ],
    }
    path = panels_dir / "test-panel.yaml"
    path.write_text(yaml.dump(data))
    return path


@pytest.fixture
def sample_program_dir(tmp_dir):
    """Create a sample program directory with program.yaml and a template file."""
    prog_dir = tmp_dir / "library" / "programs" / "test-program"
    prog_dir.mkdir(parents=True)
    data = {
        "name": "test-program",
        "description": "A test program",
        "editable_files": ["content.md"],
        "read_only_files": ["brief.md"],
        "eval_mode": "panel",
        "default_panel": "test-panel",
        "driver_model": "haiku",
        "driver_instructions": "Improve the content based on feedback.",
    }
    (prog_dir / "program.yaml").write_text(yaml.dump(data))
    # A template file that should be copied on init
    (prog_dir / "content.md").write_text("Initial content here.")
    return prog_dir


@pytest.fixture
def sample_objective_program_dir(tmp_dir):
    """Create a sample objective program directory."""
    prog_dir = tmp_dir / "library" / "programs" / "test-objective"
    prog_dir.mkdir(parents=True)
    data = {
        "name": "test-objective",
        "description": "A test objective program",
        "editable_files": ["code.py"],
        "eval_mode": "objective",
        "objective": {
            "run_command": 'echo "score: 42.5"',
            "metric_extract": 'echo "score: 42.5"',
            "metric_name": "score",
            "metric_regex": r"[\d.]+",
            "direction": "maximize",
            "timeout_seconds": 10,
        },
        "driver_model": "haiku",
        "driver_instructions": "Improve the code.",
    }
    (prog_dir / "program.yaml").write_text(yaml.dump(data))
    (prog_dir / "code.py").write_text("print('hello')")
    return prog_dir


@pytest.fixture
def project_dir(tmp_dir, sample_program_dir, sample_agent_yaml, sample_panel_yaml):
    """Create a fully initialized project directory."""
    project = tmp_dir / "my-project"
    project.mkdir()
    autoforge_dir = project / ".autoforge"
    autoforge_dir.mkdir()

    project_config = {
        "name": "my-project",
        "program": "test-program",
        "panel": "test-panel",
    }
    (autoforge_dir / "project.yaml").write_text(yaml.dump(project_config))
    (project / "content.md").write_text("Draft content for testing.")
    (project / "brief.md").write_text("Audience: testers. Goal: pass all tests.")
    return project
