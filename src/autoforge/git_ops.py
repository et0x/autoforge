"""Git operations for project-level branch/commit/revert."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitOps:
    """Isolated git operations scoped to a project working directory."""

    def __init__(self, working_dir: Path, branch_prefix: str = "autoforge"):
        self.working_dir = working_dir
        self.branch_prefix = branch_prefix

    def _run(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            check=check,
        )
        return result.stdout.strip()

    def is_repo(self) -> bool:
        """Check if working_dir has its own .git (not just inside a parent repo)."""
        return (self.working_dir / ".git").exists()

    def init(self) -> None:
        if not self.is_repo():
            self._run("init")
            # Initial commit so branches work
            self._run("commit", "--allow-empty", "-m", "Initial commit")

    def current_branch(self) -> str:
        return self._run("branch", "--show-current")

    def create_branch(self, tag: str) -> str:
        branch = f"{self.branch_prefix}/{tag}"
        current = self.current_branch()
        if current != branch:
            try:
                self._run("checkout", "-b", branch)
            except subprocess.CalledProcessError:
                # Branch already exists, just switch
                self._run("checkout", branch)
        return branch

    def commit(self, message: str, files: list[str] | None = None) -> str:
        """Stage and commit. Returns short hash."""
        if files:
            for f in files:
                self._run("add", f)
        else:
            self._run("add", "-A")
        self._run("commit", "-m", message, check=False)
        return self._run("rev-parse", "--short=7", "HEAD")

    def revert_last(self) -> None:
        """Discard the last commit (git reset --hard HEAD~1)."""
        self._run("reset", "--hard", "HEAD~1")

    def get_diff(self, from_ref: str = "HEAD~1") -> str:
        return self._run("diff", from_ref, "HEAD", check=False)

    def get_short_hash(self) -> str:
        return self._run("rev-parse", "--short=7", "HEAD")

    def has_changes(self) -> bool:
        status = self._run("status", "--porcelain")
        return bool(status)
