"""Tests for git operations."""

import pytest
from pathlib import Path

from autoforge.git_ops import GitOps


class TestGitOps:
    def test_init_creates_repo(self, tmp_dir):
        git = GitOps(tmp_dir)
        assert git.is_repo() is False
        git.init()
        assert git.is_repo() is True

    def test_create_branch(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()
        branch = git.create_branch("test-run")
        assert branch == "autoforge/test-run"
        assert git.current_branch() == "autoforge/test-run"

    def test_commit_and_hash(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()
        # Create a file to commit
        (tmp_dir / "test.txt").write_text("hello")
        hash = git.commit("test commit")
        assert len(hash) == 7

    def test_revert_last(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "file.txt").write_text("version 1")
        git.commit("v1")

        (tmp_dir / "file.txt").write_text("version 2")
        git.commit("v2")

        git.revert_last()
        assert (tmp_dir / "file.txt").read_text() == "version 1"

    def test_has_changes(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()
        assert git.has_changes() is False

        (tmp_dir / "new.txt").write_text("new file")
        assert git.has_changes() is True

    def test_get_diff(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "file.txt").write_text("before")
        git.commit("first")

        (tmp_dir / "file.txt").write_text("after")
        git.commit("second")

        diff = git.get_diff()
        assert "before" in diff or "after" in diff

    def test_custom_branch_prefix(self, tmp_dir):
        git = GitOps(tmp_dir, branch_prefix="custom")
        git.init()
        branch = git.create_branch("run1")
        assert branch == "custom/run1"

    def test_commit_specific_files(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "tracked.txt").write_text("tracked")
        (tmp_dir / "untracked.txt").write_text("untracked")
        git.commit("only tracked", files=["tracked.txt"])

        # untracked.txt should still show as untracked
        assert git.has_changes() is True
