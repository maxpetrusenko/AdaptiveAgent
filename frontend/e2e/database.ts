import os from "node:os";
import path from "node:path";

const databasePath =
  process.env.ADAPTIVE_AGENT_E2E_DATABASE_PATH ??
  path.join(os.tmpdir(), `adaptive-agent-playwright-${process.pid}.sqlite3`);

process.env.ADAPTIVE_AGENT_E2E_DATABASE_PATH = databasePath;

export const e2eDatabasePath = databasePath;
export const e2eDatabaseUrl = `sqlite+aiosqlite:///${databasePath}`;
export const e2eBackendPort = 8017;
export const e2eBackendUrl = `http://127.0.0.1:${e2eBackendPort}`;
export const e2eResearchDatabasePath = path.join(
  os.tmpdir(),
  `adaptive-agent-research-playwright-${process.pid}.sqlite3`
);
export const e2eKnowledgeIndexPath = path.join(
  os.tmpdir(),
  `adaptive-agent-knowledge-playwright-${process.pid}`
);
