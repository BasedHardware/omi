import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import { createServedCounter } from "../../apps/service/observability/served-count";
import type {
  CheckedOutPostgresConnection,
  PostgresTransactionPool,
  SerializableTransactionOptions,
} from "./connection";
import type { CloseablePostgresTransactionPool } from "./postgresjs";
import { createPostgresFirebaseAuthorizedMemoryServiceProcess } from
  "./firebase-authorized-memory-service-process";
import { POSTGRES_MIGRATIONS } from "./migrations/manifest";
import { createPostgresProductionRuntimeReadiness } from "./production-runtime-readiness";

const deferred = <Value>() => {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>((done) => { resolve = done; });
  return { promise, resolve };
};

const readinessRows = (released = true) => POSTGRES_MIGRATIONS.map((migration) => ({
  server_version_num: "180004",
  database_generation_released: released,
  migration_version: String(migration.version),
  migration_name: migration.name,
  migration_sha256: migration.sha256,
}));

const fixture = (input: Readonly<{
  readiness?: () => Promise<readonly Record<string, unknown>[]>;
  mcp?: () => Promise<Response> | Response;
  close?: () => Promise<void>;
}> = {}) => {
  let closeCalls = 0;
  const pool: CloseablePostgresTransactionPool = Object.freeze({
    async withTransaction<Result>(
      _options: SerializableTransactionOptions,
      callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
    ): Promise<Result> {
      return callback({
        connectionIdentity: Object.freeze({ readiness: true }),
        query: async <Row extends Record<string, unknown>>() =>
          (input.readiness?.() ?? readinessRows()) as Promise<readonly Row[]>,
        execute: async () => { throw new Error("readiness must not mutate PostgreSQL"); },
      });
    },
    tryWithSessionAdvisoryLock: async () => { throw new Error("not used"); },
    close: async () => { closeCalls += 1; await input.close?.(); },
  });
  const service_options = {
    mcp_handler: input.mcp ?? (() => new Response("mcp", { status: 202 })),
    memory_read: {
      authorization: {
        pool,
        project_id: "omi-project",
        runtime_mode: "deployed" as const,
        id_token_adapter: {
          verification_source: "firebase_production" as const,
          verifyIdToken: async () => { throw new Error("raw identity detail"); },
        },
        application_id: "app:memory",
        context_ttl_seconds: 60,
        database_generation_digest: "d".repeat(64),
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: new Uint8Array(32).fill(0x31),
        produce_renders: async () => [],
        verify_cursor: () => { throw new Error("not reached"); },
        issue_cursor: () => { throw new Error("not reached"); },
        trace_sink: () => undefined,
        accepted_coverage_state: "bypassed" as const,
        stm_coverage_state: "bypassed" as const,
      },
    },
    now_epoch_seconds: () => 100,
    counter: createServedCounter(),
  };
  return {
    pool,
    service_options,
    options: {
      pool,
      service_options,
      readiness: createPostgresProductionRuntimeReadiness(pool, "d".repeat(64)),
    },
    closeCalls: () => closeCalls,
  };
};

const request = (path: string, init?: RequestInit) => new Request(`https://memory.invalid${path}`, init);

