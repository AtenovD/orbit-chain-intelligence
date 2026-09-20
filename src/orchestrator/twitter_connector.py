from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from orchestrator.config import get_settings
from orchestrator.security import secret_codec


X_API = "https://api.x.com"
PROFILE_FIELDS = "confirmed_email,created_at,description,location,profile_image_url,protected,public_metrics,url,verified"
POST_FIELDS = "created_at,lang,public_metrics"
X_AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
X_TOKEN_URL = "https://api.x.com/2/oauth2/token"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def twitter_callback_url() -> str:
    settings = get_settings()
    return settings.twitter_oauth_callback_url or (
        f"{settings.public_url.rstrip('/')}{settings.api_prefix}/integrations/twitter/oauth/callback"
    )


def create_twitter_authorization(workspace_id: str, user_id: str) -> tuple[str, str]:
    settings = get_settings()
    if not settings.twitter_oauth_client_id:
        raise RuntimeError("X OAuth Client ID is not configured")
    verifier = secrets.token_urlsafe(64)
    challenge = _b64encode(hashlib.sha256(verifier.encode()).digest())
    state_data = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "verifier": verifier,
        "nonce": secrets.token_urlsafe(16),
        "expires_at": int(time.time()) + settings.twitter_oauth_state_ttl_seconds,
    }
    state = secret_codec.encrypt(json.dumps(state_data, separators=(",", ":")))
    if not state:
        raise RuntimeError("Could not create X OAuth state")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.twitter_oauth_client_id,
            "redirect_uri": twitter_callback_url(),
            "scope": settings.twitter_oauth_scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{X_AUTHORIZE_URL}?{query}", state


def verify_twitter_state(state: str) -> dict[str, Any]:
    try:
        decrypted = secret_codec.decrypt(state)
        if not decrypted:
            raise ValueError("state empty")
        value = json.loads(decrypted)
        if int(value.get("expires_at", 0)) < int(time.time()):
            raise ValueError("state expired")
        if not all(value.get(key) for key in ("workspace_id", "user_id", "verifier", "nonce")):
            raise ValueError("state incomplete")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired X OAuth state") from exc


def twitter_login_callback_url() -> str:
    return twitter_callback_url().replace(
        "/integrations/twitter/oauth/callback", "/auth/twitter/callback"
    )


def twitter_login_scopes() -> str:
    """Return login scopes, always requesting the confirmed email claim."""
    scopes = get_settings().twitter_oauth_scopes.split()
    if "users.email" not in scopes:
        scopes.append("users.email")
    return " ".join(dict.fromkeys(scopes))


def create_twitter_login_authorization() -> str:
    """Create a PKCE authorization URL for signing into Orbit with X."""
    settings = get_settings()
    if not settings.twitter_oauth_client_id:
        raise RuntimeError("X OAuth Client ID is not configured")
    verifier = secrets.token_urlsafe(64)
    challenge = _b64encode(hashlib.sha256(verifier.encode()).digest())
    state_data = {
        "flow": "login",
        "verifier": verifier,
        "nonce": secrets.token_urlsafe(16),
        "expires_at": int(time.time()) + settings.twitter_oauth_state_ttl_seconds,
    }
    state = secret_codec.encrypt(json.dumps(state_data, separators=(",", ":")))
    if not state:
        raise RuntimeError("Could not create X OAuth state")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.twitter_oauth_client_id,
            "redirect_uri": twitter_login_callback_url(),
            "scope": twitter_login_scopes(),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{X_AUTHORIZE_URL}?{query}"


def verify_twitter_login_state(state: str) -> dict[str, Any]:
    try:
        decrypted = secret_codec.decrypt(state)
        if not decrypted:
            raise ValueError("state empty")
        value = json.loads(decrypted)
        if value.get("flow") != "login" or int(value.get("expires_at", 0)) < int(time.time()):
            raise ValueError("state expired")
        if not all(value.get(key) for key in ("verifier", "nonce")):
            raise ValueError("state incomplete")
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid or expired X OAuth state") from exc


