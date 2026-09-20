import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
