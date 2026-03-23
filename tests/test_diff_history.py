"""Tests for diff capture in iteration history."""

import json

from autoforge.git_ops import GitOps
from autoforge.state import AgentScore, IterationRecord, ProjectState


class TestDiffInIterationRecord:
    """Verify the diff field on IterationRecord works correctly."""

    def test_default_empty(self):
        rec = IterationRecord(
            iteration=1,
            timestamp="2026-03-23T00:00:00Z",
            score=7.0,
            status="keep",
        )
        assert rec.diff == ""

    def test_stores_diff_string(self):
        diff_text = "--- a/content.md\n+++ b/content.md\n@@ -1 +1 @@\n-old\n+new"
        rec = IterationRecord(
            iteration=1,
            timestamp="2026-03-23T00:00:00Z",
            score=7.0,
            status="keep",
            diff=diff_text,
        )
        assert rec.diff == diff_text

    def test_serialization_roundtrip(self):
        diff_text = "--- a/content.md\n+++ b/content.md\n@@ -1 +1 @@\n-old\n+new"
        rec = IterationRecord(
            iteration=1,
            timestamp="2026-03-23T00:00:00Z",
            score=7.0,
            status="keep",
            diff=diff_text,
        )
        json_str = rec.model_dump_json()
        loaded = IterationRecord(**json.loads(json_str))
        assert loaded.diff == diff_text

    def test_backwards_compatible_load(self):
        """Records without a diff field (old history) should load fine."""
        old_json = json.dumps({
            "iteration": 1,
            "timestamp": "2026-03-23T00:00:00Z",
            "score": 7.0,
            "status": "keep",
            "description": "old record",
        })
        rec = IterationRecord(**json.loads(old_json))
        assert rec.diff == ""


class TestDiffCapturedByGitOps:
    """Verify GitOps.get_diff captures the right content at each stage."""

    def test_diff_shows_change(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "content.md").write_text("original text")
        git.commit("baseline")

        (tmp_dir / "content.md").write_text("improved text")
        git.commit("iteration 1")

        diff = git.get_diff()
        assert "-original text" in diff
        assert "+improved text" in diff

    def test_diff_after_revert_shows_previous_change(self, tmp_dir):
        """After revert, get_diff should reflect the state before revert."""
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "content.md").write_text("version 1")
        git.commit("v1")

        (tmp_dir / "content.md").write_text("version 2")
        git.commit("v2")

        # Capture diff BEFORE revert (this is what engine.py does)
        diff_before_revert = git.get_diff()
        assert "-version 1" in diff_before_revert
        assert "+version 2" in diff_before_revert

        # After revert, file is back to v1
        git.revert_last()
        assert (tmp_dir / "content.md").read_text() == "version 1"

    def test_diff_multiline_content(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "content.md").write_text("line 1\nline 2\nline 3\n")
        git.commit("baseline")

        (tmp_dir / "content.md").write_text("line 1\nchanged line\nline 3\n")
        git.commit("edit line 2")

        diff = git.get_diff()
        assert "-line 2" in diff
        assert "+changed line" in diff
        # Unchanged lines should not appear as additions/removals
        assert "-line 1" not in diff
        assert "-line 3" not in diff

    def test_diff_new_file(self, tmp_dir):
        git = GitOps(tmp_dir)
        git.init()

        (tmp_dir / "existing.md").write_text("existing")
        git.commit("baseline")

        (tmp_dir / "new_file.md").write_text("new content")
        git.commit("add file")

        diff = git.get_diff()
        assert "new_file.md" in diff
        assert "+new content" in diff


class TestDiffInHistory:
    """Verify diffs persist correctly through history append/load cycle."""

    def test_diff_persisted_in_history(self, tmp_dir):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")

        diff_text = "--- a/content.md\n+++ b/content.md\n@@ -1 +1 @@\n-old\n+new"
        rec = state.record(1, 7.0, "keep", "improved", diff=diff_text)
        ProjectState.append_history(tmp_dir, rec)

        history = ProjectState.load_history(tmp_dir)
        assert len(history) == 1
        assert history[0].diff == diff_text

    def test_baseline_has_empty_diff(self, tmp_dir):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")

        rec = state.record(0, 5.0, "baseline", "Initial baseline")
        ProjectState.append_history(tmp_dir, rec)

        history = ProjectState.load_history(tmp_dir)
        assert history[0].diff == ""

    def test_keep_and_discard_both_have_diffs(self, tmp_dir):
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")

        rec0 = state.record(0, 5.0, "baseline", "initial")
        ProjectState.append_history(tmp_dir, rec0)

        diff_keep = "@@ -1 +1 @@\n-draft\n+better draft"
        rec1 = state.record(1, 6.0, "keep", "improved", diff=diff_keep)
        ProjectState.append_history(tmp_dir, rec1)

        diff_discard = "@@ -1 +1 @@\n-better draft\n+worse draft"
        rec2 = state.record(2, 5.5, "discard", "regression", diff=diff_discard)
        ProjectState.append_history(tmp_dir, rec2)

        history = ProjectState.load_history(tmp_dir)
        assert len(history) == 3
        assert history[0].diff == ""  # baseline
        assert history[1].diff == diff_keep
        assert history[1].status == "keep"
        assert history[2].diff == diff_discard
        assert history[2].status == "discard"

    def test_full_flow_with_git(self, tmp_dir, tmp_path_factory):
        """End-to-end: git commits → capture diffs → record history → reload.

        Uses a separate state_dir for history storage so git revert doesn't
        clobber the history.jsonl (in real usage, .autoforge/ is gitignored).
        """
        git = GitOps(tmp_dir)
        git.init()
        state = ProjectState(project_name="p", program_name="prog", direction="maximize")

        # State dir outside the git repo (simulates .autoforge/ being gitignored)
        state_dir = tmp_path_factory.mktemp("state_store")

        # Baseline
        (tmp_dir / "content.md").write_text("original post")
        git.commit("baseline")
        rec0 = state.record(0, 5.0, "baseline", "initial")
        ProjectState.append_history(state_dir, rec0)

        # Iteration 1: kept
        (tmp_dir / "content.md").write_text("better post")
        git.commit("iter 1")
        diff1 = git.get_diff()
        rec1 = state.record(1, 6.0, "keep", "improved hook", diff=diff1)
        ProjectState.append_history(state_dir, rec1)

        # Iteration 2: discarded
        (tmp_dir / "content.md").write_text("worse post")
        git.commit("iter 2")
        diff2 = git.get_diff()
        rec2 = state.record(2, 5.5, "discard", "bad change", diff=diff2)
        ProjectState.append_history(state_dir, rec2)
        git.revert_last()

        # Iteration 3: kept (starts from "better post" since iter 2 was reverted)
        assert (tmp_dir / "content.md").read_text() == "better post"
        (tmp_dir / "content.md").write_text("best post")
        git.commit("iter 3")
        diff3 = git.get_diff()
        rec3 = state.record(3, 7.0, "keep", "great change", diff=diff3)
        ProjectState.append_history(state_dir, rec3)

        # Verify history
        history = ProjectState.load_history(state_dir)
        assert len(history) == 4

        # Baseline: no diff
        assert history[0].diff == ""

        # Iter 1 (keep): original → better
        assert "-original post" in history[1].diff
        assert "+better post" in history[1].diff

        # Iter 2 (discard): better → worse
        assert "-better post" in history[2].diff
        assert "+worse post" in history[2].diff

        # Iter 3 (keep): better → best (not worse → best, since iter 2 was reverted)
        assert "-better post" in history[3].diff
        assert "+best post" in history[3].diff
