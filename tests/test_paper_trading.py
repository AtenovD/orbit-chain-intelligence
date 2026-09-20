from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.paper_trading import (
    close_paper_position,
    evaluate_historical_decision,
    open_paper_position,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(identifier: str, minutes: int, price: float, kind: str = "trade"):
    return {
        "id": identifier,
        "observed_at": NOW + timedelta(minutes=minutes),
        "price": price,
        "kind": kind,
    }


def test_replay_excludes_pre_decision_data_and_non_executable_marks():
    result = evaluate_historical_decision(
        decision="ENTER",
        decision_at=NOW,
        observations=[
            observation("past", -1, 1),
            observation("mark", 1, 99, "mark"),
            observation("entry", 2, 10),
            observation("exit", 30, 12),
            observation("too-late", 70, 100),
        ],
        horizon_seconds=3600,
        fee_bps=0,
        slippage_bps=0,
    )
    assert result["status"] == "complete"
    assert result["entry_observation_id"] == "entry"
    assert result["exit_observation_id"] == "exit"
    assert result["benchmark_return_pct"] == pytest.approx(20)
    assert result["strategy_return_pct"] == pytest.approx(20)
    assert result["anti_leakage"]["marks_excluded"] is True


def test_replay_is_inconclusive_without_two_post_decision_trades():
    result = evaluate_historical_decision(
        decision="ENTER",
        decision_at=NOW,
        observations=[observation("only", 1, 10)],
        horizon_seconds=3600,
    )
    assert result["status"] == "inconclusive"
    assert result["outcome"] == "insufficient_data"


def test_skip_and_watch_are_scored_without_opening_a_position():
    falling = [observation("a", 1, 10), observation("b", 10, 8)]
    skip = evaluate_historical_decision(
        decision="SKIP", decision_at=NOW, observations=falling, horizon_seconds=3600
    )
    assert skip["outcome"] == "correct"
    assert skip["strategy_return_pct"] == 0

    watch = evaluate_historical_decision(
        decision="WATCH",
        decision_at=NOW,
        observations=[observation("a", 1, 10), observation("b", 10, 10.1)],
        horizon_seconds=3600,
        watch_band_pct=3,
    )
    assert watch["outcome"] == "correct"


def test_paper_trade_math_charges_entry_exit_fees_and_adverse_slippage():
    opened = open_paper_position(price=10, notional=1000, fee_bps=10, slippage_bps=100)
    assert opened["entry_price"] == pytest.approx(10.1)
    assert opened["entry_fee"] == pytest.approx(1)
    closed = close_paper_position(
        entry_price=opened["entry_price"],
        quantity=opened["quantity"],
        notional=1000,
        exit_price=12,
        entry_fee=opened["entry_fee"],
        fee_bps=10,
        slippage_bps=100,
    )
    assert closed["exit_price"] == pytest.approx(11.88)
    assert closed["fees_paid"] > 2
    assert 15 < closed["return_pct"] < 20
