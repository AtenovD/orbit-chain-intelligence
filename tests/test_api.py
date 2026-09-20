import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from orchestrator import api as api_module
from orchestrator import runtime as runtime_module
from orchestrator.db import SessionFactory
from orchestrator.events import broker
from orchestrator.models import Approval, ApprovalStatus, Run, RunStatus
from orchestrator.providers import ProviderResult


def test_default_team_turn_is_a_sequential_roundtable():
    """A plain chat must hand each contribution to the next selected agent."""
    agents = [
        SimpleNamespace(id="captain", role="Coordinator"),
        SimpleNamespace(id="scout", role="Researcher"),
        SimpleNamespace(id="sentinel", role="Reviewer"),
    ]

    layers = runtime_module.RuntimeManager._workflow_layers(None, agents)

    assert [[node["agent_id"] for node in layer] for layer in layers] == [
        ["captain"],
        ["scout"],
        ["sentinel"],
    ]


async def bootstrap(client):
    workspace = (
        await client.post("/api/v1/workspaces", json={"name": "Demo Workspace"})
    ).json()
    agent_ids = []
    for slug, role in [("planner", "Planner"), ("reviewer", "Reviewer")]:
        response = await client.post(
            "/api/v1/agents",
            json={
                "workspace_id": workspace["id"],
                "name": role,
                "slug": slug,
                "role": role,
                "goal": f"Act as {role}",
                "system_prompt": f"You are the {role}.",
                "can_review": role == "Reviewer",
            },
        )
        assert response.status_code == 201, response.text
        agent_ids.append(response.json()["id"])
    team_response = await client.post(
        "/api/v1/teams",
        json={
            "workspace_id": workspace["id"],
            "name": "Product Team",
            "goal": "Prepare a launch plan",
            "agent_ids": agent_ids,
            "supervisor_agent_id": agent_ids[0],
        },
    )
    assert team_response.status_code == 201, team_response.text
    return workspace, agent_ids, team_response.json()


async def test_crud_and_mock_run(client):
    _, agent_ids, team = await bootstrap(client)
    response = await client.post(
        "/api/v1/runs",
        json={"team_id": team["id"], "mode": "constructive", "auto_start": True},
    )
    assert response.status_code == 201
    run_id = response.json()["id"]

    for _ in range(50):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)

    assert run["status"] == "completed"
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    # Runtime v2 keeps the two contributions and adds review/supervisor synthesis.
    assert len([event for event in events if event["type"] == "message.agent"]) >= 2
    assert any(event["type"] == "plan.created" for event in events)
    assert any("Check:" in event["payload"].get("content", "") for event in events)

    tasks = (await client.get(f"/api/v1/runs/{run_id}/tasks")).json()
    assert len(tasks) >= 2
    assert any("final synthesis" in task["title"] for task in tasks)
    assert {task["assigned_agent_id"] for task in tasks} == set(agent_ids)
    workspace_id = (await client.get("/api/v1/workspaces")).json()[0]["id"]
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace_id}")).json()
    assert {note["scope"] for note in memory} == {"global", "dialogue"}
    assert any("Verifiable results" in note["content"] for note in memory)


async def test_new_run_seeds_memory_in_requested_interface_language(client):
    workspace, _, team = await bootstrap(client)
    response = await client.post(
        "/api/v1/runs",
        json={
            "team_id": team["id"],
            "goal": "Assess an on-chain token",
            "context": {"language": "en"},
            "auto_start": False,
        },
    )
    assert response.status_code == 201, response.text
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    global_note = next(note for note in memory if note["scope"] == "global")
    dialogue_note = next(note for note in memory if note["scope"] == "dialogue")
    assert global_note["title"] == "Core memory"
    assert global_note["content"].startswith("# Core memory")
    assert dialogue_note["summary"] == "A compact record of this dialogue’s goals and decisions."
    assert dialogue_note["content"] == "# Dialogue\n\nGoal: Assess an on-chain token"


async def test_google_account_sign_in_and_capability_gating(client, monkeypatch):
    settings = api_module.get_settings()
    capabilities = (await client.get("/api/v1/auth/capabilities")).json()
    assert capabilities["auth"]["password"] is True
    assert capabilities["auth"]["google"] is False

    monkeypatch.setattr(settings, "google_auth_client_id", "google-auth-client")
    monkeypatch.setattr(settings, "google_auth_client_secret", "google-auth-secret")
    monkeypatch.setattr(settings, "public_url", "http://test")
    start = await client.get("/api/v1/auth/google/start")
    assert start.status_code == 200, start.text
    parsed = urlparse(start.json()["authorization_url"])
    query = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert query["scope"] == ["openid email profile"]

    async def fake_exchange(code):
        assert code == "google-code"
        return {
            "subject": "google-user-1",
            "email": "creator@example.com",
            "display_name": "Orbit Creator",
        }

    monkeypatch.setattr(api_module, "exchange_google_auth_code", fake_exchange)
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "google-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("?google_auth=success")
    assert "orbit_session=" in callback.headers["set-cookie"]
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "creator@example.com"
    assert (await client.get("/api/v1/auth/capabilities")).json()["auth"]["google"] is True


async def test_run_can_be_pinned_and_archived(client):
    _, _, team = await bootstrap(client)
    response = await client.post(
        "/api/v1/runs",
        json={"team_id": team["id"], "goal": "Keep this dialogue", "auto_start": False},
    )
    assert response.status_code == 201
    run_id = response.json()["id"]
    updated = await client.patch(
        f"/api/v1/runs/{run_id}/meta",
        json={"pinned": True, "archived": True},
    )
    assert updated.status_code == 200
    assert updated.json()["context"]["pinned"] is True
    assert updated.json()["context"]["archived"] is True
    restored = await client.patch(
        f"/api/v1/runs/{run_id}/meta",
        json={"archived": False},
    )
    assert restored.json()["context"]["pinned"] is True
    assert restored.json()["context"]["archived"] is False


