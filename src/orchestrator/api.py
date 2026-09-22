from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from orchestrator import chain_tools, wallet_auth
from orchestrator.agent_evals import build_agent_scorecards
from orchestrator.db import get_session
from orchestrator.auth import (
    create_auth_session,
    current_user_id,
    ensure_workspace_access,
    hash_password,
    request_client_address,
    is_superuser,
    require_superuser,
    token_hash,
    verify_password,
)
from orchestrator.events import broker
from orchestrator.github_connector import (
    fetch_github_context,
    fetch_repository_file,
    fetch_repository_tree,
    github_memory_markdown,
    search_repository_code,
)
from orchestrator.github_oauth import (
    callback_url as github_oauth_callback_url,
    create_authorization as create_github_authorization,
    exchange_code as exchange_github_code,
    revoke_token as revoke_github_token,
    verify_state as verify_github_state,
)
from orchestrator.twitter_connector import (
    create_twitter_authorization,
    create_twitter_login_authorization,
    exchange_twitter_code,
    fetch_twitter_context,
    twitter_callback_url,
    twitter_login_scopes,
    twitter_login_callback_url,
    twitter_memory_markdown,
    verify_twitter_state,
    verify_twitter_login_state,
)
from orchestrator.google_model_oauth import (
    create_google_model_authorization,
    discover_google_models,
    exchange_google_model_code,
    google_model_callback_url,
    token_expiry,
    verify_google_model_state,
)
from orchestrator.google_auth import (
    callback_url as google_auth_callback_url,
    create_authorization as create_google_auth_authorization,
    exchange_code as exchange_google_auth_code,
    verify_state as verify_google_auth_state,
)
from orchestrator.context_connectors import (
    CONNECTOR_CATALOG,
    connector_memory_markdown,
    connector_preset,
    configure_telegram_webhook,
    fetch_context_connector,
    remove_telegram_webhook,
    telegram_record,
)
from orchestrator.context_oauth import (
    callback_url as context_oauth_callback_url,
    create_authorization as create_context_authorization,
    exchange_code as exchange_context_code,
    revoke_token as revoke_context_token,
    stop_drive_watch,
    verify_state as verify_context_state,
)
from orchestrator.context_sync import (
    ingest_context_records,
    mark_sync_error,
    sync_connection_by_id,
    sync_context_connection,
)
from orchestrator.mcp_catalog import MCP_CATALOG, find_mcp_preset
from orchestrator.mcp import MCPClient
from orchestrator.models import (
    Agent,
    AgentLesson,
    AuthSession,
    DailyUsage,
    WalletNonce,
    DailyVisit,
    EmailVerificationToken,
    PasswordResetToken,
    Approval,
    ApprovalStatus,
    Artifact,
    FileAsset,
    MemoryNote,
    MarketObservation,
    PaperTrade,
    DecisionEvaluation,
    RunCheckpoint,
    RunCommand,
    ProviderConnection,
    ResearchReport,
    Run,
    RunEvent,
    RunStatus,
    Task,
    TaskAttempt,
    Team,
    TeamAgent,
    Token,
    TokenVerdict,
    ToolCall,
    User,
    Workflow,
    Workspace,
    WorkspaceMember,
)
from orchestrator.runtime import runtime
from orchestrator.memory import index_memory_note, retrieve_memory
from orchestrator.research import build_report, run_research
from orchestrator.schemas import (
    AgentCreate,
    AgentRead,
    AgentLessonDecision,
    AgentLessonRead,
    AgentUpdate,
    AuthLogin,
    AuthRead,
    AuthRegister,
    AuthSessionRead,
    UserUpdate,
    AccountDelete,
    PasswordResetRequest,
    PasswordResetRequestRead,
    PasswordResetConfirm,
    EmailVerificationConfirm,
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    ArtifactCreate,
    ArtifactRead,
    ConnectionCreate,
    ConnectionDiscover,
    ConnectionDiscovery,
    ConnectionRead,
    DialogueMaterial,
    EventRead,
    FileAssetRead,
    HumanMessage,
    GitHubConnect,
    GitHubCodeSearch,
    GitHubFileQuery,
    GitHubRepositoryQuery,
    GitHubSyncRead,
    TwitterConnect,
    TwitterAuthSync,
    TwitterOAuthStartRead,
    TwitterSyncRead,
    GoogleModelOAuthStartRead,
    ContextConnectorConnect,
    ContextConnectorOAuthStartRead,
    ContextConnectorSyncRead,
    ModeChange,
    MemoryCreate,
    MemoryRead,
    MemoryUpdate,
    MemorySearch,
    MemorySearchResult,
    MCPInstall,
    MCPToolRead,
    RunCreate,
    RunBudgetUpdate,
    RunBranchCreate,
    ImpersonatedAgentMessage,
    ReplayShareRead,
    ReplayForkCreate,
    ReplayForkRead,
    PublicReplayRead,
    RunMetaUpdate,
    RunParticipantsUpdate,
    RunMemoryMerge,
    RunRead,
    RunCheckpointRead,
    RunCommandRead,
    ResearchCreate,
    ResearchRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    ToolCallCreate,
    ToolCallRead,
    TeamCreate,
    TeamRead,
    TeamMemberAdd,
    TokenCreate,
    TokenRead,
    TokenUpdate,
    TokenVerdictCreate,
    TokenVerdictRead,
    MarketObservationCreate,
    MarketObservationCapture,
    MarketObservationRead,
    DecisionReplayCreate,
    DecisionEvaluationRead,
    PaperTradeCreate,
    PaperTradeClose,
    PaperTradeRead,
    DecisionQualityRead,
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceOwnershipTransfer,
    WorkspaceMemberRead,
    WorkspaceRead,
    UserRead,
    WalletNonceRead,
    WalletVerify,
    WorkflowCreate,
    WorkflowRead,
    WorkflowUpdate,
    WorkflowValidation,
)
from orchestrator.security import secret_codec, secret_fingerprint
from orchestrator.config import get_settings
from orchestrator.files import extract_text, persist_file, remove_file, safe_name
from orchestrator.providers import (
    discover_anthropic_models,
    discover_models,
    discover_tabitoken_models,
)
from orchestrator.mailer import send_email_verification, send_password_reset
from orchestrator.network_security import validate_outbound_url
from orchestrator.paper_trading import (
    close_paper_position,
    evaluate_historical_decision,
    open_paper_position,
)

router = APIRouter()


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        "orbit_session", token, httponly=True,
        secure=get_settings().app_env == "production", samesite="lax",
        expires=expires_at, path="/",
    )


def user_read(user: User) -> UserRead:
    """Expose configuration-backed admin status without persisting config secrets."""
    return UserRead.model_validate(user).model_copy(update={"is_superuser": is_superuser(user)})


async def require(session: AsyncSession, model: type, item_id: str):
    item = await session.get(model, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    workspace_id = getattr(item, "workspace_id", None)
    if isinstance(item, Workspace):
        workspace_id = item.id
    elif isinstance(item, Run):
        team = await session.get(Team, item.team_id)
        workspace_id = team.workspace_id if team else None
    elif not workspace_id and getattr(item, "run_id", None):
        run = await session.get(Run, item.run_id)
        if run:
            team = await session.get(Team, run.team_id)
            workspace_id = team.workspace_id if team else None
    if workspace_id:
        await ensure_workspace_access(session, workspace_id)
    return item


async def require_verified_user(session: AsyncSession) -> User | None:
    """Model work is billable/expensive, so new accounts must confirm email first."""
    if not get_settings().email_verification_required:
        return None
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await require(session, User, user_id)
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Confirm your email before starting a run")
    return user


async def consume_daily_quota(session: AsyncSession, *, kind: str) -> None:
    """Cap model spend per account per UTC day. Call after validation so a rejected request costs nothing."""
    settings = get_settings()
    user_id = current_user_id.get()
    if not user_id:
        return
    user = await session.get(User, user_id)
    if not user or is_superuser(user):
        return
    # Anonymous guests get a smaller quota; linking a wallet lifts them to the full one.
    guest = user.is_guest and not user.wallet_address
    if kind == "research":
        limit = settings.guest_daily_research_limit if guest else settings.daily_research_limit
    else:
        limit = settings.guest_daily_message_limit if guest else settings.daily_message_limit
    if limit <= 0:
        return
    day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    usage = await session.scalar(select(DailyUsage).where(DailyUsage.day == day, DailyUsage.user_id == user_id))
    if usage is None:
        # Column defaults only land at flush time, so seed the counters here:
        # this row is read back before it is ever written.
        usage = DailyUsage(day=day, user_id=user_id, research_count=0, message_count=0)
        session.add(usage)
    used = usage.research_count if kind == "research" else usage.message_count
    if used >= limit:
        noun = "analyses" if kind == "research" else "messages"
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit reached: {limit} {noun} per day. The quota resets at 00:00 UTC.",
            headers={"Retry-After": "3600"},
        )
    if kind == "research":
        usage.research_count = used + 1
    else:
        usage.message_count = used + 1
    await session.commit()


async def issue_email_verification(session: AsyncSession, user: User) -> str:
    raw_token = secrets.token_urlsafe(40)
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=get_settings().email_verification_ttl_minutes),
        )
    )
    await session.commit()
    return raw_token


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    await session.execute(text("SELECT 1"))
    active_jobs = sum(1 for job in runtime._jobs.values() if not job.done())
    queued_runs = int(
        await session.scalar(select(func.count(Run.id)).where(Run.status.in_([RunStatus.created, RunStatus.running]))) or 0
    )
    return {
        "status": "ok",
        "database": "ready",
        "runtime": "ready",
        "active_jobs": active_jobs,
        "queue_depth": queued_runs,
        "worker_id": runtime.worker_id,
    }


@router.get("/auth/capabilities")
async def auth_capabilities() -> dict[str, object]:
    """Public, secret-free deployment capability map for honest UI states."""
    settings = get_settings()
    google_context = bool(
        settings.google_context_oauth_client_id
        and settings.google_context_oauth_client_secret
    )
    return {
        "auth": {
            "password": True,
            "google": bool(settings.google_auth_client_id and settings.google_auth_client_secret),
            "twitter": bool(settings.twitter_oauth_client_id and settings.twitter_oauth_client_secret),
            "password_recovery_email": bool(settings.smtp_host and settings.smtp_from),
        },
        "connectors": {
            "github": bool(settings.github_oauth_client_id and settings.github_oauth_client_secret),
            "notion": bool(settings.notion_oauth_client_id and settings.notion_oauth_client_secret),
            "slack": bool(settings.slack_oauth_client_id and settings.slack_oauth_client_secret),
            "google-drive": google_context,
            "youtube": google_context,
            "twitter": bool(settings.twitter_oauth_client_id),
            "google-model": bool(
                settings.google_model_oauth_client_id
                and settings.google_model_oauth_client_secret
            ),
        },
        "research": {
            "web": True,
            "youtube": True,
            "tiktok": True,
            "instagram": True,
            "onchain": True,
            "enhanced_web": bool(settings.research_brave_api_key),
            "enhanced_youtube": bool(settings.research_youtube_api_key),
            "enhanced_tiktok": bool(settings.research_tiktok_access_token),
            "enhanced_instagram": bool(
                settings.research_instagram_access_token
                and settings.research_instagram_account_id
            ),
        },
    }


@router.post("/files", response_model=FileAssetRead, status_code=201)
async def upload_file_asset(
    workspace_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    await ensure_workspace_access(session, workspace_id, write=True)
    if not await session.get(Workspace, workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    data = await file.read(get_settings().max_file_bytes + 1)
    if len(data) > get_settings().max_file_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the 25 MB limit")
    name = safe_name(file.filename or "material.txt")
    try:
        extracted, metadata = extract_text(name, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asset = FileAsset(
        workspace_id=workspace_id,
        uploaded_by_user_id=current_user_id.get(),
        name=name,
        mime_type=file.content_type or "application/octet-stream",
        size=len(data),
        sha256="pending",
        storage_path="pending",
        extracted_text=extracted,
        metadata_=metadata,
    )
    session.add(asset)
    await session.flush()
    try:
        path, digest = persist_file(asset.id, name, data)
        asset.storage_path = path
        asset.sha256 = digest
        await session.commit()
        await session.refresh(asset)
        return asset
    except Exception:
        await session.rollback()
        if asset.storage_path != "pending":
            remove_file(asset.storage_path)
        raise


@router.get("/files", response_model=list[FileAssetRead])
async def list_file_assets(workspace_id: str, session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (await session.scalars(select(FileAsset).where(FileAsset.workspace_id == workspace_id).order_by(FileAsset.created_at.desc()))).all()
    )


@router.delete("/files/{asset_id}", status_code=204)
async def delete_file_asset(asset_id: str, session: AsyncSession = Depends(get_session)):
    asset = await require(session, FileAsset, asset_id)
    path = asset.storage_path
    await session.delete(asset)
    await session.commit()
    remove_file(path)


@router.post("/auth/register", response_model=AuthRead, status_code=201)
async def register(
    payload: AuthRegister, request: Request, response: Response, session: AsyncSession = Depends(get_session)
):
    settings = get_settings()
    if settings.app_env == "production" and settings.email_verification_required and not settings.smtp_host:
        raise HTTPException(status_code=503, detail="Registration is temporarily unavailable while email delivery is offline")
    email = payload.email.strip().lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = User(email=email, display_name=payload.display_name.strip(), password_hash=password_hash)
    session.add(user)
    await session.flush()
    auth_session, token = await create_auth_session(session, user, request)
    set_session_cookie(response, token, auth_session.expires_at)
    await session.refresh(user)
    verification_token = await issue_email_verification(session, user)
    delivered = await send_email_verification(user.email, verification_token)
    if get_settings().app_env == "production" and not delivered:
        raise HTTPException(status_code=503, detail="Email delivery is temporarily unavailable")
    return AuthRead(
        token=token,
        expires_at=auth_session.expires_at,
        user=user_read(user),
        verification_required=get_settings().email_verification_required,
        debug_verification_token=verification_token if get_settings().app_env == "development" else None,
    )


@router.post("/auth/guest", response_model=AuthRead, status_code=201)
async def create_guest(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    """Open the site without a form: every visitor gets an isolated anonymous account."""
    settings = get_settings()
    if not settings.guest_access_enabled:
        raise HTTPException(status_code=403, detail="Guest access is disabled")
    address = request_client_address(request) or "unknown"
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent = await session.scalar(
        select(func.count(AuthSession.id))
        .join(User, User.id == AuthSession.user_id)
        .where(User.is_guest.is_(True), AuthSession.ip_address == address, AuthSession.created_at >= since)
    )
    if (recent or 0) >= settings.guest_max_per_ip_per_day:
        raise HTTPException(status_code=429, detail="Too many new guest sessions from this network. Try again later", headers={"Retry-After": "3600"})
    user = User(
        email=f"guest-{secrets.token_hex(8)}@guest.orbit",
        display_name="Guest",
        password_hash=hash_password(secrets.token_urlsafe(32)),
        is_guest=True,
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    auth_session, token = await create_auth_session(session, user, request)
    set_session_cookie(response, token, auth_session.expires_at)
    await session.refresh(user)
    return AuthRead(token=token, expires_at=auth_session.expires_at, user=user_read(user))


@router.post("/auth/wallet/nonce", response_model=WalletNonceRead)
async def wallet_nonce() -> WalletNonceRead:
    now = datetime.now(timezone.utc)
    return WalletNonceRead(
        nonce=wallet_auth.issue_nonce(now),
        domain=wallet_auth.expected_domain(),
        uri=get_settings().public_url.rstrip("/"),
        chain_id=wallet_auth.ROBINHOOD_CHAIN_ID,
        issued_at=now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        expires_at=(now + wallet_auth.NONCE_TTL).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    )


@router.post("/auth/wallet/verify", response_model=AuthRead)
async def wallet_verify(
    payload: WalletVerify, request: Request, response: Response, session: AsyncSession = Depends(get_session)
):
    """Link the wallet to the current account, or sign in to the account it is already linked to."""
    try:
        address, nonce = wallet_auth.verify_signed_message(payload.message, payload.signature)
    except wallet_auth.WalletAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    session.add(WalletNonce(nonce=nonce))
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This sign-in request was already used. Try again") from exc
    await session.execute(delete(WalletNonce).where(WalletNonce.created_at < datetime.now(timezone.utc) - timedelta(days=1)))
    owner = await session.scalar(select(User).where(User.wallet_address == address))
    current_id = current_user_id.get()
    current = await session.get(User, current_id) if current_id else None
    if owner:
        if not owner.enabled:
            raise HTTPException(status_code=403, detail="This account is disabled")
        user = owner
    elif current:
        current.wallet_address = address
        user = current
    else:
        user = User(
            email=f"{address}@wallet.orbit",
            display_name=f"{address[:6]}...{address[-4:]}",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            email_verified=True,
            wallet_address=address,
        )
        session.add(user)
    await session.flush()
    auth_session, token = await create_auth_session(session, user, request)
    set_session_cookie(response, token, auth_session.expires_at)
    await session.refresh(user)
    return AuthRead(token=token, expires_at=auth_session.expires_at, user=user_read(user))


@router.delete("/auth/wallet", response_model=UserRead)
async def unlink_wallet(session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await require(session, User, user_id)
    if not user.wallet_address:
        return user_read(user)
    if user.email.endswith("@wallet.orbit"):
        raise HTTPException(status_code=409, detail="This account signs in with the wallet, so it cannot be disconnected")
    user.wallet_address = None
    await session.commit()
    await session.refresh(user)
    return user_read(user)


@router.get("/auth/google/start")
async def google_auth_start() -> dict[str, str]:
    try:
        return {
            "authorization_url": create_google_auth_authorization(),
            "callback_url": google_auth_callback_url(),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/auth/google/callback")
async def google_auth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    destination = f"{settings.public_url.rstrip('/')}/"
    if error:
        return RedirectResponse(f"{destination}?google_auth=denied", status_code=303)
    try:
        verify_google_auth_state(state)
        profile = await exchange_google_auth_code(code)
        user = await session.scalar(select(User).where(User.email == profile["email"]))
        if not user:
            # OAuth-only accounts can later set a password through the normal
            # recovery flow. A generated value is never returned or persisted raw.
            user = User(
                email=profile["email"],
                display_name=profile["display_name"],
                password_hash=hash_password(secrets.token_urlsafe(48)),
                email_verified=True,
            )
            session.add(user)
            await session.flush()
        elif not user.enabled:
            raise ValueError("This Orbit account is disabled")
        auth_session, token = await create_auth_session(session, user)
        response = RedirectResponse(f"{destination}?google_auth=success", status_code=303)
        set_session_cookie(response, token, auth_session.expires_at)
        return response
    except Exception:
        return RedirectResponse(f"{destination}?google_auth=failed", status_code=303)


@router.get("/auth/twitter/start")
async def twitter_auth_start() -> dict[str, str]:
    try:
        return {
            "authorization_url": create_twitter_login_authorization(),
            "callback_url": twitter_login_callback_url(),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/auth/twitter/callback")
async def twitter_auth_callback(
    request: Request,
    response: Response,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    destination = f"{get_settings().public_url.rstrip('/')}/"
    if error or not code or not state:
        return RedirectResponse(f"{destination}?twitter_auth=denied", status_code=303)
    try:
        state_data = verify_twitter_login_state(state)
        token_data = await exchange_twitter_code(
            code,
            str(state_data["verifier"]),
            redirect_uri=twitter_login_callback_url(),
        )
        access_token = str(token_data["access_token"])
        twitter_data = await fetch_twitter_context(access_token)
        profile = twitter_data["profile"]
        twitter_user_id = str(profile["id"])
        email = str(profile.get("confirmed_email") or "").strip().lower()
        user = await session.scalar(select(User).where(User.twitter_user_id == twitter_user_id))
        if user is None and email:
            user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            if not email:
                raise ValueError("X did not return a confirmed email; add the users.email scope")
            user = User(
                email=email,
                display_name=str(profile.get("name") or profile.get("username") or email.split("@", 1)[0])[:120],
                password_hash=hash_password(secrets.token_urlsafe(48)),
                email_verified=True,
            )
            session.add(user)
            await session.flush()
        elif not user.enabled:
            raise ValueError("This Orbit account is disabled")
        if user.twitter_user_id and user.twitter_user_id != twitter_user_id:
            raise ValueError("This Orbit account is already linked to another X account")
        credentials = {
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "bearer"),
            "expires_at": (
                (datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))).isoformat()
                if token_data.get("expires_in") else None
            ),
        }
        user.twitter_user_id = twitter_user_id
        user.twitter_profile = profile
        user.twitter_credentials = secret_codec.encrypt(json.dumps(credentials, separators=(",", ":")))
        if email and not user.email_verified:
            user.email_verified = True
        await session.flush()
        auth_session, token = await create_auth_session(session, user, request)
        redirect = RedirectResponse(f"{destination}?twitter_auth=success", status_code=303)
        set_session_cookie(redirect, token, auth_session.expires_at)
        return redirect
    except Exception:
        await session.rollback()
        return RedirectResponse(f"{destination}?twitter_auth=failed", status_code=303)


@router.post("/auth/login", response_model=AuthRead)
async def login(
    payload: AuthLogin, request: Request, response: Response, session: AsyncSession = Depends(get_session)
):
    user = await session.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash) or not user.enabled:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    auth_session, token = await create_auth_session(session, user, request)
    set_session_cookie(response, token, auth_session.expires_at)
    return AuthRead(
        token=token,
        expires_at=auth_session.expires_at,
        user=user_read(user),
        verification_required=get_settings().email_verification_required and not user.email_verified,
    )


@router.get("/auth/me", response_model=UserRead)
async def auth_me(session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_read(await require(session, User, user_id))


@router.post("/auth/email-verification/request", status_code=202)
async def request_email_verification(session: AsyncSession = Depends(get_session)) -> dict[str, str | None]:
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await require(session, User, user_id)
    if user.email_verified:
        return {"message": "Email is already confirmed", "debug_token": None}
    raw_token = await issue_email_verification(session, user)
    delivered = await send_email_verification(user.email, raw_token)
    if get_settings().app_env == "production" and not delivered:
        raise HTTPException(status_code=503, detail="Email delivery is temporarily unavailable")
    return {
        "message": "Confirmation instructions have been sent.",
        "debug_token": raw_token if get_settings().app_env == "development" else None,
    }


@router.post("/auth/email-verification/confirm", status_code=204)
async def confirm_email_verification(
    payload: EmailVerificationConfirm, session: AsyncSession = Depends(get_session)
):
    value = await session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash(payload.token))
    )
    if not value or value.used_at is not None:
        raise HTTPException(status_code=400, detail="Verification token is invalid or already used")
    expires_at = value.expires_at if value.expires_at.tzinfo else value.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification token has expired")
    user = await session.get(User, value.user_id)
    if not user or not user.enabled:
        raise HTTPException(status_code=400, detail="Verification token is invalid")
    user.email_verified = True
    value.used_at = datetime.now(timezone.utc)
    await session.commit()
    return None


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request, response: Response, authorization: str = Header(default=""), session: AsyncSession = Depends(get_session)
):
    raw_token = authorization.removeprefix("Bearer ").strip() or request.cookies.get("orbit_session", "")
    if raw_token:
        value = await session.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token)))
        if value:
            await session.delete(value)
            await session.commit()
    response.delete_cookie("orbit_session", path="/")
    return None


