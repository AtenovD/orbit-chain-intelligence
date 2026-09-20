from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orchestrator.db import Base


def uuid4_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InteractionMode(str, enum.Enum):
    standard = "standard"
    constructive = "constructive"


class RunStatus(str, enum.Enum):
    created = "created"
    running = "running"
    paused = "paused"
    waiting_for_human = "waiting_for_human"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskStatus(str, enum.Enum):
    backlog = "backlog"
    ready = "ready"
    in_progress = "in_progress"
    review = "review"
    blocked = "blocked"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agents: Mapped[list[Agent]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    teams: Mapped[list[Team]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    tokens: Mapped[list[Token]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class Token(Base):
    """A workspace-scoped on-chain asset tracked by Orbit.

    Addresses are stored in normalized lowercase form by the API.  The unique
    key therefore represents one asset on one chain, while labels and watchlist
    state remain workspace-local preferences.
    """

    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("workspace_id", "chain_id", "address", name="uq_token_workspace_chain_address"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    address: Mapped[str] = mapped_column(String(256))
    chain_id: Mapped[int] = mapped_column(Integer, default=4663)
    asset_kind: Mapped[str] = mapped_column(String(16), default="token")
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    watchlist: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="tokens")
    verdicts: Mapped[list[TokenVerdict]] = relationship(
        back_populates="token", cascade="all, delete-orphan", order_by="TokenVerdict.created_at.desc()"
    )
    observations: Mapped[list[MarketObservation]] = relationship(
        back_populates="token", cascade="all, delete-orphan", order_by="MarketObservation.observed_at.desc()"
    )
    paper_trades: Mapped[list[PaperTrade]] = relationship(
        back_populates="token", cascade="all, delete-orphan", order_by="PaperTrade.created_at.desc()"
    )
    evaluations: Mapped[list[DecisionEvaluation]] = relationship(
        back_populates="token", cascade="all, delete-orphan", order_by="DecisionEvaluation.created_at.desc()"
    )


class TokenVerdict(Base):
    """Immutable agent or operator assessment attached to a tracked token."""

    __tablename__ = "token_verdicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    token_id: Mapped[str] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True)
    artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verdict: Mapped[str] = mapped_column(String(80), default="unknown")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    token: Mapped[Token] = relationship(back_populates="verdicts")
    paper_trades: Mapped[list[PaperTrade]] = relationship(back_populates="verdict")
    evaluations: Mapped[list[DecisionEvaluation]] = relationship(
        back_populates="verdict", cascade="all, delete-orphan"
    )


class MarketObservation(Base):
    """Source-bound market fact used by replay and paper execution.

    ``trade`` observations come from executed swaps and are eligible for fills.
    ``mark`` observations are useful for monitoring but cannot silently become
    an executable price.
    """

    __tablename__ = "market_observations"
    __table_args__ = (
        UniqueConstraint("token_id", "source", "source_ref", name="uq_market_observation_source_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    token_id: Mapped[str] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Float)
    quote_symbol: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    kind: Mapped[str] = mapped_column(String(20), default="trade", index=True)
    source: Mapped[str] = mapped_column(String(160))
    source_ref: Mapped[str] = mapped_column(String(500))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    token: Mapped[Token] = relationship(back_populates="observations")


class PaperTrade(Base):
    """Dry-run position. It never authorises or represents a real transaction."""

    __tablename__ = "paper_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    token_id: Mapped[str] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    verdict_id: Mapped[str | None] = mapped_column(
        ForeignKey("token_verdicts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True)
    decision: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    quote_symbol: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    notional: Mapped[float] = mapped_column(Float, default=1000.0)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_observations.id", ondelete="SET NULL"), nullable=True
    )
    exit_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_observations.id", ondelete="SET NULL"), nullable=True
    )
    fee_bps: Mapped[float] = mapped_column(Float, default=10.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=25.0)
    fees_paid: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    token: Mapped[Token] = relationship(back_populates="paper_trades")
    verdict: Mapped[TokenVerdict | None] = relationship(back_populates="paper_trades")


class DecisionEvaluation(Base):
    """Immutable, leakage-resistant measurement of a historical decision."""

    __tablename__ = "decision_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    token_id: Mapped[str] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    verdict_id: Mapped[str] = mapped_column(
        ForeignKey("token_verdicts.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="complete", index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    horizon_seconds: Mapped[int] = mapped_column(Integer)
    entry_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_observations.id", ondelete="SET NULL"), nullable=True
    )
    exit_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("market_observations.id", ondelete="SET NULL"), nullable=True
    )
    benchmark_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_favorable_excursion_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_adverse_excursion_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    token: Mapped[Token] = relationship(back_populates="evaluations")
    verdict: Mapped[TokenVerdict] = relationship(back_populates="evaluations")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    twitter_user_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True, index=True)
    twitter_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    twitter_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyVisit(Base):
    """Privacy-preserving daily activity counter; no raw visitor identifier."""

    __tablename__ = "daily_visits"
    __table_args__ = (UniqueConstraint("day", "visitor_hash", name="uq_daily_visit"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    visitor_hash: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailyUsage(Base):
    """Per-account daily spend gate; durable so a restart cannot reset someone's quota."""

    __tablename__ = "daily_usage"
    __table_args__ = (UniqueConstraint("day", "user_id", name="uq_daily_usage"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    research_count: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiRateLimit(Base):
    """Durable fixed-window counter shared by every API process."""

    __tablename__ = "api_rate_limits"
    __table_args__ = (UniqueConstraint("scope", "subject_hash", "window_started_at", name="uq_rate_limit_window"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    scope: Mapped[str] = mapped_column(String(100), index=True)
    subject_hash: Mapped[str] = mapped_column(String(64), index=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProviderConnection(Base):
    __tablename__ = "provider_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_agent_workspace_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(160))
    goal: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    skill_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    skill_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    adhd_skill_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    professional_memory: Mapped[str] = mapped_column(Text, default="")
    lessons_count: Mapped[int] = mapped_column(Integer, default=0)
    experience_level: Mapped[int] = mapped_column(Integer, default=1)
    model: Mapped[str] = mapped_column(String(160), default="mock-model")
    tools: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    max_turns: Mapped[int] = mapped_column(Integer, default=8)
    token_budget: Mapped[int] = mapped_column(Integer, default=20_000)
    can_delegate: Mapped[bool] = mapped_column(Boolean, default=True)
    can_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="agents")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    goal: Mapped[str] = mapped_column(Text)
    mode: Mapped[InteractionMode] = mapped_column(Enum(InteractionMode), default=InteractionMode.standard)
    supervisor_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    max_parallel_agents: Mapped[int] = mapped_column(Integer, default=3)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    workspace: Mapped[Workspace] = relationship(back_populates="teams")
    memberships: Mapped[list[TeamAgent]] = relationship(
        back_populates="team", cascade="all, delete-orphan", order_by="TeamAgent.position"
    )


class TeamAgent(Base):
    __tablename__ = "team_agents"
    __table_args__ = (UniqueConstraint("team_id", "agent_id", name="uq_team_agent"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    team: Mapped[Team] = relationship(back_populates="memberships")
    agent: Mapped[Agent] = relationship()


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    edges: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True)
    goal: Mapped[str] = mapped_column(Text)
    mode: Mapped[InteractionMode] = mapped_column(Enum(InteractionMode))
    status: Mapped[RunStatus] = mapped_column(Enum(RunStatus), default=RunStatus.created)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    runtime_version: Mapped[str] = mapped_column(String(20), default="v2", index=True)
    plan_revision: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str] = mapped_column(String(80), default="created")
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    parent_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.backlog)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(80), index=True)
    actor_type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recipients: Mapped[list[str]] = mapped_column(JSON, default=list)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    parent_event_id: Mapped[str | None] = mapped_column(ForeignKey("run_events.id", ondelete="SET NULL"), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    visibility: Mapped[str] = mapped_column(String(30), default="shared")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    created_by_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(80), default="text")
    mime_type: Mapped[str] = mapped_column(String(160), default="text/plain")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    requested_by_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(String(40), default="medium")
    status: Mapped[ApprovalStatus] = mapped_column(Enum(ApprovalStatus), default=ApprovalStatus.pending)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryNote(Base):
    __tablename__ = "memory_notes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "scope", "run_id", name="uq_memory_scope_run"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(30), default="dialogue")
    title: Mapped[str] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    links: Mapped[list[str]] = mapped_column(JSON, default=list)
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    depth: Mapped[str] = mapped_column(String(20), default="deep")
    requested_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_status: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    report: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunCheckpoint(Base):
    """Durable cursor for the orchestration state machine.

    A checkpoint is deliberately append-only.  This makes a run recoverable after a
    process restart and gives the UI an auditable history of plan revisions.
    """

    __tablename__ = "run_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_run_checkpoint_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(80))
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunCommand(Base):
    __tablename__ = "run_commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    command: Mapped[str] = mapped_column(String(50), default="instruction")
    content: Mapped[str] = mapped_column(Text, default="")
    recipients: Mapped[list[str]] = mapped_column(JSON, default=list)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    __table_args__ = (UniqueConstraint("task_id", "attempt", name="uq_task_attempt"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="running")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="SET NULL"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(180))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="requested", index=True)
    risk: Mapped[str] = mapped_column(String(30), default="read")
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memory_notes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)
    source: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentLesson(Base):
    __tablename__ = "agent_lessons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    lesson: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    confidence: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileAsset(Base):
    __tablename__ = "file_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(160))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(1000))
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="ready", index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