async def test_workspace_token_registry_watchlist_and_verdict_history(client):
    workspace, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/tokens",
        json={
            "workspace_id": workspace["id"],
            "address": "  0xAbCdEfAbCdEfAbCdEfAbCdEfAbCdEfAbCdEfAbCd  ",
            "label": "  Core position  ",
            "symbol": " ORB ",
        },
    )
    assert created.status_code == 201, created.text
    token = created.json()
    assert token["address"] == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    assert token["chain_id"] == 4663
    assert token["asset_kind"] == "token"
    assert token["label"] == "Core position"
    assert token["symbol"] == "ORB"
    assert token["watchlist"] is False

    duplicate = await client.post(
        "/api/v1/tokens",
        json={"workspace_id": workspace["id"], "address": "0xABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCD"},
    )
    assert duplicate.status_code == 409
    watched = await client.post(
        "/api/v1/tokens",
        json={
            "workspace_id": workspace["id"], "address": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            "chain_id": 1, "asset_kind": "nft", "watchlist": True, "name": "Orbit on mainnet",
        },
    )
    assert watched.status_code == 201, watched.text
    watched_token = watched.json()
    assert [item["id"] for item in (await client.get(
        f"/api/v1/tokens?workspace_id={workspace['id']}&watchlist=true"
    )).json()] == [watched_token["id"]]
    assert watched_token["asset_kind"] == "nft"

    updated = await client.patch(
        f"/api/v1/tokens/{token['id']}",
        json={"address": "0x1234567890abcdef1234567890abcdef12345678", "asset_kind": "nft", "watchlist": True, "label": ""},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["address"] == "0x1234567890abcdef1234567890abcdef12345678"
    assert updated.json()["label"] is None
    assert updated.json()["watchlist"] is True
    assert updated.json()["asset_kind"] == "nft"

    run = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": False})
    artifact = await client.post(
        f"/api/v1/runs/{run.json()['id']}/artifacts",
        json={"name": "Token thesis", "kind": "verdict", "metadata": {"score": 82}},
    )
    verdict = await client.post(
        f"/api/v1/tokens/{token['id']}/verdicts",
        json={
            "verdict": "accumulate",
            "payload": {"score": 82, "risk": "medium"},
            "run_id": run.json()["id"],
            "artifact_id": artifact.json()["id"],
        },
    )
    assert verdict.status_code == 201, verdict.text
    history = (await client.get(f"/api/v1/tokens/{token['id']}/verdicts")).json()
    assert len(history) == 1
    assert history[0]["verdict"] == "accumulate"
    assert history[0]["payload"]["score"] == 82
    assert history[0]["run_id"] == run.json()["id"]

    assert (await client.delete(f"/api/v1/tokens/{token['id']}")).status_code == 204
    assert (await client.get(f"/api/v1/tokens/{token['id']}")).status_code == 404


async def test_decision_replay_and_paper_trade_ledger(client):
    workspace, _, _ = await bootstrap(client)
    token_response = await client.post(
        "/api/v1/tokens",
        json={
            "workspace_id": workspace["id"],
            "address": "0x1111111111111111111111111111111111111111",
            "symbol": "TEST",
        },
    )
    token = token_response.json()
    verdict_response = await client.post(
        f"/api/v1/tokens/{token['id']}/verdicts",
        json={
            "verdict": "ENTER",
            "payload": {
                "confidence": 88,
                "protections": {"status": "passed", "final_verdict": "ENTER"},
            },
        },
    )
    assert verdict_response.status_code == 201, verdict_response.text
    verdict = verdict_response.json()
    decision_at = datetime.fromisoformat(verdict["created_at"].replace("Z", "+00:00"))

    paper = await client.post(
        f"/api/v1/tokens/{token['id']}/paper-trades",
        json={"verdict_id": verdict["id"], "notional": 1000, "fee_bps": 10, "slippage_bps": 25},
    )
    assert paper.status_code == 201, paper.text
    assert paper.json()["status"] == "pending"

    first_at = decision_at + timedelta(minutes=1)
    first = await client.post(
        f"/api/v1/tokens/{token['id']}/market-observations",
        json={
            "price": 10,
            "quote_symbol": "USDC",
            "kind": "trade",
            "source": "test-feed",
            "source_ref": "trade-1",
            "observed_at": first_at.isoformat(),
        },
    )
    assert first.status_code == 201, first.text
    trades = (await client.get(f"/api/v1/tokens/{token['id']}/paper-trades")).json()
    assert trades[0]["status"] == "open"
    assert trades[0]["entry_observation_id"] == first.json()["id"]
    assert trades[0]["entry_price"] > 10

    second_at = decision_at + timedelta(hours=1)
    second = await client.post(
        f"/api/v1/tokens/{token['id']}/market-observations",
        json={
            "price": 12,
            "quote_symbol": "USDC",
            "kind": "trade",
            "source": "test-feed",
            "source_ref": "trade-2",
            "observed_at": second_at.isoformat(),
        },
    )
    assert second.status_code == 201, second.text
    closed = await client.post(
        f"/api/v1/paper-trades/{paper.json()['id']}/close",
        json={"exit_observation_id": second.json()["id"], "close_reason": "test horizon"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["realized_pnl"] > 0
    assert closed.json()["fees_paid"] > 0

    evaluation = await client.post(
        f"/api/v1/tokens/{token['id']}/evaluations",
        json={
            "verdict_id": verdict["id"],
            "horizon_seconds": 7200,
            "fee_bps": 10,
            "slippage_bps": 25,
            "source": "test-feed",
        },
    )
    assert evaluation.status_code == 201, evaluation.text
    assert evaluation.json()["status"] == "complete"
    assert evaluation.json()["outcome"] == "correct"
    assert evaluation.json()["strategy_return_pct"] > 0
    assert evaluation.json()["payload"]["anti_leakage"]["future_only"] is True


async def test_trading_run_creates_a_linked_dry_run_ledger_record(client):
    workspace, agent_ids, team = await bootstrap(client)
    await client.patch(
        f"/api/v1/agents/{agent_ids[0]}",
        json={"skill_name": "On-Chain Researcher"},
    )
    token = (
        await client.post(
            "/api/v1/tokens",
            json={
                "workspace_id": workspace["id"],
                "address": "0x2222222222222222222222222222222222222222",
                "symbol": "AUTO",
            },
        )
    ).json()
    run = await client.post(
        "/api/v1/runs",
        json={
            "team_id": team["id"],
            "goal": "Assess this token and return a bounded trading decision.",
            "context": {"token_id": token["id"], "paper_trading": True},
            "auto_start": True,
        },
    )
    assert run.status_code == 201, run.text
    for _ in range(100):
        status = (await client.get(f"/api/v1/runs/{run.json()['id']}")).json()["status"]
        if status in {"completed", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert status == "completed"
    verdicts = (await client.get(f"/api/v1/tokens/{token['id']}/verdicts")).json()
    trades = (await client.get(f"/api/v1/tokens/{token['id']}/paper-trades")).json()
    assert len(verdicts) == 1
    assert len(trades) == 1
    assert trades[0]["verdict_id"] == verdicts[0]["id"]
    assert trades[0]["config"]["real_funds"] is False
    verdict_at = datetime.fromisoformat(verdicts[0]["created_at"].replace("Z", "+00:00"))
    for index, price in enumerate((10, 11), start=1):
        observation = await client.post(
            f"/api/v1/tokens/{token['id']}/market-observations",
            json={
                "price": price,
                "quote_symbol": "USDC",
                "kind": "trade",
                "source": "runtime-score-test",
                "source_ref": f"runtime-{index}",
                "observed_at": (verdict_at + timedelta(minutes=index)).isoformat(),
            },
        )
        assert observation.status_code == 201, observation.text
    measured = await client.post(
        f"/api/v1/tokens/{token['id']}/evaluations",
        json={"verdict_id": verdicts[0]["id"], "horizon_seconds": 3600, "source": "runtime-score-test"},
    )
    assert measured.status_code == 201, measured.text
    quality = await client.get(f"/api/v1/workspaces/{workspace['id']}/decision-quality")
    assert quality.status_code == 200, quality.text
    assert quality.json()["resolved_decisions"] == 1
    assert quality.json()["scorecards"]
    assert quality.json()["scorecards"][0]["signals"] >= 1


async def test_deleting_dialogue_removes_linked_memory(client):
    workspace, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs",
        json={"team_id": team["id"], "goal": "Temporary dialogue", "auto_start": True},
    )
    run_id = created.json()["id"]
    for _ in range(80):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    before = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    assert any(note["run_id"] == run_id for note in before)

    deleted = await client.delete(f"/api/v1/runs/{run_id}")
    assert deleted.status_code == 204
    after = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    assert all(note["run_id"] != run_id for note in after)
    assert (await client.get(f"/api/v1/runs/{run_id}")).status_code == 404


async def test_completed_run_accepts_follow_up_and_restarts_team(client):
    _, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "auto_start": True}
    )
    run_id = created.json()["id"]
    for _ in range(80):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    follow_up = await client.post(
        f"/api/v1/runs/{run_id}/messages",
        json={"content": "Continue with a better version", "recipients": ["all"]},
    )
    assert follow_up.status_code == 201, follow_up.text
    assert follow_up.json()["type"] == "message.human"
    initial_agent_messages = len(
        [event for event in (await client.get(f"/api/v1/runs/{run_id}/events")).json() if event["type"] == "message.agent"]
    )
    for _ in range(80):
        events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if (
            len([event for event in events if event["type"] == "run.completed"]) >= 2
            and len([event for event in events if event["type"] == "message.agent"]) > initial_agent_messages
        ):
            break
        await asyncio.sleep(0.02)
    assert len([event for event in events if event["type"] == "run.completed"]) == 2
    assert any(event["type"] == "run.resumed" for event in events)
    # Standard chat is coordinated internally: the hidden supervisor plan is
    # not rendered as a user-facing answer. The specialist contributes once
    # and the supervisor publishes one shared synthesis.
    assert len([event for event in events if event["type"] == "message.agent"]) - initial_agent_messages == 2
    assert any(
        event["type"] == "message.internal" and event["visibility"] == "internal"
        for event in events
    )
    assert run["plan_revision"] == 1


async def test_declared_turn_plan_can_skip_unneeded_specialists(client, monkeypatch):
    _, agent_ids, team = await bootstrap(client)

    class PlanningProvider:
        async def complete(self, *, agent, goal, mode, messages):
            assignment = "\n".join(
                str(item.get("content", "")) for item in messages if item.get("role") == "system"
            )
            if "hidden turn planner" in assignment:
                content = json.dumps({"summary": "Direct answer", "tasks": []})
            elif "final answer" in assignment.lower():
                content = "One concise answer from the lead."
            else:
                content = f"Unexpected specialist call: {agent.name}"
            return ProviderResult(content=content, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(runtime_module, "provider_for", lambda _connection: PlanningProvider())
    created = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": True})
    run_id = created.json()["id"]
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)

    assert run["status"] == "completed"
    tasks = (await client.get(f"/api/v1/runs/{run_id}/tasks")).json()
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert not any(task["assigned_agent_id"] == agent_ids[1] for task in tasks)
    assert any(event["type"] == "turn.plan.created" and event["payload"]["tasks"] == [] for event in events)
    visible = [event for event in events if event["type"] == "message.agent"]
    assert [event["actor_id"] for event in visible] == [agent_ids[0]]


async def test_agent_mention_creates_and_closes_executable_handoff(client, monkeypatch):
    _, agent_ids, team = await bootstrap(client)
    agents = (await client.get(f"/api/v1/agents?workspace_id={team['workspace_id']}")).json()
    by_id = {agent["id"]: agent for agent in agents}
    planner_slug = by_id[agent_ids[0]]["slug"]
    specialist_slug = by_id[agent_ids[1]]["slug"]

    class HandoffProvider:
        async def complete(self, *, agent, goal, mode, messages):
            assignment = "\n".join(
                str(item.get("content", "")) for item in messages if item.get("role") == "system"
            )
            if "hidden turn planner" in assignment:
                content = json.dumps(
                    {
                        "summary": "Check one specialist finding",
                        "tasks": [
                            {
                                "agent_slug": specialist_slug,
                                "instruction": "Inspect the launch risk",
                                "acceptance_criteria": ["Name one material risk"],
                                "depends_on": [],
                            }
                        ],
                    }
                )
            elif "sent you this concrete handoff" in assignment:
                content = "The requested decision is WATCH until liquidity is verified."
            elif agent.id == agent_ids[1]:
                content = f"@{planner_slug} decide whether missing liquidity blocks launch."
            else:
                content = "Final decision: WATCH pending liquidity evidence."
            return ProviderResult(content=content, input_tokens=1, output_tokens=1)

    monkeypatch.setattr(runtime_module, "provider_for", lambda _connection: HandoffProvider())
    created = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": True})
    run_id = created.json()["id"]
    for _ in range(120):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)

    assert run["status"] == "completed"
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert any(event["type"] == "handoff.created" for event in events)
    assert any(event["type"] == "handoff.accepted" for event in events)
    assert any(event["type"] == "handoff.answered" for event in events)
    handoff_tasks = [
        task for task in (await client.get(f"/api/v1/runs/{run_id}/tasks")).json()
        if task["title"].startswith("Handoff from")
    ]
    assert len(handoff_tasks) == 1
    assert handoff_tasks[0]["assigned_agent_id"] == agent_ids[0]


