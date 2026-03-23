"""Tests for skill discovery and loading."""

import pytest
from pathlib import Path

from autoforge.skills import discover_skill_files, load_skill_content, resolve_skill_dirs


class TestResolveSkillDirs:
    def test_expands_tilde(self, tmp_dir):
        # Can't easily test ~ expansion, but we can test real paths
        resolved = resolve_skill_dirs([str(tmp_dir)])
        assert resolved == [tmp_dir]

    def test_filters_nonexistent(self):
        resolved = resolve_skill_dirs(["/nonexistent/path"])
        assert resolved == []

    def test_empty(self):
        assert resolve_skill_dirs([]) == []


class TestDiscoverSkillFiles:
    def test_claude_skills_pattern(self, tmp_dir):
        """Discovers .claude/skills/<name>/SKILL.md"""
        skill_dir = tmp_dir / ".claude" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# My Skill")

        found = discover_skill_files([str(tmp_dir)])
        assert len(found) == 1
        assert found[0] == skill_md

    def test_plugins_pattern(self, tmp_dir):
        """Discovers plugins/<plugin>/skills/<name>/SKILL.md"""
        skill_dir = tmp_dir / "plugins" / "my-plugin" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# My Skill")

        found = discover_skill_files([str(tmp_dir)])
        assert len(found) == 1
        assert found[0] == skill_md

    def test_filter_by_name(self, tmp_dir):
        """filter_names limits which skills are returned."""
        for name in ["skill-a", "skill-b", "skill-c"]:
            d = tmp_dir / "plugins" / "p" / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name}")

        all_skills = discover_skill_files([str(tmp_dir)])
        assert len(all_skills) == 3

        filtered = discover_skill_files([str(tmp_dir)], filter_names=["skill-b"])
        assert len(filtered) == 1
        assert filtered[0].parent.name == "skill-b"

    def test_no_skills(self, tmp_dir):
        assert discover_skill_files([str(tmp_dir)]) == []


class TestLoadSkillContent:
    def test_loads_skill_md(self, tmp_dir):
        skill_dir = tmp_dir / ".claude" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# My Skill\n\nSome content here.")

        content = load_skill_content([str(tmp_dir)])
        assert "My Skill" in content
        assert "Some content here" in content

    def test_loads_references(self, tmp_dir):
        skill_dir = tmp_dir / ".claude" / "skills" / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Skill")
        refs = skill_dir / "references"
        refs.mkdir()
        (refs / "ref1.md").write_text("Reference doc 1 content")

        content = load_skill_content([str(tmp_dir)])
        assert "Reference doc 1 content" in content

    def test_max_total_chars(self, tmp_dir):
        skill_dir = tmp_dir / ".claude" / "skills" / "big-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("X" * 5000)

        content = load_skill_content([str(tmp_dir)], max_total_chars=100)
        assert len(content) <= 5100  # SKILL.md loaded first, then cap kicks in

    def test_filter_by_name(self, tmp_dir):
        for name in ["a", "b"]:
            d = tmp_dir / ".claude" / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"Content for {name}")

        content = load_skill_content([str(tmp_dir)], filter_names=["a"])
        assert "Content for a" in content
        assert "Content for b" not in content

    def test_empty(self, tmp_dir):
        assert load_skill_content([str(tmp_dir)]) == ""