@router.patch("/auth/me", response_model=UserRead)
async def update_current_user(payload: UserUpdate, session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await require(session, User, user_id)
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.new_password is not None:
        if not payload.current_password or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=403, detail="Current password is incorrect")
        try:
            user.password_hash = hash_password(payload.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        # A password change is a security boundary: revoke every other login.
        current_hash = ""
        # The current request token is intentionally unavailable here; require a
        # fresh sign-in after the change instead of accidentally preserving it.
        sessions = list((await session.scalars(select(AuthSession).where(AuthSession.user_id == user.id))).all())
        for value in sessions:
            if value.token_hash != current_hash:
                await session.delete(value)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/auth/sessions", response_model=list[AuthSessionRead])
async def list_auth_sessions(request: Request, authorization: str = Header(default=""), session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    raw_token = authorization.removeprefix("Bearer ").strip() or request.cookies.get("orbit_session", "")
    current_hash = token_hash(raw_token) if raw_token else ""
    values = list((await session.scalars(select(AuthSession).where(AuthSession.user_id == user_id).order_by(AuthSession.created_at.desc()))).all())
    return [AuthSessionRead.model_validate(value).model_copy(update={"current": value.token_hash == current_hash}) for value in values]


@router.delete("/auth/sessions/{session_id}", status_code=204)
async def revoke_auth_session(session_id: str, session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    value = await session.get(AuthSession, session_id)
    if not value or value.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    await session.delete(value)
    await session.commit()
    return None


@router.post("/auth/password-reset/request", response_model=PasswordResetRequestRead, status_code=202)
async def request_password_reset(payload: PasswordResetRequest, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(User.email == payload.email.strip().lower(), User.enabled.is_(True)))
    debug_token = None
    if user:
        raw_token = secrets.token_urlsafe(40)
        session.add(PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ))
        await session.commit()
        try:
            await send_password_reset(user.email, raw_token)
        except Exception:
            # Keep the response enumeration-safe. Production readiness reports
            # missing SMTP separately; local development exposes a test token.
            pass
        if get_settings().app_env == "development":
            debug_token = raw_token
    return PasswordResetRequestRead(
        message="If the account exists, password reset instructions have been sent.",
        debug_token=debug_token,
    )


@router.post("/auth/password-reset/confirm", status_code=204)
async def confirm_password_reset(payload: PasswordResetConfirm, session: AsyncSession = Depends(get_session)):
    value = await session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash(payload.token)))
    if not value or value.used_at is not None:
        raise HTTPException(status_code=400, detail="Reset token is invalid or already used")
    expires_at = value.expires_at if value.expires_at.tzinfo else value.expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token has expired")
    user = await session.get(User, value.user_id)
    if not user or not user.enabled:
        raise HTTPException(status_code=400, detail="Reset token is invalid")
    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    value.used_at = datetime.now(timezone.utc)
    sessions = list((await session.scalars(select(AuthSession).where(AuthSession.user_id == user.id))).all())
    for auth_session in sessions:
        await session.delete(auth_session)
    await session.commit()
    return None


@router.delete("/auth/me", status_code=204)
async def delete_current_account(payload: AccountDelete, session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = await require(session, User, user_id)
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Password is incorrect")
    owned = list((await session.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id, WorkspaceMember.role == "owner"))).all())
    for membership in owned:
        others = list((await session.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == membership.workspace_id, WorkspaceMember.user_id != user.id))).all())
        if others:
            raise HTTPException(status_code=409, detail="Transfer ownership of shared workspaces before deleting the account")
    for membership in owned:
        workspace = await session.get(Workspace, membership.workspace_id)
        if workspace:
            # Teams can point at one of the workspace agents as supervisor.
            # Clear those references before the workspace cascade deletes the
            # agents; PostgreSQL otherwise rejects the ORM's delete ordering.
            teams = list((await session.scalars(select(Team).where(Team.workspace_id == workspace.id))).all())
            for team in teams:
                team.supervisor_agent_id = None
            await session.flush()
            agent_ids = list(
                (await session.scalars(select(Agent.id).where(Agent.workspace_id == workspace.id))).all()
            )
            run_ids = list(
                (
                    await session.scalars(
                        select(Run.id).join(Team, Team.id == Run.team_id).where(Team.workspace_id == workspace.id)
                    )
                ).all()
            )
            task_ids = list(
                (await session.scalars(select(Task.id).where(Task.run_id.in_(run_ids)))).all()
            ) if run_ids else []
            if agent_ids:
                await session.execute(update(Task).where(Task.assigned_agent_id.in_(agent_ids)).values(assigned_agent_id=None))
                await session.execute(update(Artifact).where(Artifact.created_by_agent_id.in_(agent_ids)).values(created_by_agent_id=None))
                await session.execute(update(Approval).where(Approval.requested_by_agent_id.in_(agent_ids)).values(requested_by_agent_id=None))
                await session.execute(update(TaskAttempt).where(TaskAttempt.agent_id.in_(agent_ids)).values(agent_id=None))
                await session.execute(update(ToolCall).where(ToolCall.agent_id.in_(agent_ids)).values(agent_id=None))
            if task_ids:
                # Legacy schemas predate ON DELETE actions on several task
                # references. Break those links explicitly before the cascade.
                await session.execute(update(Task).where(Task.parent_task_id.in_(task_ids)).values(parent_task_id=None))
                await session.execute(update(RunEvent).where(RunEvent.task_id.in_(task_ids)).values(task_id=None))
                await session.execute(update(Artifact).where(Artifact.task_id.in_(task_ids)).values(task_id=None))
                await session.execute(update(Approval).where(Approval.task_id.in_(task_ids)).values(task_id=None))
                await session.execute(update(RunCommand).where(RunCommand.task_id.in_(task_ids)).values(task_id=None))
                await session.execute(update(ToolCall).where(ToolCall.task_id.in_(task_ids)).values(task_id=None))
            # Let PostgreSQL execute the workspace-wide CASCADE as one
            # statement. ORM row-by-row deletion can remove agents before
            # their run tasks and trip otherwise valid cross-branch FKs.
            await session.execute(delete(Workspace).where(Workspace.id == workspace.id))
    await session.delete(user)
    await session.commit()
    return None


def _day_key(value: object) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _pct_change(current: float, previous: float) -> float | None:
    """None means there is no prior period to compare against, which the UI must not show as 0%."""
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


@router.get("/admin/overview")
async def admin_overview(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """One bounded query surface for the owner dashboard; never leaks to workspace roles."""
    await require_superuser(session)
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_7 = today - timedelta(days=6)
    since_30 = today - timedelta(days=29)
    month_start = today - timedelta(days=29)

    total_users = int(await session.scalar(select(func.count(User.id))) or 0)
    registrations_7 = int(await session.scalar(select(func.count(User.id)).where(User.created_at >= since_7)) or 0)
    registrations_30 = int(await session.scalar(select(func.count(User.id)).where(User.created_at >= since_30)) or 0)
    dau = int(await session.scalar(select(func.count(User.id)).where(User.last_seen_at >= now - timedelta(days=1))) or 0)
    live_sessions = int(
        await session.scalar(select(func.count(func.distinct(AuthSession.user_id))).where(AuthSession.expires_at > now)) or 0
    )
    runs_today = int(await session.scalar(select(func.count(Run.id)).where(Run.created_at >= today)) or 0)
    spend_month = int(
        await session.scalar(select(func.coalesce(func.sum(Run.total_cost_micros), 0)).where(Run.created_at >= month_start)) or 0
    )
    total_runs = int(await session.scalar(select(func.count(Run.id))) or 0)
    failed_runs = int(await session.scalar(select(func.count(Run.id)).where(Run.status == RunStatus.failed)) or 0)
    activated_users = int(
        await session.scalar(
            select(func.count(func.distinct(WorkspaceMember.user_id)))
            .select_from(ProviderConnection)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == ProviderConnection.workspace_id)
            .where(WorkspaceMember.role == "owner", ProviderConnection.enabled.is_(True))
        )
        or 0
    )

    async def visit_window(start: datetime, end: datetime | None) -> tuple[int, int, int, int]:
        clauses = [DailyVisit.day >= start]
        if end is not None:
            clauses.append(DailyVisit.day < end)
        row = (
            await session.execute(
                select(
                    # A visitor can return on several UTC days. Count the stable
                    # privacy hash once for the selected period, not once per day.
                    func.count(func.distinct(DailyVisit.visitor_hash)),
                    func.coalesce(func.sum(DailyVisit.request_count), 0),
                    # This is a daily visit with one request, not a conventional
                    # analytics "bounce". The UI names it accordingly.
                    func.coalesce(func.sum(case((DailyVisit.request_count <= 1, 1), else_=0)), 0),
                    func.count(DailyVisit.id),
                ).where(*clauses)
            )
        ).one()
        return int(row[0] or 0), int(row[1] or 0), int(row[2] or 0), int(row[3] or 0)

    visitors_7, requests_7, single_request_visits_7, visit_days_7 = await visit_window(since_7, None)
    visitors_prev, requests_prev, single_request_visits_prev, visit_days_prev = await visit_window(today - timedelta(days=13), since_7)
    bounce_rate_7 = round(single_request_visits_7 / visit_days_7 * 100, 1) if visit_days_7 else 0.0
    bounce_rate_prev = round(single_request_visits_prev / visit_days_prev * 100, 1) if visit_days_prev else 0.0

    registration_rows = (
        await session.execute(
            select(func.date(User.created_at), func.count(User.id))
            .where(User.created_at >= since_30)
            .group_by(func.date(User.created_at))
        )
    ).all()
    activity_rows = (
        await session.execute(
            select(func.date(DailyVisit.day), func.count(DailyVisit.id))
            .where(DailyVisit.day >= since_30)
            .group_by(func.date(DailyVisit.day))
        )
    ).all()
    login_rows = (
        await session.execute(
            select(func.date(AuthSession.created_at), func.count(AuthSession.id))
            .where(AuthSession.created_at >= since_30)
            .group_by(func.date(AuthSession.created_at))
        )
    ).all()
    registrations = {_day_key(day): int(count) for day, count in registration_rows}
    activity = {_day_key(day): int(count) for day, count in activity_rows}
    logins = {_day_key(day): int(count) for day, count in login_rows}
    timeline = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        key = day.date().isoformat()
        timeline.append({"day": key, "registrations": registrations.get(key, 0), "active": activity.get(key, 0), "logins": logins.get(key, 0)})

    run_stats_rows = (
        await session.execute(
            select(
                WorkspaceMember.user_id,
                func.count(Run.id),
                func.coalesce(func.sum(Run.total_cost_micros), 0),
                func.coalesce(func.sum(Run.total_input_tokens), 0),
            )
            .select_from(WorkspaceMember)
            .join(Team, Team.workspace_id == WorkspaceMember.workspace_id)
            .join(Run, Run.team_id == Team.id)
            .where(WorkspaceMember.role == "owner")
            .group_by(WorkspaceMember.user_id)
        )
    ).all()
    run_stats = {row[0]: {"runs": int(row[1]), "cost_micros": int(row[2]), "input_tokens": int(row[3])} for row in run_stats_rows}
    login_rows_by_user = (
        await session.execute(select(AuthSession.user_id, func.max(AuthSession.created_at)).group_by(AuthSession.user_id))
    ).all()
    last_login = {row[0]: row[1] for row in login_rows_by_user}
    users = list((await session.scalars(select(User).order_by(User.created_at.desc()).limit(200))).all())
    user_rows = [
        {
            "id": item.id,
            "email": item.email,
            "display_name": item.display_name,
            "enabled": item.enabled,
            "is_superuser": is_superuser(item),
            "email_verified": item.email_verified,
            "created_at": item.created_at,
            "last_seen_at": item.last_seen_at,
            "last_login_at": last_login.get(item.id),
            **run_stats.get(item.id, {"runs": 0, "cost_micros": 0, "input_tokens": 0}),
        }
        for item in users
    ]
    recent_rows = (
        await session.execute(
            select(Run, Team, User.email)
            .join(Team, Team.id == Run.team_id)
            .outerjoin(
                WorkspaceMember,
                (WorkspaceMember.workspace_id == Team.workspace_id) & (WorkspaceMember.role == "owner"),
            )
            .outerjoin(User, User.id == WorkspaceMember.user_id)
            .order_by(Run.created_at.desc())
            .limit(30)
        )
    ).all()
    recent_runs = [
        {"id": run.id, "goal": run.goal, "status": run.status.value, "created_at": run.created_at, "cost_micros": run.total_cost_micros, "owner_email": email}
        for run, _team, email in recent_rows
    ]
    token_rows = (
        await session.execute(
            select(Token.symbol, Token.name, Token.address, func.count(TokenVerdict.id))
            .outerjoin(TokenVerdict, TokenVerdict.token_id == Token.id)
            .group_by(Token.id, Token.symbol, Token.name, Token.address)
            .order_by(func.count(TokenVerdict.id).desc(), Token.updated_at.desc())
            .limit(10)
        )
    ).all()
    verdict_rows = (
        await session.execute(select(TokenVerdict.verdict, func.count(TokenVerdict.id)).group_by(TokenVerdict.verdict))
    ).all()
    return {
        "summary": {
            "total_users": total_users, "registrations_7": registrations_7, "registrations_30": registrations_30,
            "dau": dau, "live_sessions": live_sessions, "runs_today": runs_today, "spend_month_micros": spend_month,
            "activation_users": activated_users, "activation_rate": round(activated_users / total_users, 4) if total_users else 0,
            "total_runs": total_runs, "failed_runs": failed_runs,
            "failure_rate": round(failed_runs / total_runs, 4) if total_runs else 0,
            "visitors_7": visitors_7, "visitors_delta": _pct_change(visitors_7, visitors_prev),
            "requests_7": requests_7, "requests_delta": _pct_change(requests_7, requests_prev),
            "bounce_rate_7": bounce_rate_7,
            "bounce_delta": round(bounce_rate_7 - bounce_rate_prev, 1) if visitors_prev else None,
        },
        "timeline": timeline,
        "users": user_rows,
        "recent_runs": recent_runs,
        "top_tokens": [
            {"symbol": symbol, "name": name, "address": address, "verdicts": int(count)}
            for symbol, name, address, count in token_rows
        ],
        "verdict_distribution": {str(verdict): int(count) for verdict, count in verdict_rows},
    }


