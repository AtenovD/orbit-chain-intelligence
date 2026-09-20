/**
 * Ready-to-save workflow graphs for the backend's WorkflowCreate/WorkflowUpdate
 * shape. Consumers add workspace_id/team_id when creating a workflow.
 */

export type TradingWorkflowNodeType =
  | "start"
  | "parallel"
  | "agent"
  | "review"
  | "condition"
  | "artifact"
  | "approval"
  | "final";

export interface TradingWorkflowPosition {
  x: number;
  y: number;
}

export interface TradingWorkflowNode {
  id: string;
  type: TradingWorkflowNodeType;
  label: string;
  position: TradingWorkflowPosition;
  agent_id?: string;
  instruction?: string;
  expression?: string;
  default?: boolean;
  description?: string;
  risk?: "low" | "medium" | "high";
  name?: string;
  kind?: string;
}

export interface TradingWorkflowEdge {
  id: string;
  source: string;
  target: string;
  /** Required by the backend for the true/false branches from a condition. */
  condition?: "true" | "false";
  label?: "true" | "false";
}

export interface TradingWorkflowGraph {
  name: string;
  description: string;
  /** A concise operator-facing objective, supplied as the run goal at execution time. */
  goal: string;
  nodes: TradingWorkflowNode[];
  edges: TradingWorkflowEdge[];
}

export interface TradingWorkflowTemplate<TAgentIds> {
  id: "token-signal-scan" | "nft-collection-scan";
  name: string;
  description: string;
  requiredAgents: readonly string[];
  build: (agents: TAgentIds) => TradingWorkflowGraph;
}

/**
 * A policy label for consumers that want to surface the gate condition. The
 * executable graph uses a runtime-native approval node, so an unapproved run
 * pauses and a rejected one cannot reach an actionable verdict.
 */
export const RISK_GATE_EXPRESSION = "context.risk_gate_passed == true";

export interface TokenSignalScanAgents {
  onChainAnalyst: string;
  contractAuditor: string;
  marketAnalyst: string;
  liquidityAnalyst: string;
  riskReviewer: string;
  verdictAgent: string;
}

export interface NftCollectionScanAgents {
  collectionResearcher: string;
  holderAnalyst: string;
  marketAnalyst: string;
  provenanceAuditor: string;
  riskReviewer: string;
  verdictAgent: string;
}

const edge = (
  source: string,
  target: string,
  condition?: "true" | "false",
): TradingWorkflowEdge => ({
  id: `${source}->${target}`,
  source,
  target,
  ...(condition ? { condition, label: condition } : {}),
});

export const TOKEN_SIGNAL_SCAN_TEMPLATE: TradingWorkflowTemplate<TokenSignalScanAgents> = {
  id: "token-signal-scan",
  name: "Token Signal Scan",
  description: "Parallel on-chain, contract, market, and liquidity research with a fail-closed risk gate.",
  requiredAgents: [
    "onChainAnalyst",
    "contractAuditor",
    "marketAnalyst",
    "liquidityAnalyst",
    "riskReviewer",
    "verdictAgent",
  ],
  build: (agents) => ({
    name: "Token Signal Scan",
    description: "Evidence-led token scan that publishes a decision only after the risk gate passes.",
    goal: "Assess a token for a time-bounded trading decision: ENTER, WATCH, or SKIP.",
    nodes: [
      { id: "start", type: "start", label: "Start token scan", position: { x: 0, y: 280 } },
      {
        id: "parallel-research",
        type: "parallel",
        label: "Run independent signal checks",
        position: { x: 220, y: 280 },
      },
      {
        id: "on-chain-signal",
        type: "agent",
        label: "On-chain signal analysis",
        position: { x: 460, y: 0 },
        agent_id: agents.onChainAnalyst,
        instruction: "Analyse holder concentration, wallet flows, transaction velocity, and suspicious on-chain behaviour. Cite raw data or explorer evidence.",
      },
      {
        id: "contract-audit",
        type: "agent",
        label: "Contract and honeypot audit",
        position: { x: 460, y: 180 },
        agent_id: agents.contractAuditor,
        instruction: "Check ownership, mint and blacklist authority, proxy upgrades, sellability, and liquidity locks. State every blocking contract risk plainly.",
      },
      {
        id: "market-signal",
        type: "agent",
        label: "Market structure and momentum",
        position: { x: 460, y: 360 },
        agent_id: agents.marketAnalyst,
        instruction: "Evaluate price structure, volume, momentum, support/resistance, and a realistic entry window. Separate observed facts from assumptions.",
      },
      {
        id: "liquidity-check",
        type: "agent",
        label: "Liquidity and execution check",
        position: { x: 460, y: 540 },
        agent_id: agents.liquidityAnalyst,
        instruction: "Assess liquidity depth, LP concentration, slippage for practical order sizes, volume-to-liquidity, and withdrawal or manipulation risk.",
      },
      {
        id: "risk-review",
        type: "review",
        label: "Risk review: identify blockers",
        position: { x: 760, y: 280 },
        agent_id: agents.riskReviewer,
        instruction: "Challenge the research. List evidence-backed blockers, unresolved assumptions, and whether risk_gate_passed should be true or false. Default to false when evidence is incomplete.",
      },
      {
        id: "risk-gate",
        type: "approval",
        label: "Operator risk gate",
        position: { x: 1010, y: 280 },
        description: "Approve only after reviewing the independent on-chain, contract, market, and liquidity evidence. Reject to stop the trade verdict.",
        risk: "high",
      },
      {
        id: "trade-verdict",
        type: "agent",
        label: "Trading verdict: ENTER / WATCH / SKIP",
        position: { x: 1260, y: 120 },
        agent_id: agents.verdictAgent,
        instruction: "Synthesize the approved evidence into ENTER, WATCH, or SKIP. Include rationale, invalidation levels, sizing constraints, and conditions that change the verdict.",
      },
      {
        id: "approved-output",
        type: "artifact",
        label: "Publish approved token decision",
        position: { x: 1510, y: 120 },
        name: "Token signal decision",
        kind: "final_output",
      },
      {
        id: "final-output",
        type: "final",
        label: "Final token scan output",
        position: { x: 1770, y:280 },
      },
    ],
    edges: [
      edge("start", "parallel-research"),
      edge("parallel-research", "on-chain-signal"),
      edge("parallel-research", "contract-audit"),
      edge("parallel-research", "market-signal"),
      edge("parallel-research", "liquidity-check"),
      edge("on-chain-signal", "risk-review"),
      edge("contract-audit", "risk-review"),
      edge("market-signal", "risk-review"),
      edge("liquidity-check", "risk-review"),
      edge("risk-review", "risk-gate"),
      edge("risk-gate", "trade-verdict"),
      edge("trade-verdict", "approved-output"),
      edge("approved-output", "final-output"),
    ],
  }),
};