async def test_workflow_tool_arguments_can_map_upstream_node_output(client):
    _, _, team = await bootstrap(client)
    created = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": False})
    run_id = created.json()["id"]
    async with SessionFactory() as session:
        await broker.publish(
            session,
            run_id=run_id,
            event_type="workflow.node.output",
            actor_type="agent",
            payload={
                "node_id": "research",
                "kind": "agent",
                "output": {"token": {"address": "0xabc"}, "chain": "robinhood"},
            },
            visibility="internal",
        )

    arguments = await runtime_module.runtime._resolve_tool_arguments(
        run_id,
        {
            "arguments": {"limit": 25},
            "input_mapping": {
                "address": "$nodes.research.output.token.address",
                "chain": {"node_id": "research", "path": "output.chain"},
            },
        },
    )
    assert arguments == {"limit": 25, "address": "0xabc", "chain": "robinhood"}


async def test_failed_run_accepts_a_recovery_turn_and_cancels_stale_approval(client):
    _, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "auto_start": False}
    )
    run_id = created.json()["id"]
    async with SessionFactory() as session:
        run = await session.get(Run, run_id)
        run.status = RunStatus.failed
        run.current_stage = "failed"
        session.add(
            Approval(
                run_id=run_id,
                action="workflow:approval",
                description="Old decision",
                status=ApprovalStatus.pending,
            )
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/runs/{run_id}/messages",
        json={
            "content": "Retry with this correction",
            "recipients": ["all"],
            "client_message_id": "recovery-message-1",
        },
    )
    assert response.status_code == 201, response.text
    reopened = (await client.get(f"/api/v1/runs/{run_id}")).json()
    approvals = (await client.get(f"/api/v1/runs/{run_id}/approvals")).json()
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert reopened["status"] in {"running", "completed"}
    assert reopened["plan_revision"] == 1
    assert approvals[0]["status"] == "cancelled"
    assert any(event["type"] == "run.resumed" for event in events)
    assert any(event["type"] == "approval.cancelled" for event in events)


async def test_human_message_idempotency_key_prevents_duplicate_turns(client):
    _, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "auto_start": False}
    )
    run_id = created.json()["id"]
    payload = {
        "content": "One message only",
        "recipients": ["all"],
        "client_message_id": "stable-browser-message-1",
    }
    first = await client.post(f"/api/v1/runs/{run_id}/messages", json=payload)
    second = await client.post(f"/api/v1/runs/{run_id}/messages", json=payload)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert len([event for event in events if event["type"] == "message.human"]) == 1


async def test_approval_decision_wakes_waiting_workflow(client):
    workspace, agent_ids, team = await bootstrap(client)
    workflow = (
        await client.post(
            "/api/v1/workflows",
            json={
                "workspace_id": workspace["id"],
                "team_id": team["id"],
                "name": "Approval gate",
                "nodes": [
                    {"id": "start", "type": "start"},
                    {"id": "approval", "type": "approval", "label": "Approve work"},
                    {"id": "agent", "type": "agent", "agent_id": agent_ids[0]},
                    {"id": "reviewer", "type": "agent", "agent_id": agent_ids[1]},
                    {"id": "final", "type": "final"},
                ],
                "edges": [
                    {"id": "e1", "source": "start", "target": "approval"},
                    {"id": "e2", "source": "approval", "target": "agent"},
                    {"id": "e3", "source": "agent", "target": "reviewer"},
                    {"id": "e4", "source": "reviewer", "target": "final"},
                ],
            },
        )
    ).json()
    created = await client.post(
        "/api/v1/runs",
        json={"team_id": team["id"], "workflow_id": workflow["id"], "auto_start": True},
    )
    run_id = created.json()["id"]
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        approvals = (await client.get(f"/api/v1/runs/{run_id}/approvals")).json()
        if run["status"] == "waiting_for_human" and approvals:
            break
        await asyncio.sleep(0.02)
    assert run["current_stage"] == "waiting_for_approval"

    decided = await client.post(
        f"/api/v1/approvals/{approvals[0]['id']}/decision",
        json={"decision": "approved"},
    )
    assert decided.status_code == 200, decided.text
    for _ in range(150):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    assert run["status"] == "completed"
    assert run["current_stage"] == "completed"


async def test_completed_run_direct_mention_only_executes_target_agent(client):
    _, agent_ids, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "auto_start": True}
    )
    run_id = created.json()["id"]
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    before = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    last_sequence = max(event["sequence"] for event in before)

    response = await client.post(
        f"/api/v1/runs/{run_id}/messages",
        json={"content": "Only you answer", "recipients": [agent_ids[1]], "command": "instruction"},
    )
    assert response.status_code == 201, response.text
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
        if run["status"] == "completed" and any(
            event["sequence"] > last_sequence and event["type"] == "message.agent"
            for event in events
        ):
            break
        await asyncio.sleep(0.02)

    replies = [
        event for event in events
        if event["sequence"] > last_sequence and event["type"] == "message.agent"
    ]
    plans = [event for event in events if event["sequence"] > last_sequence and event["type"] == "plan.created"]
    assert plans[-1]["payload"]["targeted_agent_ids"] == [agent_ids[1]]
    assert [event["actor_id"] for event in replies] == [agent_ids[1]]
    assert "turn_recipients" not in run["context"]


async def test_active_redirect_creates_a_fresh_answering_revision(client, monkeypatch):
    """An in-flight provider call must not let a redirect complete silently."""
    started = asyncio.Event()
    release = asyncio.Event()

    class DelayedProvider:
        async def complete(self, *, agent, goal, mode, messages):
            started.set()
            await release.wait()
            return ProviderResult(
                content=f"{agent.name} saw goal: {goal}", input_tokens=1, output_tokens=1,
            )

    monkeypatch.setattr(runtime_module, "provider_for", lambda _connection: DelayedProvider())
    _, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "goal": "Old objective", "auto_start": True}
    )
    run_id = created.json()["id"]
    await asyncio.wait_for(started.wait(), timeout=1)

    redirected = await client.post(
        f"/api/v1/runs/{run_id}/messages",
        json={"content": "New objective", "recipients": ["all"], "command": "redirect"},
    )
    assert redirected.status_code == 201, redirected.text
    assert (await client.get(f"/api/v1/runs/{run_id}")).json()["plan_revision"] == 1
    release.set()

    for _ in range(150):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    assert run["status"] == "completed"
    assert run["goal"] == "New objective"
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    human = next(event for event in events if event["type"] == "message.human")
    assert any(event["type"] == "plan.revised" for event in events)
    assert any(
        event["type"] == "message.agent"
        and event["sequence"] > human["sequence"]
        and "New objective" in event["payload"]["content"]
        for event in events
    )


