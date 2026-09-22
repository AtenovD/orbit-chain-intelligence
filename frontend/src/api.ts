import type {
  Agent,
  Approval,
  Artifact,
  Connection,
  ConnectionDiscovery,
  FileAsset,
  MCPPreset,
  MemoryNote,
  Mode,
  MarketObservation,
  DecisionEvaluation,
  PaperTrade,
  DecisionQuality,
  PublicReplay,
  ResearchReport,
  Run,
  RunEvent,
  Task,
  Team,
  Token,
  TokenVerdict,
  Workflow,
  Workspace,
} from "./types";

const API = import.meta.env.VITE_API_URL || "/api/v1";
const authToken = () =>
  typeof localStorage === "undefined"
    ? null
    : localStorage.getItem("orbit-auth-token");

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export type DeploymentCapabilities = {
  auth: { password: boolean; google: boolean; twitter: boolean; password_recovery_email: boolean };
  connectors: Record<string, boolean>;
  research: Record<string, boolean>;
};

export type AdminUser = {
  id: string; email: string; display_name: string; enabled: boolean; is_superuser: boolean;
  email_verified: boolean; created_at: string; last_seen_at: string | null; last_login_at: string | null;
  runs: number; cost_micros: number; input_tokens: number;
};
export type AdminOverview = {
  summary: { total_users: number; registrations_7: number; registrations_30: number; dau: number; live_sessions: number; runs_today: number; spend_month_micros: number; activation_users: number; activation_rate: number; total_runs: number; failed_runs: number; failure_rate: number; visitors_7: number; visitors_delta: number | null; requests_7: number; requests_delta: number | null; bounce_rate_7: number; bounce_delta: number | null };
  timeline: Array<{ day: string; registrations: number; active: number; logins: number }>;
  users: AdminUser[];
  recent_runs: Array<{ id: string; goal: string; status: string; created_at: string; cost_micros: number; owner_email: string | null }>;
  top_tokens: Array<{ symbol: string | null; name: string | null; address: string; verdicts: number }>;
  verdict_distribution: Record<string, number>;
};

export type SessionUser = {
  id: string; email: string; display_name: string; email_verified: boolean; is_superuser: boolean;
  is_guest?: boolean; wallet_address?: string | null;
};
export type WalletNonce = { nonce: string; domain: string; uri: string; chain_id: number; issued_at: string; expires_at: string };
export type WalletAuthResult = { token: string; expires_at: string; user: SessionUser };

let authenticationRequiredHandler: (() => void) | null = null;
export function setAuthenticationRequiredHandler(handler: (() => void) | null) {
  authenticationRequiredHandler = handler;
  return () => {
    if (authenticationRequiredHandler === handler)
      authenticationRequiredHandler = null;
  };
}

