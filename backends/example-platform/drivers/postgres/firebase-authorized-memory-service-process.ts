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
  /**
   * `drained` is false when the shutdown deadline expired with requests still
   * in flight. The pool is closed either way — the alternative is being
   * SIGKILLed mid-close — but the two are not the same event and a caller that
   * cannot tell them apart cannot alarm on repeated undrained shutdowns.
   */
  | Readonly<{ kind: "stopped"; drained: boolean }>
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
  /**
   * How long `stop()` waits for in-flight requests before closing the pool
   * anyway, in milliseconds.
   *
   * Required, with no default. `stop()` previously awaited the drain with no
   * bound at all, so a single hung request blocked shutdown until the
   * supervisor's SIGKILL — which is the one shutdown that strands work leases
   * and drops requests. A default here would be a deployment policy smuggled
   * into a driver: the correct value is a property of the supervisor's
   * termination window, which this module cannot see. The caller states it.
   */
  readonly graceful_shutdown_ms: number;
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
  const options = exactRecord(optionsValue, [
    "graceful_shutdown_ms", "pool", "readiness", "service_options",
  ]);
  const gracefulShutdownMs = options["graceful_shutdown_ms"];
  if (!Number.isSafeInteger(gracefulShutdownMs) || (gracefulShutdownMs as number) < 1) fail();
  const shutdownDeadlineMs = gracefulShutdownMs as number;
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

  /** Resolves true when in-flight reached zero, false when the deadline won. */
  const waitForDrain = async (): Promise<boolean> => {
    if (inFlight === 0) return true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const drained = new Promise<boolean>((resolve) => drainWaiters.push(() => resolve(true)));
    const expired = new Promise<boolean>((resolve) => {
      timer = setTimeout(() => resolve(false), shutdownDeadlineMs);
    });
    try {
      return await Promise.race([drained, expired]);
    } finally {
      // Without this the timer keeps the event loop alive for the full deadline
      // after a clean drain, which turns a fast shutdown into a slow one.
      if (timer !== undefined) clearTimeout(timer);
    }
  };

  const stop = (): Promise<ProductionMemoryServiceStopOutcome> => {
    if (stopPromise !== null) return stopPromise;
    if (phase === "stopped") {
      return Promise.resolve(Object.freeze({ kind: "stopped" as const, drained: true }));
    }
    if (phase === "failed") return Promise.resolve(Object.freeze({ kind: "failed" as const }));
    phase = "draining";
    stopPromise = (async () => {
      if (startPromise !== null) await startPromise;
      // Close the pool even when the deadline expires. An undrained close can
      // abort in-flight transactions, but they are serializable and roll back;
      // being SIGKILLed instead leaves the pool unclosed and work leases held
      // until they expire, which is strictly worse.
      const drained = await waitForDrain();
      try {
        await close();
        phase = "stopped";
        return Object.freeze({ kind: "stopped" as const, drained });
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
