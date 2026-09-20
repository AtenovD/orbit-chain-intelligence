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
    return settings.google_auth_callback_url or (
        f"{settings.public_url.rstrip('/')}{settings.api_prefix}/auth/google/callback"
    )


def create_authorization() -> str:
    settings = get_settings()
    if not settings.google_auth_client_id:
        raise RuntimeError("Google Sign-In is not configured")
    state = secret_codec.encrypt(
        json.dumps(
            {
                "nonce": secrets.token_urlsafe(24),
                "expires_at": int(time.time()) + settings.google_auth_state_ttl_seconds,
            },
            separators=(",", ":"),
        )
    )
    if not state:
        raise RuntimeError("Could not create Google OAuth state")
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": settings.google_auth_client_id,
            "redirect_uri": callback_url(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )


def verify_state(state: str) -> dict[str, Any]:
    try:
        value = json.loads(secret_codec.decrypt(state) or "")
        if int(value.get("expires_at", 0)) < int(time.time()) or not value.get("nonce"):
            raise ValueError("expired or incomplete")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired Google OAuth state") from exc


async def exchange_code(code: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.google_auth_client_id or not settings.google_auth_client_secret:
        raise RuntimeError("Google Sign-In credentials are not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_auth_client_id,
                "client_secret": settings.google_auth_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_url(),
            },
        )
        token_response.raise_for_status()
        token = token_response.json()
        access_token = token.get("access_token")
        if not access_token:
            raise ValueError("Google returned no access token")
        profile_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
    email = str(profile.get("email") or "").strip().lower()
    if not email or profile.get("email_verified") is not True:
        raise ValueError("Google account does not have a verified email address")
    return {
        "subject": str(profile.get("sub") or ""),
        "email": email,
        "display_name": str(profile.get("name") or email.split("@", 1)[0])[:120],
    }
