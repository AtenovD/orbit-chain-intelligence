import { describe, expect, it } from "vitest";
import {
  NFT_COLLECTION_SCAN_TEMPLATE,
  RISK_GATE_EXPRESSION,
  TOKEN_SIGNAL_SCAN_TEMPLATE,
  type NftCollectionScanAgents,
  type TokenSignalScanAgents,
  type TradingWorkflowGraph,
} from "./trading-workflow-templates";

const tokenAgents: TokenSignalScanAgents = {
  onChainAnalyst: "token-on-chain",
  contractAuditor: "token-contract",
  marketAnalyst: "token-market",
  liquidityAnalyst: "token-liquidity",
  riskReviewer: "token-risk",
  verdictAgent: "token-verdict",
};

const nftAgents: NftCollectionScanAgents = {
  collectionResearcher: "nft-collection",
  holderAnalyst: "nft-holders",
  marketAnalyst: "nft-market",
  provenanceAuditor: "nft-provenance",
  riskReviewer: "nft-risk",
  verdictAgent: "nft-verdict",
};

function expectRunnableGraph(graph: TradingWorkflowGraph) {
  const ids = new Set(graph.nodes.map((node) => node.id));
  expect(graph.nodes.filter((node) => node.type === "start")).toHaveLength(1);
  expect(graph.nodes.filter((node) => node.type === "final")).toHaveLength(1);
  expect(graph.nodes.filter((node) => node.type === "agent" || node.type === "review").every((node) => Boolean(node.agent_id))).toBe(true);
  expect(graph.edges.every((item) => ids.has(item.source) && ids.has(item.target))).toBe(true);

  const riskGate = graph.nodes.find((node) => node.id === "risk-gate");
  expect(RISK_GATE_EXPRESSION).toBe("context.risk_gate_passed == true");
  expect(riskGate).toMatchObject({ type: "approval", risk: "high" });
  expect(graph.edges.filter((item) => item.source === "risk-gate")).toHaveLength(1);
}

describe("trading workflow templates", () => {
  it("builds a valid fail-closed token signal graph", () => {
    expectRunnableGraph(TOKEN_SIGNAL_SCAN_TEMPLATE.build(tokenAgents));
  });

  it("builds a valid fail-closed NFT collection graph", () => {
    expectRunnableGraph(NFT_COLLECTION_SCAN_TEMPLATE.build(nftAgents));
  });
});
