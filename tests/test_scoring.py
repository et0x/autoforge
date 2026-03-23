"""Tests for weighted consensus scoring."""

import pytest

from autoforge.eval.scoring import partial_consensus, score_summary, weighted_consensus
from autoforge.state import AgentScore


def _score(agent: str, weight: float, score: float, error: bool = False) -> AgentScore:
    return AgentScore(agent=agent, weight=weight, score=score, error=error)


class TestWeightedConsensus:
    def test_simple(self):
        scores = [_score("a", 0.6, 8.0), _score("b", 0.4, 6.0)]
        assert weighted_consensus(scores) == pytest.approx(7.2)

    def test_single_agent(self):
        scores = [_score("a", 1.0, 9.0)]
        assert weighted_consensus(scores) == pytest.approx(9.0)

    def test_empty(self):
        assert weighted_consensus([]) == 0.0

    def test_with_error_agent(self):
        scores = [
            _score("a", 0.5, 8.0),
            _score("b", 0.5, 5.0, error=True),  # fallback score
        ]
        assert weighted_consensus(scores) == pytest.approx(6.5)

    def test_many_agents(self):
        scores = [
            _score("a", 0.25, 10.0),
            _score("b", 0.25, 8.0),
            _score("c", 0.25, 6.0),
            _score("d", 0.25, 4.0),
        ]
        assert weighted_consensus(scores) == pytest.approx(7.0)


class TestPartialConsensus:
    def test_renormalizes(self):
        # Only agent "a" has finished (weight 0.6 out of 1.0)
        scores = [_score("a", 0.6, 8.0)]
        # Should normalize: 8.0 * (0.6/0.6) = 8.0
        assert partial_consensus(scores) == pytest.approx(8.0)

    def test_two_of_three(self):
        scores = [_score("a", 0.5, 8.0), _score("b", 0.3, 6.0)]
        # Normalize: (8*0.5 + 6*0.3) / 0.8 = 5.8/0.8 = 7.25
        assert partial_consensus(scores) == pytest.approx(7.25)

    def test_empty(self):
        assert partial_consensus([]) == 0.0


class TestScoreSummary:
    def test_format(self):
        scores = [_score("agent-a", 0.6, 8.0), _score("agent-b", 0.4, 6.0)]
        summary = score_summary(scores)
        assert "agent-a" in summary
        assert "agent-b" in summary
        assert "Consensus" in summary
        assert "7.20" in summary
