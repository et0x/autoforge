"""Tests for CLI commands (smoke tests)."""

import pytest
from typer.testing import CliRunner

from autoforge.cli import app, _build_extra_context

runner = CliRunner()


class TestBuildExtraContext:
    def test_from_strings(self):
        result = _build_extra_context(["context A", "context B"], None)
        assert "context A" in result
        assert "context B" in result

    def test_from_file(self, tmp_dir):
        f = tmp_dir / "ctx.md"
        f.write_text("file context content")
        result = _build_extra_context(None, [str(f)])
        assert "file context content" in result

    def test_combined(self, tmp_dir):
        f = tmp_dir / "ctx.md"
        f.write_text("from file")
        result = _build_extra_context(["from flag"], [str(f)])
        assert "from flag" in result
        assert "from file" in result

    def test_missing_file(self, tmp_dir, capsys):
        result = _build_extra_context(None, ["/nonexistent/file.md"])
        assert result == ""

    def test_empty(self):
        assert _build_extra_context(None, None) == ""


class TestCLIHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "autoforge" in result.output.lower() or "optimization" in result.output.lower()

    def test_run_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--context" in result.output
        assert "--context-file" in result.output
        assert "--skill-dir" in result.output
        assert "--model" in result.output

    def test_eval_help(self):
        result = runner.invoke(app, ["eval", "--help"])
        assert result.exit_code == 0
        assert "--context" in result.output
        assert "--agent" in result.output

    def test_program_list(self):
        result = runner.invoke(app, ["program", "list"])
        assert result.exit_code == 0
        assert "ml-training" in result.output
        assert "content-optimization" in result.output

    def test_agent_list(self):
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert "formal-writing" in result.output

    def test_panel_list(self):
        result = runner.invoke(app, ["panel", "list"])
        assert result.exit_code == 0
        assert "government-stakeholders" in result.output

    def test_panel_show(self):
        result = runner.invoke(app, ["panel", "show", "government-stakeholders"])
        assert result.exit_code == 0
        assert "national-security-language" in result.output

    def test_program_show(self):
        result = runner.invoke(app, ["program", "show", "ml-training"])
        assert result.exit_code == 0
        assert "objective" in result.output


class TestCLIInit:
    def test_init_creates_project(self, tmp_dir):
        result = runner.invoke(app, [
            "init", "test-project",
            "-p", "content-optimization",
            "-d", str(tmp_dir / "test-project"),
        ])
        assert result.exit_code == 0
        project_dir = tmp_dir / "test-project"
        assert (project_dir / ".autoforge" / "project.yaml").is_file()

    def test_init_copies_template_files(self, tmp_dir):
        result = runner.invoke(app, [
            "init", "ml-test",
            "-p", "ml-training",
            "-d", str(tmp_dir / "ml-test"),
        ])
        assert result.exit_code == 0
        project_dir = tmp_dir / "ml-test"
        assert (project_dir / "train.py").is_file()
        assert (project_dir / "prepare.py").is_file()

    def test_init_with_panel_override(self, tmp_dir):
        result = runner.invoke(app, [
            "init", "test-project",
            "-p", "content-optimization",
            "--panel", "government-stakeholders",
            "-d", str(tmp_dir / "test-project"),
        ])
        assert result.exit_code == 0
        import yaml
        config = yaml.safe_load(
            (tmp_dir / "test-project" / ".autoforge" / "project.yaml").read_text()
        )
        assert config["panel"] == "government-stakeholders"
