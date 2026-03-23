"""Weighted consensus scoring utilities."""

from __future__ import annotations

from autoforge.state import AgentScore


def weighted_consensus(scores: list[AgentScore]) -> float:
    """Compute weighted consensus score from agent scores.

    Returns the weighted sum: Σ(weight_i × score_i).
    Agents that errored out are included with their fallback score.
    """
    if not scores:
        return 0.0
    return sum(s.score * s.weight for s in scores)


def partial_consensus(scores: list[AgentScore]) -> float:
    """Compute partial consensus from scores received so far.

    Re-normalizes weights to sum to 1.0 across completed agents only.
    Useful for live UI updates while agents are still running.
    """
    if not scores:
        return 0.0
    total_weight = sum(s.weight for s in scores)
    if total_weight == 0:
        return 0.0
    return sum(s.score * (s.weight / total_weight) for s in scores)


def score_summary(scores: list[AgentScore]) -> str:
    """Format a human-readable summary of agent scores."""
    lines = []
    for s in sorted(scores, key=lambda x: x.weight, reverse=True):
        status = "ERR" if s.error else f"{s.score:.1f}"
        lines.append(f"  {s.agent:<30s} {status:>5s}  (w: {s.weight:.2f})")
    consensus = weighted_consensus(scores)
    lines.append(f"  {'Consensus':<30s} {consensus:>5.2f}")
    return "\n".join(lines)
