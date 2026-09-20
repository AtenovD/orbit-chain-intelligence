from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.protections import apply_decision_protections


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def signal(*, valid=True, evidence=None):
    return {"valid": valid, "stance": "support" if valid else "abstain", "evidence": evidence or []}


def test_enter_without_evidence_is_clamped_to_watch():
    result = apply_decision_protections(
        {"verdict": "ENTER", "confidence": 90, "evidence": [], "blocking_risks": []},
        signals=[signal()],
        now=NOW,
    )
    assert result["proposed_verdict"] == "ENTER"
    assert result["final_verdict"] == "WATCH"
    assert any(event["code"] == "insufficient_traceable_evidence" for event in result["events"])


def test_enter_requires_a_reference_not_just_a_provider_name():
    result = apply_decision_protections(
        {"verdict": "ENTER", "confidence": 90, "evidence": [], "blocking_risks": []},
        signals=[signal(evidence=[{"claim": "Liquidity is healthy", "source": "chain_rpc"}])],
        now=NOW,
    )
    assert result["final_verdict"] == "WATCH"
    assert result["evidence_quality"] == {"declared": 1, "traceable_unique": 0}
    assert {event["code"] for event in result["events"]} >= {
        "untraceable_evidence",
        "insufficient_traceable_evidence",
    }


def test_enter_allows_traceable_independent_evidence_and_respects_policy():
    result = apply_decision_protections(
        {"verdict": "ENTER", "confidence": 90, "evidence": [], "blocking_risks": []},
        signals=[
            signal(evidence=[
                {"claim": "Liquidity is healthy", "source": "chain_rpc", "reference": "block 123"},
                {"claim": "Volume confirms", "source": "dex_trades", "reference": "tx 0xabc"},
            ])
        ],
        context={"min_enter_evidence_refs": 2},
        now=NOW,
    )
    assert result["final_verdict"] == "ENTER"
    assert result["evidence_quality"] == {"declared": 2, "traceable_unique": 2}


def test_blocking_risk_clamps_enter_to_skip():
    result = apply_decision_protections(
        {"verdict": "ENTER", "confidence": 95, "blocking_risks": ["Owner can mint"]},
        signals=[signal(evidence=[{"claim": "mint", "source": "audit"}])],
        now=NOW,
    )
    assert result["final_verdict"] == "SKIP"
    assert result["status"] == "clamped"


def test_protection_never_promotes_a_conservative_decision():
    result = apply_decision_protections(
        {"verdict": "SKIP", "confidence": 5, "blocking_risks": []},
        signals=[signal(evidence=[{"claim": "safe", "source": "audit"}])],
        now=NOW,
    )
    assert result["final_verdict"] == "SKIP"


def test_execution_pause_is_a_hard_global_stop():
    result = apply_decision_protections(
        {"verdict": "ENTER", "confidence": 99, "blocking_risks": [], "evidence": ["verified"]},
        signals=[signal(evidence=[{"claim": "verified", "source": "rpc"}])],
        context={"execution_paused": True},
        now=NOW,
    )
    assert result["final_verdict"] == "SKIP"
    assert result["events"][0]["code"] == "execution_paused"