@router.patch("/admin/users/{user_id}", response_model=UserRead)
async def admin_update_user(user_id: str, payload: AdminUserUpdate, session: AsyncSession = Depends(get_session)):
    admin = await require_superuser(session)
    user = await require(session, User, user_id)
    if user.id == admin.id and not payload.enabled:
        raise HTTPException(status_code=422, detail="You cannot disable your own administrator account")
    user.enabled = payload.enabled
    await session.commit()
    await session.refresh(user)
    return user_read(user)


@router.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(payload: WorkspaceCreate, session: AsyncSession = Depends(get_session)):
    workspace = Workspace(**payload.model_dump())
    session.add(workspace)
    await session.flush()
    user_id = current_user_id.get()
    if user_id:
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner"))
    await session.commit()
    await session.refresh(workspace)
    return workspace


@router.get("/workspaces", response_model=list[WorkspaceRead])
async def list_workspaces(session: AsyncSession = Depends(get_session)):
    user_id = current_user_id.get()
    query = select(Workspace).order_by(Workspace.created_at.desc())
    if user_id:
        query = query.join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id).where(
            WorkspaceMember.user_id == user_id
        )
    return list((await session.scalars(query)).all())


@router.get("/workspaces/{workspace_id}/decision-quality", response_model=DecisionQualityRead)
async def workspace_decision_quality(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Show retrospective agent calibration; never use it to alter a live run."""
    await ensure_workspace_access(session, workspace_id)
    pairs = list(
        (
            await session.execute(
                select(DecisionEvaluation, TokenVerdict)
                .join(TokenVerdict, DecisionEvaluation.verdict_id == TokenVerdict.id)
                .join(Token, DecisionEvaluation.token_id == Token.id)
                .where(
                    Token.workspace_id == workspace_id,
                    DecisionEvaluation.status == "complete",
                    DecisionEvaluation.benchmark_return_pct.is_not(None),
                )
                .order_by(DecisionEvaluation.created_at.desc())
                .limit(500)
            )
        ).all()
    )
    run_ids = {verdict.run_id for _, verdict in pairs if verdict.run_id}
    signal_artifacts = []
    if run_ids:
        signal_artifacts = list(
            (
                await session.scalars(
                    select(Artifact)
                    .where(Artifact.run_id.in_(run_ids), Artifact.kind == "agent_signal")
                    .order_by(Artifact.created_at.desc())
                )
            ).all()
        )
    signals_by_run: dict[str, list[Artifact]] = {}
    for artifact in signal_artifacts:
        signals_by_run.setdefault(artifact.run_id, []).append(artifact)

    resolved = []
    for evaluation, verdict in pairs:
        latest_by_agent: dict[str, Artifact] = {}
        decision_at = _utc_datetime(verdict.created_at)
        for artifact in signals_by_run.get(verdict.run_id or "", []):
            if _utc_datetime(artifact.created_at) > decision_at:
                continue
            signal = dict(artifact.metadata_ or {})
            agent_id = str(signal.get("agent_id") or "")
            if agent_id and agent_id not in latest_by_agent:
                latest_by_agent[agent_id] = artifact
        resolved.append(
            {
                "evaluation_id": evaluation.id,
                "benchmark_return_pct": evaluation.benchmark_return_pct,
                "signals": [dict(item.metadata_ or {}) for item in latest_by_agent.values()],
            }
        )
    return build_agent_scorecards(resolved)


@router.get("/tokens", response_model=list[TokenRead])
async def list_tokens(
    workspace_id: str = Query(...),
    watchlist: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Return a workspace's token registry, optionally restricted to its watchlist."""
    await ensure_workspace_access(session, workspace_id)
    query = select(Token).where(Token.workspace_id == workspace_id)
    if watchlist is not None:
        query = query.where(Token.watchlist == watchlist)
    query = query.order_by(Token.watchlist.desc(), Token.updated_at.desc(), Token.created_at.desc())
    return list((await session.scalars(query)).all())


@router.post("/tokens", response_model=TokenRead, status_code=status.HTTP_201_CREATED)
async def create_token(payload: TokenCreate, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    token = Token(**payload.model_dump())
    session.add(token)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A token with this normalized address and chain is already registered in the workspace",
        ) from exc
    await session.refresh(token)
    return token


@router.get("/tokens/{token_id}", response_model=TokenRead)
async def get_token(token_id: str, session: AsyncSession = Depends(get_session)):
    return await require(session, Token, token_id)


@router.patch("/tokens/{token_id}", response_model=TokenRead)
async def update_token(
    token_id: str, payload: TokenUpdate, session: AsyncSession = Depends(get_session)
):
    token = await require(session, Token, token_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(token, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A token with this normalized address and chain is already registered in the workspace",
        ) from exc
    await session.refresh(token)
    return token


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(token_id: str, session: AsyncSession = Depends(get_session)):
    token = await require(session, Token, token_id)
    await session.delete(token)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def validate_token_verdict_links(
    session: AsyncSession, token: Token, payload: TokenVerdictCreate
) -> None:
    """Ensure optional evidence references belong to the token's workspace."""
    run = None
    if payload.run_id:
        run = await require(session, Run, payload.run_id)
        team = await session.get(Team, run.team_id)
        if not team or team.workspace_id != token.workspace_id:
            raise HTTPException(status_code=422, detail="Run and token must belong to the same workspace")
    if payload.artifact_id:
        artifact = await require(session, Artifact, payload.artifact_id)
        artifact_run = await session.get(Run, artifact.run_id)
        artifact_team = await session.get(Team, artifact_run.team_id) if artifact_run else None
        if not artifact_team or artifact_team.workspace_id != token.workspace_id:
            raise HTTPException(status_code=422, detail="Artifact and token must belong to the same workspace")
        if run and artifact.run_id != run.id:
            raise HTTPException(status_code=422, detail="Artifact must belong to the referenced run")


@router.get("/tokens/{token_id}/verdicts", response_model=list[TokenVerdictRead])
async def list_token_verdicts(token_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Token, token_id)
    return list(
        (
            await session.scalars(
                select(TokenVerdict)
                .where(TokenVerdict.token_id == token_id)
                .order_by(TokenVerdict.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/tokens/{token_id}/verdicts", response_model=TokenVerdictRead, status_code=status.HTTP_201_CREATED
)
async def create_token_verdict(
    token_id: str, payload: TokenVerdictCreate, session: AsyncSession = Depends(get_session)
):
    token = await require(session, Token, token_id)
    await validate_token_verdict_links(session, token, payload)
    verdict = TokenVerdict(token_id=token.id, **payload.model_dump())
    session.add(verdict)
    await session.commit()
    await session.refresh(verdict)
    return verdict


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _token_verdict(session: AsyncSession, token: Token, verdict_id: str) -> TokenVerdict:
    verdict = await session.scalar(
        select(TokenVerdict).where(TokenVerdict.id == verdict_id, TokenVerdict.token_id == token.id)
    )
    if not verdict:
        raise HTTPException(status_code=404, detail="Token verdict not found")
    return verdict


def _paper_trade_from_observation(trade: PaperTrade, observation: MarketObservation) -> None:
    opened = open_paper_position(
        price=observation.price,
        notional=trade.notional,
        fee_bps=trade.fee_bps,
        slippage_bps=trade.slippage_bps,
    )
    trade.status = "open"
    trade.quote_symbol = observation.quote_symbol
    trade.entry_observation_id = observation.id
    trade.entry_price = opened["entry_price"]
    trade.quantity = opened["quantity"]
    trade.fees_paid = opened["entry_fee"]
    trade.opened_at = observation.observed_at
    trade.config = {**dict(trade.config or {}), "entry_fee": opened["entry_fee"]}


async def _reconcile_pending_paper_trades(
    session: AsyncSession, token_id: str, observation: MarketObservation
) -> None:
    if observation.kind != "trade":
        return
    pending = list(
        (
            await session.scalars(
                select(PaperTrade).where(
                    PaperTrade.token_id == token_id,
                    PaperTrade.status == "pending",
                    PaperTrade.decision == "ENTER",
                    PaperTrade.created_at <= observation.observed_at,
                )
            )
        ).all()
    )
    for trade in pending:
        _paper_trade_from_observation(trade, observation)


@router.get("/tokens/{token_id}/market-observations", response_model=list[MarketObservationRead])
async def list_market_observations(
    token_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
):
    await require(session, Token, token_id)
    return list(
        (
            await session.scalars(
                select(MarketObservation)
                .where(MarketObservation.token_id == token_id)
                .order_by(MarketObservation.observed_at.desc())
                .limit(limit)
            )
        ).all()
    )


@router.post(
    "/tokens/{token_id}/market-observations",
    response_model=MarketObservationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_market_observation(
    token_id: str,
    payload: MarketObservationCreate,
    session: AsyncSession = Depends(get_session),
):
    token = await require(session, Token, token_id)
    observation = MarketObservation(
        token_id=token.id,
        **payload.model_dump(exclude={"payload"}),
        payload={**payload.payload, "ingest": "operator"},
    )
    session.add(observation)
    try:
        await session.flush()
        await _reconcile_pending_paper_trades(session, token.id, observation)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="This source observation is already stored") from exc
    await session.refresh(observation)
    return observation


@router.post(
    "/tokens/{token_id}/market-observations/capture",
    response_model=list[MarketObservationRead],
)
async def capture_market_observations(
    token_id: str,
    payload: MarketObservationCapture,
    session: AsyncSession = Depends(get_session),
):
    """Capture Robinhood Chain V3 swap candles without fabricating missing prices."""
    token = await require(session, Token, token_id)
    if token.asset_kind != "token":
        raise HTTPException(status_code=422, detail="On-chain candle capture supports fungible tokens only")
    try:
        result = await chain_tools.token_candles(
            token.address, blocks=payload.blocks, interval_blocks=payload.interval_blocks
        )
    except chain_tools.ChainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    source = "robinhood-chain-v3-swap"
    quote = str(result.get("paired_symbol") or "UNKNOWN")[:40]
    created: list[MarketObservation] = []
    for candle in result.get("candles") or []:
        timestamp = candle.get("closed_at")
        block = candle.get("last_swap_block")
        price = candle.get("close")
        if not isinstance(timestamp, int) or not isinstance(block, int) or not isinstance(price, (int, float)):
            continue
        source_ref = f"{result.get('pool')}:{block}:close"
        exists = await session.scalar(
            select(MarketObservation.id).where(
                MarketObservation.token_id == token.id,
                MarketObservation.source == source,
                MarketObservation.source_ref == source_ref,
            )
        )
        if exists:
            continue
        observation = MarketObservation(
            token_id=token.id,
            price=float(price),
            quote_symbol=quote,
            kind="trade",
            source=source,
            source_ref=source_ref,
            observed_at=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            payload={**candle, "pool": result.get("pool"), "history_complete": result.get("history_complete")},
        )
        session.add(observation)
        await session.flush()
        await _reconcile_pending_paper_trades(session, token.id, observation)
        created.append(observation)
    live_price = result.get("live_price_in_paired")
    if isinstance(live_price, (int, float)) and live_price > 0:
        source_ref = f"{result.get('pool')}:{result.get('to_block')}:slot0"
        exists = await session.scalar(
            select(MarketObservation.id).where(
                MarketObservation.token_id == token.id,
                MarketObservation.source == "robinhood-chain-v3-slot0",
                MarketObservation.source_ref == source_ref,
            )
        )
        if not exists:
            mark = MarketObservation(
                token_id=token.id,
                price=float(live_price),
                quote_symbol=quote,
                kind="mark",
                source="robinhood-chain-v3-slot0",
                source_ref=source_ref,
                observed_at=datetime.now(timezone.utc),
                payload={"pool": result.get("pool"), "block": result.get("to_block")},
            )
            session.add(mark)
            created.append(mark)
    await session.commit()
    for item in created:
        await session.refresh(item)
    return created


@router.get("/tokens/{token_id}/evaluations", response_model=list[DecisionEvaluationRead])
async def list_decision_evaluations(token_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Token, token_id)
    return list(
        (
            await session.scalars(
                select(DecisionEvaluation)
                .where(DecisionEvaluation.token_id == token_id)
                .order_by(DecisionEvaluation.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/tokens/{token_id}/evaluations",
    response_model=DecisionEvaluationRead,
    status_code=status.HTTP_201_CREATED,
)
async def evaluate_token_decision(
    token_id: str,
    payload: DecisionReplayCreate,
    session: AsyncSession = Depends(get_session),
):
    token = await require(session, Token, token_id)
    verdict = await _token_verdict(session, token, payload.verdict_id)
    window_end = _utc_datetime(verdict.created_at) + timedelta(seconds=payload.horizon_seconds)
    query = select(MarketObservation).where(
        MarketObservation.token_id == token.id,
        MarketObservation.kind == "trade",
        MarketObservation.observed_at >= verdict.created_at,
        MarketObservation.observed_at <= window_end,
    )
    if payload.source:
        query = query.where(MarketObservation.source == payload.source)
    observations = list((await session.scalars(query.order_by(MarketObservation.observed_at))).all())
    result = evaluate_historical_decision(
        decision=verdict.verdict,
        decision_at=verdict.created_at,
        observations=[
            {"id": item.id, "price": item.price, "kind": item.kind, "observed_at": item.observed_at}
            for item in observations
        ],
        horizon_seconds=payload.horizon_seconds,
        fee_bps=payload.fee_bps,
        slippage_bps=payload.slippage_bps,
        watch_band_pct=payload.watch_band_pct,
    )
    evaluation = DecisionEvaluation(
        token_id=token.id,
        verdict_id=verdict.id,
        decision=str(result["decision"]),
        status=str(result["status"]),
        outcome=str(result["outcome"]),
        horizon_seconds=payload.horizon_seconds,
        entry_observation_id=result.get("entry_observation_id"),
        exit_observation_id=result.get("exit_observation_id"),
        benchmark_return_pct=result.get("benchmark_return_pct"),
        strategy_return_pct=result.get("strategy_return_pct"),
        max_favorable_excursion_pct=result.get("max_favorable_excursion_pct"),
        max_adverse_excursion_pct=result.get("max_adverse_excursion_pct"),
        payload=result,
    )
    session.add(evaluation)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation


@router.get("/tokens/{token_id}/paper-trades", response_model=list[PaperTradeRead])
async def list_paper_trades(token_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Token, token_id)
    return list(
        (
            await session.scalars(
                select(PaperTrade)
                .where(PaperTrade.token_id == token_id)
                .order_by(PaperTrade.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/tokens/{token_id}/paper-trades",
    response_model=PaperTradeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_paper_trade(
    token_id: str,
    payload: PaperTradeCreate,
    session: AsyncSession = Depends(get_session),
):
    token = await require(session, Token, token_id)
    verdict = await _token_verdict(session, token, payload.verdict_id)
    decision = str(verdict.verdict or "WATCH").upper()
    protected = str((verdict.payload.get("protections") or {}).get("final_verdict") or decision).upper()
    if decision != "ENTER" or protected != "ENTER":
        raise HTTPException(status_code=422, detail="Paper positions require a protection-approved ENTER verdict")
    duplicate = await session.scalar(
        select(PaperTrade).where(
            PaperTrade.verdict_id == verdict.id,
            PaperTrade.status.in_(["pending", "open"]),
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This verdict already has an active paper position")
    observation = None
    if payload.entry_observation_id:
        observation = await session.scalar(
            select(MarketObservation).where(
                MarketObservation.id == payload.entry_observation_id,
                MarketObservation.token_id == token.id,
                MarketObservation.kind == "trade",
                MarketObservation.observed_at >= verdict.created_at,
            )
        )
        if not observation:
            raise HTTPException(status_code=422, detail="Entry must be a post-decision executable trade observation")
    else:
        observation = await session.scalar(
            select(MarketObservation)
            .where(
                MarketObservation.token_id == token.id,
                MarketObservation.kind == "trade",
                MarketObservation.observed_at >= verdict.created_at,
            )
            .order_by(MarketObservation.observed_at)
        )
    trade = PaperTrade(
        token_id=token.id,
        verdict_id=verdict.id,
        run_id=verdict.run_id,
        decision=decision,
        status="pending",
        notional=payload.notional,
        fee_bps=payload.fee_bps,
        slippage_bps=payload.slippage_bps,
        config={
            "contract_version": "paper-trade.v1",
            "execution": "long-only dry run",
            "real_funds": False,
            "verdict_created_at": _utc_datetime(verdict.created_at).isoformat(),
        },
    )
    session.add(trade)
    await session.flush()
    if observation:
        _paper_trade_from_observation(trade, observation)
    await session.commit()
    await session.refresh(trade)
    return trade


@router.post("/paper-trades/{trade_id}/close", response_model=PaperTradeRead)
async def close_paper_trade(
    trade_id: str,
    payload: PaperTradeClose,
    session: AsyncSession = Depends(get_session),
):
    trade = await session.get(PaperTrade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Paper trade not found")
    await require(session, Token, trade.token_id)
    if trade.status != "open" or not trade.opened_at or not trade.entry_price or not trade.quantity:
        raise HTTPException(status_code=409, detail="Only an open paper position can be closed")
    observation = await session.scalar(
        select(MarketObservation).where(
            MarketObservation.id == payload.exit_observation_id,
            MarketObservation.token_id == trade.token_id,
            MarketObservation.kind == "trade",
            MarketObservation.observed_at > trade.opened_at,
        )
    )
    if not observation:
        raise HTTPException(status_code=422, detail="Exit must be a later executable trade observation")
    closed = close_paper_position(
        entry_price=trade.entry_price,
        quantity=trade.quantity,
        notional=trade.notional,
        exit_price=observation.price,
        entry_fee=float((trade.config or {}).get("entry_fee") or trade.fees_paid),
        fee_bps=trade.fee_bps,
        slippage_bps=trade.slippage_bps,
    )
    trade.status = "closed"
    trade.exit_observation_id = observation.id
    trade.exit_price = closed["exit_price"]
    trade.fees_paid = closed["fees_paid"]
    trade.realized_pnl = closed["realized_pnl"]
    trade.return_pct = closed["return_pct"]
    trade.closed_at = observation.observed_at
    trade.close_reason = payload.close_reason
    await session.commit()
    await session.refresh(trade)
    return trade


@router.post("/connections", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
async def create_connection(payload: ConnectionCreate, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    if payload.base_url:
        try:
            validate_outbound_url(payload.base_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    data = payload.model_dump()
    fingerprint = secret_fingerprint(
        payload.api_key,
        f"{payload.workspace_id}:{payload.provider}:{(payload.base_url or '').rstrip('/').lower()}",
    )
    existing = None
    if fingerprint:
        existing = await session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.workspace_id == payload.workspace_id,
                ProviderConnection.provider == payload.provider,
                ProviderConnection.base_url == payload.base_url,
                ProviderConnection.credential_fingerprint == fingerprint,
            )
        )
    if existing:
        config = dict(existing.config or {})
        available = list(dict.fromkeys([*config.get("available_models", []), *payload.config.get("available_models", [])]))
        active = list(dict.fromkeys([*config.get("active_models", []), *payload.config.get("active_models", [])]))
        config.update(payload.config)
        if available:
            config["available_models"] = available
        if active:
            config["active_models"] = active
        existing.config = config
        existing.enabled = True
        await session.commit()
        await session.refresh(existing)
        return existing
    data["api_key"] = secret_codec.encrypt(payload.api_key)
    data["credential_fingerprint"] = fingerprint
    connection = ProviderConnection(**data)
    session.add(connection)
    await session.commit()
    await session.refresh(connection)
    return connection


async def require_workspace_admin(session: AsyncSession, workspace_id: str) -> WorkspaceMember | None:
    await ensure_workspace_access(session, workspace_id)
    user_id = current_user_id.get()
    if not get_settings().auth_required or not user_id:
        return None
    membership = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
        )
    )
    if not membership or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Workspace admin access required")
    return membership


@router.get("/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
async def list_workspace_members(workspace_id: str, session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, workspace_id)
    rows = (
        await session.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at)
        )
    ).all()
    return [
        WorkspaceMemberRead(
            user_id=user.id, email=user.email, display_name=user.display_name,
            role=member.role, created_at=member.created_at,
        )
        for member, user in rows
    ]


@router.post("/workspaces/{workspace_id}/members", response_model=WorkspaceMemberRead, status_code=201)
async def add_workspace_member(
    workspace_id: str, payload: WorkspaceMemberCreate, session: AsyncSession = Depends(get_session)
):
    await require_workspace_admin(session, workspace_id)
    user = await session.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user:
        raise HTTPException(status_code=404, detail="User must create an Orbit account before being invited")
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id
        )
    )
    if member and member.role == "owner":
        raise HTTPException(status_code=409, detail="The workspace owner role cannot be changed")
    if not member:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=payload.role)
        session.add(member)
    else:
        member.role = payload.role
    await session.commit();await session.refresh(member)
    return WorkspaceMemberRead(user_id=user.id, email=user.email, display_name=user.display_name, role=member.role, created_at=member.created_at)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
async def remove_workspace_member(workspace_id: str, user_id: str, session: AsyncSession = Depends(get_session)):
    await require_workspace_admin(session, workspace_id)
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="Workspace member not found")
    if member.role == "owner":
        raise HTTPException(status_code=409, detail="The workspace owner cannot be removed")
    await session.delete(member);await session.commit()


@router.post("/workspaces/{workspace_id}/transfer-ownership", response_model=list[WorkspaceMemberRead])
async def transfer_workspace_ownership(
    workspace_id: str, payload: WorkspaceOwnershipTransfer, session: AsyncSession = Depends(get_session)
):
    user_id = current_user_id.get()
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    current = await session.scalar(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.role == "owner",
    ))
    if not current:
        raise HTTPException(status_code=403, detail="Only the workspace owner can transfer ownership")
    target_user = await session.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not target_user or target_user.id == user_id:
        raise HTTPException(status_code=422, detail="Choose another existing workspace member")
    target = await session.scalar(select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == target_user.id,
    ))
    if not target:
        raise HTTPException(status_code=422, detail="The new owner must already be a workspace member")
    current.role = "admin"
    target.role = "owner"
    await session.commit()
    return await list_workspace_members(workspace_id, session)


@router.get("/connections", response_model=list[ConnectionRead])
async def list_connections(
    workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (
            await session.scalars(
                select(ProviderConnection)
                .where(ProviderConnection.workspace_id == workspace_id)
                .order_by(ProviderConnection.created_at.desc())
            )
        ).all()
    )


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_model_connection(
    connection_id: str, session: AsyncSession = Depends(get_session)
):
    """Remove a saved model API without touching agents that reference it.

    Agent foreign keys are ``SET NULL`` on deletion, so an agent remains
    editable and falls back to demo mode instead of leaving a broken FK.
    Context integrations keep their dedicated revoke flows and cannot be
    deleted through this generic model-connection endpoint.
    """
    connection = await require(session, ProviderConnection, connection_id)
    await ensure_workspace_access(session, connection.workspace_id)
    if connection.provider not in {"openai", "openai-compatible", "anthropic", "gemini-oauth"}:
        raise HTTPException(status_code=409, detail="Use the connector-specific revoke action for this connection")
    await session.delete(connection)
    await session.commit()
    return Response(status_code=204)


@router.post("/connections/discover", response_model=ConnectionDiscovery)
async def discover_connection_models(payload: ConnectionDiscover):
    resolved_base_url = payload.base_url.rstrip("/")
    try:
        if payload.provider == "tabitoken":
            validate_outbound_url(payload.base_url)
            if not payload.api_key:
                raise ValueError("TabiToken API key is required")
            models, latency_ms = await discover_tabitoken_models(payload.base_url, payload.api_key)
        elif payload.provider == "anthropic":
            validate_outbound_url(payload.base_url)
            if not payload.api_key:
                raise ValueError("Anthropic API key is required")
            models, latency_ms = await discover_anthropic_models(payload.base_url, payload.api_key)
        else:
            discovery = await discover_models(payload.base_url, payload.api_key)
            models, latency_ms = discovery
            resolved_base_url = getattr(discovery, "base_url", resolved_base_url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Connection check failed: {exc}") from exc
    if not models:
        raise HTTPException(status_code=422, detail="Connection works but returned no models")
    return ConnectionDiscovery(
        ok=True,
        latency_ms=latency_ms,
        models=models,
        model_count=len(models),
        base_url=resolved_base_url,
    )


async def connect_github(
    payload: GitHubConnect, session: AsyncSession = Depends(get_session)
):
    await require(session, Workspace, payload.workspace_id)
    try:
        github_data = await fetch_github_context(payload.token)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"GitHub connection failed: {exc}") from exc

    connection = await session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == payload.workspace_id,
            ProviderConnection.provider == "github",
        )
    )
    config = {
        "login": github_data["profile"]["login"],
        "repository_count": github_data["repository_count"],
        "profile": github_data["profile"],
        "repositories": github_data["repositories"],
    }
    if connection:
        config.update(
            {
                key: connection.config[key]
                for key in ("auth_method", "scopes")
                if key in (connection.config or {})
            }
        )
        connection.api_key = secret_codec.encrypt(payload.token)
        connection.config = config
        connection.enabled = True
    else:
        connection = ProviderConnection(
            workspace_id=payload.workspace_id,
            name=f"GitHub · {github_data['profile']['login']}",
            provider="github",
            base_url="https://api.github.com",
            api_key=secret_codec.encrypt(payload.token),
            config=config,
        )
        session.add(connection)

    memory = await session.scalar(
        select(MemoryNote).where(
            MemoryNote.workspace_id == payload.workspace_id,
            MemoryNote.scope == "global",
        )
    )
    source = github_memory_markdown(github_data)
    if not memory:
        memory = MemoryNote(
            workspace_id=payload.workspace_id,
            scope="global",
            title="Core memory",
            summary="Long-term user context and connected sources.",
            content=f"# Core memory\n\n{source}",
        )
        session.add(memory)
    else:
        marker = "## Connected source: GitHub"
        prefix = memory.content.split(marker, 1)[0].rstrip()
        memory.content = f"{prefix}\n\n{source}"
        memory.summary = (
            f"User working memory. GitHub @{github_data['profile']['login']}: "
            f"{github_data['repository_count']} repositories indexed."
        )
    memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
    await session.flush()
    await index_memory_note(session, memory)
    await session.commit()
    await session.refresh(connection)
    await session.refresh(memory)
    return GitHubSyncRead(
        connection=connection,
        login=github_data["profile"]["login"],
        repository_count=github_data["repository_count"],
        memory_note_id=memory.id,
    )


def github_oauth_redirect(status_value: str) -> RedirectResponse:
    query = urlencode({"screen": "connections", "github_oauth": status_value})
    return RedirectResponse(f"{get_settings().public_url.rstrip('/')}?{query}", status_code=302)


@router.get("/integrations/github/oauth/start", response_model=ContextConnectorOAuthStartRead)
async def start_github_oauth(
    workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, workspace_id)
    try:
        authorization_url = create_github_authorization(
            workspace_id, current_user_id.get() or "local-user"
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ContextConnectorOAuthStartRead(
        authorization_url=authorization_url,
        callback_url=github_oauth_callback_url(),
    )


@router.get("/integrations/github/oauth/callback")
async def github_oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
):
    if error or not code or not state:
        return github_oauth_redirect("denied" if error else "invalid_callback")
    try:
        state_data = verify_github_state(state)
        workspace_id = str(state_data["workspace_id"])
        await require(session, Workspace, workspace_id)
        token_data = await exchange_github_code(code)
        result = await connect_github(
            GitHubConnect(
                workspace_id=workspace_id,
                token=str(token_data["access_token"]),
            ),
            session,
        )
        connection = await require(session, ProviderConnection, result.connection.id)
        connection.config = {
            **dict(connection.config or {}),
            "auth_method": "oauth2",
            "scopes": str(token_data.get("scope") or "").replace(",", " ").split(),
        }
        await session.commit()
    except Exception:
        return github_oauth_redirect("connection_failed")
    return github_oauth_redirect("success")


@router.post("/integrations/github/{connection_id}/sync", response_model=GitHubSyncRead)
async def refresh_github_connection(
    connection_id: str, session: AsyncSession = Depends(get_session)
):
    connection = await require(session, ProviderConnection, connection_id)
    if connection.provider != "github":
        raise HTTPException(status_code=422, detail="Connection is not GitHub")
    token = secret_codec.decrypt(connection.api_key) or ""
    if not token:
        raise HTTPException(status_code=422, detail="GitHub access is unavailable")
    return await connect_github(
        GitHubConnect(workspace_id=connection.workspace_id, token=token), session
    )


@router.delete("/integrations/github/{connection_id}", status_code=204)
async def revoke_github_connection(
    connection_id: str, session: AsyncSession = Depends(get_session)
):
    connection = await require(session, ProviderConnection, connection_id)
    if connection.provider != "github":
        raise HTTPException(status_code=422, detail="Connection is not GitHub")
    token = secret_codec.decrypt(connection.api_key) or ""
    if token and (connection.config or {}).get("auth_method") == "oauth2":
        try:
            await revoke_github_token(token)
        except Exception:
            pass
    memory = await session.scalar(
        select(MemoryNote).where(
            MemoryNote.workspace_id == connection.workspace_id,
            MemoryNote.scope == "global",
        )
    )
    if memory:
        marker = "## Connected source: GitHub"
        memory.content = memory.content.split(marker, 1)[0].rstrip()
        memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
        await index_memory_note(session, memory)
    await session.delete(connection)
    await session.commit()
    return Response(status_code=204)


@router.post("/integrations/twitter/connect", response_model=TwitterSyncRead)
async def connect_twitter(
    payload: TwitterConnect, session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, payload.workspace_id)
    try:
        twitter_data = await fetch_twitter_context(payload.token)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"X connection failed: {exc}") from exc

    profile = twitter_data["profile"]
    connection = await session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == payload.workspace_id,
            ProviderConnection.provider == "twitter",
        )
    )
    config = {
        "username": profile["username"],
        "profile": profile,
        "posts": twitter_data["posts"],
        "posts_count": len(twitter_data["posts"]),
        "timeline_available": twitter_data["timeline_warning"] is None,
        "timeline_warning": twitter_data["timeline_warning"],
    }
    if connection:
        connection.name = f"X · @{profile['username']}"
        connection.api_key = secret_codec.encrypt(payload.token)
        connection.config = config
        connection.enabled = True
    else:
        connection = ProviderConnection(
            workspace_id=payload.workspace_id,
            name=f"X · @{profile['username']}",
            provider="twitter",
            base_url="https://api.x.com",
            api_key=secret_codec.encrypt(payload.token),
            config=config,
        )
        session.add(connection)

    memory = await session.scalar(
        select(MemoryNote).where(
            MemoryNote.workspace_id == payload.workspace_id,
            MemoryNote.scope == "global",
        )
    )
    source = twitter_memory_markdown(twitter_data)
    if not memory:
        memory = MemoryNote(
            workspace_id=payload.workspace_id,
            scope="global",
            title="Core memory",
            summary="Long-term user context and connected sources.",
            content=f"# Core memory\n\n{source}",
        )
        session.add(memory)
    else:
        start_marker = "<!-- source:x -->"
        end_marker = "<!-- /source:x -->"
        if start_marker in memory.content and end_marker in memory.content:
            prefix, remainder = memory.content.split(start_marker, 1)
            _, suffix = remainder.split(end_marker, 1)
            memory.content = f"{prefix.rstrip()}\n\n{source}{suffix}"
        else:
            memory.content = f"{memory.content.rstrip()}\n\n{source}"
        memory.summary = (
            f"User working memory. X @{profile['username']}: "
            f"{len(twitter_data['posts'])} recent posts indexed."
        )
    memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
    await session.flush()
    await index_memory_note(session, memory)
    await session.commit()
    await session.refresh(connection)
    await session.refresh(memory)
    return TwitterSyncRead(
        connection=connection,
        username=profile["username"],
        posts_count=len(twitter_data["posts"]),
        timeline_available=twitter_data["timeline_warning"] is None,
        memory_note_id=memory.id,
    )


@router.post("/auth/twitter/sync", response_model=TwitterSyncRead)
async def sync_twitter_login(payload: TwitterAuthSync, session: AsyncSession = Depends(get_session)):
    """Attach the X grant used for login to the user's first workspace."""
    user_id = current_user_id.get()
    user = await session.get(User, user_id) if user_id else None
    if not user or not user.twitter_credentials:
        raise HTTPException(status_code=404, detail="No X login grant is waiting to be connected")
    token_payload = json.loads(secret_codec.decrypt(user.twitter_credentials) or "{}")
    access_token = str(token_payload.get("access_token") or "")
    if not access_token:
        raise HTTPException(status_code=422, detail="The X login grant is no longer available")
    result = await connect_twitter(TwitterConnect(workspace_id=payload.workspace_id, token=access_token), session)
    connection = await session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == payload.workspace_id,
            ProviderConnection.provider == "twitter",
        )
    )
    if connection:
        connection.config = {
            **dict(connection.config or {}),
            "auth_method": "oauth2_pkce",
            "scopes": twitter_login_scopes().split(),
            "expires_at": token_payload.get("expires_at"),
        }
        await session.commit()
    return result