async def test_request_review_runs_reviewer_and_synthesis_for_standard_turn(client):
    _, _, team = await bootstrap(client)
    created = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": False})
    run_id = created.json()["id"]
    review = await client.post(
        f"/api/v1/runs/{run_id}/messages",
        json={"content": "Review the proposed approach", "recipients": ["all"], "command": "request_review"},
    )
    assert review.status_code == 201, review.text
    for _ in range(150):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    assert run["status"] == "completed"
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    tasks = (await client.get(f"/api/v1/runs/{run_id}/tasks")).json()
    assert any(event["type"] == "review.requested" for event in events)
    assert any("independent review" in task["title"] for task in tasks)
    assert any("final synthesis" in task["title"] for task in tasks)


async def test_provider_task_failure_marks_run_failed_not_completed(client, monkeypatch):
    class FailingProvider:
        async def complete(self, **_kwargs):
            raise ValueError("provider unavailable")

    monkeypatch.setattr(runtime_module, "provider_for", lambda _connection: FailingProvider())
    _, _, team = await bootstrap(client)
    created = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": True})
    run_id = created.json()["id"]
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "failed":
            break
        await asyncio.sleep(0.02)
    assert run["status"] == "failed"
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert any(event["type"] == "task.failed" for event in events)
    assert not any(event["type"] == "run.completed" for event in events)


async def test_selected_agent_missing_from_saved_workflow_still_runs(client):
    workspace, agent_ids, team = await bootstrap(client)
    workflow = (
        await client.post(
            "/api/v1/workflows",
            json={
                "workspace_id": workspace["id"],
                "team_id": team["id"],
                "name": "Old fixed team",
                "nodes": [
                    {"id": "start", "type": "start", "label": "Start"},
                    {"id": "planner", "type": "agent", "label": "Planner", "agent_id": agent_ids[0]},
                ],
                "edges": [{"source": "start", "target": "planner"}],
            },
        )
    ).json()
    created = await client.post(
        "/api/v1/runs",
        json={
            "team_id": team["id"],
            "workflow_id": workflow["id"],
            "goal": "Talk to the selected reviewer",
            "context": {"agent_ids": [agent_ids[1]]},
            "auto_start": True,
        },
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    tasks = (await client.get(f"/api/v1/runs/{run_id}/tasks")).json()
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    assert tasks
    assert {task["assigned_agent_id"] for task in tasks} == {agent_ids[1]}
    assert any(event["type"] == "message.agent" and event["actor_id"] == agent_ids[1] for event in events)


async def test_run_safeguards_can_be_configured_and_extended(client):
    _, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs",
        json={
            "team_id": team["id"],
            "auto_start": False,
            "context": {"budget_tokens": 10_000, "budget_cost_micros": 500_000, "max_rounds": 4},
        },
    )
    assert created.status_code == 201
    updated = await client.patch(
        f"/api/v1/runs/{created.json()['id']}/budget",
        json={"token_limit": 35_000, "cost_limit_micros": 1_500_000, "max_rounds": 9},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["context"]["budget_tokens"] == 35_000
    assert updated.json()["context"]["budget_cost_micros"] == 1_500_000
    assert updated.json()["context"]["max_rounds"] == 9


async def test_dialogue_can_fork_and_user_can_speak_as_agent(client):
    _, agent_ids, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "goal": "Test a branching decision", "auto_start": True}
    )
    run_id = created.json()["id"]
    for _ in range(80):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    point = next(event for event in events if event["type"] == "message.agent")

    branch = await client.post(
        f"/api/v1/runs/{run_id}/branch",
        json={"event_id": point["id"], "instruction": "Use a more conservative assumption.", "kind": "fork"},
    )
    assert branch.status_code == 201, branch.text
    assert branch.json()["context"]["parent_run_id"] == run_id
    assert branch.json()["context"]["branch_point_event_id"] == point["id"]
    branch_events = (await client.get(f"/api/v1/runs/{branch.json()['id']}/events")).json()
    assert any(event["payload"].get("replayed_from_event_id") == point["id"] for event in branch_events)
    assert any(event["payload"].get("branch_instruction") is True for event in branch_events)

    impersonated = await client.post(
        f"/api/v1/runs/{run_id}/impersonate",
        json={"agent_id": agent_ids[1], "content": "I want the team to stress-test the fallback."},
    )
    assert impersonated.status_code == 201, impersonated.text
    assert impersonated.json()["actor_id"] == agent_ids[1]
    assert impersonated.json()["payload"]["impersonated_by_user"] is True
    for _ in range(80):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    assert run["status"] == "completed"


async def test_public_replay_contains_team_process_and_artifacts(client):
    _, _, team = await bootstrap(client)
    created = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "mode": "constructive", "auto_start": True}
    )
    run_id = created.json()["id"]
    for _ in range(80):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    shared = await client.post(f"/api/v1/runs/{run_id}/share")
    assert shared.status_code == 200, shared.text
    replay = await client.get(f"/api/v1/public/replays/{shared.json()['token']}")
    assert replay.status_code == 200, replay.text
    payload = replay.json()
    assert payload["run"]["id"] == run_id
    assert len(payload["agents"]) == 2
    assert any(event["type"] == "message.agent" for event in payload["events"])
    assert any(artifact["kind"] == "working_document" for artifact in payload["artifacts"])
    assert any(artifact["kind"] == "verdict" for artifact in payload["artifacts"])
    signals = [artifact for artifact in payload["artifacts"] if artifact["kind"] == "agent_signal"]
    assert signals
    assert all(signal["metadata"]["contract_version"] == "agent-signal.v1" for signal in signals)
    assert all(signal["metadata"]["valid"] is True for signal in signals)
    assert any(artifact["kind"] == "decision_record" for artifact in payload["artifacts"])
    target = await client.post("/api/v1/workspaces", json={"name": "Replay target"})
    forked = await client.post(
        f"/api/v1/replays/{shared.json()['token']}/fork",
        json={"workspace_id": target.json()["id"]},
    )
    assert forked.status_code == 201, forked.text
    fork_payload = forked.json()
    assert fork_payload["goal"] == run["goal"]
    assert len(fork_payload["agents"]) == 2
    assert fork_payload["team"]["agent_ids"] == [agent["id"] for agent in fork_payload["agents"]]
    assert all(agent["workspace_id"] == target.json()["id"] for agent in fork_payload["agents"])
    assert all(agent["connection_id"] is None and agent["model"] == "mock-model" for agent in fork_payload["agents"])


