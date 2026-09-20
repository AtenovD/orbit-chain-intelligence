export interface ProviderPreset {
  id: string;
  name: string;
  short: string;
  baseUrl: string;
  color: string;
  local?: boolean;
  hint: string;
  accountOAuth?: "google";
  protocol?: "openai-compatible" | "anthropic";
  fixedModels?: string[];
  defaultModel?: string;
  consoleUrl?: string;
}

export function connectionModelIds(config: Record<string, unknown>): string[] {
  const available = Array.isArray(config.available_models)
    ? config.available_models
    : [];
  const active = Array.isArray(config.active_models) ? config.active_models : [];
  return [
    ...new Set(
      [...available, ...active].filter(
        (value): value is string => typeof value === "string" && Boolean(value.trim()),
      ),
    ),
  ];
}

export const PROVIDERS: ProviderPreset[] = [
  {
    id: "anthropic",
    name: "Anthropic",
    short: "AI",
    baseUrl: "https://api.anthropic.com/v1",
    color: "#d97757",
    hint: "Claude models through the native Messages API",
    protocol: "anthropic",
  },
  {
    id: "tabitoken",
    name: "TabiToken",
    short: "TT",
    baseUrl: "https://tabitoken.com/v1",
    color: "#f2a65a",
    hint: "Claude-compatible Messages API",
    protocol: "anthropic",
      // The backend loads the complete per-key catalog from /models. This value
      // is only used by legacy TabiToken gateways that do not expose a catalog.
      fixedModels: ["claude-opus-4-8-thinking"],
  },
  {
    id: "openai",
    name: "OpenAI",
    short: "OA",
    baseUrl: "https://api.openai.com/v1",
    color: "#18a77a",
    hint: "GPT and reasoning models",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    short: "GE",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    color: "#78a7ff",
    hint: "API key or official Google account OAuth",
    accountOAuth: "google",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    short: "OR",
    baseUrl: "https://openrouter.ai/api/v1",
    color: "#716ff2",
    hint: "Hundreds of models through one API",
  },
  {
    id: "openrouter-free",
    name: "OpenRouter Free",
    short: "OF",
    baseUrl: "https://openrouter.ai/api/v1",
    color: "#4caf82",
    hint: "Free community models via OpenRouter — no cost, no billing required",
    defaultModel: "openrouter/auto:free",
  },
  {
    id: "agentrouter",
    name: "AgentRouter",
    short: "AR",
    baseUrl: "https://co.agentrouter.org/v1",
    color: "#f1c94a",
    hint: "Multiple AI models through one compatible API — get your key at agentrouter.org/console",
    consoleUrl: "https://agentrouter.org/console",
  },
  {
    id: "groq",
    name: "Groq",
    short: "GQ",
    baseUrl: "https://api.groq.com/openai/v1",
    color: "#f06f43",
    hint: "Fast open-weight inference",
  },
  {
    id: "mistral",
    name: "Mistral AI",
    short: "MI",
    baseUrl: "https://api.mistral.ai/v1",
    color: "#f3a536",
    hint: "Mistral and Codestral models",
  },
  {
    id: "xai",
    name: "xAI",
    short: "xAI",
    baseUrl: "https://api.x.ai/v1",
    color: "#e8e8eb",
    hint: "Grok models",
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    short: "DS",
    baseUrl: "https://api.deepseek.com/v1",
    color: "#4f7cff",
    hint: "DeepSeek chat and reasoning",
  },
  {
    id: "minimax",
    name: "MiniMax",
    short: "MM",
    baseUrl: "https://api.minimax.io/v1",
    color: "#ff6a4d",
    hint: "MiniMax M2 models through the official API",
  },
  {
    id: "kimi",
    name: "Kimi",
    short: "KI",
    baseUrl: "https://api.moonshot.ai/v1",
    color: "#ad7cff",
    hint: "Kimi models through Moonshot's official API",
  },
  {
    id: "together",
    name: "Together AI",
    short: "TO",
    baseUrl: "https://api.together.xyz/v1",
    color: "#7759e8",
    hint: "Hosted open-source models",
  },
  {
    id: "fireworks",
    name: "Fireworks AI",
    short: "FW",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    color: "#ef5d47",
    hint: "Fast serverless inference",
  },
  {
    id: "cerebras",
    name: "Cerebras",
    short: "CB",
    baseUrl: "https://api.cerebras.ai/v1",
    color: "#f0b13e",
    hint: "Ultra-fast inference",
  },
  {
    id: "nvidia",
    name: "NVIDIA NIM",
    short: "NV",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    color: "#76b900",
    hint: "NVIDIA hosted models",
  },
  {
    id: "sambanova",
    name: "SambaNova",
    short: "SN",
    baseUrl: "https://api.sambanova.ai/v1",
    color: "#e94c89",
    hint: "Fast enterprise inference",
  },
  {
    id: "ollama",
    name: "Ollama",
    short: "OL",
    baseUrl: "http://localhost:11434/v1",
    color: "#9da3ad",
    local: true,
    hint: "Local models on your machine",
  },
  {
    id: "lmstudio",
    name: "LM Studio",
    short: "LM",
    baseUrl: "http://localhost:1234/v1",
    color: "#55b0cf",
    local: true,
    hint: "Local OpenAI-compatible server",
  },
  {
    id: "vllm",
    name: "vLLM",
    short: "VL",
    baseUrl: "http://localhost:8001/v1",
    color: "#b07bea",
    local: true,
    hint: "Self-hosted vLLM server",
  },
  {
    id: "custom",
    name: "Custom API",
    short: "+",
    baseUrl: "",
    color: "#7d8390",
    hint: "Any OpenAI-compatible endpoint",
    protocol: "openai-compatible",
  },
];

export function normalizeProviderBaseUrl(value: string): string {
  let trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) return trimmed;
  if (!/^[a-z][a-z\d+.-]*:\/\//i.test(trimmed)) {
    trimmed = /^(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?\b/i.test(trimmed)
      ? `http://${trimmed}`
      : `https://${trimmed}`;
  }
  try {
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname.toLowerCase();
    if (hostname === "agentrouter.org" || hostname === "www.agentrouter.org") {
      return "https://co.agentrouter.org/v1";
    }
    const path = parsed.pathname.replace(/\/+$/, "");
    const withoutOperation = path.replace(/\/(chat\/completions|completions|responses|models)$/i, "");
    return `${parsed.origin}${withoutOperation}`.replace(/\/+$/, "");
  } catch {
    return trimmed;
  }
}
