"""Pydantic models for all YAML configuration files."""

from __future__ import annotations

import importlib.resources
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Resolution: project-local → user-global → built-in
# ---------------------------------------------------------------------------

LIBRARY_DIRS: list[Path] = []  # populated at startup by cli.py

def _built_in_library() -> Path:
    return Path(importlib.resources.files("autoforge")).parent.parent / "library"  # type: ignore[arg-type]


def resolve_config(kind: str, name: str, project_dir: Path | None = None) -> Path:
    """Find a YAML config file by kind (programs/agents/panels) and name.

    Supports two layouts:
      - Flat file:  <dir>/<kind>/<name>.yaml
      - Directory:  <dir>/<kind>/<name>/program.yaml

    Search order per layout:
      1. <project_dir>/.autoforge/<kind>/
      2. ~/.autoforge/library/<kind>/
      3. <package>/library/<kind>/
    """
    search_dirs: list[Path] = []
    if project_dir is not None:
        search_dirs.append(project_dir / ".autoforge" / kind)
    search_dirs.append(Path.home() / ".autoforge" / "library" / kind)
    search_dirs.append(_built_in_library() / kind)

    candidates: list[Path] = []
    for d in search_dirs:
        # Directory layout: <name>/program.yaml
        dir_path = d / name / "program.yaml"
        candidates.append(dir_path)
        if dir_path.is_file():
            return dir_path
        # Flat layout: <name>.yaml
        flat_path = d / f"{name}.yaml"
        candidates.append(flat_path)
        if flat_path.is_file():
            return flat_path

    searched = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"Config '{name}' ({kind}) not found. Searched:\n  {searched}")


def resolve_program_dir(name: str, project_dir: Path | None = None) -> Path | None:
    """Find the directory for a program (for copying template files).

    Returns the directory containing program.yaml, or None if it's a flat file.
    """
    search_dirs: list[Path] = []
    if project_dir is not None:
        search_dirs.append(project_dir / ".autoforge" / "programs")
    search_dirs.append(Path.home() / ".autoforge" / "library" / "programs")
    search_dirs.append(_built_in_library() / "programs")

    for d in search_dirs:
        dir_path = d / name / "program.yaml"
        if dir_path.is_file():
            return d / name
    return None


def list_configs(kind: str, project_dir: Path | None = None) -> dict[str, Path]:
    """List all available configs of a given kind, deduplicated by name (first wins)."""
    dirs: list[Path] = []
    if project_dir is not None:
        dirs.append(project_dir / ".autoforge" / kind)
    dirs.append(Path.home() / ".autoforge" / "library" / kind)
    dirs.append(_built_in_library() / kind)

    found: dict[str, Path] = {}
    for d in dirs:
        if d.is_dir():
            # Flat files: <name>.yaml
            for f in sorted(d.glob("*.yaml")):
                name = f.stem
                if name not in found:
                    found[name] = f
            # Directory layout: <name>/program.yaml
            for f in sorted(d.glob("*/program.yaml")):
                name = f.parent.name
                if name not in found:
                    found[name] = f
    return found


# ---------------------------------------------------------------------------
# Evaluation config
# ---------------------------------------------------------------------------

class EvalMode(str, Enum):
    OBJECTIVE = "objective"
    PANEL = "panel"


class ObjectiveEvalConfig(BaseModel):
    """Run a command and extract a numeric metric."""
    run_command: str
    metric_extract: str  # shell command to extract metric line
    metric_name: str = "score"
    metric_regex: str = r"[\d.]+"
    direction: str = "minimize"  # "minimize" or "maximize"
    timeout_seconds: int = 600
    setup_command: Optional[str] = None


class PanelEvalConfig(BaseModel):
    """Evaluate using a weighted panel of AI agents."""
    panel: str  # panel name
    target_files: list[str] = []  # files to send to evaluators (defaults to editable_files)
    context_files: list[str] = []  # additional context for evaluators


# ---------------------------------------------------------------------------
# Program config
# ---------------------------------------------------------------------------

