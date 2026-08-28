import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, test } from "bun:test";

import { D1_MIGRATIONS } from "../migrations/manifest";
import {
  main,
  parseMigrationPreflightArgs,
  sanitizeDisplayUrl,
  verifyMigrationEvidence,
  verifyMigrations,
} from "../scripts/verify-migrations";

const directory = new URL("../migrations/", import.meta.url);

const latestMigration = D1_MIGRATIONS.at(-1);
if (latestMigration === undefined) {
  throw new Error("D1 migration manifest is empty");
}

const safeEvidence = (evidenceId: string) => ({
  schema_version: latestMigration.name,
  migrations: D1_MIGRATIONS.map((migration) => ({
    name: migration.name,
    sha256: migration.sha256,
  })),
  evidence_id: evidenceId,
});

function startServer(
  handler: (request: Request) => Response | Promise<Response>
) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(new Request(input, init))) as typeof fetch;
  return {
    server: { stop: async () => (globalThis.fetch = originalFetch) },
    url: "https://evidence.example.invalid/migrations",
  };
}

describe("sanitizeDisplayUrl", () => {
  test("redacts a valid endpoint", () => {
    expect(
      sanitizeDisplayUrl("https://user:pass@example.com/evidence?secret=1#frag")
    ).toBe("[endpoint]");
  });

  test("returns placeholder for invalid url", () => {
    expect(sanitizeDisplayUrl("not a url")).toBe("[invalid]");
  });
});

describe("parseMigrationPreflightArgs", () => {
  test("accepts a url and an explicit evidence id", () => {
    expect(
      parseMigrationPreflightArgs([
        "https://evidence.example.invalid/migrations",
        "--evidence",
        "ops-20260818-1",
      ])
    ).toEqual({
      kind: "ok",
      value: {
        evidenceUrl: "https://evidence.example.invalid/migrations",
        evidenceId: "ops-20260818-1",
      },
    });
  });

  test("rejects a missing evidence id", () => {
    expect(
      parseMigrationPreflightArgs([
        "https://evidence.example.invalid/migrations",
      ])
    ).toEqual({ kind: "error", reason: "evidence_id_required" });
  });

  test("rejects malformed evidence and duplicate options", () => {
    expect(
      parseMigrationPreflightArgs([
        "https://evidence.example.invalid/migrations",
        "--evidence",
        "contains space",
      ])
    ).toEqual({ kind: "error", reason: "invalid_evidence_id" });

    expect(
      parseMigrationPreflightArgs([
        "https://evidence.example.invalid/migrations",
        "--evidence",
        "ops-1",
        "--evidence",
        "ops-2",
      ])
    ).toEqual({ kind: "error", reason: "duplicate_option" });
  });
});

describe("verifyMigrationEvidence", () => {
  test("accepts a synthetic safe evidence matching the manifest", () => {
    expect(
      verifyMigrationEvidence(safeEvidence("ops-20260818-1"), "ops-20260818-1")
    ).toEqual({
      kind: "ok",
      schemaVersion: latestMigration.name,
      evidenceId: "ops-20260818-1",
    });
  });

  test("rejects an evidence id that does not match the operator value", () => {
    const result = verifyMigrationEvidence(
      safeEvidence("ops-20260818-1"),
      "ops-20260818-2"
    );
    expect(result).toEqual({
      kind: "error",
      reason: "evidence_id_mismatch",
    });
  });

  test("rejects a missing migration", () => {
    const body = {
      schema_version: latestMigration.name,
      migrations: D1_MIGRATIONS.filter(
        (migration) => migration.version !== 2
      ).map((migration) => ({
        name: migration.name,
        sha256: migration.sha256,
      })),
      evidence_id: "ops-20260818-1",
    };
    expect(verifyMigrationEvidence(body, "ops-20260818-1")).toEqual({
      kind: "error",
      reason: "migration_count_mismatch",
    });
  });

  test("rejects an extra field that could carry a database id or token", () => {
    expect(
      verifyMigrationEvidence(
        {
          ...safeEvidence("ops-20260818-1"),
          database_id: "028f665e-87df-4329-b794-b0811a6e24a4",
        },
        "ops-20260818-1"
      )
    ).toEqual({ kind: "error", reason: "evidence_has_extra_fields" });

    expect(
      verifyMigrationEvidence(
        {
          ...safeEvidence("ops-20260818-1"),
          migrations: [
            ...D1_MIGRATIONS.map((migration) => ({
              name: migration.name,
              sha256: migration.sha256,
              token: "secret",
            })),
          ],
        },
        "ops-20260818-1"
      )
    ).toEqual({ kind: "error", reason: "migration_item_has_extra_fields" });
  });

  test("rejects an out-of-date schema version", () => {
    const body = {
      ...safeEvidence("ops-20260818-1"),
      schema_version: D1_MIGRATIONS[0]!.name,
    };
    expect(verifyMigrationEvidence(body, "ops-20260818-1")).toEqual({
      kind: "error",
      reason: "schema_version_mismatch",
    });
  });

  test("rejects a checksum mismatch", () => {
    const body = {
      ...safeEvidence("ops-20260818-1"),
      migrations: D1_MIGRATIONS.map((migration) =>
        migration.version === 1
          ? { name: migration.name, sha256: "0".repeat(64) }
          : { name: migration.name, sha256: migration.sha256 }
      ),
    };
    expect(verifyMigrationEvidence(body, "ops-20260818-1")).toEqual({
      kind: "error",
      reason: "migration_checksum_mismatch:0001_tasks.sql",
    });
  });
});

