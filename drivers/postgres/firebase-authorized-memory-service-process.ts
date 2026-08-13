import { isProxy } from "node:util/types";

import type { StandardFetchHandler } from "../../apps/service/app";
import {
  createPostgresFirebaseAuthorizedMemoryServiceApp,
  type PostgresFirebaseAuthorizedMemoryServiceAppOptions,
} from "./firebase-authorized-memory-service-app";
import type { CloseablePostgresTransactionPool } from "./postgresjs";
import {
  bindPostgresProductionRuntimeReadiness,
  type PostgresProductionRuntimeReadiness,
} from "./production-runtime-readiness";

export type ProductionMemoryServiceProcessPhase =
  | "constructed"
  | "starting"
  | "ready"
  | "unavailable"
  | "draining"
  | "stopped"
  | "failed";

export interface ProductionMemoryServiceProcessSnapshot {
  readonly version: "production-memory-service-process-v1";
  readonly phase: ProductionMemoryServiceProcessPhase;
  readonly in_flight: number;
}

export type ProductionMemoryServiceStartOutcome =
  | Readonly<{ kind: "ready" }>
  | Readonly<{ kind: "unavailable" }>;

export type ProductionMemoryServiceStopOutcome =
  | Readonly<{ kind: "stopped" }>
  | Readonly<{ kind: "failed" }>;

export interface PostgresFirebaseAuthorizedMemoryServiceProcess {
  readonly fetch: StandardFetchHandler;
  readonly start: () => Promise<ProductionMemoryServiceStartOutcome>;
  readonly stop: () => Promise<ProductionMemoryServiceStopOutcome>;
  readonly snapshot: () => Readonly<ProductionMemoryServiceProcessSnapshot>;
}

export interface PostgresFirebaseAuthorizedMemoryServiceProcessOptions {
  readonly service_options: PostgresFirebaseAuthorizedMemoryServiceAppOptions;
  readonly pool: CloseablePostgresTransactionPool;
  readonly readiness: PostgresProductionRuntimeReadiness;
}

const fail = (): never => { throw new TypeError("invalid PostgreSQL Firebase memory service process options"); };

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const record = value as Record<string, unknown>;
  const ownKeys = Reflect.ownKeys(record);
  if (ownKeys.some((key) => typeof key !== "string")) fail();
  const actual = (ownKeys as string[]).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) fail();
  const result: Record<string, unknown> = {};
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(record, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail();
    result[key] = (descriptor as PropertyDescriptor & { value: unknown }).value;
  }
  return result;
};

const exactRecordWithOptional = (
  value: unknown,
  required: readonly string[],
  optional: readonly string[],
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail();
  const record = value as Record<string, unknown>;
  const allowed = new Set([...required, ...optional]);
  const ownKeys = Reflect.ownKeys(record);
  if (ownKeys.some((key) => typeof key !== "string" || !allowed.has(key))) fail();
  if (!required.every((key) => Object.hasOwn(record, key))) fail();
  const result: Record<string, unknown> = {};
  for (const key of ownKeys as string[]) {
    const descriptor = Object.getOwnPropertyDescriptor(record, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail();
    result[key] = (descriptor as PropertyDescriptor & { value: unknown }).value;
  }
  return result;
};

const nestedAuthorization = (serviceOptions: unknown): Readonly<{
  pool: unknown;
  databaseGenerationDigest: unknown;
}> => {
  const service = exactRecordWithOptional(serviceOptions, [
    "counter", "mcp_handler", "memory_read", "now_epoch_seconds",
  ], ["observability"]);
  const memoryRead = exactRecord(service["memory_read"], ["authorization", "product"]);
  const authorization = exactRecord(memoryRead["authorization"], [
    "application_id", "context_ttl_seconds", "database_generation_digest",
    "id_token_adapter", "pool", "project_id", "runtime_mode",
  ]);
  return Object.freeze({
    pool: authorization["pool"],
    databaseGenerationDigest: authorization["database_generation_digest"],
  });
};

const json = (body: Readonly<Record<string, string>>, status: number): Response => new Response(
  JSON.stringify(body),
  {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json",
    },
  },
);

const unavailable = (): Response => json({ status: "unavailable" }, 503);