class ProgramConfig(BaseModel):
    """A program defines what is being optimized and how to evaluate it."""
    name: str
    description: str = ""
    version: str = "1.0"

    editable_files: list[str]  # glob patterns
    read_only_files: list[str] = []

    eval_mode: EvalMode
    objective: Optional[ObjectiveEvalConfig] = None
    panel_eval: Optional[PanelEvalConfig] = None
    default_panel: Optional[str] = None

    driver_instructions: str = ""
    simplicity_criterion: bool = True
    driver_model: str = "sonnet"
    driver_tools: list[str] = Field(default_factory=lambda: ["Read", "Edit", "Write", "Glob", "Grep", "Bash"])
    driver_mcp_servers: dict[str, dict] = Field(default_factory=dict)
    driver_skill_dirs: list[str] = Field(default_factory=list)
    driver_max_turns: Optional[int] = None

    max_iterations: Optional[int] = None
    never_stop: bool = True
    setup_commands: list[str] = []

    # Files to copy into project workspace on init

    @model_validator(mode="after")
    def _check_eval_config(self) -> "ProgramConfig":
        if self.eval_mode == EvalMode.OBJECTIVE and self.objective is None:
            raise ValueError("objective config required when eval_mode is 'objective'")
        if self.eval_mode == EvalMode.PANEL and self.default_panel is None and (self.panel_eval is None or not self.panel_eval.panel):
            raise ValueError("default_panel or panel_eval.panel required when eval_mode is 'panel'")
        return self

    @classmethod
    def load(cls, name: str, project_dir: Path | None = None) -> "ProgramConfig":
        path = resolve_config("programs", name, project_dir)
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


# ---------------------------------------------------------------------------
# Agent config
# ---------------------------------------------------------------------------

class AgentConfig(BaseModel):
    """An evaluator agent persona with system prompt and model config."""
    name: str
    description: str = ""
    model: str = "haiku"
    temperature: float = 0.3
    max_tokens: int = 512

    system_prompt: str
    scoring_rubric: str = ""

    # Tools and MCPs for the Claude Code SDK session
    tools: list[str] = []
    mcp_servers: dict[str, dict] = Field(default_factory=dict)

    # Skills: directories containing .claude/skills/ or plugin structures.
    # Passed as add_dirs to Claude.query() so the agent can invoke skills.
    skill_dirs: list[str] = Field(default_factory=list)

    # Optional: only load specific skills by name (e.g. ["netrise-knowledge-base"]).
    # If empty, all discovered skills from skill_dirs are loaded.
    skills: list[str] = Field(default_factory=list)

    # Max turns (prevents runaway agents)
    max_turns: int = 10

    @classmethod
    def load(cls, name: str, project_dir: Path | None = None) -> "AgentConfig":
        path = resolve_config("agents", name, project_dir)
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


# ---------------------------------------------------------------------------
# Panel config
# ---------------------------------------------------------------------------

class PanelMember(BaseModel):
    agent: str  # agent name
    weight: float = Field(ge=0.0, le=1.0)


class PanelConfig(BaseModel):
    """A weighted set of evaluator agents."""
    name: str
    description: str = ""
    members: list[PanelMember]
    min_score: float = 0.0
    max_score: float = 10.0

    @model_validator(mode="after")
    def _check_weights(self) -> "PanelConfig":
        total = sum(m.weight for m in self.members)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Panel weights must sum to 1.0, got {total:.3f}")
        return self

    @classmethod
    def load(cls, name: str, project_dir: Path | None = None) -> "PanelConfig":
        path = resolve_config("panels", name, project_dir)
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)


# ---------------------------------------------------------------------------
# Project config
# ---------------------------------------------------------------------------

class ProjectConfig(BaseModel):
    """A project binds a program to a working directory."""
    name: str
    program: str
    panel: Optional[str] = None  # override program's default panel
    driver_model: Optional[str] = None  # override program's driver model
    max_iterations: Optional[int] = None
    target_score: Optional[float] = None  # stop early if achieved
    extra_context: str = ""

    @classmethod
    def load(cls, project_dir: Path) -> "ProjectConfig":
        path = project_dir / ".autoforge" / "project.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"No project found at {project_dir}. Run `autoforge init` first.")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def save(self, project_dir: Path) -> None:
        path = project_dir / ".autoforge" / "project.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(exclude_none=True), f, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Model name resolution
# ---------------------------------------------------------------------------

MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6-20250514",
    "opus": "claude-opus-4-6-20250514",
}


def resolve_model(name: str) -> str:
    """Resolve a short model name to a full model ID."""
    return MODEL_MAP.get(name, name)
