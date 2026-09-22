from contextlib import contextmanager
from datetime import datetime, timezone

from eth_account import Account
from eth_account.messages import encode_defunct

from orchestrator import wallet_auth
from orchestrator.config import get_settings


@contextmanager
def guest_settings(**overrides):
    settings = get_settings()
    saved = {key: getattr(settings, key) for key in ("auth_required", *overrides)}
    settings.auth_required = True
    for key, value in overrides.items():
        setattr(settings, key, value)
    try:
        yield settings
    finally:
        for key, value in saved.items():
            setattr(settings, key, value)


def bearer(payload):
    return {"Authorization": f"Bearer {payload['token']}"}


async def sign_in_message(client, account, *, headers=None):
    nonce = (await client.post("/api/v1/auth/wallet/nonce")).json()["nonce"]
    message = wallet_auth.build_message(address=account.address, nonce=nonce, issued_at=datetime.now(timezone.utc))
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return message, "0x" + signature.removeprefix("0x")


async def make_team(client, headers, slug="a"):
    workspace = await client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers)
    agent = await client.post(
        "/api/v1/agents",
        headers=headers,
        json={"workspace_id": workspace.json()["id"], "name": "A", "slug": slug, "role": "R", "goal": "G", "system_prompt": "P"},
    )
    team = await client.post(
        "/api/v1/teams",
        headers=headers,
        json={"workspace_id": workspace.json()["id"], "name": "T", "goal": "G", "agent_ids": [agent.json()["id"]]},
    )
    return team.json()["id"]


async def test_guest_gets_an_isolated_account_without_any_form(client):
    with guest_settings():
        first = (await client.post("/api/v1/auth/guest")).json()
        second = (await client.post("/api/v1/auth/guest")).json()
        assert first["user"]["is_guest"] and first["user"]["wallet_address"] is None
        assert first["user"]["id"] != second["user"]["id"]
        created = await client.post("/api/v1/workspaces", json={"name": "Mine"}, headers=bearer(first))
        assert created.status_code == 201
        assert (await client.get("/api/v1/workspaces", headers=bearer(second))).json() == []


async def test_guest_creation_is_capped_per_network_address(client):
    with guest_settings(guest_max_per_ip_per_day=2):
        assert (await client.post("/api/v1/auth/guest")).status_code == 201
        assert (await client.post("/api/v1/auth/guest")).status_code == 201
        assert (await client.post("/api/v1/auth/guest")).status_code == 429


async def test_guest_access_can_be_disabled(client):
    with guest_settings(guest_access_enabled=False):
        assert (await client.post("/api/v1/auth/guest")).status_code == 403


async def test_wallet_signature_links_to_the_guest_and_cannot_be_replayed(client):
    with guest_settings():
        guest = (await client.post("/api/v1/auth/guest")).json()
        account = Account.create()
        message, signature = await sign_in_message(client, account)
        linked = await client.post(
            "/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=bearer(guest)
        )
        assert linked.status_code == 200, linked.text
        assert linked.json()["user"]["id"] == guest["user"]["id"]
        assert linked.json()["user"]["wallet_address"] == account.address.lower()
        replay = await client.post(
            "/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=bearer(guest)
        )
        assert replay.status_code == 409


async def test_wallet_signature_from_another_key_is_rejected(client):
    with guest_settings():
        guest = (await client.post("/api/v1/auth/guest")).json()
        claimed, attacker = Account.create(), Account.create()
        message, _ = await sign_in_message(client, claimed)
        forged = Account.sign_message(encode_defunct(text=message), attacker.key).signature.hex()
        response = await client.post(
            "/api/v1/auth/wallet/verify",
            json={"message": message, "signature": "0x" + forged.removeprefix("0x")},
            headers=bearer(guest),
        )
        assert response.status_code == 401


async def test_message_for_another_site_is_rejected(client):
    with guest_settings():
        guest = (await client.post("/api/v1/auth/guest")).json()
        account = Account.create()
        nonce = (await client.post("/api/v1/auth/wallet/nonce")).json()["nonce"]
        message = wallet_auth.build_message(
            address=account.address, nonce=nonce, issued_at=datetime.now(timezone.utc), domain="evil.example", uri="https://evil.example"
        )
        signature = "0x" + Account.sign_message(encode_defunct(text=message), account.key).signature.hex().removeprefix("0x")
        response = await client.post(
            "/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=bearer(guest)
        )
        assert response.status_code == 401


async def test_returning_wallet_signs_in_to_its_existing_account(client):
    with guest_settings():
        account = Account.create()
        first_guest = (await client.post("/api/v1/auth/guest")).json()
        message, signature = await sign_in_message(client, account)
        first = await client.post(
            "/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=bearer(first_guest)
        )
        # A fresh browser (new guest) signs with the same wallet and lands in the original account.
        new_guest = (await client.post("/api/v1/auth/guest")).json()
        message, signature = await sign_in_message(client, account)
        again = await client.post(
            "/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=bearer(new_guest)
        )
        assert again.json()["user"]["id"] == first.json()["user"]["id"]


async def test_wallet_with_no_session_creates_a_wallet_account(client):
    with guest_settings():
        account = Account.create()
        message, signature = await sign_in_message(client, account)
        response = await client.post("/api/v1/auth/wallet/verify", json={"message": message, "signature": signature})
        assert response.status_code == 200, response.text
        assert response.json()["user"]["wallet_address"] == account.address.lower()
        assert response.json()["user"]["is_guest"] is False
        # Its only way in is the wallet, so it must not be possible to detach it.
        assert (await client.delete("/api/v1/auth/wallet", headers=bearer(response.json()))).status_code == 409


async def test_guest_quota_is_smaller_and_a_wallet_lifts_it(client):
    with guest_settings(guest_daily_research_limit=1, daily_research_limit=3, email_verification_required=False):
        guest = (await client.post("/api/v1/auth/guest")).json()
        headers = bearer(guest)
        team_id = await make_team(client, headers)
        assert (await client.post("/api/v1/runs", headers=headers, json={"team_id": team_id})).status_code == 201
        blocked = await client.post("/api/v1/runs", headers=headers, json={"team_id": team_id})
        assert blocked.status_code == 429, blocked.text
        message, signature = await sign_in_message(client, Account.create())
        assert (await client.post("/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=headers)).status_code == 200
        assert (await client.post("/api/v1/runs", headers=headers, json={"team_id": team_id})).status_code == 201


async def test_guest_can_detach_a_linked_wallet(client):
    with guest_settings():
        guest = (await client.post("/api/v1/auth/guest")).json()
        message, signature = await sign_in_message(client, Account.create())
        await client.post("/api/v1/auth/wallet/verify", json={"message": message, "signature": signature}, headers=bearer(guest))
        detached = await client.delete("/api/v1/auth/wallet", headers=bearer(guest))
        assert detached.status_code == 200 and detached.json()["wallet_address"] is None