async def test_agent_has_one_global_skill_and_uses_it(client):
    _, agent_ids, team = await bootstrap(client)
    updated = await client.patch(
        f"/api/v1/agents/{agent_ids[0]}",
        json={
            "skill_name": "Critical Thinking",
            "skill_description": "Tests assumptions",
            "skill_prompt": "Challenge weak assumptions and offer alternatives.",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["skill_name"] == "Critical Thinking"

    run_response = await client.post(
        "/api/v1/runs", json={"team_id": team["id"], "auto_start": True}
    )
    run_id = run_response.json()["id"]
    for _ in range(50):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    events = (await client.get(f"/api/v1/runs/{run_id}/events")).json()
    planner_message = next(
        event
        for event in events
        if event["type"] == "message.agent" and event["actor_id"] == agent_ids[0]
    )
    assert planner_message["payload"]["metadata"]["active_skill"] == "Critical Thinking"
    assert "Active skill" not in planner_message["payload"]["content"]
    evolved = (await client.get(f"/api/v1/agents/{agent_ids[0]}")).json()
    assert evolved["lessons_count"] == 1
    assert "Verified lesson" in evolved["professional_memory"]
    assert "Source: task:" in evolved["professional_memory"]


async def test_dialogue_material_is_stored_in_run_context(client):
    _, _, team = await bootstrap(client)
    run = (
        await client.post(
            "/api/v1/runs",
            json={
                "team_id": team["id"],
                "auto_start": False,
                "context": {
                    "materials": [
                        {"name": "brief.md", "content": "Audience prefers practical examples.", "kind": "markdown"}
                    ]
                },
            },
        )
    ).json()
    assert run["context"]["materials"][0]["name"] == "brief.md"
    updated = await client.post(
        f"/api/v1/runs/{run['id']}/materials",
        json={"name": "metrics.csv", "content": "views,likes\n100,20", "kind": "text"},
    )
    assert updated.status_code == 200, updated.text
    assert len(updated.json()["context"]["materials"]) == 2


async def test_github_connector_syncs_profile_into_global_memory(client, monkeypatch):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "GitHub"})).json()
    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "github_oauth_client_id", "github-client")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "github-secret")
    monkeypatch.setattr(settings, "public_url", "http://test")

    async def fake_context(token):
        assert token == "github-token"
        return {
            "profile": {
                "login": "octocat",
                "name": "The Octocat",
                "bio": "Builds useful things",
                "company": "GitHub",
                "public_repos": 2,
                "followers": 100,
                "url": "https://github.com/octocat",
            },
            "repositories": [
                {
                    "name": "octocat/hello-world",
                    "description": "A demo",
                    "language": "Python",
                    "stars": 42,
                    "forks": 3,
                    "private": False,
                    "updated_at": "2026-01-01T00:00:00Z",
                    "url": "https://github.com/octocat/hello-world",
                    "topics": ["agents"],
                }
            ],
            "repository_count": 1,
        }

    monkeypatch.setattr(api_module, "fetch_github_context", fake_context)
    async def fake_exchange(code):
        assert code == "github-code"
        return {"access_token": "github-token", "scope": "read:user,repo", "token_type": "bearer"}

    monkeypatch.setattr(api_module, "exchange_github_code", fake_exchange)
    start = await client.get(
        "/api/v1/integrations/github/oauth/start",
        params={"workspace_id": workspace["id"]},
    )
    assert start.status_code == 200, start.text
    parsed = urlparse(start.json()["authorization_url"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://github.com/login/oauth/authorize"
    assert set(query["scope"][0].split()) == {"read:user", "repo"}
    response = await client.get(
        "/api/v1/integrations/github/oauth/callback",
        params={"code": "github-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    assert response.headers["location"].endswith("?screen=connections&github_oauth=success")
    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    assert connections[0]["config"]["auth_method"] == "oauth2"
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    assert "octocat/hello-world" in memory[0]["content"]


async def test_twitter_connector_validates_account_and_indexes_content(client, monkeypatch):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Creator"})).json()

    async def fake_context(token):
        assert token == "x-user-token"
        return {
            "profile": {
                "id": "42",
                "username": "orbit_creator",
                "name": "Orbit Creator",
                "description": "Building agent teams",
                "location": "Kyiv",
                "url": "https://x.com/orbit_creator",
                "profile_image_url": None,
                "verified": False,
                "protected": False,
                "created_at": "2024-01-01T00:00:00Z",
                "public_metrics": {"followers_count": 1250, "following_count": 120, "tweet_count": 88},
            },
            "posts": [
                {
                    "id": "100",
                    "text": "Agent orchestration should feel like a real team.",
                    "created_at": "2026-07-31T12:00:00Z",
                    "lang": "en",
                    "public_metrics": {"like_count": 90, "retweet_count": 12, "reply_count": 8, "quote_count": 2},
                }
            ],
            "timeline_warning": None,
        }

    monkeypatch.setattr(api_module, "fetch_twitter_context", fake_context)
    response = await client.post(
        "/api/v1/integrations/twitter/connect",
        json={"workspace_id": workspace["id"], "token": "x-user-token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "orbit_creator"
    assert response.json()["posts_count"] == 1
    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    assert connections[0]["provider"] == "twitter"
    assert connections[0]["config"]["profile"]["public_metrics"]["followers_count"] == 1250
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    assert "Agent orchestration should feel like a real team" in memory[0]["content"]


async def test_twitter_oauth_pkce_redirect_and_callback(client, monkeypatch):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "OAuth Creator"})).json()
    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "twitter_oauth_client_id", "x-client-id")
    monkeypatch.setattr(settings, "twitter_oauth_client_secret", "x-client-secret")
    monkeypatch.setattr(settings, "public_url", "http://test")

    start = await client.get(
        "/api/v1/integrations/twitter/oauth/start",
        params={"workspace_id": workspace["id"]},
    )
    assert start.status_code == 200, start.text
    authorization_url = start.json()["authorization_url"]
    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://x.com/i/oauth2/authorize"
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == {"tweet.read", "users.read", "offline.access"}

    async def fake_exchange(code, verifier):
        assert code == "authorization-code"
        assert len(verifier) >= 43
        return {
            "access_token": "oauth-access-token",
            "refresh_token": "oauth-refresh-token",
            "token_type": "bearer",
            "expires_in": 7200,
            "scope": "tweet.read users.read offline.access",
        }

    async def fake_context(token):
        assert token == "oauth-access-token"
        return {
            "profile": {
                "id": "84", "username": "oauth_creator", "name": "OAuth Creator",
                "description": "OAuth connected", "location": "", "url": "https://x.com/oauth_creator",
                "profile_image_url": None, "verified": False, "protected": False,
                "created_at": "2026-01-01T00:00:00Z",
                "public_metrics": {"followers_count": 8, "following_count": 2, "tweet_count": 3},
            },
            "posts": [],
            "timeline_warning": None,
        }

    monkeypatch.setattr(api_module, "exchange_twitter_code", fake_exchange)
    monkeypatch.setattr(api_module, "fetch_twitter_context", fake_context)
    callback = await client.get(
        "/api/v1/integrations/twitter/oauth/callback",
        params={"code": "authorization-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("?screen=profile&twitter_oauth=success")
    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    assert connections[0]["provider"] == "twitter"
    assert connections[0]["config"]["auth_method"] == "oauth2_pkce"
    assert connections[0]["config"]["scopes"] == ["tweet.read", "users.read", "offline.access"]


async def test_google_model_oauth_discovers_gemini_models_and_persists_refresh_token(client, monkeypatch):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Gemini Team"})).json()
    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "google_model_oauth_client_id", "google-client-id")
    monkeypatch.setattr(settings, "google_model_oauth_client_secret", "google-client-secret")
    monkeypatch.setattr(settings, "public_url", "http://test")

    start = await client.get(
        "/api/v1/integrations/google-model/oauth/start",
        params={"workspace_id": workspace["id"], "project_id": "orbit-gemini-test"},
    )
    assert start.status_code == 200, start.text
    parsed = urlparse(start.json()["authorization_url"])
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    assert query["access_type"] == ["offline"]
    assert "https://www.googleapis.com/auth/cloud-platform" in query["scope"][0]

    async def fake_exchange(code):
        assert code == "google-authorization-code"
        return {
            "access_token": "google-access",
            "refresh_token": "google-refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid email profile https://www.googleapis.com/auth/cloud-platform",
        }

    async def fake_models(access_token, project_id):
        assert access_token == "google-access"
        assert project_id == "orbit-gemini-test"
        return [
            {"id": "gemini-3.5-flash", "name": "Gemini 3.5 Flash", "owner": "Google", "context_length": 1000000}
        ]

    monkeypatch.setattr(api_module, "exchange_google_model_code", fake_exchange)
    monkeypatch.setattr(api_module, "discover_google_models", fake_models)
    callback = await client.get(
        "/api/v1/integrations/google-model/oauth/callback",
        params={"code": "google-authorization-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("?screen=team&gemini_oauth=success")
    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    assert connections[0]["provider"] == "gemini-oauth"
    assert connections[0]["config"]["auth_method"] == "google_oauth2"
    assert connections[0]["config"]["available_models"] == ["gemini-3.5-flash"]


async def test_popular_context_connectors_are_verified_and_indexed(client, monkeypatch):
    from orchestrator import context_sync as context_sync_module
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Sources"})).json()

    async def fake_connector(connector, credential, identifier=None, **_kwargs):
        assert credential == f"secret-{connector}"
        if connector == "youtube":
            assert identifier == "@orbit"
        return {
            "label": f"{connector} account",
            "item_count": 7,
            "summary": f"Verified {connector} context.",
            "details": {"source_id": f"id-{connector}"},
        }

    async def fake_telegram_webhook(*_args, **_kwargs):
        return None

    monkeypatch.setattr(context_sync_module, "fetch_context_connector", fake_connector)
    monkeypatch.setattr(api_module, "configure_telegram_webhook", fake_telegram_webhook)
    catalog = (await client.get("/api/v1/integrations/context/catalog")).json()
    assert {item["id"] for item in catalog} == {
        "notion", "slack", "google-drive", "telegram", "youtube", "bitquery", "blockscout"
    }

    addresses = {
        "bitquery": "token:0x0000000000000000000000000000000000000001",
        "blockscout": "0x0000000000000000000000000000000000000001",
    }
    for connector in ["notion", "slack", "google-drive", "telegram", "youtube", "bitquery", "blockscout"]:
        response = await client.post(
            "/api/v1/integrations/context/connect",
            json={
                "workspace_id": workspace["id"],
                "connector": connector,
                "credential": f"secret-{connector}",
                "identifier": "@orbit" if connector == "youtube" else addresses.get(connector),
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["connection"]["provider"] == f"connector-{connector}"
        assert "secret" not in str(response.json()["connection"]["config"])

    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    assert len([item for item in connections if item["provider"].startswith("connector-")]) == 7
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    for name in ["Notion", "Slack", "Google Drive", "Telegram", "YouTube", "Bitquery", "Blockscout"]:
        assert f"Connected source: {name}" in memory[0]["content"]


async def test_context_oauth_sync_and_revoke_lifecycle(client, monkeypatch):
    from orchestrator import context_sync as context_sync_module

    workspace = (await client.post("/api/v1/workspaces", json={"name": "OAuth sources"})).json()
    monkeypatch.setattr(
        api_module,
        "create_context_authorization",
        lambda connector, workspace_id, user_id: f"https://oauth.example/{connector}?workspace={workspace_id}",
    )
    start = await client.get(
        f"/api/v1/integrations/context/oauth/start?workspace_id={workspace['id']}&connector=notion"
    )
    assert start.status_code == 200
    assert start.json()["authorization_url"].startswith("https://oauth.example/notion")
    monkeypatch.setattr(
        api_module,
        "verify_context_state",
        lambda _state: {"connector": "notion", "workspace_id": workspace["id"], "user_id": "local-user", "nonce": "valid"},
    )

    async def fake_exchange(_connector, _code):
        return {"access_token": "oauth-access", "refresh_token": None, "expires_at": None, "scope": "read_content", "workspace_id": "notion-workspace-1"}

    async def fake_fetch(connector, credential, identifier=None, **_kwargs):
        assert connector == "notion"
        assert credential == "oauth-access"
        return {
            "label": "OAuth workspace",
            "item_count": 1,
            "content_bytes": 18,
            "summary": "Readable pages.",
            "records": [{"id": "p1", "title": "Roadmap", "content": "Launch plan content"}],
            "details": {"pages": 1},
            "cursor": None,
            "has_more": False,
        }

    monkeypatch.setattr(api_module, "exchange_context_code", fake_exchange)
    monkeypatch.setattr(context_sync_module, "fetch_context_connector", fake_fetch)
    callback = await client.get(
        "/api/v1/integrations/context/oauth/callback?code=ok&state=valid",
        follow_redirects=False,
    )
    assert callback.status_code == 303
    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    connection = next(item for item in connections if item["provider"] == "connector-notion")
    assert connection["config"]["auth_method"] == "oauth2"
    assert "token" not in str(connection["config"]).lower()
    refreshed = await client.post(f"/api/v1/integrations/context/{connection['id']}/sync")
    assert refreshed.status_code == 200
    assert refreshed.json()["item_count"] == 1
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()[0]
    assert "Launch plan content" in memory["content"]

    async def fake_revoke(_connector, _token):
        return None

    monkeypatch.setattr(api_module, "revoke_context_token", fake_revoke)
    revoked = await client.delete(f"/api/v1/integrations/context/{connection['id']}")
    assert revoked.status_code == 204
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()[0]
    assert "source:connector-notion" not in memory["content"]


async def test_global_slack_and_notion_webhooks_are_signed_and_routed(client, monkeypatch):
    from orchestrator import context_sync as context_sync_module
    from orchestrator.config import get_settings

    workspace = (await client.post("/api/v1/workspaces", json={"name": "Webhook sources"})).json()

    async def fake_fetch(connector, _credential, identifier=None, **_kwargs):
        return {
            "label": f"{connector} workspace",
            "item_count": 1,
            "content_bytes": 8,
            "summary": "Webhook context.",
            "records": [{"id": "1", "title": "Update", "content": "New data"}],
            "details": {"team_id": "T-ORBIT"} if connector == "slack" else {"pages": 1},
            "cursor": None,
            "has_more": False,
        }

    monkeypatch.setattr(context_sync_module, "fetch_context_connector", fake_fetch)
    slack = await client.post("/api/v1/integrations/context/connect", json={"workspace_id": workspace["id"], "connector": "slack", "credential": "slack-token"})
    assert slack.status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "slack_signing_secret", "slack-signing-secret")
    timestamp = str(int(time.time()))
    slack_body = json.dumps({"type": "event_callback", "team_id": "T-ORBIT", "event": {"type": "message"}}, separators=(",", ":")).encode()
    slack_signature = "v0=" + hmac.new(b"slack-signing-secret", f"v0:{timestamp}:".encode() + slack_body, hashlib.sha256).hexdigest()
    slack_event = await client.post("/api/v1/integrations/context/webhooks/slack", content=slack_body, headers={"x-slack-request-timestamp": timestamp, "x-slack-signature": slack_signature})
    assert slack_event.status_code == 200
    bad_slack_event = await client.post("/api/v1/integrations/context/webhooks/slack", content=slack_body, headers={"x-slack-request-timestamp": timestamp, "x-slack-signature": "v0=bad"})
    assert bad_slack_event.status_code == 401

    monkeypatch.setattr(api_module, "verify_context_state", lambda _state: {"connector": "notion", "workspace_id": workspace["id"], "user_id": "local-user", "nonce": "valid"})
    monkeypatch.setattr(api_module, "exchange_context_code", lambda *_args: None)

    async def fake_notion_exchange(*_args):
        return {"access_token": "notion-token", "workspace_id": "W-ORBIT", "scope": "read_content"}

    monkeypatch.setattr(api_module, "exchange_context_code", fake_notion_exchange)
    notion_callback = await client.get("/api/v1/integrations/context/oauth/callback?code=ok&state=valid", follow_redirects=False)
    assert notion_callback.status_code == 303
    monkeypatch.setattr(settings, "notion_webhook_verification_token", "notion-verification")
    notion_body = json.dumps({"id": "event-1", "workspace_id": "W-ORBIT", "type": "page.content_updated"}, separators=(",", ":")).encode()
    notion_signature = "sha256=" + hmac.new(b"notion-verification", notion_body, hashlib.sha256).hexdigest()
    notion_event = await client.post("/api/v1/integrations/context/webhooks/notion", content=notion_body, headers={"x-notion-signature": notion_signature})
    assert notion_event.status_code == 200
    bad_notion_event = await client.post("/api/v1/integrations/context/webhooks/notion", content=notion_body, headers={"x-notion-signature": "sha256=bad"})
    assert bad_notion_event.status_code == 401


async def test_mcp_catalog_install_and_rejects_legacy_agent_attachment(client):
    workspace, agent_ids, _ = await bootstrap(client)
    catalog = (await client.get("/api/v1/mcp/catalog")).json()
    assert len(catalog) == 9
    assert {"github", "filesystem", "postgres", "fetch", "memory"} <= {
        item["id"] for item in catalog
    }

    installed = await client.post(
        "/api/v1/mcp/servers",
        json={"workspace_id": workspace["id"], "preset_id": "memory"},
    )
    assert installed.status_code == 201, installed.text
    assert installed.json()["provider"] == "mcp"
    attached = await client.post(
        f"/api/v1/agents/{agent_ids[0]}/mcp/{installed.json()['id']}"
    )
    assert attached.status_code == 410, attached.text
    assert "workflow" in attached.json()["detail"].lower()


async def test_team_rejects_more_than_ten_agents(client):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Large"})).json()
    response = await client.post(
        "/api/v1/teams",
        json={
            "workspace_id": workspace["id"],
            "name": "Too large",
            "goal": "Test limit",
            "agent_ids": [f"agent-{index}" for index in range(11)],
        },
    )
    assert response.status_code == 422


async def test_deep_research_report_and_memory_update(client, monkeypatch):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Research"})).json()
    await client.post(
        "/api/v1/memory",
        json={
            "workspace_id": workspace["id"],
            "scope": "global",
            "title": "Core",
            "content": "# Core",
        },
    )

    async def fake_research(query, sources, credentials, depth):
        assert query == "short video trends"
        return (
            [
                {
                    "source": "youtube",
                    "title": "Strong hooks",
                    "url": "https://youtube.com/watch?v=1",
                    "snippet": "Retention improves when the promise is clear in the first seconds.",
                    "score": 0.9,
                }
            ],
            {
                "web": {"status": "direct", "results": 0},
                "youtube": {"status": "direct", "results": 1},
            },
        )

    monkeypatch.setattr(api_module, "run_research", fake_research)
    response = await client.post(
        "/api/v1/research/reports",
        json={
            "workspace_id": workspace["id"],
            "query": "short video trends",
            "sources": ["web", "youtube"],
            "depth": "deep",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["findings"][0]["title"] == "Strong hooks"
    reports = (await client.get(f"/api/v1/research/reports?workspace_id={workspace['id']}")).json()
    assert len(reports) == 1
    memory = (await client.get(f"/api/v1/memory?workspace_id={workspace['id']}")).json()
    assert "Strong hooks" in memory[0]["content"]


async def test_deep_research_accepts_native_onchain_source(client, monkeypatch):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "On-chain research"})).json()
    address = "0x" + "ab" * 20

    async def fake_research(query, sources, credentials, depth):
        assert query == f"Audit {address}"
        assert sources == ["onchain"]
        assert {"web", "youtube", "tiktok", "instagram"} <= set(credentials)
        return (
            [{"source": "onchain", "title": "Token overview", "url": "https://explorer.test/token", "snippet": "Native evidence", "score": 0.96}],
            {"onchain": {"status": "native-chain", "results": 1, "queries": 1}},
        )

    monkeypatch.setattr(api_module, "run_research", fake_research)
    capabilities = (await client.get("/api/v1/auth/capabilities")).json()
    assert capabilities["research"]["onchain"] is True
    response = await client.post(
        "/api/v1/research/reports",
        json={"workspace_id": workspace["id"], "query": f"Audit {address}", "sources": ["onchain"]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["requested_sources"] == ["onchain"]
    assert response.json()["source_status"]["onchain"]["status"] == "native-chain"


async def test_human_message_mode_and_task(client):
    _, agent_ids, team = await bootstrap(client)
    run = (
        await client.post(
            "/api/v1/runs",
            json={"team_id": team["id"], "auto_start": False},
        )
    ).json()
    message = await client.post(
        f"/api/v1/runs/{run['id']}/messages",
        json={
            "content": "Проверьте риски",
            "recipients": [agent_ids[1]],
            "command": "instruction",
        },
    )
    assert message.status_code == 201
    assert message.json()["recipients"] == [agent_ids[1]]
    for _ in range(80):
        live_run = (await client.get(f"/api/v1/runs/{run['id']}")).json()
        if live_run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    assert live_run["status"] == "completed"

    mode = await client.post(
        f"/api/v1/runs/{run['id']}/mode", json={"mode": "constructive"}
    )
    assert mode.status_code == 200
    assert mode.json()["mode"] == "constructive"

    task = await client.post(
        f"/api/v1/runs/{run['id']}/tasks",
        json={"title": "Security review", "assigned_agent_id": agent_ids[1]},
    )
    assert task.status_code == 201
    update = await client.patch(
        f"/api/v1/tasks/{task.json()['id']}", json={"status": "in_progress"}
    )
    assert update.status_code == 200
    assert update.json()["status"] == "in_progress"


async def test_workflow_artifact_and_approval(client):
    workspace, agent_ids, team = await bootstrap(client)
    workflow_response = await client.post(
        "/api/v1/workflows",
        json={
            "workspace_id": workspace["id"],
            "team_id": team["id"],
            "name": "Reviewed workflow",
            "nodes": [
                {"id": "start", "type": "start"},
                {"id": "planner", "type": "agent", "agent_id": agent_ids[0]},
                {"id": "final", "type": "final"},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "planner"},
                {"id": "e2", "source": "planner", "target": "final"},
            ],
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow = workflow_response.json()
    validation = await client.post(f"/api/v1/workflows/{workflow['id']}/validate")
    assert validation.json() == {"valid": True, "errors": [], "warnings": []}

    run = (
        await client.post(
            "/api/v1/runs",
            json={"team_id": team["id"], "workflow_id": workflow["id"], "auto_start": False},
        )
    ).json()
    artifact = await client.post(
        f"/api/v1/runs/{run['id']}/artifacts",
        json={"name": "plan.md", "content": "# Plan", "metadata": {"version": 1}},
    )
    assert artifact.status_code == 201, artifact.text
    assert artifact.json()["metadata"] == {"version": 1}

    approval = await client.post(
        f"/api/v1/runs/{run['id']}/approvals",
        json={
            "action": "publish",
            "description": "Publish the plan",
            "requested_by_agent_id": agent_ids[1],
        },
    )
    assert approval.status_code == 201, approval.text
    decision = await client.post(
        f"/api/v1/approvals/{approval.json()['id']}/decision",
        json={"decision": "approved", "note": "Looks good"},
    )
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"


async def test_add_agent_to_existing_team(client):
    workspace, _, team = await bootstrap(client)
    agent = (
        await client.post(
            "/api/v1/agents",
            json={
                "workspace_id": workspace["id"],
                "name": "Security Agent",
                "slug": "security-agent",
                "role": "Security",
                "goal": "Review risks",
                "system_prompt": "Review security risks.",
            },
        )
    ).json()
    response = await client.post(
        f"/api/v1/teams/{team['id']}/agents", json={"agent_id": agent["id"]}
    )
    assert response.status_code == 201
    teams = (await client.get(f"/api/v1/teams?workspace_id={workspace['id']}")).json()
    assert agent["id"] in teams[0]["agent_ids"]


async def test_discover_connection_models(client, monkeypatch):
    async def fake_discovery(base_url, api_key):
        assert base_url == "https://models.example/v1"
        assert api_key == "secret"
        return ([{"id": "model-a", "name": "Model A", "owner": "demo"}], 42)

    monkeypatch.setattr("orchestrator.api.discover_models", fake_discovery)
    response = await client.post(
        "/api/v1/connections/discover",
        json={
            "provider": "openai-compatible",
            "base_url": "https://models.example/v1",
            "api_key": "secret",
        },
    )
    assert response.status_code == 200
    assert response.json()["model_count"] == 1
    assert response.json()["latency_ms"] == 42


async def test_same_provider_key_is_reused_across_multiple_agent_models(client):
    workspace = (await client.post("/api/v1/workspaces", json={"name": "Reuse API"})).json()
    common = {
        "workspace_id": workspace["id"],
        "provider": "openai-compatible",
        "base_url": "https://models.example/v1",
        "api_key": "one-shared-secret",
    }
    first = await client.post(
        "/api/v1/connections",
        json={**common, "name": "First agent API", "config": {"preset": "custom", "available_models": ["model-a", "model-b"], "active_models": ["model-a"]}},
    )
    second = await client.post(
        "/api/v1/connections",
        json={**common, "name": "Second agent API", "config": {"preset": "custom", "available_models": ["model-a", "model-b"], "active_models": ["model-b"]}},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["config"]["active_models"] == ["model-a", "model-b"]
    connections = (await client.get(f"/api/v1/connections?workspace_id={workspace['id']}")).json()
    assert len(connections) == 1


async def test_runtime_v2_checkpoints_commands_and_memory_search(client):
    workspace, _, team = await bootstrap(client)
    workspace_id = workspace["id"]
    created = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": True})
    assert created.status_code == 201
    run_id = created.json()["id"]
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed":
            break
        await asyncio.sleep(0.02)
    assert run["runtime_version"] == "v2"
    checkpoints = (await client.get(f"/api/v1/runs/{run_id}/checkpoints")).json()
    assert checkpoints[0]["stage"] == "planned"
    assert checkpoints[-1]["stage"] == "completed"

    redirected = await client.post(
        f"/api/v1/runs/{run_id}/messages",
        json={"content": "Prepare a safer enterprise launch", "recipients": ["all"], "command": "redirect"},
    )
    assert redirected.status_code == 201
    for _ in range(100):
        run = (await client.get(f"/api/v1/runs/{run_id}")).json()
        if run["status"] == "completed" and run["plan_revision"] == 1:
            break
        await asyncio.sleep(0.02)
    assert run["goal"] == "Prepare a safer enterprise launch"
    commands = (await client.get(f"/api/v1/runs/{run_id}/commands")).json()
    assert commands[-1]["status"] == "handled"
    search = await client.post(
        "/api/v1/memory/search",
        json={"workspace_id": workspace_id, "query": "enterprise launch safer"},
    )
    assert search.status_code == 200
    assert search.json()


async def test_auth_register_login_and_workspace_membership(client):
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "display_name": "Owner", "password": "strong-password-123"},
    )
    assert registered.status_code == 201, registered.text
    token = registered.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    workspace = await client.post("/api/v1/workspaces", json={"name": "Private"}, headers=headers)
    assert workspace.status_code == 201
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "owner@example.com"
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "strong-password-123"},
    )
    assert login.status_code == 200


async def test_account_profile_sessions_and_password_recovery(client):
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "security@example.com", "display_name": "Security", "password": "strong-password-123"},
    )
    token = registered.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    second = await client.post(
        "/api/v1/auth/login",
        json={"email": "security@example.com", "password": "strong-password-123"},
    )
    assert second.status_code == 200
    sessions = await client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()) == 2
    other = next(item for item in sessions.json() if not item["current"])
    assert (await client.delete(f"/api/v1/auth/sessions/{other['id']}", headers=headers)).status_code == 204

    updated = await client.patch("/api/v1/auth/me", headers=headers, json={"display_name": "Secure User"})
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Secure User"

    requested = await client.post("/api/v1/auth/password-reset/request", json={"email": "security@example.com"})
    assert requested.status_code == 202
    reset_token = requested.json()["debug_token"]
    assert reset_token
    confirmed = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "new-strong-password-456"},
    )
    assert confirmed.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    relogin = await client.post(
        "/api/v1/auth/login",
        json={"email": "security@example.com", "password": "new-strong-password-456"},
    )
    assert relogin.status_code == 200
    relogin_headers = {"Authorization": f"Bearer {relogin.json()['token']}"}
    workspace = await client.post("/api/v1/workspaces", headers=relogin_headers, json={"name": "Delete me"})
    assert workspace.status_code == 201
    agent = await client.post(
        "/api/v1/agents",
        headers=relogin_headers,
        json={
            "workspace_id": workspace.json()["id"],
            "name": "Supervisor",
            "slug": "supervisor",
            "role": "Coordinator",
            "goal": "Coordinate the team",
            "system_prompt": "Coordinate the team.",
        },
    )
    assert agent.status_code == 201
    team = await client.post(
        "/api/v1/teams",
        headers=relogin_headers,
        json={
            "workspace_id": workspace.json()["id"],
            "name": "Delete team",
            "goal": "Exercise account cleanup",
            "agent_ids": [agent.json()["id"]],
            "supervisor_agent_id": agent.json()["id"],
        },
    )
    assert team.status_code == 201
    assert (await client.request("DELETE", "/api/v1/auth/me", headers=relogin_headers, json={"password": "new-strong-password-456"})).status_code == 204
    assert (await client.post("/api/v1/auth/login", json={"email": "security@example.com", "password": "new-strong-password-456"})).status_code == 401


