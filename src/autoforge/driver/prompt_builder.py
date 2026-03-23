"""Build the driver agent's prompt from program config + project state."""

from __future__ import annotations

from pathlib import Path

from autoforge.config import ProgramConfig
from autoforge.state import IterationRecord, ProjectState


def build_driver_prompt(
    program: ProgramConfig,
    state: ProjectState,
    history: list[IterationRecord],
    workspace: Path,
    extra_context: str = "",
) -> str:
    """Build a comprehensive prompt for the driver agent.

    Includes: program instructions, current state, recent history with
    per-agent feedback, file contents, and constraints.
    """
    parts: list[str] = []

    # 1. Program instructions (the "program.md" equivalent)
    parts.append(f"# Optimization Instructions\n\n{program.driver_instructions}")

    # 2. Current state
    direction_word = "lower" if state.direction == "minimize" else "higher"
    parts.append(f"""
# Current State
- Iteration: {state.iteration + 1}
- Best score: {state.best_score} (iteration {state.best_iteration})
- Direction: {direction_word} is better
""")

    if extra_context:
        parts.append(f"# Additional Context\n\n{extra_context}")

    # 3. Recent history (last 10 iterations)
    if history:
        recent = history[-10:]
        history_lines = ["# Recent History", ""]
        history_lines.append(f"{'Iter':>4}  {'Score':>8}  {'Status':<8}  Description")
        history_lines.append(f"{'─'*4}  {'─'*8}  {'─'*8}  {'─'*40}")
        for rec in recent:
            history_lines.append(
                f"{rec.iteration:>4}  {rec.score:>8.4f}  {rec.status:<8}  {rec.description}"
            )
        parts.append("\n".join(history_lines))

        # 4. Per-agent feedback from last evaluation (panel mode)
        last = recent[-1]
        if last.agent_scores:
            feedback_lines = ["# Feedback from Last Evaluation", ""]
            for s in sorted(last.agent_scores, key=lambda x: x.weight, reverse=True):
                feedback_lines.append(f"## {s.agent} (score: {s.score:.1f}, weight: {s.weight:.2f})")
                feedback_lines.append(f"**Reasoning:** {s.reasoning}")
                if s.strengths:
                    feedback_lines.append("**Strengths:** " + "; ".join(s.strengths))
                if s.weaknesses:
                    feedback_lines.append("**Weaknesses:** " + "; ".join(s.weaknesses))
                feedback_lines.append("")
            parts.append("\n".join(feedback_lines))

    # 5. File contents
    parts.append("# Editable Files\n")
    for pattern in program.editable_files:
        for path in sorted(workspace.glob(pattern)):
            if path.is_file():
                content = path.read_text()
                rel = path.relative_to(workspace)
                parts.append(f"## `{rel}`\n```\n{content}\n```\n")

    if program.read_only_files:
        parts.append("# Read-Only Context Files\n")
        for pattern in program.read_only_files:
            for path in sorted(workspace.glob(pattern)):
                if path.is_file():
                    content = path.read_text()
                    rel = path.relative_to(workspace)
                    parts.append(f"## `{rel}` (DO NOT EDIT)\n```\n{content}\n```\n")

    # 6. Constraints
    editable = ", ".join(program.editable_files)
    constraints = [f"- You may ONLY edit: {editable}"]
    if program.read_only_files:
        readonly = ", ".join(program.read_only_files)
        constraints.append(f"- Do NOT edit: {readonly}")
    if program.simplicity_criterion:
        constraints.append(
            "- Prefer simpler changes. Small improvements from complexity are not worth it."
        )
    constraints.append(
        "- Make ONE focused change per iteration. Describe what you changed concisely."
    )
    parts.append("# Constraints\n\n" + "\n".join(constraints))

    # 7. Output instructions
    parts.append("""
# Your Task

1. Review the current state, history, and feedback
2. Decide on a single focused improvement to try
3. Edit the editable file(s) to implement your change
4. Respond with a SHORT description (one line) of what you changed
""")

    return "\n\n".join(parts)
