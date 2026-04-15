import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3737",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "cd ../backend && python3 -m uvicorn app.main:app --port 8000",
      port: 8000,
      reuseExistingServer: true,
      timeout: 15000,
    },
    {
      command: "pnpm dev --port 3737",
      port: 3737,
      reuseExistingServer: true,
      timeout: 15000,
    },
  ],
});
