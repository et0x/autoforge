"""Typer CLI for autoforge."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from autoforge.ui.console import console

app = typer.Typer(
    name="autoforge",
    help="Autonomous optimization framework with pluggable evaluation.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

program_app = typer.Typer(help="Browse and create program templates.")
agent_app = typer.Typer(help="Browse and create evaluator agent personas.")
panel_app = typer.Typer(help="Browse and create evaluation panels.")

app.add_typer(program_app, name="program")
app.add_typer(agent_app, name="agent")
app.add_typer(panel_app, name="panel")


# ---------------------------------------------------------------------------
# autoforge init
# ---------------------------------------------------------------------------

@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    program: str = typer.Option(..., "--program", "-p", help="Program template to use"),
    panel: Optional[str] = typer.Option(None, "--panel", help="Override default evaluation panel"),
    directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Project directory (default: ./<name>)"),
):
    """Initialize a new optimization project."""
    from autoforge.config import ProgramConfig, ProjectConfig

    project_dir = Path(directory) if directory else Path.cwd() / name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".autoforge").mkdir(exist_ok=True)

    # Load program to get defaults and template files
    prog = ProgramConfig.load(program)

    # Create project config
    project = ProjectConfig(
        name=name,
        program=program,
        panel=panel or prog.default_panel,
    )
    project.save(project_dir)

    # Copy template files from program
    if prog.template_files:
        import importlib.resources
        prog_dir = Path(importlib.resources.files("autoforge")).parent.parent / "library" / "programs"  # type: ignore
        for tmpl in prog.template_files:
            src = prog_dir / tmpl
            if src.is_file():
                dst = project_dir / Path(tmpl).name
                dst.write_text(src.read_text())

    console.print(f"[green]Project '{name}' initialized at {project_dir}[/]")
    console.print(f"  Program: {program}")
    if project.panel:
        console.print(f"  Panel: {project.panel}")
    console.print(f"\n  Run [bold]cd {project_dir} && autoforge run[/] to start optimizing.")


# ---------------------------------------------------------------------------
# autoforge run
# ---------------------------------------------------------------------------

@app.command()
def run(
    iterations: Optional[int] = typer.Option(None, "--iterations", "-n", help="Max iterations"),
    target: Optional[float] = typer.Option(None, "--target", "-t", help="Target score to stop at"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override model for all agents (e.g. opus, claude-opus-4-6)"),
    directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Project directory (default: cwd)"),
):
    """Start the optimization loop."""
    asyncio.run(_run_async(iterations, target, model, directory))


async def _run_async(iterations: int | None, target: float | None, model: str | None, directory: str | None) -> None:
    from autoforge.config import ProgramConfig, ProjectConfig
    from autoforge.engine import OptimizationEngine
    from autoforge.ui.progress import ProgressUI

    project_dir = Path(directory) if directory else Path.cwd()
    project = ProjectConfig.load(project_dir)
    program = ProgramConfig.load(project.program, project_dir)

    panel_name = project.panel or program.default_panel

    ui = ProgressUI(
        project_name=project.name,
        program_name=program.name,
        panel_name=panel_name,
        eval_mode=program.eval_mode.value,
        direction=program.objective.direction if program.objective else "maximize",
    )
    ui.show_header()

    engine = OptimizationEngine(project_dir, project, program, ui, model_override=model)
    await engine.run(max_iterations=iterations, target_score=target)


# ---------------------------------------------------------------------------
# autoforge eval
# ---------------------------------------------------------------------------

@app.command()
def eval(
    agent_name: Optional[str] = typer.Option(None, "--agent", "-a", help="Test a single agent"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="File to evaluate"),
    directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Project directory"),
):
    """Run a single evaluation (without the optimization loop)."""
    asyncio.run(_eval_async(agent_name, file, directory))


async def _eval_async(agent_name: str | None, file: str | None, directory: str | None) -> None:
    from anthropic import AsyncAnthropic
    from autoforge.config import AgentConfig, PanelConfig, ProgramConfig, ProjectConfig
    from autoforge.eval.agent_runner import AgentRunner
    from autoforge.eval.panel import PanelEvaluator
    from autoforge.eval.scoring import weighted_consensus

    project_dir = Path(directory) if directory else Path.cwd()

    if agent_name and file:
        # Single agent test
        agent = AgentConfig.load(agent_name, project_dir)
        content = Path(file).read_text()
        runner = AgentRunner()
        score = await runner.run_evaluator(agent, content, weight=1.0)
        console.print(f"\n[agent]{agent.name}[/] scored: [score]{score.score:.1f}/10[/]")
        console.print(f"  Reasoning: {score.reasoning}")
        if score.strengths:
            console.print(f"  Strengths: {', '.join(score.strengths)}")
        if score.weaknesses:
            console.print(f"  Weaknesses: {', '.join(score.weaknesses)}")
        return

    # Full panel evaluation
    project = ProjectConfig.load(project_dir)
    program = ProgramConfig.load(project.program, project_dir)
    panel_name = project.panel or program.default_panel
    if not panel_name:
        console.print("[crash]No panel configured for this project[/]")
        raise typer.Exit(1)

    panel = PanelConfig.load(panel_name, project_dir)
    evaluator = PanelEvaluator(panel, project_dir)

    # Read content
    content_parts = []
    for pattern in program.editable_files:
        for path in sorted(project_dir.glob(pattern)):
            if path.is_file():
                content_parts.append(path.read_text())
    content = "\n\n".join(content_parts)

    context = project.extra_context or ""

    async def on_score(s: AgentScore) -> None:
        status = "ERR" if s.error else f"{s.score:.1f}"
        console.print(f"  [agent]{s.agent:<28s}[/] {status:>5s}  (w: {s.weight:.2f})")

    console.print(f"\n[bold]Evaluating with panel: {panel.name}[/]\n")
    result = await evaluator.evaluate(content, context, on_score)
    consensus = result.consensus_score
    console.print(f"\n  [bold]Consensus score:[/] [score]{consensus:.2f}/10[/]\n")


# ---------------------------------------------------------------------------
# autoforge status / history
# ---------------------------------------------------------------------------

@app.command()
def status(
    directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Project directory"),
):
    """Show current project state."""
    from autoforge.config import ProjectConfig
    from autoforge.state import ProjectState

    project_dir = Path(directory) if directory else Path.cwd()
    project = ProjectConfig.load(project_dir)
    state = ProjectState.load(project_dir)

    console.print(f"\n[bold]Project:[/] {project.name}")
    console.print(f"[bold]Program:[/] {project.program}")
    if project.panel:
        console.print(f"[bold]Panel:[/] {project.panel}")
    console.print(f"[bold]Iteration:[/] {state.iteration}")
    console.print(f"[bold]Best score:[/] [score]{state.best_score}[/] (iteration {state.best_iteration})")
    console.print(f"[bold]Direction:[/] {state.direction}")
    console.print()


@app.command()
def history(
    directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Project directory"),
    last: int = typer.Option(20, "--last", "-n", help="Show last N iterations"),
):
    """Show iteration history."""
    from autoforge.state import ProjectState

    project_dir = Path(directory) if directory else Path.cwd()
    records = ProjectState.load_history(project_dir)

    if not records:
        console.print("[dim]No history found.[/]")
        return

    table = Table(title="Iteration History", show_lines=False)
    table.add_column("#", justify="right", width=4)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Status", width=8)
    table.add_column("Description")
    table.add_column("Commit", width=8, style="dim")

    for rec in records[-last:]:
        style = {"keep": "green", "discard": "dim", "crash": "red", "baseline": "cyan"}.get(rec.status, "")
        table.add_row(
            str(rec.iteration),
            f"{rec.score:.4f}",
            rec.status,
            rec.description,
            rec.commit_hash or "",
            style=style,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# program list / show
# ---------------------------------------------------------------------------

@program_app.command("list")
def program_list():
    """List available program templates."""
    from autoforge.config import list_configs
    import yaml

    configs = list_configs("programs")
    if not configs:
        console.print("[dim]No programs found.[/]")
        return

    table = Table(title="Programs")
    table.add_column("Name", style="bold")
    table.add_column("Eval Mode")
    table.add_column("Description")
    table.add_column("Source", style="dim")

    for name, path in sorted(configs.items()):
        with open(path) as f:
            data = yaml.safe_load(f)
        table.add_row(
            name,
            data.get("eval_mode", "?"),
            data.get("description", "")[:60],
            _source_label(path),
        )

    console.print(table)


@program_app.command("show")
def program_show(name: str):
    """Show details of a program template."""
    from autoforge.config import ProgramConfig
    prog = ProgramConfig.load(name)
    console.print(f"\n[bold]{prog.name}[/] (v{prog.version})")
    console.print(f"  {prog.description}")
    console.print(f"  Eval: {prog.eval_mode.value}")
    console.print(f"  Editable: {', '.join(prog.editable_files)}")
    if prog.read_only_files:
        console.print(f"  Read-only: {', '.join(prog.read_only_files)}")
    console.print(f"  Driver model: {prog.driver_model}")
    console.print()


# ---------------------------------------------------------------------------
# agent list / show
# ---------------------------------------------------------------------------

@agent_app.command("list")
def agent_list():
    """List available evaluator agent personas."""
    from autoforge.config import list_configs
    import yaml

    configs = list_configs("agents")
    if not configs:
        console.print("[dim]No agents found.[/]")
        return

    table = Table(title="Agent Personas")
    table.add_column("Name", style="bold")
    table.add_column("Model")
    table.add_column("Description")
    table.add_column("Source", style="dim")

    for name, path in sorted(configs.items()):
        with open(path) as f:
            data = yaml.safe_load(f)
        table.add_row(
            name,
            data.get("model", "haiku"),
            data.get("description", "")[:60],
            _source_label(path),
        )

    console.print(table)


@agent_app.command("show")
def agent_show(name: str):
    """Show details of an agent persona."""
    from autoforge.config import AgentConfig
    agent = AgentConfig.load(name)
    console.print(f"\n[bold]{agent.name}[/]")
    console.print(f"  {agent.description}")
    console.print(f"  Model: {agent.model}, Temp: {agent.temperature}")
    console.print(f"\n[dim]System Prompt:[/]\n{agent.system_prompt}")
    if agent.scoring_rubric:
        console.print(f"[dim]Scoring Rubric:[/]\n{agent.scoring_rubric}")


# ---------------------------------------------------------------------------
# panel list / show
# ---------------------------------------------------------------------------

@panel_app.command("list")
def panel_list():
    """List available evaluation panels."""
    from autoforge.config import list_configs
    import yaml

    configs = list_configs("panels")
    if not configs:
        console.print("[dim]No panels found.[/]")
        return

    table = Table(title="Panels")
    table.add_column("Name", style="bold")
    table.add_column("Agents")
    table.add_column("Description")
    table.add_column("Source", style="dim")

    for name, path in sorted(configs.items()):
        with open(path) as f:
            data = yaml.safe_load(f)
        members = data.get("members", [])
        agent_count = len(members)
        table.add_row(
            name,
            str(agent_count),
            data.get("description", "")[:60],
            _source_label(path),
        )

    console.print(table)


@panel_app.command("show")
def panel_show(name: str):
    """Show details of an evaluation panel."""
    from autoforge.config import PanelConfig
    panel = PanelConfig.load(name)
    console.print(f"\n[bold]{panel.name}[/]")
    console.print(f"  {panel.description}")
    console.print()

    table = Table(title="Panel Members")
    table.add_column("Agent", style="agent")
    table.add_column("Weight", justify="right")
    table.add_column("Bar")

    for member in sorted(panel.members, key=lambda m: m.weight, reverse=True):
        bar_len = int(member.weight * 40)
        bar = "[green]" + "█" * bar_len + "[/]"
        table.add_row(member.agent, f"{member.weight:.2f}", bar)

    console.print(table)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _source_label(path: Path) -> str:
    s = str(path)
    if "/.autoforge/" in s:
        return "project"
    if str(Path.home()) in s and "/.autoforge/" in s:
        return "user"
    return "built-in"