def twitter_oauth_redirect(status_value: str) -> RedirectResponse:
    public_url = get_settings().public_url.rstrip("/")
    query = urlencode({"screen": "profile", "twitter_oauth": status_value})
    return RedirectResponse(f"{public_url}/?{query}", status_code=303)


def google_model_oauth_redirect(status_value: str) -> RedirectResponse:
    public_url = get_settings().public_url.rstrip("/")
    query = urlencode({"screen": "team", "gemini_oauth": status_value})
    return RedirectResponse(f"{public_url}/?{query}", status_code=303)


@router.get("/integrations/google-model/oauth/start", response_model=GoogleModelOAuthStartRead)
async def start_google_model_oauth(
    workspace_id: str = Query(...),
    project_id: str = Query(..., min_length=4, max_length=100, pattern=r"^[a-z][a-z0-9-]+[a-z0-9]$"),
    session: AsyncSession = Depends(get_session),
):
    await ensure_workspace_access(session, workspace_id)
    user_id = current_user_id.get() or "local-user"
    try:
        authorization_url = create_google_model_authorization(workspace_id, user_id, project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return GoogleModelOAuthStartRead(
        authorization_url=authorization_url,
        callback_url=google_model_callback_url(),
    )


@router.get("/integrations/google-model/oauth/callback")
async def finish_google_model_oauth(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if error or not code or not state:
        return google_model_oauth_redirect("denied" if error else "invalid_callback")
    try:
        state_data = verify_google_model_state(state)
        request_user = current_user_id.get() or "local-user"
        if state_data["user_id"] != request_user:
            raise ValueError("Google OAuth session belongs to another user")
        workspace_id = str(state_data["workspace_id"])
        project_id = str(state_data["project_id"])
        await ensure_workspace_access(session, workspace_id)
        token_data = await exchange_google_model_code(code)
        models = await discover_google_models(str(token_data["access_token"]), project_id)
        if not models:
            raise ValueError("Google account returned no Gemini generation models")
        credentials = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": token_expiry(token_data),
        }
        connection = await session.scalar(select(ProviderConnection).where(
            ProviderConnection.workspace_id == workspace_id,
            ProviderConnection.provider == "gemini-oauth",
            ProviderConnection.config["project_id"].as_string() == project_id,
        ))
        config = {
            "preset": "gemini",
            "auth_method": "google_oauth2",
            "project_id": project_id,
            "available_models": [str(model["id"]) for model in models],
            "active_models": [],
            "scopes": str(token_data.get("scope") or get_settings().google_model_oauth_scopes).split(),
            "expires_at": credentials["expires_at"],
        }
        if connection:
            connection.api_key = secret_codec.encrypt(json.dumps(credentials, separators=(",", ":")))
            connection.config = config
            connection.enabled = True
        else:
            connection = ProviderConnection(
                workspace_id=workspace_id,
                name=f"Google Gemini · {project_id}",
                provider="gemini-oauth",
                base_url="https://generativelanguage.googleapis.com/v1beta",
                api_key=secret_codec.encrypt(json.dumps(credentials, separators=(",", ":"))),
                config=config,
            )
            session.add(connection)
        await session.commit()
    except Exception:
        return google_model_oauth_redirect("connection_failed")
    return google_model_oauth_redirect("success")


@router.get("/integrations/twitter/oauth/start", response_model=TwitterOAuthStartRead)
async def start_twitter_oauth(
    workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, workspace_id)
    user_id = current_user_id.get() or "local-user"
    try:
        authorization_url, _ = create_twitter_authorization(workspace_id, user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TwitterOAuthStartRead(
        authorization_url=authorization_url,
        callback_url=twitter_callback_url(),
    )


@router.get("/integrations/twitter/oauth/callback")
async def finish_twitter_oauth(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    if error or not code or not state:
        return twitter_oauth_redirect("denied" if error else "invalid_callback")
    try:
        state_data = verify_twitter_state(state)
        request_user = current_user_id.get() or "local-user"
        if state_data["user_id"] != request_user:
            raise ValueError("X OAuth session belongs to another user")
        workspace_id = str(state_data["workspace_id"])
        await ensure_workspace_access(session, workspace_id)
        token_data = await exchange_twitter_code(code, str(state_data["verifier"]))
        access_token = str(token_data["access_token"])
        await connect_twitter(TwitterConnect(workspace_id=workspace_id, token=access_token), session)

        connection = await session.scalar(
            select(ProviderConnection).where(
                ProviderConnection.workspace_id == workspace_id,
                ProviderConnection.provider == "twitter",
            )
        )
        if not connection:
            raise ValueError("X connection was not persisted")
        expires_at = None
        if token_data.get("expires_in"):
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))
            ).isoformat()
        connection.api_key = secret_codec.encrypt(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": token_data.get("refresh_token"),
                    "token_type": token_data.get("token_type", "bearer"),
                    "expires_at": expires_at,
                },
                separators=(",", ":"),
            )
        )
        connection.config = {
            **dict(connection.config or {}),
            "auth_method": "oauth2_pkce",
            "scopes": str(token_data.get("scope") or get_settings().twitter_oauth_scopes).split(),
            "token_type": token_data.get("token_type", "bearer"),
            "expires_at": expires_at,
        }
        await session.commit()
    except Exception:
        return twitter_oauth_redirect("connection_failed")
    return twitter_oauth_redirect("success")


