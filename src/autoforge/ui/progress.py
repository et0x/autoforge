"""Live progress display for the optimization loop."""

from __future__ import annotations

from typing import Optional

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from autoforge.state import AgentScore, IterationRecord, ProjectState
from autoforge.ui.console import console


class ProgressUI:
    """Rich terminal UI for the optimization loop.

    Shows: header panel, current evaluation progress, iteration history.
    """

    def __init__(
        self,
        project_name: str,
        program_name: str,
        panel_name: str | None = None,
        eval_mode: str = "panel",
        direction: str = "maximize",
    ):
        self.project_name = project_name
        self.program_name = program_name
        self.panel_name = panel_name
        self.eval_mode = eval_mode
        self.direction = direction

        # State for live display
        self.current_iteration: int = 0
        self.best_score: Optional[float] = None
        self.best_iteration: Optional[int] = None
        self.current_proposal: str = ""
        self.current_phase: str = ""
        self.agent_scores: list[AgentScore] = []
        self.pending_agents: list[str] = []
        self.history: list[_HistoryEntry] = []

        self._live: Optional[Live] = None

    # --- Public API ---

    def show_header(self) -> None:
        eval_info = f"panel ({self.panel_name})" if self.panel_name else f"objective ({self.direction})"
        header = Table.grid(padding=(0, 2))
        header.add_row(
            f"[bold]Project:[/] {self.project_name}",
            f"[bold]Program:[/] {self.program_name}",
        )
        header.add_row(
            f"[bold]Eval:[/] {eval_info}",
            f"[bold]Best:[/] --",
        )
        console.print(Panel(header, title="[header] autoforge [/header]", border_style="blue"))
        console.print()

    def show_baseline(self, score: float) -> None:
        self.best_score = score
        self.best_iteration = 0
        self.history.append(_HistoryEntry(0, score, "baseline", "Initial baseline"))
        console.print(f"  [baseline]Baseline score:[/] [score]{score:.4f}[/]")
        console.print()

    def start_iteration(self, iteration: int) -> None:
        self.current_iteration = iteration
        self.current_proposal = ""
        self.current_phase = ""
        self.agent_scores = []
        self.pending_agents = []
        console.rule(f"[bold]Iteration {iteration}[/]")

    def show_phase(self, phase: str) -> None:
        self.current_phase = phase
        console.print(f"  [phase]{phase}[/]")

    def show_proposal(self, description: str) -> None:
        self.current_proposal = description
        console.print(f"  [bold]Proposal:[/] {description}")
        console.print()

    def set_pending_agents(self, agent_names: list[str]) -> None:
        self.pending_agents = list(agent_names)

    async def on_agent_score(self, score: AgentScore) -> None:
        """Callback for when an individual agent finishes scoring."""
        self.agent_scores.append(score)
        if score.agent in self.pending_agents:
            self.pending_agents.remove(score.agent)
        self._print_agent_score(score)

    def show_panel_result(self, consensus: float, scores: list[AgentScore]) -> None:
        """Show final panel result after all agents complete."""
        console.print()
        console.print(f"  [bold]Consensus:[/] [score]{consensus:.2f}[/]")

    def show_kept(
        self,
        iteration: int,
        score: float,
        description: str,
        best_score: float | None,
    ) -> None:
        delta = ""
        if best_score is not None and self.best_score is not None:
            diff = score - self.best_score
            sign = "+" if diff >= 0 else ""
            delta = f" ({sign}{diff:.4f})"

        self.best_score = score
        self.best_iteration = iteration
        self.history.append(_HistoryEntry(iteration, score, "keep", description))

        console.print()
        console.print(f"  [keep]KEEP[/] score={score:.4f}{delta}  {description}")
        console.print()

    def show_discarded(
        self,
        iteration: int,
        score: float,
        description: str,
        best_score: float | None,
    ) -> None:
        delta = ""
        if best_score is not None:
            diff = score - (best_score or 0)
            sign = "+" if diff >= 0 else ""
            delta = f" ({sign}{diff:.4f})"

        self.history.append(_HistoryEntry(iteration, score, "discard", description))

        console.print()
        console.print(f"  [discard]DISCARD[/] score={score:.4f}{delta}  {description}")
        console.print()

    def show_error(self, message: str) -> None:
        console.print(f"  [crash]ERROR:[/] {message}")

    def show_complete(self, state: ProjectState) -> None:
        console.print()
        console.rule("[bold green]Optimization Complete[/]")
        console.print(f"  Best score: [score]{state.best_score:.4f}[/] (iteration {state.best_iteration})")
        console.print(f"  Total iterations: {state.iteration}")
        console.print()
        self._print_history_table()

    def show_target_reached(self, state: ProjectState, target: float) -> None:
        console.print()
        console.rule("[bold green]Target Reached![/]")
        console.print(f"  Target: {target:.4f}  Achieved: [score]{state.best_score:.4f}[/] (iteration {state.best_iteration})")
        console.print()
        self._print_history_table()

    # --- Private helpers ---

    def _print_agent_score(self, score: AgentScore) -> None:
        bar = _score_bar(score.score)
        status = "[crash]ERR[/]" if score.error else f"{score.score:.1f}"
        console.print(f"    [agent]{score.agent:<28s}[/] {bar}  {status:>5s}  (w: {score.weight:.2f})")

    def _print_history_table(self) -> None:
        table = Table(title="Iteration History", show_lines=False, padding=(0, 1))
        table.add_column("#", justify="right", style="dim", width=4)
        table.add_column("Score", justify="right", width=8)
        table.add_column("Delta", justify="right", width=8)
        table.add_column("Status", width=8)
        table.add_column("Description")

        best_so_far = None
        for entry in self.history:
            delta_str = ""
            if entry.status in ("keep", "baseline") and best_so_far is not None:
                diff = entry.score - best_so_far
                sign = "+" if diff >= 0 else ""
                delta_str = f"{sign}{diff:.4f}"

            style = {
                "keep": "green",
                "discard": "dim",
                "crash": "red",
                "baseline": "cyan",
            }.get(entry.status, "")

            status_display = {
                "keep": "[keep]keep[/]",
                "discard": "[discard]drop[/]",
                "crash": "[crash]crash[/]",
                "baseline": "[baseline]base[/]",
            }.get(entry.status, entry.status)

            table.add_row(
                str(entry.iteration),
                f"{entry.score:.4f}",
                delta_str,
                status_display,
                entry.description,
                style=style if entry.status == "discard" else "",
            )

            if entry.status in ("keep", "baseline"):
                best_so_far = entry.score

        console.print(table)


def _score_bar(score: float, width: int = 10) -> str:
    """Create a visual score bar like ▰▰▰▰▰▰▰▱▱▱."""
    filled = int(round(score / 10 * width))
    empty = width - filled
    return "[green]" + "▰" * filled + "[/][dim]" + "▱" * empty + "[/]"


class _HistoryEntry:
    def __init__(self, iteration: int, score: float, status: str, description: str):
        self.iteration = iteration
        self.score = score
        self.status = status
        self.description = description
