import { defineConfig } from "@playwright/test";

import {
  e2eDatabaseUrl,
  e2eBackendPort,
  e2eBackendUrl,
  e2eKnowledgeIndexPath,
  e2eResearchDatabasePath,
} from "./e2e/database";

const e2eOperatorToken = "e2e-local-operator-token";

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
        `uv run python -m app.demo_seed && uv run uvicorn app.main:app --port ${e2eBackendPort}`,
      cwd: "../backend",
      env: {
        DATABASE_URL: e2eDatabaseUrl,
        KNOWLEDGE_EMBEDDING_DIMENSIONS: "32",
        KNOWLEDGE_EMBEDDING_PROVIDER: "deterministic",
        KNOWLEDGE_INDEX_PATH: e2eKnowledgeIndexPath,
        RESEARCH_DATABASE_PATH: e2eResearchDatabasePath,
        RESEARCH_PROOF_MODE: "true",
        OPERATOR_API_TOKEN: e2eOperatorToken,
      },
      port: e2eBackendPort,
      reuseExistingServer: false,
      timeout: 15000,
    },
    {
      command: "pnpm build && pnpm start --port 3737",
      cwd: ".",
      env: {
        BACKEND_INTERNAL_URL: e2eBackendUrl,
        NEXT_PUBLIC_API_URL: e2eBackendUrl,
        OPERATOR_API_TOKEN: e2eOperatorToken,
        OPERATOR_PROXY_MODE: "local",
        PROOF_PROXY_MODE: "local",
      },
      port: 3737,
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
});