@router.get("/integrations/context/catalog")
async def context_connector_catalog():
    return [
        {"id": connector_id, **preset}
        for connector_id, preset in CONNECTOR_CATALOG.items()
    ]


@router.post("/integrations/context/connect", response_model=ContextConnectorSyncRead)
async def connect_context_connector(
    payload: ContextConnectorConnect, session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, payload.workspace_id)
    preset = connector_preset(payload.connector)
    provider = f"connector-{payload.connector}"
    connection = await session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == payload.workspace_id,
            ProviderConnection.provider == provider,
        )
    )
    if (
        preset.get("credential_required", True)
        and not payload.credential.strip()
        and not (connection and payload.connector == "bitquery")
    ):
        raise HTTPException(status_code=422, detail=f"{preset['name']} API credential is required")
    if preset.get("needs_identifier") and not (payload.identifier or "").strip():
        raise HTTPException(status_code=422, detail=f"{preset['name']} requires an identifier")
    identifier = (payload.identifier or "").strip() or None
    config = {
        "identifier": identifier,
        "auth_method": "credential",
        "sync_status": "syncing",
        "target_configured": bool(identifier) if payload.connector == "bitquery" else True,
    }
    telegram_webhook_secret = None
    if payload.connector == "telegram":
        telegram_webhook_secret = secrets.token_urlsafe(24).replace("-", "_")
        config["webhook_secret_hash"] = hashlib.sha256(telegram_webhook_secret.encode()).hexdigest()
    fingerprint = secret_fingerprint(
        payload.credential, f"{payload.workspace_id}:{provider}"
    )
    if connection:
        connection.name = preset["name"]
        connection.base_url = preset["base_url"]
        # A saved Bitquery key can be given a scan target later.  Do not make
        # the user paste their secret again merely to choose that target.
        if payload.credential.strip():
            connection.api_key = secret_codec.encrypt(payload.credential)
            connection.credential_fingerprint = fingerprint
        connection.config = config
        connection.enabled = True
    else:
        connection = ProviderConnection(
            workspace_id=payload.workspace_id,
            name=preset["name"],
            provider=provider,
            base_url=preset["base_url"],
            api_key=secret_codec.encrypt(payload.credential),
            credential_fingerprint=fingerprint,
            config=config,
        )
        session.add(connection)
    await session.flush()
    if payload.connector == "bitquery" and not identifier:
        connection.name = "Bitquery · API connected"
        connection.config = {
            **dict(connection.config or {}),
            "label": "API connected — scan target not selected",
            "item_count": 0,
            "target_configured": False,
            "sync_status": "ready",
            "last_error": None,
        }
        await session.commit()
        await session.refresh(connection)
        return ContextConnectorSyncRead(
            connection=connection,
            label="API connected — scan target not selected",
            item_count=0,
        )
    try:
        connector_data, memory = await sync_context_connection(session, connection, reason="connected")
        if payload.connector == "telegram":
            webhook_url = f"{get_settings().public_url.rstrip('/')}{get_settings().api_prefix}/integrations/context/webhooks/telegram/{connection.id}"
            await configure_telegram_webhook(payload.credential, webhook_url, str(telegram_webhook_secret))
            connection.config = {**dict(connection.config or {}), "webhook_url": webhook_url, "webhook_active": True}
            await session.commit()
    except Exception as exc:
        await mark_sync_error(session, connection, exc)
        raise HTTPException(status_code=422, detail=f"{preset['name']} connection failed: {exc}") from exc
    return ContextConnectorSyncRead(
        connection=connection,
        label=str(connector_data["label"]),
        item_count=int(connector_data["item_count"]),
        memory_note_id=memory.id,
    )


def context_oauth_redirect(connector: str, status_value: str) -> RedirectResponse:
    public_url = get_settings().public_url.rstrip("/")
    query = urlencode({"screen": "connections", "context_oauth": status_value, "connector": connector})
    return RedirectResponse(f"{public_url}/?{query}", status_code=303)


@router.get("/integrations/context/oauth/start", response_model=ContextConnectorOAuthStartRead)
async def start_context_oauth(
    workspace_id: str = Query(...), connector: str = Query(..., pattern=r"^(notion|slack|google-drive|youtube)$"), session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, workspace_id)
    try:
        authorization_url = create_context_authorization(connector, workspace_id, current_user_id.get() or "local-user")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ContextConnectorOAuthStartRead(authorization_url=authorization_url, callback_url=context_oauth_callback_url(connector))


@router.get("/integrations/context/oauth/callback")
async def finish_context_oauth(
    code: str | None = Query(default=None), state: str | None = Query(default=None), error: str | None = Query(default=None), session: AsyncSession = Depends(get_session)
):
    connector = "unknown"
    if error or not code or not state:
        return context_oauth_redirect(connector, "denied" if error else "invalid_callback")
    try:
        state_data = verify_context_state(state)
        connector = str(state_data["connector"])
        if state_data["user_id"] != (current_user_id.get() or "local-user"):
            raise ValueError("OAuth session belongs to another user")
        workspace_id = str(state_data["workspace_id"])
        await ensure_workspace_access(session, workspace_id)
        token_data = await exchange_context_code(connector, code)
        provider = f"connector-{connector}"
        connection = await session.scalar(select(ProviderConnection).where(ProviderConnection.workspace_id == workspace_id, ProviderConnection.provider == provider))
        credentials = {key: token_data.get(key) for key in ("access_token", "refresh_token", "expires_at")}
        config = {"auth_method": "oauth2", "scopes": str(token_data.get("scope") or "").replace(",", " ").split(), "sync_status": "syncing"}
        if connector == "notion":
            config["external_workspace_id"] = token_data.get("workspace_id")
        elif connector == "slack":
            team = token_data.get("team") or {}
            config["external_workspace_id"] = team.get("id") if isinstance(team, dict) else None
        preset = connector_preset(connector)
        if connection:
            connection.name = preset["name"]
            connection.api_key = secret_codec.encrypt(json.dumps(credentials, separators=(",", ":")))
            connection.base_url = preset["base_url"]
            connection.config = config
            connection.enabled = True
        else:
            connection = ProviderConnection(workspace_id=workspace_id, name=preset["name"], provider=provider, base_url=preset["base_url"], api_key=secret_codec.encrypt(json.dumps(credentials, separators=(",", ":"))), config=config)
            session.add(connection)
        await session.flush()
        await sync_context_connection(session, connection, reason="oauth_connected")
    except Exception:
        return context_oauth_redirect(connector, "connection_failed")
    return context_oauth_redirect(connector, "success")


@router.post("/integrations/context/{connection_id}/sync", response_model=ContextConnectorSyncRead)
async def refresh_context_connector(connection_id: str, session: AsyncSession = Depends(get_session)):
    connection = await require(session, ProviderConnection, connection_id)
    await ensure_workspace_access(session, connection.workspace_id)
    if not connection.provider.startswith("connector-"):
        raise HTTPException(status_code=422, detail="This connection is not a context source")
    try:
        data, memory = await sync_context_connection(session, connection, reason="manual")
    except Exception as exc:
        await mark_sync_error(session, connection, exc)
        raise HTTPException(status_code=422, detail=f"Synchronization failed: {exc}") from exc
    return ContextConnectorSyncRead(connection=connection, label=str(data["label"]), item_count=int(data["item_count"]), memory_note_id=memory.id)


