from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.decision_contracts import (
    AGENT_SIGNAL_VERSION,
    DECISION_RECORD_VERSION,
    build_decision_record,
    parse_agent_signal,
)


def parse(content: str):
    return parse_agent_signal(
        content,
        run_id="run-1",
        task_id="task-1",
        agent_id="agent-1",
        agent_name="Priya",
        agent_role="On-Chain Scout",
        model="model-1",
        skill_name="On-Chain Researcher",
        subject="Assess token",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_valid_signal_is_hidden_from_visible_message_and_bound_to_runtime_identity():
    visible, signal = parse(
        "Liquidity is thin, so entry is premature.\n"
        '<orbit-signal>{"stance":"challenge","confidence":81,'
        '"thesis":"Liquidity is below the required threshold.",'
        '"evidence":[{"claim":"Pool reserve is 4 ETH","source":"chain_token_liquidity",'
        '"reference":"tool-call:7","as_of":"block 42"}],'
        '"assumptions":[],"unknowns":[],"blocking_risks":["Thin liquidity"],'
        '"invalidation_conditions":["Reserve exceeds 50 ETH"]}</orbit-signal>'
    )
    assert visible == "Liquidity is thin, so entry is premature."
    assert signal["contract_version"] == AGENT_SIGNAL_VERSION
    assert signal["valid"] is True
    assert signal["agent_id"] == "agent-1"
    assert signal["stance"] == "challenge"
    assert signal["evidence"][0]["reference"] == "tool-call:7"


def test_missing_or_invalid_signal_becomes_an_explicit_abstention():
    visible, missing = parse("Human-readable answer only.")
    assert visible == "Human-readable answer only."
    assert missing["valid"] is False
    assert missing["stance"] == "abstain"
    assert "missing_agent_signal_envelope" in missing["validation_errors"]

    _, invalid = parse(
        'Visible<orbit-signal>{"stance":"support","confidence":999,"thesis":"x"}</orbit-signal>'
    )
    assert invalid["valid"] is False
    assert invalid["stance"] == "abstain"


def test_decision_record_has_a_stable_summary():
    record = build_decision_record(
        run={"id": "run-1"},
        team={"id": "team-1"},
        agents=[{"id": "agent-1"}],
        tasks=[{"id": "task-1"}],
        signals=[{"valid": True, "stance": "support"}, {"valid": False, "stance": "abstain"}],
        tool_calls=[{"id": "tool-1"}],
        protections={"status": "warning", "events": [{"code": "test"}]},
        artifacts=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert record["contract_version"] == DECISION_RECORD_VERSION
    assert record["summary"] == {
        "agents": 1,
        "tasks": 1,
        "valid_signals": 1,
        "abstentions": 1,
        "tool_calls": 1,
        "traceable_evidence": 0,
        "protection_events": 1,
    }
