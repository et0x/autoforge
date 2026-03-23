"""The optimization loop — the heart of autoforge."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from anthropic import AsyncAnthropic

from autoforge.config import (
    EvalMode,
    PanelConfig,
    ProgramConfig,
    ProjectConfig,
)
from autoforge.eval.objective import run_objective_eval, run_setup
from autoforge.eval.panel import PanelEvaluator
from autoforge.git_ops import GitOps
from autoforge.driver.driver import run_driver_sdk, run_driver_api
from autoforge.driver.prompt_builder import build_driver_prompt
from autoforge.state import AgentScore, ProjectState
from autoforge.ui.progress import ProgressUI


class OptimizationEngine:
    """Orchestrates the full optimization loop."""

    def __init__(
        self,
        project_dir: Path,
        project: ProjectConfig,
        program: ProgramConfig,
        ui: ProgressUI,
        client: AsyncAnthropic | None = None,
        model_override: str | None = None,
        extra_skill_dirs: list[str] | None = None,
    ):
        self.project_dir = project_dir
        self.project = project
        self.program = program
        self.ui = ui
        self.client = client or AsyncAnthropic()
        self.git = GitOps(project_dir)
        self.model_override = model_override
        self.extra_skill_dirs = extra_skill_dirs or []

        # Determine direction
        if program.eval_mode == EvalMode.OBJECTIVE and program.objective:
            self.direction = program.objective.direction
        else:
            self.direction = "maximize"  # panel mode: higher is better

        # Load or create state
        try:
            self.state = ProjectState.load(project_dir)
        except FileNotFoundError:
            self.state = ProjectState(
                project_name=project.name,
                program_name=program.name,
                direction=self.direction,
            )

        # Panel evaluator (if panel mode)
        self.panel_evaluator: Optional[PanelEvaluator] = None
        if program.eval_mode == EvalMode.PANEL:
            panel_name = project.panel or program.default_panel
            if panel_name:
                panel = PanelConfig.load(panel_name, project_dir)
                self.panel_evaluator = PanelEvaluator(
                    panel, project_dir, self.client,
                    model_override=model_override,
                    extra_skill_dirs=self.extra_skill_dirs,
                )

    async def run(self, max_iterations: int | None = None, target_score: float | None = None) -> None:
        """Run the optimization loop."""
        max_iter = max_iterations or self.project.max_iterations or self.program.max_iterations
        target = target_score or self.project.target_score

        # Initialize git if needed
        self.git.init()
        if not self.state.branch:
            tag = self.project.name.replace(" ", "-").lower()
            self.state.branch = self.git.create_branch(tag)

        # Setup (one-time)
        if self.state.iteration == 0:
            await self._setup()
            baseline = await self._evaluate()
            self._record_iteration(0, baseline.score, "baseline", "Initial baseline", baseline)
            self.ui.show_baseline(self.state.best_score or 0.0)

        # Main loop
        while True:
            iteration = self.state.iteration + 1

            if max_iter and iteration > max_iter:
                self.ui.show_complete(self.state)
                break

            if target is not None and self.state.best_score is not None:
                if self._target_reached(self.state.best_score, target):
                    self.ui.show_target_reached(self.state, target)
                    break

            # Perfect score — nothing left to optimize
            if self.state.best_score is not None and self._is_perfect_score():
                self.ui.show_target_reached(self.state, self.state.best_score)
                break

            self.ui.start_iteration(iteration)

            # 1. Driver agent proposes a change
            start = time.monotonic()
            history = ProjectState.load_history(self.project_dir)
            prompt = build_driver_prompt(
                self.program, self.state, history,
                self.project_dir, self.project.extra_context,
            )

            model = self.model_override or self.project.driver_model or self.program.driver_model
            self.ui.show_phase("Driver thinking...")

            if self.program.driver_mode == "sdk":
                merged_skill_dirs = (self.program.driver_skill_dirs or []) + self.extra_skill_dirs
                description = await run_driver_sdk(
                    self.project_dir, prompt, model,
                    allowed_tools=self.program.driver_tools or None,
                    mcp_servers=self.program.driver_mcp_servers or None,
                    skill_dirs=merged_skill_dirs or None,
                    max_turns=self.program.driver_max_turns,
                )
            else:
                description = await run_driver_api(
                    self.project_dir, prompt, self.program, model, self.client,
                )

            self.ui.show_proposal(description)

            # 2. Commit
            commit_hash = self.git.commit(description, list(self.program.editable_files))

            # 3. Evaluate
            self.ui.show_phase("Evaluating...")
            result = await self._evaluate()
            elapsed = time.monotonic() - start

            # 4. Keep or discard
            score = result.score
            is_better = self.state.is_improvement(score)

            if is_better:
                status = "keep"
                self._record_iteration(iteration, score, status, description, result, commit_hash, elapsed)
                self.ui.show_kept(iteration, score, description, self.state.best_score)
            else:
                status = "discard"
                self._record_iteration(iteration, score, status, description, result, commit_hash, elapsed)
                self.git.revert_last()
                self.ui.show_discarded(iteration, score, description, self.state.best_score)

            self.state.save(self.project_dir)

    async def evaluate_once(self) -> float:
        """Run a single evaluation without the optimization loop."""
        result = await self._evaluate()
        return result.score

    # --- Private helpers ---

    async def _setup(self) -> None:
        """One-time setup: run setup commands, etc."""
        if self.program.eval_mode == EvalMode.OBJECTIVE and self.program.objective:
            if self.program.objective.setup_command:
                self.ui.show_phase("Running setup...")
                success = await run_setup(self.program.objective, self.project_dir)
                if not success:
                    self.ui.show_error("Setup command failed")

        for cmd in self.program.setup_commands:
            proc = await asyncio.create_subprocess_shell(
                cmd, cwd=self.project_dir,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            await proc.communicate()

    async def _evaluate(self) -> _EvalResult:
        """Run evaluation based on program's eval_mode."""
        if self.program.eval_mode == EvalMode.OBJECTIVE:
            return await self._eval_objective()
        else:
            return await self._eval_panel()

    async def _eval_objective(self) -> _EvalResult:
        assert self.program.objective is not None
        result = await run_objective_eval(self.program.objective, self.project_dir)
        return _EvalResult(
            score=result.score,
            crashed=result.crashed,
            error_message=result.error_message,
            raw_metrics={result.metric_name: result.score},
            duration_seconds=result.duration_seconds,
        )

    async def _eval_panel(self) -> _EvalResult:
        assert self.panel_evaluator is not None

        # Read content from editable files
        content_parts = []
        for pattern in self.program.editable_files:
            for path in sorted(self.project_dir.glob(pattern)):
                if path.is_file():
                    content_parts.append(f"## {path.name}\n\n{path.read_text()}")
        content = "\n\n".join(content_parts)

        # Build context from read-only files + extra context
        context_parts = []
        if self.project.extra_context:
            context_parts.append(self.project.extra_context)
        for pattern in self.program.read_only_files:
            for path in sorted(self.project_dir.glob(pattern)):
                if path.is_file():
                    context_parts.append(f"### {path.name}\n{path.read_text()}")
        context = "\n\n".join(context_parts)

        result = await self.panel_evaluator.evaluate(
            content=content,
            context=context,
            on_score=self.ui.on_agent_score,
        )

        # Save detailed scores
        ProjectState.save_iteration_scores(
            self.project_dir,
            self.state.iteration + 1,
            result.agent_scores,
            result.consensus_score,
        )

        return _EvalResult(
            score=result.consensus_score,
            agent_scores=result.agent_scores,
        )

    def _record_iteration(
        self,
        iteration: int,
        score: float,
        status: str,
        description: str,
        result: _EvalResult,
        commit_hash: str | None = None,
        duration: float = 0.0,
    ) -> None:
        record = self.state.record(
            iteration=iteration,
            score=score,
            status=status,
            description=description,
            commit_hash=commit_hash,
            duration_seconds=duration,
            agent_scores=result.agent_scores,
            raw_metrics=result.raw_metrics,
        )
        ProjectState.append_history(self.project_dir, record)

    def _target_reached(self, score: float, target: float) -> bool:
        if self.direction == "minimize":
            return score <= target
        return score >= target

    def _is_perfect_score(self) -> bool:
        """Check if the best score has hit the ceiling (panel) or floor (objective)."""
        score = self.state.best_score
        if score is None:
            return False
        if self.direction == "maximize":
            # Panel mode: max_score from panel config (default 10.0)
            if self.panel_evaluator:
                return score >= self.panel_evaluator.panel.max_score
            return False
        else:
            # Objective mode: 0.0 is the floor
            return score <= 0.0


class _EvalResult:
    """Internal wrapper for evaluation results."""
    def __init__(
        self,
        score: float,
        crashed: bool = False,
        error_message: str = "",
        agent_scores: list[AgentScore] | None = None,
        raw_metrics: dict | None = None,
        duration_seconds: float = 0.0,
    ):
        self.score = score
        self.crashed = crashed
        self.error_message = error_message
        self.agent_scores = agent_scores
        self.raw_metrics = raw_metrics
        self.duration_seconds = duration_seconds
