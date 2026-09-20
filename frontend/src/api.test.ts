import { afterEach, describe, expect, it, vi } from "vitest";
import { api, setAuthenticationRequiredHandler } from "./api";

describe("API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads workspaces from the normalized API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([{ id: "w1", name: "Orbit", created_at: "2026-01-01" }]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const result = await api.workspaces();
    expect(result[0].name).toBe("Orbit");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workspaces", expect.any(Object));
  });

  it("surfaces backend errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Run not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(api.run("missing")).rejects.toThrow("Run not found");
  });

  it("notifies the app when a protected request loses authentication", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ message: "Authentication required" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const expired=vi.fn();
    const dispose=setAuthenticationRequiredHandler(expired);
    await expect(api.workspaces()).rejects.toMatchObject({status:401});
    expect(expired).toHaveBeenCalledOnce();
    dispose();
  });
});