describe("PostgreSQL Firebase production memory service process kernel", () => {
  test("keeps liveness distinct from readiness and admits the canonical app only after start", async () => {
    const value = fixture();
    const process = createPostgresFirebaseAuthorizedMemoryServiceProcess(value.options);
    expect(await (await process.fetch(request("/health"))).json()).toEqual({ status: "ok" });
    expect((await process.fetch(request("/ready"))).status).toBe(503);
    expect((await process.fetch(request("/v1/memories"))).status).toBe(503);
    expect(process.snapshot()).toEqual({
      version: "production-memory-service-process-v1", phase: "constructed", in_flight: 0,
    });

    await expect(process.start()).resolves.toEqual({ kind: "ready" });
    expect((await process.fetch(request("/ready"))).status).toBe(200);
    const memory = await process.fetch(request("/v1/memories", {
      headers: { authorization: "Bearer invalid.token" },
    }));
    expect(memory.status).toBe(401);
    expect(await memory.text()).toBe('{"error":"unauthorized"}');
    expect(await (await process.fetch(request("/mcp", { method: "POST" }))).text()).toBe("mcp");

    await expect(process.stop()).resolves.toEqual({ kind: "stopped" });
    expect(value.closeCalls()).toBe(1);
    await expect(process.start()).resolves.toEqual({ kind: "unavailable" });
    expect((await process.fetch(request("/ready"))).status).toBe(503);
    expect((await process.fetch(request("/health"))).status).toBe(503);
  });

  test("closes admission before draining an already admitted request", async () => {
    const held = deferred<Response>();
    let mcpCalls = 0;
    const value = fixture({ mcp: () => { mcpCalls += 1; return held.promise; } });
    const process = createPostgresFirebaseAuthorizedMemoryServiceProcess(value.options);
    await process.start();
    const admitted = process.fetch(request("/mcp", { method: "POST" }));
    await Promise.resolve();
    expect(process.snapshot().in_flight).toBe(1);
    const stopping = process.stop();
    expect(process.snapshot().phase).toBe("draining");
    expect(value.closeCalls()).toBe(0);
    expect((await process.fetch(request("/mcp", { method: "POST" }))).status).toBe(503);
    expect(mcpCalls).toBe(1);
    held.resolve(new Response("done"));
    expect(await (await admitted).text()).toBe("done");
    await expect(stopping).resolves.toEqual({ kind: "stopped" });
    expect(value.closeCalls()).toBe(1);
  });

  test("a stop racing readiness can never reopen admission", async () => {
    const ready = deferred<readonly Record<string, unknown>[]>();
    const value = fixture({ readiness: () => ready.promise });
    const process = createPostgresFirebaseAuthorizedMemoryServiceProcess(value.options);
    const starting = process.start();
    const stopping = process.stop();
    expect(process.snapshot().phase).toBe("draining");
    ready.resolve(readinessRows());
    await expect(starting).resolves.toEqual({ kind: "unavailable" });
    await expect(stopping).resolves.toEqual({ kind: "stopped" });
    expect((await process.fetch(request("/v1/memories"))).status).toBe(503);
    expect(value.closeCalls()).toBe(1);
  });

  test("readiness and close failures stay terminal, closed, and replayable", async () => {
    const unavailable = fixture({ readiness: async () => { throw new Error("secret"); } });
    const first = createPostgresFirebaseAuthorizedMemoryServiceProcess(unavailable.options);
    await expect(first.start()).resolves.toEqual({ kind: "unavailable" });
    expect((await first.fetch(request("/ready"))).status).toBe(503);
    await expect(first.stop()).resolves.toEqual({ kind: "stopped" });

    const broken = fixture({ close: async () => { throw new Error("secret"); } });
    const second = createPostgresFirebaseAuthorizedMemoryServiceProcess(broken.options);
    await second.start();
    const one = second.stop();
    const two = second.stop();
    expect(one).toBe(two);
    await expect(one).resolves.toEqual({ kind: "failed" });
    await expect(second.stop()).resolves.toEqual({ kind: "failed" });
    expect(broken.closeCalls()).toBe(1);
    expect(second.snapshot().phase).toBe("failed");
  });

  test("rejects substitution and hostile containers before construction work", () => {
    const value = fixture();
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceProcess({
      ...value.options,
      pool: fixture().pool,
    })).toThrow("invalid PostgreSQL Firebase memory service process options");
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceProcess({
      ...value.options,
      readiness: createPostgresProductionRuntimeReadiness(value.pool, "e".repeat(64)),
    })).toThrow("invalid PostgreSQL production readiness options");
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceProcess(
      new Proxy(value.options, {}) as never,
    )).toThrow();
    let getters = 0;
    const hostile = Object.defineProperty({ ...value.options }, "readiness", {
      enumerable: true,
      get() { getters += 1; return value.options.readiness; },
    });
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceProcess(hostile as never)).toThrow();
    expect(getters).toBe(0);

    const nested = fixture();
    const authorization = Object.defineProperty({
      ...nested.service_options.memory_read.authorization,
    }, "pool", {
      enumerable: true,
      get() { getters += 1; return nested.pool; },
    });
    expect(() => createPostgresFirebaseAuthorizedMemoryServiceProcess({
      ...nested.options,
      service_options: {
        ...nested.service_options,
        memory_read: { ...nested.service_options.memory_read, authorization },
      },
    } as never)).toThrow();
    expect(getters).toBe(0);
  });

  test("snapshots readiness and close methods so later mutation cannot retarget lifecycle", async () => {
    const base = fixture();
    let originalClose = 0;
    let replacementClose = 0;
    const mutablePool: {
      withTransaction: PostgresTransactionPool["withTransaction"];
      tryWithSessionAdvisoryLock: CloseablePostgresTransactionPool["tryWithSessionAdvisoryLock"];
      close: () => Promise<void>;
    } = {
      withTransaction: base.pool.withTransaction,
      tryWithSessionAdvisoryLock: base.pool.tryWithSessionAdvisoryLock,
      close: async () => { originalClose += 1; },
    };
    let readinessCalls = 0;
    mutablePool.withTransaction = async <Result>(
      _options: SerializableTransactionOptions,
      callback: (connection: CheckedOutPostgresConnection) => Promise<Result>,
    ): Promise<Result> => {
      readinessCalls += 1;
      return callback({
        connectionIdentity: Object.freeze({ readiness: true }),
        query: async <Row extends Record<string, unknown>>() =>
          readinessRows() as unknown as readonly Row[],
        execute: async () => { throw new Error("not used"); },
      });
    };
    const mutableOptions = {
      pool: mutablePool,
      readiness: createPostgresProductionRuntimeReadiness(mutablePool, "d".repeat(64)),
      service_options: {
        ...base.service_options,
        memory_read: {
          ...base.service_options.memory_read,
          authorization: {
            ...base.service_options.memory_read.authorization,
            pool: mutablePool,
          },
        },
      },
    };
    const process = createPostgresFirebaseAuthorizedMemoryServiceProcess(mutableOptions);
    mutablePool.withTransaction = async () => { throw new Error("replacement must not run"); };
    mutablePool.close = async () => { replacementClose += 1; };
    await expect(process.start()).resolves.toEqual({ kind: "ready" });
    await expect(process.stop()).resolves.toEqual({ kind: "stopped" });
    expect(readinessCalls).toBe(1);
    expect(originalClose).toBe(1);
    expect(replacementClose).toBe(0);
  });

  test("contains no listener, environment, signal, QA, SQLite, or dev credential composition", () => {
    const source = readFileSync(new URL("./firebase-authorized-memory-service-process.ts", import.meta.url), "utf8");
    for (const forbidden of [
      "Bun.serve", "process.env", "addEventListener(\"SIG", "drivers/sqlite",
      "apps/service/app-facing", "dev-server", "qa-control",
    ]) expect(source).not.toContain(forbidden);
  });
});
