"""Transparent scorecards for resolved agent signals.

This module deliberately measures only observed historical outcomes.  It does not
alter prompts, model choice, or position size; humans decide how to use the data.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _probability_up(signal: dict[str, Any]) -> float:
    confidence = signal.get("confidence")
    value = float(confidence) / 100 if isinstance(confidence, (int, float)) else 0.5
    value = max(0.0, min(1.0, value))
    stance = str(signal.get("stance") or "abstain").lower()
    if stance == "support":
        return value
    if stance == "challenge":
        return 1 - value
    return 0.5


def build_agent_scorecards(
    resolved: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate direction hit-rate and Brier calibration for completed replay.

    Each item contains a resolved evaluation plus the latest AgentSignal for each
    agent that existed before that decision. Neutral and abstaining signals are
    visible but do not receive a directional hit/miss.
    """

    rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "agent_id": "",
            "agent_name": "Agent",
            "model": "",
            "signals": 0,
            "directional_signals": 0,
            "correct": 0,
            "incorrect": 0,
            "brier_total": 0.0,
            "confidence_total": 0.0,
            "resolved_decisions": set(),
        }
    )
    decisions = 0
    for item in resolved:
        benchmark = item.get("benchmark_return_pct")
        if not isinstance(benchmark, (int, float)):
            continue
        decisions += 1
        actual_up = float(benchmark) > 0
        evaluation_id = str(item.get("evaluation_id") or "")
        for signal in item.get("signals") or []:
            agent_id = str(signal.get("agent_id") or "")
            if not agent_id or not bool(signal.get("valid")):
                continue
            row = rows[agent_id]
            row["agent_id"] = agent_id
            row["agent_name"] = str(signal.get("agent_name") or "Agent")
            row["model"] = str(signal.get("model") or "")
            row["signals"] += 1
            row["resolved_decisions"].add(evaluation_id)
            probability = _probability_up(signal)
            row["brier_total"] += (probability - int(actual_up)) ** 2
            confidence = signal.get("confidence")
            if isinstance(confidence, (int, float)):
                row["confidence_total"] += float(confidence)
            stance = str(signal.get("stance") or "abstain").lower()
            if stance not in {"support", "challenge"} or probability == 0.5:
                continue
            row["directional_signals"] += 1
            predicted_up = probability > 0.5
            if predicted_up == actual_up:
                row["correct"] += 1
            else:
                row["incorrect"] += 1

    scorecards = []
    for row in rows.values():
        signals = row.pop("signals")
        directional = row.pop("directional_signals")
        correct = row.pop("correct")
        incorrect = row.pop("incorrect")
        brier_total = row.pop("brier_total")
        confidence_total = row.pop("confidence_total")
        decision_ids = row.pop("resolved_decisions")
        scorecards.append(
            {
                **row,
                "signals": signals,
                "resolved_decisions": len(decision_ids),
                "directional_signals": directional,
                "correct": correct,
                "incorrect": incorrect,
                "hit_rate": correct / directional if directional else None,
                "brier_score": brier_total / signals if signals else None,
                "average_confidence": confidence_total / signals if signals else None,
            }
        )
    scorecards.sort(
        key=lambda item: (
            item["hit_rate"] is not None,
            item["hit_rate"] or -1,
            item["directional_signals"],
        ),
        reverse=True,
    )
    return {
        "contract_version": "agent-scorecard.v1",
        "resolved_decisions": decisions,
        "scorecards": scorecards,
        "notes": [
            "Observational historical score only; it does not alter agents or models.",
            "Brier score is lower when directional confidence is better calibrated.",
            "Neutral and abstaining signals are preserved but excluded from hit rate.",
        ],
    }
