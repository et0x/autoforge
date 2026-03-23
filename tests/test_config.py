"""Tests for config loading, validation, and resolution."""

import pytest
import yaml
from pathlib import Path

from autoforge.config import (
    AgentConfig,
    EvalMode,
    ObjectiveEvalConfig,
    PanelConfig,
    PanelMember,
    ProgramConfig,
    ProjectConfig,
    list_configs,
    resolve_config,
    resolve_model,
    resolve_program_dir,
)


# ---------------------------------------------------------------------------
# resolve_model
# ---------------------------------------------------------------------------

class TestResolveModel:
    def test_short_names(self):
        assert "haiku" in resolve_model("haiku")
        assert "sonnet" in resolve_model("sonnet")
        assert "opus" in resolve_model("opus")

    def test_passthrough(self):
        assert resolve_model("claude-opus-4-6") == "claude-opus-4-6"
        assert resolve_model("my-custom-model") == "my-custom-model"


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------

class TestAgentConfig:
    def test_load_from_yaml(self, sample_agent_yaml):
        agent = AgentConfig(**yaml.safe_load(sample_agent_yaml.read_text()))
        assert agent.name == "test-agent"
        assert agent.model == "haiku"
        assert agent.temperature == 0.3
        assert agent.mode == "api"
        assert agent.is_agentic is False
        assert "test evaluator" in agent.system_prompt

    def test_defaults(self):
        agent = AgentConfig(name="a", system_prompt="test")
        assert agent.model == "haiku"
        assert agent.temperature == 0.3
        assert agent.max_tokens == 2048
        assert agent.mode == "api"
        assert agent.tools == []
        assert agent.mcp_servers == {}
        assert agent.skill_dirs == []
        assert agent.skills == []
        assert agent.max_turns == 10

    def test_sdk_mode(self):
        agent = AgentConfig(name="a", system_prompt="test", mode="sdk")
        assert agent.is_agentic is True

    def test_model_copy_override(self):
        agent = AgentConfig(name="a", system_prompt="test", model="haiku")
        overridden = agent.model_copy(update={"model": "opus"})
        assert overridden.model == "opus"
        assert agent.model == "haiku"  # original unchanged


# ---------------------------------------------------------------------------
# PanelConfig
# ---------------------------------------------------------------------------

class TestPanelConfig:
    def test_valid_panel(self):
        panel = PanelConfig(
            name="test",
            members=[
                PanelMember(agent="a", weight=0.6),
                PanelMember(agent="b", weight=0.4),
            ],
        )
        assert len(panel.members) == 2
        assert panel.min_score == 0.0
        assert panel.max_score == 10.0

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            PanelConfig(
                name="bad",
                members=[
                    PanelMember(agent="a", weight=0.5),
                    PanelMember(agent="b", weight=0.3),
                ],
            )

    def test_weights_tolerance(self):
        # 0.995 + 0.005 = 1.0, but let's test near the tolerance edge
        panel = PanelConfig(
            name="ok",
            members=[
                PanelMember(agent="a", weight=0.504),
                PanelMember(agent="b", weight=0.504),
            ],
        )
        assert panel is not None

    def test_load_from_yaml(self, sample_panel_yaml):
        panel = PanelConfig(**yaml.safe_load(sample_panel_yaml.read_text()))
        assert panel.name == "test-panel"
        assert len(panel.members) == 2
        assert sum(m.weight for m in panel.members) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ProgramConfig
# ---------------------------------------------------------------------------

class TestProgramConfig:
    def test_panel_program(self, sample_program_dir):
        data = yaml.safe_load((sample_program_dir / "program.yaml").read_text())
        prog = ProgramConfig(**data)
        assert prog.name == "test-program"
        assert prog.eval_mode == EvalMode.PANEL
        assert prog.default_panel == "test-panel"
        assert prog.editable_files == ["content.md"]
        assert prog.driver_model == "haiku"

    def test_objective_program(self, sample_objective_program_dir):
        data = yaml.safe_load(
            (sample_objective_program_dir / "program.yaml").read_text()
        )
        prog = ProgramConfig(**data)
        assert prog.eval_mode == EvalMode.OBJECTIVE
        assert prog.objective is not None
        assert prog.objective.direction == "maximize"

    def test_objective_requires_config(self):
        with pytest.raises(ValueError, match="objective config required"):
            ProgramConfig(
                name="bad",
                editable_files=["x"],
                eval_mode="objective",
            )

    def test_panel_requires_panel_name(self):
        with pytest.raises(ValueError, match="default_panel"):
            ProgramConfig(
                name="bad",
                editable_files=["x"],
                eval_mode="panel",
            )

    def test_defaults(self):
        prog = ProgramConfig(
            name="t",
            editable_files=["x"],
            eval_mode="panel",
            default_panel="p",
        )
        assert prog.driver_model == "sonnet"
        assert prog.driver_mode == "sdk"
        assert prog.simplicity_criterion is True
        assert prog.never_stop is True
        assert "Read" in prog.driver_tools


# ---------------------------------------------------------------------------
# ProjectConfig
# ---------------------------------------------------------------------------

