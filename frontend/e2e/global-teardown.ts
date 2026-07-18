import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

import { e2eDatabasePath } from "./database";

export default function globalTeardown() {
  const databaseFiles = [
    e2eDatabasePath,
    `${e2eDatabasePath}-shm`,
    `${e2eDatabasePath}-wal`,
  ].filter(existsSync);

  if (databaseFiles.length === 0) {
    return;
  }

  const result = spawnSync("trash", databaseFiles, { stdio: "inherit" });
  if (
    result.error &&
    "code" in result.error &&
    result.error.code === "ENOENT" &&
    process.env.CI === "true"
  ) {
    // GitHub's ephemeral workspace is discarded after the job. Keep local
    // cleanup Trash-only while allowing the same suite to run on Ubuntu.
    return;
  }
  if (result.status !== 0) {
    throw new Error("Could not safely trash the isolated Playwright database.");
  }
}