@router.delete("/integrations/context/{connection_id}", status_code=204)
async def revoke_context_connector(connection_id: str, session: AsyncSession = Depends(get_session)):
    connection = await require(session, ProviderConnection, connection_id)
    await ensure_workspace_access(session, connection.workspace_id)
    connector = connection.provider.removeprefix("connector-")
    raw = secret_codec.decrypt(connection.api_key) or ""
    access_token = raw
    try:
        credentials = json.loads(raw)
        access_token = str(credentials.get("access_token") or "")
        token = str(credentials.get("refresh_token") or access_token)
    except json.JSONDecodeError:
        token = raw
    if (connection.config or {}).get("auth_method") == "oauth2" and token:
        if connector == "google-drive":
            watch = dict((connection.config or {}).get("drive_watch") or {})
            try:
                await stop_drive_watch(access_token, str(watch.get("channel_id") or ""), str(watch.get("resource_id") or ""))
            except Exception:
                pass
        try:
            await revoke_context_token(connector, token)
        except Exception:
            pass
    if connector == "telegram" and token:
        try:
            await remove_telegram_webhook(token)
        except Exception:
            pass
    connection.enabled = False
    connection.api_key = None
    connection.config = {**dict(connection.config or {}), "sync_status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat()}
    memory = await session.scalar(select(MemoryNote).where(MemoryNote.workspace_id == connection.workspace_id, MemoryNote.scope == "global"))
    if memory:
        start, end = f"<!-- source:connector-{connector} -->", f"<!-- /source:connector-{connector} -->"
        if start in memory.content and end in memory.content:
            prefix, remainder = memory.content.split(start, 1)
            _, suffix = remainder.split(end, 1)
            memory.content = (prefix.rstrip() + "\n\n" + suffix.lstrip()).strip()
            memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
            await index_memory_note(session, memory)
    await session.commit()
    return Response(status_code=204)


def _verify_slack_webhook(body: bytes, timestamp: str, signature: str) -> None:
    signing_secret = get_settings().slack_signing_secret or ""
    try:
        fresh = timestamp and abs(int(time.time()) - int(timestamp)) <= 300
    except ValueError:
        fresh = False
    if not fresh:
        raise HTTPException(status_code=401, detail="Stale Slack event")
    expected = "v0=" + hmac.new(signing_secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    if not signing_secret or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")


@router.post("/integrations/context/webhooks/slack")
async def slack_context_webhook(request: Request, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    body = await request.body()
    _verify_slack_webhook(body, request.headers.get("x-slack-request-timestamp", ""), request.headers.get("x-slack-signature", ""))
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid Slack event") from exc
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
    team_id = str(payload.get("team_id") or "")
    connections = list((await session.scalars(select(ProviderConnection).where(ProviderConnection.provider == "connector-slack", ProviderConnection.enabled.is_(True)))).all())
    for connection in connections:
        config = dict(connection.config or {})
        details = dict(config.get("details") or {})
        if team_id and team_id in {str(config.get("external_workspace_id") or ""), str(details.get("team_id") or "")}:
            background_tasks.add_task(sync_connection_by_id, connection.id, "slack_webhook")
    return {"ok": True}


@router.post("/integrations/context/webhooks/notion")
async def notion_context_webhook(request: Request, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid Notion event") from exc
    if payload.get("verification_token"):
        return {"ok": True}
    verification_token = get_settings().notion_webhook_verification_token or ""
    received = request.headers.get("x-notion-signature", "")
    calculated = "sha256=" + hmac.new(verification_token.encode(), body, hashlib.sha256).hexdigest()
    if not verification_token or not received or not hmac.compare_digest(calculated, received):
        raise HTTPException(status_code=401, detail="Invalid Notion signature")
    workspace_id = str(payload.get("workspace_id") or "")
    connections = list((await session.scalars(select(ProviderConnection).where(ProviderConnection.provider == "connector-notion", ProviderConnection.enabled.is_(True)))).all())
    for connection in connections:
        if workspace_id and workspace_id == str((connection.config or {}).get("external_workspace_id") or ""):
            background_tasks.add_task(sync_connection_by_id, connection.id, "notion_webhook")
    return {"ok": True}


@router.post("/integrations/context/webhooks/{connector}/{connection_id}")
async def context_connector_webhook(
    connector: str,
    connection_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    connection = await session.get(ProviderConnection, connection_id)
    if not connection or connection.provider != f"connector-{connector}" or not connection.enabled:
        raise HTTPException(status_code=404, detail="Connector not found")
    body = await request.body()
    config = dict(connection.config or {})
    if connector == "telegram":
        received = request.headers.get("x-telegram-bot-api-secret-token", "")
        expected_hash = str(config.get("webhook_secret_hash") or "")
        legacy_expected = str(config.get("webhook_secret") or "")
        valid = bool(received) and (
            (expected_hash and hmac.compare_digest(expected_hash, hashlib.sha256(received.encode()).hexdigest()))
            or (legacy_expected and hmac.compare_digest(legacy_expected, received))
        )
        if not valid:
            raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
        try:
            update = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid Telegram update") from exc
        record = telegram_record(update)
        if record:
            await ingest_context_records(session, connection, [record], reason="telegram_webhook")
        return {"ok": True}
    if connector == "google-drive":
        watch = dict(config.get("drive_watch") or {})
        received_token = request.headers.get("x-goog-channel-token", "")
        expected_hash = str(watch.get("channel_token_hash") or "")
        legacy_expected = str(watch.get("channel_token") or "")
        valid_token = bool(received_token) and (
            (expected_hash and hmac.compare_digest(expected_hash, hashlib.sha256(received_token.encode()).hexdigest()))
            or (legacy_expected and hmac.compare_digest(legacy_expected, received_token))
        )
        if not valid_token:
            raise HTTPException(status_code=401, detail="Invalid Google channel token")
        if str(watch.get("channel_id") or "") != request.headers.get("x-goog-channel-id", ""):
            raise HTTPException(status_code=401, detail="Invalid Google channel ID")
        resource_id = request.headers.get("x-goog-resource-id", "")
        if watch.get("resource_id") and not hmac.compare_digest(str(watch["resource_id"]), resource_id):
            raise HTTPException(status_code=401, detail="Invalid Google resource ID")
    else:
        raise HTTPException(status_code=404, detail="Unsupported webhook")
    background_tasks.add_task(sync_connection_by_id, connection.id, f"{connector}_webhook")
    return {"ok": True}


async def github_connection_for(session: AsyncSession, workspace_id: str, repository: str) -> ProviderConnection:
    await require(session, Workspace, workspace_id)
    connection = await session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.workspace_id == workspace_id,
            ProviderConnection.provider == "github",
            ProviderConnection.enabled.is_(True),
        )
    )
    if not connection:
        raise HTTPException(status_code=404, detail="GitHub is not connected")
    allowed = {str(item.get("name")) for item in connection.config.get("repositories", [])}
    if repository not in allowed:
        raise HTTPException(status_code=403, detail="Repository is not enabled for this workspace")
    return connection


@router.post("/integrations/github/tree")
async def github_tree(payload: GitHubRepositoryQuery, session: AsyncSession = Depends(get_session)):
    connection = await github_connection_for(session, payload.workspace_id, payload.repository)
    try:
        return await fetch_repository_tree(
            secret_codec.decrypt(connection.api_key) or "", payload.repository, payload.ref
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"GitHub tree failed: {exc}") from exc


@router.post("/integrations/github/file")
async def github_file(payload: GitHubFileQuery, session: AsyncSession = Depends(get_session)):
    connection = await github_connection_for(session, payload.workspace_id, payload.repository)
    try:
        return await fetch_repository_file(
            secret_codec.decrypt(connection.api_key) or "", payload.repository, payload.path, payload.ref
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"GitHub file failed: {exc}") from exc


@router.post("/integrations/github/search")
async def github_search(payload: GitHubCodeSearch, session: AsyncSession = Depends(get_session)):
    connection = await github_connection_for(session, payload.workspace_id, payload.repository)
    try:
        return await search_repository_code(
            secret_codec.decrypt(connection.api_key) or "", payload.repository, payload.query
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"GitHub search failed: {exc}") from exc


@router.get("/mcp/catalog")
async def list_mcp_catalog():
    return MCP_CATALOG


@router.get("/mcp/servers", response_model=list[ConnectionRead])
async def list_mcp_servers(
    workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (
            await session.scalars(
                select(ProviderConnection)
                .where(
                    ProviderConnection.workspace_id == workspace_id,
                    ProviderConnection.provider == "mcp",
                )
                .order_by(ProviderConnection.created_at.desc())
            )
        ).all()
    )


@router.post("/mcp/servers", response_model=ConnectionRead, status_code=201)
async def install_mcp_server(
    payload: MCPInstall, session: AsyncSession = Depends(get_session)
):
    await require(session, Workspace, payload.workspace_id)
    preset = find_mcp_preset(payload.preset_id)
    if not preset and payload.preset_id != "custom":
        raise HTTPException(status_code=404, detail="Unknown MCP preset")
    transport = payload.transport or (preset["transport"] if preset else "streamable_http")
    command = payload.command or (preset.get("command") if preset else None)
    args = payload.args if payload.args is not None else (list(preset.get("args", [])) if preset else [])
    if transport in {"streamable_http", "sse"} and not payload.url:
        raise HTTPException(status_code=422, detail="Remote MCP requires an endpoint URL")
    if transport == "stdio" and not command:
        raise HTTPException(status_code=422, detail="stdio MCP requires a command")
    if get_settings().app_env == "production" and transport == "stdio":
        raise HTTPException(status_code=422, detail="stdio MCP requires an isolated tool runner and is disabled on the public API")
    if payload.url:
        try:
            validate_outbound_url(payload.url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    protected_config = {"preset_id", "transport", "command", "args", "url", "secret_name", "risk", "official", "status"}
    extra_config = {key: value for key, value in payload.extra_config.items() if key not in protected_config}
    config = {
        "preset_id": payload.preset_id,
        "transport": transport,
        "command": command,
        "args": args,
        "url": payload.url,
        "secret_name": preset.get("secret_name") if preset else payload.extra_config.get("secret_name"),
        "risk": preset.get("risk", "custom") if preset else "custom",
        "official": bool(preset and preset.get("official")),
        "status": "installed",
        **extra_config,
    }
    server = ProviderConnection(
        workspace_id=payload.workspace_id,
        name=payload.name or (preset["name"] if preset else "Custom MCP"),
        provider="mcp",
        base_url=payload.url,
        api_key=secret_codec.encrypt(payload.secret),
        config=config,
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return server


@router.post("/agents/{agent_id}/mcp/{server_id}", response_model=AgentRead)
async def attach_mcp_to_agent(
    agent_id: str, server_id: str, session: AsyncSession = Depends(get_session)
):
    agent = await require(session, Agent, agent_id)
    server = await require(session, ProviderConnection, server_id)
    if server.provider != "mcp" or server.workspace_id != agent.workspace_id:
        raise HTTPException(status_code=422, detail="MCP server belongs to another workspace")
    raise HTTPException(
        status_code=410,
        detail="Per-agent MCP bindings were removed. Add an MCP tool node to the workflow instead.",
    )


@router.get("/mcp/servers/{server_id}/tools", response_model=list[MCPToolRead])
async def discover_mcp_tools(server_id: str, session: AsyncSession = Depends(get_session)):
    server = await require(session, ProviderConnection, server_id)
    if server.provider != "mcp":
        raise HTTPException(status_code=422, detail="Connection is not an MCP server")
    try:
        tools = await MCPClient(server).list_tools()
    except Exception as exc:
        config = dict(server.config or {})
        config["status"] = "error"
        config["last_error"] = str(exc)[:500]
        server.config = config
        await session.commit()
        raise HTTPException(status_code=422, detail=f"MCP check failed: {exc}") from exc
    config = dict(server.config or {})
    config["status"] = "ready"
    config["tools"] = [
        {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
        for tool in tools
    ]
    server.config = config
    attached_agents = list(
        (
            await session.scalars(select(Agent).where(Agent.workspace_id == server.workspace_id))
        ).all()
    )
    for agent in attached_agents:
        changed = False
        bindings = []
        for binding in agent.tools or []:
            value = dict(binding)
            if value.get("type") == "mcp" and value.get("connection_id") == server.id:
                value["tools"] = config["tools"]
                changed = True
            bindings.append(value)
        if changed:
            agent.tools = bindings
    await session.commit()
    return [MCPToolRead(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in tools]


async def execute_tool_call_record(session: AsyncSession, call: ToolCall) -> ToolCall:
    server = await require(session, ProviderConnection, call.connection_id or "")
    call.status = "running"
    await session.commit()
    await broker.publish(
        session, run_id=call.run_id, event_type="tool.call.started", actor_type="agent",
        actor_id=call.agent_id, task_id=call.task_id,
        payload={"tool_call_id": call.id, "tool": call.tool_name, "risk": call.risk},
    )
    try:
        result = await MCPClient(server).call_tool(call.tool_name, call.arguments)
        call.status = "completed"
        call.result = result
        call.finished_at = datetime.now(timezone.utc)
        await session.commit()
        await broker.publish(
            session, run_id=call.run_id, event_type="tool.call.completed", actor_type="agent",
            actor_id=call.agent_id, task_id=call.task_id,
            payload={"tool_call_id": call.id, "tool": call.tool_name, "result": result},
        )
    except Exception as exc:
        call.status = "failed"
        call.error = str(exc)[:4000]
        call.finished_at = datetime.now(timezone.utc)
        await session.commit()
        await broker.publish(
            session, run_id=call.run_id, event_type="tool.call.failed", actor_type="agent",
            actor_id=call.agent_id, task_id=call.task_id,
            payload={"tool_call_id": call.id, "tool": call.tool_name, "error": call.error},
        )
    await session.refresh(call)
    return call


@router.post("/runs/{run_id}/tools/call", response_model=ToolCallRead, status_code=201)
async def call_mcp_tool(
    run_id: str, payload: ToolCallCreate, session: AsyncSession = Depends(get_session)
):
    run = await require(session, Run, run_id)
    team = await require(session, Team, run.team_id)
    server = await require(session, ProviderConnection, payload.connection_id)
    if server.provider != "mcp" or server.workspace_id != team.workspace_id:
        raise HTTPException(status_code=422, detail="MCP server belongs to another workspace")
    if payload.agent_id:
        agent = await require(session, Agent, payload.agent_id)
        if agent.workspace_id != team.workspace_id:
            raise HTTPException(status_code=422, detail="Agent belongs to another workspace")
    call = ToolCall(run_id=run_id, **payload.model_dump())
    session.add(call)
    await session.commit()
    await session.refresh(call)
    await broker.publish(
        session, run_id=run_id, event_type="tool.call.requested", actor_type="agent",
        actor_id=call.agent_id, task_id=call.task_id,
        payload={"tool_call_id": call.id, "tool": call.tool_name, "risk": call.risk},
    )
    auto_approve = call.risk == "read" or bool(server.config.get("auto_approve_write"))
    if auto_approve:
        return await execute_tool_call_record(session, call)
    approval = Approval(
        run_id=run_id,
        task_id=call.task_id,
        requested_by_agent_id=call.agent_id,
        action=f"tool:{call.tool_name}",
        description=(
            f"Разрешить инструменту {call.tool_name} выполнить действие уровня {call.risk}"
            if str((run.context or {}).get("language") or "en").startswith("ru")
            else f"Allow {call.tool_name} to perform a {call.risk}-risk action"
        ),
        risk=call.risk,
        request_payload={"tool_call_id": call.id},
    )
    call.status = "waiting_for_approval"
    session.add(approval)
    await session.commit()
    await broker.publish(
        session, run_id=run_id, event_type="approval.requested", actor_type="agent",
        actor_id=call.agent_id, task_id=call.task_id,
        payload={"approval_id": approval.id, "action": approval.action, "risk": approval.risk},
    )
    await session.refresh(call)
    return call


@router.get("/runs/{run_id}/tool-calls", response_model=list[ToolCallRead])
async def list_tool_calls(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(ToolCall).where(ToolCall.run_id == run_id).order_by(ToolCall.created_at)
            )
        ).all()
    )


@router.get("/research/reports", response_model=list[ResearchRead])
async def list_research_reports(
    workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)
):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (
            await session.scalars(
                select(ResearchReport)
                .where(ResearchReport.workspace_id == workspace_id)
                .order_by(ResearchReport.created_at.desc())
            )
        ).all()
    )


@router.post("/research/reports", response_model=ResearchRead, status_code=201)
async def create_research_report(
    payload: ResearchCreate, session: AsyncSession = Depends(get_session)
):
    await require(session, Workspace, payload.workspace_id)
    allowed = {"web", "youtube", "tiktok", "instagram", "onchain"}
    sources = list(dict.fromkeys(source for source in payload.sources if source in allowed))
    await consume_daily_quota(session, kind="research")
    settings = get_settings()
    credentials = {
        "web": {"key": settings.research_brave_api_key},
        "youtube": {"key": settings.research_youtube_api_key},
        "tiktok": {"key": settings.research_tiktok_access_token},
        "instagram": {
            "key": settings.research_instagram_access_token,
            "account_id": settings.research_instagram_account_id,
        },
    }
    findings, source_status = await run_research(payload.query, sources, credentials, payload.depth)
    report_text = build_report(payload.query, findings, source_status)
    report = ResearchReport(
        workspace_id=payload.workspace_id,
        query=payload.query,
        status="completed",
        depth=payload.depth,
        requested_sources=sources,
        source_status=source_status,
        findings=findings,
        report=report_text,
    )
    session.add(report)
    memory = await session.scalar(
        select(MemoryNote).where(
            MemoryNote.workspace_id == payload.workspace_id,
            MemoryNote.scope == "global",
        )
    )
    if memory and findings:
        compact = "\n".join(
            f"- [{item['source']}] {item['title']}: {item['snippet'][:180]}"
            for item in findings[:8]
        )
        memory.content += f"\n\n## Research evidence: {payload.query[:100]}\n{compact}"
        memory.content = memory.content[-18000:]
        query_is_russian = any("а" <= char.lower() <= "я" or char.lower() == "ё" for char in payload.query)
        memory.summary = (
            f"Обновлено Deep Research: {payload.query[:120]}"
            if query_is_russian
            else f"Updated by Deep Research: {payload.query[:120]}"
        )
        memory.byte_size = len((memory.content + memory.summary).encode("utf-8"))
        await index_memory_note(session, memory)
    await session.commit()
    await session.refresh(report)
    return report


@router.post("/agents", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(payload: AgentCreate, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    if payload.connection_id:
        connection = await require(session, ProviderConnection, payload.connection_id)
        if connection.workspace_id != payload.workspace_id:
            raise HTTPException(status_code=422, detail="Connection belongs to another workspace")
    agent = Agent(**payload.model_dump())
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.get("/agents", response_model=list[AgentRead])
async def list_agents(workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (
            await session.scalars(
                select(Agent).where(Agent.workspace_id == workspace_id).order_by(Agent.created_at)
            )
        ).all()
    )


@router.get("/agents/{agent_id}", response_model=AgentRead)
async def get_agent(agent_id: str, session: AsyncSession = Depends(get_session)):
    return await require(session, Agent, agent_id)


@router.patch("/agents/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str, payload: AgentUpdate, session: AsyncSession = Depends(get_session)
):
    agent = await require(session, Agent, agent_id)
    changes = payload.model_dump(exclude_unset=True)
    if "connection_id" in changes and changes["connection_id"]:
        connection = await require(session, ProviderConnection, changes["connection_id"])
        if connection.workspace_id != agent.workspace_id:
            raise HTTPException(status_code=422, detail="Connection belongs to another workspace")
    for field, value in changes.items():
        setattr(agent, field, value)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, session: AsyncSession = Depends(get_session)):
    agent = await require(session, Agent, agent_id)
    await ensure_workspace_access(session, agent.workspace_id, write=True)
    # Remove memberships explicitly so this also behaves correctly on local
    # SQLite databases where foreign-key cascades may be disabled.
    await session.execute(delete(TeamAgent).where(TeamAgent.agent_id == agent.id))
    await session.execute(
        update(Team)
        .where(Team.supervisor_agent_id == agent.id)
        .values(supervisor_agent_id=None)
    )
    await session.delete(agent)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/teams", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    agents = list(
        (
            await session.scalars(
                select(Agent).where(
                    Agent.id.in_(payload.agent_ids), Agent.workspace_id == payload.workspace_id
                )
            )
        ).all()
    )
    if len(agents) != len(set(payload.agent_ids)):
        raise HTTPException(status_code=422, detail="Some agents do not exist in this workspace")
    if payload.supervisor_agent_id and payload.supervisor_agent_id not in payload.agent_ids:
        raise HTTPException(status_code=422, detail="Supervisor must be a team member")
    data = payload.model_dump(exclude={"agent_ids"})
    team = Team(**data)
    session.add(team)
    await session.flush()
    for position, agent_id in enumerate(payload.agent_ids):
        session.add(TeamAgent(team_id=team.id, agent_id=agent_id, position=position))
    await session.commit()
    await session.refresh(team)
    return TeamRead.model_validate(team).model_copy(update={"agent_ids": payload.agent_ids})


@router.get("/teams", response_model=list[TeamRead])
async def list_teams(workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, workspace_id)
    teams = list(
        (
            await session.scalars(
                select(Team)
                .where(Team.workspace_id == workspace_id)
                .options(selectinload(Team.memberships))
                .order_by(Team.created_at.desc())
            )
        ).all()
    )
    return [
        TeamRead.model_validate(team).model_copy(
            update={"agent_ids": [membership.agent_id for membership in team.memberships]}
        )
        for team in teams
    ]


@router.post("/teams/{team_id}/agents", status_code=status.HTTP_201_CREATED)
async def add_team_agent(
    team_id: str, payload: TeamMemberAdd, session: AsyncSession = Depends(get_session)
):
    team = await require(session, Team, team_id)
    agent = await require(session, Agent, payload.agent_id)
    if agent.workspace_id != team.workspace_id:
        raise HTTPException(status_code=422, detail="Agent belongs to another workspace")
    existing = await session.scalar(
        select(TeamAgent).where(
            TeamAgent.team_id == team_id,
            TeamAgent.agent_id == payload.agent_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Agent is already a team member")
    member_count = len(
        list(
            (
                await session.scalars(
                    select(TeamAgent).where(TeamAgent.team_id == team_id)
                )
            ).all()
        )
    )
    if member_count >= 10:
        raise HTTPException(status_code=422, detail="A team can contain at most 10 agents")
    position = await session.scalar(
        select(TeamAgent.position)
        .where(TeamAgent.team_id == team_id)
        .order_by(TeamAgent.position.desc())
        .limit(1)
    )
    membership = TeamAgent(
        team_id=team_id,
        agent_id=agent.id,
        position=(position or 0) + 1,
    )
    session.add(membership)
    await session.commit()
    return {"agent_id": agent.id, "team_id": team.id}


def validate_workflow_graph(workflow: Workflow) -> WorkflowValidation:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    node_ids = [str(node.get("id", "")) for node in workflow.nodes]
    if not node_ids:
        errors.append({"code": "empty_graph", "message": "Workflow must contain at least one node"})
    if len(node_ids) != len(set(node_ids)) or "" in node_ids:
        errors.append({"code": "invalid_node_ids", "message": "Every node must have a unique id"})
    start_nodes = [node for node in workflow.nodes if node.get("type") == "start"]
    if len(start_nodes) != 1:
        errors.append({"code": "start_count", "message": "Workflow must contain exactly one start node"})
    if not any(node.get("type") in {"final", "output"} for node in workflow.nodes):
        errors.append({"code": "missing_final", "message": "Workflow must contain a final node"})
    connected: set[str] = set()
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    allowed_types = {
        "start", "agent", "human_input", "condition", "parallel", "approval",
        "artifact", "tool", "review", "final", "output",
    }
    for node in workflow.nodes:
        node_type = str(node.get("type", ""))
        if node_type not in allowed_types:
            errors.append({"code": "unknown_node_type", "message": f"Unsupported node type: {node_type}"})
        if node_type == "agent" and not node.get("agent_id"):
            errors.append({"code": "agent_missing", "message": f"Agent node {node.get('id')} has no agent_id"})
        if node_type == "condition" and not node.get("expression"):
            warnings.append({"code": "condition_missing", "message": f"Condition {node.get('id')} has no expression"})
        if node_type == "tool":
            if not node.get("connection_id") and node.get("source") != "chain":
                errors.append({"code": "tool_connection_missing", "message": f"Tool node {node.get('id')} has no MCP connection"})
            if not node.get("tool_name"):
                errors.append({"code": "tool_missing", "message": f"Tool node {node.get('id')} has no tool_name"})
    for edge in workflow.edges:
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source not in node_ids or target not in node_ids:
            errors.append({"code": "dangling_edge", "message": f"Invalid edge {source} -> {target}"})
        elif source == target:
            errors.append({"code": "self_cycle", "message": f"Node {source} cannot connect to itself"})
        else:
            outgoing[source].append(target)
            indegree[target] += 1
        connected.update({source, target})
    condition_ids = {str(node.get("id")) for node in workflow.nodes if node.get("type") == "condition"}
    for condition_id in condition_ids:
        labels = {
            str(edge.get("condition") or edge.get("label") or "").lower()
            for edge in workflow.edges if str(edge.get("source")) == condition_id
        }
        if labels and not ({"true", "yes", "да", "1"} & labels and {"false", "no", "нет", "0"} & labels):
            warnings.append({
                "code": "condition_branches",
                "message": f"Condition {condition_id} should have labelled true and false edges",
            })
    for node_id in node_ids:
        if len(node_ids) > 1 and node_id not in connected:
            warnings.append({"code": "isolated_node", "message": f"Node {node_id} is isolated"})
    queue = [node_id for node_id, count in indegree.items() if count == 0]
    visited = 0
    while queue:
        node_id = queue.pop()
        visited += 1
        for target in outgoing.get(node_id, []):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if node_ids and visited != len(node_ids):
        errors.append({"code": "unbounded_cycle", "message": "Workflow contains a cycle; loops require an explicit bounded loop node"})
    return WorkflowValidation(valid=not errors, errors=errors, warnings=warnings)


@router.post("/workflows", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(payload: WorkflowCreate, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    if payload.team_id:
        team = await require(session, Team, payload.team_id)
        if team.workspace_id != payload.workspace_id:
            raise HTTPException(status_code=422, detail="Team belongs to another workspace")
    workflow = Workflow(**payload.model_dump())
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)
    return workflow


@router.get("/workflows", response_model=list[WorkflowRead])
async def list_workflows(workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (
            await session.scalars(
                select(Workflow)
                .where(Workflow.workspace_id == workspace_id)
                .order_by(Workflow.updated_at.desc())
            )
        ).all()
    )


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(workflow_id: str, session: AsyncSession = Depends(get_session)):
    return await require(session, Workflow, workflow_id)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowRead)
async def update_workflow(
    workflow_id: str, payload: WorkflowUpdate, session: AsyncSession = Depends(get_session)
):
    workflow = await require(session, Workflow, workflow_id)
    changes = payload.model_dump(exclude_unset=True)
    if any(key in changes for key in {"nodes", "edges"}):
        workflow.version += 1
        workflow.published = False
    for key, value in changes.items():
        setattr(workflow, key, value)
    if workflow.published:
        validation = validate_workflow_graph(workflow)
        if not validation.valid:
            raise HTTPException(status_code=422, detail=validation.model_dump())
    await session.commit()
    await session.refresh(workflow)
    return workflow


@router.post("/workflows/{workflow_id}/validate", response_model=WorkflowValidation)
async def validate_workflow(workflow_id: str, session: AsyncSession = Depends(get_session)):
    workflow = await require(session, Workflow, workflow_id)
    return validate_workflow_graph(workflow)


@router.post("/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, session: AsyncSession = Depends(get_session)):
    await require_verified_user(session)
    team = await require(session, Team, payload.team_id)
    if payload.workflow_id:
        workflow = await require(session, Workflow, payload.workflow_id)
        if workflow.team_id and workflow.team_id != team.id:
            raise HTTPException(status_code=422, detail="Workflow belongs to another team")
    requested_mode = payload.mode or team.mode
    # Constructive is an orchestration mode, not a provider-diversity tier.
    # A reviewer with a different model family is preferred when available,
    # but role separation and an explicit critic pass still work when a team
    # intentionally uses one provider or one subscription-backed connection.
    await consume_daily_quota(session, kind="research")
    language = str(payload.context.get("language") or "en").lower()
    ru = language.startswith("ru")
    run = Run(
        team_id=team.id,
        workflow_id=payload.workflow_id,
        goal=payload.goal or team.goal,
        mode=requested_mode,
        context=payload.context,
    )
    session.add(run)
    await session.flush()
    workspace_id = team.workspace_id
    global_memory = await session.scalar(
        select(MemoryNote).where(
            MemoryNote.workspace_id == workspace_id,
            MemoryNote.scope == "global",
        )
    )
    if not global_memory:
        global_memory = MemoryNote(
            workspace_id=workspace_id,
            scope="global",
            title="Основная память" if ru else "Core memory",
            summary=(
                "Долговременные знания, предпочтения и решения пользователя."
                if ru
                else "Long-term knowledge, preferences, and decisions for this workspace."
            ),
            content=(
                "# Основная память\n\nЗдесь сохраняются устойчивые знания между диалогами."
                if ru
                else "# Core memory\n\nDurable knowledge is kept here between dialogues."
            ),
        )
        global_memory.byte_size = len(global_memory.content.encode("utf-8"))
        session.add(global_memory)
        await session.flush()
    dialogue_memory = MemoryNote(
        workspace_id=workspace_id,
        run_id=run.id,
        scope="dialogue",
        title=(payload.goal or team.goal)[:100],
        summary=(
            "Компактный лог целей и решений этого диалога."
            if ru
            else "A compact record of this dialogue’s goals and decisions."
        ),
        content=(
            f"# Диалог\n\nЦель: {payload.goal or team.goal}"
            if ru
            else f"# Dialogue\n\nGoal: {payload.goal or team.goal}"
        ),
        links=[global_memory.id],
    )
    dialogue_memory.byte_size = len(dialogue_memory.content.encode("utf-8"))
    session.add(dialogue_memory)
    await session.flush()
    await index_memory_note(session, global_memory)
    await index_memory_note(session, dialogue_memory)
    await session.commit()
    await session.refresh(run)
    if payload.auto_start:
        await runtime.start(run.id)
    return run


@router.get("/runs/{run_id}", response_model=RunRead)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)):
    return await require(session, Run, run_id)


@router.patch("/runs/{run_id}/meta", response_model=RunRead)
async def update_run_meta(run_id: str, payload: RunMetaUpdate, session: AsyncSession = Depends(get_session)):
    run = await require(session, Run, run_id)
    context = dict(run.context or {})
    if payload.pinned is not None:
        context["pinned"] = payload.pinned
    if payload.archived is not None:
        context["archived"] = payload.archived
    if payload.title is not None:
        run.goal = payload.title.strip()
        note = await session.scalar(select(MemoryNote).where(MemoryNote.run_id == run.id))
        if note:
            note.title = run.goal[:300]
    run.context = context
    await session.commit()
    await session.refresh(run)
    return run


@router.patch("/runs/{run_id}/agents", response_model=RunRead)
async def update_run_participants(
    run_id: str,
    payload: RunParticipantsUpdate,
    session: AsyncSession = Depends(get_session),
):
    run = await require(session, Run, run_id)
    team = await require(session, Team, run.team_id)
    requested_ids = list(dict.fromkeys(payload.agent_ids))
    agents = list(
        (
            await session.scalars(
                select(Agent).where(
                    Agent.id.in_(requested_ids),
                    Agent.workspace_id == team.workspace_id,
                )
            )
        ).all()
    )
    if len(agents) != len(requested_ids):
        raise HTTPException(
            status_code=422,
            detail="One or more agents do not belong to this workspace",
        )

    existing = set(
        (
            await session.scalars(
                select(TeamAgent.agent_id).where(TeamAgent.team_id == team.id)
            )
        ).all()
    )
    maximum_position = await session.scalar(
        select(func.max(TeamAgent.position)).where(TeamAgent.team_id == team.id)
    )
    next_position = int(maximum_position if maximum_position is not None else -1) + 1
    for agent_id in requested_ids:
        if agent_id not in existing:
            session.add(
                TeamAgent(
                    team_id=team.id,
                    agent_id=agent_id,
                    position=next_position,
                )
            )
            next_position += 1

    context = dict(run.context or {})
    context["agent_ids"] = requested_ids
    run.context = context
    await session.commit()
    await session.refresh(run)
    await broker.publish(
        session,
        run_id=run.id,
        event_type="run.participants_changed",
        actor_type="human",
        recipients=["all"],
        payload={"agent_ids": requested_ids, "count": len(requested_ids)},
    )
    return run


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await require(session, Run, run_id)
    await session.delete(run)
    await session.commit()


@router.post("/runs/{run_id}/merge-memory", response_model=MemoryRead)
async def merge_run_memory(run_id: str, payload: RunMemoryMerge, session: AsyncSession = Depends(get_session)):
    if run_id == payload.target_run_id:
        raise HTTPException(status_code=422, detail="Source and target dialogue must be different")
    source_run = await require(session, Run, run_id)
    target_run = await require(session, Run, payload.target_run_id)
    source = await session.scalar(select(MemoryNote).where(MemoryNote.run_id == source_run.id))
    target = await session.scalar(select(MemoryNote).where(MemoryNote.run_id == target_run.id))
    if not source or not target:
        raise HTTPException(status_code=404, detail="Dialogue memory not found")
    ru = str((target_run.context or {}).get("language") or "en").startswith("ru")
    heading = "Память из диалога" if ru else "Memory from dialogue"
    block = f"\n\n## {heading}: {source_run.goal[:160]}\n{source.summary}\n\n{source.content[-6000:]}"
    if block not in target.content:
        target.content = (target.content + block)[-18000:]
        target.summary = (
            f"Добавлена память из диалога «{source_run.goal[:100]}»"
            if ru
            else f"Added memory from dialogue “{source_run.goal[:100]}”"
        )
        target.links = list(dict.fromkeys([*target.links, source.id]))
        target.byte_size = len((target.content + target.summary).encode("utf-8"))
    await session.commit()
    await session.refresh(target)
    return target


@router.patch("/runs/{run_id}/budget", response_model=RunRead)
async def update_run_budget(run_id: str, payload: RunBudgetUpdate, session: AsyncSession = Depends(get_session)):
    run = await require(session, Run, run_id)
    context = dict(run.context or {})
    if payload.token_limit is not None:
        context["budget_tokens"] = payload.token_limit
    if payload.cost_limit_micros is not None:
        context["budget_cost_micros"] = payload.cost_limit_micros
    if payload.max_rounds is not None:
        context["max_rounds"] = payload.max_rounds
    run.context = context
    await session.commit()
    await session.refresh(run)
    return run


@router.post("/runs/{run_id}/branch", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def branch_run(run_id: str, payload: RunBranchCreate, session: AsyncSession = Depends(get_session)):
    source = await require(session, Run, run_id)
    point = await require(session, RunEvent, payload.event_id)
    if point.run_id != source.id:
        raise HTTPException(status_code=422, detail="Branch point does not belong to this dialogue")
    source_context = dict(source.context or {})
    context = {
        **source_context,
        "parent_run_id": source.id,
        "branch_point_event_id": point.id,
        "branch_point_sequence": point.sequence,
        "branch_kind": payload.kind,
        "replay_public": False,
    }
    context.pop("replay_token", None)
    branch = Run(
        team_id=source.team_id,
        workflow_id=source.workflow_id,
        goal=source.goal,
        mode=source.mode,
        context=context,
        plan_revision=source.plan_revision + 1,
    )
    session.add(branch)
    await session.flush()
    source_note = await session.scalar(select(MemoryNote).where(MemoryNote.run_id == source.id))
    team = await require(session, Team, source.team_id)
    note = MemoryNote(
        workspace_id=team.workspace_id,
        run_id=branch.id,
        scope="dialogue",
        title=f"{source.goal[:230]} · {payload.kind}",
        summary=f"{payload.kind.title()} from message #{point.sequence}",
        content=(source_note.content if source_note else f"# {source.goal}")[-12_000:],
        links=[source_note.id] if source_note else [],
    )
    note.byte_size = len((note.content + note.summary).encode("utf-8"))
    session.add(note)
    previous = list((await session.scalars(select(RunEvent).where(RunEvent.run_id == source.id, RunEvent.sequence <= point.sequence).order_by(RunEvent.sequence))).all())
    for sequence, event in enumerate(previous, start=1):
        session.add(RunEvent(
            run_id=branch.id,
            sequence=sequence,
            type=event.type,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            recipients=list(event.recipients or []),
            payload={**dict(event.payload or {}), "replayed_from_event_id": event.id},
            visibility=event.visibility,
            created_at=event.created_at,
        ))
    source_context["has_branches"] = True
    source.context = source_context
    await session.commit()
    await index_memory_note(session, note)
    if payload.instruction.strip():
        await broker.publish(
            session, run_id=branch.id, event_type="message.human", actor_type="human", recipients=["all"],
            parent_event_id=None, payload={"content": payload.instruction.strip(), "command": "redirect", "branch_instruction": True},
        )
    await broker.publish(
        session, run_id=branch.id, event_type="run.branched", actor_type="system", recipients=["all"],
        payload={"parent_run_id": source.id, "event_id": point.id, "sequence": point.sequence, "kind": payload.kind},
    )
    await runtime.start(branch.id)
    await session.refresh(branch)
    return branch


@router.post("/runs/{run_id}/impersonate", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def impersonate_agent(run_id: str, payload: ImpersonatedAgentMessage, session: AsyncSession = Depends(get_session)):
    run = await require(session, Run, run_id)
    agent = await require(session, Agent, payload.agent_id)
    membership = await session.scalar(select(TeamAgent).where(TeamAgent.team_id == run.team_id, TeamAgent.agent_id == agent.id))
    if not membership:
        raise HTTPException(status_code=422, detail="Agent is not a member of this dialogue team")
    if run.status in {RunStatus.cancelled, RunStatus.failed}:
        raise HTTPException(status_code=409, detail=f"Cannot message a {run.status.value} run")
    # A human instruction is an explicit resume signal.  Previously only a
    # completed run was reopened; a run paused by the budget/loop guard (or
    # waiting for human input) accepted the message but its worker immediately
    # returned because the persisted status was still paused.
    reopened = run.status in {
        RunStatus.completed,
        RunStatus.paused,
        RunStatus.waiting_for_human,
    }
    if reopened:
        run.status = RunStatus.running
        run.finished_at = None
    # Speaking as a teammate is still an operator turn.  Give it a new plan
    # revision even while another provider request is active so the team gets a
    # chance to consider it rather than merely displaying it in the transcript.
    run.plan_revision += 1
    session.add(RunCommand(
        run_id=run.id,
        command="instruction",
        content=f"Colleague {agent.name} adds: {payload.content.strip()}",
        recipients=["all"],
    ))
    await session.commit()
    message = await broker.publish(
        session, run_id=run.id, event_type="message.agent", actor_type="agent", actor_id=agent.id,
        recipients=["all"], payload={
            "content": payload.content.strip(), "role": agent.role, "agent_name": agent.name,
            "impersonated_by_user": True, "usage": {"input_tokens": 0, "output_tokens": 0, "cost_micros": 0},
        },
    )
    await runtime.notify_replan(run.id)
    return message


@router.post("/runs/{run_id}/share", response_model=ReplayShareRead)
async def share_run_replay(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await require(session, Run, run_id)
    context = dict(run.context or {})
    token = str(context.get("replay_token") or secrets.token_urlsafe(18))
    context.update({"replay_token": token, "replay_public": True})
    run.context = context
    await session.commit()
    return ReplayShareRead(token=token, public_url=f"/?replay={token}")


@router.get("/public/replays/{token}", response_model=PublicReplayRead)
async def public_replay(token: str, session: AsyncSession = Depends(get_session)):
    run = await session.scalar(select(Run).where(Run.context["replay_token"].as_string() == token))
    if not run or not bool((run.context or {}).get("replay_public")):
        raise HTTPException(status_code=404, detail="Replay not found")
    team = await session.scalar(select(Team).where(Team.id == run.team_id).options(selectinload(Team.memberships).selectinload(TeamAgent.agent)))
    events = list((await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id, RunEvent.visibility == "shared").order_by(RunEvent.sequence))).all())
    artifacts = list((await session.scalars(select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.created_at))).all())
    verdict_artifact = next(
        (item for item in reversed(artifacts) if item.kind in {"trading_verdict", "verdict"}),
        None,
    )
    return PublicReplayRead(
        run={"id": run.id, "goal": run.goal, "mode": run.mode.value, "status": run.status.value, "created_at": run.created_at.isoformat(), "finished_at": run.finished_at.isoformat() if run.finished_at else None},
        agents=[{"id": member.agent.id, "name": member.agent.name, "role": member.agent.role, "model": member.agent.model} for member in (team.memberships if team else [])],
        events=[{"id": event.id, "sequence": event.sequence, "type": event.type, "actor_type": event.actor_type, "actor_id": event.actor_id, "payload": event.payload, "created_at": event.created_at.isoformat()} for event in events],
        artifacts=[{"id": item.id, "name": item.name, "kind": item.kind, "mime_type": item.mime_type, "content": item.content, "metadata": item.metadata_} for item in artifacts if item.kind in {"working_document", "final_output", "verdict", "trading_verdict", "agent_signal", "protection_report", "decision_record"}],
        verdict=(verdict_artifact.metadata_ if verdict_artifact else None),
    )


@router.post("/replays/{token}/fork", response_model=ReplayForkRead, status_code=201)
async def fork_replay_team(token: str, payload: ReplayForkCreate, session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, payload.workspace_id, write=True)
    if not await session.get(Workspace, payload.workspace_id):
        raise HTTPException(status_code=404, detail="Target workspace not found")
    source_run = await session.scalar(select(Run).where(Run.context["replay_token"].as_string() == token))
    if not source_run or not bool((source_run.context or {}).get("replay_public")):
        raise HTTPException(status_code=404, detail="Replay not found")
    source_team = await session.scalar(
        select(Team).where(Team.id == source_run.team_id).options(selectinload(Team.memberships).selectinload(TeamAgent.agent))
    )
    if not source_team:
        raise HTTPException(status_code=404, detail="Replay team not found")
    suffix = secrets.token_hex(3)
    cloned_agents: list[Agent] = []
    for index, membership in enumerate(source_team.memberships):
        source = membership.agent
        clone = Agent(
            workspace_id=payload.workspace_id,
            connection_id=None,
            name=source.name,
            slug=f"{source.slug[:82]}-fork-{suffix}-{index}",
            role=source.role,
            goal=source.goal,
            system_prompt=f"You are the {source.role} in a forked Orbit team. Work independently and produce verifiable results.",
            skill_name=source.skill_name,
            skill_description=source.skill_description,
            skill_prompt=None,
            adhd_skill_enabled=source.adhd_skill_enabled,
            professional_memory="",
            model="mock-model",
            tools=[],
            capabilities={"forked_from_replay": token, "intended_model": source.model},
            max_turns=source.max_turns,
            token_budget=source.token_budget,
            can_delegate=source.can_delegate,
            can_review=source.can_review,
        )
        session.add(clone);cloned_agents.append(clone)
    await session.flush()
    team = Team(
        workspace_id=payload.workspace_id,
        name=f"{source_team.name[:92]} · Fork",
        goal=source_run.goal,
        mode=source_run.mode,
        supervisor_agent_id=cloned_agents[0].id if cloned_agents else None,
        max_parallel_agents=source_team.max_parallel_agents,
        rules={**dict(source_team.rules or {}), "forked_from_replay": token},
    )
    session.add(team);await session.flush()
    for position, agent in enumerate(cloned_agents):
        session.add(TeamAgent(team_id=team.id, agent_id=agent.id, position=position))
    await session.commit();await session.refresh(team)
    for agent in cloned_agents:
        await session.refresh(agent)
    team_read = TeamRead.model_validate(team).model_copy(update={"agent_ids": [agent.id for agent in cloned_agents]})
    return ReplayForkRead(team=team_read, agents=[AgentRead.model_validate(agent) for agent in cloned_agents], goal=source_run.goal)


@router.get("/runs", response_model=list[RunRead])
async def list_runs(team_id: str = Query(...), session: AsyncSession = Depends(get_session)):
    await require(session, Team, team_id)
    return list(
        (
            await session.scalars(
                select(Run).where(Run.team_id == team_id).order_by(Run.created_at.desc())
            )
        ).all()
    )


@router.post("/runs/{run_id}/pause", status_code=status.HTTP_202_ACCEPTED)
async def pause_run(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    await runtime.pause(run_id)
    return {"status": "paused"}


@router.post("/runs/{run_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await require(session, Run, run_id)
    if run.status not in {RunStatus.created, RunStatus.running}:
        raise HTTPException(status_code=409, detail=f"Cannot start a {run.status.value} run")
    await runtime.start(run_id)
    return {"status": "running"}


@router.post("/runs/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_run(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    await runtime.resume(run_id)
    return {"status": "running"}


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    await runtime.cancel(run_id)
    return {"status": "cancelled"}


@router.post("/runs/{run_id}/messages", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def send_human_message(
    run_id: str, payload: HumanMessage, session: AsyncSession = Depends(get_session)
):
    run = await require(session, Run, run_id)
    if run.status is RunStatus.cancelled:
        raise HTTPException(status_code=409, detail=f"Cannot message a {run.status.value} run")

    # A browser retry or fast double-click must not create two operator turns.
    # Keep the idempotency key in the event payload so this works without a
    # schema migration and remains auditable in the dialogue history.
    if payload.client_message_id:
        recent_messages = list(
            (
                await session.scalars(
                    select(RunEvent)
                    .where(
                        RunEvent.run_id == run_id,
                        RunEvent.type == "message.human",
                        RunEvent.created_at >= datetime.now(timezone.utc) - timedelta(minutes=10),
                    )
                    .order_by(RunEvent.sequence.desc())
                    .limit(25)
                )
            ).all()
        )
        duplicate = next(
            (
                event
                for event in recent_messages
                if (event.payload or {}).get("client_message_id") == payload.client_message_id
            ),
            None,
        )
        if duplicate:
            return duplicate
    await consume_daily_quota(session, kind="message")
    reopened = run.status in {
        RunStatus.completed,
        RunStatus.failed,
        RunStatus.paused,
        RunStatus.waiting_for_human,
    }
    actionable = payload.command in {"instruction", "redirect", "replace_goal", "request_review"}
    # A mention is a routing instruction, not merely a history visibility hint.
    # Persist it on the new turn so the resumed worker executes only the
    # addressed agent(s).  Reset it for redirects too: a preceding direct
    # mention must not accidentally constrain a later team-wide redirect.
    if actionable:
        context = dict(run.context or {})
        context["turn_recipients"] = list(payload.recipients or ["all"])
        if payload.command == "request_review":
            context["turn_review_requested"] = True
        else:
            context.pop("turn_review_requested", None)
        run.context = context
    if reopened:
        # A failed turn is recoverable: the next operator message is a fresh
        # plan revision in the same visible dialogue, not a dead composer.
        # Pending approvals belong to the superseded revision and must not
        # strand the successor worker.
        pending_approvals = list(
            (
                await session.scalars(
                    select(Approval).where(
                        Approval.run_id == run_id,
                        Approval.status == ApprovalStatus.pending,
                    )
                )
            ).all()
        )
        for approval in pending_approvals:
            approval.status = ApprovalStatus.cancelled
            approval.decision_note = "Superseded by a new operator turn"
            approval.decided_at = datetime.now(timezone.utc)
        run.status = RunStatus.running
        run.current_stage = "planning"
        run.finished_at = None
        run.worker_id = None
        run.lease_until = None
    # Revisioning happens when the message is accepted, rather than at a later
    # worker boundary.  This prevents an in-flight worker from completing the
    # old plan around an operator message or redirect.
    if actionable:
        run.plan_revision += 1
    command = RunCommand(
        run_id=run_id,
        command=payload.command,
        content=payload.content,
        recipients=payload.recipients,
        task_id=payload.task_id,
    )
    session.add(command)
    await session.commit()
    message = await broker.publish(
        session,
        run_id=run_id,
        event_type="message.human",
        actor_type="human",
        recipients=payload.recipients,
        task_id=payload.task_id,
        parent_event_id=payload.parent_event_id,
        payload={
            "content": payload.content,
            "command": payload.command,
            "client_message_id": payload.client_message_id,
        },
    )
    for approval in pending_approvals if reopened else []:
        await broker.publish(
            session,
            run_id=run_id,
            event_type="approval.cancelled",
            actor_type="system",
            payload={"approval_id": approval.id, "reason": "superseded_by_new_turn"},
        )
    if reopened:
        await broker.publish(
            session,
            run_id=run_id,
            event_type="run.resumed",
            actor_type="human",
            payload={"status": "running", "reason": "follow_up_message"},
        )
    if actionable:
        await runtime.notify_replan(run_id)
    return message


@router.get("/runs/{run_id}/checkpoints", response_model=list[RunCheckpointRead])
async def list_run_checkpoints(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(RunCheckpoint)
                .where(RunCheckpoint.run_id == run_id)
                .order_by(RunCheckpoint.sequence)
            )
        ).all()
    )


@router.get("/runs/{run_id}/commands", response_model=list[RunCommandRead])
async def list_run_commands(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(RunCommand)
                .where(RunCommand.run_id == run_id)
                .order_by(RunCommand.created_at)
            )
        ).all()
    )


@router.post("/runs/{run_id}/materials", response_model=RunRead)
async def add_dialogue_material(
    run_id: str, payload: DialogueMaterial, session: AsyncSession = Depends(get_session)
):
    run = await require(session, Run, run_id)
    context = dict(run.context or {})
    materials = list(context.get("materials", []))
    materials.append(payload.model_dump())
    context["materials"] = materials[-20:]
    run.context = context
    await session.commit()
    await session.refresh(run)
    await broker.publish(
        session,
        run_id=run.id,
        event_type="context.material_added",
        actor_type="human",
        payload={"name": payload.name, "kind": payload.kind},
    )
    return run


@router.post("/runs/{run_id}/file-assets/{asset_id}", response_model=RunRead)
async def attach_file_asset(
    run_id: str, asset_id: str, session: AsyncSession = Depends(get_session)
):
    run = await require(session, Run, run_id)
    asset = await require(session, FileAsset, asset_id)
    team = await session.get(Team, run.team_id)
    if not team or asset.workspace_id != team.workspace_id:
        raise HTTPException(status_code=422, detail="File and dialogue belong to different workspaces")
    context = dict(run.context or {})
    asset_ids = list(dict.fromkeys([*context.get("file_asset_ids", []), asset.id]))
    context["file_asset_ids"] = asset_ids[-30:]
    run.context = context
    await session.commit()
    await session.refresh(run)
    await broker.publish(
        session,
        run_id=run.id,
        event_type="context.file_attached",
        actor_type="human",
        payload={"file_asset_id": asset.id, "name": asset.name, "size": asset.size},
    )
    return run


@router.post("/runs/{run_id}/mode", response_model=RunRead)
async def change_mode(
    run_id: str, payload: ModeChange, session: AsyncSession = Depends(get_session)
):
    run = await require(session, Run, run_id)
    old_mode = run.mode
    run.mode = payload.mode
    await session.commit()
    await session.refresh(run)
    await broker.publish(
        session,
        run_id=run_id,
        event_type="run.mode_changed",
        actor_type="human",
        recipients=["all"],
        payload={"from": old_mode.value, "to": payload.mode.value},
    )
    return run


@router.get("/runs/{run_id}/events", response_model=list[EventRead])
async def list_events(
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.sequence > after_sequence)
                .order_by(RunEvent.sequence)
                .limit(limit)
            )
        ).all()
    )


@router.get("/runs/{run_id}/stream")
async def stream_events(
    run_id: str,
    after_sequence: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    await require(session, Run, run_id)
    return StreamingResponse(
        broker.subscribe(run_id, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    run_id: str, payload: TaskCreate, session: AsyncSession = Depends(get_session)
):
    await require(session, Run, run_id)
    if payload.assigned_agent_id:
        await require(session, Agent, payload.assigned_agent_id)
    task = Task(run_id=run_id, **payload.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await broker.publish(
        session,
        run_id=run_id,
        event_type="task.created",
        actor_type="human",
        task_id=task.id,
        payload={"title": task.title, "assigned_agent_id": task.assigned_agent_id},
    )
    return task


@router.get("/runs/{run_id}/tasks", response_model=list[TaskRead])
async def list_tasks(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(Task).where(Task.run_id == run_id).order_by(Task.created_at)
            )
        ).all()
    )


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str, payload: TaskUpdate, session: AsyncSession = Depends(get_session)
):
    task = await require(session, Task, task_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(task, key, value)
    await session.commit()
    await session.refresh(task)
    await broker.publish(
        session,
        run_id=task.run_id,
        event_type="task.updated",
        actor_type="human",
        task_id=task.id,
        payload={"changes": {k: getattr(v, "value", v) for k, v in changes.items()}},
    )
    return task


@router.post("/runs/{run_id}/artifacts", response_model=ArtifactRead, status_code=201)
async def create_artifact(
    run_id: str, payload: ArtifactCreate, session: AsyncSession = Depends(get_session)
):
    await require(session, Run, run_id)
    data = payload.model_dump(exclude={"metadata"})
    artifact = Artifact(run_id=run_id, metadata_=payload.metadata, **data)
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    await broker.publish(
        session,
        run_id=run_id,
        event_type="artifact.created",
        actor_type="agent" if artifact.created_by_agent_id else "human",
        actor_id=artifact.created_by_agent_id,
        task_id=artifact.task_id,
        payload={"artifact_id": artifact.id, "name": artifact.name, "kind": artifact.kind},
    )
    return artifact


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at)
            )
        ).all()
    )


