export type Mode = "standard" | "constructive";
export type RunStatus = "created" | "running" | "paused" | "waiting_for_human" | "completed" | "failed" | "cancelled";

export interface Workspace { id: string; name: string; created_at: string }
export interface Agent {
  id: string; workspace_id: string; connection_id: string | null; name: string; slug: string;
  role: string; goal: string; system_prompt: string; model: string; tools: unknown[];
  skill_name: string | null; skill_description: string | null; skill_prompt: string | null;
  adhd_skill_enabled: boolean;
  professional_memory: string; lessons_count: number; experience_level: number;
  capabilities: Record<string, unknown>; max_turns: number; token_budget: number;
  can_delegate: boolean; can_review: boolean; created_at: string;
}
export interface Team {
  id: string; workspace_id: string; name: string; goal: string; mode: Mode;
  supervisor_agent_id: string | null; max_parallel_agents: number; rules: Record<string, unknown>;
  agent_ids: string[]; created_at: string;
}
export interface Workflow {
  id: string; workspace_id: string; team_id: string | null; name: string; description: string;
  version: number; nodes: Array<Record<string, unknown>>; edges: Array<Record<string, unknown>>;
  published: boolean; created_at: string; updated_at: string;
}
export interface Run {
  id: string; team_id: string; workflow_id: string | null; goal: string; mode: Mode; status: RunStatus;
  context: Record<string, unknown>; runtime_version:string; plan_revision:number; current_stage:string;
  total_input_tokens: number; total_output_tokens: number; total_cost_micros: number;
  created_at: string; started_at: string | null; finished_at: string | null; last_checkpoint_at:string|null;
}
export interface AppearanceSettings {
  theme:"midnight"|"aurora"|"warm"; sounds:boolean; language:"ru"|"en";
}
export interface RunEvent {
  id: string; run_id: string; sequence: number; type: string; actor_type: string; actor_id: string | null;
  recipients: string[]; task_id: string | null; parent_event_id: string | null;
  payload: Record<string, unknown>; visibility: string; created_at: string;
}
export interface Task {
  id: string; run_id: string; assigned_agent_id: string | null; title: string; description: string;
  status: string; priority: number; result: Record<string, unknown> | null; created_at: string; updated_at: string;
}
export interface Approval {
  id: string; run_id: string; requested_by_agent_id: string | null; action: string; description: string;
  risk: string; status: string; decision_note: string | null; created_at: string;
}
export interface Artifact {
  id: string; run_id: string; name: string; kind: string; mime_type: string; content: string | null;
  uri: string | null; metadata: Record<string, unknown>; created_at: string;
}
export interface PublicReplay {
  run:{id:string;goal:string;mode:Mode;status:RunStatus;created_at:string;finished_at:string|null};
  agents:Array<{id:string;name:string;role:string;model:string}>;
  events:Array<{id:string;sequence:number;type:string;actor_type:string;actor_id:string|null;payload:Record<string,unknown>;created_at:string}>;
  artifacts:Array<{id:string;name:string;kind:string;mime_type:string;content:string|null;metadata:Record<string,unknown>}>;
  verdict:Record<string,unknown>|null;
}
export interface Connection {
  id: string; workspace_id: string; name: string; provider: string; base_url: string | null;
  enabled: boolean; config: Record<string, unknown>; created_at: string;
}
export interface DiscoveredModel { id:string; name:string; owner:string|null; context_length:number|null }
export interface ConnectionDiscovery { ok:boolean; latency_ms:number; models:DiscoveredModel[]; model_count:number; base_url?:string|null }
export interface MCPPreset {
  id:string; name:string; description:string; transport:"stdio"|"streamable_http"|"sse";
  command:string|null; args:string[]; secret_name:string|null; risk:string; official:boolean;
}
export interface MemoryNote {
  id: string; workspace_id: string; run_id: string | null; scope: "global"|"dialogue";
  title: string; content: string; summary: string; links: string[]; byte_size: number;
  created_at: string; updated_at: string;
}
export interface ResearchFinding {
  source:string; title:string; url:string; snippet:string; score:number;
  author?:string; published_at?:string; thumbnail?:string; metrics?:Record<string,number>;
}
export interface ResearchReport {
  id:string; workspace_id:string; query:string; status:string; depth:"quick"|"deep";
  requested_sources:string[]; source_status:Record<string,{status:string;results:number}>;
  findings:ResearchFinding[]; report:string; created_at:string;
}
export interface Token {
  id:string; workspace_id:string; address:string; chain_id:number; asset_kind:"token"|"nft";
  label:string|null; symbol:string|null; name:string|null; watchlist:boolean;
  created_at:string; updated_at:string;
}
export interface TokenVerdict {
  id:string; token_id:string; run_id:string|null; artifact_id:string|null;
  verdict:string; payload:Record<string,unknown>; created_at:string;
}
export interface MarketObservation {
  id:string; token_id:string; price:number; quote_symbol:string; kind:"trade"|"mark";
  source:string; source_ref:string; observed_at:string; payload:Record<string,unknown>; created_at:string;
}
export interface DecisionEvaluation {
  id:string; token_id:string; verdict_id:string; decision:string; status:string; outcome:string;
  horizon_seconds:number; entry_observation_id:string|null; exit_observation_id:string|null;
  benchmark_return_pct:number|null; strategy_return_pct:number|null;
  max_favorable_excursion_pct:number|null; max_adverse_excursion_pct:number|null;
  payload:Record<string,unknown>; created_at:string;
}
export interface PaperTrade {
  id:string; token_id:string; verdict_id:string|null; run_id:string|null; decision:string; status:string;
  quote_symbol:string; notional:number; quantity:number|null; entry_price:number|null; exit_price:number|null;
  entry_observation_id:string|null; exit_observation_id:string|null; fee_bps:number; slippage_bps:number;
  fees_paid:number; realized_pnl:number|null; return_pct:number|null; opened_at:string|null; closed_at:string|null;
  close_reason:string|null; config:Record<string,unknown>; created_at:string; updated_at:string;
}
export interface DecisionQuality {
  contract_version:string; resolved_decisions:number;
  scorecards:Array<{
    agent_id:string; agent_name:string; model:string; signals:number; resolved_decisions:number;
    directional_signals:number; correct:number; incorrect:number; hit_rate:number|null;
    brier_score:number|null; average_confidence:number|null;
  }>;
  notes:string[];
}
export interface FileAsset {
  id:string; workspace_id:string; uploaded_by_user_id:string|null; name:string; mime_type:string;
  size:number; sha256:string; status:string; metadata:Record<string,unknown>; created_at:string;
}
