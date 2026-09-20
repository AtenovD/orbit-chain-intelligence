"""Versioned, machine-readable contracts for agent decisions.

The dialogue remains human-readable, but every visible contribution also carries a
hidden ``AgentSignal`` envelope.  The runtime removes the envelope before publishing
the message and persists it as its own JSON artifact.  Invalid or missing envelopes
are explicit abstentions; they are never upgraded into confident evidence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


SIGNAL_OPEN = "<orbit-signal>"
SIGNAL_CLOSE = "</orbit-signal>"
AGENT_SIGNAL_VERSION = "agent-signal.v1"
DECISION_RECORD_VERSION = "decision-record.v1"

AGENT_SIGNAL_INSTRUCTION = f"""
MACHINE-READABLE CONTRIBUTION CONTRACT
Write the concise human-facing answer first. End the response with exactly one
{SIGNAL_OPEN} JSON {SIGNAL_CLOSE} block. The block is hidden from the human and must use:
{{
  "stance": "support" | "challenge" | "neutral" | "abstain",
  "confidence": integer 0-100 or null,
  "thesis": "one concrete conclusion",
  "evidence": [{{"claim":"verified claim","source":"tool or document","reference":"URL, block, tx or tool-call id","as_of":"time or block"}}],
  "assumptions": ["unverified assumption"],
  "unknowns": ["missing fact"],
  "blocking_risks": ["risk that prevents the proposed action"],
  "invalidation_conditions": ["what would make the conclusion false"],
  "expires_at": "ISO-8601 time when this signal becomes stale, or null"
}}
Use ``abstain`` when evidence is insufficient. Never invent evidence, URLs, block
numbers, tool results, or confidence. Use empty arrays when a category has no items.
""".strip()


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=600)
    source: str = Field(min_length=1, max_length=240)
    reference: str = Field(default="", max_length=1000)
    as_of: str = Field(default="", max_length=160)

    @field_validator("claim", "source", "reference", "as_of", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()


class AgentSignalEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stance: Literal["support", "challenge", "neutral", "abstain"]
    confidence: int | None = Field(default=None, ge=0, le=100)
    thesis: str = Field(min_length=1, max_length=1600)
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    unknowns: list[str] = Field(default_factory=list, max_length=12)
    blocking_risks: list[str] = Field(default_factory=list, max_length=12)
    invalidation_conditions: list[str] = Field(default_factory=list, max_length=12)
    expires_at: str | None = Field(default=None, max_length=160)

    @field_validator("assumptions", "unknowns", "blocking_risks", "invalidation_conditions", mode="before")
    @classmethod
    def normalise_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("must be a list of strings")
        return [re.sub(r"\s+", " ", str(item)).strip()[:600] for item in value if str(item).strip()]

    @field_validator("thesis", mode="before")
    @classmethod
    def clean_thesis(cls, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @field_validator("expires_at", mode="before")
    @classmethod
    def clean_expiry(cls, value: Any) -> str | None:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        return cleaned or None


def _find_signal_block(content: str) -> tuple[str, str | None]:
    pattern = re.compile(
        rf"\s*{re.escape(SIGNAL_OPEN)}\s*(.*?)\s*{re.escape(SIGNAL_CLOSE)}\s*",
        flags=re.IGNORECASE | re.DOTALL,
    )
    matches = list(pattern.finditer(content or ""))
    if len(matches) != 1:
        return (content or "").strip(), None
    match = matches[0]
    visible = ((content or "")[: match.start()] + (content or "")[match.end() :]).strip()
    return visible, match.group(1).strip()


def parse_agent_signal(
    content: str,
    *,
    run_id: str,
    task_id: str,
    agent_id: str,
    agent_name: str,
    agent_role: str,
    model: str,
    skill_name: str | None,
    subject: str,
    created_at: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Remove and validate one signal envelope, returning an abstention on failure."""

    visible, raw = _find_signal_block(content)
    errors: list[str] = []
    parsed: AgentSignalEnvelope | None = None
    if raw is None:
        errors.append("missing_agent_signal_envelope")
    else:
        try:
            payload = json.loads(raw)
            parsed = AgentSignalEnvelope.model_validate(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid_json:{exc.msg}")
        except ValidationError as exc:
            errors.extend(
                f"invalid_{'.'.join(str(item) for item in error['loc'])}:{error['type']}"
                for error in exc.errors()[:8]
            )

    if parsed is None:
        parsed = AgentSignalEnvelope(
            stance="abstain",
            confidence=None,
            thesis="No valid structured signal was supplied.",
            evidence=[],
            assumptions=[],
            unknowns=["The agent contribution could not be validated as AgentSignal v1."],
            blocking_risks=[],
            invalidation_conditions=[],
            expires_at=None,
        )

    timestamp = created_at or datetime.now(timezone.utc)
    signal = {
        "contract_version": AGENT_SIGNAL_VERSION,
        "valid": not errors,
        "validation_errors": errors,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agent_role": agent_role,
        "model": model,
        "skill_name": skill_name,
        "subject": subject[:1000],
        "created_at": timestamp.isoformat(),
        **parsed.model_dump(mode="json"),
    }
    # Do not replace a malformed model reply with an empty chat bubble.
    if not visible:
        visible = parsed.thesis if not errors else (content or "").strip()
    return visible, signal


def build_decision_record(
    *,
    run: dict[str, Any],
    team: dict[str, Any],
    agents: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    protections: dict[str, Any] | None,
    artifacts: list[dict[str, Any]],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the immutable, serialisable receipt for one run revision."""

    traceable_evidence = {
        (str(reference.get("source") or "").strip().lower(), str(reference.get("reference") or "").strip().lower())
        for signal in signals
        if bool(signal.get("valid"))
        for reference in (signal.get("evidence") or [])
        if isinstance(reference, dict)
        and str(reference.get("source") or "").strip()
        and str(reference.get("reference") or "").strip()
    }
    return {
        "contract_version": DECISION_RECORD_VERSION,
        "created_at": (created_at or datetime.now(timezone.utc)).isoformat(),
        "run": run,
        "team": team,
        "agents": agents,
        "tasks": tasks,
        "signals": signals,
        "tool_calls": tool_calls,
        "protections": protections or {"status": "not_applicable", "events": []},
        "artifacts": artifacts,
        "summary": {
            "agents": len(agents),
            "tasks": len(tasks),
            "valid_signals": sum(bool(item.get("valid")) for item in signals),
            "abstentions": sum(item.get("stance") == "abstain" for item in signals),
            "tool_calls": len(tool_calls),
            "traceable_evidence": len(traceable_evidence),
            "protection_events": len((protections or {}).get("events", [])),
        },
    }