@router.post("/runs/{run_id}/approvals", response_model=ApprovalRead, status_code=201)
async def request_approval(
    run_id: str, payload: ApprovalCreate, session: AsyncSession = Depends(get_session)
):
    run = await require(session, Run, run_id)
    approval = Approval(run_id=run_id, **payload.model_dump())
    session.add(approval)
    run.status = RunStatus.waiting_for_human
    await session.commit()
    await session.refresh(approval)
    await broker.publish(
        session,
        run_id=run_id,
        event_type="approval.requested",
        actor_type="agent",
        actor_id=approval.requested_by_agent_id,
        task_id=approval.task_id,
        payload={
            "approval_id": approval.id,
            "action": approval.action,
            "description": approval.description,
            "risk": approval.risk,
        },
    )
    return approval


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalRead])
async def list_approvals(run_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Run, run_id)
    return list(
        (
            await session.scalars(
                select(Approval).where(Approval.run_id == run_id).order_by(Approval.created_at)
            )
        ).all()
    )


@router.post("/approvals/{approval_id}/decision", response_model=ApprovalRead)
async def decide_approval(
    approval_id: str, payload: ApprovalDecision, session: AsyncSession = Depends(get_session)
):
    approval = await require(session, Approval, approval_id)
    if approval.status is not ApprovalStatus.pending:
        raise HTTPException(status_code=409, detail="Approval has already been decided")
    if payload.decision not in {ApprovalStatus.approved, ApprovalStatus.rejected}:
        raise HTTPException(status_code=422, detail="Decision must be approved or rejected")
    approval.status = payload.decision
    approval.decision_note = payload.note
    approval.decided_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(approval)
    await broker.publish(
        session,
        run_id=approval.run_id,
        event_type=f"approval.{payload.decision.value}",
        actor_type="human",
        task_id=approval.task_id,
        payload={"approval_id": approval.id, "note": payload.note},
    )
    tool_call_id = approval.request_payload.get("tool_call_id") if approval.request_payload else None
    if tool_call_id:
        tool_call = await session.get(ToolCall, str(tool_call_id))
        if tool_call:
            if payload.decision is ApprovalStatus.approved:
                await execute_tool_call_record(session, tool_call)
            else:
                tool_call.status = "rejected"
                tool_call.error = payload.note or "Rejected by user"
                tool_call.finished_at = datetime.now(timezone.utc)
                await session.commit()
    # The workflow worker waits on an in-memory gate. Persisting the decision
    # alone leaves the UI forever at waiting_for_approval after a refresh.
    await runtime.resume(approval.run_id)
    return approval


