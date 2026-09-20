from __future__ import annotations

import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from orchestrator.config import get_settings
from orchestrator.security import secret_codec


def callback_url() -> str:
    settings = get_settings()
    return settings.github_oauth_callback_url or (
        f"{settings.public_url.rstrip('/')}{settings.api_prefix}"
        "/integrations/github/oauth/callback"
    )


def create_authorization(workspace_id: str, user_id: str) -> str:
    settings = get_settings()
    if not settings.github_oauth_client_id:
        raise RuntimeError("GitHub OAuth Client ID is not configured")
    state = secret_codec.encrypt(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "user_id": user_id,
                "nonce": secrets.token_urlsafe(18),
                "expires_at": int(time.time()) + settings.github_oauth_state_ttl_seconds,
            },
            separators=(",", ":"),
        )
    )
    if not state:
        raise RuntimeError("Could not create GitHub OAuth state")
    return "https://github.com/login/oauth/authorize?" + urlencode(
        {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": callback_url(),
            "scope": settings.github_oauth_scopes,
            "state": state,
            "allow_signup": "true",
        }
    )


def verify_state(state: str) -> dict[str, Any]:
    try:
        value = json.loads(secret_codec.decrypt(state) or "")
        if int(value.get("expires_at", 0)) < int(time.time()):
            raise ValueError("expired")
        if not all(value.get(key) for key in ("workspace_id", "user_id", "nonce")):
            raise ValueError("incomplete")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired GitHub OAuth state") from exc


async def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise RuntimeError("GitHub OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": callback_url(),
            },
        )
        response.raise_for_status()
        data = response.json()
    if data.get("error"):
        raise ValueError(f"GitHub OAuth: {data.get('error_description') or data['error']}")
    if not data.get("access_token"):
        raise ValueError("GitHub returned no access token")
    return data


async def revoke_token(token: str) -> None:
    settings = get_settings()
    if not token or not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(
            "DELETE",
            f"https://api.github.com/applications/{settings.github_oauth_client_id}/token",
            auth=httpx.BasicAuth(
                settings.github_oauth_client_id,
                settings.github_oauth_client_secret,
            ),
            headers={"Accept": "application/vnd.github+json"},
            json={"access_token": token},
        )
        if response.status_code not in {204, 404, 401}:
            response.raise_for_status()