export const NFT_COLLECTION_SCAN_TEMPLATE: TradingWorkflowTemplate<NftCollectionScanAgents> = {
  id: "nft-collection-scan",
  name: "NFT Collection Scan",
  description: "Parallel collection, holder, market, and provenance research with a fail-closed risk gate.",
  requiredAgents: [
    "collectionResearcher",
    "holderAnalyst",
    "marketAnalyst",
    "provenanceAuditor",
    "riskReviewer",
    "verdictAgent",
  ],
  build: (agents) => ({
    name: "NFT Collection Scan",
    description: "Evidence-led NFT collection scan that publishes a decision only after the risk gate passes.",
    goal: "Assess an NFT collection for a time-bounded trading decision: BUY, WATCH, or SKIP.",
    nodes: [
      { id: "start", type: "start", label: "Start NFT collection scan", position: { x: 0, y: 280 } },
      {
        id: "parallel-research",
        type: "parallel",
        label: "Run independent collection checks",
        position: { x: 220, y: 280 },
      },
      {
        id: "collection-research",
        type: "agent",
        label: "Collection thesis and catalysts",
        position: { x: 460, y: 0 },
        agent_id: agents.collectionResearcher,
        instruction: "Research the collection's thesis, team, roadmap, community signals, launch mechanics, and near-term catalysts. Cite verifiable sources.",
      },
      {
        id: "holder-analysis",
        type: "agent",
        label: "Holder distribution and wallet flows",
        position: { x: 460, y: 180 },
        agent_id: agents.holderAnalyst,
        instruction: "Analyse unique holders, concentration, whale activity, wash-trading patterns, listing pressure, and transfers between related wallets.",
      },
      {
        id: "market-analysis",
        type: "agent",
        label: "Floor, volume, and liquidity analysis",
        position: { x: 460, y: 360 },
        agent_id: agents.marketAnalyst,
        instruction: "Assess floor-price structure, volume quality, bid depth, spread, sales velocity, rarity liquidity, and viable entry or exit conditions.",
      },
      {
        id: "provenance-audit",
        type: "agent",
        label: "Provenance and contract risk audit",
        position: { x: 460, y: 540 },
        agent_id: agents.provenanceAuditor,
        instruction: "Check collection authenticity, contract permissions, metadata mutability, royalties, marketplace risks, phishing vectors, and other ownership or provenance blockers.",
      },
      {
        id: "risk-review",
        type: "review",
        label: "Risk review: identify blockers",
        position: { x: 760, y: 280 },
        agent_id: agents.riskReviewer,
        instruction: "Challenge the collection research. List evidence-backed blockers, unresolved assumptions, and whether risk_gate_passed should be true or false. Default to false when evidence is incomplete.",
      },
      {
        id: "risk-gate",
        type: "approval",
        label: "Operator risk gate",
        position: { x: 1010, y: 280 },
        description: "Approve only after reviewing the independent collection, holder, market, and provenance evidence. Reject to stop the collection verdict.",
        risk: "high",
      },
      {
        id: "collection-verdict",
        type: "agent",
        label: "Collection verdict: BUY / WATCH / SKIP",
        position: { x: 1260, y: 120 },
        agent_id: agents.verdictAgent,
        instruction: "Synthesize the approved evidence into BUY, WATCH, or SKIP. Include target collection segment, entry constraints, liquidity caveats, and invalidation conditions.",
      },
      {
        id: "approved-output",
        type: "artifact",
        label: "Publish approved collection decision",
        position: { x: 1510, y: 120 },
        name: "NFT collection decision",
        kind: "final_output",
      },
      {
        id: "final-output",
        type: "final",
        label: "Final NFT collection scan output",
        position: { x: 1770, y: 280 },
      },
    ],
    edges: [
      edge("start", "parallel-research"),
      edge("parallel-research", "collection-research"),
      edge("parallel-research", "holder-analysis"),
      edge("parallel-research", "market-analysis"),
      edge("parallel-research", "provenance-audit"),
      edge("collection-research", "risk-review"),
      edge("holder-analysis", "risk-review"),
      edge("market-analysis", "risk-review"),
      edge("provenance-audit", "risk-review"),
      edge("risk-review", "risk-gate"),
      edge("risk-gate", "collection-verdict"),
      edge("collection-verdict", "approved-output"),
      edge("approved-output", "final-output"),
    ],
  }),
};

export const TRADING_WORKFLOW_TEMPLATES = [
  TOKEN_SIGNAL_SCAN_TEMPLATE,
  NFT_COLLECTION_SCAN_TEMPLATE,
] as const;
