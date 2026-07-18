import os from "node:os";
import path from "node:path";

const databasePath =
  process.env.ADAPTIVE_AGENT_E2E_DATABASE_PATH ??
  path.join(os.tmpdir(), `adaptive-agent-playwright-${process.pid}.sqlite3`);

process.env.ADAPTIVE_AGENT_E2E_DATABASE_PATH = databasePath;

export const e2eDatabasePath = databasePath;
export const e2eDatabaseUrl = `sqlite+aiosqlite:///${databasePath}`;
