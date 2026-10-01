import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  formatRuntimeLogLine,
  readRuntimeLogs,
  runDevLogsCli,
} from "./dev-logs";

const scratch = (): string => mkdtempSync(join(tmpdir(), "omi-dev-logs-"));

const writeJsonl = (path: string, records: readonly Record<string, unknown>[]): void => {
  writeFileSync(
    path,
    records.map((record) => JSON.stringify(record)).join("\n") + (records.length > 0 ? "\n" : ""),
  );
};

describe("dev logs reader", () => {
  test("merges events across process files by timestamp, not file order", () => {
    const dir = scratch();
    try {
      writeJsonl(join(dir, "gateway.jsonl"), [{
        ts: "2026-08-15T00:00:02.000Z",
        proc: "gateway",
        level: "info",
        event: "gateway.ready",
      }]);
      writeJsonl(join(dir, "service.jsonl"), [
        {
          ts: "2026-08-15T00:00:03.000Z",
          proc: "service",
          level: "info",
          event: "service.request",
          method: "GET",
          path: "/health",
          status: 200,
          duration_ms: 1,
        },
        {
          ts: "2026-08-15T00:00:01.000Z",
          proc: "service",
          level: "info",
          event: "service.boot",
          persona: "qa",
        },
      ]);
      const merged = readRuntimeLogs({ dir, limit: 10 });
      expect(merged.map((record) => record.event)).toEqual([
        "service.boot",
        "gateway.ready",
        "service.request",
      ]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("missing files and a missing directory degrade to an empty list", () => {
    expect(readRuntimeLogs({ dir: join(tmpdir(), "omi-dev-logs-absent-never-created") })).toEqual([]);
    const dir = scratch();
    try {
      mkdirSync(dir, { recursive: true });
      writeJsonl(join(dir, "service.jsonl"), [{
        ts: "2026-08-15T00:00:01.000Z",
        proc: "service",
        level: "warn",
        event: "service.request",
        method: "GET",
        path: "/v3/memories",
        status: 404,
        duration_ms: 2,
      }]);
      expect(readRuntimeLogs({ dir, proc: "chat" })).toEqual([]);
      expect(readRuntimeLogs({ dir, proc: "service" }).map((record) => record.path)).toEqual(["/v3/memories"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("--errors names the 404 path and --json is parseable", () => {
    const dir = scratch();
    try {
      writeJsonl(join(dir, "service.jsonl"), [
        {
          ts: "2026-08-15T00:00:01.000Z",
          proc: "service",
          level: "info",
          event: "service.request",
          method: "GET",
          path: "/health",
          status: 200,
          duration_ms: 1,
        },
        {
          ts: "2026-08-15T00:00:02.000Z",
          proc: "service",
          level: "warn",
          event: "service.request",
          method: "GET",
          path: "/v3/memories",
          status: 404,
          duration_ms: 3,
        },
      ]);
      writeFileSync(join(dir, "shell.jsonl"), "{not-json\n");
      const errors = runDevLogsCli(["--dir", dir, "--errors"]);
      expect(errors.code).toBe(0);
      expect(errors.stdout).toContain("GET /v3/memories 404");
      expect(errors.stdout).not.toContain("/health");
      const json = runDevLogsCli(["--dir", dir, "--errors", "--json"]);
      expect(json.code).toBe(0);
      const parsed = JSON.parse(json.stdout) as readonly Record<string, unknown>[];
      expect(parsed).toHaveLength(1);
      expect(parsed[0]).toMatchObject({ path: "/v3/memories", status: 404, level: "warn" });
      expect(formatRuntimeLogLine(parsed[0] as never)).toContain("service.request GET /v3/memories 404 3ms");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("filters by proc, event, and since without requiring a running stack", () => {
    const dir = scratch();
    try {
      writeJsonl(join(dir, "service.jsonl"), [
        { ts: "2026-08-15T00:00:01.000Z", proc: "service", level: "info", event: "service.boot" },
        { ts: "2026-08-15T00:00:03.000Z", proc: "service", level: "info", event: "service.ready" },
      ]);
      writeJsonl(join(dir, "chat.jsonl"), [
        { ts: "2026-08-15T00:00:02.000Z", proc: "chat", level: "error", event: "chat.generation.failed" },
      ]);
      const since = runDevLogsCli(["--dir", dir, "--since", "2026-08-15T00:00:02.000Z", "--limit", "20"]);
      expect(JSON.parse(runDevLogsCli(["--dir", dir, "--json", "--limit", "20"]).stdout).map((row: { event: string }) => row.event)).toEqual([
        "service.boot",
        "chat.generation.failed",
        "service.ready",
      ]);
      expect(since.stdout).not.toContain("service.boot");
      expect(since.stdout).toContain("service.ready");
      expect(runDevLogsCli(["--dir", dir, "--event", "service.boot"]).stdout).toContain("service.boot");
      expect(runDevLogsCli(["--dir", dir, "--event", "service.boot"]).stdout).not.toContain("service.ready");
      expect(runDevLogsCli(["--dir", dir, "--proc", "nope"]).code).toBe(2);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