export const createPostgresFirebaseAuthorizedMemoryServiceProcess = (
  optionsValue: PostgresFirebaseAuthorizedMemoryServiceProcessOptions,
): PostgresFirebaseAuthorizedMemoryServiceProcess => {
  const options = exactRecord(optionsValue, ["pool", "readiness", "service_options"]);
  const poolValue = options["pool"];
  if (poolValue === null || typeof poolValue !== "object" || isProxy(poolValue)) fail();
  const closeDescriptor = Object.getOwnPropertyDescriptor(poolValue, "close");
  if (!closeDescriptor || !("value" in closeDescriptor)
    || typeof closeDescriptor.value !== "function" || isProxy(closeDescriptor.value)) fail();
  const authorization = nestedAuthorization(options["service_options"]);
  if (authorization.pool !== poolValue
    || typeof authorization.databaseGenerationDigest !== "string") fail();
  const databaseGenerationDigest = authorization.databaseGenerationDigest as string;

  const closeMethod = (closeDescriptor as PropertyDescriptor & { value: () => Promise<void> }).value;
  const close = closeMethod.bind(poolValue);
  const check = bindPostgresProductionRuntimeReadiness(
    options["readiness"],
    poolValue as CloseablePostgresTransactionPool,
    databaseGenerationDigest,
  );
  const app = createPostgresFirebaseAuthorizedMemoryServiceApp(
    options["service_options"] as PostgresFirebaseAuthorizedMemoryServiceAppOptions,
  );

  let phase: ProductionMemoryServiceProcessPhase = "constructed";
  let inFlight = 0;
  let startPromise: Promise<ProductionMemoryServiceStartOutcome> | null = null;
  let stopPromise: Promise<ProductionMemoryServiceStopOutcome> | null = null;
  let drainWaiters: Array<() => void> = [];

  const snapshot = (): Readonly<ProductionMemoryServiceProcessSnapshot> => Object.freeze({
    version: "production-memory-service-process-v1" as const,
    phase,
    in_flight: inFlight,
  });

  const start = (): Promise<ProductionMemoryServiceStartOutcome> => {
    if (phase === "ready") return Promise.resolve(Object.freeze({ kind: "ready" as const }));
    if (phase === "starting" && startPromise !== null) return startPromise;
    if (phase !== "constructed") return Promise.resolve(Object.freeze({ kind: "unavailable" as const }));
    phase = "starting";
    startPromise = (async () => {
      let ready = false;
      try {
        ready = await check() === true;
      } catch {
        ready = false;
      }
      if (phase === "starting") phase = ready ? "ready" : "unavailable";
      return Object.freeze({
        kind: phase === "ready" ? "ready" as const : "unavailable" as const,
      });
    })();
    return startPromise;
  };

  const waitForDrain = async (): Promise<void> => {
    if (inFlight === 0) return;
    await new Promise<void>((resolve) => drainWaiters.push(resolve));
  };

  const stop = (): Promise<ProductionMemoryServiceStopOutcome> => {
    if (stopPromise !== null) return stopPromise;
    if (phase === "stopped") return Promise.resolve(Object.freeze({ kind: "stopped" as const }));
    if (phase === "failed") return Promise.resolve(Object.freeze({ kind: "failed" as const }));
    phase = "draining";
    stopPromise = (async () => {
      if (startPromise !== null) await startPromise;
      await waitForDrain();
      try {
        await close();
        phase = "stopped";
        return Object.freeze({ kind: "stopped" as const });
      } catch {
        phase = "failed";
        return Object.freeze({ kind: "failed" as const });
      }
    })();
    return stopPromise;
  };

  const fetch: StandardFetchHandler = async (request) => {
    if (!(request instanceof Request)) throw new TypeError("invalid production memory service request");
    const path = new URL(request.url).pathname;
    if (path === "/health") {
      return phase === "stopped" || phase === "failed"
        ? unavailable()
        : app.fetch(request);
    }
    if (path === "/ready") {
      return phase === "ready" ? app.fetch(request) : unavailable();
    }
    if (phase !== "ready") return unavailable();
    inFlight += 1;
    try {
      return await app.fetch(request);
    } finally {
      inFlight = Math.max(0, inFlight - 1);
      if (inFlight === 0) {
        const waiters = drainWaiters;
        drainWaiters = [];
        for (const resolve of waiters) resolve();
      }
    }
  };

  return Object.freeze({ fetch, start, stop, snapshot });
};
