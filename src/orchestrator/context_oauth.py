from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from orchestrator.config import get_settings
from orchestrator.security import secret_codec


SUPPORTED = {"notion", "slack", "google-drive", "youtube"}


def callback_url(connector: str) -> str:
    settings = get_settings()
    configured = {
        "notion": settings.notion_oauth_callback_url,
        "slack": settings.slack_oauth_callback_url,
        "google-drive": settings.google_context_oauth_callback_url,
        "youtube": settings.google_context_oauth_callback_url,
    }.get(connector)
    return configured or f"{settings.public_url.rstrip('/')}{settings.api_prefix}/integrations/context/oauth/callback"


def _state(connector: str, workspace_id: str, user_id: str) -> str:
    value = secret_codec.encrypt(json.dumps({
        "connector": connector,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(18),
        "expires_at": int(time.time()) + get_settings().context_oauth_state_ttl_seconds,
    }, separators=(",", ":")))
    if not value:
        raise RuntimeError("Could not create OAuth state")
    return value


def verify_state(state: str) -> dict[str, Any]:
    try:
        raw = secret_codec.decrypt(state)
        value = json.loads(raw or "")
        if value.get("connector") not in SUPPORTED or int(value.get("expires_at", 0)) < int(time.time()):
            raise ValueError("expired")
        if not all(value.get(key) for key in ("workspace_id", "user_id", "nonce")):
            raise ValueError("incomplete")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired connector OAuth state") from exc


def create_authorization(connector: str, workspace_id: str, user_id: str) -> str:
    if connector not in SUPPORTED:
        raise ValueError("OAuth is not supported for this connector")
    settings = get_settings()
    state = _state(connector, workspace_id, user_id)
    if connector == "notion":
        if not settings.notion_oauth_client_id:
            raise RuntimeError("Notion OAuth Client ID is not configured")
        return "https://api.notion.com/v1/oauth/authorize?" + urlencode({
            "client_id": settings.notion_oauth_client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": callback_url(connector),
            "state": state,
        })
    if connector == "slack":
        if not settings.slack_oauth_client_id:
            raise RuntimeError("Slack OAuth Client ID is not configured")
        return "https://slack.com/oauth/v2/authorize?" + urlencode({
            "client_id": settings.slack_oauth_client_id,
            "scope": settings.slack_oauth_scopes,
            "redirect_uri": callback_url(connector),
            "state": state,
        })
    if not settings.google_context_oauth_client_id:
        raise RuntimeError("Google Context OAuth Client ID is not configured")
    scopes = settings.google_drive_oauth_scopes if connector == "google-drive" else settings.youtube_oauth_scopes
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.google_context_oauth_client_id,
        "redirect_uri": callback_url(connector),
        "response_type": "code",
        "scope": scopes,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })


async def exchange_code(connector: str, code: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        if connector == "notion":
            if not settings.notion_oauth_client_id or not settings.notion_oauth_client_secret:
                raise RuntimeError("Notion OAuth credentials are not configured")
            response = await client.post("https://api.notion.com/v1/oauth/token", auth=httpx.BasicAuth(settings.notion_oauth_client_id, settings.notion_oauth_client_secret), json={"grant_type": "authorization_code", "code": code, "redirect_uri": callback_url(connector)})
        elif connector == "slack":
            if not settings.slack_oauth_client_id or not settings.slack_oauth_client_secret:
                raise RuntimeError("Slack OAuth credentials are not configured")
            response = await client.post("https://slack.com/api/oauth.v2.access", data={"client_id": settings.slack_oauth_client_id, "client_secret": settings.slack_oauth_client_secret, "code": code, "redirect_uri": callback_url(connector)})
        else:
            if not settings.google_context_oauth_client_id or not settings.google_context_oauth_client_secret:
                raise RuntimeError("Google Context OAuth credentials are not configured")
            response = await client.post("https://oauth2.googleapis.com/token", data={"client_id": settings.google_context_oauth_client_id, "client_secret": settings.google_context_oauth_client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": callback_url(connector)})
        response.raise_for_status()
        data = response.json()
    if connector == "slack" and not data.get("ok"):
        raise ValueError(f"Slack OAuth: {data.get('error', 'exchange failed')}")
    token = data.get("access_token")
    if not token:
        raise ValueError(f"{connector} returned no access token")
    expires_at = None
    if data.get("expires_in"):
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=int(data["expires_in"]))).isoformat()
    return {"access_token": token, "refresh_token": data.get("refresh_token"), "expires_at": expires_at, "scope": data.get("scope"), "workspace_id": data.get("workspace_id"), "workspace_name": data.get("workspace_name"), "bot_id": data.get("bot_id"), "team": data.get("team")}


async def refresh_google(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://oauth2.googleapis.com/token", data={"client_id": settings.google_context_oauth_client_id, "client_secret": settings.google_context_oauth_client_secret, "refresh_token": refresh_token, "grant_type": "refresh_token"})
        response.raise_for_status()
        data = response.json()
    data["refresh_token"] = refresh_token
    data["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))).isoformat()
    return data


async def revoke_token(connector: str, token: str) -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        if connector == "notion" and settings.notion_oauth_client_id and settings.notion_oauth_client_secret:
            response = await client.post("https://api.notion.com/v1/oauth/revoke", auth=httpx.BasicAuth(settings.notion_oauth_client_id, settings.notion_oauth_client_secret), json={"token": token})
        elif connector == "slack":
            response = await client.post("https://slack.com/api/auth.revoke", headers={"Authorization": f"Bearer {token}"})
        elif connector in {"google-drive", "youtube"}:
            response = await client.post("https://oauth2.googleapis.com/revoke", params={"token": token}, headers={"Content-Type": "application/x-www-form-urlencoded"})
        else:
            return
        if response.status_code not in {200, 201, 204, 400, 401}:
            response.raise_for_status()


async def configure_drive_watch(access_token: str, webhook_url: str, channel_token: str) -> dict[str, Any]:
    """Create a renewable Google Drive change-log notification channel."""
    headers = {"Authorization": f"Bearer {access_token}"}
    expiration = int((time.time() + 6 * 24 * 60 * 60) * 1000)
    async with httpx.AsyncClient(timeout=30) as client:
        start = await client.get(
            "https://www.googleapis.com/drive/v3/changes/startPageToken",
            headers=headers,
            params={"supportsAllDrives": "true"},
        )
        start.raise_for_status()
        page_token = str(start.json().get("startPageToken") or "")
        if not page_token:
            raise ValueError("Google Drive returned no changes page token")
        response = await client.post(
            "https://www.googleapis.com/drive/v3/changes/watch",
            headers=headers,
            params={"pageToken": page_token, "supportsAllDrives": "true"},
            json={
                "id": str(uuid.uuid4()),
                "type": "web_hook",
                "address": webhook_url,
                "token": channel_token,
                "expiration": expiration,
            },
        )
        response.raise_for_status()
        channel = response.json()
    return {
        "channel_id": channel.get("id"),
        "resource_id": channel.get("resourceId"),
        "resource_uri": channel.get("resourceUri"),
        "expiration": int(channel.get("expiration") or expiration),
        "changes_page_token": page_token,
    }


async def stop_drive_watch(access_token: str, channel_id: str, resource_id: str) -> None:
    if not channel_id or not resource_id:
        return
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://www.googleapis.com/drive/v3/channels/stop",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"id": channel_id, "resourceId": resource_id},
        )
        if response.status_code not in {200, 204, 404, 410}:
            response.raise_for_status()
