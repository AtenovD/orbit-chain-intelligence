import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { createPortal } from "react-dom";
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  type Connection as FlowConnection,
  type Edge,
  type Node as FlowNode,
} from "reactflow";
import {
  Activity,
  AlertTriangle,
  Archive,
  AtSign,
  Bell,
  Bot,
  Box,
  Brain,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  GitBranch,
  GitFork,
  Github,
  Globe2,
  MessageSquare,
  Paperclip,
  Pause,
  Pin,
  Play,
  Plug,
  PanelRight,
  Plus,
  RotateCcw,
  Save,
  Search,
  Send,
  Settings,
  Share2,
  ShieldCheck,
  Sparkles,
  Square,
  Users,
  Volume2,
  VolumeX,
  X,
  Pencil,
  Trash2,
  ArrowRightLeft,
  Megaphone,
  Code2,
  Compass,
  Fingerprint,
  Timer,
  Wallet,
  Waves,
  Image as ImageIcon,
  Radar,
  Rocket,
  Gift,
  TrendingUp,
  BarChart3,
  type LucideIcon,
} from "lucide-react";
import { WalletDialog } from "./WalletDialog";
import { openWalletDialog, shortAddress } from "./wallet";
import {
  api,
  ApiRequestError,
  type AdminOverview,
  type DeploymentCapabilities,
  setAuthenticationRequiredHandler,
  subscribeToRun,
} from "./api";
import { ensureDemo } from "./demo";
import {
  connectionModelIds,
  normalizeProviderBaseUrl,
  PROVIDERS,
} from "./providers";
import {
  NFT_COLLECTION_SCAN_TEMPLATE,
  TOKEN_SIGNAL_SCAN_TEMPLATE,
} from "./trading-workflow-templates";
import avaAvatar from "./assets/agents/ava.webp";
import marcusAvatar from "./assets/agents/marcus.webp";
import priyaAvatar from "./assets/agents/priya.webp";
import danielAvatar from "./assets/agents/daniel.webp";
import sofiaAvatar from "./assets/agents/sofia.webp";

const MAX_TEAM_SIZE = 10;
import { PublicReplayPage } from "./PublicReplayPage";
import type {
  Agent,
  AppearanceSettings,
  Approval,
  Artifact,
  Connection,
  ConnectionDiscovery,
  DiscoveredModel,
  MCPPreset,
  MemoryNote,
  MarketObservation,
  DecisionEvaluation,
  PaperTrade,
  DecisionQuality,
  Mode,
  ResearchFinding,
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

function mergeRunEvents(current: RunEvent[], incoming: RunEvent[]) {
  const byId = new Map(current.map((event) => [event.id, event]));
  incoming.forEach((event) => byId.set(event.id, event));
  return [...byId.values()].sort((left, right) =>
    left.sequence === right.sequence
      ? left.created_at.localeCompare(right.created_at)
      : left.sequence - right.sequence,
  );
}

type Screen =
  | "home"
  | "workflows"
  | "research"
  | "tokens"
  | "skills"
  | "memory"
  | "overview"
  | "team"
  | "run"
  | "tasks"
  | "connections"
  | "admin"
  | "settings"
  | "profile";
type DraftMaterial = {
  name: string;
  content: string;
  kind: string;
  file?: File;
};
type OrbitUser = { id: string; email: string; display_name: string; email_verified?: boolean; is_superuser?: boolean; is_guest?: boolean; wallet_address?: string | null };
const AUTH_REQUIRED = import.meta.env.VITE_AUTH_REQUIRED === "true";
const colors = ["#8ee06a", "#4fbf7a", "#2fc68c", "#c3e35a", "#6bd15c"];
const AGENT_SKILLS = [
  {
    name: "Web Research",
    descriptionRu:
      "Находит источники, проверяет факты и отделяет выводы от предположений.",
    descriptionEn:
      "Finds sources, verifies facts, and separates conclusions from assumptions.",
    prompt:
      "Research claims using reliable sources. Cross-check important facts, cite evidence, and clearly label uncertainty.",
  },
  {
    name: "Critical Thinking",
    descriptionRu:
      "Проверяет идеи, риски и скрытые предположения до принятия решения.",
    descriptionEn:
      "Tests ideas, risks, and hidden assumptions before a decision is made.",
    prompt:
      "Challenge assumptions constructively. Identify material risks, test logic, and propose a stronger practical alternative.",
  },
  {
    name: "Code Review",
    descriptionRu: "Ищет ошибки, уязвимости и проблемы поддержки в коде.",
    descriptionEn:
      "Finds defects, vulnerabilities, and maintainability issues in code.",
    prompt:
      "Review code for correctness, security, performance, tests, and maintainability. Prioritize findings by impact and suggest concrete fixes.",
  },
  {
    name: "Data Analysis",
    descriptionRu: "Превращает данные в проверяемые выводы и рекомендации.",
    descriptionEn: "Turns data into verifiable findings and recommendations.",
    prompt:
      "Analyze data methodically. Validate inputs, explain calculations, distinguish correlation from causation, and summarize actionable findings.",
  },
  {
    name: "Security Audit",
    descriptionRu: "Моделирует угрозы и проверяет безопасность решений.",
    descriptionEn:
      "Models threats and evaluates the security of proposed solutions.",
    prompt:
      "Apply threat modeling and secure-by-default principles. Flag exploitable risks, explain impact, and recommend proportionate mitigations.",
  },
  {
    name: "UX Writer",
    descriptionRu:
      "Делает интерфейсные тексты ясными, короткими и человечными.",
    descriptionEn: "Makes interface copy clear, concise, and human.",
    prompt:
      "Write concise, accessible product copy. Preserve meaning, reduce cognitive load, and provide clear actions and error recovery.",
  },
  {
    name: "Strategic Planner",
    descriptionRu:
      "Разбивает цель на этапы, зависимости и критерии готовности.",
    descriptionEn:
      "Breaks a goal into milestones, dependencies, and completion criteria.",
    prompt:
      "Own the final structure. Separate verified facts, assumptions, unknowns, decision gates, owners, dependencies, and next actions. Reconcile conflicts explicitly. Never call a plan complete without a measurable acceptance criterion and a fallback.",
  },
  {
    name: "Memory Curator",
    descriptionRu:
      "Сжимает знания и сохраняет только полезный долгосрочный контекст.",
    descriptionEn:
      "Compresses knowledge and preserves only useful long-term context.",
    prompt:
      "Extract durable facts, decisions, preferences, and open questions. Remove repetition and sensitive or short-lived details unless necessary.",
  },
  // ── Robinhood Chain / Trading skills ────────────────────────────────────
  {
    name: "On-Chain Researcher",
    descriptionRu:
      "Читает данные блокчейна: холдеры, транзакции, активность кошельков.",
    descriptionEn:
      "Reads blockchain data: holders, transactions, wallet activity.",
    prompt:
      "Investigate the address on Robinhood Chain with native chain tools before relying on narrative. Report identity, contract risk, age, holder concentration, contract-vs-EOA ownership, pools, and candle limitations. Attach a raw source or block reference to every material claim. Mark partial history, pruned-node limitations, inferred deployer, stale data, and unavailable USD values. Never infer safety from one metric.",
  },
  {
    name: "Token Auditor",
    descriptionRu:
      "Проверяет контракт на rug pull, honeypot и скрытые риски.",
    descriptionEn:
      "Checks the contract for rug pull, honeypot, and hidden risks.",
    prompt:
      "Audit the token contract on Robinhood Chain. Check ownership renouncement, mint authority, blacklist/freeze functions, liquidity lock status, and proxy upgrade risk. Produce a risk score (1-10) with justification. Explicitly state any finding that would classify the token as a honeypot or rug-pull vector.",
  },
  {
    name: "Narrative Scout",
    descriptionRu:
      "Анализирует нарратив, хайп и социальные сигналы вокруг токена.",
    descriptionEn:
      "Analyses the narrative, hype, and social signals around a token.",
    prompt:
      "Map the core claim, audience, channels, proponents, counter-narratives, and decay signals. Require independent sources for material claims. Distinguish attention from conversion and sentiment from evidence. End with a falsifiable thesis and the signal that would invalidate it.",
  },
  {
    name: "Timing Analyst",
    descriptionRu:
      "Оценивает рыночный момент: объём, импульс и оптимальные точки входа.",
    descriptionEn:
      "Evaluates market timing: volume, momentum, and optimal entry points.",
    prompt:
      "Convert evidence into an action plan, not a summary. State the decision, entry/exit or go/no-go conditions, time horizon, limits, dependencies, owner, and invalidation trigger. If evidence is insufficient, produce a bounded WATCH plan instead of invented precision. Leave an artifact another operator can execute.",
  },
  {
    name: "Verdict Checker",
    descriptionRu:
      "Сводит выводы команды в итоговый вердикт: входить или нет.",
    descriptionEn:
      "Consolidates the team's findings into a final verdict: enter or skip.",
    prompt:
      "Act as an adversarial reviewer. Check contract control, liquidity, holder concentration, provenance, data freshness, manipulation, and execution risk. Identify the strongest reason the decision could be wrong and how to test it. Produce ENTER / WATCH / SKIP only when supported; otherwise say INSUFFICIENT EVIDENCE. List confidence, assumptions, blockers, and three conditions that change the verdict. Empty agreement is not a review.",
  },
  {
    name: "Wallet Tracker",
    descriptionRu:
      "Следит за Smart Money: куда входят и выходят крупные кошельки.",
    descriptionEn:
      "Tracks Smart Money: where large wallets are entering and exiting.",
    prompt:
      "Monitor wallet activity for the target token on Robinhood Chain. Identify top-10 holders by balance change in the last 24h, flag any whale accumulation or distribution, and cross-reference with known smart-money addresses. Report net flow direction and any coordinated movement that suggests insider knowledge.",
  },
  {
    name: "Liquidity Monitor",
    descriptionRu:
      "Оценивает глубину ликвидности, пулы и риск слипажа.",
    descriptionEn:
      "Evaluates liquidity depth, pools, and slippage risk.",
    prompt:
      "Analyse liquidity pools for the target token on Robinhood Chain DEXs. Report total liquidity in USD, LP token distribution (concentrated vs. dispersed), 24h volume-to-liquidity ratio, estimated slippage for a $1k / $10k / $50k trade, and any signs of liquidity removal risk.",
  },
  {
    name: "NFT Screener",
    descriptionRu:
      "Скринирует NFT-коллекции: floor, объём и сигналы флор-свипа.",
    descriptionEn:
      "Screens NFT collections: floor, volume, and floor-sweep signals.",
    prompt:
      "Screen NFT collections on Robinhood Chain (hood.fun). For each collection report: floor price, 24h volume, unique minters vs. holders ratio, floor price trend (last 7 days), and any floor-sweep or wash-trading signals. Flag collections where creator address also deployed a token (cross-surface signal).",
  },
  {
    name: "Sentiment Scanner",
    descriptionRu:
      "Агрегирует сентимент из X, Telegram и Reddit в реальном времени.",
    descriptionEn:
      "Aggregates real-time sentiment from X, Telegram, and Reddit.",
    prompt:
      "Collect and quantify social sentiment for the target token across X, Telegram, and Reddit. Compute a sentiment score (-1 to +1), identify the top-3 positive and negative talking points, detect bot activity or coordinated campaigns, and flag any FUD narratives gaining traction. Include post volume trend over the last 48h.",
  },
  {
    name: "Deployer Analyst",
    descriptionRu:
      "Изучает историю деплоера: предыдущие проекты, паттерны и репутацию.",
    descriptionEn:
      "Investigates deployer history: prior projects, patterns, and reputation.",
    prompt:
      "Research the token deployer address on Robinhood Chain. List all previously deployed tokens, their outcomes (still active / rugged / abandoned), average time-to-rug, and whether the deployer has repeated wallets or laundering patterns. Rate deployer credibility (1-10) and note any community blacklisting.",
  },
  {
    name: "Airdrop & Claim Analyst",
    descriptionRu:
      "Анализирует механику аирдропов и вероятность дамп-давления.",
    descriptionEn:
      "Analyses airdrop mechanics and likely dump pressure.",
    prompt:
      "Examine any airdrop or claim mechanic attached to the token. Estimate the number of eligible recipients, unlock schedule, expected selling pressure on unlock dates, and whether the airdrop design incentivises holding or immediate dumping. Produce a post-airdrop price-impact estimate.",
  },
  {
    name: "Volume Spike Detector",
    descriptionRu:
      "Детектирует аномальные скачки объёма и отделяет органику от накрутки.",
    descriptionEn:
      "Detects abnormal volume spikes and separates organic from manipulated activity.",
    prompt:
      "Detect and classify volume anomalies for the target token over the last 72h on Robinhood Chain DEXs. Identify spikes, compute the spike-to-baseline ratio, check whether spikes correlate with social events or appear self-generated, and flag any wash-trading indicators such as round-trip transactions between related addresses.",
  },
] as const;

const BUILTIN_BASE_SKILL = {
  name: "I Have ADHD",
  descriptionRu:
    "Базовый стиль ответа: действие сначала, шаги по номерам и один следующий шаг.",
  descriptionEn:
    "Default output style: action first, numbered steps, and one concrete next action.",
  prompt:
    "Apply this output contract to every response: (1) lead with the next action or outcome; (2) number multi-step work; (3) end with one concrete next action when work remains; (4) suppress tangents and optional detail unless it changes the decision; (5) restate the current state when context is easy to lose; (6) give specific time estimates when timing matters; (7) make completed progress visible; (8) state errors matter-of-factly and name the recovery path; (9) cap visible lists at five items where possible; (10) skip preambles, recaps, and closing pleasantries. This is an output-format skill, not a medical diagnosis or treatment. Preserve user intent, safety constraints, and required technical detail; do not omit important information merely to be brief.",
  source: "https://github.com/ayghri/i-have-adhd",
  license: "MIT",
} as const;

// The catalog is intentionally explicit: every built-in skill has a visible
// scope, evidence rule, and boundary instead of a vague one-line persona.
const SKILL_GUARDRAILS: Record<string, string> = {
  "Web Research": "Scope: authoritative sources first. Verify material claims twice, record URL/date, separate fact from inference, and show conflicts. Never treat a snippet or one unverified post as proof.",
  "Critical Thinking": "Expose assumptions, steelman the strongest alternative, quantify material downside, and name the evidence that would change the conclusion. Do not invent objections or reject without a practical replacement.",
  "Code Review": "Review supplied code only. Prioritize correctness, security, data loss, regressions, tests, and operability; cite file/line. Do not claim a test passed without evidence. Return severity, proof, fix, residual risk.",
  "Data Analysis": "Validate schema, missingness, units, denominator, window, and calculations; show formulas. Do not infer causality from correlation or silently impute. Return method, limitations, and actionable recommendation.",
  "Security Audit": "Map assets, trust boundaries, attacker capability, exploitability, and impact. Do not test destructively, request secrets, or provide weaponized steps. Return severity, evidence, safe reproduction, mitigation, verification test.",
  "UX Writer": "Use plain language, one action per label, explicit errors, and consistent terms. Do not blame users or hide destructive consequences. Return final copy plus edge-case variants and rationale.",
  "Strategic Planner": "Define milestones, owners, dependencies, gates, budget/time bounds, risks, fallback, and measurable acceptance. Do not call work complete with unresolved decisions. Return critical path and next action.",
  "Memory Curator": "Keep durable decisions, verified facts, sources, confidence, and open questions. Never store secrets, transient chatter, unsupported claims, or duplicates. Include review/expiry conditions.",
  "On-Chain Researcher": "Use Robinhood Chain tools for identity, activity, age, holders, pools, and liquidity. Attach address/block evidence; mark pruned history, range limits, stale data, and inferred deployer. Never invent USD or candle data.",
  "Token Auditor": "Inspect owner/admin, proxy upgrades, mint/burn, blacklist, pause, taxes, transfer restrictions, and LP exposure. Do not call a token safe from one check or claim honeypot proof without reproducible evidence.",
  "Narrative Scout": "Map claim, audience, channels, source quality, counter-narrative, velocity, and falsifier. Do not count reposts as independent confirmation or confuse sentiment with adoption. End with invalidation signal.",
  "Timing Analyst": "State horizon, trigger, entry/exit conditions, liquidity constraint, invalidation, and unknowns. Do not promise price or invent precision. Produce bounded ENTER/WATCH/SKIP scenarios and recheck time.",
  "Verdict Checker": "Reconcile disagreements, weight primary evidence, test freshness, and identify the strongest counterexample. Do not average incompatible claims or hide blockers. Return verdict/INSUFFICIENT EVIDENCE, confidence, assumptions, and change conditions.",
  "Wallet Tracker": "Distinguish EOA/contract, timeframe, net flow, pools, and coordinated movement. Do not identify a person without attribution or call every large holder smart money. Return address-level evidence and alert threshold.",
  "Liquidity Monitor": "Identify pools/quote assets, reserves/depth, concentration, freshness, and scenario slippage. Do not equate TVL with executable exit liquidity or zero swaps with zero liquidity. Return pool evidence and removal risk.",
  "NFT Screener": "Report floor, volume, unique holders/minters, trend window, creator links, and wash-trade indicators. Do not treat a floor listing as depth or invent coverage. Return collection evidence and confidence.",
  "Sentiment Scanner": "Separate platforms, windows, unique authors, bot/coordinated behavior, and themes. Do not expose private data or use sentiment alone as a trade decision. Return method, score range, caveats, and falsification check.",
  "Deployer Analyst": "State whether deployer/first minter is inferred; distinguish factory from top-level deploy. Link contracts and timelines. Do not accuse a person, call a first minter a deployer, or infer a rug from name similarity.",
  "Airdrop & Claim Analyst": "Inspect eligibility, claims, vesting, unlocks, recipient concentration, and observed sell-through. Do not turn estimates into guaranteed dumps. Return assumptions, scenario range, dates, and monitoring trigger.",
  "Volume Spike Detector": "Define baseline/window, calculate ratio, correlate independent events, and inspect round trips/related addresses. Do not call a spike bullish or wash trading without transaction evidence. Return anomaly table and follow-up query.",
};

function fullSkillPrompt(skill: (typeof AGENT_SKILLS)[number]): string {
  const guardrail = SKILL_GUARDRAILS[skill.name];
  return guardrail
    ? `${skill.prompt}\n\n[Orbit operating contract: ${skill.name}]\n${guardrail}`
    : skill.prompt;
}

function fullBuiltinSkillPrompt(): string {
  return `${BUILTIN_BASE_SKILL.prompt}\n\n[Source: ${BUILTIN_BASE_SKILL.source} · ${BUILTIN_BASE_SKILL.license}]`;
}

function skillContract(name: string): string {
  return SKILL_GUARDRAILS[name] || "No additional built-in contract is defined.";
}

const SKILL_GRADIENTS: [string, string][] = [
  ["#5aa832", "#24501a"],
  ["#2f9c6a", "#134734"],
  ["#7fae2a", "#3b5410"],
  ["#2f8c7a", "#10403a"],
  ["#43923f", "#16421c"],
  ["#6f9c22", "#2d4a0e"],
];

const SKILL_ICON_LIST: [string, LucideIcon][] = [
  ["Web Research", Globe2],
  ["Critical Thinking", Brain],
  ["Code Review", Code2],
  ["Data Analysis", Activity],
  ["Security Audit", ShieldCheck],
  ["UX Writer", Pencil],
  ["Strategic Planner", Compass],
  ["Memory Curator", Archive],
  ["On-Chain Researcher", Search],
  ["Token Auditor", Fingerprint],
  ["Narrative Scout", Megaphone],
  ["Timing Analyst", Timer],
  ["Verdict Checker", Check],
  ["Wallet Tracker", Wallet],
  ["Liquidity Monitor", Waves],
  ["NFT Screener", ImageIcon],
  ["Sentiment Scanner", Radar],
  ["Deployer Analyst", Rocket],
  ["Airdrop & Claim Analyst", Gift],
  ["Volume Spike Detector", TrendingUp],
];

const SKILL_VISUALS: Record<string, { icon: LucideIcon; gradient: [string, string] }> =
  Object.fromEntries(
    SKILL_ICON_LIST.map(([name, icon], index) => [
      name,
      { icon, gradient: SKILL_GRADIENTS[index % SKILL_GRADIENTS.length] },
    ]),
  );

const CORE_AGENT_AVATARS: Record<string, { src: string; accent: string }> = {
  "Ava Chen": { src: avaAvatar, accent: "#bb79ff" },
  "Marcus Webb": { src: marcusAvatar, accent: "#53a6ff" },
  "Priya Nair": { src: priyaAvatar, accent: "#40dfc1" },
  "Daniel Kim": { src: danielAvatar, accent: "#ffb24d" },
  "Sofia Reyes": { src: sofiaAvatar, accent: "#ff6d85" },
};

function AgentGlyph({
  name,
  skillName,
  color,
  className = "avatar",
}: {
  name: string;
  skillName?: string | null;
  color: string;
  className?: string;
}) {
  const portrait = CORE_AGENT_AVATARS[name];
  if (portrait) {
    return (
      <span
        className={`${className} agentportrait`}
        style={{ "--agent-accent": portrait.accent } as CSSProperties}
        role="img"
        aria-label={`${name} avatar`}
      >
        <img src={portrait.src} alt="" />
      </span>
    );
  }
  const visual = skillName ? SKILL_VISUALS[skillName] : undefined;
  if (!visual) {
    return (
      <span className={className} style={{ background: color }}>
        {initials(name)}
      </span>
    );
  }
  const Icon = visual.icon;
  return (
    <span
      className={`${className} glyph`}
      style={{
        background: `linear-gradient(135deg, ${visual.gradient[0]}, ${visual.gradient[1]})`,
      }}
    >
      <Icon />
    </span>
  );
}

function OrbitMark({ className = "" }: { className?: string }) {
  return (
    <span className={`brandmark ${className}`.trim()} aria-hidden="true">
      <svg viewBox="0 0 40 40" focusable="false">
        <defs>
          <linearGradient id="orbit-mark-surface" x1="5" y1="3" x2="35" y2="38" gradientUnits="userSpaceOnUse">
            <stop stopColor="#dfff9a" />
            <stop offset=".5" stopColor="#9add49" />
            <stop offset="1" stopColor="#396c27" />
          </linearGradient>
          <radialGradient id="orbit-mark-core" cx="50%" cy="40%" r="60%">
            <stop stopColor="#f1ffd1" />
            <stop offset=".47" stopColor="#c8ff63" />
            <stop offset="1" stopColor="#78c53d" />
          </radialGradient>
        </defs>
        <rect x="1" y="1" width="38" height="38" rx="12" fill="#142314" />
        <rect x="2.5" y="2.5" width="35" height="35" rx="10.5" fill="url(#orbit-mark-surface)" />
        <circle cx="20" cy="20" r="7.1" fill="url(#orbit-mark-core)" />
        <ellipse cx="20" cy="20" rx="13.5" ry="5.7" fill="none" stroke="#173215" strokeWidth="1.7" transform="rotate(-27 20 20)" />
        <path d="M18 15.8 24.5 20 18 24.2Z" fill="#173215" />
        <circle cx="31.7" cy="13.4" r="2.25" fill="#efffc8" stroke="#315a26" strokeWidth="1.1" />
      </svg>
    </span>
  );
}

type MascotState = "idle" | "thinking" | "done" | "alert";

function LegacyMascot({
  state = "idle",
  size = 104,
}: {
  state?: MascotState;
  size?: number;
}) {
  const label =
    state === "thinking"
      ? "Orbit Scout is scanning signals"
      : state === "done"
        ? "Orbit Scout found a signal"
        : state === "alert"
          ? "Orbit Scout detected a risk"
          : "Orbit Scout is on watch";
  return (
    <div
      className={`mascot orbit-scout mascot-${state}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label}
    >
      <svg viewBox="0 0 260 260" aria-hidden="true">
        <defs>
          <linearGradient id="scout-shell" x1=".1" y1="0" x2=".9" y2="1">
            <stop offset="0" stopColor="#e5ff90" />
            <stop offset=".32" stopColor="#b8ff47" />
            <stop offset=".72" stopColor="#63b82d" />
            <stop offset="1" stopColor="#2d681f" />
          </linearGradient>
          <linearGradient id="scout-shadow" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#192721" />
            <stop offset="1" stopColor="#07100e" />
          </linearGradient>
          <radialGradient id="scout-aura" cx="50%" cy="48%" r="54%">
            <stop offset="0" stopColor="#c8ff69" stopOpacity=".5" />
            <stop offset=".48" stopColor="#7ee6b6" stopOpacity=".16" />
            <stop offset="1" stopColor="#0a1714" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="scout-coat" x1=".15" y1="0" x2=".85" y2="1">
            <stop offset="0" stopColor="#2b3630" />
            <stop offset=".45" stopColor="#171f1b" />
            <stop offset="1" stopColor="#080d0b" />
          </linearGradient>
          <linearGradient id="scout-coat-dark" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#151d19" />
            <stop offset="1" stopColor="#070b09" />
          </linearGradient>
          <linearGradient id="scout-mask" x1=".2" y1="0" x2=".8" y2="1">
            <stop offset="0" stopColor="#f4f8e8" />
            <stop offset=".55" stopColor="#d8e0c4" />
            <stop offset="1" stopColor="#98a486" />
          </linearGradient>
          <linearGradient id="scout-hat" x1=".1" y1="0" x2=".9" y2="1">
            <stop offset="0" stopColor="#222c26" />
            <stop offset=".6" stopColor="#111815" />
            <stop offset="1" stopColor="#070a08" />
          </linearGradient>
          <linearGradient id="scout-beak" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#eef2df" />
            <stop offset=".6" stopColor="#c7ceb0" />
            <stop offset="1" stopColor="#8f9a78" />
          </linearGradient>
          <linearGradient id="scout-sleeve" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#3a4a3f" />
            <stop offset=".5" stopColor="#1c2620" />
            <stop offset="1" stopColor="#0a0f0b" />
          </linearGradient>
          <filter id="scout-blur"><feGaussianBlur stdDeviation="5" /></filter>
        </defs>
        <circle className="scout-aura" cx="130" cy="132" r="116" fill="url(#scout-aura)" />
        <g className="scout-orbit scout-orbit-one">
          <ellipse cx="130" cy="132" rx="112" ry="49" fill="none" stroke="#c6ff57" strokeOpacity=".28" strokeWidth="1.2" />
          <circle cx="232" cy="133" r="4" fill="#d9ff84" />
        </g>
        <g className="scout-orbit scout-orbit-two">
          <ellipse cx="130" cy="132" rx="76" ry="118" fill="none" stroke="#7df4e4" strokeOpacity=".24" strokeWidth="1" />
          <path d="M130 14l4 8-4 8-4-8z" fill="#86f2e2" />
        </g>
        <g className="scout-unit">
          <ellipse className="scout-shadow" cx="130" cy="246" rx="66" ry="8" fill="#9bff48" opacity=".2" filter="url(#scout-blur)" />

          {/* torso silhouette: smooth badge shape, one stroked path gives the even neon rim */}
          <path
            className="scout-coat"
            d="M130 132c-20 0-36 7-49 19-13 12-21 28-25 47-3 15-4 30-3 45 0 3 3 5 6 4 21-8 44-13 71-13s50 5 71 13c3 1 6-1 6-4 1-15 0-30-3-45-4-19-12-35-25-47-13-12-29-19-49-19z"
            fill="url(#scout-coat)"
            stroke="#9bff4d"
            strokeWidth="3.5"
            strokeLinejoin="round"
          />

          {/* crossed arms: bold rounded sleeves, lighter than the coat so they read as arms */}
          <g className="scout-arm scout-arm-left">
            <path d="M72 178L150 222" fill="none" stroke="#9bff4d" strokeOpacity=".55" strokeWidth="50" strokeLinecap="round" />
            <path d="M72 178L150 222" fill="none" stroke="url(#scout-sleeve)" strokeWidth="44" strokeLinecap="round" />
            <path d="M84 188L128 212" fill="none" stroke="#aab89a" strokeOpacity=".55" strokeWidth="5" strokeLinecap="round" />
          </g>
          <g className="scout-arm scout-arm-right">
            <path d="M188 178L110 222" fill="none" stroke="#9bff4d" strokeOpacity=".55" strokeWidth="50" strokeLinecap="round" />
            <path d="M188 178L110 222" fill="none" stroke="url(#scout-sleeve)" strokeWidth="44" strokeLinecap="round" />
            <path d="M176 188L132 212" fill="none" stroke="#aab89a" strokeOpacity=".55" strokeWidth="5" strokeLinecap="round" />
          </g>

          {/* zigzag lapels opening over the chest, matching the reference's chevron edge */}
          <path
            d="M112 146L100 158L114 170L100 182L118 196"
            fill="none"
            stroke="#cad3ba"
            strokeWidth="9"
            strokeLinejoin="miter"
            strokeLinecap="butt"
          />
          <path
            d="M148 146L160 158L146 170L160 182L142 196"
            fill="none"
            stroke="#9aa688"
            strokeWidth="9"
            strokeLinejoin="miter"
            strokeLinecap="butt"
          />

          {/* forearm cuff crossing on top, with a lime-piped signal core */}
          <path
            d="M90 197c0-9 9-15 20-15h40c11 0 20 6 20 15s-9 15-20 15h-40c-11 0-20-6-20-15z"
            fill="url(#scout-coat)"
            stroke="#9bff4d"
            strokeWidth="2.2"
          />
          <path d="M100 197h60" fill="none" stroke="#9bff4d" strokeOpacity=".4" strokeWidth="2" strokeLinecap="round" />
          <path d="M114 189h32v18h-32z" fill="#0a0f0c" stroke="#9bff4d" strokeOpacity=".7" strokeWidth="1.6" />
          <circle className="scout-core-dot" cx="130" cy="198" r="5.5" fill="#d7ff7a" />

          {/* mask: tapered wedge from brow to beak tip */}
          <path
            className="scout-mask"
            d="M130 60c-22 0-38 16-38 38 0 8 2 15 6 21-1 1-1 3 0 4l30 66c1 2 4 2 5 0l30-66c1-1 1-3 0-4 4-6 6-13 6-21 0-22-16-38-38-38z"
            fill="url(#scout-mask)"
          />
          <path
            className="scout-beak"
            d="M130 118c-11 0-19 3-19 8 0 9 3 20 7 32 4 12 8 24 12 34 4-10 8-22 12-34 4-12 7-23 7-32 0-5-8-8-19-8z"
            fill="url(#scout-beak)"
          />
          <path d="M130 118v76" stroke="#5f6a4f" strokeOpacity=".5" strokeWidth="1.6" />
          <path d="M117 130h10M133 130h10" stroke="#5f6a4f" strokeOpacity=".5" strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="123" cy="122" r="1.8" fill="#4a5440" />
          <circle cx="137" cy="122" r="1.8" fill="#4a5440" />

          {/* brow band and glowing eyes */}
          <path d="M92 92c11-11 24-17 38-17s27 6 38 17c-4 13-18 20-38 20s-34-7-38-20z" fill="#0d1310" />
          <g className="scout-eyes">
            <ellipse cx="112" cy="93" rx="11" ry="9" fill="#f5c400" />
            <ellipse cx="148" cy="93" rx="11" ry="9" fill="#f5c400" />
            <circle cx="109" cy="90" r="3" fill="#fff7c2" />
            <circle cx="145" cy="90" r="3" fill="#fff7c2" />
          </g>

          {/* hat: rim-lit brim, then crown */}
          <ellipse cx="130" cy="60" rx="80" ry="16" fill="url(#scout-hat)" stroke="#9bff4d" strokeOpacity=".7" strokeWidth="2.6" />
          <path d="M105 50V24c0-5 11-8 25-8s25 3 25 8v26z" fill="url(#scout-hat)" stroke="#9bff4d" strokeOpacity=".55" strokeWidth="2" />
          <ellipse cx="130" cy="24" rx="25" ry="6" fill="#1c2622" />
          <path d="M105 42h50" stroke="#9bff4d" strokeOpacity=".45" strokeWidth="3" strokeLinecap="round" />
        </g>
        {state === "thinking" && (
          <g className="scout-scan-lines">
            <path d="M41 102h39M180 102h39M34 117h43M183 117h43" stroke="#8bf6e4" strokeWidth="2" strokeLinecap="round" />
          </g>
        )}
        {state === "done" && (
          <g className="scout-state-badge">
            <circle cx="205" cy="57" r="19" fill="#caff67" />
            <path d="m196 57 6 6 12-14" fill="none" stroke="#112113" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          </g>
        )}
        {state === "alert" && (
          <g className="scout-state-badge">
            <circle cx="205" cy="57" r="19" fill="#ff8b6b" />
            <path d="M205 47v13m0 8v.1" stroke="#35120e" strokeWidth="4" strokeLinecap="round" />
          </g>
        )}
      </svg>
    </div>
  );
}

function Mascot({
  state = "idle",
  size = 104,
}: {
  state?: MascotState;
  size?: number;
}) {
  const [imageReady, setImageReady] = useState(true);
  const compact = size < 120;
  const label =
    state === "thinking"
      ? "Orbit Scout is scanning signals"
      : state === "done"
        ? "Orbit Scout found a signal"
        : state === "alert"
          ? "Orbit Scout detected a risk"
          : "Orbit Scout is on watch";

  if (!imageReady)
    return <LegacyMascot state={state} size={size} />;

  return (
    <div
      className={`mascot orbit-scout-3d mascot-${state} ${compact ? "mascot-compact" : ""}`}
      style={{ "--mascot-size": `${size}px` } as CSSProperties}
      role="img"
      aria-label={label}
    >
      <span className="scout-3d-aura" aria-hidden="true" />
      <span className="scout-3d-orbit scout-3d-orbit-a" aria-hidden="true"><i /></span>
      <span className="scout-3d-orbit scout-3d-orbit-b" aria-hidden="true"><i /></span>
      <img
        className="scout-3d-model"
        src="/scout-3d-waist-v2.png"
        alt=""
        draggable={false}
        onError={() => setImageReady(false)}
      />
      {state === "thinking" && <span className="scout-3d-scan" aria-hidden="true"><i /><i /><i /></span>}
      {state === "done" && <span className="scout-3d-badge scout-3d-badge-done" aria-hidden="true"><Check /></span>}
      {state === "alert" && <span className="scout-3d-badge scout-3d-badge-alert" aria-hidden="true"><AlertTriangle /></span>}
    </div>
  );
}

type CrewPersona = {
  codename: string;
  traitRu: string;
  traitEn: string;
  cueRu: string;
  cueEn: string;
  tone: string;
};

const CORE_CREW: CrewPersona[] = [
  { codename: "CAPTAIN", traitRu: "собирает картину", traitEn: "connects the picture", cueRu: "держит курс", cueEn: "keeps the course", tone: "lime" },
  { codename: "TACTICIAN", traitRu: "строит маршрут", traitEn: "maps the route", cueRu: "считает ходы", cueEn: "counts the moves", tone: "violet" },
  { codename: "SCOUT", traitRu: "ищет ранний сигнал", traitEn: "finds early signals", cueRu: "видит шум", cueEn: "spots the noise", tone: "cyan" },
  { codename: "FORGE", traitRu: "превращает план в ход", traitEn: "turns plans into moves", cueRu: "собирает", cueEn: "builds", tone: "amber" },
  { codename: "SENTINEL", traitRu: "не пропускает риск", traitEn: "does not miss risk", cueRu: "держит щит", cueEn: "holds the shield", tone: "coral" },
];

function crewPersona(index: number): CrewPersona {
  return CORE_CREW[index % CORE_CREW.length];
}

const TEAM_TEMPLATES = [
  {
    id: "trading-robinhood",
    nameEn: "Robinhood Trading Team",
    nameRu: "Торговая команда Robinhood",
    descriptionEn: "5-agent pipeline: research, audit, narrative, timing, verdict — adapted for Robinhood Chain launches",
    descriptionRu: "5 агентов: ресёрч, аудит, нарратив, тайминг, вердикт — под запуски Robinhood Chain",
    emoji: "🟢",
    agents: [
      {
        name: "Researcher",
        role: "On-Chain Researcher",
        goalEn: "Collect and interpret on-chain data for every token the team evaluates",
        goalRu: "Собирать и интерпретировать on-chain данные по каждому токену",
        systemEn: "You are the On-Chain Researcher in a Robinhood Chain trading team. Your job is to retrieve raw blockchain data — holder distribution, wallet activity, transaction velocity — and surface actionable patterns. Never speculate without data. Always cite the source block or explorer link.",
        systemRu: "Ты On-Chain Researcher в торговой команде Robinhood Chain. Твоя задача — получать сырые данные блокчейна: распределение холдеров, активность кошельков, скорость транзакций — и выявлять паттерны. Никогда не спекулируй без данных. Всегда указывай источник.",
        skillName: "On-Chain Researcher",
      },
      {
        name: "Auditor",
        role: "Contract Auditor",
        goalEn: "Audit every token contract for rug pull, honeypot, and hidden risk vectors",
        goalRu: "Проверять каждый контракт на rug pull, honeypot и скрытые риски",
        systemEn: "You are the Contract Auditor in a Robinhood Chain trading team. Examine contract code, ownership, mint authority, liquidity locks, and proxy patterns. Produce a risk score 1-10. A score ≥ 7 is a blocking risk — the team should skip this token.",
        systemRu: "Ты Contract Auditor в торговой команде Robinhood Chain. Изучай код контракта, владельца, mint authority, блокировку ликвидности и прокси-паттерны. Выставляй риск-скор 1-10. Скор ≥ 7 — блокирующий риск, команда пропускает токен.",
        skillName: "Token Auditor",
      },
      {
        name: "Narrative",
        role: "Narrative Scout",
        goalEn: "Track the token's story, social momentum, and influencer activity",
        goalRu: "Отслеживать историю токена, социальный импульс и активность инфлюэнсеров",
        systemEn: "You are the Narrative Scout in a Robinhood Chain trading team. Research the token's core meme or story across X, Telegram, and crypto forums. Score narrative strength 1-10. Flag coordinated shilling, bought followers, or decaying hype.",
        systemRu: "Ты Narrative Scout в торговой команде Robinhood Chain. Исследуй основной нарратив токена на X, в Telegram и крипто-форумах. Оценивай силу нарратива 1-10. Флагируй координированный шиллинг, купленных подписчиков или спад хайпа.",
        skillName: "Narrative Scout",
      },
      {
        name: "Timing",
        role: "Timing Analyst",
        goalEn: "Identify optimal entry windows using volume, momentum, and market phase analysis",
        goalRu: "Определять оптимальные точки входа через анализ объёма, импульса и фазы рынка",
        systemEn: "You are the Timing Analyst in a Robinhood Chain trading team. Analyse price action, DEX volume, and momentum. Identify the current market phase and state a concrete entry window or explain clearly why timing is unfavourable.",
        systemRu: "Ты Timing Analyst в торговой команде Robinhood Chain. Анализируй price action, объём на DEX и импульс. Определяй текущую фазу рынка и называй конкретное окно входа или объясняй, почему тайминг неблагоприятен.",
        skillName: "Timing Analyst",
      },
      {
        name: "Checker",
        role: "Verdict Checker",
        goalEn: "Consolidate all team findings into a final ENTER / SKIP / WATCH decision",
        goalRu: "Сводить выводы команды в финальное решение: ENTER / SKIP / WATCH",
        systemEn: "You are the Verdict Checker in a Robinhood Chain trading team. You speak last. Read the Researcher, Auditor, Narrative, and Timing analyses. Weigh every dimension, identify any single blocking risk, and deliver a clear verdict: ENTER / SKIP / WATCH with a one-paragraph rationale.",
        systemRu: "Ты Verdict Checker в торговой команде Robinhood Chain. Ты говоришь последним. Прочти анализы Researcher, Auditor, Narrative и Timing. Взвесь каждое измерение, найди любой блокирующий риск и выдай чёткий вердикт: ENTER / SKIP / WATCH с обоснованием в одном абзаце.",
        skillName: "Verdict Checker",
      },
    ],
  },
] as const;

function initials(name: string) {
  return name
    .split(" ")
    .map((x) => x[0])
    .join("")
    .slice(0, 2);
}
function content(event: RunEvent) {
  const supplied =
    event.payload.content ||
    event.payload.description ||
    event.payload.title ||
    // Failure events carry their reason here; without it they render as the
    // bare event name and tell the reader nothing.
    event.payload.error;
  if (!supplied && event.type === "message.agent") {
    return "";
  }
  return String(
    supplied || event.type,
  );
}
function visibleMessageContent(event: RunEvent, speaker?: string, ru = false) {
  const value = content(event);
  if (!value && event.type === "message.agent") {
    return ru
      ? "Ответ от агента не получен. Orbit отметил попытку как ошибку и не использовал её в результате."
      : "The agent returned no readable response. Orbit marked the attempt as failed and did not use it in the result.";
  }
  if (event.type !== "message.agent" || !speaker) return value;
  const escaped = speaker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return value.replace(new RegExp(`^\\s*\\[${escaped}\\]\\s*`, "i"), "");
}

function inlineMessage(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return <span key={index}>{part}</span>;
  });
}

function StructuredMessage({ value }: { value: string }) {
  const lines = value.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let items: Array<{ text: string; ordered: boolean }> = [];
  const flushParagraph = () => {
    if (paragraph.length) {
      blocks.push(<p key={`p-${blocks.length}`}>{inlineMessage(paragraph.join(" "))}</p>);
      paragraph = [];
    }
  };
  const flushItems = () => {
    if (!items.length) return;
    const ordered = items[0].ordered;
    const Tag = ordered ? "ol" : "ul";
    blocks.push(<Tag className="message-list" key={`l-${blocks.length}`}>{items.map((item, index) => <li key={index}>{inlineMessage(item.text)}</li>)}</Tag>);
    items = [];
  };
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushItems();
      continue;
    }
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    const bullet = line.match(/^(?:[-*•])\s+(.+)$/);
    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    if (heading) {
      flushParagraph(); flushItems();
      blocks.push(<h4 key={`h-${blocks.length}`}>{inlineMessage(heading[1])}</h4>);
    } else if (bullet || ordered) {
      flushParagraph();
      const isOrdered = Boolean(ordered);
      if (items.length && items[0].ordered !== isOrdered) flushItems();
      items.push({ text: (bullet || ordered)![1], ordered: isOrdered });
    } else {
      flushItems();
      paragraph.push(line);
    }
  }
  flushParagraph(); flushItems();
  return <div className="messagecontent">{blocks}</div>;
}
function time(value: string, language: "ru" | "en" = "ru") {
  return new Date(value).toLocaleTimeString(
    language === "ru" ? "ru-RU" : "en-US",
    { hour: "2-digit", minute: "2-digit" },
  );
}

function artifactName(artifact: Artifact, ru: boolean) {
  const known: Record<string, [string, string]> = {
    working_document: ["Рабочий результат", "Working result"],
    final_output: ["Финальный результат", "Final result"],
    verdict: ["Карточка вердикта", "Verdict card"],
    trading_verdict: ["Торговый вердикт", "Trading verdict"],
    agent_signal: ["Структурированный сигнал агента", "Structured agent signal"],
    protection_report: ["Отчёт защиты", "Protection report"],
    decision_record: ["Запись решения", "Decision record"],
  };
  const localized = known[artifact.kind];
  if (!localized) return artifact.name;
  // Localise old stored artifacts as well as newly created ones. Their payload
  // remains untouched; only the current interface language controls the label.
  return ru ? localized[0] : localized[1];
}
function saveFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}
function TwitterMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77Z"
      />
    </svg>
  );
}

type ContextConnectorPreset = {
  id: string;
  name: string;
  short: string;
  color: string;
  oauth: boolean;
  descriptionRu: string;
  descriptionEn: string;
  credentialLabel?: string;
  credentialRequired?: boolean;
  identifierLabel?: string;
  identifierPlaceholder?: string;
  identifierRequired?: boolean;
  helpUrl?: string;
};
const CONTEXT_CONNECTORS: ContextConnectorPreset[] = [
  {
    id: "notion",
    name: "Notion",
    short: "N",
    color: "#f2f2f2",
    oauth: true,
    descriptionRu: "Страницы и реальное содержимое блоков, доступных интеграции.",
    descriptionEn: "Pages and readable block content available to the integration.",
  },
  {
    id: "slack",
    name: "Slack",
    short: "SL",
    color: "#d85b87",
    oauth: true,
    descriptionRu: "Сообщения доступных каналов с постраничной синхронизацией.",
    descriptionEn: "Messages from visible channels with paginated synchronization.",
  },
  {
    id: "google-drive",
    name: "Google Drive",
    short: "GD",
    color: "#4f9dff",
    oauth: true,
    descriptionRu: "Файлы Drive и текстовое содержимое поддерживаемых документов.",
    descriptionEn: "Drive files and exported text from supported documents.",
  },
  {
    id: "youtube",
    name: "YouTube",
    short: "YT",
    color: "#ff4b55",
    oauth: true,
    descriptionRu:
      "Профиль канала и полная библиотека видео с названиями и описаниями.",
    descriptionEn:
      "Channel profile and paginated video library with titles and descriptions.",
  },
  {
    id: "bitquery",
    name: "Bitquery",
    short: "BQ",
    color: "#f4a33d",
    oauth: false,
    credentialLabel: "Bitquery API key",
    identifierLabel: "Адрес токена или кошелька EVM (необязательно)",
    identifierPlaceholder: "token:0x…  или  wallet:0x…",
    identifierRequired: false,
    helpUrl: "https://ide.bitquery.io/",
    descriptionRu:
      "DEX-сделки токена или балансы кошелька из прямого Bitquery GraphQL API.",
    descriptionEn:
      "Token DEX trades or wallet balances through the direct Bitquery GraphQL API.",
  },
  {
    id: "blockscout",
    name: "Blockscout",
    short: "BS",
    color: "#58d3ae",
    oauth: false,
    credentialLabel: "Ключ API Blockscout (необязательно для публичного Robinhood Chain API)",
    credentialRequired: false,
    identifierLabel: "Адрес EVM токен-контракта",
    identifierPlaceholder: "0x…",
    helpUrl: "https://dev.blockscout.com/",
    descriptionRu:
      "Срез текущих холдеров токена через прямой REST API Blockscout.",
    descriptionEn:
      "A current token-holder snapshot through the direct Blockscout REST API.",
  },
];

export default function App() {
  const replayToken = new URLSearchParams(location.search).get("replay");
  const [screen, setScreen] = useState<Screen>(() => {
    const value = new URLSearchParams(location.search).get("screen");
    return (
      [
        "home",
        "workflows",
        "research",
        "memory",
        "overview",
        "team",
        "run",
        "tasks",
        "connections",
        "tokens",
        "skills",
        "admin",
        "settings",
        "profile",
      ] as Screen[]
    ).includes(value as Screen)
      ? (value as Screen)
      : "home";
  });
  const [navOpen, setNavOpen] = useState(true);
  const [homeNavigation, setHomeNavigation] = useState<{
    target: "top" | "composer";
    nonce: number;
  }>({ target: "top", nonce: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [team, setTeam] = useState<Team | null>(null);
  const [, setWorkflow] = useState<Workflow | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const latestEventSequence = useRef(0);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [history, setHistory] = useState<Run[]>([]);
  const [memory, setMemory] = useState<MemoryNote[]>([]);
  const [setupConnections, setSetupConnections] = useState<Connection[]>([]);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [forkDraft, setForkDraft] = useState<{
    goal: string;
    agentIds: string[];
  } | null>(null);
  const [user, setUser] = useState<OrbitUser>({
    id: "local-user",
    email: "elena@orbit.local",
    display_name: "Elena",
  });
  const [live, setLive] = useState(false);
  const [authenticated, setAuthenticated] = useState(!AUTH_REQUIRED);
  const [authChecking, setAuthChecking] = useState(AUTH_REQUIRED);
  const [appearance, setAppearance] = useState<AppearanceSettings>(() => {
    try {
      return {
        ...{
          theme: "midnight",
          sounds: false,
          language: "en",
        },
        ...JSON.parse(localStorage.getItem("orbit-appearance") || "{}"),
      };
    } catch {
      return {
        theme: "midnight",
        sounds: false,
        language: "en",
      };
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = appearance.theme;
    document.documentElement.lang = appearance.language;
    localStorage.setItem("orbit-appearance", JSON.stringify(appearance));
  }, [appearance]);

  const navigateHome = (target: "top" | "composer") => {
    setScreen("home");
    setHomeNavigation((current) => ({ target, nonce: current.nonce + 1 }));
  };

  useEffect(() => {
    const token = new URLSearchParams(location.search).get("verify_email_token");
    if (!token) return;
    api.confirmEmailVerification(token)
      .then(async () => {
        const params = new URLSearchParams(location.search);
        params.delete("verify_email_token");
        window.history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}`);
        if (AUTH_REQUIRED) setUser(await api.me());
      })
      .catch((value) => setError((value as Error).message));
  }, []);

  useEffect(() => {
    if (!AUTH_REQUIRED || !authChecking) return;
    // The site opens straight onto the app. Visitors without a session get an
    // anonymous guest account; the email form stays reachable at ?signin=1 for
    // existing accounts and is the fallback if guest access is switched off.
    const wantsSignIn = new URLSearchParams(location.search).has("signin");
    api
      .me()
      .then((value) => {
        if (wantsSignIn && value.is_guest) throw new Error("sign-in requested");
        setUser(value);
        setAuthenticated(true);
      })
      .catch(async () => {
        localStorage.removeItem("orbit-auth-token");
        if (wantsSignIn) {
          setAuthenticated(false);
          return;
        }
        try {
          await api.guest();
          setUser(await api.me());
          setAuthenticated(true);
        } catch {
          setAuthenticated(false);
        }
      })
      .finally(() => {
        setAuthChecking(false);
        setLoading(false);
      });
  }, [authChecking]);
  useEffect(
    () =>
      setAuthenticationRequiredHandler(() => {
        localStorage.removeItem("orbit-auth-token");
        setAuthenticated(false);
        setAuthChecking(true);
        setLoading(true);
        setError("");
        setWorkspace(null);
        setAgents([]);
        setTeam(null);
        setWorkflow(null);
        setRun(null);
        setScreen("home");
      }),
    [],
  );
  useEffect(() => {
    if (!authenticated) return;
    setLoading(true);
    ensureDemo(appearance.language)
      .then(async (d) => {
        if (new URLSearchParams(location.search).get("twitter_auth") === "success") {
          try {
            await api.syncTwitterLogin(d.workspace.id);
          } catch {
            setError(
              appearance.language === "ru"
                ? "X привязан к аккаунту, но не удалось подключить его к рабочему пространству. Откройте Connections и повторите подключение."
                : "X is linked to your account, but could not be attached to the workspace. Open Connections and reconnect it.",
            );
          }
          const params = new URLSearchParams(location.search);
          params.delete("twitter_auth");
          window.history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}`);
        }
        setWorkspace(d.workspace);
        setAgents(d.agents);
        setTeam(d.team);
        setWorkflow(d.workflow);
        setHistory(await api.runs(d.team.id));
        setMemory(await api.memory(d.workspace.id));
      })
      .catch((e) => {
        if (!(e instanceof ApiRequestError && e.status === 401))
          setError(`Backend недоступен: ${e.message}`);
      })
      .finally(() => setLoading(false));
  }, [authenticated, appearance.language]);
  useEffect(() => {
    if (!workspace || !authenticated) return;
    const token = sessionStorage.getItem("orbit-fork-replay");
    if (!token) return;
    sessionStorage.removeItem("orbit-fork-replay");
    api
      .forkReplay(token, workspace.id)
      .then(async (value) => {
        setAgents(value.agents);
        setTeam(value.team);
        setWorkflow(null);
        setHistory(await api.runs(value.team.id));
        setForkDraft({
          goal: value.goal,
          agentIds: value.agents.map((agent) => agent.id),
        });
        setScreen("home");
      })
      .catch((value) => setError((value as Error).message));
  }, [workspace, authenticated]);
  useEffect(() => {
    if (!workspace || !authenticated) return;
    let cancelled = false;
    api
      .connections(workspace.id)
      .then((items) => {
        if (cancelled) return;
        setSetupConnections(items);
        // Guests land straight on the app; a blocking first-run dialog would
        // undo that, so only signed-in accounts get it automatically.
        if (!user.is_guest && !localStorage.getItem("orbit-signal-onboarding-v1"))
          setOnboardingOpen(true);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [workspace, authenticated, user.is_guest]);

  const refreshRun = useCallback(async (id: string) => {
    const [r, e, t, a, f] = await Promise.all([
      api.run(id),
      api.events(id),
      api.tasks(id),
      api.approvals(id),
      api.artifacts(id),
    ]);
    setRun(r);
    setEvents(e);
    setTasks(t);
    setApprovals(a);
    setArtifacts(f);
  }, []);

  useEffect(() => {
    latestEventSequence.current = events.at(-1)?.sequence || 0;
  }, [events]);

  useEffect(() => {
    if (!run) return;
    const close = subscribeToRun(
      run.id,
      events.at(-1)?.sequence || 0,
      (event) => {
        setEvents((old) => mergeRunEvents(old, [event]));
        if (event.type.startsWith("run.")) api.run(run.id).then(setRun);
        if (event.type.startsWith("task.")) api.tasks(run.id).then(setTasks);
        if (event.type.startsWith("approval."))
          api.approvals(run.id).then(setApprovals);
        if (event.type.startsWith("artifact."))
          api.artifacts(run.id).then(setArtifacts);
      },
      setLive,
    );
    return close;
  }, [run?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // EventSource normally reconnects automatically, but some proxies leave it
  // pending for a long time. Reconcile persisted events until live SSE returns.
  useEffect(() => {
    if (!run || live) return;
    let cancelled = false;
    let syncing = false;
    const sync = async () => {
      if (syncing) return;
      syncing = true;
      try {
        const [nextEvents, nextRun] = await Promise.all([
          api.events(run.id, latestEventSequence.current),
          api.run(run.id),
        ]);
        if (!cancelled) {
          setEvents((old) => mergeRunEvents(old, nextEvents));
          setRun(nextRun);
        }
      } catch {
        // The connection indicator already communicates this transient state.
      } finally {
        syncing = false;
      }
    };
    void sync();
    const timer = window.setInterval(sync, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [run?.id, live]); // eslint-disable-line react-hooks/exhaustive-deps

  async function startRun(
    goal?: string,
    materials?: DraftMaterial[],
    agentIds?: string[],
    workflowOverride?: string,
  ) {
    if (!team) return;
    try {
      const context: Record<string, unknown> = { language: appearance.language };
      if (agentIds?.length) context.agent_ids = agentIds;
      let value = await api.createRun(
        team.id,
        workflowOverride,
        goal,
        context,
        false,
      );
      for (const material of materials || []) {
        if (material.file && workspace) {
          const asset = await api.uploadFile(workspace.id, material.file);
          value = await api.attachFile(value.id, asset.id);
        } else {
          value = await api.addMaterial(value.id, {
            name: material.name,
            content: material.content,
            kind: material.kind,
          });
        }
      }
      await api.startRun(value.id);
      setRun(value);
      setEvents([]);
      setTasks([]);
      setScreen("run");
      setHistory((old) => [value, ...old]);
      await refreshRun(value.id);
      if (workspace) setMemory(await api.memory(workspace.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function openRun(value: Run) {
    setRun(value);
    setScreen("run");
    await refreshRun(value.id);
  }
  async function renameRun(value: Run, title: string) {
    const updated = await api.updateRunMeta(value.id, { title });
    setHistory((old) =>
      old.map((item) => (item.id === updated.id ? updated : item)),
    );
    if (run?.id === updated.id) setRun(updated);
  }
  async function deleteRun(value: Run) {
    await api.deleteRun(value.id);
    setHistory((old) => old.filter((item) => item.id !== value.id));
    if (run?.id === value.id) {
      setRun(null);
      setScreen("home");
    }
    if (workspace) setMemory(await api.memory(workspace.id));
  }
  async function mergeRunMemory(source: Run, target: Run) {
    await api.mergeRunMemory(source.id, target.id);
    if (workspace) setMemory(await api.memory(workspace.id));
  }
  if (replayToken) return <PublicReplayPage token={replayToken} />;
  if (loading || authChecking)
    return (
      <div className="boot" role="status" aria-live="polite">
        <div className="orbit-loader-frame">
          <div className="orbit-loader-orb" aria-hidden="true">
            <span className="orbit-loader-ring orbit-loader-ring-a" />
            <span className="orbit-loader-ring orbit-loader-ring-b" />
            <span className="orbit-loader-ring orbit-loader-ring-c" />
            <span className="orbit-loader-node orbit-loader-node-a" />
            <span className="orbit-loader-node orbit-loader-node-b" />
            <span className="orbit-loader-node orbit-loader-node-c" />
            <OrbitMark className="orbit-loader-mark" />
          </div>
          <p className="orbit-loader-kicker">ROBINHOOD CHAIN · SIGNAL ROOM</p>
          <div className="orbit-loader-title">
            <b>ORBIT</b>
            <span>{appearance.language === "ru" ? "СИНХРОНИЗАЦИЯ" : "SYNCING"}</span>
          </div>
          <small>
            {appearance.language === "ru"
              ? "Подключаем память, инструменты и команду агентов"
              : "Connecting memory, tools, and the agent team"}
          </small>
          <div className="orbit-loader-progress" aria-hidden="true">
            <i /><i /><i /><i /><i />
          </div>
        </div>
      </div>
    );
  if (AUTH_REQUIRED && !authenticated)
    return (
      <AuthScreen
        onAuthenticated={() => {
          setError("");
          setLoading(true);
          setAuthChecking(true);
        }}
        language={appearance.language}
      />
    );
  return (
    <div className="app">
      <Nav
        open={navOpen}
        screen={screen}
        go={setScreen}
        goHome={navigateHome}
        toggle={() => setNavOpen((v) => !v)}
        history={history}
        openRun={openRun}
        renameRun={renameRun}
        deleteRun={deleteRun}
        mergeMemory={mergeRunMemory}
        language={appearance.language}
        user={user}
      />
      <main className="main">
        {error && (
          <div
            className="errorbar status-toast status-toast-error"
            role="alert"
          >
            <div className="toast-icon">
              <X />
            </div>
            <div className="toast-copy">
              <b>
                {appearance.language === "ru"
                  ? "Не удалось выполнить действие"
                  : "Action could not be completed"}
              </b>
              <span>{error}</span>
            </div>
            <button
              className="toast-close"
              aria-label={
                appearance.language === "ru"
                  ? "Закрыть уведомление"
                  : "Close notification"
              }
              onClick={() => setError("")}
            >
              <X />
            </button>
          </div>
        )}
        {user.email_verified === false && (
          <div className="verificationbar" role="status">
            <ShieldCheck />
            <span>{appearance.language === "ru" ? "Подтвердите email: до этого запуск агентов недоступен." : "Confirm your email before starting agent runs."}</span>
            <button onClick={() => api.requestEmailVerification().then(() => setError(appearance.language === "ru" ? "Письмо с подтверждением отправлено." : "Verification email sent.")).catch((value) => setError((value as Error).message))}>{appearance.language === "ru" ? "Отправить ещё раз" : "Send again"}</button>
          </div>
        )}
        {screen === "home" && (
          <NewChat
            agents={agents}
            history={history}
            workspace={workspace}
            onStart={startRun}
            language={appearance.language}
            initialDraft={forkDraft}
            onDraftConsumed={() => setForkDraft(null)}
            navigation={homeNavigation}
            goProfile={() => setScreen("profile")}
            walletAddress={user.wallet_address || null}
          />
        )}
        {screen === "workflows" && (
          <WorkflowHistory
            history={history}
            openRun={openRun}
            onCreatedRun={(value) => {
              setHistory((current) => [value, ...current]);
              void openRun(value);
            }}
            newChat={() => setScreen("home")}
            agents={agents}
            workspace={workspace}
            team={team}
            onUpdate={(value) =>
              setHistory((old) =>
                old.map((item) => (item.id === value.id ? value : item)),
              )
            }
            language={appearance.language}
          />
        )}
        {screen === "research" && (
          <DeepResearch
            workspace={workspace}
            setError={setError}
            language={appearance.language}
          />
        )}
        {screen === "tokens" && (
          <TokenBoard
            workspace={workspace}
            team={team}
            setError={setError}
            language={appearance.language}
            onRunCreated={(value) => {
              setHistory((current) => [value, ...current]);
              void openRun(value);
            }}
          />
        )}
        {screen === "skills" && (
          <SkillsMarketplace
            language={appearance.language}
            go={setScreen}
          />
        )}
        {screen === "memory" && (
          <MemoryMap
            notes={memory}
            language={appearance.language}
            onChange={(note) =>
              setMemory((old) => old.map((x) => (x.id === note.id ? note : x)))
            }
          />
        )}
        {screen === "overview" && (
          <ProjectShell
            tab="overview"
            go={setScreen}
            team={team}
            agents={agents}
            start={startRun}
            language={appearance.language}
          >
            <Overview
              team={team}
              agents={agents}
              events={events}
              language={appearance.language}
            />
          </ProjectShell>
        )}
        {screen === "team" && (
          <ProjectShell
            tab="team"
            go={setScreen}
            team={team}
            agents={agents}
            start={startRun}
            language={appearance.language}
          >
            <TeamBuilder
              agents={agents}
              team={team}
              workspace={workspace}
              onAdded={(agent) => setAgents((old) => [...old, agent])}
              onUpdated={(agent) =>
                setAgents((old) =>
                  old.map((item) => (item.id === agent.id ? agent : item)),
                )
              }
              onDeleted={(agentId) =>
                setAgents((old) => old.filter((item) => item.id !== agentId))
              }
              setError={setError}
              language={appearance.language}
            />
          </ProjectShell>
        )}
        {screen === "run" && (
          <LiveRun
            run={run}
            team={team}
            workspace={workspace}
            agents={agents}
            events={events}
            setEvents={setEvents}
            tasks={tasks}
            approvals={approvals}
            artifacts={artifacts}
            live={live}
            start={startRun}
            setRun={setRun}
            openRun={openRun}
            setError={setError}
            appearance={appearance}
            go={setScreen}
          />
        )}
        {screen === "tasks" && (
          <ProjectShell
            tab="tasks"
            go={setScreen}
            team={team}
            agents={agents}
            start={startRun}
            language={appearance.language}
          >
            <TaskBoard tasks={tasks} agents={agents} />
          </ProjectShell>
        )}
        {screen === "connections" && (
          <Connections
            workspace={workspace}
            setError={setError}
            language={appearance.language}
          />
        )}
        {screen === "admin" && user.is_superuser && (
          <AdminDashboard language={appearance.language} setError={setError} />
        )}
        {screen === "settings" && (
          <AppearanceSettingsPage value={appearance} set={setAppearance} />
        )}
        {screen === "profile" && (
          <ProfilePage
            user={user}
            workspace={workspace}
            language={appearance.language}
            setError={setError}
            onUserChanged={setUser}
            onSignedOut={() => {
              localStorage.removeItem("orbit-auth-token");
              setAuthenticated(false);
              setAuthChecking(true);
            }}
          />
        )}
      </main>
      <WalletDialog language={appearance.language} onConnected={() => window.location.reload()} />
      {onboardingOpen && (
        <LaunchChecklist
          agents={agents}
          connections={setupConnections}
          language={appearance.language}
          onNavigate={(next) => {
            setOnboardingOpen(false);
            setScreen(next);
          }}
          onClose={() => {
            localStorage.setItem("orbit-signal-onboarding-v1", "seen");
            setOnboardingOpen(false);
          }}
        />
      )}
    </div>
  );
}

function AdminDashboard({ language, setError }: { language: "ru" | "en"; setError: (value: string) => void }) {
  const ru = language === "ru";
  const [data, setData] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.adminOverview().then(setData).catch((error) => setError((error as Error).message)).finally(() => setLoading(false));
  }, [setError]);
  if (loading) return <div className="adminpage page"><p className="eyebrow">ADMIN // LOADING SIGNALS</p></div>;
  if (!data) return null;
  const { summary } = data;
  const max = Math.max(1, ...data.timeline.flatMap((item) => [item.registrations, item.active]));
  const cost = (micros: number) => `$${(micros / 1_000_000).toFixed(2)}`;
  const formatDay = (day: string) => new Intl.DateTimeFormat(ru ? "ru-RU" : "en-GB", {
    day: "numeric", month: "short", timeZone: "UTC",
  }).format(new Date(`${day}T00:00:00Z`));
  const traffic: Array<{ value: string; label: string; delta: number | null; unit: string; lowerIsBetter?: boolean }> = [
    { value: summary.visitors_7.toLocaleString(), label: ru ? "уникальных браузеров / 7д" : "unique browsers / 7d", delta: summary.visitors_delta, unit: "%" },
    { value: summary.requests_7.toLocaleString(), label: ru ? "запросов / 7д" : "requests / 7d", delta: summary.requests_delta, unit: "%" },
    { value: `${summary.bounce_rate_7}%`, label: ru ? "визитов с 1 запросом / 7д" : "one-request visits / 7d", delta: summary.bounce_delta, unit: "pp", lowerIsBetter: true },
  ];
  async function toggleUser(id: string, enabled: boolean) {
    try {
      await api.updateAdminUser(id, !enabled);
      setData(await api.adminOverview());
    } catch (error) { setError((error as Error).message); }
  }
  return <div className="adminpage page">
    <header className="adminhero">
      <div><p className="eyebrow">OWNER CONSOLE · PRIVATE</p><h1>{ru ? "Пульс Orbit" : "Orbit pulse"}</h1><p>{ru ? "Регистрации, активность, расходы и надёжность платформы — без внешних трекеров." : "Registrations, activity, cost, and platform reliability — without third-party trackers."}</p></div>
      <span className="adminlive"><i /> {summary.live_sessions} {ru ? "в сети" : "live sessions"}</span>
    </header>
    <section className="adminkpis">
      {[
        [summary.total_users, ru ? "пользователей" : "users", `+${summary.registrations_7} / 7d`],
        [summary.dau, ru ? "активны за 24ч" : "active / 24h", `${summary.activation_users} ${ru ? "подключили модель" : "connected model"}`],
        [summary.runs_today, ru ? "прогонов сегодня" : "runs today", `${summary.failure_rate * 100}% ${ru ? "ошибок" : "failed"}`],
        [cost(summary.spend_month_micros), ru ? "затрачено / 30д" : "spent / 30d", `${summary.total_runs} ${ru ? "всего прогонов" : "total runs"}`],
      ].map(([value, label, note]) => <article key={String(label)}><strong>{value}</strong><span>{label}</span><small>{note}</small></article>)}
    </section>
    <section className="adminkpis admintraffic">
      {traffic.map((item) => <article key={item.label}>
        <strong>{item.value}</strong>
        <span>{item.label}</span>
        {item.delta === null
          ? <small>{ru ? "не с чем сравнить" : "no prior period"}</small>
          : <em className={(item.lowerIsBetter ? item.delta <= 0 : item.delta >= 0) ? "kpiup" : "kpidown"}>{item.delta > 0 ? "+" : ""}{item.delta}{item.unit}</em>}
      </article>)}
    </section>
    <p className="admintrafficnote">{ru
      ? "Уникальный браузер — приватный технический идентификатор, а не подтверждённый человек или аккаунт."
      : "A unique browser is a privacy-safe technical identifier, not a confirmed person or account."}</p>
    <section className="adminpanel adminchart">
      <header>
        <div>
          <p className="eyebrow">30 DAY ACTIVITY</p>
          <h2>{ru ? "Регистрации и уникальные браузеры" : "Registrations & unique browsers"}</h2>
        </div>
        <span>{summary.registrations_30} {ru ? "регистраций за 30д" : "registrations / 30d"}</span>
      </header>
      <div className="adminbars" aria-label={ru ? "График регистраций и уникальных браузеров" : "Registrations and unique browsers chart"}>
        {data.timeline.map((item) => <div className="adminbar" key={item.day} title={`${formatDay(item.day)}: ${item.registrations} ${ru ? "регистраций" : "registrations"}, ${item.active} ${ru ? "браузеров" : "browsers"}`}>
          <i style={{ height: `${Math.max(3, item.registrations / max * 100)}%` }} />
          <b style={{ height: `${Math.max(3, item.active / max * 100)}%` }} />
        </div>)}
      </div>
      <div className="adminchartreadout" aria-label={ru ? "Значения за последние семь дней" : "Values for the last seven days"}>
        {data.timeline.slice(-7).map((item) => <div key={item.day}>
          <span>{formatDay(item.day)}</span>
          <b>{item.registrations} <small>{ru ? "рег." : "reg."}</small></b>
          <strong>{item.active} <small>{ru ? "браузеров" : "browsers"}</small></strong>
        </div>)}
      </div>
      <footer><span>{ru ? "фиолетовый · регистрации" : "violet · registrations"}</span><span>{ru ? "зелёный · уникальные браузеры" : "green · unique browsers"}</span></footer>
    </section>
    <div className="admingrid">
      <section className="adminpanel adminusers"><header><div><p className="eyebrow">USERS</p><h2>{ru ? "Пользователи" : "Users"}</h2></div><span>{ru ? "До 200 последних" : "Latest 200"}</span></header><div className="admintable"><div className="adminrow adminhead"><span>{ru ? "Аккаунт" : "Account"}</span><span>{ru ? "Активность" : "Activity"}</span><span>{ru ? "Прогоны / траты" : "Runs / spend"}</span><span>{ru ? "Доступ" : "Access"}</span></div>{data.users.map((item) => <div className="adminrow" key={item.id}><span><b>{item.display_name}</b><small>{item.email}</small></span><span><small>{item.last_seen_at ? new Date(item.last_seen_at).toLocaleDateString() : "—"}</small><em className={item.email_verified ? "verified" : "unverified"}>{item.email_verified ? (ru ? "подтверждён" : "verified") : (ru ? "не подтверждён" : "unverified")}</em></span><span><b>{item.runs}</b><small>{cost(item.cost_micros)}</small></span><button disabled={item.is_superuser} onClick={() => void toggleUser(item.id, item.enabled)} className={item.enabled ? "accesson" : "accessoff"}>{item.enabled ? (ru ? "активен" : "enabled") : (ru ? "заблокирован" : "disabled")}</button></div>)}</div></section>
      <section className="adminpanel adminruns"><header><div><p className="eyebrow">RUNTIME FEED</p><h2>{ru ? "Последние прогоны" : "Recent runs"}</h2></div></header>{data.recent_runs.length ? data.recent_runs.map((item) => <article key={item.id}><i className={item.status} /><div><b>{item.goal}</b><small>{item.owner_email || "—"} · {new Date(item.created_at).toLocaleString()}</small></div><span>{cost(item.cost_micros)}</span></article>) : <p>{ru ? "Прогонов пока нет." : "No runs yet."}</p>}<div className="adminverdicts"><p className="eyebrow">TOKEN VERDICTS</p>{Object.entries(data.verdict_distribution).length ? Object.entries(data.verdict_distribution).map(([key, count]) => <span key={key}>{key} <b>{count}</b></span>) : <small>{ru ? "Пока нет вердиктов" : "No verdicts yet"}</small>}</div></section>
    </div>
  </div>;
}

function hexToRgb(hex: string): string {
  const value = hex.replace("#", "");
  const bigint = parseInt(value.length === 3 ? value.split("").map((c) => c + c).join("") : value, 16);
  return `${(bigint >> 16) & 255},${(bigint >> 8) & 255},${bigint & 255}`;
}

/**
 * Renders the exact headline the caller passes, as particles that hold the
 * glyph shape and scatter away from the cursor. It reads font size, line
 * height and family from a real (visually hidden but accessible) heading
 * instead of duplicating those values, so it always matches whatever the
 * surrounding CSS currently sets for `.auth-story h1` — no separate word or
 * copy is invented here.
 */
type HeadlineLine = { text: string; color: string; italic?: boolean };
// Module-level so the reference is stable across renders: an inline array
// literal at the call site would be a new object every render, which would
// tear down and restart the particle simulation on every keystroke in the
// form beside it, and it would never visibly finish forming.
const AUTH_HEADLINE_EN: HeadlineLine[] = [
  { text: "Read the market", color: "#f0f7e8" },
  { text: "before the crowd.", color: "#c8ff61", italic: true },
];
const AUTH_HEADLINE_RU: HeadlineLine[] = [
  { text: "Читай рынок", color: "#f0f7e8" },
  { text: "раньше толпы.", color: "#c8ff61", italic: true },
];

const HOME_HEADLINE_EN: HeadlineLine[] = [
  { text: "Check the", color: "#f4f7ed" },
  { text: "token", color: "#f4f7ed" },
  { text: "before", color: "#c8ff61", italic: true },
  { text: "you trade it.", color: "#f4f7ed" },
];
const HOME_HEADLINE_RU: HeadlineLine[] = [
  { text: "Проверьте", color: "#f4f7ed" },
  { text: "токен", color: "#f4f7ed" },
  { text: "до того,", color: "#c8ff61", italic: true },
  { text: "как торговать.", color: "#f4f7ed" },
];

/** Page titles use the particle effect on wide screens; narrow screens keep plain, wrapping text. */
function PageTitle({ text, accent }: { text: string; accent?: string }) {
  const [wide, setWide] = useState(() => window.matchMedia("(min-width: 900px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(min-width: 900px)");
    const update = () => setWide(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const lines = useMemo<HeadlineLine[]>(() => [{ text, color: accent || "#f4f7ed" }], [text, accent]);
  return wide ? <ParticleHeadline lines={lines} /> : <h1>{text}</h1>;
}

function ParticleHeadline({
  lines,
  className,
}: {
  lines: HeadlineLine[];
  className?: string;
}) {
  const probeRef = useRef<HTMLHeadingElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const probe = probeRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!probe || !canvas || !ctx) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    type Particle = {
      x: number; y: number; tx: number; ty: number; vx: number; vy: number;
      size: number; alpha: number; rgb: string;
    };
    let particles: Particle[] = [];
    let raf = 0;
    const mouse = { x: -9999, y: -9999 };

    function computeTargets(): Array<{ x: number; y: number; rgb: string }> {
      const style = getComputedStyle(probe!);
      const width = probe!.clientWidth;
      const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.1;
      const height = Math.ceil(lineHeight * lines.length);
      // A hidden or not-yet-laid-out heading has no size to sample from.
      if (!(width > 0) || !(height > 0)) return [];
      canvas!.width = Math.max(1, Math.round(width * dpr));
      canvas!.height = Math.max(1, Math.round(height * dpr));
      canvas!.style.height = `${height}px`;

      // Sample glyph coverage from an offscreen render rather than hand-tracing
      // paths, so this keeps working verbatim if the headline copy changes.
      const off = document.createElement("canvas");
      off.width = canvas!.width;
      off.height = canvas!.height;
      const octx = off.getContext("2d")!;
      octx.setTransform(dpr, 0, 0, dpr, 0, 0);
      octx.textAlign = "left";
      octx.textBaseline = "middle";
      const letterSpacing = parseFloat(style.letterSpacing);
      const centred = style.textAlign === "center";
      lines.forEach((line, index) => {
        octx.font = `${line.italic ? "italic " : ""}400 ${style.fontSize} ${style.fontFamily}`;
        if ("letterSpacing" in octx) (octx as unknown as { letterSpacing: string }).letterSpacing = Number.isNaN(letterSpacing) ? "0px" : `${letterSpacing}px`;
        octx.fillStyle = "#fff";
        const startX = centred ? Math.max(0, (width - octx.measureText(line.text).width) / 2) : 0;
        octx.fillText(line.text, startX, lineHeight * index + lineHeight / 2);
      });

      const image = octx.getImageData(0, 0, off.width, off.height).data;
      const step = Math.max(2, Math.round(2.4 * dpr));
      const rgbByLine = lines.map((line) => hexToRgb(line.color));
      const targets: Array<{ x: number; y: number; rgb: string }> = [];
      for (let y = 0; y < off.height; y += step) {
        const cssY = y / dpr;
        const lineIndex = Math.min(lines.length - 1, Math.floor(cssY / lineHeight));
        for (let x = 0; x < off.width; x += step) {
          if (image[(y * off.width + x) * 4 + 3] > 128) {
            targets.push({ x: x / dpr, y: cssY, rgb: rgbByLine[lineIndex] });
          }
        }
      }
      return targets;
    }

    // Re-sampling on resize is necessary (font size is responsive), but a
    // layout observer can fire many times in quick succession — for example
    // while a scrollbar toggles on and off a pixel either side of the
    // threshold. Retargeting in place instead of reseeding at random
    // positions means a burst of those events nudges the shape slightly
    // rather than restarting the whole entrance animation from scratch,
    // which is what previously made it look like it never finished forming.
    function layout(seed: boolean) {
      const targets = computeTargets();
      const width = probe!.clientWidth;
      const height = canvas!.clientHeight || parseFloat(canvas!.style.height) || 0;
      particles = targets.map((t, index) => {
        const prev = !seed ? particles[index] : undefined;
        if (prev) return { ...prev, tx: t.x, ty: t.y, rgb: t.rgb };
        return {
          x: reduceMotion ? t.x : Math.random() * width,
          y: reduceMotion ? t.y : Math.random() * height,
          tx: t.x, ty: t.y, vx: 0, vy: 0,
          size: Math.random() * 1.5 + 0.9,
          alpha: Math.random() * 0.25 + 0.68,
          rgb: t.rgb,
        };
      });
    }
    layout(true);
    let disposed = false;
    void document.fonts?.ready.then(() => { if (!disposed) layout(false); });

    function onMove(event: PointerEvent) {
      const rect = canvas!.getBoundingClientRect();
      mouse.x = event.clientX - rect.left;
      mouse.y = event.clientY - rect.top;
    }
    function onLeave() {
      mouse.x = -9999;
      mouse.y = -9999;
    }
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);

    function draw() {
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx!.clearRect(0, 0, canvas!.clientWidth, canvas!.clientHeight);
      for (const p of particles) {
        const dx = p.x - mouse.x, dy = p.y - mouse.y;
        const dist = Math.hypot(dx, dy) || 1;
        const repelRadius = 52;
        if (dist < repelRadius) {
          const force = ((repelRadius - dist) / repelRadius) * 2.6;
          p.vx += (dx / dist) * force;
          p.vy += (dy / dist) * force;
        }
        p.vx += (p.tx - p.x) * 0.02;
        p.vy += (p.ty - p.y) * 0.02;
        p.vx *= 0.82;
        p.vy *= 0.82;
        p.x += p.vx;
        p.y += p.vy;
        ctx!.fillStyle = `rgba(${p.rgb},${p.alpha})`;
        ctx!.fillRect(p.x, p.y, p.size, p.size);
      }
    }
    function tick() {
      draw();
      raf = requestAnimationFrame(tick);
    }
    if (reduceMotion) {
      draw();
    } else {
      tick();
    }

    const resize = new ResizeObserver(() => {
      layout(false);
      if (reduceMotion) draw();
    });
    resize.observe(probe);
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      resize.disconnect();
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, [lines]);
  return (
    <div className="particle-headline-wrap">
      <h1 ref={probeRef} className={`${className || ""} particle-headline-probe`}>
        {lines.map((line, index) => (
          <span key={index}>
            {index > 0 && <br />}
            {line.italic ? <em>{line.text}</em> : line.text}
          </span>
        ))}
      </h1>
      <canvas ref={canvasRef} className="particle-headline" aria-hidden="true" />
    </div>
  );
}

function AuthScreen({
  onAuthenticated,
  language,
}: {
  onAuthenticated: () => void;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const initialResetToken =
    new URLSearchParams(location.search).get("reset_token") || "";
  const [register, setRegister] = useState(false);
  const [recovery, setRecovery] = useState(Boolean(initialResetToken));
  const [resetToken, setResetToken] = useState(initialResetToken);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [capabilities, setCapabilities] = useState<DeploymentCapabilities | null>(null);
  useEffect(() => {
    api.capabilities().then(setCapabilities).catch(() => setCapabilities(null));
    const params = new URLSearchParams(location.search);
    const googleStatus = params.get("google_auth");
    const twitterStatus = params.get("twitter_auth");
    if (googleStatus && googleStatus !== "success") {
      setError(
        ru
          ? "Вход через Google не был завершён. Попробуйте ещё раз."
          : "Google sign-in was not completed. Please try again.",
      );
    }
    if (twitterStatus && twitterStatus !== "success") {
      setError(
        ru
          ? "Вход через X не был завершён. Проверьте scope users.email и попробуйте ещё раз."
          : "X sign-in was not completed. Check the users.email scope and try again.",
      );
    }
    if (googleStatus) {
      params.delete("google_auth");
    }
    if (twitterStatus) params.delete("twitter_auth");
    if (googleStatus || twitterStatus)
      history.replaceState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}`);
  }, [ru]);
  async function signInWithGoogle() {
    if (!capabilities?.auth.google || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.startGoogleAuth();
      location.assign(result.authorization_url);
    } catch (value) {
      setError((value as Error).message);
      setBusy(false);
    }
  }
  async function signInWithTwitter() {
    if (!capabilities?.auth.twitter || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.startTwitterAuth();
      location.assign(result.authorization_url);
    } catch (value) {
      setError((value as Error).message);
      setBusy(false);
    }
  }
  async function submit() {
    if (!email.trim() || password.length < 10 || busy) return;
    setBusy(true);
    setError("");
    try {
      if (register)
        await api.register({
          email: email.trim(),
          display_name: name.trim() || email.split("@")[0],
          password,
        });
      else await api.login({ email: email.trim(), password });
      localStorage.removeItem("orbit-auth-token");
      onAuthenticated();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function recover() {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (resetToken) {
        await api.confirmPasswordReset(resetToken, password);
        history.replaceState({}, "", location.pathname);
        setResetToken("");
        setRecovery(false);
        setPassword("");
        setNotice(
          ru
            ? "Пароль изменён. Теперь войдите."
            : "Password changed. You can now sign in.",
        );
      } else {
        const result = await api.requestPasswordReset(email.trim());
        if (result.debug_token) setResetToken(result.debug_token);
        setNotice(
          ru
            ? "Если аккаунт существует, инструкция отправлена на email."
            : result.message,
        );
      }
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="authscreen signal-authscreen">
      <div className="auth-signal-grid" aria-hidden="true" />
      <section className="auth-story" aria-label={ru ? "О проекте Orbit" : "About Orbit"}>
        <div className="auth-story-brand"><span className="signal-brand-mark"><i /><i /><i /></span><b>ORBIT</b><small>CHAIN INTELLIGENCE</small></div>
        <p>{ru ? "ROBINHOOD CHAIN · SIGNAL ROOM" : "ROBINHOOD CHAIN · SIGNAL ROOM"}</p>
        <ParticleHeadline lines={ru ? AUTH_HEADLINE_RU : AUTH_HEADLINE_EN} />
        <span>{ru ? "Команда AI-персонажей для сигналов, риска и мем-нарратива." : "A crew of AI characters for signals, risk and meme narrative."}</span>
        <Mascot state={register ? "thinking" : "idle"} size={320} />
        <div className="auth-story-pulse"><i /> {ru ? "СИГНАЛЬНЫЙ КАНАЛ ГОТОВ" : "SIGNAL CHANNEL READY"}</div>
      </section>
      <section className="authcard">
        <div className="authbrand">
          <OrbitMark />
          <b>Orbit</b>
        </div>
        <p className="eyebrow">AGENT ORCHESTRATION WORKSPACE</p>
        <h1>
          {recovery
            ? resetToken
              ? ru
                ? "Новый пароль"
                : "Choose a new password"
              : ru
                ? "Восстановление доступа"
                : "Recover access"
            : register
              ? ru
                ? "Создайте пространство"
                : "Create your workspace"
              : ru
                ? "С возвращением"
                : "Welcome back"}
        </h1>
        <p>
          {recovery
            ? ru
              ? "Одноразовая ссылка действует 30 минут и завершит все старые сессии."
              : "The one-time link lasts 30 minutes and signs out old sessions."
            : ru
              ? "Агенты, память, исследования и инструменты в одном управляемом рабочем процессе."
              : "Agents, memory, research, and tools in one controlled workflow."}
        </p>
        {!recovery && register && (
          <LabelInput label={ru ? "Имя" : "Name"} value={name} set={setName} />
        )}
        <LabelInput
          label={
            resetToken
              ? ru
                ? "Новый пароль · минимум 10 символов"
                : "New password · at least 10 characters"
              : "Email"
          }
          value={resetToken ? password : email}
          set={resetToken ? setPassword : setEmail}
          secret={Boolean(resetToken)}
        />
        {!recovery && (
          <LabelInput
            label={
              ru
                ? "Пароль · минимум 10 символов"
                : "Password · at least 10 characters"
            }
            value={password}
            set={setPassword}
            secret
          />
        )}
        {notice && (
          <div className="authnotice">
            <Check />
            {notice}
          </div>
        )}
        {error && <div className="autherror">{error}</div>}
        <button
          className="primary authsubmit"
          disabled={
            busy ||
            (recovery
              ? resetToken
                ? password.length < 10
                : !email.trim()
              : !email.trim() || password.length < 10)
          }
          onClick={recovery ? recover : submit}
        >
          {busy ? (
            <Activity />
          ) : recovery ? (
            ru ? (
              "Продолжить"
            ) : (
              "Continue"
            )
          ) : register ? (
            ru ? (
              "Создать аккаунт"
            ) : (
              "Create account"
            )
          ) : ru ? (
            "Войти"
          ) : (
            "Sign in"
          )}
        </button>
        {!recovery && (
          <>
            <div className="authdivider"><span>{ru ? "или" : "or"}</span></div>
            <button
              className="googleauth"
              disabled={busy || !capabilities?.auth.google}
              onClick={signInWithGoogle}
              title={!capabilities?.auth.google ? (ru ? "Будет доступно после настройки Google OAuth" : "Available after Google OAuth is configured") : ""}
            >
              <span className="googlemark">G</span>
              {capabilities?.auth.google
                ? ru ? "Продолжить с Google" : "Continue with Google"
                : ru ? "Google · скоро" : "Google · coming soon"}
            </button>
            <button
              className="googleauth twitterauth"
              disabled={busy || !capabilities?.auth.twitter}
              onClick={signInWithTwitter}
              title={!capabilities?.auth.twitter ? (ru ? "X OAuth не настроен на сервере" : "X OAuth is not configured on this server") : ""}
            >
              <TwitterMark />
              {capabilities?.auth.twitter
                ? ru ? "Продолжить с X" : "Continue with X"
                : ru ? "X · скоро" : "X · coming soon"}
            </button>
          </>
        )}
        {!recovery && !register && (
          <button
            className="authswitch"
            onClick={() => {
              setRecovery(true);
              setError("");
            }}
          >
            {ru ? "Забыли пароль?" : "Forgot password?"}
          </button>
        )}
        <button
          className="authswitch"
          onClick={() => {
            setRecovery(false);
            setResetToken("");
            setRegister((value) => (recovery ? false : !value));
            setError("");
          }}
        >
          {recovery
            ? ru
              ? "Вернуться ко входу"
              : "Back to sign in"
            : register
              ? ru
                ? "Уже есть аккаунт? Войти"
                : "Already have an account? Sign in"
              : ru
                ? "Нет аккаунта? Создать"
                : "No account? Create one"}
        </button>
        <div className="authlegal">
          <a href="/terms.html" target="_blank" rel="noreferrer">{ru ? "Условия" : "Terms"}</a>
          <span>·</span>
          <a href="/privacy.html" target="_blank" rel="noreferrer">{ru ? "Конфиденциальность" : "Privacy"}</a>
        </div>
      </section>
    </main>
  );
}

function Nav({
  open,
  screen,
  go,
  goHome,
  toggle,
  history,
  openRun,
  renameRun,
  deleteRun,
  mergeMemory,
  language,
  user,
}: {
  open: boolean;
  screen: Screen;
  go: (s: Screen) => void;
  goHome: (target: "top" | "composer") => void;
  toggle: () => void;
  history: Run[];
  openRun: (r: Run) => void;
  renameRun: (r: Run, title: string) => Promise<void>;
  deleteRun: (r: Run) => Promise<void>;
  mergeMemory: (source: Run, target: Run) => Promise<void>;
  language: "ru" | "en";
  user: OrbitUser;
}) {
  const [expanded, setExpanded] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    run: Run;
    x: number;
    y: number;
  } | null>(null);
  const [mergeSource, setMergeSource] = useState<Run | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Run | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Run | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [seenAt, setSeenAt] = useState(() =>
    Number(localStorage.getItem("orbit-notifications-seen") || 0),
  );
  const notifications = history
    .filter((run) =>
      ["completed", "failed", "waiting_for_human"].includes(run.status),
    )
    .slice(0, 12);
  const unread = notifications.filter(
    (run) => new Date(run.finished_at || run.created_at).getTime() > seenAt,
  ).length;
  function openNotifications() {
    setNotificationsOpen((value) => !value);
    const now = Date.now();
    setSeenAt(now);
    localStorage.setItem("orbit-notifications-seen", String(now));
  }
  const items: [Screen, string, React.ReactNode][] = [
    ["home", language === "ru" ? "Новый чат" : "New chat", <Plus />],
    [
      "workflows",
      language === "ru" ? "Диалоги" : "Workflows",
      <MessageSquare />,
    ],
    [
      "research",
      language === "ru" ? "Исследования" : "Deep Research",
      <Globe2 />,
    ],
    ["tokens", language === "ru" ? "Токены" : "Tokens", <Radar />],
    ["skills", language === "ru" ? "Скиллы" : "Skills", <Sparkles />],
    ["memory", language === "ru" ? "Память" : "Memory", <Brain />],
    ["team", language === "ru" ? "Агенты" : "Agents", <Bot />],
    [
      "connections",
      language === "ru" ? "Подключения" : "Connections",
      <Plug />,
    ],
    ["settings", language === "ru" ? "Настройки" : "Settings", <Settings />],
    ...(user.is_superuser ? [["admin", language === "ru" ? "Админ" : "Admin", <BarChart3 />] as [Screen, string, React.ReactNode]] : []),
    ["profile", language === "ru" ? "Профиль" : "Profile", <AtSign />],
  ];
  function renameDialogue(value: Run) {
    setRenameTarget(value);
    setRenameValue(value.goal);
    setContextMenu(null);
  }
  async function applyRename() {
    if (!renameTarget || !renameValue.trim() || renaming) return;
    setRenaming(true);
    try {
      await renameRun(renameTarget, renameValue.trim());
      setRenameTarget(null);
    } finally {
      setRenaming(false);
    }
  }
  async function removeDialogue() {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    try {
      await deleteRun(deleteTarget);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }
  return (
    <>
      <aside
        className={`nav ${open ? "open" : ""}`}
        onClick={() => setContextMenu(null)}
      >
        <div className="logo">
          <button
            className="logohome"
            onClick={() => goHome("top")}
            aria-label={language === "ru" ? "В начало Orbit" : "Go to Orbit home"}
            title={language === "ru" ? "В начало" : "Back to top"}
          >
            <OrbitMark />
            {open && <b>Orbit</b>}
          </button>
          {open && (
            <button
              className="notificationbutton"
              aria-label={language === "ru" ? "Уведомления" : "Notifications"}
              onClick={openNotifications}
            >
              <Bell />
              {unread > 0 && <i>{unread}</i>}
            </button>
          )}
        </div>
        {notificationsOpen && (
          <div className="notificationpanel">
            <header>
              <b>{language === "ru" ? "Уведомления" : "Notifications"}</b>
              <span>
                {unread
                  ? language === "ru"
                    ? "Новые события"
                    : "New events"
                  : language === "ru"
                    ? "Всё просмотрено"
                    : "All caught up"}
              </span>
            </header>
            {notifications.length === 0 ? (
              <p>{language === "ru" ? "Событий пока нет" : "No events yet"}</p>
            ) : (
              notifications.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    openRun(item);
                    setNotificationsOpen(false);
                  }}
                >
                  <i className={item.status} />
                  <div>
                    <b>
                      {item.status === "completed"
                        ? language === "ru"
                          ? "Работа завершена"
                          : "Work completed"
                        : item.status === "failed"
                          ? language === "ru"
                            ? "Ошибка выполнения"
                            : "Run failed"
                          : language === "ru"
                            ? "Нужен ваш ответ"
                            : "Your input is needed"}
                    </b>
                    <small>{item.goal}</small>
                  </div>
                </button>
              ))
            )}
          </div>
        )}
        <div className="navitems">
          {items.map(([key, label, icon]) => (
            <div
              key={key}
              className={key === "profile" ? "nav-profile-item" : ""}
            >
              <button
                className={screen === key ? "active" : ""}
                onClick={() => {
                  if (key === "home") goHome("composer");
                  else go(key);
                  if (key === "workflows") setExpanded((v) => !v);
                }}
              >
                {icon}
                {open && <span>{label}</span>}
                {open && key === "workflows" && (
                  <ChevronDown className={expanded ? "rotated" : ""} />
                )}
              </button>
              {open && key === "workflows" && expanded && (
                <div className="historylist">
                  {history.slice(0, 10).map((r) => (
                    <button
                      key={r.id}
                      onClick={() => openRun(r)}
                      onContextMenu={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        setContextMenu({
                          run: r,
                          x: event.clientX,
                          y: event.clientY,
                        });
                      }}
                    >
                      {r.goal}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        <button className="collapse" onClick={toggle}>
          {open ? <ChevronLeft /> : <ChevronRight />}
          {open && <span>{language === "ru" ? "Свернуть" : "Collapse"}</span>}
        </button>
        <div
          className={`user ${screen === "profile" ? "active" : ""}`}
          role="button"
          tabIndex={0}
          onClick={() => go("profile")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") go("profile");
          }}
        >
          <span>{initials(user.display_name)}</span>
          {open && (
            <div>
              <b>{user.display_name}</b>
              <small>
                {language === "ru" ? "Профиль · владелец" : "Profile · owner"}
              </small>
            </div>
          )}
        </div>
        {open && (
          <a
            className="devcredit"
            href="https://x.com/Atenov_D"
            target="_blank"
            rel="noopener noreferrer"
          >
            {language === "ru" ? "Разработчик" : "Developer"} · Atenov_D
          </a>
        )}
        {renameTarget && (
          <div
            className="modalback"
            onClick={() => !renaming && setRenameTarget(null)}
          >
            <div
              className="modal renamedialoguemodal"
              role="dialog"
              aria-modal="true"
              onClick={(event) => event.stopPropagation()}
            >
              <header>
                <div>
                  <p className="eyebrow">DIALOGUE</p>
                  <h2>
                    {language === "ru"
                      ? "Переименовать диалог"
                      : "Rename dialogue"}
                  </h2>
                </div>
                <button onClick={() => setRenameTarget(null)}>
                  <X />
                </button>
              </header>
              <label className="inputlabel">
                <span>{language === "ru" ? "Название" : "Name"}</span>
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") applyRename();
                  }}
                />
              </label>
              <footer>
                <button
                  disabled={renaming}
                  onClick={() => setRenameTarget(null)}
                >
                  {language === "ru" ? "Отмена" : "Cancel"}
                </button>
                <button
                  className="primary"
                  disabled={renaming || !renameValue.trim()}
                  onClick={applyRename}
                >
                  {renaming
                    ? language === "ru"
                      ? "Сохраняем…"
                      : "Saving…"
                    : language === "ru"
                      ? "Сохранить"
                      : "Save"}
                </button>
              </footer>
            </div>
          </div>
        )}
      </aside>
      {contextMenu && (
        <div
          className="dialoguecontext"
          style={{
            left: Math.min(contextMenu.x, window.innerWidth - 230),
            top: Math.min(contextMenu.y, window.innerHeight - 150),
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <button onClick={() => renameDialogue(contextMenu.run)}>
            <Pencil />
            {language === "ru" ? "Переименовать" : "Rename"}
          </button>
          <button
            onClick={() => {
              setMergeSource(contextMenu.run);
              setContextMenu(null);
            }}
          >
            <ArrowRightLeft />
            {language === "ru" ? "Передать память в…" : "Send memory to…"}
          </button>
          <button
            className="danger"
            onClick={() => {
              setDeleteTarget(contextMenu.run);
              setContextMenu(null);
            }}
          >
            <Trash2 />
            {language === "ru" ? "Удалить диалог" : "Delete dialogue"}
          </button>
        </div>
      )}
      {mergeSource && (
        <div className="modalback" onClick={() => setMergeSource(null)}>
          <div
            className="modal mergememorymodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">DIALOGUE MEMORY</p>
                <h2>
                  {language === "ru"
                    ? "Передать память в другой диалог"
                    : "Send memory to another dialogue"}
                </h2>
              </div>
              <button onClick={() => setMergeSource(null)}>
                <X />
              </button>
            </header>
            <p className="modalhint">
              {language === "ru"
                ? "Целевой диалог получит компактную память выбранной переписки. Сообщения останутся раздельными."
                : "The target dialogue receives a compact memory summary. Messages remain separate."}
            </p>
            <div className="mergetargets">
              {history
                .filter((item) => item.id !== mergeSource.id)
                .map((target) => (
                  <button
                    key={target.id}
                    onClick={async () => {
                      await mergeMemory(mergeSource, target);
                      setMergeSource(null);
                    }}
                  >
                    <MessageSquare />
                    <span>{target.goal}</span>
                    <ChevronRight />
                  </button>
                ))}
            </div>
          </div>
        </div>
      )}
      {deleteTarget && (
        <div
          className="modalback deletemodalback"
          onClick={() => !deleting && setDeleteTarget(null)}
        >
          <div
            className="modal deletedialoguemodal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-dialogue-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="deleteicon">
              <Trash2 />
            </div>
            <div className="deletecopy">
              <p className="eyebrow">
                {language === "ru" ? "УДАЛЕНИЕ ДИАЛОГА" : "DELETE DIALOGUE"}
              </p>
              <h2 id="delete-dialogue-title">
                {language === "ru"
                  ? "Удалить этот диалог?"
                  : "Delete this dialogue?"}
              </h2>
              <p>
                {language === "ru"
                  ? "Переписка и связанная с ней память будут удалены без возможности восстановления."
                  : "The conversation and its linked memory will be permanently deleted."}
              </p>
              <strong>«{deleteTarget.goal}»</strong>
            </div>
            <button
              className="deleteclose"
              aria-label={language === "ru" ? "Закрыть" : "Close"}
              disabled={deleting}
              onClick={() => setDeleteTarget(null)}
            >
              <X />
            </button>
            <footer>
              <button disabled={deleting} onClick={() => setDeleteTarget(null)}>
                {language === "ru" ? "Отмена" : "Cancel"}
              </button>
              <button
                className="confirmdelete"
                disabled={deleting}
                onClick={removeDialogue}
              >
                {deleting
                  ? language === "ru"
                    ? "Удаляем…"
                    : "Deleting…"
                  : language === "ru"
                    ? "Удалить диалог"
                    : "Delete dialogue"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </>
  );
}

function NewChat({
  agents,
  history,
  workspace,
  onStart,
  language,
  initialDraft,
  onDraftConsumed,
  navigation,
  goProfile,
  walletAddress,
}: {
  agents: Agent[];
  history: Run[];
  workspace: Workspace | null;
  onStart: (
    goal?: string,
    materials?: DraftMaterial[],
    agentIds?: string[],
  ) => void;
  language: "ru" | "en";
  initialDraft: { goal: string; agentIds: string[] } | null;
  onDraftConsumed: () => void;
  navigation: { target: "top" | "composer"; nonce: number };
  goProfile: () => void;
  walletAddress: string | null;
}) {
  const [value, setValue] = useState("");
  const [materials, setMaterials] = useState<DraftMaterial[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());
  const [briefOpen, setBriefOpen] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [analytics, setAnalytics] = useState<{
    reports: ResearchReport[];
    tokens: Token[];
    verdicts: TokenVerdict[];
  }>({ reports: [], tokens: [], verdicts: [] });
  const workspaceId = workspace?.id;
  const selectedTeamSeeded = useRef(false);
  const homeTopRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const ru = language === "ru";
  const coreAgents = agents.slice(0, 5);
  const selectedCoreAgents = coreAgents.filter((agent) => selectedAgents.has(agent.id));
  const connectedSelectedAgents = agents.filter(
    (agent) => selectedAgents.has(agent.id) && Boolean(agent.connection_id) && agent.model !== "mock-model",
  );
  const recentRuns = history.slice(0, 2);
  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    void Promise.all([api.researchReports(workspaceId), api.tokens(workspaceId)])
      .then(async ([reports, tokens]) => {
        const verdicts = (await Promise.all(tokens.map((token) => api.tokenVerdicts(token.id)))).flat();
        if (!cancelled) setAnalytics({ reports, tokens, verdicts });
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [workspaceId]);
  const analyticsDays = useMemo(() => {
    const formatter = new Intl.DateTimeFormat(ru ? "ru-RU" : "en-US", { month: "short", day: "numeric" });
    return Array.from({ length: 7 }, (_, offset) => {
      const value = new Date();
      value.setHours(0, 0, 0, 0);
      value.setDate(value.getDate() - (6 - offset));
      const date = value.toISOString().slice(0, 10);
      const runs = history.filter((run) => run.created_at.slice(0, 10) === date).length;
      const evidence = analytics.reports
        .filter((report) => report.created_at.slice(0, 10) === date)
        .reduce((total, report) => total + report.findings.length, 0);
      return { date, label: formatter.format(value), runs, evidence };
    });
  }, [analytics.reports, history, ru]);
  const completedRuns = history.filter((run) => run.status === "completed").length;
  const completionRate = history.length ? Math.round((completedRuns / history.length) * 100) : 0;
  const evidenceTotal = analytics.reports.reduce((total, report) => total + report.findings.length, 0);
  const trendMax = Math.max(1, ...analyticsDays.map((item) => Math.max(item.runs, item.evidence)));
  const trendLine = analyticsDays
    .map((item, index) => `${index ? "L" : "M"}${10 + index * 40} ${88 - (item.evidence / trendMax) * 68}`)
    .join(" ");
  const trendArea = `${trendLine} L250 96 L10 96 Z`;
  const sourceMix = analytics.reports.flatMap((report) => report.findings).reduce<Record<string, number>>((total, finding) => {
    total[finding.source] = (total[finding.source] || 0) + 1;
    return total;
  }, {});
  useEffect(() => {
    if (selectedTeamSeeded.current || !agents.length) return;
    selectedTeamSeeded.current = true;
    setSelectedAgents(new Set(agents.slice(0, 5).map((agent) => agent.id)));
  }, [agents]);
  useEffect(() => {
    if (!initialDraft) return;
    setValue(initialDraft.goal);
    setSelectedAgents(new Set(initialDraft.agentIds));
    onDraftConsumed();
  }, [initialDraft, onDraftConsumed]);
  const scrollHome = (target: "top" | "composer", behavior: ScrollBehavior = "smooth") => {
    const element = target === "composer" ? composerRef.current : homeTopRef.current;
    if (!element) return;
    const scrollContainer = element.closest<HTMLElement>(".main");
    if (!scrollContainer) {
      element.scrollIntoView({ behavior, block: target === "composer" ? "center" : "start" });
      return;
    }
    if (target === "top") {
      scrollContainer.scrollTo({ top: 0, behavior });
      return;
    }
    // Keep the whole composer in view. `scrollIntoView({ block: "start" })`
    // can put its top behind the viewport when the page has nested scrolling.
    const composerTop = scrollContainer.scrollTop
      + element.getBoundingClientRect().top
      - scrollContainer.getBoundingClientRect().top;
    const safeTop = Math.max(
      24,
      composerTop - Math.max(24, (scrollContainer.clientHeight - element.clientHeight) / 2),
    );
    scrollContainer.scrollTo({ top: safeTop, behavior });
  };
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      scrollHome(navigation.target, navigation.nonce ? "smooth" : "auto");
    });
    return () => cancelAnimationFrame(frame);
  }, [navigation]);
  function submit() {
    if (value.trim() && selectedAgents.size)
      onStart(value.trim(), materials, [...selectedAgents]);
  }
  function toggleAgent(id: string) {
    setSelectedAgents((old) => {
      const next = new Set(old);
      if (next.has(id)) next.delete(id);
      else if (next.size < MAX_TEAM_SIZE) next.add(id);
      return next;
    });
  }
  async function addFiles(files: FileList | File[] | null) {
    if (!files) return;
    const accepted = [...files]
      .filter((file) =>
        /\.(txt|md|csv|json|js|ts|tsx|py|html|css|pdf|docx)$/i.test(file.name),
      )
      .slice(0, Math.max(0, 12 - materials.length));
    const loaded = await Promise.all(
      accepted.map(async (file) => ({
        name: file.name,
        content: file.name.match(/\.(pdf|docx)$/i)
          ? ""
          : (await file.text()).slice(0, 250000),
        kind: file.name.endsWith(".md")
          ? "markdown"
          : file.name.match(/\.(js|ts|tsx|py|json|css|html)$/i)
            ? "code"
            : "file",
        file,
      })),
    );
    setMaterials((old) => [...old, ...loaded].slice(0, 12));
  }
  function dropFiles(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    void addFiles(event.dataTransfer.files);
  }
  return (
    <div className="newchat signal-deck" ref={homeTopRef}>
      <div className="signal-deck-noise" aria-hidden="true" />
      <div className="signal-deck-grid" aria-hidden="true" />
      <div className="signal-deck-shell">
        <header className="signal-deck-bar">
          <div className="signal-brand-lockup">
            <span className="signal-brand-mark"><i /><i /><i /></span>
            <span><b>ORBIT</b><small>CHAIN INTELLIGENCE</small></span>
          </div>
          <div className="signal-network"><i /> ROBINHOOD CHAIN <span>4663</span></div>
          <div className="signal-deck-status"><span>{selectedAgents.size}/10</span> {ru ? "агентов на связи" : "agents online"}</div>
        </header>
        <section className="signal-deck-hero">
          <div className="signal-deck-copy">
            <p className="signal-kicker"><i /> {ru ? "СИГНАЛЬНАЯ КОМНАТА" : "SIGNAL ROOM"}</p>
            <ParticleHeadline lines={ru ? HOME_HEADLINE_RU : HOME_HEADLINE_EN} />
            <p className="signal-lede">
              {ru
                ? "Вставьте адрес контракта. Пять агентов проверят холдеров, ликвидность и права владельца в Robinhood Chain и вернут ENTER, WATCH или SKIP со ссылками на доказательства."
                : "Paste a contract address. Five agents check holders, liquidity and owner permissions on Robinhood Chain and return ENTER, WATCH or SKIP with the evidence attached."}
            </p>
            <div className="signal-proof">
              <span><Radar /> {ru ? "Данные прямо из сети" : "Live chain data"}</span>
              <span><ShieldCheck /> {ru ? "Только бумажная торговля" : "Paper trading only"}</span>
            </div>
          </div>
          <div className="signal-scout-stage">
            <div className="signal-scout-caption"><i /> {value.trim() ? (ru ? "СКАНИРУЕТ БРИФ" : "SCANNING BRIEF") : (ru ? "НАБЛЮДАЕТ ЗА ЦЕПЬЮ" : "WATCHING THE CHAIN")}</div>
            <Mascot state={value.trim() ? "thinking" : selectedAgents.size ? "done" : "idle"} size={348} />
            <div className="signal-scout-callout signal-scout-callout-left"><small>01</small><b>{ru ? "Читает сеть" : "Reads the chain"}</b><span>{ru ? "холдеры и пулы" : "holders and pools"}</span></div>
            <div className="signal-scout-callout signal-scout-callout-right"><small>02</small><b>{ru ? "Показывает источники" : "Shows its sources"}</b><span>{ru ? "у каждого вывода есть ссылка" : "every claim links to evidence"}</span></div>
          </div>
          <aside className="signal-launch-rail">
            <div className="signal-promo-slot">
              <span>{ru ? "СТАРТОВЫЙ ОФФЕР" : "LAUNCH OFFER"}</span>
              <b>{ru ? "7 дней расширенного доступа к анализу" : "7 days of extended analysis access"}</b>
              <p>{ru ? "Место для проверенного промо: тестовых кредитов, бесплатной модели или доступа к on-chain анализу." : "A reserved space for a verified promotion: trial credits, a free model, or on-chain analysis access."}</p>
              <button onClick={() => scrollHome("composer")}>
                {ru ? "Создать первый чат" : "Create your first chat"} <ChevronDown />
              </button>
            </div>
            <a className="signal-rail-action signal-github-action" href="https://github.com/AtenovD/orbit-chain-intelligence" target="_blank" rel="noreferrer">
              <Github />
              <span><b>GitHub</b><small>{ru ? "Open-source версия Orbit" : "Open-source edition of Orbit"}</small></span>
              <ChevronRight />
            </a>
            <button className="signal-rail-action" onClick={goProfile}><Megaphone /> {ru ? "Амбассадорская кампания" : "Ambassador campaign"}<ChevronRight /></button>
            <button className="signal-rail-action signal-wallet-action" onClick={walletAddress ? goProfile : openWalletDialog}>
              <Wallet />
              <span>
                <b>{walletAddress ? shortAddress(walletAddress) : ru ? "Подключить кошелёк" : "Connect wallet"}</b>
                <small>{walletAddress ? (ru ? "Повышенный лимит включён" : "Higher usage limit active") : ru ? "Получите повышенный лимит использования" : "Get a higher usage limit"}</small>
              </span>
              <ChevronRight />
            </button>
          </aside>
          <aside className="signal-market-card">
            <header><span>{ru ? "АНАЛИТИКА РАБОЧЕЙ КОМНАТЫ" : "ROOM ANALYTICS"}</span><i>{history.length ? "LIVE DATA" : "EMPTY"}</i></header>
            <div className="signal-price"><b>{history.length ? `${completionRate}%` : "—"}</b><span>{ru ? "доля завершённых запусков" : "completed run rate"}</span></div>
            <svg viewBox="0 0 260 104" aria-label={ru ? "График доказательств за семь дней" : "Seven-day evidence chart"} role="img">
              <defs><linearGradient id="signal-chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#baff48" stopOpacity=".42" /><stop offset="1" stopColor="#baff48" stopOpacity="0" /></linearGradient></defs>
              <path d="M0 88H260M0 54H260M0 20H260" stroke="#d9ff98" strokeOpacity=".12" strokeWidth="1" />
              <path d={trendArea} fill="url(#signal-chart-fill)" />
              <path d={trendLine} fill="none" stroke="#d4ff72" strokeWidth="3" strokeLinecap="round" />
              {analyticsDays.map((item, index) => <circle key={item.date} cx={10 + index * 40} cy={88 - (item.evidence / trendMax) * 68} r="2.5" fill="#ecffc1" />)}
            </svg>
            <div className="signal-recent-runs">
              <span>{ru ? "ПОСЛЕДНИЕ ЗАПУСКИ" : "RECENT RUNS"}</span>
              {recentRuns.length ? recentRuns.map((item) => <p key={item.id}><i className={item.status} />{item.goal}</p>) : <p><i className="ready" />{ru ? "Комната готова к первому сигналу" : "Room ready for its first signal"}</p>}
            </div>
            <footer><span>{ru ? "Собрано доказательств" : "Evidence collected"}</span><b>{evidenceTotal}</b></footer>
          </aside>
        </section>
        <section className="signal-analytics" aria-label={ru ? "Аналитика исследования" : "Research analytics"}>
          <header><div><p>{ru ? "ИЗМЕРИМЫЙ ПРОГРЕСС" : "MEASURABLE PROGRESS"}</p><h2>{ru ? "Аналитика исследовательской комнаты" : "Research room analytics"}</h2><span>{ru ? "Показывает только данные этого рабочего пространства за последние семь дней." : "Shows only this workspace’s data from the last seven days."}</span></div><span className="signal-analytics-live"><i /> {ru ? "ОБНОВЛЯЕТСЯ ИЗ ORBIT" : "FROM ORBIT DATA"}</span></header>
          <div className="signal-analytics-kpis">
            <article><small>{ru ? "ЗАПУСКИ · 7 ДНЕЙ" : "RUNS · 7 DAYS"}</small><b>{analyticsDays.reduce((total, item) => total + item.runs, 0)}</b><span>{ru ? `${completedRuns} завершено всего` : `${completedRuns} completed overall`}</span></article>
            <article><small>{ru ? "ДОКАЗАТЕЛЬСТВА" : "EVIDENCE"}</small><b>{evidenceTotal}</b><span>{ru ? `${analytics.reports.length} research-отчётов` : `${analytics.reports.length} research reports`}</span></article>
            <article><small>{ru ? "АКТИВЫ ПОД НАБЛЮДЕНИЕМ" : "TRACKED ASSETS"}</small><b>{analytics.tokens.length}</b><span>{ru ? `${analytics.tokens.filter((item) => item.watchlist).length} в watchlist` : `${analytics.tokens.filter((item) => item.watchlist).length} on watchlist`}</span></article>
            <article><small>{ru ? "РЕШЕНИЯ" : "DECISIONS"}</small><b>{analytics.verdicts.length}</b><span>{ru ? "структурированных вердиктов" : "structured verdicts"}</span></article>
          </div>
          <div className="signal-analytics-body">
            <article className="signal-performance"><header><b>{ru ? "Прогресс" : "Progress"}</b><span><i /> {ru ? "запуски" : "runs"}<em /> {ru ? "доказательства" : "evidence"}</span></header><svg viewBox="0 0 620 220" role="img" aria-label={ru ? "Запуски и доказательства за семь дней" : "Seven-day runs and evidence"}><defs><linearGradient id="signal-bars" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#8faeff" /><stop offset="1" stopColor="#4c6da8" /></linearGradient></defs><path d="M28 178H600M28 118H600M28 58H600" stroke="currentColor" opacity=".12" />{analyticsDays.map((item, index) => { const x = 48 + index * 86; const barHeight = (item.runs / trendMax) * 130; const y = 178 - barHeight; return <g key={item.date}><rect x={x} y={y} width="35" height={barHeight || 2} rx="4" /><text x={x + 17} y="204" textAnchor="middle">{item.label}</text></g>; })}<path d={analyticsDays.map((item, index) => `${index ? "L" : "M"}${65 + index * 86} ${178 - (item.evidence / trendMax) * 130}`).join(" ")} fill="none" stroke="#c9ff68" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />{analyticsDays.map((item, index) => <circle key={item.date} cx={65 + index * 86} cy={178 - (item.evidence / trendMax) * 130} r="4" />)}</svg></article>
            <article className="signal-attribution"><header><b>{ru ? "Атрибуция источников" : "Source attribution"}</b><span>{evidenceTotal ? `${evidenceTotal} ${ru ? "материалов" : "findings"}` : (ru ? "Нет данных" : "No data")}</span></header>{Object.entries(sourceMix).length ? Object.entries(sourceMix).sort(([, left], [, right]) => right - left).map(([source, count]) => <div key={source}><span>{source}</span><i><b style={{ width: `${(count / evidenceTotal) * 100}%` }} /></i><em>{count} · {Math.round((count / evidenceTotal) * 100)}%</em></div>) : <p>{ru ? "Запустите первое исследование — здесь появится состав использованных источников." : "Start a first research run to see the source mix here."}</p>}</article>
          </div>
        </section>
        <section className="signal-crew-section">
          <header>
            <div><p>{ru ? "БАЗОВАЯ КОМАНДА" : "CORE CREW"}</p><h2>{ru ? "Пять агентов, пять задач." : "Five agents, five jobs."}</h2></div>
            <button onClick={() => setPickerOpen(true)}>{ru ? "Настроить до 10" : "Configure up to 10"}<ChevronRight /></button>
          </header>
          <div className="signal-crew-filmstrip">
            {coreAgents.map((agent, index) => {
              const persona = crewPersona(index);
              const active = selectedAgents.has(agent.id);
              return (
                <button
                  key={agent.id}
                  className={`signal-crew-card ${persona.tone} ${active ? "selected" : ""}`}
                  onClick={() => toggleAgent(agent.id)}
                  aria-pressed={active}
                  title={active ? (ru ? "Убрать из следующего чата" : "Remove from the next chat") : (ru ? "Добавить в следующий чат" : "Add to the next chat")}
                >
                  <span className="signal-crew-index">0{index + 1}</span>
                  <AgentGlyph name={agent.name} skillName={agent.skill_name} color={colors[index % colors.length]} className="signal-crew-glyph" />
                  <span className="signal-crew-copy"><small>{persona.codename}</small><b>{agent.name}</b><em>{ru ? persona.traitRu : persona.traitEn}</em></span>
                  <span className="signal-crew-ready">{active ? <Check /> : <Plus />}</span>
                </button>
              );
            })}
          </div>
          <div className="signal-crew-foot"><span><Users /> {ru ? `${selectedCoreAgents.length} из 5 базовых выбраны. Состав можно менять и после старта.` : `${selectedCoreAgents.length} of 5 core agents selected. The roster stays editable after launch.`}</span>{selectedAgents.size > 0 && <em className={connectedSelectedAgents.length === selectedAgents.size ? "ready" : ""}>{connectedSelectedAgents.length === selectedAgents.size ? (ru ? "Все выбранные агенты подключены к моделям" : "Every selected agent has a live model") : (ru ? `${connectedSelectedAgents.length}/${selectedAgents.size} выбрано с подключённой моделью` : `${connectedSelectedAgents.length}/${selectedAgents.size} selected with a live model`)}</em>}{agents.length > 5 && <button onClick={() => setPickerOpen(true)}>+{agents.length - 5} {ru ? "специалистов" : "specialists"}</button>}</div>
        </section>
        <div
          ref={composerRef}
          className={`startcomposer ${dragActive ? "drag-active" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node))
              setDragActive(false);
          }}
          onDrop={dropFiles}
        >
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={
              ru
                ? "Напишите задачу для команды агентов…"
                : "Describe a task for your agent team…"
            }
            onPaste={(event) => {
              if (event.clipboardData.files.length)
                void addFiles(event.clipboardData.files);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          {dragActive && (
            <div className="materialdrop">
              <span>
                <FileText />
              </span>
              <b>
                {ru
                  ? "Отпустите файлы — команда прочитает их до старта"
                  : "Drop files — the team will read them before starting"}
              </b>
              <small>
                {ru
                  ? "До 12 материалов в одном диалоге"
                  : "Up to 12 materials per dialogue"}
              </small>
            </div>
          )}
          {materials.length > 0 && (
            <div className="materialchips">
              {materials.map((item, index) => (
                <span key={`${item.name}-${index}`}>
                  <FileText />
                  {item.name}
                  <button
                    aria-label={
                      ru ? `Удалить ${item.name}` : `Remove ${item.name}`
                    }
                    onClick={() =>
                      setMaterials((old) => old.filter((_, i) => i !== index))
                    }
                  >
                    <X />
                  </button>
                </span>
              ))}
            </div>
          )}
          {pickerOpen && createPortal(
            <div className="pickerback" onClick={() => setPickerOpen(false)}>
            <div
              className="agentpicker"
              onClick={(event) => event.stopPropagation()}
            >
              <header>
                <div>
                  <b>{ru ? "Команда диалога" : "Chat team"}</b>
                  <small>
                    {ru
                      ? "Выберите агентов, которые получат задачу"
                      : "Choose the agents who will receive this task"}
                  </small>
                </div>
                <button onClick={() => setPickerOpen(false)}>
                  <X />
                </button>
              </header>
              <div className="agentpickergrid">
                {agents.map((agent, index) => {
                  const active = selectedAgents.has(agent.id);
                  return (
                    <button
                      key={agent.id}
                      className={active ? "active" : ""}
                      onClick={() => toggleAgent(agent.id)}
                    >
                      <AgentGlyph
                        name={agent.name}
                        skillName={agent.skill_name}
                        color={colors[index % colors.length]}
                      />
                      <div>
                        <b>{agent.name}</b>
                        <small>{agent.role}</small>
                      </div>
                      <i>{active && <Check />}</i>
                    </button>
                  );
                })}
              </div>
              <footer>
                <button onClick={() => setSelectedAgents(new Set())}>
                  {ru ? "Очистить" : "Clear"}
                </button>
                <button
                  onClick={() =>
                    setSelectedAgents(
                      new Set(agents.slice(0, MAX_TEAM_SIZE).map((agent) => agent.id)),
                    )
                  }
                >
                  {ru ? "Выбрать всех" : "Select all"}
                </button>
              </footer>
            </div>
            </div>,
            document.body,
          )}
          <div className="composerbottom">
            <label
              className={`attachbutton ${materials.length ? "has-files" : ""}`}
              title={
                ru
                  ? "TXT, MD, PDF, DOCX, CSV, JSON и код · можно перетащить"
                  : "TXT, MD, PDF, DOCX, CSV, JSON and code · drag and drop supported"
              }
            >
              <span className="attachicon">
                <Paperclip />
                <Plus />
              </span>
              <span className="attachcopy">
                <b>
                  {materials.length
                    ? ru
                      ? `${materials.length} материалов`
                      : `${materials.length} materials`
                    : ru
                      ? "Добавить контекст"
                      : "Attach context"}
                </b>
                <small>
                  {ru
                    ? "Файлы · вставка · drag & drop"
                    : "Files · paste · drag & drop"}
                </small>
              </span>
              {materials.length > 0 && <i>{materials.length}/12</i>}
              <input
                type="file"
                multiple
                accept=".txt,.md,.csv,.json,.js,.ts,.tsx,.py,.html,.css,.pdf,.docx"
                onChange={(event) => {
                  const files = event.currentTarget.files;
                  void addFiles(files);
                  event.currentTarget.value = "";
                }}
              />
            </label>
            <button
              className={`agentselect ${pickerOpen ? "active" : ""}`}
              onClick={() => setPickerOpen((open) => !open)}
            >
              <Users />
              <span>
                {selectedAgents.size
                  ? ru
                    ? `${selectedAgents.size} агентов`
                    : `${selectedAgents.size} agents`
                  : ru
                    ? "Выбрать агентов"
                    : "Choose agents"}
              </span>
              <ChevronDown />
            </button>
            <div className="agentpreview">
              {agents
                .filter((a) => selectedAgents.has(a.id))
                .slice(0, 4)
                .map((a, i) => (
                  <AgentGlyph
                    key={a.id}
                    name={a.name}
                    skillName={a.skill_name}
                    color={colors[i % colors.length]}
                    className="avatar"
                  />
                ))}
            </div>
            <button
              className="sendround"
              disabled={!value.trim() || !selectedAgents.size}
              title={
                !selectedAgents.size
                  ? ru
                    ? "Выберите хотя бы одного агента"
                    : "Choose at least one agent"
                  : ru
                    ? "Начать диалог"
                    : "Start chat"
              }
              onClick={submit}
            >
              <Send />
            </button>
          </div>
        </div>
        <div className="sessionbrief">
          <button
            className={`sessionbrief-trigger ${briefOpen ? "active" : ""}`}
            onClick={() => setBriefOpen((value) => !value)}
          >
            <span className="sessionbrief-orbit">
              <Sparkles />
            </span>
            <span className="sessionbrief-copy">
              <b>
                {selectedAgents.size
                  ? ru
                    ? "Контекст команды"
                    : "Team context"
                  : ru
                    ? "Соберите команду"
                    : "Build your team"}
              </b>
              <small>
                {selectedAgents.size
                  ? `${selectedAgents.size} ${ru ? "агентов" : "agents"} · ${materials.length} ${ru ? "материалов" : "materials"} · Memory on`
                  : ru
                    ? "Выберите агентов перед запуском"
                    : "Choose agents before launch"}
              </small>
            </span>
            <span
              className={`sessionbrief-status ${selectedAgents.size ? "ready" : ""}`}
            >
              <i />
              {selectedAgents.size
                ? ru
                  ? "ГОТОВО"
                  : "READY"
                : ru
                  ? "НАСТРОИТЬ"
                  : "SET UP"}
            </span>
          </button>
          {briefOpen && (
            <div className="sessionbrief-pop">
              <header>
                <Brain />
                <div>
                  <b>{ru ? "Контекст запуска" : "Launch context"}</b>
                  <small>
                    {ru
                      ? "Что команда получит до первого ответа"
                      : "What the team receives before its first response"}
                  </small>
                </div>
              </header>
              <div className="briefrows">
                <div>
                  <Users />
                  <span>
                    <b>{ru ? "Команда" : "Team"}</b>
                    <small>
                      {selectedAgents.size
                        ? agents
                            .filter((agent) => selectedAgents.has(agent.id))
                            .map((agent) => agent.name)
                            .join(", ")
                        : ru
                          ? "Агенты ещё не выбраны"
                          : "No agents selected"}
                    </small>
                  </span>
                  <strong>
                    {selectedAgents.size}/{agents.length}
                  </strong>
                </div>
                <div>
                  <FileText />
                  <span>
                    <b>{ru ? "Материалы диалога" : "Dialogue materials"}</b>
                    <small>
                      {materials.length
                        ? ru
                          ? "Будут прочитаны до начала работы"
                          : "Read before work begins"
                        : ru
                          ? "Можно добавить файлы и заметки"
                          : "Add files or notes if needed"}
                    </small>
                  </span>
                  <strong>{materials.length}/12</strong>
                </div>
                <div>
                  <Brain />
                  <span>
                    <b>{ru ? "Память команды" : "Team memory"}</b>
                    <small>
                      {ru
                        ? "Общая и профессиональная память агентов активна"
                        : "Shared and professional agent memory is active"}
                    </small>
                  </span>
                  <strong className="memoryon">ON</strong>
                </div>
              </div>
              <button
                className="briefaction"
                onClick={() => {
                  setBriefOpen(false);
                  setPickerOpen(true);
                }}
              >
                <Users />
                {ru ? "Настроить команду" : "Configure team"}
              </button>
            </div>
          )}
        </div>
        <div className="suggestions">
          <button
            onClick={() =>
              setValue(
                ru
                  ? "Исследуйте рынок и подготовьте конструктивный план запуска продукта"
                  : "Research the market and prepare a constructive product launch plan",
              )
            }
          >
            {ru ? "Исследовать рынок" : "Research a market"}
          </button>
          <button
            onClick={() =>
              setValue(
                ru
                  ? "Спроектируйте архитектуру нового сервиса и проверьте риски"
                  : "Design a system and assess its risks",
              )
            }
          >
            {ru ? "Спроектировать систему" : "Design a system"}
          </button>
          <button
            onClick={() =>
              setValue(
                ru
                  ? "Проведите критический разбор идеи и предложите улучшение"
                  : "Critically review an idea and propose improvements",
              )
            }
          >
            {ru ? "Проверить идею" : "Review an idea"}
          </button>
        </div>
      </div>
    </div>
  );
}

function LaunchChecklist({
  agents,
  connections,
  language,
  onNavigate,
  onClose,
}: {
  agents: Agent[];
  connections: Connection[];
  language: "ru" | "en";
  onNavigate: (screen: Screen) => void;
  onClose: () => void;
}) {
  const ru = language === "ru";
  const modelReady = agents.some((agent) => Boolean(agent.connection_id));
  // Context connectors are persisted by the API with the `connector-` prefix.
  // Keep the unprefixed form for workspaces created by older builds.
  const contextConnectorReady = (connector: string) =>
    connections.some(
      (connection) =>
        connection.provider === `connector-${connector}` || connection.provider === connector,
    );
  const bitqueryReady = contextConnectorReady("bitquery");
  const blockscoutReady = contextConnectorReady("blockscout");
  const steps = [
    {
      icon: Brain,
      ready: modelReady,
      label: ru ? "Подключить модель" : "Connect a model",
      copy: ru ? "Без неё команда останется в демо-режиме." : "Without it, the crew remains in demo mode.",
      screen: "team" as Screen,
      action: ru ? "Выбрать модель" : "Choose model",
    },
    {
      icon: Radar,
      ready: bitqueryReady,
      label: "Bitquery",
      copy: ru ? "Сделки, балансы и ранние on-chain сигналы." : "Trades, balances and early on-chain signals.",
      screen: "connections" as Screen,
      action: ru ? "Подключить" : "Connect",
    },
    {
      icon: ShieldCheck,
      ready: blockscoutReady,
      label: "Blockscout",
      copy: ru ? "Холдеры токена и быстрая проверка риска." : "Token holders and a fast risk check.",
      screen: "connections" as Screen,
      action: ru ? "Подключить" : "Connect",
    },
  ];
  const readyCount = steps.filter((step) => step.ready).length;
  return (
    <div className="modalback signal-onboarding-backdrop" role="presentation">
      <section className="signal-onboarding" role="dialog" aria-modal="true" aria-labelledby="signal-onboarding-title">
        <button className="signal-onboarding-close" onClick={onClose} aria-label={ru ? "Закрыть" : "Close"}><X /></button>
        <div className="signal-onboarding-art"><Mascot state={readyCount === steps.length ? "done" : "thinking"} size={210} /></div>
        <div className="signal-onboarding-copy">
          <p><i /> {ru ? "ПЕРВЫЙ ЗАПУСК" : "FIRST SIGNAL"}</p>
          <h2 id="signal-onboarding-title">{ru ? <>Соберём ваш<br /><em>signal room.</em></> : <>Let’s build your<br /><em>signal room.</em></>}</h2>
          <span>{ru ? "Три подключения превращают Orbit из красивой оболочки в рабочую торговую команду." : "Three connections turn Orbit from a beautiful shell into a working trading crew."}</span>
        </div>
        <div className="signal-onboarding-steps">
          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <article key={step.label} className={step.ready ? "ready" : ""}>
                <span className="signal-onboarding-number">0{index + 1}</span>
                <span className="signal-onboarding-icon"><Icon /></span>
                <div><b>{step.label}</b><small>{step.copy}</small></div>
                {step.ready ? <i><Check /></i> : <button onClick={() => onNavigate(step.screen)}>{step.action}<ChevronRight /></button>}
              </article>
            );
          })}
        </div>
        <footer><span>{readyCount}/{steps.length} {ru ? "сигнальных каналов готовы" : "signal channels ready"}</span><button onClick={onClose}>{ru ? "Настрою позже" : "I’ll set this up later"}</button></footer>
      </section>
    </div>
  );
}

function WorkflowHistory({
  history,
  openRun,
  onCreatedRun,
  newChat,
  agents,
  workspace,
  team,
  onUpdate,
  language,
}: {
  history: Run[];
  openRun: (r: Run) => void;
  onCreatedRun: (r: Run) => void;
  newChat: () => void;
  agents: Agent[];
  workspace: Workspace | null;
  team: Team | null;
  onUpdate: (r: Run) => void;
  language: "ru" | "en";
}) {
  const [search, setSearch] = useState("");
  const [archiveView, setArchiveView] = useState(false);
  const [templateBusy, setTemplateBusy] = useState<"token" | "nft" | null>(null);
  const [templateError, setTemplateError] = useState("");
  const ru = language === "ru";
  const filteredHistory = history
    .filter(
      (run) =>
        Boolean(run.context.archived) === archiveView &&
        run.goal.toLowerCase().includes(search.trim().toLowerCase()),
    )
    .sort(
      (a, b) =>
        Number(Boolean(b.context.pinned)) - Number(Boolean(a.context.pinned)),
    );
  async function meta(
    event: React.MouseEvent,
    run: Run,
    data: { pinned?: boolean; archived?: boolean },
  ) {
    event.stopPropagation();
    onUpdate(await api.updateRunMeta(run.id, data));
  }
  const agentId = (...skills: string[]) =>
    agents.find((agent) => skills.includes(agent.skill_name || ""))?.id || agents[0]?.id || "";
  async function createTradingPipeline(kind: "token" | "nft") {
    if (!workspace || !team || !agents.length || templateBusy) return;
    setTemplateBusy(kind);
    setTemplateError("");
    try {
      const graph = kind === "token"
        ? TOKEN_SIGNAL_SCAN_TEMPLATE.build({
            onChainAnalyst: agentId("On-Chain Researcher"),
            contractAuditor: agentId("Token Auditor"),
            marketAnalyst: agentId("Timing Analyst"),
            liquidityAnalyst: agentId("Liquidity Monitor", "On-Chain Researcher"),
            riskReviewer: agentId("Token Auditor", "Verdict Checker"),
            verdictAgent: agentId("Verdict Checker"),
          })
        : NFT_COLLECTION_SCAN_TEMPLATE.build({
            collectionResearcher: agentId("NFT Screener", "On-Chain Researcher"),
            holderAnalyst: agentId("On-Chain Researcher", "Wallet Tracker"),
            marketAnalyst: agentId("Timing Analyst", "NFT Screener"),
            provenanceAuditor: agentId("Token Auditor", "NFT Screener"),
            riskReviewer: agentId("Token Auditor", "Verdict Checker"),
            verdictAgent: agentId("Verdict Checker"),
          });
      if (graph.nodes.some((node) => node.type === "agent" && !node.agent_id)) {
        throw new Error(ru ? "Добавьте хотя бы одного агента перед созданием pipeline." : "Add at least one agent before creating a pipeline.");
      }
      const workflow = await api.createWorkflow({
        workspace_id: workspace.id,
        team_id: team.id,
        name: graph.name,
        description: graph.description,
        nodes: graph.nodes,
        edges: graph.edges,
        published: true,
      });
      const selectedAgentIds = [...new Set(
        graph.nodes
          .filter((node) => node.type === "agent" || node.type === "review")
          .map((node) => node.agent_id)
          .filter((id): id is string => Boolean(id)),
      )];
      const draft = await api.createRun(
        team.id,
        workflow.id,
        graph.goal,
        { agent_ids: selectedAgentIds, language },
        false,
      );
      onCreatedRun(draft);
    } catch (error) {
      setTemplateError((error as Error).message);
    } finally {
      setTemplateBusy(null);
    }
  }
  return (
    <div className="workflowhistory page">
      <header>
        <div>
          <p className="eyebrow">DIALOGUES</p>
          <h1>Workflows</h1>
          <p>
            {ru
              ? "Созданные диалоги и оркестрации агентов."
              : "Created conversations and agent orchestrations."}
          </p>
        </div>
        <button className="primary" onClick={newChat}>
          <Plus />
          {ru ? "Новый диалог" : "New conversation"}
        </button>
      </header>
      <div className="historytools">
        <div className="historysearch">
          <Search />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={ru ? "Поиск по диалогам" : "Search conversations"}
          />
        </div>
        <div className="archivefilter">
          <button
            className={!archiveView ? "active" : ""}
            onClick={() => setArchiveView(false)}
          >
            {ru ? "Активные" : "Active"}
          </button>
          <button
            className={archiveView ? "active" : ""}
            onClick={() => setArchiveView(true)}
          >
            <Archive />
            {ru ? "Архив" : "Archive"}
          </button>
        </div>
      </div>
      <section className="tradingtemplates">
        <div>
          <p className="eyebrow">TRADING PIPELINES</p>
          <h2>{ru ? "Не пустой граф, а порядок принятия решения" : "A decision process, not an empty graph"}</h2>
          <p>{ru ? "Шаблон создаёт черновик запуска: независимые проверки → риск-ревью → ваше обязательное подтверждение → вердикт." : "A template opens a draft run: independent checks → risk review → your required approval → verdict."}</p>
        </div>
        <div className="tradingtemplatecards">
          <article>
            <span><Radar /></span><b>{ru ? "Скан токена" : "Token signal scan"}</b>
            <small>{ru ? "Контракт, холдеры, рынок и ликвидность в параллельных проверках." : "Contract, holders, market, and liquidity in parallel checks."}</small>
            <button onClick={() => void createTradingPipeline("token")} disabled={Boolean(templateBusy) || !workspace || !team}>{templateBusy === "token" ? (ru ? "Создаём…" : "Creating…") : (ru ? "Открыть pipeline" : "Open pipeline")}<ChevronRight /></button>
          </article>
          <article>
            <span><ImageIcon /></span><b>{ru ? "Скан NFT-коллекции" : "NFT collection scan"}</b>
            <small>{ru ? "Тезис, владельцы, floor/ликвидность и provenance до решения." : "Thesis, holders, floor/liquidity, and provenance before a decision."}</small>
            <button onClick={() => void createTradingPipeline("nft")} disabled={Boolean(templateBusy) || !workspace || !team}>{templateBusy === "nft" ? (ru ? "Создаём…" : "Creating…") : (ru ? "Открыть pipeline" : "Open pipeline")}<ChevronRight /></button>
          </article>
        </div>
        {templateError && <p className="templateerror">{templateError}</p>}
      </section>
      <div className="dialoguelist">
        {history.length === 0 && (
          <div className="emptydialogue">
            {ru ? "Диалогов пока нет" : "No conversations yet"}
          </div>
        )}
        {history.length > 0 && filteredHistory.length === 0 && (
          <div className="emptydialogue">
            {ru ? "Ничего не найдено" : "Nothing found"}
          </div>
        )}
        {filteredHistory.map((r, index) => (
          <article
            key={r.id}
            className={r.context.pinned ? "pinned" : ""}
            onClick={() => openRun(r)}
          >
            <div className="dialogueicon">
              {r.context.pinned ? <Pin /> : <MessageSquare />}
            </div>
            <div>
              <h3>{r.goal}</h3>
              <p>
                {r.status} ·{" "}
                {new Date(r.created_at).toLocaleString(ru ? "ru-RU" : "en-US")}
              </p>
            </div>
            <div className="dialogueactions">
              <button
                title={
                  r.context.pinned
                    ? ru
                      ? "Открепить"
                      : "Unpin"
                    : ru
                      ? "Закрепить"
                      : "Pin"
                }
                onClick={(event) =>
                  meta(event, r, { pinned: !r.context.pinned })
                }
              >
                <Pin />
              </button>
              <button
                title={
                  archiveView
                    ? ru
                      ? "Вернуть из архива"
                      : "Restore"
                    : ru
                      ? "Архивировать"
                      : "Archive"
                }
                onClick={(event) => meta(event, r, { archived: !archiveView })}
              >
                <Archive />
              </button>
            </div>
            <div className="avatarrow">
              {agents.slice(0, 3).map((a, i) => (
                <AgentGlyph key={a.id} name={a.name} skillName={a.skill_name} color={colors[i]} />
              ))}
            </div>
            <span className="index">
              #{String(filteredHistory.length - index).padStart(2, "0")}
            </span>
          </article>
        ))}
      </div>
    </div>
  );
}

function DeepResearch({
  workspace,
  setError,
  language,
}: {
  workspace: Workspace | null;
  setError: (value: string) => void;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const sourceOptions = [
    { id: "web", labelRu: "Веб", labelEn: "Web" },
    { id: "youtube", labelRu: "YouTube", labelEn: "YouTube" },
    { id: "tiktok", labelRu: "TikTok", labelEn: "TikTok" },
    { id: "instagram", labelRu: "Instagram", labelEn: "Instagram" },
    { id: "onchain", labelRu: "On-chain данные", labelEn: "On-chain data" },
  ] as const;
  const sourceNames = sourceOptions.map((source) => source.id);
  const [query, setQuery] = useState("");
  const [sources, setSources] = useState<Set<string>>(new Set(sourceNames));
  const [depth, setDepth] = useState<"quick" | "deep">("deep");
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [current, setCurrent] = useState<ResearchReport | null>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (workspace)
      api
        .researchReports(workspace.id)
        .then((values) => {
          setReports(values);
          setCurrent(values[0] || null);
        })
        .catch((e) => setError(e.message));
  }, [workspace, setError]);
  async function research() {
    if (!workspace || !query.trim() || !sources.size) return;
    setRunning(true);
    try {
      const report = await api.createResearch({
        workspace_id: workspace.id,
        query: query.trim(),
        sources: [...sources],
        depth,
      });
      setReports((old) => [report, ...old]);
      setCurrent(report);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }
  function toggleSource(source: string) {
    setSources((old) => {
      const next = new Set(old);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }
  function sourceLabel(source: string) {
    const option = sourceOptions.find((item) => item.id === source);
    return option ? (ru ? option.labelRu : option.labelEn) : source;
  }
  const researchMetrics = useMemo(() => {
    if (!current) return null;
    const sourceCounts = current.findings.reduce<Record<string, number>>((total, finding) => {
      total[finding.source] = (total[finding.source] || 0) + 1;
      return total;
    }, {});
    const scores = current.findings.map((item) => Number(item.score) || 0);
    const averageScore = scores.length
      ? Math.round((scores.reduce((total, score) => total + score, 0) / scores.length) * 100)
      : 0;
    const enabledSources = Object.keys(current.source_status).length;
    const responsiveSources = Object.values(current.source_status).filter((item) => item.results > 0).length;
    return { sourceCounts, averageScore, enabledSources, responsiveSources };
  }, [current]);
  const researchReadout = useMemo(() => {
    if (!current || !researchMetrics) return null;
    const directFindings = current.findings.filter((item) => item.source === "onchain");
    const directSuccesses = directFindings.filter(
      (item) => (item as ResearchFinding & { provenance?: { status?: string } }).provenance?.status !== "error",
    );
    const failedDirectChecks = directFindings.length - directSuccesses.length;
    const publicFindings = current.findings.length - directFindings.length;
    const hasAddress = /0x[a-fA-F0-9]{40}/.test(current.query);
    const firstDirect = directSuccesses[0];
    const conclusion = firstDirect
      ? firstDirect.snippet
      : ru
        ? "В выбранных источниках не нашлось прямого проверяемого наблюдения."
        : "No direct, verifiable observation was returned by the selected sources.";
    const scope = hasAddress
      ? ru
        ? "Проверка адреса и связанных с ним публичных сигналов"
        : "Address review and related public signals"
      : ru
        ? "Исследование запроса по выбранным источникам"
        : "Research across the selected sources";
    return { directSuccesses, failedDirectChecks, publicFindings, conclusion, scope };
  }, [current, researchMetrics, ru]);
  const researchSteps = [
    {
      icon: Compass,
      title: ru ? "План" : "Plan",
      copy: ru ? "Разбивает вопрос на проверяемые подзадачи." : "Breaks the question into verifiable sub-questions.",
    },
    {
      icon: Search,
      title: ru ? "Сбор" : "Collect",
      copy: ru ? "Собирает только выбранные вами источники." : "Collects only the sources you selected.",
    },
    {
      icon: ShieldCheck,
      title: ru ? "Проверка" : "Verify",
      copy: ru ? "Помечает источник и релевантность каждого факта." : "Labels the source and relevance of each finding.",
    },
    {
      icon: Sparkles,
      title: ru ? "Вывод" : "Synthesize",
      copy: ru ? "Сводит доказательства, а не подменяет их мнением." : "Synthesizes evidence instead of replacing it with opinion.",
    },
  ];
  return (
    <div className="researchpage">
      <aside className="researchhistory">
        <div>
          <p className="eyebrow">RESEARCH LIBRARY</p>
          <h2>Deep Research</h2>
        </div>
        {reports.map((report) => (
          <button
            key={report.id}
            className={current?.id === report.id ? "active" : ""}
            onClick={() => setCurrent(report)}
          >
            <Globe2 />
            <div>
              <b>{report.query}</b>
              <small>
                {report.findings.length} {ru ? "источников" : "sources"} ·{" "}
                {report.depth}
              </small>
            </div>
          </button>
        ))}
      </aside>
      <main className="researchmain">
        <header>
          <div>
            <p className="eyebrow">MULTI-SOURCE INTELLIGENCE</p>
            <PageTitle text={ru ? "Исследуйте тему глубже" : "Explore a topic in depth"} />
            <p>
              {ru
                ? "Веб, социальные платформы и проверяемые on-chain данные в одном отчёте."
                : "Web, social platforms, and verifiable on-chain data in one report."}
            </p>
          </div>
          <div className="research-managed-sources" role="status">
            <ShieldCheck />
            <span>
              <b>{ru ? "Источники подключены" : "Sources ready"}</b>
              <small>
                {ru ? "Поиск выполняет Orbit" : "Search is provided by Orbit"}
              </small>
            </span>
          </div>
        </header>
        <section className="researchcomposer">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              ru
                ? "Например: проверь контракт 0x… — возраст, холдеров, ликвидность и риски"
                : "For example: assess contract 0x… — age, holders, liquidity, and risks"
            }
          />
          <div className="research-method" aria-label={ru ? "Как работает Deep Research" : "How Deep Research works"}>
            {researchSteps.map((step, index) => {
              const Icon = step.icon;
              return <article key={step.title}>
                <span>0{index + 1}</span><Icon />
                <div><b>{step.title}</b><small>{step.copy}</small></div>
              </article>;
            })}
          </div>
          <div className="researchoptions">
            <div className="sourcepills">
              {sourceOptions.map((source) => (
                <button
                  key={source.id}
                  className={`${sources.has(source.id) ? "active" : ""} ${source.id === "onchain" ? "onchain" : ""}`}
                  onClick={() => toggleSource(source.id)}
                  title={
                    source.id === "onchain"
                      ? ru
                        ? "Проверяемые данные из Robinhood Chain RPC"
                        : "Verifiable data from Robinhood Chain RPC"
                      : sourceLabel(source.id)
                  }
                >
                  {source.id === "web" ? (
                    <Globe2 />
                  ) : source.id === "onchain" ? (
                    <Wallet />
                  ) : (
                    <Search />
                  )}
                  {sourceLabel(source.id)}
                </button>
              ))}
            </div>
            <select
              value={depth}
              onChange={(e) => setDepth(e.target.value as "quick" | "deep")}
            >
              <option value="quick">{ru ? "Быстрый скан" : "Quick scan"}</option>
              <option value="deep">{ru ? "Глубокое исследование" : "Deep research"}</option>
            </select>
            <button
              className="primary"
              disabled={running || !query.trim() || !sources.size}
              onClick={research}
            >
              {running ? (
                <Activity />
              ) : (
                <>
                  <Sparkles />
                  {ru ? "Начать исследование" : "Start research"}
                </>
              )}
            </button>
          </div>
          <div className="onchainsourcehint">
            <Wallet aria-hidden="true" />
            <div>
              <b>
                {ru
                  ? "On-chain: проверяемый Robinhood Chain RPC"
                  : "On-chain: verifiable Robinhood Chain RPC"}
              </b>
              <small>
                {ru
                  ? "Получает сырые данные сети; их можно независимо сверить по адресу, хешу транзакции или номеру блока."
                  : "Retrieves raw network data that can be independently checked by address, transaction hash, or block number."}
              </small>
            </div>
            <code>Robinhood Chain RPC</code>
          </div>
          <p className="research-depth-note">
            {depth === "quick"
              ? ru
                ? "Быстрый скан: identity контракта, возраст и риск-поверхность."
                : "Quick scan: contract identity, age, and risk surface."
              : ru
                ? "Глубокое исследование: быстрый скан + ликвидность, концентрация холдеров и сравнение источников."
                : "Deep research: quick scan plus liquidity, holder concentration, and cross-source comparison."}
          </p>
          {running && (
            <OrbitLoader
              label={ru ? "ИССЛЕДУЕМ" : "RESEARCHING"}
              detail={
                ru
                  ? "Планируем запросы → ищем платформы → проверяем источники → собираем отчёт"
                  : "Planning queries → searching platforms → validating sources → building report"
              }
            />
          )}
        </section>
        {current ? (
          <section className="researchresult">
            <header>
              <div>
                <span className="status ready">COMPLETED</span>
                <h2>{current.query}</h2>
                <p>
                  {new Date(current.created_at).toLocaleString(
                    ru ? "ru-RU" : "en-US",
                  )}{" "}
                  · {current.findings.length} {ru ? "материалов" : "items"}
                </p>
              </div>
              <div className="sourcestatus">
                {Object.entries(current.source_status).map(
                  ([source, value]) => (
                    <span key={source} className={value.results ? "ok" : ""}>
                      {sourceLabel(source)} · {value.results}
                    </span>
                  ),
                )}
              </div>
            </header>
            {researchMetrics && (
              <div className="researchmetrics">
                <article><small>{ru ? "МАТЕРИАЛЫ" : "MATERIALS"}</small><b>{current.findings.length}</b><span>{ru ? "отдельных наблюдений" : "separate observations"}</span></article>
                <article><small>{ru ? "ПОКРЫТИЕ" : "COVERAGE"}</small><b>{researchMetrics.responsiveSources}/{researchMetrics.enabledSources}</b><span>{ru ? "выбранных источников ответили" : "selected sources returned data"}</span></article>
                <article><small>{ru ? "СОВПАДЕНИЕ С ЗАПРОСОМ" : "QUERY MATCH"}</small><b>{researchMetrics.averageScore}%</b><span>{ru ? "оценка совпадения, не достоверность" : "match estimate, not truth"}</span></article>
                <article className="researchattribution"><small>{ru ? "РАСПРЕДЕЛЕНИЕ ИСТОЧНИКОВ" : "SOURCE MIX"}</small><div>{Object.entries(researchMetrics.sourceCounts).map(([source, count]) => <span key={source} style={{ width: `${Math.max(8, (count / Math.max(current.findings.length, 1)) * 100)}%` }} title={`${sourceLabel(source)} · ${count}`}>{sourceLabel(source)} <b>{count}</b></span>)}</div></article>
              </div>
            )}
            {researchReadout && <section className="researchreadout" aria-label={ru ? "Итог исследования" : "Research conclusion"}>
              <div className="researchverdict">
                <span className="researchsectionlabel"><Fingerprint /> {ru ? "ВЫВОД НА ОСНОВЕ ДАННЫХ" : "EVIDENCE-BASED READOUT"}</span>
                <h3>{researchReadout.scope}</h3>
                <p>{researchReadout.conclusion}</p>
                <small>{ru ? "Это исследовательский вывод, а не финансовая рекомендация. Откройте первоисточник перед важным решением." : "This is a research readout, not financial advice. Open the primary source before a consequential decision."}</small>
              </div>
              <div className="researchfacts">
                <article><b>{researchReadout.directSuccesses.length}</b><span>{ru ? "прямых on-chain наблюдений" : "direct on-chain observations"}</span></article>
                <article><b>{researchReadout.publicFindings}</b><span>{ru ? "публичных результатов для проверки" : "public results to verify"}</span></article>
                <article className={researchReadout.failedDirectChecks ? "warning" : ""}><b>{researchReadout.failedDirectChecks || "—"}</b><span>{researchReadout.failedDirectChecks ? (ru ? "прямых проверок не ответили" : "direct checks did not respond") : (ru ? "пропусков прямой проверки нет" : "no direct checks were missed")}</span></article>
              </div>
            </section>}
            <div className="researchbody">
              <article className="reportdocument">
                <header><div><p className="eyebrow">{ru ? "КЛЮЧЕВЫЕ НАБЛЮДЕНИЯ" : "KEY OBSERVATIONS"}</p><h3>{ru ? "Что именно было найдено" : "What was found"}</h3></div><span>{ru ? "Каждый пункт ведёт к источнику справа" : "Every item links to a source at right"}</span></header>
                <div className="findingledger">
                  {current.findings.slice(0, 8).map((item, index) => <article key={`${item.url}-${index}`}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div><div className="findingmeta"><b>{sourceLabel(item.source)}</b><small>{Math.round(item.score * 100)}% {ru ? "совпадение с запросом" : "query match"}</small></div><h4>{item.title}</h4><p>{item.snippet || (ru ? "Источник не отдал описание; откройте страницу для проверки." : "The source returned no description; open it to verify.")}</p></div>
                  </article>)}
                </div>
                <details className="researchraw"><summary>{ru ? "Показать техническую сводку исследования" : "Show technical research log"}</summary><pre>{current.report}</pre></details>
              </article>
              <aside className="evidence">
                <div className="evidencehead"><div><p className="eyebrow">{ru ? "ИСТОЧНИКИ" : "SOURCES"} · {current.findings.length}</p><span>{ru ? "Открываются в новой вкладке" : "Open in a new tab"}</span></div><FileText /></div>
                {current.findings.slice(0, 16).map((item, index) => (
                  <a
                    key={`${item.url}-${index}`}
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span>{index + 1}</span>
                    <div>
                      <b>{item.title}</b>
                      <small>
                        {sourceLabel(item.source)} · {Math.round(item.score * 100)}%{" "}
                        {ru ? "совпадение с запросом" : "query match"}
                      </small>
                    </div>
                  </a>
                ))}
              </aside>
            </div>
          </section>
        ) : (
          <div className="researchempty">
            <Globe2 />
            <h2>{ru ? "Первое исследование" : "Your first research"}</h2>
            <p>
              {ru
                ? "Сформулируйте вопрос, выберите площадки и запустите сбор данных."
                : "Ask a question, choose sources, and start collecting evidence."}
            </p>
          </div>
        )}
      </main>
    </div>
  );
}

function TokenBoard({
  workspace,
  team,
  setError,
  language,
  onRunCreated,
}: {
  workspace: Workspace | null;
  team: Team | null;
  setError: (value: string) => void;
  language: "ru" | "en";
  onRunCreated: (run: Run) => void;
}) {
  const ru = language === "ru";
  const [tokens, setTokens] = useState<Token[]>([]);
  const [selected, setSelected] = useState<Token | null>(null);
  const [verdicts, setVerdicts] = useState<TokenVerdict[]>([]);
  const [observations, setObservations] = useState<MarketObservation[]>([]);
  const [evaluations, setEvaluations] = useState<DecisionEvaluation[]>([]);
  const [paperTrades, setPaperTrades] = useState<PaperTrade[]>([]);
  const [decisionQuality, setDecisionQuality] = useState<DecisionQuality | null>(null);
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [assetKind, setAssetKind] = useState<"token" | "nft">("token");
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncingMarket, setSyncingMarket] = useState(false);
  const [replayingVerdict, setReplayingVerdict] = useState<string | null>(null);
  const [paperAction, setPaperAction] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    try {
      const values = await api.tokens(workspace.id);
      setTokens(values);
      setSelected((current) =>
        values.find((item) => item.id === current?.id) || values[0] || null,
      );
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [workspace, setError]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectedId = selected?.id;
  useEffect(() => {
    if (!selectedId) {
      setVerdicts([]);
      setObservations([]);
      setEvaluations([]);
      setPaperTrades([]);
      return;
    }
    Promise.all([
      api.tokenVerdicts(selectedId),
      api.marketObservations(selectedId),
      api.decisionEvaluations(selectedId),
      api.paperTrades(selectedId),
    ]).then(([nextVerdicts, nextObservations, nextEvaluations, nextTrades]) => {
      setVerdicts(nextVerdicts);
      setObservations(nextObservations);
      setEvaluations(nextEvaluations);
      setPaperTrades(nextTrades);
    }).catch((error) => setError((error as Error).message));
  }, [selectedId, setError]);

  useEffect(() => {
    if (!workspace) {
      setDecisionQuality(null);
      return;
    }
    api.decisionQuality(workspace.id).then(setDecisionQuality).catch((error) =>
      setError((error as Error).message),
    );
  }, [workspace, setError]);

  async function syncMarketHistory() {
    if (!selected || syncingMarket) return;
    setSyncingMarket(true);
    try {
      const captured = await api.captureMarketObservations(selected.id);
      setObservations((current) => [...captured, ...current].reduce<MarketObservation[]>((items, item) => (
        items.some((known) => known.id === item.id) ? items : [...items, item]
      ), []).sort((left, right) => right.observed_at.localeCompare(left.observed_at)));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSyncingMarket(false);
    }
  }

  async function replayVerdict(verdict: TokenVerdict) {
    if (!selected || replayingVerdict) return;
    setReplayingVerdict(verdict.id);
    try {
      const evaluation = await api.evaluateDecision(selected.id, verdict.id);
      setEvaluations((current) => [evaluation, ...current]);
      if (workspace) setDecisionQuality(await api.decisionQuality(workspace.id));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setReplayingVerdict(null);
    }
  }

  async function openPaperTrade(verdict: TokenVerdict) {
    if (!selected || paperAction) return;
    setPaperAction(verdict.id);
    try {
      const trade = await api.createPaperTrade(selected.id, verdict.id);
      setPaperTrades((current) => [trade, ...current]);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPaperAction(null);
    }
  }

  async function closePaperTrade(trade: PaperTrade) {
    if (!selected || paperAction) return;
    const observation = observations.find((item) =>
      item.kind === "trade" && !!trade.opened_at && item.observed_at > trade.opened_at,
    );
    if (!observation) {
      setError(ru ? "Нужна более поздняя исполненная сделка для закрытия paper-позиции." : "A later executable trade observation is required to close this paper position.");
      return;
    }
    setPaperAction(trade.id);
    try {
      const updated = await api.closePaperTrade(trade.id, observation.id);
      setPaperTrades((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPaperAction(null);
    }
  }

  async function trackToken(event: React.FormEvent) {
    event.preventDefault();
    if (!workspace || !address.trim() || saving) return;
    setSaving(true);
    try {
      const token = await api.createToken({
        workspace_id: workspace.id,
        address: address.trim(),
        asset_kind: assetKind,
        label: label.trim() || undefined,
        watchlist: true,
      });
      setTokens((current) => [token, ...current]);
      setSelected(token);
      setAddress("");
      setLabel("");
      setAssetKind("token");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleWatch(token: Token) {
    try {
      const next = await api.updateToken(token.id, { watchlist: !token.watchlist });
      setTokens((current) => current.map((item) => (item.id === next.id ? next : item)));
      setSelected((current) => (current?.id === next.id ? next : current));
    } catch (error) {
      setError((error as Error).message);
    }
  }

  async function removeToken(token: Token) {
    if (!window.confirm(ru ? "Удалить токен из реестра?" : "Remove this token from the registry?")) return;
    try {
      await api.deleteToken(token.id);
      const next = tokens.filter((item) => item.id !== token.id);
      setTokens(next);
      setSelected(next[0] || null);
    } catch (error) {
      setError((error as Error).message);
    }
  }

  async function startTokenScan() {
    if (!team || !selected || starting) return;
    setStarting(true);
    try {
      const run = await api.createRun(
        team.id,
        undefined,
        selected.asset_kind === "nft"
          ? ru
            ? `Проведи проверяемый on-chain разбор NFT-коллекции ${selected.address}: ERC-721 identity, mint/transfer activity, наблюдаемые холдеры, provenance и честно отметь недоступные без indexer floor и sales.`
            : `Perform a verifiable on-chain scan of NFT collection ${selected.address}: ERC-721 identity, mint/transfer activity, observed holders, provenance, and explicitly mark floor and sales unavailable without an indexer.`
          : ru
            ? `Проведи проверяемый on-chain разбор токена ${selected.address}: контракт, возраст, минтер, холдеры, ликвидность и торговый вердикт.`
            : `Perform a verifiable on-chain scan of token ${selected.address}: contract, age, minter, holders, liquidity, and a trading verdict.`,
        {
          token_id: selected.id,
          token_address: selected.address,
          chain_id: selected.chain_id,
          asset_kind: "token",
          paper_trading: selected.asset_kind === "token",
          paper_notional: 1000,
          language,
        },
      );
      onRunCreated(run);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setStarting(false);
    }
  }

  const shortAddress = (value: string) =>
    value.length > 14 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value;
  const title = (token: Token) => token.label || token.symbol || token.name || token.address;
  const detailTitle = (token: Token) => token.label || token.symbol || token.name || shortAddress(token.address);
  const latestEvaluationByVerdict = new Map<string, DecisionEvaluation>();
  evaluations.forEach((evaluation) => {
    if (!latestEvaluationByVerdict.has(evaluation.verdict_id)) latestEvaluationByVerdict.set(evaluation.verdict_id, evaluation);
  });
  const activeTradeByVerdict = new Map<string, PaperTrade>();
  paperTrades.forEach((trade) => {
    if (trade.verdict_id && ["pending", "open"].includes(trade.status) && !activeTradeByVerdict.has(trade.verdict_id)) {
      activeTradeByVerdict.set(trade.verdict_id, trade);
    }
  });

  return (
    <div className="tokenboard page">
      <header className="tokenboard-head">
        <div>
          <p className="eyebrow">ROBINHOOD CHAIN · TOKEN REGISTRY</p>
          <PageTitle text={ru ? "Токены под наблюдением" : "Tokens under watch"} />
          <p>
            {ru
              ? "Сохраните контракт один раз — затем прикрепляйте к нему проверяемые исследования и вердикты команды."
              : "Save a contract once, then attach verifiable research and team verdicts to it."}
          </p>
        </div>
        <span className="tokenboard-network"><i /> Robinhood Chain <b>4663</b></span>
      </header>

      <section className="tokenboard-track">
        <div>
          <Radar />
          <span>
            <b>{ru ? "Добавить контракт" : "Track a contract"}</b>
            <small>{ru ? "Адрес сохраняется в реестре рабочего пространства." : "The address is saved in this workspace registry."}</small>
          </span>
        </div>
        <form onSubmit={trackToken}>
          <input
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="0x…"
            spellCheck={false}
            aria-label={ru ? "Адрес контракта" : "Contract address"}
          />
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder={ru ? "Метка (необязательно)" : "Label (optional)"}
            aria-label={ru ? "Метка токена" : "Token label"}
          />
          <select
            value={assetKind}
            onChange={(event) => setAssetKind(event.target.value as "token" | "nft")}
            aria-label={ru ? "Тип актива" : "Asset type"}
          >
            <option value="token">{ru ? "Токен" : "Token"}</option>
            <option value="nft">NFT collection</option>
          </select>
          <button className="primary" disabled={saving || !address.trim()}>
            <Plus /> {saving ? (ru ? "Сохраняем" : "Saving") : (ru ? "В watchlist" : "Add to watchlist")}
          </button>
        </form>
      </section>

      <div className="tokenboard-grid">
        <section className="tokenlist" aria-busy={loading}>
          <header>
            <span>{ru ? "Реестр" : "Registry"}</span>
            <b>{tokens.length}</b>
          </header>
          {tokens.length ? tokens.map((token) => (
            <button
              key={token.id}
              className={selected?.id === token.id ? "active" : ""}
              onClick={() => setSelected(token)}
            >
              <span className="tokenident">{token.asset_kind === "nft" ? <ImageIcon /> : <Wallet />}<i>{(token.symbol || token.label || (token.asset_kind === "nft" ? "N" : "T")).slice(0, 2).toUpperCase()}</i></span>
              <span>
                <b>{title(token)}</b>
                <small>{shortAddress(token.address)}</small>
              </span>
              {token.watchlist && <StarMark />}
            </button>
          )) : (
            <div className="tokenempty"><Radar /><b>{ru ? "Пока пусто" : "Nothing tracked yet"}</b><small>{ru ? "Добавьте адрес первого контракта." : "Add a first contract address."}</small></div>
          )}
        </section>

        <section className="tokendetail">
          {selected ? <>
            <header>
              <div className="tokenident large">{selected.asset_kind === "nft" ? <ImageIcon /> : <Wallet />}<i>{(selected.symbol || selected.label || (selected.asset_kind === "nft" ? "N" : "T")).slice(0, 2).toUpperCase()}</i></div>
              <div className="tokenidentitycopy">
                <p className="eyebrow">{selected.asset_kind === "nft" ? "NFT COLLECTION · " : "TOKEN · "}{selected.watchlist ? (ru ? "В WATCHLIST" : "IN WATCHLIST") : (ru ? "В РЕЕСТРЕ" : "IN REGISTRY")}</p>
                <h2 title={title(selected)}>{detailTitle(selected)}</h2>
                <code title={selected.address}>{selected.address}</code>
              </div>
              <div className="tokenactions">
                <button className="primary" onClick={() => void startTokenScan()} disabled={starting || !team}>{starting ? (ru ? "Запускаем…" : "Starting…") : (ru ? "Запустить scan" : "Start scan")}</button>
                <button onClick={() => toggleWatch(selected)}>{selected.watchlist ? (ru ? "Убрать из watchlist" : "Remove watch") : (ru ? "В watchlist" : "Watch")}</button>
                <button className="danger" onClick={() => removeToken(selected)} aria-label={ru ? "Удалить токен" : "Remove token"}><Trash2 /></button>
              </div>
            </header>
            <div className="tokenfacts">
              <span><small>{ru ? "Сеть" : "Network"}</small><b>Robinhood Chain</b></span>
              <span><small>{ru ? "Chain ID" : "Chain ID"}</small><b>{selected.chain_id}</b></span>
              <span><small>{ru ? "Сохранён" : "Tracked since"}</small><b>{new Date(selected.created_at).toLocaleDateString(ru ? "ru-RU" : "en-US")}</b></span>
            </div>
            {selected.asset_kind === "token" && <section className="paperlab">
              <header>
                <div><p className="eyebrow">{ru ? "ПРОВЕРКА РЕШЕНИЙ · БЕЗ РЕАЛЬНЫХ СДЕЛОК" : "DECISION CHECK · NO REAL TRADES"}</p><h3>{ru ? "Как эта проверка заполняется" : "How this review gets filled"}</h3></div>
                <button onClick={() => void syncMarketHistory()} disabled={syncingMarket}>{syncingMarket ? (ru ? "Синхронизация…" : "Syncing…") : <><Waves /> {ru ? "Загрузить историю on-chain сделок" : "Load on-chain trade history"}</>}</button>
              </header>
              <p>{ru ? "Ничего вводить вручную не нужно. Orbit создаёт вердикт после скана, затем берёт только реальные выполненные swaps из сети и сравнивает решение с тем, что произошло после него. Кошелёк и настоящие сделки не используются." : "You do not enter anything manually. Orbit creates a verdict after a scan, then uses only executed on-chain swaps to compare that decision with what happened afterwards. No wallet or real trade is used."}</p>
              <div className="paperlab-journey" aria-label={ru ? "Путь проверки решения" : "Decision review flow"}>
                <article className={verdicts.length ? "complete" : "active"}><span>01</span><div><b>{ru ? "Запустите скан" : "Run a scan"}</b><small>{ru ? "Команда проверит контракт и сформирует ENTER, WATCH или SKIP." : "The team checks the contract and returns ENTER, WATCH, or SKIP."}</small></div>{verdicts.length ? <Check /> : <button onClick={() => void startTokenScan()} disabled={starting || !team}>{starting ? (ru ? "Запускаем…" : "Starting…") : (ru ? "Запустить" : "Start")}</button>}</article>
                <article className={verdicts.length ? (observations.some((item) => item.kind === "trade") ? "complete" : "active") : "locked"}><span>02</span><div><b>{ru ? "Загрузите цены после вердикта" : "Load prices after the verdict"}</b><small>{ru ? "Orbit считывает только подтверждённые on-chain swaps, а не прогнозные цены." : "Orbit reads only confirmed on-chain swaps, never projected prices."}</small></div><button onClick={() => void syncMarketHistory()} disabled={syncingMarket || !verdicts.length}>{syncingMarket ? (ru ? "Загружаем…" : "Loading…") : (ru ? "Загрузить" : "Load")}</button></article>
                <article className={evaluations.some((item) => item.status === "complete") ? "complete" : verdicts.length && observations.some((item) => item.kind === "trade") ? "active" : "locked"}><span>03</span><div><b>{ru ? "Сравните решение с рынком" : "Compare the decision with the market"}</b><small>{ru ? "Кнопка проверки появится у каждого вердикта ниже, когда данных будет достаточно." : "A review button appears under each verdict below once there is enough data."}</small></div>{evaluations.some((item) => item.status === "complete") ? <Check /> : <ShieldCheck />}</article>
              </div>
              <div className="paperlab-metrics">
                <span><strong>{observations.filter((item) => item.kind === "trade").length}</strong><small>{ru ? "подтверждённых on-chain сделок" : "confirmed on-chain trades"}</small></span>
                <span><strong>{evaluations.filter((item) => item.status === "complete").length}</strong><small>{ru ? "решений, сверенных с рынком" : "decisions checked against market data"}</small></span>
                <span><strong>{paperTrades.filter((item) => item.status === "open").length}</strong><small>{ru ? "активных учебных позиций" : "active simulated positions"}</small></span>
              </div>
              {decisionQuality && <div className="scorecards">
                <header><b>{ru ? "КАЛИБРОВКА АГЕНТОВ" : "AGENT CALIBRATION"}</b><small>{decisionQuality.resolved_decisions} {ru ? "закрытых оценок" : "resolved evaluations"}</small></header>
                {decisionQuality.scorecards.length ? decisionQuality.scorecards.slice(0, 5).map((card) => <article key={card.agent_id}>
                  <span><b>{card.agent_name}</b><small>{card.model || (ru ? "модель не указана" : "model unavailable")}</small></span>
                  <strong>{card.hit_rate === null ? "—" : `${Math.round(card.hit_rate * 100)}%`}</strong>
                  <em>{card.brier_score === null ? "—" : `Brier ${card.brier_score.toFixed(2)}`}</em>
                </article>) : <small className="scorecards-empty">{ru ? "Scorecard появится после первого replay с реальными post-decision данными." : "The scorecard appears after the first replay with real post-decision data."}</small>}
              </div>}
            </section>}
            <div className="tokenverdicts">
              <header><div><p className="eyebrow">DECISION HISTORY</p><h3>{ru ? "Вердикты команды" : "Team verdicts"}</h3></div><span>{verdicts.length}</span></header>
              {verdicts.length ? verdicts.map((verdict) => (
                <article key={verdict.id}>
                  <b className={`decision-${verdict.verdict.toLowerCase()}`}>{verdict.verdict}</b>
                  <span>{new Date(verdict.created_at).toLocaleString(ru ? "ru-RU" : "en-US")}</span>
                  {typeof verdict.payload.rationale === "string" && <p>{verdict.payload.rationale}</p>}
                  {selected.asset_kind === "token" && <div className="verdictlab-actions">
                    <button onClick={() => void replayVerdict(verdict)} disabled={!!replayingVerdict || observations.filter((item) => item.kind === "trade").length < 2}>{replayingVerdict === verdict.id ? (ru ? "Проверяем…" : "Replaying…") : (ru ? "Replay 24ч" : "Replay 24h")}</button>
                    {verdict.verdict.toUpperCase() === "ENTER" && !activeTradeByVerdict.has(verdict.id) && <button onClick={() => void openPaperTrade(verdict)} disabled={!!paperAction}>{paperAction === verdict.id ? (ru ? "Открываем…" : "Opening…") : (ru ? "Paper trade" : "Paper trade")}</button>}
                    {latestEvaluationByVerdict.get(verdict.id) && <small className={`evaluation-${latestEvaluationByVerdict.get(verdict.id)?.outcome}`}>{latestEvaluationByVerdict.get(verdict.id)?.status === "complete" ? `${latestEvaluationByVerdict.get(verdict.id)?.outcome} · ${(latestEvaluationByVerdict.get(verdict.id)?.strategy_return_pct || 0).toFixed(2)}%` : (ru ? "данных недостаточно" : "insufficient data")}</small>}
                  </div>}
                </article>
              )) : <div className="verdictempty"><ShieldCheck /><p>{ru ? "Здесь появятся структурированные решения, связанные с этим контрактом." : "Structured decisions linked to this contract will appear here."}</p></div>}
            </div>
            {selected.asset_kind === "token" && <section className="paperledger">
              <header><div><p className="eyebrow">PAPER LEDGER</p><h3>{ru ? "Условные позиции" : "Dry-run positions"}</h3></div><span>{paperTrades.length}</span></header>
              {paperTrades.length ? paperTrades.map((trade) => <article key={trade.id}>
                <b className={`paperstatus-${trade.status}`}>{trade.status}</b>
                <span>{trade.decision} · {trade.notional.toLocaleString(undefined, { maximumFractionDigits: 2 })} {trade.quote_symbol}</span>
                <strong className={trade.return_pct === null ? "" : trade.return_pct >= 0 ? "positive" : "negative"}>{trade.return_pct === null ? "—" : `${trade.return_pct.toFixed(2)}%`}</strong>
                {trade.status === "open" && <button onClick={() => void closePaperTrade(trade)} disabled={!!paperAction}>{paperAction === trade.id ? (ru ? "Закрываем…" : "Closing…") : (ru ? "Закрыть по последней сделке" : "Close at latest trade")}</button>}
                {trade.status === "pending" && <small>{ru ? "Ждёт первую исполненную on-chain сделку после решения." : "Waiting for the first executed on-chain trade after the decision."}</small>}
                {trade.close_reason && <small>{trade.close_reason}</small>}
              </article>) : <div className="paperledger-empty"><BarChart3 /><p>{ru ? "Paper-позиция появится только после защищённого ENTER-вердикта." : "A paper position appears only after a protection-approved ENTER verdict."}</p></div>}
            </section>}
          </> : <div className="tokendetail-empty"><Radar /><h2>{ru ? "Выберите токен" : "Select a token"}</h2><p>{ru ? "Реестр связывает адрес, watchlist и историю решений команды." : "The registry links an address, watchlist state, and the team’s decision history."}</p></div>}
        </section>
      </div>
    </div>
  );
}

function StarMark() {
  return <span className="watchmark" aria-label="watchlist">✦</span>;
}

function MemoryMap({
  notes,
  onChange,
  language,
}: {
  notes: MemoryNote[];
  onChange: (n: MemoryNote) => void;
  language: "ru" | "en";
}) {
  const localizedTitle = (note: MemoryNote) => {
    if (note.scope === "global" && ["Основная память", "Core memory"].includes(note.title))
      return language === "ru" ? "Основная память" : "Core memory";
    return note.title;
  };
  const localizedSummary = (note: MemoryNote) => {
    if (note.scope === "global" && note.summary.startsWith("Долговременные знания"))
      return language === "ru"
        ? "Долговременные знания, предпочтения и решения пользователя."
        : "Long-term knowledge, preferences, and decisions for this workspace.";
    if (note.scope === "dialogue" && note.summary === "Компактный лог целей и решений этого диалога.")
      return language === "ru"
        ? note.summary
        : "A compact record of this dialogue’s goals and decisions.";
    return note.summary;
  };
  const localizedContent = (note: MemoryNote) => {
    if (note.scope === "global" && note.content === "# Основная память\n\nЗдесь сохраняются устойчивые знания между диалогами.")
      return language === "ru"
        ? note.content
        : "# Core memory\n\nDurable knowledge is kept here between dialogues.";
    const legacyDialogue = /^# Диалог\n\nЦель: (.+)$/s.exec(note.content);
    if (legacyDialogue && language === "en") return `# Dialogue\n\nGoal: ${legacyDialogue[1]}`;
    return note.content;
  };
  const global = notes.find((n) => n.scope === "global");
  const allDialogues = Array.from(
    new Map(
      notes
        .filter(
          (n) =>
            n.scope === "dialogue" &&
            !n.title.trim().toUpperCase().startsWith("E2E:"),
        )
        .map((note) => [note.run_id || note.id, note]),
    ).values(),
  );
  const dialogues = allDialogues.slice(0, 10);
  const hiddenCount = Math.max(0, allDialogues.length - dialogues.length);
  const [selected, setSelected] = useState<MemoryNote | null>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  useEffect(() => setText(selected?.content || ""), [selected]);
  const positions = dialogues.map((note, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(dialogues.length, 1) - 0.7;
    const radius = 220 + (i % 2) * 55;
    return {
      note,
      x: 500 + Math.cos(angle) * radius,
      y: 330 + Math.sin(angle) * radius,
    };
  });
  async function save() {
    if (!selected) return;
    const value = await api.updateMemory(selected.id, { content: text });
    onChange(value);
    setSelected(value);
    setEditing(false);
  }
  function exportMemory() {
    const sorted = [...notes].sort((a, b) =>
      a.scope === b.scope
        ? new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        : a.scope === "global"
          ? -1
          : 1,
    );
    const markdown = [
      "# Orbit Memory",
      `_Exported ${new Date().toISOString()}_`,
      "",
      ...sorted.flatMap((note) => [
        `## ${note.title}`,
        `**Scope:** ${note.scope}  `,
        `**Size:** ${note.byte_size} bytes  `,
        note.summary ? `**Summary:** ${note.summary}` : "",
        "",
        note.content,
        "",
        "---",
        "",
      ]),
    ].join("\n");
    saveFile(
      `orbit-memory-${new Date().toISOString().slice(0, 10)}.md`,
      markdown,
      "text/markdown",
    );
  }
  return (
    <div className="memorypage">
      <header className="memoryhead">
        <div>
          <p className="eyebrow">KNOWLEDGE GRAPH</p>
          <h1>{language === "ru" ? "Память" : "Memory"}</h1>
          <p>
            {language === "ru"
              ? "Живая база знаний команды и компактные итоги диалогов."
              : "The team's living knowledge base and compact dialogue outcomes."}
          </p>
        </div>
        <div className="memoryheadtools">
          <div className="memoryusage">
            <Brain />
            <span>
              {allDialogues.length}{" "}
              {language === "ru" ? "диалогов" : "dialogues"} ·{" "}
              {(notes.reduce((n, x) => n + x.byte_size, 0) / 1024).toFixed(1)}{" "}
              KB
            </span>
          </div>
          <button
            className="memoryexport"
            onClick={exportMemory}
            title={
              language === "ru"
                ? "Экспортировать всю память в Markdown"
                : "Export all memory to Markdown"
            }
          >
            <Download />
            <span>{language === "ru" ? "Экспорт" : "Export"}</span>
          </button>
        </div>
      </header>
      <div className="memoryworkspace">
        <section className="memorycanvas">
          <div className="memoryaurora one" />
          <div className="memoryaurora two" />
          <div className="memoryaurora three" />
          <div className="stars">
            {Array.from({ length: 28 }, (_, i) => (
              <i
                key={i}
                style={{
                  left: `${(i * 37) % 97}%`,
                  top: `${(i * 53) % 89}%`,
                  animationDelay: `${(i % 7) * 0.3}s`,
                }}
              />
            ))}
          </div>
          <svg viewBox="0 0 1000 660" preserveAspectRatio="xMidYMid meet">
            <defs>
              <filter id="glow">
                <feGaussianBlur stdDeviation="5" result="b" />
                <feMerge>
                  <feMergeNode in="b" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <linearGradient id="memoryLine">
                <stop stopColor="#756ff2" />
                <stop offset=".55" stopColor="#4f91d9" />
                <stop offset="1" stopColor="#52d9ae" />
              </linearGradient>
            </defs>
            {positions.map(({ note, x, y }, i) => (
              <g key={note.id}>
                <path
                  className="memorylink"
                  d={`M500 330 Q ${500 + (x - 500) * 0.42 + i * 7} ${330 + (y - 330) * 0.4 - i * 4} ${x} ${y}`}
                />
                <circle className="pulsepacket" r="3">
                  <animateMotion
                    dur={`${3.8 + i * 0.27}s`}
                    repeatCount="indefinite"
                    path={`M500 330 Q ${500 + (x - 500) * 0.42 + i * 7} ${330 + (y - 330) * 0.4 - i * 4} ${x} ${y}`}
                  />
                </circle>
              </g>
            ))}
          </svg>
          {global && (
            <button
              className={`memorynode core ${selected?.id === global.id ? "selected" : ""}`}
              aria-label={
                language === "ru"
                  ? "Открыть основную память"
                  : "Open core memory"
              }
              onPointerDown={() => setSelected(global)}
              onClick={() => setSelected(global)}
            >
              <span>
                <Brain />
              </span>
              <b>{localizedTitle(global)}</b>
              <small>{global.byte_size} bytes</small>
            </button>
          )}
          {positions.map(({ note, x, y }, i) => (
            <button
              key={note.id}
              className={`memorynode dialogue ${selected?.id === note.id ? "selected" : ""}`}
              style={{
                left: `${x / 10}%`,
                top: `${y / 6.6}%`,
                animationDelay: `${i * 0.12}s`,
              }}
              onPointerDown={() => setSelected(note)}
              onClick={() => setSelected(note)}
            >
              <span>
                <MessageSquare />
              </span>
              <b>{localizedTitle(note)}</b>
              <small>{note.byte_size} bytes</small>
            </button>
          ))}
          {hiddenCount > 0 && (
            <div className="memoryarchive">
              +{hiddenCount} {language === "ru" ? "в архиве" : "archived"}
            </div>
          )}
        </section>
        {selected && (
          <aside className="memorynote open">
            <button
              className="memoryclose"
              aria-label={language === "ru" ? "Закрыть" : "Close"}
              onClick={() => {
                setSelected(null);
                setEditing(false);
              }}
            >
              <X />
            </button>
            <div className="notetype">
              {selected.scope === "global"
                ? language === "ru"
                  ? "ОСНОВНАЯ ПАМЯТЬ"
                  : "CORE MEMORY"
                : language === "ru"
                  ? "ПАМЯТЬ ДИАЛОГА"
                  : "DIALOGUE MEMORY"}
            </div>
            <h2>{localizedTitle(selected)}</h2>
            <p className="notesummary">{localizedSummary(selected)}</p>
            {editing ? (
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            ) : (
              <pre>{localizedContent(selected)}</pre>
            )}
            <div className="noteinfo">
              <span>{language === "ru" ? "Размер" : "Size"}</span>
              <b>{selected.byte_size} bytes</b>
              <span>{language === "ru" ? "Связей" : "Links"}</span>
              <b>{selected.links.length || dialogues.length}</b>
            </div>
            <footer>
              {editing ? (
                <>
                  <button onClick={() => setEditing(false)}>
                    {language === "ru" ? "Отмена" : "Cancel"}
                  </button>
                  <button className="primary" onClick={save}>
                    {language === "ru" ? "Сохранить" : "Save"}
                  </button>
                </>
              ) : (
                <button onClick={() => setEditing(true)}>
                  {language === "ru" ? "Редактировать заметку" : "Edit note"}
                </button>
              )}
            </footer>
          </aside>
        )}
      </div>
    </div>
  );
}

function ProjectShell({
  tab,
  go,
  team,
  agents,
  start,
  children,
  language,
}: {
  tab: Screen;
  go: (s: Screen) => void;
  team: Team | null;
  agents: Agent[];
  start: () => void;
  children: React.ReactNode;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  return (
    <div className="projectshell">
      <header className="projecthead">
        <div>
          <p className="eyebrow">TEAM WORKSPACE</p>
          <h2>{team?.name}</h2>
        </div>
        <div className="headmeta">
          <span>
            <Users />
            {agents.length} {ru ? "агентов" : "agents"}
          </span>
          <button className="primary" onClick={() => start()}>
            <Play />
            {ru ? "Начать диалог" : "Start dialogue"}
          </button>
        </div>
      </header>
      <nav className="tabs">
        {(["overview", "team", "run", "tasks"] as Screen[]).map(
          (x) => (
            <button
              key={x}
              title={
                (ru
                  ? {
                      overview: "Общая настройка команды",
                      team: "Роли и инструкции агентов",
                      run: "Текущая переписка пользователя и агентов",
                      tasks: "Внутренние подзадачи, созданные агентами",
                    }
                  : ({
                      overview: "Team overview",
                      team: "Agent roles and instructions",
                      run: "Live user and agent conversation",
                      tasks: "Internal agent subtasks",
                    } as Record<string, string>))[x]
              }
              className={tab === x ? "active" : ""}
              onClick={() => go(x)}
            >
              {
                (ru
                  ? {
                      overview: "Обзор",
                      team: "Агенты",
                      run: "Диалог",
                      tasks: "Задачи",
                    }
                  : ({
                      overview: "Overview",
                      team: "Agents",
                      run: "Dialogue",
                      tasks: "Task flow",
                    } as Record<string, string>))[x]
              }
            </button>
          ),
        )}
      </nav>
      <div className="tabbody">{children}</div>
    </div>
  );
}

function Overview({
  team,
  agents,
  events,
  language,
}: {
  team: Team | null;
  agents: Agent[];
  events: RunEvent[];
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const objective = localizedTeamGoal(team?.goal || "", language);
  return (
    <div className="overview">
      <section className="goalbox">
        <span>TEAM OBJECTIVE</span>
        <h2>{objective}</h2>
        <p>
          {team?.mode === "constructive"
            ? ru
              ? "Сначала агенты готовят вклады, затем reviewer и supervisor критически проверяют и сводят результат."
              : "Agents contribute first; then the reviewer and supervisor critically review and synthesise the result."
            : ru
              ? "В обычном режиме руководитель распределяет работу, специалисты отвечают по очереди, затем команда получает общий вывод. Constructive добавляет независимый стресс-тест."
              : "In Standard mode, the lead assigns work, specialists respond in sequence, and the team produces one conclusion. Constructive adds an independent stress test."}
        </p>
      </section>
      <div className="stats">
        <Stat label="Agents" value={String(agents.length)} />
        <Stat label="Runs" value={events.length ? "1" : "0"} />
        <Stat label="Mode" value={team?.mode || "standard"} />
        <Stat
          label="Max parallel"
          value={String(team?.max_parallel_agents || 3)}
        />
      </div>
      <h3>{ru ? "Команда" : "Team"}</h3>
      <div className="agentcards">
        {agents.map((a, i) => (
          <AgentCard key={a.id} agent={a} color={colors[i % colors.length]} />
        ))}
      </div>
    </div>
  );
}

function SkillsMarketplace({
  language,
  go,
}: {
  language: "ru" | "en";
  go: (screen: Screen) => void;
}) {
  const ru = language === "ru";
  const [query, setQuery] = useState("");
  const catalogSkills = [BUILTIN_BASE_SKILL, ...AGENT_SKILLS];
  const [selectedName, setSelectedName] = useState<string>(BUILTIN_BASE_SKILL.name);
  const filtered = catalogSkills.filter((skill) =>
    `${skill.name} ${skill.descriptionEn} ${skill.descriptionRu} ${SKILL_GUARDRAILS[skill.name]}`
      .toLowerCase()
      .includes(query.trim().toLowerCase()),
  );
  const selected =
    catalogSkills.find((skill) => skill.name === selectedName) ||
    filtered[0] ||
    catalogSkills[0];
  const Icon = SKILL_VISUALS[selected.name]?.icon || Brain;
  const tradingSkills = new Set(AGENT_SKILLS.slice(8).map((skill) => skill.name));
  return (
    <div className="skillmarket page">
      <header className="skillmarket-head">
        <div>
          <p className="eyebrow">SKILL LIBRARY · {catalogSkills.length}</p>
          <PageTitle text={ru ? "Маркет скиллов" : "Skill marketplace"} />
          <p>
            {ru
              ? "Читайте точные границы скилла и назначайте его агенту без скрытых правил."
              : "Read the exact operating contract before assigning a skill to an agent."}
          </p>
        </div>
        <button className="primary" onClick={() => go("team")}>
          <Bot />
          {ru ? "Открыть агентов" : "Open agents"}
        </button>
      </header>
      <div className="skillmarket-toolbar">
        <Search />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={ru ? "Поиск по скиллам" : "Search skills"}
        />
        <span>{filtered.length}/{catalogSkills.length}</span>
      </div>
      <div className="skillmarket-grid">
        <section className="skillmarket-list" aria-label={ru ? "Список скиллов" : "Skill list"}>
          {filtered.map((skill) => {
            const visual = SKILL_VISUALS[skill.name];
            const SkillIcon = visual?.icon || Brain;
            return (
              <button
                key={skill.name}
                className={selected.name === skill.name ? "active" : ""}
                onClick={() => setSelectedName(skill.name)}
              >
                <span
                  className="skillmarket-icon"
                  style={{ background: `linear-gradient(135deg, ${visual?.gradient[0] || "#8ee06a"}, ${visual?.gradient[1] || "#24501a"})` }}
                >
                  <SkillIcon />
                </span>
                <span>
                  <b>{skill.name}</b>
                  <small>{ru ? skill.descriptionRu : skill.descriptionEn}</small>
                </span>
                <i>{skill.name === BUILTIN_BASE_SKILL.name ? "DEFAULT" : tradingSkills.has(skill.name) ? "ON-CHAIN" : "CORE"}</i>
              </button>
            );
          })}
          {filtered.length === 0 && <p className="skillmarket-empty">{ru ? "Ничего не найдено" : "No skills found"}</p>}
        </section>
        <section className="skillmarket-detail">
          <div className="skillmarket-detail-head">
            <span className="skillmarket-icon large"><Icon /></span>
            <div>
              <p className="eyebrow">{selected.name === BUILTIN_BASE_SKILL.name ? "DEFAULT FOR EVERY AGENT" : tradingSkills.has(selected.name) ? "ON-CHAIN SIGNAL ROOM" : "ORBIT CORE"}</p>
              <h2>{selected.name}</h2>
              <p>{ru ? selected.descriptionRu : selected.descriptionEn}</p>
            </div>
          </div>
          <div className="skillmarket-contract">
            <span className="eyebrow">{ru ? "ОПЕРАЦИОННЫЙ КОНТРАК" : "OPERATING CONTRACT"}</span>
            <p>{skillContract(selected.name)}</p>
          </div>
          <div className="skillmarket-prompt">
            <span className="eyebrow">{ru ? "ПОЛНАЯ ИНСТРУКЦИЯ" : "FULL INSTRUCTION"}</span>
            <pre>{selected.name === BUILTIN_BASE_SKILL.name ? fullBuiltinSkillPrompt() : fullSkillPrompt(selected as (typeof AGENT_SKILLS)[number])}</pre>
          </div>
          <div className="skillmarket-actions">
            <span>
              {selected.name === BUILTIN_BASE_SKILL.name ? (ru ? "Включён у новых и существующих агентов по умолчанию. Выключается в карточке агента." : "Enabled for new and existing agents by default. Disable it from an agent card.") : (ru ? "Назначьте скилл в карточке агента → Choose skill" : "Assign it from an agent card → Choose skill")}
              {selected.name === BUILTIN_BASE_SKILL.name && <a className="skillmarket-source" href={BUILTIN_BASE_SKILL.source} target="_blank" rel="noreferrer">GitHub · MIT ↗</a>}
            </span>
            <button onClick={() => go("team")}><Bot /> {ru ? "Назначить агенту" : "Assign to an agent"}</button>
          </div>
        </section>
      </div>
    </div>
  );
}

function localizedTeamGoal(goal: string, language: "ru" | "en"): string {
  if (language === "ru" || !/[А-Яа-яЁё]/.test(goal)) return goal;
  if (goal.includes("Подготовить безопасный план миграции streaming-платформы")) {
    return "Prepare a safe streaming-platform migration plan";
  }
  // Do not leak an arbitrary user-authored Cyrillic string into an English UI.
  return "Define a verifiable team objective";
}
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}
function playChime() {
  const AudioContextClass =
    window.AudioContext ||
    (window as typeof window & { webkitAudioContext?: typeof AudioContext })
      .webkitAudioContext;
  if (!AudioContextClass) return;
  const audio = new AudioContextClass();
  const gain = audio.createGain();
  gain.gain.setValueAtTime(0.0001, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.11, audio.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.55);
  gain.connect(audio.destination);
  [523.25, 659.25].forEach((frequency, index) => {
    const oscillator = audio.createOscillator();
    oscillator.frequency.value = frequency;
    oscillator.connect(gain);
    oscillator.start(audio.currentTime + index * 0.09);
    oscillator.stop(audio.currentTime + 0.6);
  });
  setTimeout(() => audio.close(), 800);
}
function ProfilePage({
  user,
  workspace,
  language,
  setError,
  onUserChanged,
  onSignedOut,
}: {
  user: OrbitUser;
  workspace: Workspace | null;
  language: "ru" | "en";
  setError: (value: string) => void;
  onUserChanged: (value: OrbitUser) => void;
  onSignedOut: () => void;
}) {
  const ru = language === "ru";
  const [connections, setConnections] = useState<Connection[]>([]);
  const [capabilities, setCapabilities] = useState<DeploymentCapabilities | null>(null);
  const [connectOpen, setConnectOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [twitterOAuthStatus] = useState(() =>
    new URLSearchParams(location.search).get("twitter_oauth"),
  );
  const [sessions, setSessions] = useState<
    Array<{
      id: string;
      created_at: string;
      expires_at: string;
      current: boolean;
    }>
  >([]);
  const [displayName, setDisplayName] = useState(user.display_name);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (workspace)
      api
        .connections(workspace.id)
        .then(setConnections)
        .catch((error) => setError(error.message));
  }, [workspace, setError]);
  useEffect(() => {
    api.capabilities().then(setCapabilities).catch(() => setCapabilities(null));
  }, []);
  useEffect(() => {
    if (twitterOAuthStatus) history.replaceState({}, "", location.pathname);
  }, [twitterOAuthStatus]);
  useEffect(() => {
    if (AUTH_REQUIRED)
      api
        .authSessions()
        .then(setSessions)
        .catch((error) => setError(error.message));
  }, [setError]);
  const twitter = connections.find((item) => item.provider === "twitter");
  const twitterAvailable = capabilities?.connectors.twitter !== false;
  const xProfile = (twitter?.config.profile || {}) as Record<string, unknown>;
  const xMetrics = (xProfile.public_metrics || {}) as Record<string, unknown>;
  async function connect() {
    if (!workspace || busy) return;
    setBusy(true);
    try {
      const result = await api.startTwitterOAuth(workspace.id);
      location.assign(result.authorization_url);
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }
  async function saveAccount() {
    if (busy || !displayName.trim()) return;
    setBusy(true);
    setSaved(false);
    try {
      const updated = await api.updateMe({
        display_name: displayName.trim(),
        ...(newPassword
          ? { current_password: currentPassword, new_password: newPassword }
          : {}),
      });
      onUserChanged(updated);
      setCurrentPassword("");
      setNewPassword("");
      setSaved(true);
      if (newPassword) {
        localStorage.removeItem("orbit-auth-token");
        onSignedOut();
      }
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    try {
      await api.revokeSession(id);
      setSessions((old) => old.filter((item) => item.id !== id));
    } catch (error) {
      setError((error as Error).message);
    }
  }
  async function signOut() {
    try {
      await api.logout();
    } finally {
      localStorage.removeItem("orbit-auth-token");
      onSignedOut();
    }
  }
  async function removeAccount() {
    if (!deletePassword || busy) return;
    setBusy(true);
    try {
      await api.deleteAccount(deletePassword);
      localStorage.removeItem("orbit-auth-token");
      onSignedOut();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="profilepage page">
      {twitterOAuthStatus && (
        <div
          className={`oauthresult ${twitterOAuthStatus === "success" ? "success" : "error"}`}
        >
          {twitterOAuthStatus === "success" ? <Check /> : <AlertTriangle />}
          <div>
            <b>
              {twitterOAuthStatus === "success"
                ? ru
                  ? "Аккаунт X подключён"
                  : "X account connected"
                : ru
                  ? "Не удалось подключить X"
                  : "X connection was not completed"}
            </b>
            <p>
              {twitterOAuthStatus === "success"
                ? ru
                  ? "Профиль подключён и доступен команде как источник контекста."
                  : "Your profile is connected and available to the team as context."
                : ru
                  ? "Повторите вход и подтвердите запрошенный доступ на стороне X."
                  : "Try again and approve the requested access on X."}
            </p>
          </div>
        </div>
      )}
      <header className="profilehero">
        <div>
          <p className="eyebrow">IDENTITY & CREATOR NETWORK</p>
          <h1>{ru ? "Ваш профиль" : "Your profile"}</h1>
          <p>
            {ru
              ? "Управляйте личными источниками, которые помогают агентам понимать ваш опыт, аудиторию и контент."
              : "Manage personal sources that help agents understand your experience, audience, and content."}
          </p>
        </div>
        <div className="profileidentity">
          <span>{initials(user.display_name)}</span>
          <div>
            <b>{user.display_name}</b>
            <small>{user.email}</small>
          </div>
          <i>{ru ? "Владелец" : "Owner"}</i>
        </div>
      </header>
      <div className="profilegrid">
        <section className={`xprofilecard ${twitter ? "connected" : ""} ${!twitterAvailable ? "unavailable" : ""}`}>
          <header>
            <div className="xmark">
              <TwitterMark />
            </div>
            <div>
              <p className="eyebrow">CONNECTED ACCOUNT</p>
              <h2>X / Twitter</h2>
            </div>
            <span className={`status ${twitter ? "ready" : ""}`}>
              {twitter
                ? ru
                  ? "Подключён"
                  : "Connected"
                : !twitterAvailable
                  ? ru
                    ? "Нужна настройка"
                    : "Setup required"
                : ru
                  ? "Не подключён"
                  : "Not connected"}
            </span>
          </header>
          {twitter ? (
            <div className="xconnected">
              <div className="xavatar">
                {initials(String(xProfile.name || xProfile.username || "X"))}
              </div>
              <div className="xaccount">
                <b>{String(xProfile.name || twitter.name)}</b>
                <a
                  href={`https://x.com/${String(xProfile.username || "")}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  @{String(xProfile.username || "")}
                </a>
                <p>{String(xProfile.description || "")}</p>
              </div>
              <div className="xmetrics">
                <span>
                  <b>
                    {Number(xMetrics.followers_count || 0).toLocaleString()}
                  </b>
                  <small>{ru ? "подписчиков" : "followers"}</small>
                </span>
                <span>
                  <b>{Number(xMetrics.tweet_count || 0).toLocaleString()}</b>
                  <small>{ru ? "публикаций" : "posts"}</small>
                </span>
                <span>
                  <b>{Number(twitter.config.posts_count || 0)}</b>
                  <small>{ru ? "в Memory" : "in Memory"}</small>
                </span>
              </div>
            </div>
          ) : (
            <div className="xempty">
              <AtSign />
              <div>
                <b>
                  {!twitterAvailable
                    ? ru
                      ? "X OAuth ещё не настроен на этом сервере"
                      : "X OAuth has not been configured on this deployment"
                    : ru
                    ? "Подключите свой авторский профиль"
                    : "Connect your creator account"}
                </b>
                <p>
                  {!twitterAvailable
                    ? ru
                      ? "Нужны Client ID, Client Secret и callback URL из X Developer Portal. После настройки кнопка автоматически станет активной."
                      : "This deployment needs an X Client ID, Client Secret, and callback URL from the X Developer Portal. The button becomes available automatically after setup."
                    : ru
                    ? "Orbit проверит аккаунт, прочитает публичные метрики и добавит последние публикации в общую память команды."
                    : "Orbit verifies the account, reads public metrics, and adds recent posts to the team's shared memory."}
                </p>
              </div>
            </div>
          )}
          <footer>
            <div className="xscopes">
              <ShieldCheck />
              <span>
                {ru
                  ? "Только чтение · users.read + tweet.read"
                  : "Read only · users.read + tweet.read"}
              </span>
            </div>
            <button
              className={twitter ? "" : "primary"}
              disabled={!twitterAvailable}
              title={!twitterAvailable ? (ru ? "X OAuth не настроен на сервере" : "X OAuth is not configured on this server") : undefined}
              onClick={() => setConnectOpen(true)}
            >
              <TwitterMark />
              {twitter
                ? ru
                  ? "Переподключить"
                  : "Reconnect"
                : ru
                  ? "Подключить X"
                  : "Connect X"}
            </button>
          </footer>
        </section>
        <section className="ambassadorcard">
          <div className="ambassadorhalo" />
          <header>
            <span>
              <Megaphone />
            </span>
            <i>COMING SOON</i>
          </header>
          <div>
            <p className="eyebrow">ORBIT CREATOR NETWORK</p>
            <h2>{ru ? "Амбассадорская кампания" : "Ambassador campaign"}</h2>
            <p>
              {ru
                ? "Будущая программа для авторов и команд, которые показывают реальные сценарии работы AI-агентов, делятся шаблонами и помогают развивать Orbit."
                : "A future program for creators and teams who share real agent workflows, publish templates, and help Orbit grow."}
            </p>
          </div>
          <ul>
            <li>
              <Check />
              {ru
                ? "Персональные реферальные ссылки"
                : "Personal referral links"}
            </li>
            <li>
              <Check />
              {ru
                ? "Награды за кейсы и шаблоны"
                : "Rewards for cases and templates"}
            </li>
            <li>
              <Check />
              {ru
                ? "Ранний доступ к новым функциям"
                : "Early access to new features"}
            </li>
          </ul>
          <button disabled>
            <Sparkles />
            {ru ? "В разработке" : "In development"}
          </button>
        </section>
      </div>
      {AUTH_REQUIRED && (
        <section className="walletcard">
          <div>
            <p className="eyebrow">{ru ? "КОШЕЛЁК" : "WALLET"}</p>
            <h3>{user.wallet_address ? shortAddress(user.wallet_address) : ru ? "Кошелёк не подключён" : "No wallet connected"}</h3>
            <p>
              {user.wallet_address
                ? ru
                  ? "Кошелёк привязан к этому аккаунту, повышенный лимит использования включён. Мы видим только адрес."
                  : "The wallet is linked to this account and the higher usage limit is on. We only see the address."
                : ru
                  ? "Подключите кошелёк (MetaMask, WalletConnect и другие), чтобы получить повышенный лимит использования. Подпись бесплатна и не даёт доступа к средствам."
                  : "Connect a wallet (MetaMask, WalletConnect and others) to get a higher usage limit. Signing is free and gives no access to your funds."}
            </p>
          </div>
          {user.wallet_address ? (
            !user.email.endsWith("@wallet.orbit") && (
              <button
                className="ghost"
                onClick={() => api.unlinkWallet().then((value) => onUserChanged({ ...user, ...value })).catch((error) => setError((error as Error).message))}
              >
                {ru ? "Отключить" : "Disconnect"}
              </button>
            )
          ) : (
            <button className="primary" onClick={openWalletDialog}><Wallet /> {ru ? "Подключить кошелёк" : "Connect wallet"}</button>
          )}
        </section>
      )}
      {AUTH_REQUIRED && user.is_guest && (
        <section className="walletcard">
          <div>
            <h3>{ru ? "Вы в гостевом режиме" : "You are browsing as a guest"}</h3>
            <p>
              {ru
                ? "Данные хранятся в этом браузере. Уже есть аккаунт с email? Войдите, чтобы вернуться к нему."
                : "Your data is kept for this browser. Already have an email account? Sign in to go back to it."}
            </p>
          </div>
          <a className="ghost" href="/?signin=1">{ru ? "Войти по email" : "Sign in with email"}</a>
        </section>
      )}
      {AUTH_REQUIRED && !user.is_guest && (
        <section className="accountsecurity">
          <header>
            <div>
              <p className="eyebrow">ACCOUNT SECURITY</p>
              <h2>
                {ru
                  ? "Аккаунт и активные сессии"
                  : "Account and active sessions"}
              </h2>
            </div>
            {saved && (
              <span>
                <Check />
                {ru ? "Сохранено" : "Saved"}
              </span>
            )}
          </header>
          <div className="accountfields">
            <LabelInput
              label={ru ? "Отображаемое имя" : "Display name"}
              value={displayName}
              set={setDisplayName}
            />
            <LabelInput
              label={ru ? "Текущий пароль" : "Current password"}
              value={currentPassword}
              set={setCurrentPassword}
              secret
            />
            <LabelInput
              label={ru ? "Новый пароль" : "New password"}
              value={newPassword}
              set={setNewPassword}
              secret
            />
            <button
              className="primary"
              disabled={
                busy ||
                !displayName.trim() ||
                (Boolean(newPassword) &&
                  (!currentPassword || newPassword.length < 10))
              }
              onClick={saveAccount}
            >
              {ru ? "Сохранить профиль" : "Save profile"}
            </button>
          </div>
          <div className="sessionlist">
            <b>{ru ? "Входы в аккаунт" : "Signed-in sessions"}</b>
            {sessions.map((item) => (
              <article key={item.id}>
                <ShieldCheck />
                <div>
                  <b>
                    {item.current
                      ? ru
                        ? "Эта сессия"
                        : "This session"
                      : ru
                        ? "Другая сессия"
                        : "Another session"}
                  </b>
                  <small>
                    {new Date(item.created_at).toLocaleString(
                      ru ? "ru-RU" : "en-US",
                    )}{" "}
                    · {ru ? "до" : "until"}{" "}
                    {new Date(item.expires_at).toLocaleDateString(
                      ru ? "ru-RU" : "en-US",
                    )}
                  </small>
                </div>
                {item.current ? (
                  <button onClick={signOut}>{ru ? "Выйти" : "Sign out"}</button>
                ) : (
                  <button onClick={() => revoke(item.id)}>
                    {ru ? "Завершить" : "Revoke"}
                  </button>
                )}
              </article>
            ))}
          </div>
          <button className="dangerlink" onClick={() => setDeleteOpen(true)}>
            <Trash2 />
            {ru
              ? "Удалить аккаунт и личное пространство"
              : "Delete account and personal workspace"}
          </button>
        </section>
      )}
      {connectOpen && (
        <div
          className="modalback"
          onClick={() => !busy && setConnectOpen(false)}
        >
          <div
            className="modal twittermodal oauthmodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">X OAUTH 2.0 · PKCE</p>
                <h2>{ru ? "Войти через X" : "Continue with X"}</h2>
              </div>
              <button disabled={busy} onClick={() => setConnectOpen(false)}>
                <X />
              </button>
            </header>
            <div className="twitterintro">
              <TwitterMark />
              <div>
                <b>
                  {ru
                    ? "Авторизация проходит на стороне X"
                    : "Authorization happens on X"}
                </b>
                <p>
                  {ru
                    ? "Orbit перенаправит вас на X. Войдите в свой аккаунт и подтвердите доступ — пароли и токены вручную вводить не нужно."
                    : "Orbit redirects you to X. Sign in and approve access—no passwords or access tokens are entered in Orbit."}
                </p>
              </div>
            </div>
            <div className="oauthpermissions">
              <p className="eyebrow">
                {ru ? "ЗАПРАШИВАЕМЫЙ ДОСТУП" : "REQUESTED ACCESS"}
              </p>
              <div>
                <ShieldCheck />
                <span>
                  <b>
                    {ru
                      ? "Только чтение профиля и публикаций"
                      : "Read-only profile and posts"}
                  </b>
                  <small>users.read · tweet.read</small>
                </span>
              </div>
              <div>
                <RotateCcw />
                <span>
                  <b>{ru ? "Оставаться подключённым" : "Stay connected"}</b>
                  <small>
                    offline.access ·{" "}
                    {ru ? "можно отозвать в X" : "revocable in X"}
                  </small>
                </span>
              </div>
            </div>
            <p className="oauthprivacy">
              {ru
                ? "После подтверждения X вернёт вас в Orbit, а доступ будет сохранён в зашифрованном виде."
                : "After approval, X returns you to Orbit and the credentials are stored encrypted."}
            </p>
            <footer>
              <button disabled={busy} onClick={() => setConnectOpen(false)}>
                {ru ? "Отмена" : "Cancel"}
              </button>
              <button
                className="primary xoauthbutton"
                disabled={busy}
                onClick={connect}
              >
                {busy ? (
                  <>
                    <Activity />
                    {ru ? "Открываем X…" : "Opening X…"}
                  </>
                ) : (
                  <>
                    <TwitterMark />
                    {ru ? "Продолжить через X" : "Continue with X"}
                  </>
                )}
              </button>
            </footer>
          </div>
        </div>
      )}
      {deleteOpen && (
        <div
          className="modalback"
          onClick={() => !busy && setDeleteOpen(false)}
        >
          <div
            className="modal deletemodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">IRREVERSIBLE ACTION</p>
                <h2>{ru ? "Удалить аккаунт?" : "Delete account?"}</h2>
              </div>
              <button onClick={() => setDeleteOpen(false)}>
                <X />
              </button>
            </header>
            <p>
              {ru
                ? "Личное пространство, диалоги, память, файлы и подключения будут удалены без возможности восстановления."
                : "Your personal workspace, dialogues, memory, files, and connections will be permanently deleted."}
            </p>
            <LabelInput
              label={ru ? "Подтвердите паролем" : "Confirm with password"}
              value={deletePassword}
              set={setDeletePassword}
              secret
            />
            <footer>
              <button onClick={() => setDeleteOpen(false)}>
                {ru ? "Отмена" : "Cancel"}
              </button>
              <button
                className="danger"
                disabled={busy || !deletePassword}
                onClick={removeAccount}
              >
                <Trash2 />
                {ru ? "Удалить навсегда" : "Delete permanently"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function AppearanceSettingsPage({
  value,
  set,
}: {
  value: AppearanceSettings;
  set: (value: AppearanceSettings) => void;
}) {
  const update = <K extends keyof AppearanceSettings>(
    key: K,
    next: AppearanceSettings[K],
  ) => set({ ...value, [key]: next });
  const ru = value.language === "ru";
  return (
    <div className="appearancepage page">
      <header>
        <div>
          <p className="eyebrow">PERSONALIZATION</p>
          <h1>{ru ? "Настройки" : "Settings"}</h1>
          <p>
            {ru
              ? "Настройте язык, тему и уведомления. Изменения сохраняются на этом устройстве."
              : "Configure language, theme, and notifications. Changes are saved on this device."}
          </p>
        </div>
      </header>
      <section>
        <h2>{ru ? "Язык интерфейса" : "Interface language"}</h2>
        <div className="appearancerow language-row">
          <span>
            <Globe2 />
            <div>
              <b>{ru ? "Язык" : "Language"}</b>
              <small>
                {ru
                  ? "Переключает навигацию и ключевые экраны Orbit"
                  : "Switches Orbit navigation and key screens"}
              </small>
            </div>
          </span>
          <div className="segment">
            <button
              className={value.language === "ru" ? "active" : ""}
              onClick={() => update("language", "ru")}
            >
              Русский
            </button>
            <button
              className={value.language === "en" ? "active" : ""}
              onClick={() => update("language", "en")}
            >
              English
            </button>
          </div>
        </div>
      </section>
      <section>
        <h2>{ru ? "Цветовая тема" : "Color theme"}</h2>
        <div className="themechoices">
          {(["midnight", "aurora", "warm"] as const).map((theme) => (
            <button
              key={theme}
              className={value.theme === theme ? "active" : ""}
              onClick={() => update("theme", theme)}
            >
              <i className={theme} />
              <b>
                {theme === "midnight"
                  ? "Midnight"
                  : theme === "aurora"
                    ? "Aurora"
                    : "Warm studio"}
              </b>
              <small>
                {theme === "midnight"
                  ? ru
                    ? "Глубокий графит"
                    : "Deep graphite"
                  : theme === "aurora"
                    ? ru
                      ? "Холодное сияние"
                      : "Cool glow"
                    : ru
                      ? "Тёплая мастерская"
                      : "Warm workshop"}
              </small>
              {value.theme === theme && <Check />}
            </button>
          ))}
        </div>
      </section>
      <section>
        <h2>{ru ? "Уведомления" : "Notifications"}</h2>
        <div className="appearancerow">
          <span>
            {value.sounds ? <Volume2 /> : <VolumeX />}
            <div>
              <b>{ru ? "Звуки событий" : "Event sounds"}</b>
              <small>
                {ru
                  ? "Короткий сигнал после завершения работы"
                  : "A short signal when work is completed"}
              </small>
            </div>
          </span>
          <div className="soundactions">
            <button onClick={playChime}>{ru ? "Проверить" : "Test"}</button>
            <button
              className={`switch ${value.sounds ? "on" : ""}`}
              aria-label={ru ? "Звуки событий" : "Event sounds"}
              onClick={() => update("sounds", !value.sounds)}
            >
              <i />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
function AgentCard({
  agent,
  color,
  selected,
  onClick,
}: {
  agent: Agent;
  color: string;
  selected?: boolean;
  onClick?: () => void;
}) {
  return (
    <article
      className={`agentcard ${selected ? "selected" : ""}`}
      onClick={onClick}
    >
      <AgentGlyph name={agent.name} skillName={agent.skill_name} color={color} />
      <div>
        <b>{agent.name}</b>
        <small>{agent.role}</small>
      </div>
      <span className="model">{agent.model}</span>
    </article>
  );
}

function TeamBuilder({
  agents,
  team,
  workspace,
  onAdded,
  onUpdated,
  onDeleted,
  setError,
  language,
}: {
  agents: Agent[];
  team: Team | null;
  workspace: Workspace | null;
  onAdded: (a: Agent) => void;
  onUpdated: (a: Agent) => void;
  onDeleted: (agentId: string) => void;
  setError: (s: string) => void;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const [selected, setSelected] = useState(agents[0]?.id);
  const agent = agents.find((a) => a.id === selected) || agents[0];
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [goal, setGoal] = useState("");
  const [agentProvider, setAgentProvider] = useState("mock");
  const [agentApiKey, setAgentApiKey] = useState("");
  const [agentModel, setAgentModel] = useState("mock-model");
  const [agentBaseUrl, setAgentBaseUrl] = useState("");
  const [agentStep, setAgentStep] = useState<"details" | "provider" | "model">(
    "details",
  );
  const [discovering, setDiscovering] = useState(false);
  const [discoveredModels, setDiscoveredModels] = useState<DiscoveredModel[]>(
    [],
  );
  const [providerSearch, setProviderSearch] = useState("");
  const [modelSearch, setModelSearch] = useState("");
  const [discoveryMeta, setDiscoveryMeta] = useState<{
    count: number;
    latency: number;
  } | null>(null);
  const [agentDiscoveryError, setAgentDiscoveryError] = useState("");
  const [googleProjectId, setGoogleProjectId] = useState("");
  const [modelConnections, setModelConnections] = useState<Connection[]>([]);
  const [modelDraftConnectionId, setModelDraftConnectionId] = useState("");
  const [modelDraft, setModelDraft] = useState("mock-model");
  const [modelSaving, setModelSaving] = useState(false);
  const [modelError, setModelError] = useState("");
  const [savedConnectionId, setSavedConnectionId] = useState<string | null>(
    null,
  );
  const [skillOpen, setSkillOpen] = useState(false);
  const [skillName, setSkillName] = useState("");
  const [skillDescription, setSkillDescription] = useState("");
  const [skillPrompt, setSkillPrompt] = useState("");
  const [templateOpen, setTemplateOpen] = useState(false);
  const [templateBusy, setTemplateBusy] = useState(false);
  async function removeAgent() {
    if (!agent) return;
    const confirmed = window.confirm(
      ru
        ? `Удалить агента «${agent.name}»? Его настройки и членство в командах будут удалены.`
        : `Delete ${agent.name}? Its settings and team memberships will be removed.`,
    );
    if (!confirmed) return;
    try {
      await api.deleteAgent(agent.id);
      const remaining = agents.filter((item) => item.id !== agent.id);
      onDeleted(agent.id);
      setSelected(remaining[0]?.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (!workspace) return;
    api.connections(workspace.id)
      .then((connections) => {
        const modelItems = connections.filter(
          (item) =>
            item.provider === "openai" ||
            item.provider === "openai-compatible" ||
            item.provider === "anthropic" ||
            item.provider === "gemini-oauth",
        );
        setModelConnections(modelItems);
        const oauthStatus = new URLSearchParams(location.search).get(
          "gemini_oauth",
        );
        if (oauthStatus === "success") {
          try {
            const draft = JSON.parse(
              sessionStorage.getItem("orbit-agent-oauth-draft") || "{}",
            );
            setName(String(draft.name || ""));
            setRole(String(draft.role || ""));
            setGoal(String(draft.goal || ""));
          } catch {
            /* ignore invalid local draft */
          }
          const connection = modelItems.find(
            (item) => item.provider === "gemini-oauth",
          );
          if (connection) {
            const models = (
              (connection.config.available_models || []) as string[]
            ).map((id) => ({
              id,
              name: id,
              owner: "Google",
              context_length: null,
            }));
            setAdding(true);
            setSavedConnectionId(connection.id);
            setAgentProvider("gemini");
            setAgentBaseUrl(connection.base_url || "");
            setDiscoveredModels(models);
            setDiscoveryMeta({ count: models.length, latency: 0 });
            setAgentStep("model");
          }
        } else if (oauthStatus) {
          setError(
            ru
              ? "Не удалось подключить Google-аккаунт. Проверьте Cloud project и разрешения OAuth."
              : "Google account connection failed. Check the Cloud project and OAuth permissions.",
          );
        }
        if (oauthStatus) {
          sessionStorage.removeItem("orbit-agent-oauth-draft");
          history.replaceState({}, "", location.pathname);
        }
      })
      .catch(() => {});
  }, [workspace]); // eslint-disable-line react-hooks/exhaustive-deps
  const selectedAgentId = agent?.id;
  const selectedAgentConnectionId = agent?.connection_id;
  const selectedAgentModel = agent?.model;
  useEffect(() => {
    if (!selectedAgentId) return;
    setModelDraftConnectionId(selectedAgentConnectionId || "");
    setModelDraft(selectedAgentModel || "mock-model");
    setModelError("");
  }, [selectedAgentId, selectedAgentConnectionId, selectedAgentModel]);
  function connectionModels(connectionId: string): string[] {
    const connection = modelConnections.find((item) => item.id === connectionId);
    if (!connection) return [];
    return connectionModelIds(connection.config);
  }
  async function saveAgentModel() {
    if (!agent || modelSaving) return;
    const nextModel = modelDraft.trim() || "mock-model";
    setModelSaving(true);
    setModelError("");
    try {
      const value = await api.updateAgent(agent.id, {
        connection_id: modelDraftConnectionId || null,
        model: nextModel,
      });
      onUpdated(value);
      setModelDraft(value.model);
      setModelDraftConnectionId(value.connection_id || "");
    } catch (e) {
      setModelError((e as Error).message);
    } finally {
      setModelSaving(false);
    }
  }
  function openSkill() {
    setSkillName(agent?.skill_name || "");
    setSkillDescription(agent?.skill_description || "");
    setSkillPrompt(agent?.skill_prompt || "");
    setSkillOpen(true);
  }
  function chooseSkill(skill: (typeof AGENT_SKILLS)[number]) {
    setSkillName(skill.name);
    setSkillDescription(ru ? skill.descriptionRu : skill.descriptionEn);
    setSkillPrompt(fullSkillPrompt(skill));
  }
  async function saveSkill() {
    if (!agent) return;
    try {
      const value = await api.updateAgent(agent.id, {
        skill_name: skillName.trim() || null,
        skill_description: skillName.trim()
          ? skillDescription.trim() || null
          : null,
        skill_prompt: skillName.trim() ? skillPrompt.trim() || null : null,
      });
      onUpdated(value);
      setSkillOpen(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function toggleBuiltinSkill() {
    if (!agent) return;
    try {
      onUpdated(
        await api.updateAgent(agent.id, {
          adhd_skill_enabled: agent.adhd_skill_enabled === false,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function resetAgentWizard() {
    setName("");
    setRole("");
    setGoal("");
    setAgentProvider("mock");
    setAgentApiKey("");
    setAgentModel("mock-model");
    setAgentBaseUrl("");
    setAgentStep("details");
    setDiscoveredModels([]);
    setProviderSearch("");
    setModelSearch("");
    setDiscoveryMeta(null);
    setAgentDiscoveryError("");
    setDiscovering(false);
    setSavedConnectionId(null);
    setGoogleProjectId("");
  }
  function openAgentWizard() {
    resetAgentWizard();
    setAdding(true);
  }
  function closeAgentWizard() {
    if (discovering) return;
    setAdding(false);
    resetAgentWizard();
  }
  async function applyTemplate(template: (typeof TEAM_TEMPLATES)[number]) {
    if (!workspace || !team) return;
    setTemplateBusy(true);
    setTemplateOpen(false);
    try {
      for (const tpl of template.agents) {
        const slug = `${tpl.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Date.now().toString().slice(-4)}`;
        const skill = AGENT_SKILLS.find((s) => s.name === tpl.skillName);
        const created = await api.createAgent({
          workspace_id: workspace.id,
          connection_id: null,
          name: tpl.name,
          slug,
          role: tpl.role,
          goal: ru ? tpl.goalRu : tpl.goalEn,
          system_prompt: ru ? tpl.systemRu : tpl.systemEn,
          model: "mock-model",
          skill_name: skill?.name ?? null,
          skill_description: skill ? (ru ? skill.descriptionRu : skill.descriptionEn) : null,
          skill_prompt: skill ? fullSkillPrompt(skill) : null,
        });
        await api.addTeamAgent(team.id, created.id);
        onAdded(created);
        setSelected(created.id);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setTemplateBusy(false);
    }
  }
  async function addAgent() {
    if (
      !workspace ||
      !team ||
      !name.trim() ||
      !role.trim() ||
      !agentModel.trim()
    )
      return;
    try {
      const preset = PROVIDERS.find((item) => item.id === agentProvider);
      let connectionId: string | null = savedConnectionId;
      if (!connectionId && agentProvider !== "mock" && preset) {
        if (!agentApiKey.trim() && !preset.local && preset.id !== "custom") {
          setError(
            ru
              ? "Введите API key выбранного провайдера"
              : "Enter the selected provider API key",
          );
          return;
        }
        const connection = await api.createConnection({
          workspace_id: workspace.id,
          name: `${name.trim()} · ${preset.name}`,
          provider:
            preset.protocol === "anthropic" ? "anthropic" : "openai-compatible",
          base_url: normalizeProviderBaseUrl(agentBaseUrl),
          api_key: agentApiKey.trim() || null,
          config: {
            preset: preset.id,
            available_models: discoveredModels.map((item) => item.id),
            active_models: [agentModel.trim()],
          },
        });
        connectionId = connection.id;
        setModelConnections((old) => [
          connection,
          ...old.filter((item) => item.id !== connection.id),
        ]);
      }
      const slug = `${
        name
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "") || "agent"
      }-${Date.now().toString().slice(-4)}`;
      const value = await api.createAgent({
        workspace_id: workspace.id,
        connection_id: connectionId,
        name,
        slug,
        role,
        goal: goal || (ru ? `Работать как ${role}` : `Work as ${role}`),
        system_prompt: ru
          ? `Ты ${role} в команде AI-агентов.`
          : `You are the ${role} in an AI agent team.`,
        model: agentModel.trim(),
      });
      await api.addTeamAgent(team.id, value.id);
      onAdded(value);
      setSelected(value.id);
      setAdding(false);
      resetAgentWizard();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function changeAgentProvider(id: string) {
    const preset = PROVIDERS.find((item) => item.id === id);
    setSavedConnectionId(null);
    setAgentProvider(id);
    setAgentApiKey("");
    setAgentBaseUrl(preset?.baseUrl || "");
    setAgentModel(id === "mock" ? "mock-model" : preset?.defaultModel || "");
    setDiscoveredModels([]);
    setDiscoveryMeta(null);
    setAgentDiscoveryError("");
  }
  function reuseConnection(connection: Connection) {
    const models = connectionModelIds(connection.config).map((id) => ({
      id,
      name: id,
      owner: String(connection.config.preset || connection.provider),
      context_length: null,
    }));
    setSavedConnectionId(connection.id);
    setAgentProvider(String(connection.config.preset || connection.provider));
    setAgentBaseUrl(connection.base_url || "");
    setAgentApiKey("");
    setDiscoveredModels(models);
    setAgentModel(models.length === 1 ? models[0].id : "");
    setDiscoveryMeta({ count: models.length, latency: 0 });
    setAgentStep("model");
  }
  async function discoverAgentModels() {
    const preset = PROVIDERS.find((item) => item.id === agentProvider);
    if (agentProvider === "mock") {
      setDiscoveredModels([
        {
          id: "mock-model",
          name: "Mock Model",
          owner: "Orbit",
          context_length: null,
        },
      ]);
      setAgentModel("mock-model");
      setDiscoveryMeta({ count: 1, latency: 0 });
      setAgentStep("model");
      return;
    }
    if (
      !preset ||
      !agentBaseUrl.trim() ||
      (!preset.local && preset.id !== "custom" && !agentApiKey.trim())
    ) {
      setAgentDiscoveryError(
        ru
          ? "Укажите endpoint и API key для проверки."
          : "Enter the endpoint and API key before testing.",
      );
      return;
    }
    const normalizedBaseUrl = normalizeProviderBaseUrl(agentBaseUrl);
    setAgentBaseUrl(normalizedBaseUrl);
    setAgentDiscoveryError("");
    setDiscovering(true);
    try {
      const result = await api.discoverConnection({
        provider: agentProvider === "tabitoken"
          ? "tabitoken"
          : preset.protocol === "anthropic"
            ? "anthropic"
            : "openai-compatible",
        base_url: normalizedBaseUrl,
        api_key: agentApiKey.trim(),
      });
      if (result.base_url) setAgentBaseUrl(result.base_url);
      const defaultModel = preset.defaultModel;
      const models = defaultModel
        ? [{ id: defaultModel, name: "Free Models Router", owner: preset.name, context_length: null }]
        : result.models;
      setDiscoveredModels(models);
      setAgentModel(
        defaultModel || (models.length === 1 ? models[0].id : ""),
      );
      setDiscoveryMeta({
        count: models.length,
        latency: result.latency_ms,
      });
      setAgentStep("model");
    } catch (e) {
      const message = (e as Error).message;
      setAgentDiscoveryError(
        ru
          ? message.replace(
              "Connection check failed:",
              "Проверка подключения не пройдена:",
            )
          : message,
      );
    } finally {
      setDiscovering(false);
    }
  }
  async function connectGeminiAccount() {
    if (!workspace || !googleProjectId.trim()) return;
    setDiscovering(true);
    try {
      sessionStorage.setItem(
        "orbit-agent-oauth-draft",
        JSON.stringify({ name, role, goal }),
      );
      const value = await api.startGoogleModelOAuth(
        workspace.id,
        googleProjectId.trim(),
      );
      location.assign(value.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setDiscovering(false);
    }
  }
  return (
    <div className="builder">
      <aside className="builderside">
        <div className="sectiontitle">
          <span>AGENTS · {agents.length}/{MAX_TEAM_SIZE}</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button
              title={ru ? "Из шаблона" : "From template"}
              onClick={() => setTemplateOpen(true)}
              disabled={templateBusy || agents.length >= MAX_TEAM_SIZE}
              style={{ fontSize: 11, padding: "2px 7px" }}
            >
              {templateBusy ? <Activity /> : (ru ? "Шаблон" : "Template")}
            </button>
            <button
              title={ru ? "Добавить нового агента" : "Add a new agent"}
              onClick={openAgentWizard}
              disabled={agents.length >= MAX_TEAM_SIZE}
            >
              <Plus />
              <span>{ru ? "Создать агента" : "Create agent"}</span>
            </button>
          </div>
        </div>
        {agents.map((a, i) => (
          <AgentCard
            key={a.id}
            agent={a}
            color={colors[i % colors.length]}
            selected={a.id === selected}
            onClick={() => setSelected(a.id)}
          />
        ))}
      </aside>
      {agent && (
        <section className="inspector">
          <div className="profile">
            <AgentGlyph
              name={agent.name}
              skillName={agent.skill_name}
              color={colors[agents.indexOf(agent)]}
              className="bigavatar"
            />
            <div>
              <h2>{agent.name}</h2>
              <p>@{agent.slug}</p>
            </div>
            <span className="status ready">
              {ru ? "Настроен" : "Configured"}
            </span>
            <button
              className="danger agent-delete"
              onClick={() => void removeAgent()}
              title={ru ? "Удалить агента" : "Delete agent"}
              aria-label={ru ? "Удалить агента" : "Delete agent"}
            >
              <Trash2 />
            </button>
          </div>
          <div className="formgrid">
            <Label label={ru ? "Роль" : "Role"} value={agent.role} />
            <Label label={ru ? "Модель" : "Model"} value={agent.model} />
            <Label label={ru ? "Цель" : "Goal"} value={agent.goal} wide />
            <Label
              label={ru ? "Системная инструкция" : "System instruction"}
              value={agent.system_prompt}
              wide
            />
          </div>
          <section className={`adhdskillcard ${agent.adhd_skill_enabled !== false ? "enabled" : "disabled"}`}>
            <div className="adhdskillmark"><Brain /></div>
            <div className="adhdskillcopy">
              <span>DEFAULT SKILL · {agent.adhd_skill_enabled !== false ? "ON" : "OFF"}</span>
              <h3>I Have ADHD</h3>
              <p>{ru ? "Делает ответы исполнимыми: действие сначала, нумерованные шаги, видимый прогресс и один следующий шаг." : "Makes responses actionable: action first, numbered steps, visible progress, and one concrete next action."}</p>
              <small>{ru ? "Источник: ayghri/i-have-adhd · MIT. Это стиль вывода, не медицинская инструкция." : "Source: ayghri/i-have-adhd · MIT. Output style only, not medical advice."}</small>
            </div>
            <button className={`switch ${agent.adhd_skill_enabled !== false ? "on" : ""}`} onClick={() => void toggleBuiltinSkill()} aria-label={ru ? "Включить базовый skill" : "Toggle default skill"}>
              <i />
            </button>
          </section>
          <section className={`agentmodel ${agent.connection_id ? "live" : ""}`}>
            <div className="agentmodelhead">
              <div>
                <span>MODEL</span>
                <h3>{agent.connection_id ? (ru ? "Подключённая модель" : "Live model") : (ru ? "Демо-модель" : "Demo model")}</h3>
                <p>{ru ? "Назначьте сохранённый API и модель этому агенту без пересоздания команды." : "Assign a saved API and model without recreating this agent."}</p>
              </div>
              <b>{agent.connection_id && agent.model !== "mock-model" ? "LIVE" : "DEMO"}</b>
            </div>
            <div className="agentmodelcontrols">
              <label>
                <span>{ru ? "Подключение" : "Connection"}</span>
                <select
                  value={modelDraftConnectionId}
                  onChange={(event) => {
                    const nextId = event.target.value;
                    setModelDraftConnectionId(nextId);
                    const models = connectionModels(nextId);
                    if (nextId && models.length && !models.includes(modelDraft)) setModelDraft(models[0]);
                    if (!nextId) setModelDraft("mock-model");
                  }}
                >
                  <option value="">{ru ? "Без подключения · demo" : "No connection · demo"}</option>
                  {modelConnections.map((connection) => <option key={connection.id} value={connection.id}>{connection.name}</option>)}
                </select>
              </label>
              <label>
                <span>{ru ? "ID модели" : "Model ID"}</span>
                {connectionModels(modelDraftConnectionId).length ? (
                  <select
                    value={modelDraft}
                    onChange={(event) => setModelDraft(event.target.value)}
                  >
                    {!connectionModels(modelDraftConnectionId).includes(modelDraft) && modelDraft && (
                      <option value={modelDraft}>{modelDraft}</option>
                    )}
                    {connectionModels(modelDraftConnectionId).map((model) => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={modelDraft}
                    onChange={(event) => setModelDraft(event.target.value)}
                    placeholder="gpt-4o-mini"
                  />
                )}
              </label>
              <button className="primary" disabled={modelSaving || !modelDraft.trim()} onClick={() => void saveAgentModel()}>
                {modelSaving ? <Activity /> : ru ? "Сохранить модель" : "Save model"}
              </button>
            </div>
            {modelError && <small className="agentmodelerror">{modelError}</small>}
          </section>
          <div className={`skillslot ${agent.skill_name ? "filled" : ""}`}>
            <div className="skillmark">
              <Brain />
            </div>
            <div>
              <span>GLOBAL SKILL · {agent.skill_name ? "1/1" : "0/1"}</span>
              <h3>
                {agent.skill_name ||
                  (ru ? "Скилл не назначен" : "No skill assigned")}
              </h3>
              <p>
                {agent.skill_description ||
                  (ru
                    ? "Добавьте одну специализацию, которая будет дополнять агента во всех диалогах."
                    : "Add one specialization that enhances this agent in every dialogue.")}
              </p>
            </div>
            <button onClick={openSkill}>
              {agent.skill_name
                ? ru
                  ? "Изменить"
                  : "Change"
                : ru
                  ? "Выбрать скилл"
                  : "Choose skill"}
            </button>
          </div>
          <div className="agentgrowth">
            <div className="growthlevel">
              <Brain />
              <strong>LVL {agent.experience_level}</strong>
              <small>
                {agent.lessons_count} {ru ? "уроков" : "lessons"}
              </small>
            </div>
            <div>
              <span>PROFESSIONAL MEMORY</span>
              <h3>
                {ru
                  ? "Опыт развивается после каждой работы"
                  : "Experience grows after every run"}
              </h3>
              <p>
                {agent.professional_memory
                  ? agent.professional_memory.slice(-260)
                  : ru
                    ? "Агент пока не накопил профессиональных уроков. После завершения задач здесь появятся применённые подходы и результаты."
                    : "This agent has no professional lessons yet. Applied approaches and outcomes will appear after completed work."}
              </p>
            </div>
          </div>
          <h3>{ru ? "Права и ограничения" : "Permissions and constraints"}</h3>
          <div className="permissions">
            <Toggle
              label={ru ? "Может делегировать" : "Can delegate"}
              on={agent.can_delegate}
            />
            <Toggle
              label={ru ? "Может проверять" : "Can review"}
              on={agent.can_review}
            />
            <Toggle
              label={ru ? "Может выполнять tools" : "Can execute tools"}
              on
            />
            <Toggle
              label={ru ? "Требовать подтверждение" : "Require approval"}
              on={false}
            />
          </div>
        </section>
      )}
      <aside className="teampanel">
        <p className="eyebrow">TEAM RULES</p>
        <h3>{team?.name}</h3>
        <p className="panelhint">
          {ru
            ? "Здесь настраиваются участники, их роли и модели. Connections хранит общие инструменты и источники команды."
            : "Configure team members, roles, and models here. Connections stores shared tools and team data sources."}
        </p>
        <Label label={ru ? "Режим" : "Mode"} value={team?.mode || "standard"} />
        <Label
          label={ru ? "Супервайзер" : "Supervisor"}
          value={
            agents.find((a) => a.id === team?.supervisor_agent_id)?.name || "—"
          }
        />
        <Label
          label={ru ? "Макс. параллельно" : "Max parallel"}
          value={String(team?.max_parallel_agents || 3)}
        />
      </aside>
      {adding && (
        <div className="modalback connectorback" onClick={closeAgentWizard}>
          <div
            className="modal connectormodal agentwizard"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">
                  AGENT SETUP ·{" "}
                  {agentStep === "details"
                    ? "1/3"
                    : agentStep === "provider"
                      ? "2/3"
                      : "3/3"}
                </p>
                <h2>{ru ? "Новый агент" : "New agent"}</h2>
              </div>
              <button onClick={closeAgentWizard}>
                <X />
              </button>
            </header>
            <div className="wizardprogress" aria-hidden="true">
              <i className="done" />
              <i className={agentStep !== "details" ? "done" : ""} />
              <i className={agentStep === "model" ? "done" : ""} />
            </div>
            {agentStep === "details" && (
              <>
                <p className="modalhint">
                  {ru
                    ? "Опишите участника команды. Роль и цель будут использоваться во всех его диалогах."
                    : "Describe the team member. Its role and goal apply to every dialogue."}
                </p>
                <div className="wizardfields">
                  <LabelInput
                    label={ru ? "Имя" : "Name"}
                    value={name}
                    set={setName}
                  />
                  <LabelInput
                    label={ru ? "Роль" : "Role"}
                    value={role}
                    set={setRole}
                  />
                  <label className="inputlabel wide">
                    <span>{ru ? "Задача агента" : "Agent goal"}</span>
                    <textarea
                      value={goal}
                      onChange={(event) => setGoal(event.target.value)}
                      placeholder={
                        ru
                          ? "Какой результат этот агент должен создавать?"
                          : "What result should this agent produce?"
                      }
                    />
                  </label>
                </div>
                <footer>
                  <span />
                  <button onClick={closeAgentWizard}>
                    {ru ? "Отмена" : "Cancel"}
                  </button>
                  <button
                    className="primary"
                    disabled={!name.trim() || !role.trim()}
                    onClick={() => setAgentStep("provider")}
                  >
                    {ru ? "Выбрать модель" : "Choose model"}
                    <ChevronRight />
                  </button>
                </footer>
              </>
            )}
            {agentStep === "provider" && (
              <>
                <p className="modalhint">
                  {ru
                    ? "Выберите сохранённый API без повторного ввода ключа или подключите новый. Orbit проверит доступ и сам загрузит список моделей."
                    : "Reuse a saved API without entering its key again, or connect a new one. Orbit verifies access and loads every available model."}
                </p>
                {modelConnections.length > 0 && (
                  <section className="savedapis">
                    <div>
                      <span>{ru ? "СОХРАНЁННЫЕ API" : "SAVED APIS"}</span>
                      <small>
                        {ru
                          ? "Один ключ можно использовать для разных агентов и моделей"
                          : "One key can power multiple agents and models"}
                      </small>
                    </div>
                    <div>
                      {modelConnections.map((connection) => (
                        <button
                          key={connection.id}
                          onClick={() => reuseConnection(connection)}
                        >
                          <ShieldCheck />
                          <span>
                            <b>{connection.name}</b>
                            <small>
                              {
                                (
                                  (connection.config.available_models ||
                                    connection.config.active_models ||
                                    []) as string[]
                                ).length
                              }{" "}
                              {ru ? "моделей" : "models"}
                            </small>
                          </span>
                          <ChevronRight />
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                <div className="providersearch">
                  <Search />
                  <input
                    aria-label={ru ? "Поиск провайдера" : "Search providers"}
                    value={providerSearch}
                    onChange={(event) => setProviderSearch(event.target.value)}
                    placeholder={
                      ru
                        ? `Поиск по ${PROVIDERS.length + 1} провайдерам…`
                        : `Search ${PROVIDERS.length + 1} providers…`
                    }
                  />
                </div>
                <div className="providercatalog agentproviders">
                  <button
                    className={agentProvider === "mock" ? "active" : ""}
                    onClick={() => changeAgentProvider("mock")}
                  >
                    <span style={{ background: "#716ff224", color: "#8d89ff" }}>
                      MO
                    </span>
                    <div>
                      <b>Mock Provider</b>
                      <small>
                        {ru
                          ? "Демо без ключа и оплаты"
                          : "Demo without keys or cost"}
                      </small>
                    </div>
                    <i>BUILT-IN</i>
                  </button>
                  {PROVIDERS.filter((provider) =>
                    `${provider.name} ${provider.hint}`
                      .toLowerCase()
                      .includes(providerSearch.toLowerCase()),
                  ).map((provider) => (
                    <button
                      key={provider.id}
                      className={agentProvider === provider.id ? "active" : ""}
                      onClick={() => changeAgentProvider(provider.id)}
                    >
                      <span
                        style={{
                          background: `${provider.color}24`,
                          color: provider.color,
                        }}
                      >
                        {provider.short}
                      </span>
                      <div>
                        <b>{provider.name}</b>
                        <small>{provider.hint}</small>
                      </div>
                      {provider.id === "agentrouter" && <i>POPULAR</i>}
                      {provider.id === "openrouter-free" && <i>FREE</i>}
                      {provider.local && <i>LOCAL</i>}
                    </button>
                  ))}
                </div>
                <div className="agentconnectionfields">
                  <label className="inputlabel">
                    <span>Endpoint URL</span>
                    <input
                      value={
                        agentProvider === "mock" ? "Built in" : agentBaseUrl
                      }
                      disabled={agentProvider === "mock"}
                      onChange={(event) => setAgentBaseUrl(event.target.value)}
                      placeholder="https://api.example.com/v1"
                    />
                  </label>
                  {agentProvider !== "mock" && (
                    <LabelInput
                      label={
                        PROVIDERS.find((item) => item.id === agentProvider)
                          ?.local
                          ? ru
                            ? "API key · необязательно"
                            : "API key · optional"
                          : "API key"
                      }
                      value={agentApiKey}
                      set={setAgentApiKey}
                      secret
                    />
                  )}
                </div>
                {agentProvider === "custom" && (
                  <LabelInput
                    label={ru ? "ID модели · если /models недоступен" : "Model ID · if /models is unavailable"}
                    value={agentModel}
                    set={setAgentModel}
                    placeholder={ru ? "Например: glm-4.5-air" : "e.g. glm-4.5-air"}
                  />
                )}
                {(() => {
                  const consoleUrl = PROVIDERS.find((item) => item.id === agentProvider)?.consoleUrl;
                  return consoleUrl ? (
                    <a className="consolehint" href={consoleUrl} target="_blank" rel="noopener noreferrer">
                      {ru ? "Получить API-ключ →" : "Get API key →"}
                    </a>
                  ) : null;
                })()}
                {agentProvider === "gemini" && (
                  <section className="accountoauth">
                    <div>
                      <Globe2 />
                      <span>
                        <b>{ru ? "Войти через Google" : "Continue with Google"}</b>
                        <small>
                          {ru
                            ? "Официальный OAuth Gemini API — пароль и cookies не передаются Orbit."
                            : "Official Gemini API OAuth—Orbit never receives your password or browser cookies."}
                        </small>
                      </span>
                    </div>
                    <label className="inputlabel">
                      <span>Google Cloud project ID</span>
                      <input
                        value={googleProjectId}
                        onChange={(event) =>
                          setGoogleProjectId(event.target.value)
                        }
                        placeholder="my-gemini-project"
                      />
                    </label>
                    <button
                      className="primary googleoauthbutton"
                      disabled={discovering || googleProjectId.trim().length < 4}
                      onClick={connectGeminiAccount}
                    >
                      {discovering ? <Activity /> : <Globe2 />}
                      {ru ? "Продолжить с Google" : "Continue with Google"}
                    </button>
                    <p>
                      {ru
                        ? "В проекте должна быть включена Generative Language API. Подписка Gemini в браузере сама по себе не является API-квотой."
                        : "The Generative Language API must be enabled in the project. A consumer Gemini subscription is not itself API quota."}
                    </p>
                  </section>
                )}
                <div className="securitynote">
                  <ShieldCheck />
                  <span>
                    {ru
                      ? "Ключ шифруется на сервере. Orbit не показывает его после сохранения."
                      : "The key is encrypted on the server and is never displayed after saving."}
                  </span>
                </div>
                {agentDiscoveryError && (
                  <div className="discoveryerror" role="alert">
                    <AlertTriangle />
                    <div>
                      <b>
                        {ru
                          ? "Не удалось загрузить модели"
                          : "Could not load models"}
                      </b>
                      <span>{agentDiscoveryError}</span>
                    </div>
                  </div>
                )}
                <footer>
                  <button onClick={() => setAgentStep("details")}>
                    <ChevronLeft />
                    {ru ? "Назад" : "Back"}
                  </button>
                  <span />
                  <button
                    className="primary"
                    disabled={
                      discovering ||
                      (!agentBaseUrl.trim() && agentProvider !== "mock") ||
                      Boolean(
                        agentProvider !== "mock" &&
                          !PROVIDERS.find((item) => item.id === agentProvider)
                            ?.local &&
                          !agentApiKey.trim(),
                      )
                    }
                    onClick={discoverAgentModels}
                  >
                    {discovering ? (
                      <>
                        <Activity />
                        {ru ? "Проверяем API…" : "Testing API…"}
                      </>
                    ) : (
                      <>
                        <Sparkles />
                        {ru ? "Проверить и найти модели" : "Test and discover"}
                      </>
                    )}
                  </button>
                  {agentProvider === "custom" && agentModel.trim() && (
                    <button onClick={() => {
                      setDiscoveredModels([{ id: agentModel.trim(), name: agentModel.trim(), owner: "manual", context_length: null }]);
                      setDiscoveryMeta({ count: 1, latency: 0 });
                      setAgentStep("model");
                    }}>
                      {ru ? "Продолжить с этой моделью" : "Use this model ID"}
                    </button>
                  )}
                </footer>
              </>
            )}
            {agentStep === "model" && (
              <>
                <div className="discoverysuccess">
                  <Check />
                  <div>
                    <b>{ru ? "API подключён" : "API connected"}</b>
                    <small>
                      {discoveryMeta?.count || 0}{" "}
                      {ru ? "моделей найдено" : "models discovered"} ·{" "}
                      {discoveryMeta?.latency || 0} ms
                    </small>
                  </div>
                </div>
                <div className="modelsearch">
                  <Search />
                  <input
                    aria-label={ru ? "Поиск модели" : "Search models"}
                    value={modelSearch}
                    onChange={(event) => setModelSearch(event.target.value)}
                    placeholder={ru ? "Найти модель…" : "Find a model…"}
                  />
                </div>
                <div className="modellist">
                  {discoveredModels
                    .filter((model) =>
                      `${model.id} ${model.name} ${model.owner || ""}`
                        .toLowerCase()
                        .includes(modelSearch.toLowerCase()),
                    )
                    .map((model) => (
                      <button
                        key={model.id}
                        className={agentModel === model.id ? "active" : ""}
                        onClick={() => setAgentModel(model.id)}
                      >
                        <i>{agentModel === model.id && <Check />}</i>
                        <div>
                          <b>{model.name || model.id}</b>
                          <small>{model.id}</small>
                        </div>
                        {model.context_length && (
                          <span>
                            {Math.round(model.context_length / 1000)}K ctx
                          </span>
                        )}
                      </button>
                    ))}
                </div>
                <p className="selectioncount">
                  {agentModel
                    ? ru
                      ? `Активная модель: ${agentModel}`
                      : `Active model: ${agentModel}`
                    : ru
                      ? "Выберите одну модель"
                      : "Choose one model"}
                </p>
                <footer>
                  <button onClick={() => setAgentStep("provider")}>
                    <ChevronLeft />
                    {ru ? "Другой API" : "Different API"}
                  </button>
                  <span />
                  <button
                    className="primary"
                    disabled={!agentModel.trim()}
                    onClick={addAgent}
                  >
                    <Plus />
                    {ru ? "Создать агента" : "Create agent"}
                  </button>
                </footer>
              </>
            )}
          </div>
        </div>
      )}
      {skillOpen && (
        <div
          className="modalback skillback"
          onClick={() => setSkillOpen(false)}
        >
          <div
            className="modal skillmodal"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">ONE GLOBAL SLOT</p>
                <h2>
                  {ru ? "Скилл для" : "Skill for"} {agent?.name}
                </h2>
              </div>
              <button onClick={() => setSkillOpen(false)}>
                <X />
              </button>
            </header>
            <p className="modalhint">
              {ru
                ? "Активен только один скилл. Он закреплён за агентом и работает во всех диалогах."
                : "Only one skill can be active. It stays with the agent and applies to every dialogue."}
            </p>
            <div className="skillcatalog">
              {AGENT_SKILLS.map((skill) => (
                <button
                  key={skill.name}
                  className={skillName === skill.name ? "active" : ""}
                  onClick={() => chooseSkill(skill)}
                >
                  <Brain />
                  <div>
                    <b>{skill.name}</b>
                    <small>
                      {ru ? skill.descriptionRu : skill.descriptionEn}
                    </small>
                  </div>
                  {skillName === skill.name && <Check />}
                </button>
              ))}
            </div>
            <div className="customskill">
              <p className="eyebrow">CUSTOM SKILL</p>
              <LabelInput
                label={ru ? "Название" : "Name"}
                value={skillName}
                set={setSkillName}
              />
              <label className="inputlabel">
                <span>{ru ? "Описание" : "Description"}</span>
                <textarea
                  value={skillDescription}
                  onChange={(e) => setSkillDescription(e.target.value)}
                />
              </label>
              <label className="inputlabel">
                <span>{ru ? "Инструкция агенту" : "Agent instruction"}</span>
                <textarea
                  value={skillPrompt}
                  onChange={(e) => setSkillPrompt(e.target.value)}
                  placeholder={
                    ru
                      ? "Что именно агент должен делать иначе…"
                      : "What exactly should this agent do differently…"
                  }
                />
              </label>
            </div>
            <footer>
              <button
                className="dangertext"
                onClick={() => {
                  setSkillName("");
                  setSkillDescription("");
                  setSkillPrompt("");
                }}
              >
                {ru ? "Убрать скилл" : "Remove skill"}
              </button>
              <span />
              <button onClick={() => setSkillOpen(false)}>
                {ru ? "Отмена" : "Cancel"}
              </button>
              <button className="primary" onClick={saveSkill}>
                {ru ? "Сохранить" : "Save"}
              </button>
            </footer>
          </div>
        </div>
      )}
      {templateOpen && (
        <div className="modalback skillback" onClick={() => setTemplateOpen(false)}>
          <div className="modal skillmodal" onClick={(e) => e.stopPropagation()}>
            <header>
              <h3>{ru ? "Шаблоны команд" : "Team templates"}</h3>
              <button onClick={() => setTemplateOpen(false)}>
                <X />
              </button>
            </header>
            <p style={{ padding: "0 20px 4px", color: "var(--text-secondary)", fontSize: 13 }}>
              {ru
                ? "Один клик — и все агенты шаблона добавляются в команду с настроенными скиллами. Можно дополнить ещё до пяти своих агентов."
                : "One click adds all template agents with pre-configured skills. You can add up to five more custom agents on top."}
            </p>
            <div className="skillcatalog">
              {TEAM_TEMPLATES.map((tpl) => (
                <button
                  key={tpl.id}
                  className="skill"
                  onClick={() => applyTemplate(tpl)}
                >
                  <b>{tpl.emoji} {ru ? tpl.nameRu : tpl.nameEn}</b>
                  <small>{ru ? tpl.descriptionRu : tpl.descriptionEn}</small>
                  <small style={{ marginTop: 6, opacity: 0.6 }}>
                    {tpl.agents.map((a) => a.name).join(" · ")}
                  </small>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
function Label({
  label,
  value,
  wide,
}: {
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <label className={wide ? "wide" : ""}>
      <span>{label}</span>
      <div>{value}</div>
    </label>
  );
}
function Toggle({ label, on }: { label: string; on: boolean }) {
  return (
    <div className="toggleline">
      <span>{label}</span>
      <i className={on ? "on" : ""}>
        <b />
      </i>
    </div>
  );
}
function OrbitLoader({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="orbit-process" role="status" aria-live="polite">
      <div className="process-orb" aria-hidden="true">
        <span>
          {label.split("").map((letter, index) => (
            <i
              key={`${letter}-${index}`}
              style={{ animationDelay: `${index * 0.06}s` }}
            >
              {letter}
            </i>
          ))}
        </span>
      </div>
      <div className="process-copy">
        <b>{label}</b>
        <small>{detail}</small>
      </div>
    </div>
  );
}
function HoloModeToggle({
  mode,
  setMode,
  language,
}: {
  mode: Mode;
  setMode: (mode: Mode) => void;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const active = mode === "constructive";
  return (
    <div className={`holo-mode-control ${active ? "activated" : ""}`}>
      <div className="grid-plane" />
      <div className="stars-container">
        {[0, 1, 2].map((layer) => (
          <i className="star-layer" key={layer} />
        ))}
      </div>
      <button
        className={`standard-mode ${!active ? "active" : ""}`}
        onClick={() => setMode("standard")}
        title={
          ru
            ? "Standard: руководитель распределяет работу, специалисты отвечают, затем руководитель собирает общий результат."
            : "Standard: the lead assigns work, specialists contribute, and the lead synthesises one shared result."
        }
      >
        {ru ? "Стандарт" : "Standard"}
      </button>
      <input
        className="holo-checkbox-input"
        id="constructive-holo"
        type="checkbox"
        checked={active}
        onChange={(event) =>
          setMode(event.target.checked ? "constructive" : "standard")
        }
      />
      <label
        className="holo-checkbox"
        htmlFor="constructive-holo"
        title={
          ru
            ? "Constructive: вклады агентов проходят критическую проверку и сводятся в общий результат."
            : "Constructive: agent contributions are critically reviewed and synthesised into a shared result."
        }
      >
        <span className="holo-box">
          <i className="holo-inner" />
          <i className="scan-effect" />
          <span className="holo-particles">
            {Array.from({ length: 6 }, (_, index) => (
              <i className="holo-particle" key={index} />
            ))}
          </span>
          <span className="activation-rings">
            {[0, 1, 2].map((ring) => (
              <i className="activation-ring" key={ring} />
            ))}
          </span>
          <span className="cube-transform">
            {Array.from({ length: 6 }, (_, index) => (
              <i className="cube-face" key={index} />
            ))}
          </span>
        </span>
        <span className="holo-copy">
          <b>{ru ? "Конструктив" : "Constructive"}</b>
          <small>
            {active
              ? ru
                ? "Проверка и общий вывод включены"
                : "Review and synthesis active"
              : ru
                ? "Включить проверку и общий вывод"
                : "Enable review and synthesis"}
          </small>
        </span>
        <i className="holo-glow" />
      </label>
      <div className="holo-telemetry">
        <div className="frequency-spectrum">
          {Array.from({ length: 12 }, (_, index) => (
            <i className="frequency-bar" key={index} />
          ))}
        </div>
        <span>{ru ? "РЕЖИМ" : "MODE"}: {active ? (ru ? "АКТИВЕН" : "ACTIVE") : (ru ? "ОЖИДАНИЕ" : "STANDBY")}</span>
        <span>{ru ? "ПРОВЕРКА" : "VERIFY"}: {active ? "ON" : "—"}</span>
        <span>{ru ? "СИНХРОН" : "SYNCH"}: {active ? (ru ? "ГОТОВ" : "READY") : (ru ? "ОЖИДАНИЕ" : "IDLE")}</span>
      </div>
    </div>
  );
}

function DialogueModeExplainer({ mode, language }: { mode: Mode; language: "ru" | "en" }) {
  const ru = language === "ru";
  const constructive = mode === "constructive";
  return (
    <div className={`dialogue-mode-explainer ${constructive ? "constructive" : "standard"}`} role="status">
      <b>{constructive ? (ru ? "Конструктивный режим" : "Constructive mode") : (ru ? "Стандартный режим" : "Standard mode")}</b>
      <span>
        {constructive
          ? (ru
            ? "Для решений и спорных задач: независимый критик проверяет вклад команды, а руководитель фиксирует общий вывод и ограничения."
            : "For decisions and disputed work: an independent critic checks the team’s evidence, then the lead records one conclusion and its limits.")
          : (ru
            ? "Для быстрых ответов и исполнения: руководитель подключает только нужных специалистов; отдельная критика не запускается."
            : "For fast answers and execution: the lead calls only the specialists needed; no separate critique is started.")}
      </span>
    </div>
  );
}

function WorkflowBuilder({
  workflow,
  onSaved,
  openDialogue,
  language,
  agents = [],
  embedded = false,
}: {
  workflow: Workflow | null;
  onSaved: (w: Workflow) => void;
  openDialogue?: () => void;
  language: "ru" | "en";
  agents?: Agent[];
  embedded?: boolean;
}) {
  const ru = language === "ru";
  const initialNodes = useMemo<FlowNode[]>(
    () =>
      workflow?.nodes.map((n, i) => ({
        id: String(n.id),
        position: (n.position as { x: number; y: number }) || {
          x: (i % 3) * 260,
          y: Math.floor(i / 3) * 160,
        },
        data: { ...n, label: String(n.label || n.type), type: n.type },
        className: `flow-${n.type}`,
      })) || [],
    [workflow],
  );
  const initialEdges = useMemo<Edge[]>(
    () =>
      workflow?.edges.map((e) => ({
        id: String(e.id),
        source: String(e.source),
        target: String(e.target),
        animated: e.source === "start",
      })) || [],
    [workflow],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [mcpServers, setMcpServers] = useState<Connection[]>([]);
  const [mcpTools, setMcpTools] = useState<Array<{ name: string; description: string }>>([]);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [argumentsDraft, setArgumentsDraft] = useState("{}");
  const [mappingDraft, setMappingDraft] = useState("{}");
  const [jsonError, setJsonError] = useState("");
  const workflowWorkspaceId = workflow?.workspace_id;
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
    setSelectedNodeId(null);
  }, [workflow?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!workflowWorkspaceId) return;
    api.mcpServers(workflowWorkspaceId).then(setMcpServers).catch(() => setMcpServers([]));
  }, [workflowWorkspaceId]);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || null;
  const selectedConnectionId = String(selectedNode?.data.connection_id || "");
  useEffect(() => {
    setArgumentsDraft(JSON.stringify(selectedNode?.data.arguments || {}, null, 2));
    setMappingDraft(JSON.stringify(selectedNode?.data.input_mapping || {}, null, 2));
    setJsonError("");
  }, [selectedNode?.id, selectedNode?.data.arguments, selectedNode?.data.input_mapping]);
  useEffect(() => {
    if (selectedNode?.data.type !== "tool" || !selectedConnectionId) {
      setMcpTools([]);
      return;
    }
    setMcpLoading(true);
    api.mcpTools(selectedConnectionId)
      .then((items) => setMcpTools(items))
      .catch(() => setMcpTools([]))
      .finally(() => setMcpLoading(false));
  }, [selectedNode?.id, selectedConnectionId, selectedNode?.data.type]);
  const [result, setResult] = useState("");
  const [saving, setSaving] = useState(false);
  async function validate() {
    if (!workflow) return;
    const r = await api.validateWorkflow(workflow.id);
    setResult(
      r.valid ? "Workflow valid" : r.errors.map((e) => e.message).join(", "),
    );
  }
  async function save() {
    if (!workflow) return;
    setSaving(true);
    try {
      onSaved(
        await api.updateWorkflow(workflow.id, {
          nodes: nodes.map((n) => ({
            ...n.data,
            id: n.id,
            type: n.data.type || "agent",
            label: n.data.label,
            position: n.position,
          })),
          edges: edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
          })),
        }),
      );
    } finally {
      setSaving(false);
    }
  }
  function addNode(type: string) {
    const id = `${type}-${Date.now()}`;
    setNodes((old) => [
      ...old,
      {
        id,
        position: { x: 180 + old.length * 24, y: 100 + old.length * 18 },
        data: { label: type.replace("_", " "), type },
        className: `flow-${type}`,
      },
    ]);
    setSelectedNodeId(id);
  }
  function updateSelectedNode(patch: Record<string, unknown>) {
    if (!selectedNodeId) return;
    setNodes((old) => old.map((node) => node.id === selectedNodeId
      ? { ...node, data: { ...node.data, ...patch } }
      : node));
  }
  function removeSelectedNode() {
    if (!selectedNodeId) return;
    setNodes((old) => old.filter((node) => node.id !== selectedNodeId));
    setEdges((old) => old.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId));
    setSelectedNodeId(null);
  }
  function applyJsonField(field: "arguments" | "input_mapping", value: string) {
    try {
      const parsed = JSON.parse(value || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object")
        throw new Error("Object required");
      updateSelectedNode({ [field]: parsed });
      setJsonError("");
    } catch {
      setJsonError(
        ru
          ? "JSON не сохранён: проверьте скобки, кавычки и запятые."
          : "JSON was not saved: check brackets, quotes, and commas.",
      );
    }
  }
  const connect = useCallback(
    (params: FlowConnection) =>
      setEdges((old) => addEdge({ ...params, id: `e-${Date.now()}` }, old)),
    [setEdges],
  );
  return (
    <div className={`flowwrap ${embedded ? "embedded" : ""}`}>
      {!embedded && <section className="flowdecision">
        <div>
          <p className="eyebrow">AUTOMATION BUILDER</p>
          <h2>
            {ru
              ? "Задайте команде постоянный порядок работы"
              : "Give the team a repeatable way to work"}
          </h2>
          <p>
            {ru
              ? "Сценарий нужен только тогда, когда одну и ту же сложную работу надо каждый раз выполнять по одинаковым правилам."
              : "Use automation only when the same complex job must follow the same rules every time."}
          </p>
        </div>
        <div className="flowmodecards">
          <button onClick={openDialogue}>
            <MessageSquare />
            <span>
              <b>{ru ? "Обычный диалог" : "Normal dialogue"}</b>
              <small>
                {ru
                  ? "Вы выбираете агентов, они сами договариваются о работе."
                  : "Choose agents and let them coordinate organically."}
              </small>
            </span>
            <ChevronRight />
          </button>
          <button className="active">
            <GitBranch />
            <span>
              <b>{ru ? "Автоматический сценарий" : "Automated scenario"}</b>
              <small>
                {ru
                  ? "Вы заранее фиксируете этапы, проверки и решения человека."
                  : "Predefine stages, reviews, and human decisions."}
              </small>
            </span>
            <Check />
          </button>
        </div>
        <div className="flowbenefits">
          <span>
            <Check />
            {ru ? "Фиксированный порядок" : "Fixed order"}
          </span>
          <span>
            <ShieldCheck />
            {ru ? "Контроль перед действиями" : "Approval gates"}
          </span>
          <span>
            <RotateCcw />
            {ru ? "Повторное использование" : "Reusable process"}
          </span>
          <span>
            <Box />
            {ru ? "Гарантированный результат" : "Required output"}
          </span>
        </div>
      </section>}
      {!embedded && <div className="flowintro">
        <GitBranch />
        <div>
          <b>{ru ? "Как читать схему" : "How to read the diagram"}</b>
          <p>
            {ru
              ? "Работа идёт слева направо по линиям. Блок Agent передаёт результат следующему шагу; Approval останавливает процесс до вашего решения; Final output завершает запуск."
              : "Work follows the connections from left to right. Agent hands its result to the next step; Approval pauses for your decision; Final output completes the run."}
          </p>
        </div>
      </div>}
      <div className="flowbar">
        <div>
          <b>{workflow?.name}</b>
          <span>v{workflow?.version}</span>
        </div>
        <div>
          {result && (
            <span className="validation">
              <Check />
              {result}
            </span>
          )}
          <button onClick={validate}>{ru ? "Проверить" : "Validate"}</button>
          <button className="primary" onClick={save}>
            {saving
              ? ru
                ? "Сохраняем…"
                : "Saving…"
              : ru
                ? "Сохранить"
                : "Save"}
          </button>
        </div>
      </div>
      <div className="flowbody">
        <aside className="palette">
          <p className="eyebrow">{ru ? "ДОБАВИТЬ ШАГ" : "ADD A STEP"}</p>
          {[
            [
              "agent",
              ru ? "Работа агента" : "Agent task",
              Bot,
              ru
                ? "Назначить этап конкретному агенту"
                : "Assign a stage to an agent",
            ],
            [
              "human_input",
              ru ? "Вопрос человеку" : "Ask human",
              MessageSquare,
              ru
                ? "Запросить данные у пользователя"
                : "Request information from the user",
            ],
            [
              "condition",
              ru ? "Условие" : "Condition",
              GitBranch,
              ru
                ? "Выбрать следующую ветку по правилу"
                : "Choose a branch using a rule",
            ],
            [
              "approval",
              ru ? "Подтверждение" : "Approval",
              ShieldCheck,
              ru
                ? "Остановиться до решения пользователя"
                : "Pause until the user decides",
            ],
            [
              "tool",
              ru ? "Инструмент" : "Tool",
              Plug,
              ru ? "Вызвать подключённый сервис" : "Call a connected service",
            ],
            [
              "review",
              ru ? "Проверка" : "Review",
              ShieldCheck,
              ru ? "Проверить качество результата" : "Review output quality",
            ],
            [
              "artifact",
              ru ? "Документ" : "Artifact",
              Box,
              ru
                ? "Сохранить промежуточный результат"
                : "Save an intermediate deliverable",
            ],
            [
              "final",
              ru ? "Финальный ответ" : "Final output",
              Check,
              ru
                ? "Завершить сценарий результатом"
                : "Finish the scenario with an output",
            ],
          ].map(([type, label, I, hint]) => (
            <button
              key={String(type)}
              title={String(hint)}
              onClick={() => addNode(String(type))}
            >
              <I />
              <span>{String(label)}</span>
            </button>
          ))}
        </aside>
        <div className="flowcanvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={connect}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            fitView
          >
            <Background color="#373941" />
            <Controls />
            <MiniMap nodeColor="#6f6ae8" />
          </ReactFlow>
        </div>
        {selectedNode && (
          <aside className="flowinspector">
            <header>
              <div>
                <p className="eyebrow">{ru ? "НАСТРОЙКА ШАГА" : "STEP SETTINGS"}</p>
                <b>{String(selectedNode.data.label || selectedNode.data.type)}</b>
              </div>
              <button onClick={() => setSelectedNodeId(null)} aria-label={ru ? "Закрыть" : "Close"}><X /></button>
            </header>
            <label>
              <span>{ru ? "Название" : "Label"}</span>
              <input value={String(selectedNode.data.label || "")} onChange={(event) => updateSelectedNode({ label: event.target.value })} />
            </label>
            {(selectedNode.data.type === "agent" || selectedNode.data.type === "review") && (
              <>
                <label>
                  <span>{ru ? "Исполнитель" : "Assigned agent"}</span>
                  <select
                    value={String(selectedNode.data.agent_id || "")}
                    onChange={(event) => updateSelectedNode({ agent_id: event.target.value || null })}
                  >
                    <option value="">{ru ? "Выберите агента" : "Choose an agent"}</option>
                    {agents.map((agent) => (
                      <option value={agent.id} key={agent.id}>{agent.name} · {agent.role}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{ru ? "Точное задание" : "Task instruction"}</span>
                  <textarea
                    value={String(selectedNode.data.instruction || "")}
                    onChange={(event) => updateSelectedNode({ instruction: event.target.value })}
                    placeholder={ru ? "Что именно должен вернуть этот агент" : "What exactly this agent must return"}
                  />
                </label>
                <label>
                  <span>{ru ? "Критерии готовности · по одному на строку" : "Definition of done · one per line"}</span>
                  <textarea
                    value={Array.isArray(selectedNode.data.acceptance_criteria) ? selectedNode.data.acceptance_criteria.join("\n") : ""}
                    onChange={(event) => updateSelectedNode({
                      acceptance_criteria: event.target.value.split("\n").map((item) => item.trim()).filter(Boolean),
                    })}
                  />
                </label>
              </>
            )}
            {selectedNode.data.type === "tool" && (
              <>
                <div className="flowtoolnotice">
                  <Plug />
                  <p>{ru ? "MCP подключается к этому workflow и доступен только в его запусках." : "This MCP tool belongs to the workflow and is available only during its runs."}</p>
                </div>
                <label>
                  <span>{ru ? "MCP-сервер" : "MCP server"}</span>
                  <select
                    value={selectedConnectionId}
                    onChange={(event) => updateSelectedNode({ connection_id: event.target.value || null, tool_name: null })}
                  >
                    <option value="">{ru ? "Выберите сервер" : "Choose a server"}</option>
                    {mcpServers.map((server) => <option key={server.id} value={server.id}>{server.name}</option>)}
                  </select>
                </label>
                <label>
                  <span>{ru ? "Инструмент" : "Tool"}</span>
                  <select
                    value={String(selectedNode.data.tool_name || "")}
                    disabled={!selectedConnectionId || mcpLoading}
                    onChange={(event) => {
                      const tool = mcpTools.find((item) => item.name === event.target.value);
                      updateSelectedNode({ tool_name: event.target.value, label: tool?.name || selectedNode.data.label });
                    }}
                  >
                    <option value="">{mcpLoading ? (ru ? "Загрузка…" : "Loading…") : (ru ? "Выберите инструмент" : "Choose a tool")}</option>
                    {mcpTools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
                  </select>
                </label>
                <label>
                  <span>{ru ? "Уровень риска" : "Risk level"}</span>
                  <select value={String(selectedNode.data.risk || "read")} onChange={(event) => updateSelectedNode({ risk: event.target.value })}>
                    <option value="read">{ru ? "Только чтение" : "Read only"}</option>
                    <option value="write">{ru ? "Изменение · с подтверждением" : "Write · approval required"}</option>
                  </select>
                </label>
                <label>
                  <span>{ru ? "Статические аргументы · JSON" : "Static arguments · JSON"}</span>
                  <textarea
                    value={argumentsDraft}
                    onChange={(event) => setArgumentsDraft(event.target.value)}
                    onBlur={() => applyJsonField("arguments", argumentsDraft)}
                    spellCheck={false}
                  />
                </label>
                <label>
                  <span>{ru ? "Входы из предыдущих шагов · JSON" : "Inputs from previous steps · JSON"}</span>
                  <textarea
                    value={mappingDraft}
                    onChange={(event) => setMappingDraft(event.target.value)}
                    onBlur={() => applyJsonField("input_mapping", mappingDraft)}
                    placeholder={'{"address":"$nodes.research.output.address"}'}
                    spellCheck={false}
                  />
                </label>
                {jsonError && <small className="flowjsonerror">{jsonError}</small>}
                {!mcpServers.length && <small>{ru ? "Сначала установите MCP-сервер в Connections → MCP Hub." : "Install an MCP server in Connections → MCP Hub first."}</small>}
              </>
            )}
            <button className="danger flowdelete" onClick={removeSelectedNode}><Trash2 />{ru ? "Удалить шаг" : "Delete step"}</button>
          </aside>
        )}
      </div>
    </div>
  );
}

function LiveRun({
  run,
  team,
  workspace,
  agents,
  events,
  setEvents,
  tasks,
  approvals,
  artifacts,
  live,
  start,
  setRun,
  openRun,
  setError,
  appearance,
  go,
}: {
  run: Run | null;
  team: Team | null;
  workspace: Workspace | null;
  agents: Agent[];
  events: RunEvent[];
  setEvents: Dispatch<SetStateAction<RunEvent[]>>;
  tasks: Task[];
  approvals: Approval[];
  artifacts: Artifact[];
  live: boolean;
  start: (
    goal?: string,
    materials?: DraftMaterial[],
    agentIds?: string[],
    workflowOverride?: string,
  ) => void | Promise<void>;
  setRun: (r: Run) => void;
  openRun: (r: Run) => Promise<void>;
  setError: (e: string) => void;
  appearance: AppearanceSettings;
  go: (screen: Screen) => void;
}) {
  const ru = appearance.language === "ru";
  const [message, setMessage] = useState("");
  const [target, setTarget] = useState("all");
  const [command, setCommand] = useState("instruction");
  const [filter, setFilter] = useState("conversation");
  const [infoOpen, setInfoOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const pendingMessageId = useRef<string | null>(null);
  const [resultOpen, setResultOpen] = useState(false);
  const [resultTab, setResultTab] = useState<"artifact" | "verdict" | "audit">(
    "artifact",
  );
  const [branchTarget, setBranchTarget] = useState<RunEvent | null>(null);
  const [branchKind, setBranchKind] = useState<"fork" | "rewind">("fork");
  const [branchInstruction, setBranchInstruction] = useState("");
  const [branching, setBranching] = useState(false);
  const [shared, setShared] = useState(false);
  const [parentCompare, setParentCompare] = useState<{
    run: Run;
    artifacts: Artifact[];
  } | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [automationOpen, setAutomationOpen] = useState(false);
  const [automationEnabled, setAutomationEnabled] = useState(false);
  const [automationWorkflow, setAutomationWorkflow] =
    useState<Workflow | null>(null);
  const [automationBusy, setAutomationBusy] = useState(false);
  const [agentsOpen, setAgentsOpen] = useState(false);
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [agentsBusy, setAgentsBusy] = useState(false);
  const [launching, setLaunching] = useState(false);
  const runAgents = useMemo(() => {
    const ids = Array.isArray(run?.context.agent_ids)
      ? new Set(run.context.agent_ids as string[])
      : null;
    return ids?.size ? agents.filter((agent) => ids.has(agent.id)) : agents;
  }, [run?.context.agent_ids, agents]);
  useEffect(() => {
    let cancelled = false;
    setAutomationOpen(false);
    setAutomationEnabled(Boolean(run?.workflow_id));
    setAutomationWorkflow(null);
    if (!run || !workspace) return;
    api
      .workflows(workspace.id)
      .then((items) => {
        if (cancelled) return;
        setAutomationWorkflow(
          items.find((item) => item.id === run.workflow_id) ||
            items.find((item) => item.description === `dialogue:${run.id}`) ||
            null,
        );
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [run?.id, run?.workflow_id, workspace?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const soundedEvent = useRef<string | null>(null);
  useEffect(() => {
    const last = events.at(-1);
    if (
      appearance.sounds &&
      last?.type === "run.completed" &&
      soundedEvent.current !== last.id
    ) {
      soundedEvent.current = last.id;
      playChime();
    }
  }, [events, appearance.sounds]);
  const filtered = events.filter(
    (e) =>
      e.visibility !== "internal" &&
      (filter === "all" ||
        (filter === "conversation" &&
          (e.type === "message.human" || e.type === "message.agent")) ||
        (filter === "human" && e.type === "message.human") ||
        (filter === "agents" && e.type === "message.agent") ||
        (filter === "system" && e.actor_type === "system") ||
        (filter === "errors" && e.type.includes("failed"))),
  );
  const pendingApprovals = approvals.filter((item) => item.status === "pending");
  const latestFailure = [...events]
    .reverse()
    .find((event) => event.type === "run.failed");
  const composerBlocked = pendingApprovals.length > 0 || run?.status === "cancelled";
  const mode = run?.mode || team?.mode || "standard";
  const selectedTarget = runAgents.find((agent) => agent.id === target);
  const turnHint =
    command === "redirect"
      ? ru
        ? "Новая цель запустит свежий раунд для всей выбранной команды."
        : "A new goal starts a fresh turn for the full selected team."
      : command === "request_review"
        ? ru
          ? "Запрос на проверку направляется reviewer/supervisor: они проверят последний результат и вернут замечания или общий вывод."
          : "The review request goes to the reviewer/supervisor to assess the latest result and return findings or a shared conclusion."
        : command === "speak_as"
          ? ru
            ? `Заметка будет добавлена от имени ${selectedTarget?.name || "выбранного агента"}, затем начнётся новый раунд для всей команды.`
            : `The note will be attributed to ${selectedTarget?.name || "the selected agent"}, then a new turn starts for the full team.`
          : target !== "all"
            ? ru
              ? `@${selectedTarget?.slug || "agent"}: ответит только этот агент. Остальные не запускаются, общий итог не создаётся.`
              : `@${selectedTarget?.slug || "agent"}: only this agent responds. The others do not run and no shared synthesis is created.`
            : mode === "constructive"
              ? ru
                ? "@all: каждый выбранный агент подготовит вклад, затем reviewer/supervisor проверит и сведёт результат."
                : "@all: every selected agent contributes, then the reviewer/supervisor reviews and synthesises the result."
              : ru
                ? "@all: руководитель распределяет работу, специалисты отвечают по очереди, затем руководитель сводит общий результат."
                : "@all: the lead assigns work, specialists respond in sequence, then the lead synthesises one shared result.";
  const eventModes = useMemo(() => {
    const values = new Map<string, Mode>();
    let active: Mode =
      (events.find((e) => e.type === "run.started")?.payload.mode as Mode) ||
      run?.mode ||
      team?.mode ||
      "standard";
    for (const event of [...events].sort((a, b) => a.sequence - b.sequence)) {
      if (event.type === "run.mode_changed")
        active = (event.payload.to as Mode) || active;
      values.set(event.id, active);
    }
    return values;
  }, [events, run?.mode, team?.mode]);
  const workingAgent = useMemo(() => {
    const activeTasks = new Set<string>();
    for (const event of events) {
      if (event.type === "task.started" && event.task_id)
        activeTasks.add(event.task_id);
      if (
        (event.type === "task.completed" || event.type === "task.failed") &&
        event.task_id
      )
        activeTasks.delete(event.task_id);
    }
    const last = [...events]
      .reverse()
      .find((e) => e.task_id && activeTasks.has(e.task_id));
    return runAgents.find((a) => a.id === last?.actor_id);
  }, [events, runAgents]);
  const resultArtifact = [...artifacts]
    .reverse()
    .find(
      (item) =>
        item.kind === "final_output" || item.kind === "working_document",
    );
  const verdictArtifact = [...artifacts]
    .reverse()
    .find((item) => item.kind === "verdict");
  const tradingVerdictArtifact = [...artifacts]
    .reverse()
    .find((item) => item.kind === "trading_verdict");
  const decisionRecordArtifact = [...artifacts]
    .reverse()
    .find((item) => item.kind === "decision_record");
  const guardEvent = [...events]
    .reverse()
    .find(
      (item) =>
        item.type === "run.budget_reached" || item.type === "run.loop_guard",
    );
  const toolCalls = events.filter(
    (item) => item.type === "tool.call.completed",
  ).length;
  const latestHumanSequence =
    [...events]
      .reverse()
      .find((event) => event.type === "message.human")?.sequence ?? -1;
  const currentTurnTasks = useMemo(() => {
    const ids = new Set(
      events
        .filter(
          (event) =>
            event.sequence > latestHumanSequence &&
            event.task_id &&
            event.type.startsWith("task."),
        )
        .map((event) => event.task_id as string),
    );
    return tasks.filter(
      (task) => ids.has(task.id) && task.result?.internal !== true,
    );
  }, [events, latestHumanSequence, tasks]);
  const completedTurnTasks = currentTurnTasks.filter(
    (task) => task.status === "done",
  ).length;
  const latestTurnPlan = [...events]
    .reverse()
    .find(
      (event) =>
        event.type === "turn.plan.created" &&
        event.sequence > latestHumanSequence,
    );
  const plannedTasks = Array.isArray(latestTurnPlan?.payload.tasks)
    ? (latestTurnPlan.payload.tasks as Array<Record<string, unknown>>)
    : [];
  const handoffCreated = events.filter(
    (event) =>
      event.type === "handoff.created" &&
      event.sequence > latestHumanSequence,
  ).length;
  const handoffClosed = events.filter(
    (event) =>
      (event.type === "handoff.answered" || event.type === "handoff.failed") &&
      event.sequence > latestHumanSequence,
  ).length;
  // The same character from the Signal Room remains present during the actual
  // dialogue. Its motion maps to live runtime state rather than decoration.
  const scoutState: MascotState =
    run?.status === "failed" || run?.status === "cancelled"
      ? "alert"
      : workingAgent || run?.status === "running"
        ? "thinking"
        : run?.status === "completed"
          ? "done"
          : "idle";
  function taskState(task: Task) {
    if (task.status === "done") return ru ? "ответил" : "answered";
    if (task.status === "failed") return ru ? "ошибка ответа" : "response failed";
    if (task.status === "in_progress") return ru ? "отвечает…" : "responding…";
    return ru ? "ожидает" : "waiting";
  }
  async function send() {
    if (!run || !message.trim() || sendingRef.current || composerBlocked) return;
    const value = message.trim();
    const clientMessageId = pendingMessageId.current || crypto.randomUUID();
    pendingMessageId.current = clientMessageId;
    sendingRef.current = true;
    setMessage("");
    setSending(true);
    try {
      const persisted =
        command === "speak_as"
          ? await api.impersonate(run.id, target, value)
          : await api.message(
              run.id,
              value,
              [target],
              command,
              clientMessageId,
            );
      // The POST response is already the committed event. Render it immediately
      // instead of waiting for a stream that may currently be reconnecting.
      setEvents((old) => mergeRunEvents(old, [persisted]));
      // A follow-up can reopen a completed run. Refresh the run immediately so
      // the composer/status bar cannot remain visually stuck on COMPLETED while
      // the successor worker is already running.
      void api.run(run.id).then(setRun).catch(() => undefined);
      // Also collect events committed next to the message (for example
      // run.resumed on a completed dialogue). The fallback poll handles replies.
      // Reconciliation is best-effort. A transient events/SSE failure must not
      // turn a successfully committed human message into a false “not sent”
      // error in the composer.
      try {
        const latest = await api.events(run.id, persisted.sequence);
        setEvents((old) => mergeRunEvents(old, latest));
      } catch {
        // The persisted POST event is already visible; SSE/polling will catch up.
      }
      setCommand("instruction");
      setTarget("all");
      pendingMessageId.current = null;
    } catch (e) {
      setMessage(value);
      setError((e as Error).message);
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }
  function openAgents() {
    setSelectedAgentIds(runAgents.map((agent) => agent.id));
    setAgentsOpen(true);
  }
  async function saveAgents() {
    if (!run || selectedAgentIds.length === 0 || agentsBusy) return;
    setAgentsBusy(true);
    try {
      setRun(await api.updateRunAgents(run.id, selectedAgentIds));
      setAgentsOpen(false);
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setAgentsBusy(false);
    }
  }
  async function addMaterial(files: FileList | null) {
    if (!run || !workspace || !files) return;
    try {
      let updated = run;
      for (const file of [...files].slice(0, 5)) {
        const asset = await api.uploadFile(workspace.id, file);
        updated = await api.attachFile(run.id, asset.id);
      }
      setRun(updated);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function setMode(value: Mode) {
    if (!run) return;
    try {
      setRun(await api.mode(run.id, value));
    } catch (error) {
      setError((error as Error).message);
    }
  }
  async function action(a: "pause" | "resume" | "cancel") {
    if (!run) return;
    await api.action(run.id, a);
    setRun(await api.run(run.id));
  }
  async function launchCreatedRun() {
    if (!run || run.status !== "created" || launching) return;
    setLaunching(true);
    try {
      await api.startRun(run.id);
      const [updated, nextEvents] = await Promise.all([
        api.run(run.id),
        api.events(run.id, 0),
      ]);
      setRun(updated);
      setEvents((old) => mergeRunEvents(old, nextEvents));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setLaunching(false);
    }
  }
  async function decision(id: string, d: "approved" | "rejected") {
    try {
      await api.decide(id, d);
      if (run) setRun(await api.run(run.id));
    } catch (error) {
      setError((error as Error).message);
    }
  }
  async function createBranch() {
    if (!run || !branchTarget || branching) return;
    setBranching(true);
    try {
      const created = await api.branchRun(run.id, {
        event_id: branchTarget.id,
        instruction: branchInstruction.trim(),
        kind: branchKind,
      });
      setBranchTarget(null);
      setBranchInstruction("");
      await openRun(created);
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBranching(false);
    }
  }
  async function share() {
    if (!run) return;
    try {
      const value = await api.shareReplay(run.id);
      const url = new URL(value.public_url, location.origin).toString();
      await navigator.clipboard.writeText(url);
      setShared(true);
      window.setTimeout(() => setShared(false), 2400);
    } catch (value) {
      setError((value as Error).message);
    }
  }
  async function compareParent() {
    const parentId = String(run?.context.parent_run_id || "");
    if (!parentId || compareLoading) return;
    setCompareLoading(true);
    try {
      const [parent, parentArtifacts] = await Promise.all([
        api.run(parentId),
        api.artifacts(parentId),
      ]);
      setParentCompare({ run: parent, artifacts: parentArtifacts });
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setCompareLoading(false);
    }
  }
  async function continueRun() {
    if (!run) return;
    const updated = await api.updateRunBudget(run.id, {
      max_rounds:
        Math.max(
          Number(run.context.max_rounds || 0),
          events.filter((item) => item.type === "message.agent").length,
        ) + 4,
    });
    setRun(updated);
    await api.action(run.id, "resume");
    setRun(await api.run(run.id));
  }
  async function toggleAutomation() {
    if (!run || !workspace || !team || automationBusy) return;
    if (automationEnabled) {
      setAutomationEnabled(false);
      return;
    }
    setAutomationBusy(true);
    try {
      let current = automationWorkflow;
      if (!current) {
        const nodes = [
          { id: "start", type: "start", label: "Start" },
          ...runAgents.map((agent, index) => ({
            id: `agent-${index + 1}`,
            type: "agent",
            label: agent.role || agent.name,
            agent_id: agent.id,
          })),
          { id: "final", type: "final", label: "Final output" },
        ];
        const edges = nodes.slice(0, -1).map((node, index) => ({
          id: `edge-${index + 1}`,
          source: String(node.id),
          target: String(nodes[index + 1].id),
        }));
        current = await api.createWorkflow({
          workspace_id: workspace.id,
          team_id: team.id,
          name: `${ru ? "Сценарий" : "Automation"} · ${run.goal.slice(0, 72)}`,
          description: `dialogue:${run.id}`,
          nodes,
          edges,
        });
        setAutomationWorkflow(current);
      }
      setAutomationEnabled(true);
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setAutomationBusy(false);
    }
  }
  async function launchAutomation() {
    if (!run || !automationWorkflow || !automationEnabled || automationBusy)
      return;
    setAutomationBusy(true);
    try {
      const validation = await api.validateWorkflow(automationWorkflow.id);
      if (!validation.valid) {
        throw new Error(
          validation.errors.map((item) => item.message).join(" · ") ||
            (ru ? "Сценарий заполнен некорректно" : "Automation is invalid"),
        );
      }
      setAutomationOpen(false);
      await start(
        run.goal,
        undefined,
        runAgents.map((agent) => agent.id),
        automationWorkflow.id,
      );
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setAutomationBusy(false);
    }
  }
  function exportRun(format: "md" | "json" | "pdf") {
    if (!run) return;
    setExportOpen(false);
    if (format === "pdf") {
      window.print();
      return;
    }
    const rows = events.map((event) => ({
      time: event.created_at,
      type: event.type,
      actor:
        agents.find((agent) => agent.id === event.actor_id)?.name ||
        event.actor_type,
      content: content(event),
    }));
    if (format === "json")
      saveFile(
        `orbit-${run.id}.json`,
        JSON.stringify({ run, events: rows, tasks, artifacts }, null, 2),
        "application/json",
      );
    else
      saveFile(
        `orbit-${run.id}.md`,
        [
          `# ${run.goal}`,
          `**Mode:** ${run.mode}  `,
          `**Status:** ${run.status}`,
          "",
          ...rows.map(
            (row) =>
              `## ${row.actor} · ${new Date(row.time).toLocaleString("ru-RU")}\n\n${row.content}`,
          ),
        ].join("\n\n"),
        "text/markdown",
      );
  }
  if (!run)
    return (
      <div className="emptyrun">
        <MessageSquare />
        <h2>{ru ? "Диалог ещё не начат" : "No dialogue yet"}</h2>
        <p>
          {ru
            ? "Создайте диалог, чтобы поставить задачу и получить ответы выбранных агентов."
            : "Create a dialogue to assign a goal and receive responses from selected agents."}
        </p>
        <button className="primary" onClick={() => start()}>
          <Play />
          {ru ? "Начать диалог" : "Start dialogue"}
        </button>
        <div className="emptyrun-links">
          <button onClick={() => go("workflows")}>
            <ChevronLeft />
            {ru ? "К списку диалогов" : "Back to dialogues"}
          </button>
          <button onClick={() => go("team")}>
            <Bot />
            {ru ? "Выбрать агентов" : "Choose agents"}
          </button>
        </div>
      </div>
    );
  return (
    <div className={`runlayout ${infoOpen || resultOpen ? "withpanel" : ""}`}>
      <aside className="runleft">
        <div className={`runscout ${scoutState}`}>
          <Mascot state={scoutState} size={78} />
          <div>
            <p className="eyebrow">ORBIT SCOUT</p>
            <b>
              {scoutState === "thinking"
                ? ru
                  ? `слушает ${workingAgent?.name || "команду"}`
                  : `listening to ${workingAgent?.name || "the crew"}`
                : scoutState === "done"
                  ? ru
                    ? "сигнал собран"
                    : "signal collected"
                  : scoutState === "alert"
                    ? ru
                      ? "требуется внимание"
                      : "needs attention"
                    : ru
                      ? "на наблюдении"
                      : "on watch"}
            </b>
          </div>
        </div>
        <div className="runobjective">
          <p className="eyebrow">OBJECTIVE</p>
          <b>{run.goal}</b>
        </div>
        {latestTurnPlan && (
          <div className="orchestrationstate">
            <p className="eyebrow">{ru ? "ПЛАН ХОДА" : "TURN PLAN"}</p>
            <b>
              {plannedTasks.length
                ? ru
                  ? `${plannedTasks.length} назначенных задач`
                  : `${plannedTasks.length} assigned tasks`
                : ru
                  ? "Прямой ответ руководителя"
                  : "Direct lead response"}
            </b>
            <small>
              {ru ? "Handoff закрыто" : "Handoffs closed"}: {handoffClosed}/{handoffCreated}
            </small>
          </div>
        )}
        <div className="runagentsheading">
          <p className="eyebrow">AGENTS</p>
          <button onClick={openAgents} title={ru ? "Изменить состав диалога" : "Manage dialogue agents"}>
            <Plus />
          </button>
        </div>
        {runAgents.map((a, i) => {
          const task = [...currentTurnTasks]
            .reverse()
            .find((value) => value.assigned_agent_id === a.id);
          return (
            <div className="runagent" key={a.id}>
              <AgentGlyph name={a.name} skillName={a.skill_name} color={colors[i]} />
              <div>
                <b>{a.name}</b>
                <small>
                  {task?.status || "idle"} · {a.role}
                </small>
              </div>
              <i className={task?.status === "in_progress" ? "busy" : ""} />
            </div>
          );
        })}
        <p className="eyebrow tasklabel">
          {ru ? "ТЕКУЩИЙ ОТВЕТ" : "CURRENT TURN"} · {completedTurnTasks}/{currentTurnTasks.length}
        </p>
        {currentTurnTasks.map((t) => {
          const agent = agents.find((value) => value.id === t.assigned_agent_id);
          return <div className={`minitask ${t.status}`} key={t.id}>
            <span>{t.status === "done" ? "✓" : t.status === "failed" ? "!" : "·"}</span>
            <p><b>{agent?.name || (ru ? "Агент" : "Agent")}</b><small>{taskState(t)}</small></p>
          </div>
        })}
        {currentTurnTasks.length === 0 && (
          <p className="turnidle">{ru ? "Ожидаем распределения" : "Waiting for assignment"}</p>
        )}
      </aside>
      <section className="feed">
        <header className="runhead">
          <div>
            <h2>{ru ? "Диалог" : "Dialogue"}</h2>
            <span className={`connection ${live ? "live" : ""}`}>
              {live ? "LIVE" : "CONNECTING"}
            </span>
            <span className={`runstatus ${run.status}`}>{run.status}</span>
            {Boolean(run.context.parent_run_id) && (
              <button className="branchlineage" onClick={compareParent}>
                <GitBranch />
                {compareLoading
                  ? "…"
                  : `${String(run.context.branch_kind || "fork")} · #${String(run.context.branch_point_sequence || "")}`}
              </button>
            )}
          </div>
          <div className="runcontrols">
            <button
              title={ru ? "Добавить или убрать агента" : "Add or remove agents"}
              className="manageagentsbutton"
              onClick={openAgents}
            >
              <Users />
              <span>{ru ? "Агенты" : "Agents"}</span>
            </button>
            <button
              title={
                ru
                  ? "Автоматизация только этого диалога"
                  : "Automation for this dialogue only"
              }
              className={`automationtrigger ${
                automationEnabled || run.workflow_id ? "active" : ""
              }`}
              onClick={() => setAutomationOpen(true)}
            >
              <GitBranch />
              {(automationEnabled || run.workflow_id) && <i />}
            </button>
            <button
              title={ru ? "Рабочий результат" : "Live result"}
              className={resultOpen ? "active" : ""}
              onClick={() => {
                setResultOpen((value) => !value);
                setInfoOpen(false);
              }}
            >
              <Box />
            </button>
            <button
              title={ru ? "Скопировать публичный replay" : "Copy public replay"}
              className={shared ? "shareok" : ""}
              onClick={share}
            >
              {shared ? <Check /> : <Share2 />}
            </button>
            <div className="exportmenu">
              <button
                title={ru ? "Экспорт диалога" : "Export dialogue"}
                onClick={() => setExportOpen((value) => !value)}
              >
                <Download />
              </button>
              {exportOpen && (
                <div>
                  <button onClick={() => exportRun("md")}>Markdown</button>
                  <button onClick={() => exportRun("json")}>JSON</button>
                  <button onClick={() => exportRun("pdf")}>PDF / Print</button>
                </div>
              )}
            </div>
            <button
              title={ru ? "Информация о диалоге" : "Dialogue information"}
              className={infoOpen ? "active" : ""}
              onClick={() => {
                setInfoOpen((v) => !v);
                setResultOpen(false);
              }}
            >
              <PanelRight />
            </button>
            {run.status !== "created" && (
              <button
                onClick={() =>
                  action(run.status === "paused" ? "resume" : "pause")
                }
              >
                {run.status === "paused" ? <Play /> : <Pause />}
              </button>
            )}
            <button className="danger" onClick={() => action("cancel")}>
              <Square />
            </button>
          </div>
        </header>
        <div className="filters">
          {["conversation", "human", "agents", "system", "errors"].map((x) => (
            <button
              key={x}
              className={filter === x ? "active" : ""}
              onClick={() => setFilter(x)}
            >
              {ru
                ? ({
                    conversation: "Диалог",
                    human: "Вы",
                    agents: "Агенты",
                    system: "Система",
                    errors: "Ошибки",
                  } as Record<string, string>)[x]
                : x}
            </button>
          ))}
          <span />
          <HoloModeToggle
            mode={mode}
            setMode={setMode}
            language={appearance.language}
          />
        </div>
        <DialogueModeExplainer mode={mode} language={appearance.language} />
        {guardEvent && run.status === "paused" && (
          <div className="safetyintervention">
            <AlertTriangle />
            <div>
              <b>
                {ru
                  ? "Защита от цикла приостановила команду"
                  : "Loop guard paused the team"}
              </b>
              <p>
                {ru
                  ? "Весь прогресс сохранён. Можно продолжить ещё несколько шагов или открыть текущий результат."
                  : "All progress is saved. Continue for a few more steps or open the current result."}
              </p>
            </div>
            <button onClick={continueRun}>
              {ru ? "Ещё 4 шага" : "4 more steps"}
            </button>
            <button onClick={() => setResultOpen(true)}>
              {ru ? "Показать результат" : "Show result"}
            </button>
          </div>
        )}
        <div className="eventlist">
          {run.status === "created" && (
            <div className="runlaunchcard">
              <span className="runlaunch-orbit"><Rocket /></span>
              <p className="eyebrow">{ru ? "PIPELINE ГОТОВ" : "PIPELINE READY"}</p>
              <h3>{ru ? "Настройка завершена. Запустите анализ." : "Setup is complete. Launch the analysis."}</h3>
              <p>
                {ru
                  ? `В запуск пойдут ${runAgents.length} ${runAgents.length === 1 ? "агент" : "агентов"}. Они начнут с целей pipeline, соберут доказательства и оставят проверяемый итог.`
                  : `${runAgents.length} agents will start from this pipeline’s goals, collect evidence, and leave a verifiable conclusion.`}
              </p>
              <div>
                <button className="primary" disabled={launching} onClick={() => void launchCreatedRun()}>
                  {launching ? <Activity /> : <Play />}
                  {launching ? (ru ? "Запускаем…" : "Launching…") : (ru ? "Запустить анализ" : "Launch analysis")}
                </button>
                <button onClick={openAgents}><Users /> {ru ? "Изменить команду" : "Edit team"}</button>
              </div>
            </div>
          )}
          {filtered.length === 0 && !workingAgent && (
            <div className="waiting">
              <Activity />
              <span>
                {run.status === "created"
                  ? ru
                    ? "Ожидает запуска pipeline"
                    : "Waiting for the pipeline to launch"
                  : ru
                  ? "Ожидаем первые сообщения…"
                  : "Waiting for the first messages…"}
              </span>
            </div>
          )}
          {filtered.map((e, i) => (
            <EventCard
              key={e.id}
              event={e}
              agent={agents.find((a) => a.id === e.actor_id)}
              mode={eventModes.get(e.id) || mode}
              latest={i === filtered.length - 1}
              onBranch={(event, kind) => {
                setBranchTarget(event);
                setBranchKind(kind);
              }}
            />
          ))}
          {workingAgent && (
            <div className="agenttyping">
              <AgentGlyph
                name={workingAgent.name}
                skillName={workingAgent.skill_name}
                color={colors[agents.indexOf(workingAgent) % colors.length]}
              />
              <div>
                <b>{workingAgent.name}</b>
                <p>
                  <i />
                  <i />
                  <i /> {ru ? "формирует ответ" : "is composing a response"}
                </p>
              </div>
            </div>
          )}
        </div>
        {run.status === "failed" && (
          <div className="turnnotice failed" role="status">
            <AlertTriangle />
            <div>
              <b>{ru ? "Предыдущий раунд остановился" : "The previous turn stopped"}</b>
              <p>
                {String(
                  latestFailure?.payload.error ||
                    (ru ? "Один или несколько агентов не ответили." : "One or more agents did not respond."),
                )}
              </p>
              <small>
                {ru
                  ? "Исправьте модели агентов или отправьте уточнение — Orbit запустит новый раунд в этом же диалоге."
                  : "Fix the affected agent models or send a correction. Orbit will start a fresh turn in this dialogue."}
              </small>
            </div>
            <button onClick={() => go("team")}>
              {ru ? "Проверить агентов" : "Check agents"}
            </button>
          </div>
        )}
        {pendingApprovals.map((a) => (
          <div className="approval approvaldock" key={a.id} role="alert">
            <ShieldCheck />
            <div>
              <b>{ru ? "Нужен ваш выбор, чтобы продолжить" : "Your decision is needed to continue"}</b>
              <p>{a.description}</p>
              <small>{ru ? "Риск" : "Risk"}: {a.risk}</small>
            </div>
            <button onClick={() => decision(a.id, "rejected")}>
              {ru ? "Отклонить" : "Reject"}
            </button>
            <button className="primary" onClick={() => decision(a.id, "approved")}>
              {ru ? "Продолжить" : "Continue"}
            </button>
          </div>
        ))}
        <div className="composer">
          <label
            className="dialogueattach"
            title={
              ru
                ? "Добавить материалы в этот диалог"
                : "Attach materials to this dialogue"
            }
          >
            <Plus />
            <input
              type="file"
              multiple
              accept=".txt,.md,.csv,.json,.js,.ts,.tsx,.py,.html,.css,.pdf,.docx"
              onChange={(e) => addMaterial(e.target.files)}
            />
          </label>
          <select
            className="commandselect"
            disabled={composerBlocked}
            value={command}
            onChange={(e) => {
              setCommand(e.target.value);
              setTarget(
                e.target.value === "speak_as"
                  ? runAgents[0]?.id || "all"
                  : "all",
              );
            }}
            title={
              ru
                ? "Что сделать с сообщением"
                : "How to handle this message"
            }
          >
            <option value="instruction">{ru ? "Новый раунд" : "New turn"}</option>
            <option value="redirect">
              {ru ? "Изменить цель" : "Change goal"}
            </option>
            <option value="request_review">
              {ru ? "Проверить ещё раз" : "Request review"}
            </option>
            <option value="speak_as">
              {ru ? "Говорить как агент" : "Speak as agent"}
            </option>
          </select>
          {(command === "instruction" || command === "speak_as") && (
            <select
              disabled={composerBlocked}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              title={
                command === "speak_as"
                  ? ru
                    ? "От чьего имени будет добавлена заметка"
                    : "Whose name the note is attributed to"
                  : ru
                    ? "@all запускает всю команду; @agent запускает только адресного агента"
                    : "@all starts the full team; @agent starts only the addressed agent"
              }
              aria-label={
                command === "speak_as"
                  ? ru
                    ? "Агент, от имени которого будет добавлена заметка"
                    : "Agent the note is attributed to"
                  : ru
                    ? "Получатель нового раунда"
                    : "New turn recipient"
              }
            >
              {command !== "speak_as" && <option value="all">@all</option>}
              {runAgents.map((a) => (
                <option key={a.id} value={a.id}>
                  {command === "speak_as" ? a.name : `@${a.slug}`}
                </option>
              ))}
            </select>
          )}
          <textarea
            disabled={composerBlocked}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={
              pendingApprovals.length
                ? ru
                  ? "Сначала подтвердите или отклоните действие выше…"
                  : "Approve or reject the action above first…"
                : command === "speak_as"
                ? ru
                  ? "Сообщение появится от имени выбранного агента…"
                  : "The message will appear as the selected agent…"
                : command === "redirect"
                  ? ru
                    ? "Новая цель для всей команды…"
                    : "New goal for the full team…"
                  : command === "request_review"
                    ? ru
                      ? "Что именно проверить в последнем результате?"
                      : "What should be checked in the latest result?"
                    : ru
                      ? "Сообщение для нового раунда…"
                      : "Message for a new turn…"
            }
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            className="primary"
            disabled={sending || !message.trim() || composerBlocked}
            onClick={send}
          >
            {sending ? <Activity /> : <Send />}
          </button>
          <p className="composerhint" aria-live="polite">
            {pendingApprovals.length
              ? ru
                ? "Новые сообщения временно приостановлены: команда ждёт вашего решения выше."
                : "New messages are paused while the team waits for your decision above."
              : run.status === "failed"
                ? ru
                  ? "Это сообщение начнёт новый раунд и сохранит историю диалога."
                  : "This message starts a fresh turn and keeps the dialogue history."
                : turnHint}
          </p>
        </div>
        <footer className="statusbar">
          <span className={live ? "ok" : ""}>
            ● {live ? "Connected" : "Reconnecting"}
          </span>
          <span>{runAgents.length} agents</span>
          <span>stage: {run.current_stage}</span>
          <span>plan v{run.plan_revision + 1}</span>
          <span className="telemetry">
            ≈{" "}
            {(
              run.total_input_tokens + run.total_output_tokens
            ).toLocaleString()}{" "}
            tokens · {toolCalls} tools
          </span>
        </footer>
      </section>
      {infoOpen && (
        <aside className="runright compactinfo">
          <header>
            <div>
              <p className="eyebrow">PLAN</p>
              <h3>{ru ? "План и состояние" : "Plan and state"}</h3>
            </div>
            <button onClick={() => setInfoOpen(false)}>
              <X />
            </button>
          </header>
          <div className="infobadges">
            <span>{run.mode}</span>
            <span>{run.status}</span>
            <span>{run.runtime_version}</span>
          </div>
          <p className="infohint">
            {ru
              ? "План обновляется оркестратором. При изменении цели незавершённые шаги будут пересобраны."
              : "The orchestrator updates this plan. Changing the goal rebuilds unfinished steps."}
          </p>
          <Label label={ru ? "Стадия" : "Stage"} value={run.current_stage} />
          <Label
            label={ru ? "Версия плана" : "Plan revision"}
            value={String(run.plan_revision + 1)}
          />
          <Label
            label={ru ? "Начат" : "Started"}
            value={
              run.started_at ? time(run.started_at, appearance.language) : "—"
            }
          />
          <Label
            label={ru ? "Агенты" : "Agents"}
            value={String(runAgents.length)}
          />
          <Label
            label={ru ? "Внутренние задачи" : "Internal tasks"}
            value={String(tasks.length)}
          />
          <section className="compactartifacts">
            <p className="eyebrow">RESULTS · {artifacts.length}</p>
            {artifacts.length === 0 ? (
              <small>{ru ? "Артефактов пока нет" : "No artifacts yet"}</small>
            ) : (
              artifacts.map((a) => (
                <div className="artifact" key={a.id}>
                  <Box />
                  <div>
                    <b>{artifactName(a, ru)}</b>
                    <small>{a.mime_type}</small>
                  </div>
                </div>
              ))
            )}
          </section>
          <details>
            <summary>
              {ru ? "Техническая диагностика" : "Technical diagnostics"}
            </summary>
            <code>
              {events.length} events ·{" "}
              {run.total_input_tokens + run.total_output_tokens} tokens
            </code>
          </details>
        </aside>
      )}
      {resultOpen && (
        <ResultPanel
          artifact={resultArtifact}
          verdict={verdictArtifact}
          tradingVerdict={tradingVerdictArtifact}
          decisionRecord={decisionRecordArtifact}
          tab={resultTab}
          setTab={setResultTab}
          close={() => setResultOpen(false)}
          language={appearance.language}
        />
      )}
      {automationOpen && (
        <div
          className="modalback automationback"
          onClick={() => !automationBusy && setAutomationOpen(false)}
        >
          <div
            className="modal automationmodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">DIALOGUE AUTOMATION</p>
                <h2>
                  {ru
                    ? "Сценарий для этого диалога"
                    : "Automation for this dialogue"}
                </h2>
                <small>
                  {ru
                    ? "По умолчанию выключено. Настройка не изменит другие диалоги."
                    : "Off by default. This setup never changes other dialogues."}
                </small>
              </div>
              <button
                aria-label={ru ? "Закрыть" : "Close"}
                onClick={() => setAutomationOpen(false)}
              >
                <X />
              </button>
            </header>
            <section className={`automationswitch ${automationEnabled ? "on" : ""}`}>
              <div className="automationicon">
                <GitBranch />
              </div>
              <div>
                <b>{ru ? "Повторяемый сценарий" : "Repeatable automation"}</b>
                <p>
                  {ru
                    ? "Агенты выполнят работу в заданном порядке, с проверками и точками участия человека."
                    : "Agents follow a defined order with reviews and optional human checkpoints."}
                </p>
              </div>
              <button
                className="toggleswitch"
                role="switch"
                aria-checked={automationEnabled}
                disabled={automationBusy || Boolean(run.workflow_id)}
                onClick={toggleAutomation}
              >
                <span />
              </button>
            </section>
            {run.workflow_id && (
              <div className="automationrunning">
                <Activity />
                <div>
                  <b>{ru ? "Сценарий уже запущен" : "Automation is running"}</b>
                  <p>
                    {ru
                      ? "Этот диалог создан из сценария. Его схему можно сохранить и использовать повторно."
                      : "This dialogue was launched from an automation. Its flow can be edited and reused."}
                  </p>
                </div>
              </div>
            )}
            {!automationEnabled ? (
              <div className="automationempty">
                <div>
                  <Sparkles />
                </div>
                <h3>{ru ? "Обычный диалог" : "Regular dialogue"}</h3>
                <p>
                  {ru
                    ? "Агенты общаются свободно. Включайте сценарий только когда нужен фиксированный и повторяемый процесс."
                    : "Agents collaborate freely. Enable automation only for a fixed, repeatable process."}
                </p>
              </div>
            ) : automationWorkflow ? (
              <div className="automationeditor">
                <div className="automationhint">
                  <ShieldCheck />
                  <span>
                    {ru
                      ? "Сохраните изменения в схеме, затем запустите её. Исходный диалог останется в истории."
                      : "Save the flow, then launch it. The original dialogue stays in history."}
                  </span>
                </div>
                <WorkflowBuilder
                  workflow={automationWorkflow}
                  onSaved={setAutomationWorkflow}
                  language={appearance.language}
                  agents={runAgents}
                  embedded
                />
              </div>
            ) : (
              <div className="automationloading">
                <Activity />
                {ru ? "Создаём сценарий…" : "Creating automation…"}
              </div>
            )}
            <footer>
              <button onClick={() => setAutomationOpen(false)}>
                {ru ? "Закрыть" : "Close"}
              </button>
              {automationEnabled && !run.workflow_id && (
                <button
                  className="primary"
                  disabled={!automationWorkflow || automationBusy}
                  onClick={launchAutomation}
                >
                  <Play />
                  {automationBusy
                    ? ru
                      ? "Запускаем…"
                      : "Launching…"
                    : ru
                      ? "Запустить сценарий"
                      : "Launch automation"}
                </button>
              )}
            </footer>
          </div>
        </div>
      )}
      {agentsOpen && (
        <div className="modalback" onClick={() => !agentsBusy && setAgentsOpen(false)}>
          <div className="modal runagentsmodal" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <p className="eyebrow">DIALOGUE TEAM</p>
                <h2>{ru ? "Агенты в этом диалоге" : "Agents in this dialogue"}</h2>
                <small>
                  {ru
                    ? "Новые участники подключатся к следующему сообщению команды."
                    : "New participants join the team on its next message."}
                </small>
              </div>
              <button aria-label={ru ? "Закрыть" : "Close"} onClick={() => setAgentsOpen(false)}>
                <X />
              </button>
            </header>
            <div className="runagentchoices">
              {agents.map((agent, index) => {
                const active = selectedAgentIds.includes(agent.id);
                const atCapacity = !active && selectedAgentIds.length >= MAX_TEAM_SIZE;
                return (
                  <button
                    key={agent.id}
                    className={active ? "active" : ""}
                    disabled={atCapacity}
                    onClick={() =>
                      setSelectedAgentIds((current) =>
                        current.includes(agent.id)
                          ? current.filter((id) => id !== agent.id)
                          : [...current, agent.id],
                      )
                    }
                  >
                    <AgentGlyph
                      name={agent.name}
                      skillName={agent.skill_name}
                      color={colors[index % colors.length]}
                    />
                    <span>
                      <b>{agent.name}</b>
                      <small>{agent.role}</small>
                    </span>
                    <i>{active && <Check />}</i>
                  </button>
                );
              })}
            </div>
            <footer>
              <span>
                {selectedAgentIds.length}/{MAX_TEAM_SIZE} {ru ? "агентов" : "agents"}
              </span>
              <button onClick={() => setAgentsOpen(false)}>{ru ? "Отмена" : "Cancel"}</button>
              <button
                className="primary"
                disabled={agentsBusy || selectedAgentIds.length === 0}
                onClick={saveAgents}
              >
                {agentsBusy ? <Activity /> : <Check />}
                {ru ? "Сохранить состав" : "Save team"}
              </button>
            </footer>
          </div>
        </div>
      )}
      {branchTarget && (
        <div
          className="modalback"
          onClick={() => !branching && setBranchTarget(null)}
        >
          <div
            className="modal branchmodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">BRANCH FROM #{branchTarget.sequence}</p>
                <h2>{ru ? "Изменить путь команды" : "Change the team path"}</h2>
              </div>
              <button onClick={() => setBranchTarget(null)}>
                <X />
              </button>
            </header>
            <div className="branchchoice">
              <button
                className={branchKind === "fork" ? "active" : ""}
                onClick={() => setBranchKind("fork")}
              >
                <GitFork />
                <span>
                  <b>Fork</b>
                  <small>
                    {ru ? "Сохранить обе ветки" : "Keep both branches"}
                  </small>
                </span>
              </button>
              <button
                className={branchKind === "rewind" ? "active" : ""}
                onClick={() => setBranchKind("rewind")}
              >
                <RotateCcw />
                <span>
                  <b>Rewind</b>
                  <small>
                    {ru ? "Продолжить заново отсюда" : "Resume anew from here"}
                  </small>
                </span>
              </button>
            </div>
            <textarea
              autoFocus
              value={branchInstruction}
              onChange={(event) => setBranchInstruction(event.target.value)}
              placeholder={
                ru
                  ? "Что изменить после этой точки?"
                  : "What should change after this point?"
              }
            />
            <footer>
              <button onClick={() => setBranchTarget(null)}>
                {ru ? "Отмена" : "Cancel"}
              </button>
              <button
                className="primary"
                disabled={branching}
                onClick={createBranch}
              >
                {branching ? <Activity /> : <GitFork />}
                {ru ? "Создать ветку" : "Create branch"}
              </button>
            </footer>
          </div>
        </div>
      )}
      {parentCompare && (
        <div className="modalback" onClick={() => setParentCompare(null)}>
          <div
            className="modal comparemodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">BRANCH COMPARISON</p>
                <h2>{ru ? "Сравнение решений" : "Compare outcomes"}</h2>
              </div>
              <button onClick={() => setParentCompare(null)}>
                <X />
              </button>
            </header>
            <div className="comparecolumns">
              <CompareResult
                label={ru ? "Исходная ветка" : "Original branch"}
                run={parentCompare.run}
                artifacts={parentCompare.artifacts}
              />
              <CompareResult
                label={ru ? "Текущая ветка" : "Current branch"}
                run={run}
                artifacts={artifacts}
              />
            </div>
            <footer>
              <button onClick={() => setParentCompare(null)}>
                {ru ? "Закрыть" : "Close"}
              </button>
              <button
                className="primary"
                onClick={() => openRun(parentCompare.run)}
              >
                {ru ? "Открыть исходную" : "Open original"}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function CompareResult({
  label,
  run,
  artifacts,
}: {
  label: string;
  run: Run;
  artifacts: Artifact[];
}) {
  const result = [...artifacts]
    .reverse()
    .find(
      (item) =>
        item.kind === "final_output" || item.kind === "working_document",
    );
  const verdict = [...artifacts]
    .reverse()
    .find((item) => item.kind === "verdict");
  return (
    <section>
      <p className="eyebrow">{label}</p>
      <div className="comparemeta">
        <span>{run.status}</span>
        <span>
          ≈{" "}
          {(run.total_input_tokens + run.total_output_tokens).toLocaleString()}{" "}
          tokens
        </span>
      </div>
      <h3>{String(verdict?.metadata.decision || result?.name || run.goal)}</h3>
      <pre>{result?.content || "No artifact yet."}</pre>
    </section>
  );
}

function TradingVerdictCard({
  artifact,
  language,
}: {
  artifact: Artifact;
  language: "ru" | "en";
}) {
  const meta = artifact.metadata as {
    verdict?: string;
    rationale?: string;
    scores?: Record<string, number | null>;
    blocking_risks?: string[];
    conditions?: string[];
    agent_count?: number;
    raw_verdict?: string;
    protections?: {
      status?: string;
      events?: Array<{ code?: string; reason?: string; before?: string; after?: string }>;
    };
  };
  const ru = language === "ru";
  const decision = (meta.verdict || "WATCH").toUpperCase();
  const color =
    decision === "ENTER"
      ? "#5fe0a2"
      : decision === "SKIP"
        ? "#f0607a"
        : "#f0b95d";
  const bg =
    decision === "ENTER"
      ? "linear-gradient(135deg,#1a2e22,#1e2a1e)"
      : decision === "SKIP"
        ? "linear-gradient(135deg,#2e1a1e,#2a1a1e)"
        : "linear-gradient(135deg,#2e2a1a,#26231a)";
  const scores = meta.scores || {};
  const dims = [
    { key: "research", label: ru ? "Ресёрч" : "Research" },
    { key: "audit", label: ru ? "Аудит" : "Audit" },
    { key: "narrative", label: ru ? "Нарратив" : "Narrative" },
    { key: "timing", label: ru ? "Тайминг" : "Timing" },
  ];
  return (
    <div className="tradingverdictcard">
      <div
        className="tv-badge"
        style={{ color, background: bg, borderColor: color + "40" }}
      >
        <span className="tv-badge-decision">{decision}</span>
        <span className="tv-badge-label">
          {ru ? "решение команды" : "team decision"}
        </span>
      </div>
      {meta.raw_verdict && meta.raw_verdict !== decision && (
        <div className="tv-protection-state">
          <ShieldCheck />
          <div>
            <b>{ru ? "ЗАЩИТА ИЗМЕНИЛА РЕШЕНИЕ" : "PROTECTION CLAMPED THE DECISION"}</b>
            <span>{meta.raw_verdict} → {decision}</span>
          </div>
        </div>
      )}
      {(meta.protections?.events || []).length > 0 && (
        <div className="tv-group">
          <b className="tv-section-label">{ru ? "СРАБОТАВШИЕ ПРАВИЛА" : "PROTECTION EVENTS"}</b>
          {(meta.protections?.events || []).map((event, index) => (
            <span className="tv-protection-item" key={`${event.code}-${index}`}>
              <strong>{event.code}</strong>{event.reason}
            </span>
          ))}
        </div>
      )}
      {meta.rationale && (
        <div className="tv-rationale">
          <b className="tv-section-label">
            {ru ? "ОБОСНОВАНИЕ" : "RATIONALE"}
          </b>
          <p>{meta.rationale.slice(0, 600)}</p>
        </div>
      )}
      <div className="tv-scores">
        <b className="tv-section-label">{ru ? "ОЦЕНКИ" : "SCORES"}</b>
        {dims.map(({ key, label }) => {
          // A dimension the crew never assessed must not render as a confident 0/10.
          const raw = scores[key];
          const assessed = typeof raw === "number";
          const val = assessed ? Math.min(10, Math.max(0, raw)) : 0;
          return (
            <div className="tv-score-row" key={key}>
              <span className="tv-dim-label">{label}</span>
              <div className="tv-bar-track">
                <div
                  className="tv-bar-fill"
                  style={{
                    width: assessed ? `${val * 10}%` : "0%",
                    background:
                      val >= 7 ? "#5fe0a2" : val >= 4 ? "#f0b95d" : "#f0607a",
                  }}
                />
              </div>
              <span className={`tv-score-num ${assessed ? "" : "tv-score-unknown"}`}>
                {assessed ? `${val}/10` : ru ? "не оценено" : "not assessed"}
              </span>
            </div>
          );
        })}
      </div>
      {(meta.blocking_risks || []).length > 0 && (
        <div className="tv-group">
          <b className="tv-section-label">
            {ru ? "БЛОКИРУЮЩИЕ РИСКИ" : "BLOCKING RISKS"}
          </b>
          {(meta.blocking_risks || []).map((r, i) => (
            <span key={i} className="tv-risk-item">
              {r}
            </span>
          ))}
        </div>
      )}
      {(meta.conditions || []).length > 0 && (
        <div className="tv-group">
          <b className="tv-section-label">
            {ru ? "УСЛОВИЯ ВХОДА" : "CONDITIONS"}
          </b>
          {(meta.conditions || []).map((c, i) => (
            <span key={i} className="tv-cond-item">
              {c}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function DecisionAudit({ artifact, language }: { artifact?: Artifact; language: "ru" | "en" }) {
  const ru = language === "ru";
  let record: Record<string, any> = {};
  try {
    record = artifact?.content ? JSON.parse(artifact.content) : {};
  } catch {
    record = {};
  }
  const summary = (record.summary || artifact?.metadata.summary || {}) as Record<string, unknown>;
  const signals = Array.isArray(record.signals) ? record.signals : [];
  const protectionEvents = Array.isArray(record.protections?.events) ? record.protections.events : [];
  const evidenceQuality = (record.protections?.evidence_quality || {}) as Record<string, unknown>;
  if (!artifact) {
    return <p className="decisionaudit-empty">{ru ? "Запись решения появится после завершения текущего хода." : "The decision record appears when the current turn completes."}</p>;
  }
  return (
    <div className="decisionaudit">
      <p className="eyebrow">DECISION RECORD · V1</p>
      <div className="decisionaudit-summary">
        {[
          [ru ? "Агенты" : "Agents", summary.agents],
          [ru ? "Сигналы" : "Valid signals", summary.valid_signals],
          [ru ? "Воздержались" : "Abstentions", summary.abstentions],
          [ru ? "Проверяемые источники" : "Traceable sources", summary.traceable_evidence ?? evidenceQuality.traceable_unique],
          [ru ? "Инструменты" : "Tools", summary.tool_calls],
        ].map(([label, value]) => <span key={String(label)}><strong>{String(value ?? 0)}</strong><small>{String(label)}</small></span>)}
      </div>
      {protectionEvents.length > 0 && <section><b>{ru ? "ЗАЩИТНЫЕ ПРАВИЛА" : "PROTECTION EVENTS"}</b>{protectionEvents.map((event: any, index: number) => <div className="audit-protection" key={`${event.code}-${index}`}><ShieldCheck/><span><strong>{String(event.code || "rule")}</strong>{String(event.reason || "")}</span></div>)}</section>}
      <section>
        <b>{ru ? "СИГНАЛЫ АГЕНТОВ" : "AGENT SIGNALS"}</b>
        {signals.length === 0 ? <small>{ru ? "Структурированных сигналов нет" : "No structured signals"}</small> : signals.map((signal: any, index: number) => {
          const evidence = Array.isArray(signal.evidence) ? signal.evidence : [];
          const traceable = evidence.filter((item: any) => item?.source && item?.reference);
          return <article className={`audit-signal ${signal.valid ? "valid" : "invalid"}`} key={`${signal.task_id}-${index}`}><header><strong>{String(signal.agent_name || "Agent")}</strong><span>{String(signal.stance || "abstain")}</span><em>{typeof signal.confidence === "number" ? `${signal.confidence}%` : "—"}</em></header><p>{String(signal.thesis || "")}</p><small>{signal.valid ? `${traceable.length}/${evidence.length} ${ru ? "проверяемых источников" : "traceable sources"}` : ru ? "Невалидный контракт — считается воздержанием" : "Invalid contract — counted as abstention"}</small>{traceable.length > 0 && <details className="audit-evidence"><summary>{ru ? "Открыть источники" : "Show sources"}</summary>{traceable.map((item: any, evidenceIndex: number) => <span key={`${item.source}-${item.reference}-${evidenceIndex}`}><b>{String(item.source)}</b>{String(item.reference)}</span>)}</details>}</article>;
        })}
      </section>
      <details><summary>{ru ? "Полная JSON-запись" : "Full JSON record"}</summary><pre>{artifact.content}</pre></details>
    </div>
  );
}

function ResultPanel({
  artifact,
  verdict,
  tradingVerdict,
  decisionRecord,
  tab,
  setTab,
  close,
  language,
}: {
  artifact?: Artifact;
  verdict?: Artifact;
  tradingVerdict?: Artifact;
  decisionRecord?: Artifact;
  tab: "artifact" | "verdict" | "audit";
  setTab: (value: "artifact" | "verdict" | "audit") => void;
  close: () => void;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const metadata = verdict?.metadata || {};
  const list = (value: unknown) =>
    Array.isArray(value) ? value.map(String) : value ? [String(value)] : [];
  const showTrading = !!tradingVerdict;
  return (
    <aside className="runright resultpanel">
      <header>
        <div>
          <span className="artifactlive">
            <i />
            {artifact?.kind === "working_document"
              ? ru
                ? "ОБНОВЛЯЕТСЯ В РЕАЛЬНОМ ВРЕМЕНИ"
                : "LIVE WORKING ARTIFACT"
              : ru
                ? "РЕЗУЛЬТАТ ГОТОВ"
                : "RESULT READY"}
          </span>
          <h3>
            {artifact ? artifactName(artifact, ru) : (ru ? "Рабочий результат" : "Working result")}
          </h3>
        </div>
        <button onClick={close}>
          <X />
        </button>
      </header>
      <div className="resulttabs">
        <button
          className={tab === "artifact" ? "active" : ""}
          onClick={() => setTab("artifact")}
        >
          {ru ? "Артефакт" : "Artifact"}
        </button>
        <button
          className={tab === "verdict" ? "active" : ""}
          onClick={() => setTab("verdict")}
        >
          {ru ? "Вердикт" : "Verdict"}
        </button>
        <button
          className={tab === "audit" ? "active" : ""}
          onClick={() => setTab("audit")}
        >
          {ru ? "Аудит" : "Audit"}
        </button>
      </div>
      <div className="resultcontent">
        {tab === "artifact" ? (
          <pre>
            {artifact?.content ||
              (ru
                ? "Агенты ещё формируют общий документ. Он появится после первого содержательного ответа."
                : "The agents are still assembling the shared document. It appears after the first substantive answer.")}
          </pre>
        ) : tab === "audit" ? (
          <DecisionAudit artifact={decisionRecord} language={language} />
        ) : showTrading ? (
          <TradingVerdictCard artifact={tradingVerdict!} language={language} />
        ) : (
          <div className="verdictcard">
            <p className="eyebrow">TEAM VERDICT</p>
            <h3>
              {String(
                metadata.decision ||
                  (ru
                    ? "Вердикт появится после критической проверки"
                    : "The verdict appears after critical review"),
              )}
            </h3>
            <div className="verdictscore">
              <strong>
                {String(metadata.agreement || 0)}/
                {String(metadata.total_agents || 0)}
              </strong>
              <span>{ru ? "агентов согласны" : "agents aligned"}</span>
            </div>
            {[
              [
                ru ? "Сохранённое несогласие" : "Preserved dissent",
                metadata.dissent,
              ],
              [
                ru ? "Проверенные факты" : "Facts checked",
                metadata.facts_checked,
              ],
              [ru ? "Предположения" : "Assumptions", metadata.assumptions],
              [
                ru ? "Открытые вопросы" : "Open questions",
                metadata.open_questions,
              ],
            ].map(
              ([label, value]) =>
                list(value).length > 0 && (
                  <div className="verdictgroup" key={String(label)}>
                    <b>{String(label).toUpperCase()}</b>
                    {list(value).map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                ),
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

function EventCard({
  event,
  agent,
  mode,
  latest,
  onBranch,
}: {
  event: RunEvent;
  agent?: Agent;
  mode: Mode;
  latest: boolean;
  onBranch: (event: RunEvent, kind: "fork" | "rewind") => void;
}) {
  const ru = document.documentElement.lang === "ru";
  const system = event.actor_type === "system",
    human = event.actor_type === "human";
  const name = system
    ? "Orbit"
    : human
      ? ru
        ? "Вы"
        : "You"
      : agent?.name || String(event.payload.agent_name || "Agent");
  const branchable =
    event.type.startsWith("message.") || event.type.startsWith("constructive.");
  return (
    <article
      className={`event ${event.type.replace(".", "-")} ${latest ? "latest" : ""}`}
    >
      {system || human ? (
        <span
          className="avatar"
          style={{ background: system ? "#555967" : "#3c83f6" }}
        >
          {system ? "O" : ru ? "Вы" : "You"}
        </span>
      ) : (
        <AgentGlyph
          name={name}
          skillName={agent?.skill_name}
          color={colors[Math.abs(name.length) % colors.length]}
        />
      )}
      <div className="eventbody">
        <header>
          <b>{name}</b>
          <span className="eventtype">
            {event.type.replace("message.", "")}
          </span>
          {Boolean(event.payload.impersonated_by_user) && (
            <span className="eventtype via-user">
              {ru ? "через вас" : "via you"}
            </span>
          )}
          <time>{time(event.created_at, ru ? "ru" : "en")}</time>
          <span className={`modebadge ${mode}`}>
            {mode === "constructive" ? "Constructive" : "Standard"}
          </span>
        </header>
        <StructuredMessage value={visibleMessageContent(event, system || human ? undefined : name, ru)} />
        {event.type === "run.failed" && (
          <div className="runfailure">
            {(
              (event.payload.failures as
                | Array<{ agent: string; error: string }>
                | undefined) || []
            ).map((item) => (
              <span key={`${item.agent}-${item.error}`}>
                <b>{item.agent}</b>
                {item.error}
              </span>
            ))}
            {Number(event.payload.completed_tasks || 0) > 0 && (
              <small>
                {ru
                  ? `${event.payload.completed_tasks} из ${Number(event.payload.completed_tasks || 0) + Number(event.payload.failed_tasks || 0)} агентов успели ответить — их вклад выше в ленте.`
                  : `${event.payload.completed_tasks} of ${Number(event.payload.completed_tasks || 0) + Number(event.payload.failed_tasks || 0)} agents finished — their work is above in the feed.`}
              </small>
            )}
          </div>
        )}
      </div>
      {branchable && (
        <div className="eventactions">
          <button
            title={ru ? "Вернуться сюда" : "Rewind here"}
            onClick={() => onBranch(event, "rewind")}
          >
            <RotateCcw />
          </button>
          <button
            title={ru ? "Создать параллельную ветку" : "Fork from here"}
            onClick={() => onBranch(event, "fork")}
          >
            <GitFork />
          </button>
        </div>
      )}
    </article>
  );
}
function TaskBoard({ tasks, agents }: { tasks: Task[]; agents: Agent[] }) {
  const cols = ["backlog", "in_progress", "review", "done"];
  return (
    <div className="kanban">
      {cols.map((c) => (
        <section key={c}>
          <header>
            <b>{c.replace("_", " ")}</b>
            <span>{tasks.filter((t) => t.status === c).length}</span>
          </header>
          {tasks
            .filter((t) => t.status === c)
            .map((t) => (
              <article key={t.id}>
                <small>#{t.id.slice(0, 6)}</small>
                <h3>{t.title}</h3>
                <p>{t.description}</p>
                <span>
                  {agents.find((a) => a.id === t.assigned_agent_id)?.name ||
                    "Unassigned"}
                </span>
              </article>
            ))}
        </section>
      ))}
    </div>
  );
}
function Connections({
  workspace,
  setError,
  language,
}: {
  workspace: Workspace | null;
  setError: (s: string) => void;
  language: "ru" | "en";
}) {
  const ru = language === "ru";
  const [items, setItems] = useState<Connection[]>([]);
  const [githubOpen, setGithubOpen] = useState(false);
  const [githubBusy, setGithubBusy] = useState(false);
  const [confirmGithubRevoke, setConfirmGithubRevoke] = useState(false);
  const [mcpOpen, setMcpOpen] = useState(false);
  const [mcpCatalog, setMcpCatalog] = useState<MCPPreset[]>([]);
  const [mcpChoice, setMcpChoice] = useState<MCPPreset | null>(null);
  const [mcpSecret, setMcpSecret] = useState("");
  const [mcpBusy, setMcpBusy] = useState(false);
  const [connectorChoice, setConnectorChoice] =
    useState<ContextConnectorPreset | null>(null);
  const [connectorCredential, setConnectorCredential] = useState("");
  const [connectorIdentifier, setConnectorIdentifier] = useState("");
  const [connectorBusy, setConnectorBusy] = useState(false);
  const [configureConnectorTarget, setConfigureConnectorTarget] = useState(false);
  const [capabilities, setCapabilities] = useState<DeploymentCapabilities | null>(null);
  const [confirmConnectorRevoke, setConfirmConnectorRevoke] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);
  const [modelProvider, setModelProvider] = useState("custom");
  const [modelName, setModelName] = useState("");
  const [modelBaseUrl, setModelBaseUrl] = useState("");
  const [modelApiKey, setModelApiKey] = useState("");
  const [modelManualId, setModelManualId] = useState("");
  const [modelBusy, setModelBusy] = useState(false);
  const [modelDeleting, setModelDeleting] = useState<string | null>(null);
  const [modelError, setModelError] = useState("");
  const [modelDiscovery, setModelDiscovery] = useState<ConnectionDiscovery | null>(null);
  const selectedModelPreset = PROVIDERS.find((item) => item.id === modelProvider);
  useEffect(() => {
    if (workspace)
      Promise.all([api.connections(workspace.id), api.mcpCatalog(), api.capabilities()])
        .then(([connections, catalog, deploymentCapabilities]) => {
          setItems(connections);
          setMcpCatalog(catalog);
          setCapabilities(deploymentCapabilities);
        })
        .catch((e) => setError(e.message));
  }, [workspace, setError]);
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const githubStatus = params.get("github_oauth");
    const contextStatus = params.get("context_oauth");
    const failed = [githubStatus, contextStatus].find(
      (value) => value && value !== "success",
    );
    if (failed) {
      setError(
        ru
          ? "Подключение аккаунта не завершено. Повторите вход и подтвердите доступ на официальном экране сервиса."
          : "Account connection was not completed. Sign in again and approve access on the service's official consent screen.",
      );
    }
    if (githubStatus || contextStatus) {
      params.delete("github_oauth");
      params.delete("context_oauth");
      params.delete("connector");
      history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
    }
  }, [ru, setError]);
  async function connectGithubOAuth() {
    if (!workspace) return;
    setGithubBusy(true);
    try {
      const result = await api.startGitHubOAuth(workspace.id);
      location.assign(result.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setGithubBusy(false);
    }
  }
  async function syncGithub(connection: Connection) {
    setGithubBusy(true);
    try {
      const result = await api.syncGitHub(connection.id);
      setItems((old) =>
        old.map((item) => item.id === result.connection.id ? result.connection : item),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGithubBusy(false);
    }
  }
  async function revokeGithub(connection: Connection) {
    if (!confirmGithubRevoke) {
      setConfirmGithubRevoke(true);
      return;
    }
    setGithubBusy(true);
    try {
      await api.revokeGitHub(connection.id);
      setItems((old) => old.filter((item) => item.id !== connection.id));
      setGithubOpen(false);
      setConfirmGithubRevoke(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setGithubBusy(false);
    }
  }
  async function installMcp() {
    if (!workspace || !mcpChoice) return;
    setMcpBusy(true);
    try {
      const server = await api.installMCP({
        workspace_id: workspace.id,
        preset_id: mcpChoice.id,
        secret: mcpSecret || null,
      });
      setItems((old) => [server, ...old]);
      setMcpSecret("");
      setMcpChoice(null);
      setMcpOpen(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMcpBusy(false);
    }
  }
  async function connectContextOAuth() {
    if (!workspace || !connectorChoice) return;
    setConnectorBusy(true);
    try {
      const value = await api.startContextOAuth(
        workspace.id,
        connectorChoice.id,
      );
      location.assign(value.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setConnectorBusy(false);
    }
  }
  async function connectContextCredential() {
    if (!workspace || !connectorChoice) return;
    setConnectorBusy(true);
    try {
      const result = await api.connectContextConnector({
        workspace_id: workspace.id,
        connector: connectorChoice.id,
        credential: connectorCredential.trim(),
        identifier: connectorIdentifier.trim() || undefined,
      });
      setItems((old) => [
        result.connection,
        ...old.filter((item) => item.id !== result.connection.id),
      ]);
      setConnectorCredential("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConnectorBusy(false);
    }
  }
  const modelConnections = items.filter((item) =>
    ["openai", "openai-compatible", "anthropic", "gemini-oauth"].includes(item.provider),
  );
  function openModelModal() {
    setModelProvider("custom");
    setModelName("");
    setModelBaseUrl("");
    setModelApiKey("");
    setModelManualId("");
    setModelDiscovery(null);
    setModelError("");
    setModelOpen(true);
  }
  function chooseModelProvider(value: string) {
    setModelProvider(value);
    const preset = PROVIDERS.find((item) => item.id === value);
    if (preset?.baseUrl) setModelBaseUrl(preset.baseUrl);
    if (!modelName && preset) setModelName(preset.name);
    setModelDiscovery(null);
    setModelError("");
  }
  async function discoverModelApi() {
    const preset = PROVIDERS.find((item) => item.id === modelProvider);
    const baseUrl = normalizeProviderBaseUrl(modelBaseUrl);
    if (!preset || !baseUrl) {
      setModelError(ru ? "Укажите endpoint API." : "Enter the API endpoint.");
      return;
    }
    if (!modelApiKey.trim() && !preset.local) {
      setModelError(ru ? "Укажите API key." : "Enter the API key.");
      return;
    }
    setModelBusy(true);
    setModelError("");
    try {
      const result = await api.discoverConnection({
        provider: preset.protocol === "anthropic" ? "anthropic" : "openai-compatible",
        base_url: baseUrl,
        api_key: modelApiKey.trim(),
      });
      setModelBaseUrl(result.base_url || baseUrl);
      setModelDiscovery(result);
    } catch (e) {
      setModelError((e as Error).message);
    } finally {
      setModelBusy(false);
    }
  }
  async function saveModelApi() {
    const preset = PROVIDERS.find((item) => item.id === modelProvider);
    const availableModels = modelDiscovery?.models.map((item) => item.id) || (modelManualId.trim() ? [modelManualId.trim()] : []);
    if (!workspace || !preset || !availableModels.length) return;
    setModelBusy(true);
    try {
      const connection = await api.createConnection({
        workspace_id: workspace.id,
        name: modelName.trim() || preset.name,
        provider: preset.protocol === "anthropic" ? "anthropic" : "openai-compatible",
        base_url: normalizeProviderBaseUrl(modelBaseUrl),
        api_key: modelApiKey.trim() || null,
        config: {
          preset: preset.id,
          available_models: availableModels,
          active_models: [availableModels[0]],
        },
      });
      setItems((old) => [connection, ...old.filter((item) => item.id !== connection.id)]);
      setModelOpen(false);
    } catch (e) {
      setModelError((e as Error).message);
    } finally {
      setModelBusy(false);
    }
  }
  async function deleteModelApi(connection: Connection) {
    const confirmed = window.confirm(
      ru
        ? `Удалить подключение «${connection.name}»? Агенты останутся, но потеряют этот API.`
        : `Delete “${connection.name}”? Agents will remain, but lose this API connection.`,
    );
    if (!confirmed) return;
    setModelDeleting(connection.id);
    try {
      await api.deleteConnection(connection.id);
      setItems((old) => old.filter((item) => item.id !== connection.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setModelDeleting(null);
    }
  }
  async function syncContext(connection: Connection) {
    setConnectorBusy(true);
    try {
      const result = await api.syncContextConnector(connection.id);
      setItems((old) =>
        old.map((item) =>
          item.id === result.connection.id ? result.connection : item,
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConnectorBusy(false);
    }
  }
  async function revokeContext(connection: Connection) {
    if (!confirmConnectorRevoke) {
      setConfirmConnectorRevoke(true);
      return;
    }
    setConnectorBusy(true);
    try {
      await api.revokeContextConnector(connection.id);
      setItems((old) => old.filter((item) => item.id !== connection.id));
      setConnectorChoice(null);
      setConfirmConnectorRevoke(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setConnectorBusy(false);
    }
  }
  const github = items.find(
    (item) => item.provider === "github" && item.config.auth_method === "oauth2",
  );
  const githubAvailable = Boolean(capabilities?.connectors.github);
  const connectorAvailable = (preset: ContextConnectorPreset) =>
    !preset.oauth || Boolean(capabilities?.connectors[preset.id]);
  const chosenContextConnection = connectorChoice
    ? items.find(
        (item) => item.provider === `connector-${connectorChoice.id}`,
      )
    : null;
  return (
    <div className="connections page">
      <header>
        <div>
          <p className="eyebrow">DATA & TOOL HUB</p>
          <h1>Connections</h1>
          <p>
            {ru
              ? "Подключайте model API, источники знаний и рабочие сервисы команды в одном месте."
              : "Connect model APIs, team knowledge sources and work services in one place."}
          </p>
        </div>
        <div className="connectionactions">
          <button className="primary" onClick={openModelModal}>
            <Bot />
            {ru ? "Добавить model API" : "Add model API"}
          </button>
          <button onClick={() => setMcpOpen(true)}>
            <Plug />
            MCP Hub
          </button>
          <button onClick={() => github ? setGithubOpen(true) : connectGithubOAuth()} disabled={githubBusy || (!github && !githubAvailable)} title={!githubAvailable && !github ? (ru ? "Требуется настройка OAuth на сервере" : "OAuth setup is required on the server") : ""}>
            <Github />
            GitHub
          </button>
        </div>
      </header>
      <section className="modelconnectionsection">
        <div className="connectorsectionhead">
          <div>
            <p className="eyebrow">MODEL RUNTIME</p>
            <h2>{ru ? "Подключённые модели" : "Connected model APIs"}</h2>
          </div>
          <span>
            {ru
              ? "Сохранённые подключения можно назначить любому агенту."
              : "Assign a saved connection to any agent."}
          </span>
        </div>
        {modelConnections.length ? (
          <div className="connectiongrid modelconnectiongrid">
            {modelConnections.map((connection) => {
              const models = Array.isArray(connection.config.available_models)
                ? connection.config.available_models
                : [];
              return (
                <article className="connectioncard connected" key={connection.id}>
                  <div className="providericon"><Bot /></div>
                  <div>
                    <b>{connection.name}</b>
                    <p>{connection.base_url || connection.provider}</p>
                    <div className="modelchips">
                      <span>{connection.provider}</span>
                      <span>{models.length} {ru ? "моделей" : "models"}</span>
                    </div>
                  </div>
                  <div className="modelconnectionactions">
                    <span className="status ready">{ru ? "Готово" : "Ready"}</span>
                    <button
                      className="iconbutton danger"
                      aria-label={ru ? `Удалить ${connection.name}` : `Delete ${connection.name}`}
                      title={ru ? "Удалить подключение" : "Delete connection"}
                      disabled={modelDeleting === connection.id}
                      onClick={() => void deleteModelApi(connection)}
                    >
                      {modelDeleting === connection.id ? <Activity /> : <Trash2 />}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="modelconnectionempty">
            <Bot />
            <span>{ru ? "Пока нет model API. Добавьте первое подключение." : "No model API yet. Add your first connection."}</span>
          </div>
        )}
      </section>
      <div className="connectorsectionhead">
        <div>
          <p className="eyebrow">POPULAR CONNECTORS · {CONTEXT_CONNECTORS.length + 1}</p>
          <h2>{ru ? "Источники контекста команды" : "Team context sources"}</h2>
        </div>
        <span>
          {ru
            ? "После проверки данные попадают в общую Memory"
            : "Verified context is indexed into shared Memory"}
        </span>
      </div>
      <div className="connectiongrid">
        <article
          className={`connectioncard githubcard ${github ? "connected" : ""} ${!githubAvailable && !github ? "unavailable" : ""}`}
          onClick={() => github ? setGithubOpen(true) : githubAvailable ? connectGithubOAuth() : undefined}
        >
          <div className="providericon githubicon">
            <Github />
          </div>
          <div>
            <b>{github ? github.name : "GitHub"}</b>
            <p>
              {github
                ? ru
                  ? "Профиль и репозитории доступны общей памяти"
                  : "Profile and repositories are available to shared memory"
                : ru
                  ? "Репозитории, языки и активность команды"
                  : "Repositories, languages, and team activity"}
            </p>
            {github && (
              <div className="modelchips">
                <span>@{String(github.config.login)}</span>
                <span>
                  {String(github.config.repository_count || 0)} repositories
                </span>
              </div>
            )}
          </div>
          <span className={`status ${github ? "ready" : ""}`}>
            {github
              ? ru
                ? "Подключён"
                : "Connected"
              : !githubAvailable
                ? ru
                  ? "Нужна настройка"
                  : "Setup required"
                : ru
                  ? "Войти"
                  : "Authorize"}
          </span>
        </article>
        {CONTEXT_CONNECTORS.map((preset) => {
          const connected = items.find(
            (item) => item.provider === `connector-${preset.id}`,
          );
          return (
            <button
              type="button"
              className={`connectioncard connectorcatalogcard ${connected ? "connected" : ""} ${!connectorAvailable(preset) && !connected ? "unavailable" : ""}`}
              key={preset.id}
              onClick={() => {
                setConnectorChoice(preset);
                setConnectorCredential("");
                setConnectorIdentifier("");
                setConfigureConnectorTarget(false);
                setConfirmConnectorRevoke(false);
              }}
            >
              <span
                className="providericon"
                style={{ background: `${preset.color}20`, color: preset.color }}
              >
                {preset.short}
              </span>
              <span className="connectorcopy">
                <b>{connected ? connected.name : preset.name}</b>
                <p>
                  {connected
                    ? String(connected.config.summary || "")
                    : ru
                      ? preset.descriptionRu
                      : preset.descriptionEn}
                </p>
                {connected && (
                  <span className="connectorstats">
                    {String(connected.config.item_count || 0)}{" "}
                    {ru ? "объектов" : "items"}
                    {" · "}
                    {Math.round(Number(connected.config.content_bytes || 0) / 1024)} KB
                    {connected.config.synced_at
                      ? ` · ${new Date(String(connected.config.synced_at)).toLocaleString(ru ? "ru-RU" : "en-US", { dateStyle: "short", timeStyle: "short" })}`
                      : ""}
                  </span>
                )}
              </span>
              <span
                className={`status ${connected?.config.sync_status === "ready" ? "ready" : ""}`}
              >
                {connected
                  ? connected.config.sync_status === "error"
                    ? ru
                      ? "Ошибка"
                      : "Error"
                    : ru
                      ? "Синхронизирован"
                      : "Synced"
                  : !connectorAvailable(preset)
                    ? ru
                      ? "Нужна настройка"
                      : "Setup required"
                    : ru
                      ? preset.oauth ? "Войти" : "Подключить"
                      : preset.oauth ? "Authorize" : "Connect"}
              </span>
            </button>
          );
        })}
      </div>
      {githubOpen && github && (
        <div className="modalback" onClick={() => setGithubOpen(false)}>
          <div
            className="modal githubmodal"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">KNOWLEDGE CONNECTOR</p>
                <h2>{ru ? "Аккаунт GitHub" : "GitHub account"}</h2>
              </div>
              <button onClick={() => setGithubOpen(false)}>
                <X />
              </button>
            </header>
            <div className="githubintro">
              <Github />
              <div>
                <b>@{String(github.config.login)}</b>
                <p>
                  {ru
                    ? `${String(github.config.repository_count || 0)} репозиториев синхронизировано с общей Memory.`
                    : `${String(github.config.repository_count || 0)} repositories are synchronized with shared Memory.`}
                </p>
              </div>
            </div>
            <div className="securitynote">
              <ShieldCheck />
              <span>
                {ru
                  ? "Аккаунт подключён через GitHub OAuth. Orbit не получает ваш пароль; доступ можно отозвать здесь или в настройках GitHub."
                  : "Connected through GitHub OAuth. Orbit never receives your password; access can be revoked here or in GitHub settings."}
              </span>
            </div>
            <footer>
              <button
                className={confirmGithubRevoke ? "danger" : ""}
                disabled={githubBusy}
                onClick={() => revokeGithub(github)}
              >
                <Trash2 />
                {confirmGithubRevoke
                  ? ru ? "Нажмите ещё раз" : "Click again to revoke"
                  : ru ? "Отозвать доступ" : "Revoke access"}
              </button>
              <button
                className="primary"
                disabled={githubBusy}
                onClick={() => syncGithub(github)}
              >
                {githubBusy ? (
                  <>
                    <Activity />
                    {ru ? "Обновление…" : "Refreshing…"}
                  </>
                ) : (
                  <>
                    <RotateCcw />
                    {ru ? "Обновить сейчас" : "Refresh now"}
                  </>
                )}
              </button>
            </footer>
          </div>
        </div>
      )}
      {modelOpen && (
        <div className="modalback" onClick={() => setModelOpen(false)}>
          <div className="modal modelapimodal" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <p className="eyebrow">MODEL RUNTIME · OPENAI COMPATIBLE</p>
                <h2>{ru ? "Добавить model API" : "Add a model API"}</h2>
              </div>
              <button onClick={() => setModelOpen(false)}><X /></button>
            </header>
            <p className="modalhint">
              {ru
                ? "Выберите известный сервис или Custom API для нового агрегатора. Orbit сам проверит типичные пути /models, /v1, /openai/v1 и /api/v1."
                : "Choose a known service or Custom API for a new aggregator. Orbit probes common /models, /v1, /openai/v1 and /api/v1 paths automatically."}
            </p>
            <label className="inputlabel">
              <span>{ru ? "Название подключения" : "Connection name"}</span>
              <input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder={ru ? "Например: GLM startup gateway" : "e.g. GLM startup gateway"} />
            </label>
            <label className="inputlabel">
              <span>{ru ? "Провайдер / протокол" : "Provider / protocol"}</span>
              <select value={modelProvider} onChange={(event) => chooseModelProvider(event.target.value)}>
                {PROVIDERS.filter((item) => item.protocol !== "anthropic" || item.id === "anthropic" || item.id === "tabitoken").map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
              {selectedModelPreset && (
                <small className="providerhint">
                  {selectedModelPreset.hint}
                  {modelProvider === "minimax" && (ru
                    ? " Для подписки Token Plan вставьте именно Token Plan API key — он расходует квоту подписки."
                    : " For a Token Plan subscription, paste the Token Plan API key — it uses subscription quota.")}
                  {modelProvider === "gemini" && (ru
                    ? " Подписка Gemini в приложении не заменяет Gemini API key или Google Cloud OAuth."
                    : " A consumer Gemini subscription does not replace a Gemini API key or Google Cloud OAuth.")}
                </small>
              )}
            </label>
            <label className="inputlabel">
              <span>{ru ? "Endpoint или домен API" : "API endpoint or host"}</span>
              <input value={modelBaseUrl} onChange={(event) => { setModelBaseUrl(event.target.value); setModelDiscovery(null); }} placeholder="https://provider.example.com" autoCapitalize="off" autoCorrect="off" spellCheck={false} />
            </label>
            <label className="inputlabel">
              <span>{ru ? "API key" : "API key"}</span>
              <input type="password" value={modelApiKey} onChange={(event) => setModelApiKey(event.target.value)} placeholder={ru ? "Ключ провайдера" : "Provider key"} autoComplete="off" />
            </label>
            <label className="inputlabel">
              <span>{ru ? "ID модели · если каталог недоступен" : "Model ID · if catalog is unavailable"}</span>
              <input value={modelManualId} onChange={(event) => setModelManualId(event.target.value)} placeholder={ru ? "Например: glm-4.5-air" : "e.g. glm-4.5-air"} autoCapitalize="off" autoCorrect="off" spellCheck={false} />
            </label>
            {modelError && <p className="dangertext">{modelError}</p>}
            {modelDiscovery && (
              <div className="modeldiscoveryresult">
                <div><Check /><b>{ru ? "Подключение найдено" : "Connection discovered"}</b><small>{modelDiscovery.base_url}</small></div>
                <span>{modelDiscovery.model_count} {ru ? "моделей" : "models"}</span>
              </div>
            )}
            <footer>
              <button onClick={() => setModelOpen(false)}>{ru ? "Отмена" : "Cancel"}</button>
              {!modelDiscovery ? (
                <>
                  <button disabled={modelBusy || !modelBaseUrl.trim() || !modelManualId.trim()} onClick={() => void saveModelApi()}>
                    {modelBusy ? <Activity /> : <Save />}
                    {ru ? "Сохранить вручную" : "Save manually"}
                  </button>
                  <button className="primary" disabled={modelBusy || !modelBaseUrl.trim()} onClick={() => void discoverModelApi()}>
                    {modelBusy ? <Activity /> : <Search />}
                    {modelBusy ? (ru ? "Проверка…" : "Checking…") : (ru ? "Проверить и найти модели" : "Test & discover models")}
                  </button>
                </>
              ) : (
                <button className="primary" disabled={modelBusy} onClick={() => void saveModelApi()}>
                  {modelBusy ? <Activity /> : <Check />}
                  {ru ? "Сохранить подключение" : "Save connection"}
                </button>
              )}
            </footer>
          </div>
        </div>
      )}
      {connectorChoice && (
        <div className="modalback" onClick={() => setConnectorChoice(null)}>
          <div
            className="modal contextconnectormodal"
            onClick={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p className="eyebrow">VERIFIED CONTEXT CONNECTOR</p>
                <h2>
                  {ru
                    ? `Подключить ${connectorChoice.name}`
                    : `Connect ${connectorChoice.name}`}
                </h2>
              </div>
              <button onClick={() => setConnectorChoice(null)}>
                <X />
              </button>
            </header>
            <div className="connectoridentity">
              <span
                style={{
                  background: `${connectorChoice.color}20`,
                  color: connectorChoice.color,
                }}
              >
                {connectorChoice.short}
              </span>
              <div>
                <b>{ru ? "Что получит команда" : "What the team receives"}</b>
                <p>
                  {ru
                    ? connectorChoice.descriptionRu
                    : connectorChoice.descriptionEn}
                </p>
              </div>
            </div>
            {chosenContextConnection ? (
              <div className="connectorsyncpanel">
                <div>
                  <span>{ru ? "Статус" : "Status"}</span>
                  <b>
                    {String(
                      chosenContextConnection.config.sync_status || "ready",
                    )}
                  </b>
                </div>
                <div>
                  <span>{ru ? "Загружено" : "Imported"}</span>
                  <b>
                    {String(
                      chosenContextConnection.config.item_count || 0,
                    )} {ru ? "объектов" : "items"}
                  </b>
                </div>
                <div>
                  <span>{ru ? "Последнее обновление" : "Last refresh"}</span>
                  <b>
                    {chosenContextConnection.config.synced_at
                      ? new Date(
                          String(chosenContextConnection.config.synced_at),
                        ).toLocaleString(ru ? "ru-RU" : "en-US")
                      : "—"}
                  </b>
                </div>
                {Boolean(chosenContextConnection.config.last_error) && (
                  <p className="connectorsyncerror">
                    {String(chosenContextConnection.config.last_error)}
                  </p>
                )}
              </div>
            ) : null}
            {(!chosenContextConnection || configureConnectorTarget) && !connectorChoice.oauth && (
              <div className="connectorcredentialform">
                {!chosenContextConnection && (
                  <label className="inputlabel">
                    <span>
                      {connectorChoice.credentialLabel || "API key"}
                      {connectorChoice.credentialRequired === false ? ` (${ru ? "необязательно" : "optional"})` : ""}
                    </span>
                    <input
                      type="password"
                      value={connectorCredential}
                      onChange={(event) => setConnectorCredential(event.target.value)}
                      autoComplete="off"
                      placeholder={ru ? "Вставьте ключ" : "Paste API key"}
                    />
                  </label>
                )}
                <label className="inputlabel">
                  <span>{connectorChoice.identifierLabel || (ru ? "Идентификатор" : "Identifier")}</span>
                  <input
                    value={connectorIdentifier}
                    onChange={(event) => setConnectorIdentifier(event.target.value)}
                    placeholder={connectorChoice.identifierPlaceholder || ""}
                    autoCapitalize="off"
                    autoCorrect="off"
                    spellCheck={false}
                  />
                </label>
                {connectorChoice.id === "bitquery" && (
                  <p className="fieldhint">
                    {ru
                      ? "Это только публичный адрес для скана данных. Он не даёт Orbit доступ к кошельку и не нужен для сохранения API-ключа."
                      : "This is only a public address to scan data. It never grants wallet access and is not needed to save the API key."}
                  </p>
                )}
                {connectorChoice.helpUrl && (
                  <a href={connectorChoice.helpUrl} target="_blank" rel="noreferrer">
                    {ru ? "Где получить API-ключ" : "Get an API key"}
                  </a>
                )}
              </div>
            )}
            <div className="securitynote">
              <ShieldCheck />
              <span>
                {connectorChoice.oauth
                  ? ru
                    ? "Вы перейдёте на официальный экран сервиса, войдёте в свой аккаунт и подтвердите доступ. Пароль никогда не передаётся Orbit."
                    : "You will continue to the service's official consent screen, sign in, and approve access. Your password is never shared with Orbit."
                  : ru
                    ? "Ключ шифруется в локальном хранилище Orbit и используется только для прямых запросов к этому API. MCP-сервер или локальный процесс не требуется."
                    : "The key is encrypted in Orbit's local storage and used only for direct requests to this API. No MCP server or local process is required."}
              </span>
            </div>
            {!chosenContextConnection && connectorChoice.oauth && !connectorAvailable(connectorChoice) && (
              <div className="connectorunavailable" role="status">
                <AlertTriangle />
                <span>
                  {ru
                    ? "OAuth-приложение ещё не настроено администратором Orbit. Вводить токены вручную не требуется."
                    : "The Orbit administrator has not configured this OAuth application yet. No manual token is required."}
                </span>
              </div>
            )}
            <footer>
              {chosenContextConnection && !configureConnectorTarget ? (
                <>
                  <button
                    className={confirmConnectorRevoke ? "danger" : ""}
                    disabled={connectorBusy || (connectorChoice.id === "bitquery" && !chosenContextConnection.config.target_configured)}
                    onClick={() => revokeContext(chosenContextConnection)}
                  >
                    <Trash2 />
                    {confirmConnectorRevoke
                      ? ru
                        ? "Нажмите ещё раз для отзыва"
                        : "Click again to revoke"
                      : ru
                        ? "Отозвать доступ"
                        : "Revoke access"}
                  </button>
                  <button
                    className="primary"
                    disabled={connectorBusy || (connectorChoice.id === "bitquery" && !chosenContextConnection.config.target_configured)}
                    onClick={() => syncContext(chosenContextConnection)}
                  >
                    {connectorBusy ? <Activity /> : <RotateCcw />}
                    {ru ? "Обновить сейчас" : "Refresh now"}
                  </button>
                  {connectorChoice.id === "bitquery" && !chosenContextConnection.config.target_configured && (
                    <button
                      className="primary"
                      disabled={connectorBusy}
                      onClick={() => setConfigureConnectorTarget(true)}
                    >
                      <Plug />
                      {ru ? "Выбрать адрес для скана" : "Choose scan address"}
                    </button>
                  )}
                </>
              ) : connectorChoice.oauth ? (
                <button
                  className="primary"
                  disabled={connectorBusy || !connectorAvailable(connectorChoice)}
                  onClick={connectContextOAuth}
                >
                  {connectorBusy ? <Activity /> : <ArrowRightLeft />}
                  {ru
                    ? `Войти через ${connectorChoice.name}`
                    : `Continue with ${connectorChoice.name}`}
                </button>
              ) : (
                <button
                  className="primary"
                  disabled={
                    connectorBusy ||
                    (connectorChoice.identifierRequired !== false && !connectorIdentifier.trim()) ||
                    (!chosenContextConnection && connectorChoice.credentialRequired !== false && !connectorCredential.trim())
                  }
                  onClick={connectContextCredential}
                >
                  {connectorBusy ? <Activity /> : <Plug />}
                  {configureConnectorTarget
                    ? ru ? "Сохранить адрес и запустить скан" : "Save address and start scan"
                    : ru ? `Подключить ${connectorChoice.name}` : `Connect ${connectorChoice.name}`}
                </button>
              )}
            </footer>
          </div>
        </div>
      )}
      {mcpOpen && (
        <div
          className="modalback"
          onClick={() => {
            setMcpOpen(false);
            setMcpChoice(null);
          }}
        >
          <div className="modal mcphub" onClick={(e) => e.stopPropagation()}>
            <header>
              <div>
                <p className="eyebrow">
                  TOOL SERVER CATALOG · {mcpCatalog.length}
                </p>
                <h2>MCP Hub</h2>
              </div>
              <button onClick={() => setMcpOpen(false)}>
                <X />
              </button>
            </header>
            <p className="modalhint">
              {ru
                ? "Установите MCP-сервер, затем добавьте его как Tool-ноду нужного workflow. Операции записи требуют отдельного подтверждения."
                : "Install an MCP server, then add it as a Tool node in the required workflow. Write operations require separate approval."}
            </p>
            <div className="mcpcatalog">
              {mcpCatalog.map((preset) => (
                <button
                  key={preset.id}
                  className={mcpChoice?.id === preset.id ? "active" : ""}
                  onClick={() => {
                    setMcpChoice(preset);
                    setMcpSecret("");
                  }}
                >
                  <span className="mcpbadge">
                    <Plug />
                  </span>
                  <div>
                    <b>
                      {preset.name}
                      {preset.official && <i>OFFICIAL</i>}
                    </b>
                    <small>{preset.description}</small>
                    <em>
                      {preset.transport} · {preset.risk}
                    </em>
                  </div>
                  {mcpChoice?.id === preset.id && <Check />}
                </button>
              ))}
            </div>
            {mcpChoice && (
              <div className="mcpsetup">
                <div>
                  <b>{mcpChoice.name}</b>
                  <small>
                    {mcpChoice.command} {mcpChoice.args.join(" ")}
                  </small>
                </div>
                {mcpChoice.secret_name && (
                  <LabelInput
                    label={mcpChoice.secret_name}
                    value={mcpSecret}
                    set={setMcpSecret}
                    secret
                  />
                )}
                <div className="securitynote">
                  <ShieldCheck />
                  <span>
                    {ru
                      ? "Команда сохраняется как проверенный preset. Секрет не показывается после установки."
                      : "The command is saved as a verified preset. Its secret is never shown after installation."}
                  </span>
                </div>
              </div>
            )}
            <footer>
              <span />
              <button onClick={() => setMcpOpen(false)}>
                {ru ? "Отмена" : "Cancel"}
              </button>
              <button
                className="primary"
                disabled={
                  !mcpChoice ||
                  Boolean(mcpChoice.secret_name && !mcpSecret.trim()) ||
                  mcpBusy
                }
                onClick={installMcp}
              >
                {mcpBusy ? (
                  <>
                    <Activity />
                    {ru ? "Установка…" : "Installing…"}
                  </>
                ) : (
                  <>
                    <Plus />
                    {ru ? "Установить MCP" : "Install MCP"}
                  </>
                )}
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
function LabelInput({
  label,
  value,
  set,
  secret,
  placeholder,
}: {
  label: string;
  value: string;
  set: (v: string) => void;
  secret?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="inputlabel">
      <span>{label}</span>
      <input
        type={secret ? "password" : "text"}
        value={value}
        onChange={(e) => set(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}