describe("verifyMigrations", () => {
  test("accepts a valid evidence endpoint", async () => {
    const { server, url } = startServer(
      () =>
        new Response(JSON.stringify(safeEvidence("ops-20260818-1")), {
          status: 200,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        })
    );
    try {
      const result = await verifyMigrations(url, "ops-20260818-1");
      expect(result.kind).toBe("ok");
      if (result.kind === "ok") {
        expect(result.schemaVersion).toBe(latestMigration.name);
        expect(result.evidenceId).toBe("ops-20260818-1");
      }
    } finally {
      await server.stop();
    }
  });

  test("rejects a non-200 response", async () => {
    const { server, url } = startServer(
      () => new Response("not found", { status: 404 })
    );
    try {
      const result = await verifyMigrations(url, "ops-20260818-1");
      expect(result).toEqual({
        kind: "error",
        reason: "unexpected status 404",
      });
    } finally {
      await server.stop();
    }
  });

  test("rejects a missing no-store cache control", async () => {
    const { server, url } = startServer(
      () =>
        new Response(JSON.stringify(safeEvidence("ops-20260818-1")), {
          status: 200,
          headers: { "content-type": "application/json" },
        })
    );
    try {
      const result = await verifyMigrations(url, "ops-20260818-1");
      expect(result).toEqual({
        kind: "error",
        reason: "cache-control is missing no-store",
      });
    } finally {
      await server.stop();
    }
  });
});

describe("main", () => {
  test("returns 0 for a safe endpoint and logs no credentials", async () => {
    const { server, url } = startServer(
      () =>
        new Response(JSON.stringify(safeEvidence("ops-20260818-1")), {
          status: 200,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        })
    );
    const logs: unknown[] = [];
    const originalLog = console.log;
    console.log = (...args: unknown[]) => logs.push(args);
    try {
      const code = await main([url, "--evidence", "ops-20260818-1"]);
      expect(code).toBe(0);
      expect(logs.length).toBeGreaterThan(0);
      expect(JSON.stringify(logs)).not.toContain("evidence.example.invalid");
    } finally {
      console.log = originalLog;
      await server.stop();
    }
  });

  test("returns 1 for a missing url argument", async () => {
    const errors: unknown[] = [];
    const originalError = console.error;
    console.error = (...args: unknown[]) => errors.push(args);
    try {
      const code = await main([]);
      expect(code).toBe(1);
    } finally {
      console.error = originalError;
    }
  });

  test("redacts the endpoint when the fetch fails", async () => {
    const errors: unknown[] = [];
    const originalError = console.error;
    console.error = (...args: unknown[]) => errors.push(args);
    try {
      const code = await main([
        "https://user:pass@127.0.0.1:1/migrations",
        "--evidence",
        "ops-20260818-1",
      ]);
      expect(code).toBe(1);
      const combined = JSON.stringify(errors);
      expect(combined).not.toContain("user:pass");
    } finally {
      console.error = originalError;
    }
  });
});

describe("D1 migration manifest", () => {
  test("covers the migration files and pins their exact bytes", () => {
    const files = [
      "0001_tasks.sql",
      "0002_chat.sql",
      "0003_attachments.sql",
      "0004_device_sessions.sql",
    ];
    expect(D1_MIGRATIONS.map((migration) => migration.fileName)).toEqual(files);

    for (const migration of D1_MIGRATIONS) {
      const bytes = readFileSync(new URL(migration.fileName, directory));
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(
        migration.sha256
      );
    }
  });
});
