"""Turning a crew's closing argument into a trading verdict.

The first version scraped the final text with regexes. That reads the first
ENTER/SKIP/WATCH token anywhere in the document, so "do not ENTER, this is a
SKIP" resolved to ENTER, and any dimension the text did not spell out became a
confident-looking 0/10. This module asks the model for a declared structure and
keeps the scrape only as a labelled fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any

DECISIONS = ("ENTER", "SKIP", "WATCH")
DIMENSIONS = ("research", "audit", "narrative", "timing")

_MAX_RATIONALE = 1200
_MAX_ITEM = 220
_MAX_ITEMS = 6

EXTRACTION_PROMPT = """You are closing a Robinhood Chain trading session. Read the crew's final
answer and restate it as JSON only — no prose, no code fences.

{
  "verdict": "ENTER" | "SKIP" | "WATCH",
  "confidence": integer 0-100,
  "rationale": "two or three sentences explaining the call",
  "scores": {"research": 0-10, "audit": 0-10, "narrative": 0-10, "timing": 0-10},
  "blocking_risks": ["concrete risk that would stop entry"],
  "conditions": ["what would have to change to revisit this"],
  "evidence": ["on-chain fact the crew actually verified"]
}

Rules:
- Use null for any score the crew did not actually assess. Never invent a number.
- blocking_risks, conditions and evidence must quote the crew's own findings; use
  an empty list rather than inventing entries.
- SKIP when a blocking risk stands. WATCH when the thesis is unproven rather than
  refuted. ENTER only when risks were checked and cleared.

FINAL ANSWER:
"""


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _score(value: Any) -> int | None:
    """Scores are 0-10; anything unusable stays unknown rather than becoming 0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, min(10, number))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = [_clean(item, _MAX_ITEM) for item in value]
    return [item for item in items if item][:_MAX_ITEMS]


def _json_payload(raw: str) -> dict[str, Any] | None:
    """Pull the JSON object out of a reply that may carry fences or prose."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    payload = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
                return payload if isinstance(payload, dict) else None
    return None


def parse_verdict(raw: str) -> dict[str, Any] | None:
    """Normalise a model's structured reply, or None when it is unusable."""
    payload = _json_payload(raw)
    if payload is None:
        return None
    decision = str(payload.get("verdict") or "").strip().upper()
    if decision not in DECISIONS:
        return None
    scores_raw = payload.get("scores")
    scores_raw = scores_raw if isinstance(scores_raw, dict) else {}
    confidence = _score(payload.get("confidence"))
    if confidence is not None:
        confidence = max(0, min(100, int(float(payload.get("confidence")))))
    return {
        "verdict": decision,
        "confidence": confidence,
        "rationale": _clean(payload.get("rationale"), _MAX_RATIONALE),
        "scores": {dimension: _score(scores_raw.get(dimension)) for dimension in DIMENSIONS},
        "blocking_risks": _string_list(payload.get("blocking_risks")),
        "conditions": _string_list(payload.get("conditions")),
        "evidence": _string_list(payload.get("evidence")),
        "extraction": "model",
    }


def heuristic_verdict(text: str) -> dict[str, Any]:
    """Last-resort scrape, used only when the structured pass fails.

    Reads the decision from the closing lines rather than the first match, so a
    passage arguing against entry is not mistaken for the call itself.
    """
    body = text or ""
    tail = "\n".join(body.strip().splitlines()[-12:]) or body
    decision = "WATCH"
    for candidate in re.finditer(r"\b(ENTER|SKIP|WATCH)\b", tail, re.IGNORECASE):
        prefix = tail[max(0, candidate.start() - 40) : candidate.start()].lower()
        if re.search(r"\b(not|never|avoid|don't|do not|не|нельзя)\s*$", prefix.strip() + " "):
            continue
        decision = candidate.group(1).upper()
    scores: dict[str, int | None] = {}
    for dimension, keys in (
        ("research", ("research", "ресёрч")),
        ("audit", ("audit", "аудит", "contract")),
        ("narrative", ("narrative", "нарратив", "sentiment")),
        ("timing", ("timing", "тайминг", "entry")),
    ):
        pattern = r"(?:" + "|".join(keys) + r")[^\d\n]{0,30}(\d{1,2})\s*/\s*10"
        found = re.search(pattern, body, re.IGNORECASE)
        scores[dimension] = _score(found.group(1)) if found else None
    risks = re.findall(r"(?:risk|риск|blocking|блокир)[^\n.]{0,30}:\s*([^\n.]{5,160})", body, re.IGNORECASE)
    return {
        "verdict": decision,
        "confidence": None,
        "rationale": _clean(body, _MAX_RATIONALE),
        "scores": scores,
        "blocking_risks": _string_list(risks),
        "conditions": [],
        "evidence": [],
        "extraction": "heuristic",
    }
