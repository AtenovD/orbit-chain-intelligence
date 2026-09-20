import { describe, expect, it } from "vitest";
import {
  connectionModelIds,
  normalizeProviderBaseUrl,
  PROVIDERS,
} from "./providers";

describe("provider catalog", () => {
  it("contains cloud, local and custom connectors", () => {
    expect(PROVIDERS.length).toBeGreaterThanOrEqual(15);
    expect(PROVIDERS.some(provider => provider.id === "openrouter")).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "openrouter-free" && provider.baseUrl === "https://openrouter.ai/api/v1" && provider.defaultModel === "openrouter/auto:free")).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "agentrouter" && provider.baseUrl === "https://co.agentrouter.org/v1")).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "tabitoken" && provider.baseUrl === "https://tabitoken.com/v1" && provider.protocol === "anthropic" && provider.fixedModels?.includes("claude-opus-4-8-thinking"))).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "gemini" && provider.accountOAuth === "google")).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "minimax")).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "kimi")).toBe(true);
    expect(PROVIDERS.some(provider => provider.id === "deepseek")).toBe(true);
    expect(PROVIDERS.some(provider => provider.local)).toBe(true);
    expect(PROVIDERS.at(-1)?.id).toBe("custom");
  });

  it("uses unique provider ids", () => {
    expect(new Set(PROVIDERS.map(provider => provider.id)).size).toBe(PROVIDERS.length);
  });

  it("repairs the obsolete AgentRouter host before discovery", () => {
    expect(normalizeProviderBaseUrl("https://agentrouter.org/v1")).toBe("https://co.agentrouter.org/v1");
    expect(normalizeProviderBaseUrl("https://api.openai.com/v1/")).toBe("https://api.openai.com/v1");
  });

  it("offers the discovered catalogue, not only previously active models", () => {
    expect(
      connectionModelIds({
        available_models: ["model-a", "model-b"],
        active_models: ["model-a", "legacy-model"],
      }),
    ).toEqual(["model-a", "model-b", "legacy-model"]);
  });
});
