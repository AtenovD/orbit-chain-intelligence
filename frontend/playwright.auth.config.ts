import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "auth.spec.ts",
  timeout: 30_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8010",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
