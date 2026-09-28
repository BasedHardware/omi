import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { SqliteAccountLifecycleStore } from "./account-lifecycle";

describe("SQLite account lifecycle adapter", () => {
  test("keeps missing state null and persists explicit lifecycle across reopen", () => {
    const directory = mkdtempSync(join(tmpdir(), "account-lifecycle-"));
    const path = join(directory, "state.sqlite");
    try {
      const firstDb = new Database(path, { create: true });
      const first = new SqliteAccountLifecycleStore(firstDb);
      expect(first.readLifecycle("unknown")).toBeNull();
      first.setLifecycle("account-active", "active");
      first.setLifecycle("account-a", "deletion_pending");
      first.setLifecycle("account-b", "deleted");
      firstDb.close();

      const secondDb = new Database(path);
      const second = new SqliteAccountLifecycleStore(secondDb);
      expect(second.readLifecycle("account-active")).toBe("active");
      expect(second.readLifecycle("account-a")).toBe("deletion_pending");
      expect(second.readLifecycle("account-b")).toBe("deleted");
      secondDb.close();
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