@router.get("/memory", response_model=list[MemoryRead])
async def list_memory(workspace_id: str = Query(...), session: AsyncSession = Depends(get_session)):
    await ensure_workspace_access(session, workspace_id)
    return list(
        (
            await session.scalars(
                select(MemoryNote)
                .where(MemoryNote.workspace_id == workspace_id)
                .order_by(MemoryNote.scope, MemoryNote.updated_at.desc())
            )
        ).all()
    )


@router.post("/memory", response_model=MemoryRead, status_code=201)
async def create_memory(payload: MemoryCreate, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    if payload.run_id:
        await require(session, Run, payload.run_id)
    note = MemoryNote(**payload.model_dump())
    note.byte_size = len((note.content + note.summary).encode("utf-8"))
    session.add(note)
    await session.flush()
    await index_memory_note(session, note)
    await session.commit()
    await session.refresh(note)
    return note


@router.patch("/memory/{memory_id}", response_model=MemoryRead)
async def update_memory(
    memory_id: str, payload: MemoryUpdate, session: AsyncSession = Depends(get_session)
):
    note = await require(session, MemoryNote, memory_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, key, value)
    note.byte_size = len((note.content + note.summary).encode("utf-8"))
    await index_memory_note(session, note)
    await session.commit()
    await session.refresh(note)
    return note


@router.post("/memory/search", response_model=list[MemorySearchResult])
async def search_memory(payload: MemorySearch, session: AsyncSession = Depends(get_session)):
    await require(session, Workspace, payload.workspace_id)
    items = await retrieve_memory(
        session,
        workspace_id=payload.workspace_id,
        query=payload.query,
        exclude_run_id=payload.exclude_run_id,
        limit=payload.limit,
    )
    return [
        MemorySearchResult(
            memory_id=note.id,
            run_id=note.run_id,
            title=note.title,
            content=chunk.content,
            score=score,
            source=chunk.source,
        )
        for chunk, note, score in items
    ]


@router.get("/agents/{agent_id}/lessons", response_model=list[AgentLessonRead])
async def list_agent_lessons(agent_id: str, session: AsyncSession = Depends(get_session)):
    await require(session, Agent, agent_id)
    return list(
        (
            await session.scalars(
                select(AgentLesson)
                .where(AgentLesson.agent_id == agent_id)
                .order_by(AgentLesson.created_at.desc())
            )
        ).all()
    )


@router.post("/agent-lessons/{lesson_id}/decision", response_model=AgentLessonRead)
async def decide_agent_lesson(
    lesson_id: str, payload: AgentLessonDecision, session: AsyncSession = Depends(get_session)
):
    lesson = await require(session, AgentLesson, lesson_id)
    if lesson.status == "accepted" and payload.status == "accepted":
        return lesson
    lesson.status = payload.status
    lesson.reviewed_at = datetime.now(timezone.utc)
    lesson.confidence = 90 if payload.status == "accepted" else 0
    if payload.status == "accepted":
        agent = await require(session, Agent, lesson.agent_id)
        block = f"\n\n## Verified lesson\n{lesson.lesson[:900]}\nSource: {lesson.evidence}"
        agent.professional_memory = (agent.professional_memory + block)[-8000:]
        agent.lessons_count += 1
        agent.experience_level = 1 + agent.lessons_count // 5
    await session.commit()
    await session.refresh(lesson)
    return lesson
