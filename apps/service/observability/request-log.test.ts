import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Hono } from "hono";

import { createLocalDevService } from "../app-facing";
import {
  attachServiceRequestLog,
  SERVICE_REQUEST_DROPPED_EVENT,
  SERVICE_REQUEST_EVENT,
} from "./request-log";
import type { RuntimeLogInput, RuntimeLogRecord, RuntimeLogSink } from "./runtime-log";

const capturingSink = (): { readonly sink: RuntimeLogSink; readonly records: RuntimeLogRecord[] } => {
  const records: RuntimeLogRecord[] = [];
  return {
    records,
    sink: Object.freeze({
      write(input: RuntimeLogInput): void {
        records.push({
          ts: "2026-08-15T00:00:00.000Z",
          proc: input.proc,
          level: input.level,
          event: input.event,
          ...Object.fromEntries(
            Object.entries(input).filter(([key]) =>
              key !== "ts" && key !== "proc" && key !== "level" && key !== "event"),
          ),
        } as RuntimeLogRecord);
      },
    }),
  };
};

const ticks = (values: number[]): () => number => {
  const remaining = [...values];
  return () => remaining.shift() ?? values[values.length - 1] ?? 0;
};

describe("service request log", () => {
  test("logs method, path, query key names, status, and duration for every fetch", async () => {
    const { sink, records } = capturingSink();
    const app = new Hono();
    app.get("/v1/memories", () => new Response("ok", { status: 200 }));
    attachServiceRequestLog(app, {
      sink,
      nowMs: ticks([100, 112]),
      createRequestId: () => "req-fixed",
    });
    const response = await app.request("/v1/memories?limit=5&cursor=secret-cursor-value");
    expect(response.status).toBe(200);
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({
      proc: "service",
      level: "info",
      event: SERVICE_REQUEST_EVENT,
      method: "GET",
      path: "/v1/memories",
      query_keys: ["limit", "cursor"],
      status: 200,
      duration_ms: 12,
      request_id: "req-fixed",
      owner_account_id: null,
      run_id: null,
    });
    expect(JSON.stringify(records)).not.toContain("secret-cursor-value");
  });

  test("4xx is warn and 5xx is error so --errors can name the failing path", async () => {
    const { sink, records } = capturingSink();
    const app = new Hono();
    app.get("/ok", () => new Response("ok"));
    app.get("/boom", () => new Response("no", { status: 500 }));
    attachServiceRequestLog(app, { sink, createRequestId: () => "req" });
    expect((await app.request("/missing")).status).toBe(404);
    expect((await app.request("/boom")).status).toBe(500);
    expect((await app.request("/ok")).status).toBe(200);
    expect(records.map((record) => [record.level, record.status, record.path])).toEqual([
      ["warn", 404, "/missing"],
      ["error", 500, "/boom"],
      ["info", 200, "/ok"],
    ]);
  });

  test("a route registered after attach still logs — fetch wrap cannot be opted out of", async () => {
    const { sink, records } = capturingSink();
    const app = new Hono();
    attachServiceRequestLog(app, { sink, createRequestId: () => "req" });
    app.get("/later", () => new Response("later"));
    expect((await app.request("/later")).status).toBe(200);
    expect(records).toHaveLength(1);
    expect(records[0]?.path).toBe("/later");
    expect(records[0]?.status).toBe(200);
  });

  test("an Authorization bearer token never appears in the log record", async () => {
    const { sink, records } = capturingSink();
    const token = "secret-bearer-token-xyz-do-not-log";
    const app = new Hono();
    app.get("/v1/memories", () => new Response("ok"));
    attachServiceRequestLog(app, {
      sink,
      createRequestId: () => "req",
      resolveOwnerAccountId: () => "local-dev-user",
    });
    await app.request("/v1/memories", {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(JSON.stringify(records)).not.toContain(token);
    expect(JSON.stringify(records)).not.toContain("Authorization");
    expect(records[0]?.owner_account_id).toBe("local-dev-user");
  });

  test("a Request stand-in without signal still logs and does not throw", async () => {
    const { sink, records } = capturingSink();
    const app = new Hono();
    app.get("/v1/memories", () => new Response("ok"));
    attachServiceRequestLog(app, { sink, createRequestId: () => "req" });
    const standIn = {
      method: "GET",
      url: "http://route-hardening.invalid/v1/memories",
      headers: {
        get(name: string): string | null {
          return name.toLowerCase() === "authorization" ? "Bearer tok" : null;
        },
      },
    };
    const response = await app.fetch(standIn as unknown as Request);
    expect(response.status).toBe(200);
    expect(records).toHaveLength(1);
    expect(records[0]?.path).toBe("/v1/memories");
    expect(records[0]?.status).toBe(200);
  });

  test("dropped connections log a warn line before a response exists", async () => {
    const { sink, records } = capturingSink();
    const app = new Hono();
    app.get("/hang", () => new Response("ok"));
    attachServiceRequestLog(app, { sink, createRequestId: () => "req", nowMs: ticks([1, 4]) });
    const abort = new AbortController();
    abort.abort();
    await app.request("/hang", { signal: abort.signal });
    expect(records).toHaveLength(1);
    expect(records[0]?.event).toBe(SERVICE_REQUEST_DROPPED_EVENT);
    expect(records[0]?.level).toBe("warn");
    expect(records[0]?.path).toBe("/hang");
    expect(records[0]).not.toHaveProperty("status");
  });

  test("the composed local service logs a 404 path and keeps the bearer token off disk", async () => {
    const dir = mkdtempSync(join(tmpdir(), "omi-service-request-log-"));
    const token = "secret-composed-bearer-token-do-not-log";
    try {
      const db = new Database(":memory:");
      const service = createLocalDevService({
        db,
        ownerAccountId: "acct-request-log",
        memoryCount: 1,
        accountTimezone: "UTC",
        devSecretLabel: "request-log-test",
        runtimeLogDir: dir,
      });
      const missing = await service.app.request("/v3/memories", {
        headers: { authorization: `Bearer ${token}` },
      });
      const health = await service.app.request("/health");
      expect(missing.status).toBe(404);
      expect(health.status).toBe(200);
      const file = readFileSync(join(dir, "service.jsonl"), "utf8");
      expect(file).not.toContain(token);
      expect(file).not.toContain(service.devToken);
      const records = file
        .split("\n")
        .filter((line) => line.length > 0)
        .map((line) => JSON.parse(line) as Record<string, unknown>);
      const notFound = records.find((record) => record.path === "/v3/memories");
      const ok = records.find((record) => record.path === "/health");
      expect(notFound).toMatchObject({
        proc: "service",
        level: "warn",
        event: SERVICE_REQUEST_EVENT,
        method: "GET",
        path: "/v3/memories",
        status: 404,
      });
      expect(typeof notFound?.duration_ms).toBe("number");
      expect(ok).toMatchObject({ path: "/health", status: 200, level: "info" });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
