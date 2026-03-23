"""Objective evaluation: run a command and extract a numeric metric."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from autoforge.config import ObjectiveEvalConfig


@dataclass
class ObjectiveResult:
    """Result of an objective evaluation."""
    score: float
    raw_output: str
    metric_name: str
    duration_seconds: float
    crashed: bool = False
    error_message: str = ""
    extra_metrics: dict[str, float] | None = None


async def run_objective_eval(
    config: ObjectiveEvalConfig,
    working_dir: Path,
    on_progress: Optional[object] = None,  # callback for UI updates
) -> ObjectiveResult:
    """Run the evaluation command and extract the metric.

    Handles timeouts, crashes, and metric extraction.
    """
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_shell(
            config.run_command,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            elapsed = time.monotonic() - start
            return ObjectiveResult(
                score=float("inf") if config.direction == "minimize" else float("-inf"),
                raw_output="",
                metric_name=config.metric_name,
                duration_seconds=elapsed,
                crashed=True,
                error_message=f"Timed out after {config.timeout_seconds}s",
            )

        elapsed = time.monotonic() - start
        raw_output = stdout_bytes.decode("utf-8", errors="replace")

        # Write log file
        log_path = working_dir / "run.log"
        log_path.write_text(raw_output)

        if proc.returncode != 0:
            # Try to get useful error from tail of output
            tail = "\n".join(raw_output.splitlines()[-20:])
            return ObjectiveResult(
                score=float("inf") if config.direction == "minimize" else float("-inf"),
                raw_output=raw_output,
                metric_name=config.metric_name,
                duration_seconds=elapsed,
                crashed=True,
                error_message=f"Exit code {proc.returncode}:\n{tail}",
            )

        # Extract metric
        score = await _extract_metric(config, working_dir, raw_output)
        if score is None:
            return ObjectiveResult(
                score=float("inf") if config.direction == "minimize" else float("-inf"),
                raw_output=raw_output,
                metric_name=config.metric_name,
                duration_seconds=elapsed,
                crashed=True,
                error_message="Could not extract metric from output",
            )

        return ObjectiveResult(
            score=score,
            raw_output=raw_output,
            metric_name=config.metric_name,
            duration_seconds=elapsed,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        return ObjectiveResult(
            score=float("inf") if config.direction == "minimize" else float("-inf"),
            raw_output="",
            metric_name=config.metric_name,
            duration_seconds=elapsed,
            crashed=True,
            error_message=str(e),
        )


async def _extract_metric(
    config: ObjectiveEvalConfig,
    working_dir: Path,
    raw_output: str,
) -> float | None:
    """Run the metric extraction command and parse the result."""
    try:
        proc = await asyncio.create_subprocess_shell(
            config.metric_extract,
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        metric_line = stdout_bytes.decode("utf-8", errors="replace").strip()

        if not metric_line:
            return None

        match = re.search(config.metric_regex, metric_line)
        if match:
            return float(match.group())
        return None

    except Exception:
        return None


async def run_setup(config: ObjectiveEvalConfig, working_dir: Path) -> bool:
    """Run the one-time setup command. Returns True if successful."""
    if not config.setup_command:
        return True

    proc = await asyncio.create_subprocess_shell(
        config.setup_command,
        cwd=working_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    await proc.communicate()
    return proc.returncode == 0
