from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from orchestrator.config import get_settings
from orchestrator.security import secret_codec


GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GEMINI_API = "https://generativelanguage.googleapis.com"


def google_model_callback_url() -> str:
    settings = get_settings()
    return settings.google_model_oauth_callback_url or (
        f"{settings.public_url.rstrip('/')}{settings.api_prefix}/integrations/google-model/oauth/callback"
    )


def create_google_model_authorization(workspace_id: str, user_id: str, project_id: str) -> str:
    settings = get_settings()
    if not settings.google_model_oauth_client_id or not settings.google_model_oauth_client_secret:
        raise RuntimeError("Google model OAuth is not configured on this Orbit server")
    state_data = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "project_id": project_id,
        "nonce": secrets.token_urlsafe(24),
        "expires_at": int(time.time()) + settings.google_model_oauth_state_ttl_seconds,
    }
    state = secret_codec.encrypt(json.dumps(state_data, separators=(",", ":")))
    if not state:
        raise RuntimeError("Could not create Google OAuth state")
    query = urlencode({
        "client_id": settings.google_model_oauth_client_id,
        "redirect_uri": google_model_callback_url(),
        "response_type": "code",
        "scope": settings.google_model_oauth_scopes,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })
    return f"{GOOGLE_AUTHORIZE_URL}?{query}"


def verify_google_model_state(state: str) -> dict[str, Any]:
    try:
        decrypted = secret_codec.decrypt(state)
        if not decrypted:
            raise ValueError("state empty")
        value = json.loads(decrypted)
        if int(value.get("expires_at", 0)) < int(time.time()):
            raise ValueError("state expired")
        if not all(value.get(key) for key in ("workspace_id", "user_id", "project_id", "nonce")):
            raise ValueError("state incomplete")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired Google OAuth state") from exc


async def exchange_google_model_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_model_oauth_client_id or not settings.google_model_oauth_client_secret:
        raise RuntimeError("Google model OAuth is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_model_oauth_client_id,
            "client_secret": settings.google_model_oauth_client_secret,
            "redirect_uri": google_model_callback_url(),
            "grant_type": "authorization_code",
        })
        response.raise_for_status()
        value = response.json()
    if not value.get("access_token"):
        raise ValueError("Google returned no access token")
    return value


async def refresh_google_model_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_model_oauth_client_id or not settings.google_model_oauth_client_secret:
        raise RuntimeError("Google model OAuth is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": settings.google_model_oauth_client_id,
            "client_secret": settings.google_model_oauth_client_secret,
            "grant_type": "refresh_token",
        })
        response.raise_for_status()
        value = response.json()
    if not value.get("access_token"):
        raise ValueError("Google returned no refreshed access token")
    return value


def token_expiry(token_data: dict[str, Any]) -> str | None:
    if not token_data.get("expires_in"):
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))).isoformat()


async def usable_google_access_token(credentials: dict[str, Any]) -> str:
    expires_at = credentials.get("expires_at")
    if expires_at:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if expiry > datetime.now(timezone.utc) + timedelta(seconds=60):
            return str(credentials["access_token"])
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        return str(credentials.get("access_token") or "")
    refreshed = await refresh_google_model_token(str(refresh_token))
    return str(refreshed["access_token"])


async def discover_google_models(access_token: str, project_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{GEMINI_API}/v1/models",
            headers={"Authorization": f"Bearer {access_token}", "x-goog-user-project": project_id},
        )
        response.raise_for_status()
        raw = response.json().get("models") or []
    models = []
    for item in raw:
        if "generateContent" not in (item.get("supportedGenerationMethods") or []):
            continue
        model_id = str(item.get("name") or "").removeprefix("models/")
        if model_id:
            models.append({
                "id": model_id,
                "name": item.get("displayName") or model_id,
                "owner": "Google",
                "context_length": item.get("inputTokenLimit"),
            })
    return sorted(models, key=lambda item: str(item["name"]).lower())
