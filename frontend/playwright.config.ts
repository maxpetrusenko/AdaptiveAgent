import { defineConfig } from "@playwright/test";

import { e2eDatabaseUrl } from "./e2e/database";

export default defineConfig({
  testDir: "./e2e",
  globalTeardown: "./e2e/global-teardown.ts",
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3737",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        "uv run python -m app.demo_seed && uv run uvicorn app.main:app --port 8000",
      cwd: "../backend",
      env: {
        DATABASE_URL: e2eDatabaseUrl,
      },
      port: 8000,
      reuseExistingServer: false,
      timeout: 15000,
    },
    {
      command: "pnpm build && pnpm start --port 3737",
      cwd: ".",
      port: 3737,
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