class TestProjectConfig:
    def test_save_and_load(self, tmp_dir):
        project = ProjectConfig(name="test", program="my-prog", panel="my-panel")
        project.save(tmp_dir)
        loaded = ProjectConfig.load(tmp_dir)
        assert loaded.name == "test"
        assert loaded.program == "my-prog"
        assert loaded.panel == "my-panel"

    def test_load_missing(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            ProjectConfig.load(tmp_dir)

    def test_defaults(self):
        p = ProjectConfig(name="t", program="p")
        assert p.panel is None
        assert p.driver_model is None
        assert p.max_iterations is None
        assert p.target_score is None
        assert p.extra_context == ""


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

class TestConfigResolution:
    def test_resolve_flat_file(self, tmp_dir):
        """Resolve a flat YAML file."""
        agents_dir = tmp_dir / "library" / "agents"
        agents_dir.mkdir(parents=True)
        path = agents_dir / "my-agent.yaml"
        path.write_text("name: my-agent\nsystem_prompt: test")

        # Monkey-patch the built-in library path
        import autoforge.config as cfg
        original = cfg._built_in_library
        cfg._built_in_library = lambda: tmp_dir / "library"
        try:
            resolved = resolve_config("agents", "my-agent")
            assert resolved == path
        finally:
            cfg._built_in_library = original

    def test_resolve_directory_layout(self, tmp_dir):
        """Resolve a directory-based program."""
        prog_dir = tmp_dir / "library" / "programs" / "my-prog"
        prog_dir.mkdir(parents=True)
        yaml_path = prog_dir / "program.yaml"
        yaml_path.write_text("name: my-prog\neditable_files: [x]\neval_mode: panel\ndefault_panel: p")

        import autoforge.config as cfg
        original = cfg._built_in_library
        cfg._built_in_library = lambda: tmp_dir / "library"
        try:
            resolved = resolve_config("programs", "my-prog")
            assert resolved == yaml_path
        finally:
            cfg._built_in_library = original

    def test_resolve_program_dir(self, tmp_dir):
        """resolve_program_dir returns the directory, not the yaml file."""
        prog_dir = tmp_dir / "library" / "programs" / "my-prog"
        prog_dir.mkdir(parents=True)
        (prog_dir / "program.yaml").write_text("name: my-prog")
        (prog_dir / "template.py").write_text("# template")

        import autoforge.config as cfg
        original = cfg._built_in_library
        cfg._built_in_library = lambda: tmp_dir / "library"
        try:
            d = resolve_program_dir("my-prog")
            assert d == prog_dir
            assert (d / "template.py").is_file()
        finally:
            cfg._built_in_library = original

    def test_project_local_overrides_builtin(self, tmp_dir):
        """Project-local config takes precedence over built-in."""
        # Built-in
        builtin_dir = tmp_dir / "library" / "agents"
        builtin_dir.mkdir(parents=True)
        (builtin_dir / "shared.yaml").write_text("name: shared\nsystem_prompt: builtin")

        # Project-local
        project = tmp_dir / "project"
        project.mkdir()
        local_dir = project / ".autoforge" / "agents"
        local_dir.mkdir(parents=True)
        (local_dir / "shared.yaml").write_text("name: shared\nsystem_prompt: local")

        import autoforge.config as cfg
        original = cfg._built_in_library
        cfg._built_in_library = lambda: tmp_dir / "library"
        try:
            resolved = resolve_config("agents", "shared", project_dir=project)
            assert "local" in resolved.read_text()
        finally:
            cfg._built_in_library = original

    def test_list_configs_finds_both_layouts(self, tmp_dir):
        """list_configs finds both flat files and directory-based programs."""
        progs_dir = tmp_dir / "library" / "programs"
        # Flat
        flat_dir = progs_dir / "flat-prog"
        flat_dir.mkdir(parents=True)
        (flat_dir / "program.yaml").write_text("name: flat-prog")
        # Also a flat yaml
        (progs_dir / "simple.yaml").write_text("name: simple")

        import autoforge.config as cfg
        original = cfg._built_in_library
        cfg._built_in_library = lambda: tmp_dir / "library"
        try:
            configs = list_configs("programs")
            assert "flat-prog" in configs
            assert "simple" in configs
        finally:
            cfg._built_in_library = original

    def test_resolve_not_found(self, tmp_dir):
        import autoforge.config as cfg
        original = cfg._built_in_library
        cfg._built_in_library = lambda: tmp_dir / "library"
        try:
            with pytest.raises(FileNotFoundError):
                resolve_config("agents", "nonexistent")
        finally:
            cfg._built_in_library = original


# ---------------------------------------------------------------------------
# Built-in library loading
# ---------------------------------------------------------------------------

class TestBuiltInLibrary:
    def test_load_builtin_programs(self):
        configs = list_configs("programs")
        assert "ml-training" in configs
        assert "content-optimization" in configs

    def test_load_builtin_agents(self):
        configs = list_configs("agents")
        assert "formal-writing" in configs
        assert "technical-accuracy" in configs
        assert len(configs) == 10

    def test_load_builtin_panels(self):
        configs = list_configs("panels")
        assert "government-stakeholders" in configs
        assert "linkedin-professional" in configs
        assert len(configs) == 4

    def test_load_all_agents_valid(self):
        """Every built-in agent YAML parses without error."""
        for name in list_configs("agents"):
            agent = AgentConfig.load(name)
            assert agent.name == name
            assert agent.system_prompt

    def test_load_all_panels_valid(self):
        """Every built-in panel YAML parses without error."""
        for name in list_configs("panels"):
            panel = PanelConfig.load(name)
            assert panel.name == name
            assert sum(m.weight for m in panel.members) == pytest.approx(1.0, abs=0.01)

    def test_load_all_programs_valid(self):
        """Every built-in program YAML parses without error."""
        for name in list_configs("programs"):
            prog = ProgramConfig.load(name)
            assert prog.name == name
