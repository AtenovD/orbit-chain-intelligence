import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testIgnore: "auth.spec.ts",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8000",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
