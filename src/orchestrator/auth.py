from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from orchestrator.config import get_settings
from orchestrator.db import SessionFactory
from orchestrator.models import ApiRateLimit, AuthSession, DailyVisit, User, WorkspaceMember


current_user_id: ContextVar[str | None] = ContextVar("orbit_current_user_id", default=None)
current_request_write: ContextVar[bool] = ContextVar("orbit_request_write", default=False)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters")
    salt = os.urandom(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(value).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt_text, expected_text = encoded.split("$", 5)
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(expected_text)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def request_client_address(request: Request | None) -> str | None:
    if not request:
        return None
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded_for or (request.client.host if request.client else None)


async def create_auth_session(session, user: User, request: Request | None = None) -> tuple[AuthSession, str]:
    token = secrets.token_urlsafe(40)
    now = datetime.now(timezone.utc)
    value = AuthSession(
        user_id=user.id,
        token_hash=token_hash(token),
        expires_at=now + timedelta(days=get_settings().session_days),
        ip_address=request_client_address(request),
        user_agent=(request.headers.get("user-agent", "")[:500] or None) if request else None,
        last_seen_at=now,
    )
    session.add(value)
    await session.commit()
    return value, token


def _minute_window(now: datetime) -> datetime:
    return now.replace(second=0, microsecond=0)


def _privacy_hash(value: str) -> str:
    # A deployment-specific secret is mandatory in production. The fallback
    # keeps development databases useful without ever persisting a raw address.
    secret = get_settings().secret_encryption_key or "orbit-local-analytics"
    return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()


async def consume_rate_limit(*, scope: str, subject: str, limit: int) -> bool:
    """Return False when a durable, one-minute limit is exhausted."""
    now = datetime.now(timezone.utc)
    window = _minute_window(now)
    subject_hash = _privacy_hash(subject)
    async with SessionFactory() as session:
        value = await session.scalar(
            select(ApiRateLimit).where(
                ApiRateLimit.scope == scope,
                ApiRateLimit.subject_hash == subject_hash,
                ApiRateLimit.window_started_at == window,
            )
        )
        if value is None:
            session.add(ApiRateLimit(scope=scope, subject_hash=subject_hash, window_started_at=window, hits=1))
            await session.commit()
            return True
        if value.hits >= max(1, limit):
            return False
        value.hits += 1
        await session.commit()
        return True


async def record_activity(*, user: User | None, client_key: str, user_agent: str, token: str) -> None:
    """Aggregate visits per UTC day and refresh account/session activity."""
    now = datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    visitor_source = f"user:{user.id}" if user else f"anonymous:{client_key}:{user_agent[:160]}"
    async with SessionFactory() as session:
        visit = await session.scalar(
            select(DailyVisit).where(
                DailyVisit.day == day,
                DailyVisit.visitor_hash == _privacy_hash(visitor_source),
            )
        )
        if visit is None:
            session.add(
                DailyVisit(
                    day=day,
                    visitor_hash=_privacy_hash(visitor_source),
                    user_id=user.id if user else None,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            visit.request_count += 1
            visit.last_seen_at = now
            if user:
                visit.user_id = user.id
        if user:
            db_user = await session.get(User, user.id)
            if db_user:
                db_user.last_seen_at = now
            if token:
                auth_session = await session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
                if auth_session:
                    auth_session.last_seen_at = now
        await session.commit()


def is_superuser(user: User) -> bool:
    return user.is_superuser or user.email.strip().lower() in set(get_settings().admin_emails)


async def require_superuser(session) -> User:
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await session.get(User, user_id)
    if not user or not user.enabled or not is_superuser(user):
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


async def authenticate_token(session, token: str) -> User | None:
    auth_session = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    )
    if not auth_session:
        return None
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        await session.delete(auth_session)
        await session.commit()
        return None
    user = await session.get(User, auth_session.user_id)
    return user if user and user.enabled else None


async def ensure_workspace_access(session, workspace_id: str, *, write: bool | None = None) -> None:
    user_id = current_user_id.get()
    if not get_settings().auth_required or not user_id:
        return
    membership = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Workspace not found")
    requires_write = current_request_write.get() if write is None else write
    if requires_write and membership.role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=403, detail="Workspace is read-only")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path
        # Production traffic reaches the API through the loopback-only reverse
        # proxy, so use the original address Apache appends for per-client
        # throttling instead of rate-limiting every public user as one client.
        forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        client_key = forwarded_for or (request.client.host if request.client else "unknown")
        auth_route = request.method == "POST" and path in {
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/password-reset/request",
            "/api/v1/auth/password-reset/confirm",
            "/api/v1/auth/email-verification/confirm",
            "/api/v1/auth/email-verification/request",
        }
        if auth_route and not await consume_rate_limit(
            scope="auth", subject=f"{client_key}:{path}", limit=settings.auth_rate_limit_per_minute
        ):
            return JSONResponse(
                {"code": "rate_limited", "message": "Too many authentication attempts", "retryable": True},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        content_length = request.headers.get("content-length")
        body_limit = settings.max_file_bytes + 100_000 if path.startswith("/api/v1/files") else settings.max_request_bytes
        if content_length and content_length.isdigit() and int(content_length) > body_limit:
            return JSONResponse(
                {"code": "request_too_large", "message": "Request body is too large", "retryable": False},
                status_code=413,
            )
        public = (
            path in {
                "/",
                "/favicon.ico",
                "/favicon.svg",
                "/scout-3d-waist-v2.png",
                "/privacy.html",
                "/terms.html",
                "/api/v1/health",
                "/docs",
                "/api/v1/openapi.json",
            }
            or path.startswith("/assets/")
            or path.startswith("/api/v1/auth/")
            or path.startswith("/api/v1/public/replays/")
            or path.startswith("/api/v1/integrations/context/webhooks/")
        )
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
        if not token:
            token = request.cookies.get("orbit_session", "")
        if not token and path.endswith("/stream"):
            token = request.query_params.get("access_token", "")
        user = None
        if token:
            async with SessionFactory() as session:
                user = await authenticate_token(session, token)
        if settings.auth_required and not public and not user:
            return JSONResponse(
                {"code": "authentication_required", "message": "Authentication required", "retryable": False},
                status_code=401,
            )
        expensive = request.method == "POST" and (
            path == "/api/v1/runs"
            or path == "/api/v1/research/reports"
            or path.endswith("/tools/call")
            or path.endswith("/sync")
            or path == "/api/v1/connections/discover"
        )
        if expensive and not await consume_rate_limit(
            scope="expensive", subject=user.id if user else client_key, limit=settings.expensive_rate_limit_per_minute
        ):
            return JSONResponse(
                {"code": "rate_limited", "message": "Too many expensive requests", "retryable": True},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        context_token = current_user_id.set(user.id if user else None)
        write_token = current_request_write.set(request.method not in {"GET", "HEAD", "OPTIONS"})
        try:
            request.state.user_id = user.id if user else None
            # Count API and UI activity centrally, with only a daily keyed hash
            # for anonymous visitors. Analytics never stores raw public IPs.
            if not path.startswith("/assets/") and path not in {"/favicon.ico", "/favicon.svg"}:
                await record_activity(
                    user=user,
                    client_key=client_key,
                    user_agent=request.headers.get("user-agent", ""),
                    token=token,
                )
            response = await call_next(request)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: blob:; media-src 'self' https://d8j0ntlcm91z4.cloudfront.net; font-src 'self'; "
                "style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; "
                "connect-src 'self' http://127.0.0.1:* http://localhost:*",
            )
            return response
        finally:
            current_request_write.reset(write_token)
            current_user_id.reset(context_token)
