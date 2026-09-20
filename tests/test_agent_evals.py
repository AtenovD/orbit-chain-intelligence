from __future__ import annotations

import pytest

from orchestrator.agent_evals import build_agent_scorecards


def test_scorecard_measures_direction_and_calibration_without_counting_neutral_as_hit():
    summary = build_agent_scorecards(
        [
            {
                "evaluation_id": "eval-1",
                "benchmark_return_pct": 12,
                "signals": [
                    {"agent_id": "a", "agent_name": "Ava", "model": "m", "valid": True, "stance": "support", "confidence": 90},
                    {"agent_id": "b", "agent_name": "Priya", "model": "m", "valid": True, "stance": "challenge", "confidence": 80},
                    {"agent_id": "c", "agent_name": "Sofia", "model": "m", "valid": True, "stance": "neutral", "confidence": 50},
                ],
            }
        ]
    )
    by_id = {item["agent_id"]: item for item in summary["scorecards"]}
    assert summary["resolved_decisions"] == 1
    assert by_id["a"]["hit_rate"] == 1
    assert by_id["a"]["brier_score"] == pytest.approx(0.01)
    assert by_id["b"]["hit_rate"] == 0
    assert by_id["c"]["directional_signals"] == 0
    assert by_id["c"]["hit_rate"] is None


def test_invalid_signal_is_not_scored():
    summary = build_agent_scorecards(
        [{"evaluation_id": "eval-1", "benchmark_return_pct": -5, "signals": [{"agent_id": "bad", "valid": False}]}]
    )
    assert summary["scorecards"] == []