async def test_viewer_cannot_mutate_workspace(client):
    from orchestrator.config import get_settings

    settings = get_settings()
    previous = settings.auth_required
    settings.auth_required = True
    try:
        owner = await client.post("/api/v1/auth/register", json={"email": "owner2@example.com", "display_name": "Owner", "password": "strong-password-123"})
        viewer = await client.post("/api/v1/auth/register", json={"email": "viewer@example.com", "display_name": "Viewer", "password": "strong-password-123"})
        owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
        viewer_headers = {"Authorization": f"Bearer {viewer.json()['token']}"}
        workspace = await client.post("/api/v1/workspaces", json={"name": "Read only"}, headers=owner_headers)
        workspace_id = workspace.json()["id"]
        added = await client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            headers=owner_headers,
            json={"email": "viewer@example.com", "role": "viewer"},
        )
        assert added.status_code == 201
        assert (await client.get(f"/api/v1/agents?workspace_id={workspace_id}", headers=viewer_headers)).status_code == 200
        denied = await client.post(
            "/api/v1/agents",
            headers=viewer_headers,
            json={"workspace_id": workspace_id, "name": "Nope", "slug": "nope", "role": "Viewer", "goal": "No write", "system_prompt": "No write"},
        )
        assert denied.status_code == 403
        transferred = await client.post(
            f"/api/v1/workspaces/{workspace_id}/transfer-ownership",
            headers=owner_headers,
            json={"email": "viewer@example.com"},
        )
        assert transferred.status_code == 200
        assert next(item for item in transferred.json() if item["email"] == "viewer@example.com")["role"] == "owner"
    finally:
        settings.auth_required = previous


