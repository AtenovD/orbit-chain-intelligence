"""Deterministic historical evaluation and paper-execution arithmetic.

The model supplies a decision; it never supplies fills or performance.  Those are
derived from timestamped observations with explicit fees and adverse slippage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def execution_price(price: float, *, entering: bool, slippage_bps: float) -> float:
    """Apply adverse slippage to a long-only paper fill."""

    rate = max(0.0, float(slippage_bps)) / 10_000
    return float(price) * (1 + rate if entering else 1 - rate)


def open_paper_position(
    *, price: float, notional: float, fee_bps: float, slippage_bps: float
) -> dict[str, float]:
    if price <= 0 or notional <= 0:
        raise ValueError("Price and notional must be positive")
    fill = execution_price(price, entering=True, slippage_bps=slippage_bps)
    entry_fee = float(notional) * max(0.0, float(fee_bps)) / 10_000
    quantity = (float(notional) - entry_fee) / fill
    return {"entry_price": fill, "entry_fee": entry_fee, "quantity": quantity}


def close_paper_position(
    *, entry_price: float, quantity: float, notional: float, exit_price: float,
    entry_fee: float, fee_bps: float, slippage_bps: float,
) -> dict[str, float]:
    if min(entry_price, quantity, notional, exit_price) <= 0:
        raise ValueError("Paper position values must be positive")
    fill = execution_price(exit_price, entering=False, slippage_bps=slippage_bps)
    gross_proceeds = quantity * fill
    exit_fee = gross_proceeds * max(0.0, float(fee_bps)) / 10_000
    net_proceeds = gross_proceeds - exit_fee
    pnl = net_proceeds - float(notional)
    return {
        "exit_price": fill,
        "exit_fee": exit_fee,
        "fees_paid": float(entry_fee) + exit_fee,
        "realized_pnl": pnl,
        "return_pct": pnl / float(notional) * 100,
    }


def evaluate_historical_decision(
    *,
    decision: str,
    decision_at: datetime,
    observations: Iterable[dict[str, Any]],
    horizon_seconds: int,
    fee_bps: float = 10,
    slippage_bps: float = 25,
    watch_band_pct: float = 3,
) -> dict[str, Any]:
    """Measure a decision using only observations visible after it was made.

    The first executable trade at or after ``decision_at`` is the simulated
    entry.  The final trade no later than the horizon is the exit.  A replay
    with fewer than two observations is explicitly inconclusive.
    """

    start = _utc(decision_at)
    end = start + timedelta(seconds=max(1, int(horizon_seconds)))
    eligible = []
    for item in observations:
        observed_at = item.get("observed_at")
        price = item.get("price")
        if not isinstance(observed_at, datetime) or not isinstance(price, (int, float)):
            continue
        timestamp = _utc(observed_at)
        if item.get("kind", "trade") != "trade" or timestamp < start or timestamp > end or price <= 0:
            continue
        eligible.append({**item, "observed_at": timestamp, "price": float(price)})
    eligible.sort(key=lambda item: (item["observed_at"], str(item.get("id") or "")))

    normalized = str(decision or "WATCH").upper()
    base = {
        "contract_version": "decision-evaluation.v1",
        "decision": normalized,
        "decision_at": start.isoformat(),
        "horizon_seconds": max(1, int(horizon_seconds)),
        "window_ends_at": end.isoformat(),
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "watch_band_pct": float(watch_band_pct),
        "observation_ids": [str(item.get("id") or "") for item in eligible],
        "anti_leakage": {
            "future_only": True,
            "entry_rule": "first executable trade at or after decision",
            "exit_rule": "last executable trade within horizon",
            "marks_excluded": True,
        },
    }
    if len(eligible) < 2:
        return {
            **base,
            "status": "inconclusive",
            "outcome": "insufficient_data",
            "reason": "At least two post-decision trade observations are required.",
            "entry_observation_id": eligible[0].get("id") if eligible else None,
            "exit_observation_id": None,
            "benchmark_return_pct": None,
            "strategy_return_pct": None,
            "max_favorable_excursion_pct": None,
            "max_adverse_excursion_pct": None,
        }

    entry, exit_ = eligible[0], eligible[-1]
    entry_mid = entry["price"]
    exit_mid = exit_["price"]
    benchmark = (exit_mid / entry_mid - 1) * 100
    path_returns = [(item["price"] / entry_mid - 1) * 100 for item in eligible]
    trade = open_paper_position(
        price=entry_mid, notional=1000, fee_bps=fee_bps, slippage_bps=slippage_bps
    )
    closed = close_paper_position(
        entry_price=trade["entry_price"], quantity=trade["quantity"], notional=1000,
        exit_price=exit_mid, entry_fee=trade["entry_fee"], fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
    if normalized == "ENTER":
        strategy_return = closed["return_pct"]
        outcome = "correct" if strategy_return > 0 else "incorrect" if strategy_return < 0 else "flat"
    elif normalized == "SKIP":
        strategy_return = 0.0
        outcome = "correct" if benchmark <= 0 else "incorrect"
    else:
        strategy_return = 0.0
        outcome = "correct" if abs(benchmark) <= max(0.0, watch_band_pct) else "incorrect"
    return {
        **base,
        "status": "complete",
        "outcome": outcome,
        "reason": "Measured from immutable post-decision trade observations.",
        "entry_observation_id": entry.get("id"),
        "exit_observation_id": exit_.get("id"),
        "entry_observed_at": entry["observed_at"].isoformat(),
        "exit_observed_at": exit_["observed_at"].isoformat(),
        "entry_mid_price": entry_mid,
        "exit_mid_price": exit_mid,
        "benchmark_return_pct": benchmark,
        "strategy_return_pct": strategy_return,
        "max_favorable_excursion_pct": max(path_returns),
        "max_adverse_excursion_pct": min(path_returns),
    }