function requestError(path: string, status: number, message: string) {
  if (status === 401 && !path.startsWith("/auth/"))
    authenticationRequiredHandler?.();
  return new ApiRequestError(message, status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = authToken();
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body: { detail?: unknown; message?: unknown } = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const message =
      typeof body.message === "string"
        ? body.message
        : typeof body.detail === "string"
          ? body.detail
          : "Request could not be completed";
    throw requestError(path, response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const token = authToken();
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    body,
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    const value: { detail?: unknown; message?: unknown } = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const message =
      typeof value.message === "string"
        ? value.message
        : typeof value.detail === "string"
          ? value.detail
          : "File upload failed";
    throw requestError(path, response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  capabilities: () => request<DeploymentCapabilities>("/auth/capabilities"),
  startGoogleAuth: () =>
    request<{ authorization_url: string; callback_url: string }>(
      "/auth/google/start",
    ),
  startTwitterAuth: () =>
    request<{ authorization_url: string; callback_url: string }>(
      "/auth/twitter/start",
    ),
  syncTwitterLogin: (workspaceId: string) =>
    request(`/auth/twitter/sync`, {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId }),
    }),
  register: (data: { email: string; display_name: string; password: string }) =>
    request<{
      token: string;
      expires_at: string;
      user: { id: string; email: string; display_name: string; email_verified: boolean; is_superuser: boolean };
      verification_required: boolean;
      debug_verification_token: string | null;
    }>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) =>
    request<{
      token: string;
      expires_at: string;
      user: { id: string; email: string; display_name: string; email_verified: boolean; is_superuser: boolean };
      verification_required: boolean;
    }>("/auth/login", { method: "POST", body: JSON.stringify(data) }),
  me: () => request<SessionUser>("/auth/me"),
  guest: () => request<WalletAuthResult>("/auth/guest", { method: "POST" }),
  walletNonce: () => request<WalletNonce>("/auth/wallet/nonce", { method: "POST" }),
  walletVerify: (message: string, signature: string) =>
    request<WalletAuthResult>("/auth/wallet/verify", { method: "POST", body: JSON.stringify({ message, signature }) }),
  unlinkWallet: () => request<SessionUser>("/auth/wallet", { method: "DELETE" }),
  requestEmailVerification: () => request<{ message: string; debug_token: string | null }>("/auth/email-verification/request", { method: "POST" }),
  confirmEmailVerification: (token: string) => request<void>("/auth/email-verification/confirm", {
    method: "POST", body: JSON.stringify({ token }),
  }),
  adminOverview: () => request<AdminOverview>("/admin/overview"),
  updateAdminUser: (id: string, enabled: boolean) =>
    request<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  updateMe: (data: {
    display_name?: string;
    current_password?: string;
    new_password?: string;
  }) =>
    request<{ id: string; email: string; display_name: string }>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  authSessions: () =>
    request<
      Array<{
        id: string;
        created_at: string;
        expires_at: string;
        current: boolean;
      }>
    >("/auth/sessions"),
  revokeSession: (id: string) =>
    request<void>(`/auth/sessions/${id}`, { method: "DELETE" }),
  requestPasswordReset: (email: string) =>
    request<{ message: string; debug_token: string | null }>(
      "/auth/password-reset/request",
      { method: "POST", body: JSON.stringify({ email }) },
    ),
  confirmPasswordReset: (token: string, newPassword: string) =>
    request<void>("/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
  deleteAccount: (password: string) =>
    request<void>("/auth/me", {
      method: "DELETE",
      body: JSON.stringify({ password }),
    }),
  workspaces: () => request<Workspace[]>("/workspaces"),
  createWorkspace: (name: string) =>
    request<Workspace>("/workspaces", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  decisionQuality: (workspaceId: string) =>
    request<DecisionQuality>(`/workspaces/${workspaceId}/decision-quality`),
  connections: (workspaceId: string) =>
    request<Connection[]>(`/connections?workspace_id=${workspaceId}`),
  createConnection: (data: Record<string, unknown>) =>
    request<Connection>("/connections", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteConnection: (connectionId: string) =>
    request<void>(`/connections/${connectionId}`, { method: "DELETE" }),
  discoverConnection: (data: {
    provider: string;
    base_url: string;
    api_key: string;
  }) =>
    request<ConnectionDiscovery>("/connections/discover", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  startGitHubOAuth: (workspaceId: string) =>
    request<{ authorization_url: string; callback_url: string }>(
      `/integrations/github/oauth/start?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),
  syncGitHub: (connectionId: string) =>
    request<{
      connection: Connection;
      login: string;
      repository_count: number;
      memory_note_id: string;
    }>(`/integrations/github/${connectionId}/sync`, { method: "POST" }),
  revokeGitHub: (connectionId: string) =>
    request<void>(`/integrations/github/${connectionId}`, { method: "DELETE" }),
  startTwitterOAuth: (workspaceId: string) =>
    request<{ authorization_url: string; callback_url: string }>(
      `/integrations/twitter/oauth/start?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),
  startGoogleModelOAuth: (workspaceId: string, projectId: string) =>
    request<{ authorization_url: string; callback_url: string }>(
      `/integrations/google-model/oauth/start?workspace_id=${encodeURIComponent(workspaceId)}&project_id=${encodeURIComponent(projectId)}`,
    ),
  startContextOAuth: (workspaceId: string, connector: string) =>
    request<{ authorization_url: string; callback_url: string }>(
      `/integrations/context/oauth/start?workspace_id=${encodeURIComponent(workspaceId)}&connector=${encodeURIComponent(connector)}`,
    ),
  connectContextConnector: (data: {
    workspace_id: string;
    connector: string;
    credential: string;
    identifier?: string;
  }) =>
    request<{
      connection: Connection;
      label: string;
      item_count: number;
      memory_note_id: string;
    }>("/integrations/context/connect", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  syncContextConnector: (connectionId: string) =>
    request<{
      connection: Connection;
      label: string;
      item_count: number;
      memory_note_id: string;
    }>(`/integrations/context/${connectionId}/sync`, { method: "POST" }),
  revokeContextConnector: (connectionId: string) =>
    request<void>(`/integrations/context/${connectionId}`, { method: "DELETE" }),
  mcpCatalog: () => request<MCPPreset[]>("/mcp/catalog"),
  mcpServers: (workspaceId: string) =>
    request<Connection[]>(`/mcp/servers?workspace_id=${workspaceId}`),
  installMCP: (data: Record<string, unknown>) =>
    request<Connection>("/mcp/servers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  researchReports: (workspaceId: string) =>
    request<ResearchReport[]>(`/research/reports?workspace_id=${workspaceId}`),
  createResearch: (data: {
    workspace_id: string;
    query: string;
    sources: string[];
    depth: "quick" | "deep";
  }) =>
    request<ResearchReport>("/research/reports", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  tokens: (workspaceId: string, watchlist?: boolean) =>
    request<Token[]>(`/tokens?workspace_id=${encodeURIComponent(workspaceId)}${watchlist === undefined ? "" : `&watchlist=${watchlist}`}`),
  createToken: (data: {
    workspace_id: string; address: string; chain_id?: number; asset_kind?: "token" | "nft"; label?: string;
    symbol?: string; name?: string; watchlist?: boolean;
  }) => request<Token>("/tokens", { method: "POST", body: JSON.stringify(data) }),
  updateToken: (id: string, data: Partial<Pick<Token, "address" | "chain_id" | "asset_kind" | "label" | "symbol" | "name" | "watchlist">>) =>
    request<Token>(`/tokens/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteToken: (id: string) => request<void>(`/tokens/${id}`, { method: "DELETE" }),
  tokenVerdicts: (id: string) => request<TokenVerdict[]>(`/tokens/${id}/verdicts`),
  marketObservations: (id: string) => request<MarketObservation[]>(`/tokens/${id}/market-observations`),
  createMarketObservation: (id: string, data: {
    price:number; quote_symbol:string; kind:"trade"|"mark"; source:string; source_ref:string; observed_at:string;
  }) => request<MarketObservation>(`/tokens/${id}/market-observations`, { method:"POST", body:JSON.stringify(data) }),
  captureMarketObservations: (id: string, blocks = 600, intervalBlocks = 50) =>
    request<MarketObservation[]>(`/tokens/${id}/market-observations/capture`, {
      method:"POST", body:JSON.stringify({ blocks, interval_blocks:intervalBlocks }),
    }),
  decisionEvaluations: (id: string) => request<DecisionEvaluation[]>(`/tokens/${id}/evaluations`),
  evaluateDecision: (id: string, verdictId: string, horizonSeconds = 86400) =>
    request<DecisionEvaluation>(`/tokens/${id}/evaluations`, {
      method:"POST", body:JSON.stringify({ verdict_id:verdictId, horizon_seconds:horizonSeconds }),
    }),
  paperTrades: (id: string) => request<PaperTrade[]>(`/tokens/${id}/paper-trades`),
  createPaperTrade: (id: string, verdictId: string, notional = 1000) =>
    request<PaperTrade>(`/tokens/${id}/paper-trades`, {
      method:"POST", body:JSON.stringify({ verdict_id:verdictId, notional }),
    }),
  closePaperTrade: (tradeId: string, observationId: string) =>
    request<PaperTrade>(`/paper-trades/${tradeId}/close`, {
      method:"POST", body:JSON.stringify({ exit_observation_id:observationId, close_reason:"manual" }),
    }),
  agents: (workspaceId: string) =>
    request<Agent[]>(`/agents?workspace_id=${workspaceId}`),
  createAgent: (data: Record<string, unknown>) =>
    request<Agent>("/agents", { method: "POST", body: JSON.stringify(data) }),
  updateAgent: (id: string, data: Record<string, unknown>) =>
    request<Agent>(`/agents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteAgent: (id: string) =>
    request<void>(`/agents/${id}`, { method: "DELETE" }),
  teams: (workspaceId: string) =>
    request<Team[]>(`/teams?workspace_id=${workspaceId}`),
  createTeam: (data: Record<string, unknown>) =>
    request<Team>("/teams", { method: "POST", body: JSON.stringify(data) }),
  addTeamAgent: (teamId: string, agentId: string) =>
    request<{ agent_id: string; team_id: string }>(`/teams/${teamId}/agents`, {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId }),
    }),
  workflows: (workspaceId: string) =>
    request<Workflow[]>(`/workflows?workspace_id=${workspaceId}`),
  createWorkflow: (data: Record<string, unknown>) =>
    request<Workflow>("/workflows", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateWorkflow: (id: string, data: Record<string, unknown>) =>
    request<Workflow>(`/workflows/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  validateWorkflow: (id: string) =>
    request<{
      valid: boolean;
      errors: Array<{ message: string }>;
      warnings: Array<{ message: string }>;
    }>(`/workflows/${id}/validate`, { method: "POST" }),
  run: (id: string) => request<Run>(`/runs/${id}`),
  runs: (teamId: string) => request<Run[]>(`/runs?team_id=${teamId}`),
  updateRunMeta: (
    runId: string,
    data: { pinned?: boolean; archived?: boolean; title?: string },
  ) =>
    request<Run>(`/runs/${runId}/meta`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  updateRunAgents: (runId: string, agentIds: string[]) =>
    request<Run>(`/runs/${runId}/agents`, {
      method: "PATCH",
      body: JSON.stringify({ agent_ids: agentIds }),
    }),
  deleteRun: (runId: string) =>
    request<void>(`/runs/${runId}`, { method: "DELETE" }),
  mergeRunMemory: (runId: string, targetRunId: string) =>
    request<MemoryNote>(`/runs/${runId}/merge-memory`, {
      method: "POST",
      body: JSON.stringify({ target_run_id: targetRunId }),
    }),
  updateRunBudget: (
    runId: string,
    data: {
      token_limit?: number;
      cost_limit_micros?: number;
      max_rounds?: number;
    },
  ) =>
    request<Run>(`/runs/${runId}/budget`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  branchRun: (
    runId: string,
    data: { event_id: string; instruction: string; kind: "fork" | "rewind" },
  ) =>
    request<Run>(`/runs/${runId}/branch`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  impersonate: (runId: string, agentId: string, content: string) =>
    request<RunEvent>(`/runs/${runId}/impersonate`, {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, content }),
    }),
  shareReplay: (runId: string) =>
    request<{ token: string; public_url: string }>(`/runs/${runId}/share`, {
      method: "POST",
    }),
  publicReplay: (token: string) =>
    request<PublicReplay>(`/public/replays/${encodeURIComponent(token)}`),
  forkReplay: (token: string, workspaceId: string) =>
    request<{ team: Team; agents: Agent[]; goal: string }>(
      `/replays/${encodeURIComponent(token)}/fork`,
      { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) },
    ),
  createRun: (
    teamId: string,
    workflowId?: string,
    goal?: string,
    context?: Record<string, unknown>,
    autoStart = true,
  ) =>
    request<Run>("/runs", {
      method: "POST",
      body: JSON.stringify({
        team_id: teamId,
        workflow_id: workflowId,
        goal,
        context: context || {},
        auto_start: autoStart,
      }),
    }),
  startRun: (runId: string) =>
    request<{ status: string }>(`/runs/${runId}/start`, { method: "POST" }),
  addMaterial: (
    runId: string,
    data: { name: string; content: string; kind: string },
  ) =>
    request<Run>(`/runs/${runId}/materials`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  uploadFile: (workspaceId: string, file: File) =>
    upload<FileAsset>(
      `/files?workspace_id=${encodeURIComponent(workspaceId)}`,
      file,
    ),
  attachFile: (runId: string, assetId: string) =>
    request<Run>(`/runs/${runId}/file-assets/${assetId}`, { method: "POST" }),
  files: (workspaceId: string) =>
    request<FileAsset[]>(
      `/files?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),
  events: async (runId: string, afterSequence = 0) => {
    const values: RunEvent[] = [];
    let after = afterSequence;
    for (;;) {
      const page = await request<RunEvent[]>(
        `/runs/${runId}/events?after_sequence=${after}&limit=1000`,
      );
      values.push(...page);
      if (page.length < 1000) break;
      after = page.at(-1)?.sequence || after;
    }
    return values;
  },
  tasks: (runId: string) => request<Task[]>(`/runs/${runId}/tasks`),
  approvals: (runId: string) => request<Approval[]>(`/runs/${runId}/approvals`),
  artifacts: (runId: string) => request<Artifact[]>(`/runs/${runId}/artifacts`),
  message: (
    runId: string,
    content: string,
    recipients: string[],
    command = "instruction",
    clientMessageId?: string,
  ) =>
    request<RunEvent>(`/runs/${runId}/messages`, {
      method: "POST",
      body: JSON.stringify({
        content,
        recipients,
        command,
        client_message_id: clientMessageId,
      }),
    }),
  checkpoints: (runId: string) =>
    request<
      Array<{
        id: string;
        sequence: number;
        stage: string;
        state: Record<string, unknown>;
        created_at: string;
      }>
    >(`/runs/${runId}/checkpoints`),
  memorySearch: (workspaceId: string, query: string) =>
    request<
      Array<{
        memory_id: string;
        run_id: string | null;
        title: string;
        content: string;
        score: number;
        source: Record<string, unknown>;
      }>
    >("/memory/search", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, query }),
    }),
  mcpTools: (serverId: string) =>
    request<
      Array<{
        name: string;
        description: string;
        input_schema: Record<string, unknown>;
      }>
    >(`/mcp/servers/${serverId}/tools`),
  mode: (runId: string, mode: Mode) =>
    request<Run>(`/runs/${runId}/mode`, {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),
  action: (runId: string, action: "pause" | "resume" | "cancel") =>
    request<{ status: string }>(`/runs/${runId}/${action}`, { method: "POST" }),
  decide: (id: string, decision: "approved" | "rejected") =>
    request<Approval>(`/approvals/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  memory: (workspaceId: string) =>
    request<MemoryNote[]>(`/memory?workspace_id=${workspaceId}`),
  updateMemory: (id: string, data: Record<string, unknown>) =>
    request<MemoryNote>(`/memory/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

export function subscribeToRun(
  runId: string,
  after: number,
  onEvent: (event: RunEvent) => void,
  onConnection: (live: boolean) => void,
) {
  const source = new EventSource(
    `${API}/runs/${runId}/stream?after_sequence=${after}`,
    { withCredentials: true },
  );
  source.onopen = () => onConnection(true);
  source.onerror = () => onConnection(false);
  const types = [
    "run.started",
    "run.recovered",
    "run.completed",
    "run.failed",
    "run.paused",
    "run.resumed",
    "run.cancelled",
    "run.mode_changed",
    "run.branched",
    "run.budget_reached",
    "run.loop_guard",
    "plan.created",
    "plan.revised",
    "message.agent",
    "message.human",
    "task.started",
    "task.completed",
    "task.failed",
    "task.created",
    "task.updated",
    "agent.state.changed",
    "agent.budget_exhausted",
    "agent.loop_detected",
    "constructive.convergence_check",
    "constructive.review_rejected",
    "constructive.objection",
    "constructive.certification",
    "constructive.decision",
    "tool.call.requested",
    "tool.call.started",
    "tool.call.completed",
    "tool.call.failed",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
    "approval.cancelled",
    "artifact.created",
    "artifact.updated",
  ];
  types.forEach((type) =>
    source.addEventListener(type, (e) =>
      onEvent(JSON.parse((e as MessageEvent).data)),
    ),
  );
  return () => source.close();
}
