from sqlalchemy import func, select

from orchestrator.config import get_settings
from orchestrator.db import SessionFactory
from orchestrator.models import User


async def test_auth_is_secure_by_default_and_blocks_unauthenticated_workspace_access(client):
    settings = get_settings()
    original = settings.auth_required
    settings.auth_required = True
    try:
        assert (await client.get("/api/v1/workspaces")).status_code == 401
        assert (await client.post("/api/v1/workspaces", json={"name": "Nope"})).status_code == 401
    finally:
        settings.auth_required = original


async def test_mascot_asset_is_public_when_auth_is_required(client):
    settings = get_settings()
    original = settings.auth_required
    settings.auth_required = True
    try:
        response = await client.get("/scout-3d-waist-v2.png")
        assert response.status_code != 401
    finally:
        settings.auth_required = original


async def test_favicon_is_public_when_auth_is_required(client):
    settings = get_settings()
    original = settings.auth_required
    settings.auth_required = True
    try:
        response = await client.get("/favicon.svg")
        assert response.status_code != 401
    finally:
        settings.auth_required = original


async def test_registration_requires_confirmation_before_a_run(client):
    settings = get_settings()
    old_auth, old_verification = settings.auth_required, settings.email_verification_required
    settings.auth_required = True
    settings.email_verification_required = True
    try:
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": "verify@example.com", "display_name": "Verify", "password": "strong-password-123"},
        )
        assert registered.status_code == 201, registered.text
        assert registered.json()["user"]["email_verified"] is False
        token = registered.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        workspace = await client.post("/api/v1/workspaces", json={"name": "Verified"}, headers=headers)
        agent = await client.post(
            "/api/v1/agents",
            headers=headers,
            json={"workspace_id": workspace.json()["id"], "name": "A", "slug": "a", "role": "R", "goal": "G", "system_prompt": "P"},
        )
        team = await client.post(
            "/api/v1/teams",
            headers=headers,
            json={"workspace_id": workspace.json()["id"], "name": "T", "goal": "G", "agent_ids": [agent.json()["id"]]},
        )
        blocked = await client.post("/api/v1/runs", headers=headers, json={"team_id": team.json()["id"]})
        assert blocked.status_code == 403
        confirmed = await client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": registered.json()["debug_verification_token"]},
        )
        assert confirmed.status_code == 204
        assert (await client.post("/api/v1/runs", headers=headers, json={"team_id": team.json()["id"]})).status_code == 201
    finally:
        settings.auth_required = old_auth
        settings.email_verification_required = old_verification


async def test_production_registration_fails_closed_before_creating_user_without_smtp(client):
    settings = get_settings()
    old_env, old_verification, old_smtp = settings.app_env, settings.email_verification_required, settings.smtp_host
    settings.app_env = "production"
    settings.email_verification_required = True
    settings.smtp_host = None
    try:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "offline@example.com", "display_name": "Offline", "password": "strong-password-123"},
        )
        assert response.status_code == 503
        async with SessionFactory() as session:
            assert await session.scalar(select(func.count(User.id))) == 0
    finally:
        settings.app_env = old_env
        settings.email_verification_required = old_verification
        settings.smtp_host = old_smtp




async def test_daily_research_quota_blocks_further_runs_for_the_day(client):
    settings = get_settings()
    old_auth, old_verify = settings.auth_required, settings.email_verification_required
    old_research, old_admin = settings.daily_research_limit, list(settings.admin_emails)
    settings.auth_required = True
    settings.email_verification_required = False
    settings.daily_research_limit = 2
    settings.admin_emails = []
    try:
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": "quota@example.com", "display_name": "Quota", "password": "strong-password-123"},
        )
        headers = {"Authorization": f"Bearer {registered.json()['token']}"}
        workspace = await client.post("/api/v1/workspaces", json={"name": "Quota"}, headers=headers)
        agent = await client.post(
            "/api/v1/agents",
            headers=headers,
            json={"workspace_id": workspace.json()["id"], "name": "A", "slug": "a", "role": "R", "goal": "G", "system_prompt": "P"},
        )
        team = await client.post(
            "/api/v1/teams",
            headers=headers,
            json={"workspace_id": workspace.json()["id"], "name": "T", "goal": "G", "agent_ids": [agent.json()["id"]]},
        )
        team_id = team.json()["id"]
        for _ in range(2):
            assert (await client.post("/api/v1/runs", headers=headers, json={"team_id": team_id})).status_code == 201
        blocked = await client.post("/api/v1/runs", headers=headers, json={"team_id": team_id})
        assert blocked.status_code == 429, blocked.text
        assert "Daily limit reached" in blocked.text
    finally:
        settings.auth_required = old_auth
        settings.email_verification_required = old_verify
        settings.daily_research_limit = old_research
        settings.admin_emails = old_admin


async def test_daily_quota_never_gates_the_owner_account(client):
    settings = get_settings()
    old_auth, old_verify = settings.auth_required, settings.email_verification_required
    old_research, old_admin = settings.daily_research_limit, list(settings.admin_emails)
    settings.auth_required = True
    settings.email_verification_required = False
    settings.daily_research_limit = 1
    settings.admin_emails = ["owner-quota@example.com"]
    try:
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": "owner-quota@example.com", "display_name": "Owner", "password": "strong-password-123"},
        )
        headers = {"Authorization": f"Bearer {registered.json()['token']}"}
        workspace = await client.post("/api/v1/workspaces", json={"name": "Owner"}, headers=headers)
        agent = await client.post(
            "/api/v1/agents",
            headers=headers,
            json={"workspace_id": workspace.json()["id"], "name": "A", "slug": "a", "role": "R", "goal": "G", "system_prompt": "P"},
        )
        team = await client.post(
            "/api/v1/teams",
            headers=headers,
            json={"workspace_id": workspace.json()["id"], "name": "T", "goal": "G", "agent_ids": [agent.json()["id"]]},
        )
        team_id = team.json()["id"]
        # The limit is 1, so a gated account would be refused on the second run.
        for _ in range(3):
            assert (await client.post("/api/v1/runs", headers=headers, json={"team_id": team_id})).status_code == 201
    finally:
        settings.auth_required = old_auth
        settings.email_verification_required = old_verify
        settings.daily_research_limit = old_research
        settings.admin_emails = old_admin