async def exchange_twitter_code(
    code: str,
    code_verifier: str,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.twitter_oauth_client_id:
        raise RuntimeError("X OAuth Client ID is not configured")
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": settings.twitter_oauth_client_id,
        "redirect_uri": redirect_uri or twitter_callback_url(),
        "code_verifier": code_verifier,
    }
    auth = (
        httpx.BasicAuth(settings.twitter_oauth_client_id, settings.twitter_oauth_client_secret)
        if settings.twitter_oauth_client_secret
        else None
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(X_TOKEN_URL, data=data, auth=auth)
        response.raise_for_status()
        token_data = response.json()
    if not token_data.get("access_token"):
        raise ValueError("X returned no access token")
    return token_data


async def refresh_twitter_token(refresh_token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.twitter_oauth_client_id:
        raise RuntimeError("X OAuth Client ID is not configured")
    data = {
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "client_id": settings.twitter_oauth_client_id,
    }
    auth = (
        httpx.BasicAuth(settings.twitter_oauth_client_id, settings.twitter_oauth_client_secret)
        if settings.twitter_oauth_client_secret
        else None
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(X_TOKEN_URL, data=data, auth=auth)
        response.raise_for_status()
        token_data = response.json()
    if not token_data.get("access_token"):
        raise ValueError("X returned no refreshed access token")
    return token_data


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "Orbit-Agent-Orchestrator",
    }


async def fetch_twitter_context(token: str) -> dict[str, Any]:
    """Validate an X user-context token and collect a compact content snapshot."""
    async with httpx.AsyncClient(base_url=X_API, headers=_headers(token), timeout=30) as client:
        profile_response = await client.get("/2/users/me", params={"user.fields": PROFILE_FIELDS})
        profile_response.raise_for_status()
        profile = profile_response.json().get("data")
        if not profile or not profile.get("id") or not profile.get("username"):
            raise ValueError("X returned no authenticated user")

        posts: list[dict[str, Any]] = []
        timeline_warning: str | None = None
        try:
            timeline_response = await client.get(
                f"/2/users/{profile['id']}/tweets",
                params={
                    "max_results": 20,
                    "exclude": "retweets,replies",
                    "tweet.fields": POST_FIELDS,
                },
            )
            timeline_response.raise_for_status()
            posts = timeline_response.json().get("data") or []
        except httpx.HTTPStatusError as exc:
            timeline_warning = f"Recent posts unavailable ({exc.response.status_code}); add tweet.read scope"

    return {
        "profile": {
            "id": str(profile["id"]),
            "username": profile["username"],
            "name": profile.get("name") or profile["username"],
            "confirmed_email": profile.get("confirmed_email") or "",
            "description": profile.get("description") or "",
            "location": profile.get("location") or "",
            "url": profile.get("url") or f"https://x.com/{profile['username']}",
            "profile_image_url": profile.get("profile_image_url"),
            "verified": bool(profile.get("verified")),
            "protected": bool(profile.get("protected")),
            "created_at": profile.get("created_at"),
            "public_metrics": profile.get("public_metrics") or {},
        },
        "posts": [
            {
                "id": str(post.get("id", "")),
                "text": str(post.get("text", ""))[:1000],
                "created_at": post.get("created_at"),
                "lang": post.get("lang"),
                "public_metrics": post.get("public_metrics") or {},
            }
            for post in posts[:20]
        ],
        "timeline_warning": timeline_warning,
    }


def twitter_memory_markdown(data: dict[str, Any]) -> str:
    profile = data["profile"]
    metrics = profile.get("public_metrics") or {}
    lines = [
        "<!-- source:x -->",
        "## Connected source: X / Twitter",
        f"- Account: {profile.get('name')} (@{profile.get('username')})",
        f"- Bio: {profile.get('description') or 'not specified'}",
        f"- Followers: {metrics.get('followers_count', 0)}",
        f"- Following: {metrics.get('following_count', 0)}",
        f"- Posts: {metrics.get('tweet_count', 0)}",
        f"- Verified: {'yes' if profile.get('verified') else 'no'}",
    ]
    posts = data.get("posts") or []
    if posts:
        lines.extend(["", "### Recent content snapshot"])
        for post in posts:
            engagement = post.get("public_metrics") or {}
            score = sum(int(engagement.get(key, 0) or 0) for key in ("like_count", "retweet_count", "reply_count", "quote_count"))
            text = " ".join(str(post.get("text", "")).split())[:400]
            lines.append(f"- [{score} interactions] {text}")
    elif data.get("timeline_warning"):
        lines.extend(["", f"- Timeline: {data['timeline_warning']}"])
    lines.append("<!-- /source:x -->")
    return "\n".join(lines)
