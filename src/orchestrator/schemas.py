from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from orchestrator.models import ApprovalStatus, InteractionMode, RunStatus, TaskStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceRead(ORMModel):
    id: str
    name: str
    created_at: datetime


class TokenCreate(BaseModel):
    workspace_id: str
    address: str = Field(min_length=1, max_length=256)
    chain_id: int = Field(default=4663, ge=1, le=2_147_483_647)
    asset_kind: str = Field(default="token", pattern=r"^(token|nft)$")
    label: str | None = Field(default=None, max_length=160)
    symbol: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=300)
    watchlist: bool = False

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            len(normalized) != 42
            or not normalized.startswith("0x")
            or any(char not in "0123456789abcdef" for char in normalized[2:])
        ):
            raise ValueError("Address must be a 20-byte 0x address")
        return normalized

    @field_validator("label", "symbol", "name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class TokenUpdate(BaseModel):
    address: str | None = Field(default=None, min_length=1, max_length=256)
    chain_id: int | None = Field(default=None, ge=1, le=2_147_483_647)
    asset_kind: str | None = Field(default=None, pattern=r"^(token|nft)$")
    label: str | None = Field(default=None, max_length=160)
    symbol: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=300)
    watchlist: bool | None = None

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Address cannot be null")
        normalized = value.strip().lower()
        if (
            len(normalized) != 42
            or not normalized.startswith("0x")
            or any(char not in "0123456789abcdef" for char in normalized[2:])
        ):
            raise ValueError("Address must be a 20-byte 0x address")
        return normalized

    @field_validator("chain_id")
    @classmethod
    def require_chain_id(cls, value: int | None) -> int:
        if value is None:
            raise ValueError("Chain id cannot be null")
        return value

    @field_validator("watchlist")
    @classmethod
    def require_watchlist(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Watchlist cannot be null")
        return value

    @field_validator("label", "symbol", "name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class TokenRead(ORMModel):
    id: str
    workspace_id: str
    address: str
    chain_id: int
    asset_kind: str
    label: str | None
    symbol: str | None
    name: str | None
    watchlist: bool
    created_at: datetime
    updated_at: datetime


class TokenVerdictCreate(BaseModel):
    verdict: str = Field(default="unknown", min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    artifact_id: str | None = None

    @field_validator("verdict")
    @classmethod
    def normalize_verdict(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Verdict must not be empty")
        return normalized


class TokenVerdictRead(ORMModel):
    id: str
    token_id: str
    run_id: str | None
    artifact_id: str | None
    verdict: str
    payload: dict[str, Any]
    created_at: datetime


class MarketObservationCreate(BaseModel):
    price: float = Field(gt=0)
    quote_symbol: str = Field(default="UNKNOWN", min_length=1, max_length=40)
    kind: str = Field(default="trade", pattern=r"^(trade|mark)$")
    source: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=1, max_length=500)
    observed_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quote_symbol", "source", "source_ref")
    @classmethod
    def normalize_observation_text(cls, value: str) -> str:
        return value.strip()


class MarketObservationCapture(BaseModel):
    blocks: int = Field(default=600, ge=10, le=2000)
    interval_blocks: int = Field(default=50, ge=1, le=2000)


class MarketObservationRead(ORMModel):
    id: str
    token_id: str
    price: float
    quote_symbol: str
    kind: str
    source: str
    source_ref: str
    observed_at: datetime
    payload: dict[str, Any]
    created_at: datetime


class DecisionReplayCreate(BaseModel):
    verdict_id: str
    horizon_seconds: int = Field(default=86400, ge=60, le=31_536_000)
    fee_bps: float = Field(default=10, ge=0, le=1000)
    slippage_bps: float = Field(default=25, ge=0, le=5000)
    watch_band_pct: float = Field(default=3, ge=0, le=100)
    source: str | None = Field(default=None, max_length=160)


class DecisionEvaluationRead(ORMModel):
    id: str
    token_id: str
    verdict_id: str
    decision: str
    status: str
    outcome: str
    horizon_seconds: int
    entry_observation_id: str | None
    exit_observation_id: str | None
    benchmark_return_pct: float | None
    strategy_return_pct: float | None
    max_favorable_excursion_pct: float | None
    max_adverse_excursion_pct: float | None
    payload: dict[str, Any]
    created_at: datetime


class PaperTradeCreate(BaseModel):
    verdict_id: str
    notional: float = Field(default=1000, gt=0, le=100_000_000)
    fee_bps: float = Field(default=10, ge=0, le=1000)
    slippage_bps: float = Field(default=25, ge=0, le=5000)
    entry_observation_id: str | None = None


class PaperTradeClose(BaseModel):
    exit_observation_id: str
    close_reason: str = Field(default="manual", min_length=1, max_length=300)


class PaperTradeRead(ORMModel):
    id: str
    token_id: str
    verdict_id: str | None
    run_id: str | None
    decision: str
    status: str
    quote_symbol: str
    notional: float
    quantity: float | None
    entry_price: float | None
    exit_price: float | None
    entry_observation_id: str | None
    exit_observation_id: str | None
    fee_bps: float
    slippage_bps: float
    fees_paid: float
    realized_pnl: float | None
    return_pct: float | None
    opened_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AgentDecisionScorecard(BaseModel):
    agent_id: str
    agent_name: str
    model: str
    signals: int
    resolved_decisions: int
    directional_signals: int
    correct: int
    incorrect: int
    hit_rate: float | None
    brier_score: float | None
    average_confidence: float | None


class DecisionQualityRead(BaseModel):
    contract_version: str
    resolved_decisions: int
    scorecards: list[AgentDecisionScorecard]
    notes: list[str]


class WorkspaceMemberCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role: str = Field(default="member", pattern=r"^(admin|member|viewer)$")


class WorkspaceOwnershipTransfer(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class WorkspaceMemberRead(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    created_at: datetime


class AuthRegister(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=200)


class AuthLogin(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class UserRead(ORMModel):
    id: str
    email: str
    display_name: str
    enabled: bool
    is_superuser: bool = False
    email_verified: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime


class AuthRead(BaseModel):
    token: str
    expires_at: datetime
    user: UserRead
    verification_required: bool = False
    debug_verification_token: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    current_password: str | None = Field(default=None, max_length=200)
    new_password: str | None = Field(default=None, min_length=10, max_length=200)


class AccountDelete(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AuthSessionRead(ORMModel):
    id: str
    expires_at: datetime
    created_at: datetime
    current: bool = False


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class PasswordResetRequestRead(BaseModel):
    message: str
    debug_token: str | None = None


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=500)
    new_password: str = Field(min_length=10, max_length=200)


class EmailVerificationConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class ConnectionCreate(BaseModel):
    workspace_id: str
    name: str
    provider: str
    base_url: str | None = None
    api_key: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ConnectionRead(ORMModel):
    id: str
    workspace_id: str
    name: str
    provider: str
    base_url: str | None
    enabled: bool
    config: dict[str, Any]
    created_at: datetime

    @field_serializer("config")
    def safe_config(self, value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: item
            for key, item in value.items()
            if "secret" not in key.lower() and "token" not in key.lower()
        }


class ConnectionDiscover(BaseModel):
    provider: str = "openai-compatible"
    base_url: str
    api_key: str | None = None


class DiscoveredModel(BaseModel):
    id: str
    name: str
    owner: str | None = None
    context_length: int | None = None


class ConnectionDiscovery(BaseModel):
    ok: bool
    latency_ms: int
    models: list[DiscoveredModel]
    model_count: int
    base_url: str | None = None


class GitHubConnect(BaseModel):
    workspace_id: str
    token: str = Field(min_length=1)


class GitHubSyncRead(BaseModel):
    connection: ConnectionRead
    login: str
    repository_count: int
    memory_note_id: str


class TwitterConnect(BaseModel):
    workspace_id: str
    token: str = Field(min_length=1)


class TwitterOAuthStartRead(BaseModel):
    authorization_url: str
    callback_url: str


class TwitterAuthSync(BaseModel):
    workspace_id: str


class GoogleModelOAuthStartRead(BaseModel):
    authorization_url: str
    callback_url: str


class TwitterSyncRead(BaseModel):
    connection: ConnectionRead
    username: str
    posts_count: int
    timeline_available: bool
    memory_note_id: str


class ContextConnectorConnect(BaseModel):
    workspace_id: str
    connector: str = Field(pattern=r"^(notion|slack|google-drive|telegram|youtube|bitquery|blockscout)$")
    credential: str = Field(default="", max_length=5000)
    identifier: str | None = Field(default=None, max_length=300)


class ContextConnectorSyncRead(BaseModel):
    connection: ConnectionRead
    label: str
    item_count: int
    memory_note_id: str


class ContextConnectorOAuthStartRead(BaseModel):
    authorization_url: str
    callback_url: str


class GitHubRepositoryQuery(BaseModel):
    workspace_id: str
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    ref: str | None = None


class GitHubFileQuery(GitHubRepositoryQuery):
    path: str = Field(min_length=1, max_length=2000)


class GitHubCodeSearch(GitHubRepositoryQuery):
    query: str = Field(min_length=2, max_length=500)


class MCPInstall(BaseModel):
    workspace_id: str
    preset_id: str
    name: str | None = None
    transport: str | None = Field(default=None, pattern=r"^(stdio|streamable_http|sse)$")
    url: str | None = None
    command: str | None = None
    args: list[str] | None = None
    secret: str | None = None
    extra_config: dict[str, Any] = Field(default_factory=dict)


class MCPToolRead(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCallCreate(BaseModel):
    connection_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None
    task_id: str | None = None
    risk: str = Field(default="read", pattern=r"^(read|write|destructive|external)$")


class ToolCallRead(ORMModel):
    id: str
    run_id: str
    task_id: str | None
    agent_id: str | None
    connection_id: str | None
    tool_name: str
    arguments: dict[str, Any]
    status: str
    risk: str
    result: dict[str, Any]
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class AgentCreate(BaseModel):
    workspace_id: str
    connection_id: str | None = None
    name: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    role: str
    goal: str
    system_prompt: str
    skill_name: str | None = Field(default=None, max_length=120)
    skill_description: str | None = None
    skill_prompt: str | None = None
    adhd_skill_enabled: bool = True
    professional_memory: str = ""
    model: str = "mock-model"
    tools: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    max_turns: int = Field(default=8, ge=1, le=100)
    token_budget: int = Field(default=20_000, ge=100)
    can_delegate: bool = True
    can_review: bool = False


class AgentUpdate(BaseModel):
    connection_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    goal: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    skill_name: str | None = Field(default=None, max_length=120)
    skill_description: str | None = None
    skill_prompt: str | None = None
    adhd_skill_enabled: bool | None = None
    professional_memory: str | None = None
    can_delegate: bool | None = None
    can_review: bool | None = None


class AgentRead(ORMModel):
    id: str
    workspace_id: str
    connection_id: str | None
    name: str
    slug: str
    role: str
    goal: str
    system_prompt: str
    skill_name: str | None
    skill_description: str | None
    skill_prompt: str | None
    adhd_skill_enabled: bool
    professional_memory: str
    lessons_count: int
    experience_level: int
    model: str
    tools: list[dict[str, Any]]
    capabilities: dict[str, Any]
    max_turns: int
    token_budget: int
    can_delegate: bool
    can_review: bool
    created_at: datetime


class TeamCreate(BaseModel):
    workspace_id: str
    name: str
    goal: str
    mode: InteractionMode = InteractionMode.standard
    agent_ids: list[str] = Field(min_length=1, max_length=10)
    supervisor_agent_id: str | None = None
    max_parallel_agents: int = Field(default=3, ge=1, le=20)
    rules: dict[str, Any] = Field(default_factory=dict)


class TeamRead(ORMModel):
    id: str
    workspace_id: str
    name: str
    goal: str
    mode: InteractionMode
    supervisor_agent_id: str | None
    max_parallel_agents: int
    rules: dict[str, Any]
    agent_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class TeamMemberAdd(BaseModel):
    agent_id: str


class WorkflowCreate(BaseModel):
    workspace_id: str
    team_id: str | None = None
    name: str
    description: str = ""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    team_id: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    published: bool | None = None


class WorkflowRead(ORMModel):
    id: str
    workspace_id: str
    team_id: str | None
    name: str
    description: str
    version: int
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    published: bool
    created_at: datetime
    updated_at: datetime


class WorkflowValidation(BaseModel):
    valid: bool
    errors: list[dict[str, str]]
    warnings: list[dict[str, str]]


class RunCreate(BaseModel):
    team_id: str
    workflow_id: str | None = None
    goal: str | None = None
    mode: InteractionMode | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    auto_start: bool = True


class RunRead(ORMModel):
    id: str
    team_id: str
    workflow_id: str | None
    goal: str
    mode: InteractionMode
    status: RunStatus
    context: dict[str, Any]
    runtime_version: str
    plan_revision: int
    current_stage: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_micros: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    last_checkpoint_at: datetime | None


class RunMetaUpdate(BaseModel):
    pinned: bool | None = None
    archived: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)


class RunParticipantsUpdate(BaseModel):
    agent_ids: list[str] = Field(min_length=1, max_length=10)


class RunMemoryMerge(BaseModel):
    target_run_id: str


class RunBudgetUpdate(BaseModel):
    token_limit: int | None = Field(default=None, ge=1_000, le=10_000_000)
    cost_limit_micros: int | None = Field(default=None, ge=0, le=10_000_000_000)
    max_rounds: int | None = Field(default=None, ge=1, le=100)


class RunBranchCreate(BaseModel):
    event_id: str
    instruction: str = Field(default="", max_length=20_000)
    kind: str = Field(default="fork", pattern=r"^(fork|rewind)$")


class ImpersonatedAgentMessage(BaseModel):
    agent_id: str
    content: str = Field(min_length=1, max_length=20_000)


class ReplayShareRead(BaseModel):
    token: str
    public_url: str


class ReplayForkCreate(BaseModel):
    workspace_id: str


class ReplayForkRead(BaseModel):
    team: TeamRead
    agents: list[AgentRead]
    goal: str


class PublicReplayRead(BaseModel):
    run: dict[str, Any]
    agents: list[dict[str, Any]]
    events: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    verdict: dict[str, Any] | None = None


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    assigned_agent_id: str | None = None
    parent_task_id: str | None = None
    priority: int = 0


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_agent_id: str | None = None
    status: TaskStatus | None = None
    priority: int | None = None


class TaskRead(ORMModel):
    id: str
    run_id: str
    parent_task_id: str | None
    assigned_agent_id: str | None
    title: str
    description: str
    status: TaskStatus
    priority: int
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class HumanMessage(BaseModel):
    content: str = Field(min_length=1)
    recipients: list[str] = Field(default_factory=lambda: ["all"])
    client_message_id: str | None = Field(default=None, min_length=8, max_length=100)
    command: str = Field(
        default="instruction",
        pattern=r"^(instruction|redirect|replace_goal|pause|cancel|request_review)$",
    )
    task_id: str | None = None
    parent_event_id: str | None = None


class DialogueMaterial(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=250_000)
    kind: str = Field(default="text", pattern=r"^(text|markdown|code|link|transcript)$")


class ModeChange(BaseModel):
    mode: InteractionMode


class EventRead(ORMModel):
    id: str
    run_id: str
    sequence: int
    type: str
    actor_type: str
    actor_id: str | None
    recipients: list[str]
    task_id: str | None
    parent_event_id: str | None
    payload: dict[str, Any]
    visibility: str
    created_at: datetime


class ArtifactCreate(BaseModel):
    name: str
    kind: str = "text"
    mime_type: str = "text/plain"
    content: str | None = None
    uri: str | None = None
    task_id: str | None = None
    created_by_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRead(ORMModel):
    id: str
    run_id: str
    task_id: str | None
    created_by_agent_id: str | None
    name: str
    kind: str
    mime_type: str
    content: str | None
    uri: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime


class ApprovalCreate(BaseModel):
    action: str
    description: str
    risk: str = "medium"
    task_id: str | None = None
    requested_by_agent_id: str | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: ApprovalStatus
    note: str | None = None


class ApprovalRead(ORMModel):
    id: str
    run_id: str
    task_id: str | None
    requested_by_agent_id: str | None
    action: str
    description: str
    risk: str
    status: ApprovalStatus
    request_payload: dict[str, Any]
    decision_note: str | None
    decided_at: datetime | None
    created_at: datetime


class MemoryCreate(BaseModel):
    workspace_id: str
    run_id: str | None = None
    scope: str = Field(default="dialogue", pattern=r"^(global|dialogue)$")
    title: str
    content: str = ""
    summary: str = ""
    links: list[str] = Field(default_factory=list)


class MemoryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    links: list[str] | None = None


class MemoryRead(ORMModel):
    id: str
    workspace_id: str
    run_id: str | None
    scope: str
    title: str
    content: str
    summary: str
    links: list[str]
    byte_size: int
    created_at: datetime
    updated_at: datetime


class MemorySearch(BaseModel):
    workspace_id: str
    query: str = Field(min_length=2, max_length=2000)
    exclude_run_id: str | None = None
    limit: int = Field(default=8, ge=1, le=30)


class MemorySearchResult(BaseModel):
    memory_id: str
    run_id: str | None
    title: str
    content: str
    score: float
    source: dict[str, Any]


class RunCheckpointRead(ORMModel):
    id: str
    run_id: str
    sequence: int
    stage: str
    state: dict[str, Any]
    created_at: datetime


class RunCommandRead(ORMModel):
    id: str
    run_id: str
    command: str
    content: str
    recipients: list[str]
    task_id: str | None
    status: str
    result: dict[str, Any]
    created_at: datetime
    handled_at: datetime | None


class AgentLessonRead(ORMModel):
    id: str
    agent_id: str
    run_id: str | None
    task_id: str | None
    lesson: str
    evidence: str
    status: str
    confidence: int
    created_at: datetime
    reviewed_at: datetime | None


class AgentLessonDecision(BaseModel):
    status: str = Field(pattern=r"^(accepted|rejected)$")


class FileAssetRead(ORMModel):
    id: str
    workspace_id: str
    uploaded_by_user_id: str | None
    name: str
    mime_type: str
    size: int
    sha256: str
    status: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    created_at: datetime


class ResearchCreate(BaseModel):
    workspace_id: str
    query: str = Field(min_length=3)
    sources: list[str] = Field(default_factory=lambda: ["web", "youtube", "tiktok", "instagram"])
    depth: str = Field(default="deep", pattern=r"^(quick|deep)$")


class ResearchRead(ORMModel):
    id: str
    workspace_id: str
    query: str
    status: str
    depth: str
    requested_sources: list[str]
    source_status: dict[str, Any]
    findings: list[dict[str, Any]]
    report: str
    created_at: datetime