async def test_file_asset_upload_and_run_attachment(client):
    workspace, _, team = await bootstrap(client)
    uploaded = await client.post(
        f"/api/v1/files?workspace_id={workspace['id']}",
        files={"file": ("brief.md", b"# Campaign brief\nFocus on verified customer evidence.", "text/markdown")},
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()
    assert asset["name"] == "brief.md"
    assert asset["status"] == "ready"
    run = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": False})
    attached = await client.post(f"/api/v1/runs/{run.json()['id']}/file-assets/{asset['id']}")
    assert attached.status_code == 200
    assert attached.json()["context"]["file_asset_ids"] == [asset["id"]]
    listed = await client.get(f"/api/v1/files?workspace_id={workspace['id']}")
    assert listed.json()[0]["sha256"] == asset["sha256"]


async def test_mcp_discovery_execution_and_approval(client, monkeypatch):
    workspace, _, team = await bootstrap(client)
    workspace_id = workspace["id"]
    installed = await client.post(
        "/api/v1/mcp/servers",
        json={
            "workspace_id": workspace_id,
            "preset_id": "custom",
            "name": "Test MCP",
            "transport": "streamable_http",
            "url": "https://mcp.invalid/rpc",
        },
    )
    server_id = installed.json()["id"]

    async def fake_tools(_self):
        from orchestrator.mcp import MCPTool
        return [MCPTool(name="lookup", description="Read data", input_schema={"type": "object"})]

    async def fake_call(_self, name, arguments):
        return {"content": [{"type": "text", "text": f"{name}:{arguments.get('q', 'ok')}"}]}

    monkeypatch.setattr("orchestrator.api.MCPClient.list_tools", fake_tools)
    monkeypatch.setattr("orchestrator.api.MCPClient.call_tool", fake_call)
    tools = await client.get(f"/api/v1/mcp/servers/{server_id}/tools")
    assert tools.status_code == 200
    assert tools.json()[0]["name"] == "lookup"

    run = await client.post("/api/v1/runs", json={"team_id": team["id"], "auto_start": False})
    run_id = run.json()["id"]
    call = await client.post(
        f"/api/v1/runs/{run_id}/tools/call",
        json={"connection_id": server_id, "tool_name": "lookup", "arguments": {"q": "orbit"}, "risk": "read"},
    )
    assert call.status_code == 201
    assert call.json()["status"] == "completed"

    dangerous = await client.post(
        f"/api/v1/runs/{run_id}/tools/call",
        json={"connection_id": server_id, "tool_name": "publish", "arguments": {}, "risk": "external"},
    )
    assert dangerous.json()["status"] == "waiting_for_approval"
    approvals = (await client.get(f"/api/v1/runs/{run_id}/approvals")).json()
    decision = await client.post(
        f"/api/v1/approvals/{approvals[-1]['id']}/decision", json={"decision": "approved"}
    )
    assert decision.status_code == 200
    tool_calls = (await client.get(f"/api/v1/runs/{run_id}/tool-calls")).json()
    assert tool_calls[-1]["status"] == "completed"


async def test_dialogue_participants_can_be_changed(client):
    workspace, original_agent_ids, team = await bootstrap(client)
    extra = await client.post(
        "/api/v1/agents",
        json={
            "workspace_id": workspace["id"],
            "name": "Researcher",
            "slug": "dialogue-researcher",
            "role": "Researcher",
            "goal": "Find evidence",
            "system_prompt": "Find useful evidence.",
        },
    )
    assert extra.status_code == 201, extra.text
    run = await client.post(
        "/api/v1/runs",
        json={
            "team_id": team["id"],
            "context": {"agent_ids": [original_agent_ids[0]]},
            "auto_start": False,
        },
    )
    assert run.status_code == 201, run.text

    changed = await client.patch(
        f"/api/v1/runs/{run.json()['id']}/agents",
        json={"agent_ids": [original_agent_ids[0], extra.json()["id"]]},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["context"]["agent_ids"] == [
        original_agent_ids[0],
        extra.json()["id"],
    ]
    refreshed_teams = await client.get(
        "/api/v1/teams", params={"workspace_id": workspace["id"]}
    )
    assert refreshed_teams.status_code == 200, refreshed_teams.text
    refreshed_team = next(item for item in refreshed_teams.json() if item["id"] == team["id"])
    assert extra.json()["id"] in refreshed_team["agent_ids"]
