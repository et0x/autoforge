"""Tests for objective evaluation."""

import pytest

from autoforge.config import ObjectiveEvalConfig
from autoforge.eval.objective import run_objective_eval, run_setup


@pytest.fixture
def success_config():
    return ObjectiveEvalConfig(
        run_command='echo "score: 42.5"',
        metric_extract='echo "score: 42.5"',
        metric_name="score",
        direction="maximize",
        timeout_seconds=10,
    )


@pytest.fixture
def minimize_config():
    return ObjectiveEvalConfig(
        run_command='echo "val_bpb: 0.9832"',
        metric_extract='echo "val_bpb: 0.9832"',
        metric_name="val_bpb",
        direction="minimize",
        timeout_seconds=10,
    )


@pytest.mark.asyncio
class TestRunObjectiveEval:
    async def test_success_maximize(self, success_config, tmp_dir):
        result = await run_objective_eval(success_config, tmp_dir)
        assert result.score == pytest.approx(42.5)
        assert result.crashed is False
        assert result.metric_name == "score"

    async def test_success_minimize(self, minimize_config, tmp_dir):
        result = await run_objective_eval(minimize_config, tmp_dir)
        assert result.score == pytest.approx(0.9832)
        assert result.crashed is False

    async def test_writes_log(self, success_config, tmp_dir):
        await run_objective_eval(success_config, tmp_dir)
        log_path = tmp_dir / "run.log"
        assert log_path.is_file()
        assert "42.5" in log_path.read_text()

    async def test_crash_nonzero_exit(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command='echo "error" && exit 1',
            metric_extract='echo ""',
            metric_name="score",
            direction="maximize",
            timeout_seconds=10,
        )
        result = await run_objective_eval(config, tmp_dir)
        assert result.crashed is True
        assert result.score == float("-inf")  # maximize: worst is -inf

    async def test_crash_minimize_gives_inf(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command="exit 1",
            metric_extract='echo ""',
            metric_name="loss",
            direction="minimize",
            timeout_seconds=10,
        )
        result = await run_objective_eval(config, tmp_dir)
        assert result.crashed is True
        assert result.score == float("inf")

    async def test_timeout(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command="sleep 60",
            metric_extract='echo ""',
            metric_name="score",
            direction="maximize",
            timeout_seconds=1,
        )
        result = await run_objective_eval(config, tmp_dir)
        assert result.crashed is True
        assert "Timed out" in result.error_message

    async def test_metric_extraction_failure(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command='echo "no metric here"',
            metric_extract='echo ""',  # empty output
            metric_name="score",
            direction="maximize",
            timeout_seconds=10,
        )
        result = await run_objective_eval(config, tmp_dir)
        assert result.crashed is True
        assert "Could not extract" in result.error_message

    async def test_duration_tracked(self, success_config, tmp_dir):
        result = await run_objective_eval(success_config, tmp_dir)
        assert result.duration_seconds > 0


@pytest.mark.asyncio
class TestRunSetup:
    async def test_success(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command="echo ok",
            metric_extract="echo ok",
            setup_command="echo setup_done",
        )
        assert await run_setup(config, tmp_dir) is True

    async def test_failure(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command="echo ok",
            metric_extract="echo ok",
            setup_command="exit 1",
        )
        assert await run_setup(config, tmp_dir) is False

    async def test_no_setup(self, tmp_dir):
        config = ObjectiveEvalConfig(
            run_command="echo ok",
            metric_extract="echo ok",
        )
        assert await run_setup(config, tmp_dir) is True
