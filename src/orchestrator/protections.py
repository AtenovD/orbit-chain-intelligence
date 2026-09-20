"""Deterministic decision protections that an LLM cannot override."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_RANK = {"ENTER": 2, "WATCH": 1, "SKIP": 0}


def _traceable_evidence(signals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Return evidence that a human can actually trace back to a source.

    A natural-language claim and provider name alone are not audit evidence: a
    reader still cannot find the page, transaction, block, or tool call that
    supports it.  We keep such claims visible, but they do not unlock an ENTER
    decision.  This is deliberately format-agnostic so it works for ordinary
    web research, on-chain references, and internal tools.
    """

    traceable: list[dict[str, Any]] = []
    declared = 0
    seen: set[tuple[str, str]] = set()
    for signal in signals:
        for raw in signal.get("evidence") or []:
            if not isinstance(raw, dict):
                continue
            declared += 1
            source = str(raw.get("source") or "").strip()
            reference = str(raw.get("reference") or "").strip()
            if not source or not reference:
                continue
            key = (source.lower(), reference.lower())
            if key in seen:
                continue
            seen.add(key)
            traceable.append(raw)
    return traceable, declared


def _event(
    code: str,
    *,
    action: str,
    reason: str,
    before: str,
    after: str,
    severity: str = "warning",
) -> dict[str, Any]:
    return {
        "code": code,
        "scope": "decision",
        "action": action,
        "reason": reason,
        "before": before,
        "after": after,
        "severity": severity,
    }


def apply_decision_protections(
    verdict: dict[str, Any],
    *,
    signals: list[dict[str, Any]],
    failed_tasks: int = 0,
    context: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Only preserve or reduce a proposed decision; never make it more aggressive."""

    context = context or {}
    timestamp = now or datetime.now(timezone.utc)
    proposed = str(verdict.get("verdict") or "WATCH").upper()
    if proposed not in _RANK:
        proposed = "WATCH"
    current = proposed
    events: list[dict[str, Any]] = []

    def clamp(target: str, code: str, reason: str, severity: str = "warning") -> None:
        nonlocal current
        before = current
        # Risk is allowed to shrink a decision, never promote it.
        if _RANK[target] < _RANK[current]:
            current = target
            events.append(
                _event(code, action="clamp", reason=reason, before=before, after=current, severity=severity)
            )
        else:
            events.append(
                _event(code, action="warn", reason=reason, before=before, after=current, severity=severity)
            )

    if bool(context.get("execution_paused")):
        clamp("SKIP", "execution_paused", "Workspace execution is explicitly paused.", "critical")

    blocking = [str(item) for item in verdict.get("blocking_risks") or [] if str(item).strip()]
    if blocking:
        clamp("SKIP", "blocking_risk", f"The verdict declares {len(blocking)} blocking risk(s).", "critical")

    valid_signals = [item for item in signals if bool(item.get("valid"))]
    evidence, declared_evidence = _traceable_evidence(valid_signals)
    invalid_signals = len(signals) - len(valid_signals)
    if invalid_signals:
        events.append(
            _event(
                "invalid_agent_signals",
                action="warn",
                reason=f"{invalid_signals} contribution(s) did not satisfy AgentSignal v1.",
                before=current,
                after=current,
            )
        )

    if current == "ENTER" and failed_tasks:
        clamp("WATCH", "partial_run", f"{failed_tasks} task(s) failed; entry cannot be certified.")
    if current == "ENTER" and not valid_signals:
        clamp("WATCH", "no_valid_signals", "No agent supplied a valid structured signal.")
    min_traceable_evidence = max(1, min(20, int(context.get("min_enter_evidence_refs", 1))))
    if declared_evidence and len(evidence) < declared_evidence:
        events.append(
            _event(
                "untraceable_evidence",
                action="warn",
                reason=(
                    f"{declared_evidence - len(evidence)} declared evidence item(s) lack a source reference "
                    "and cannot be independently checked."
                ),
                before=current,
                after=current,
            )
        )
    if current == "ENTER" and len(evidence) < min_traceable_evidence:
        clamp(
            "WATCH",
            "insufficient_traceable_evidence",
            f"Entry requires {min_traceable_evidence} independently traceable evidence reference(s).",
        )

    confidence = verdict.get("confidence")
    threshold = max(0, min(100, int(context.get("min_enter_confidence", 65))))
    if current == "ENTER" and (not isinstance(confidence, (int, float)) or confidence < threshold):
        clamp("WATCH", "low_confidence", f"Entry requires confidence of at least {threshold}.")

    expired = 0
    for signal in valid_signals:
        expires_at = signal.get("expires_at")
        if not expires_at:
            continue
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            expired += expiry <= timestamp
        except ValueError:
            expired += 1
    if current == "ENTER" and expired:
        clamp("WATCH", "stale_signal", f"{expired} signal(s) are expired or have an invalid expiry.")

    return {
        "contract_version": "decision-protection.v1",
        "status": "clamped" if current != proposed else ("warning" if events else "passed"),
        "proposed_verdict": proposed,
        "final_verdict": current,
        "events": events,
        "evaluated_at": timestamp.isoformat(),
        "policy": {
            "min_enter_confidence": threshold,
            "min_enter_evidence_refs": min_traceable_evidence,
            "risk_can_only_reduce": True,
        },
        "evidence_quality": {
            "declared": declared_evidence,
            "traceable_unique": len(evidence),
        },
    }
