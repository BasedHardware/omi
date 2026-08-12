import { isProxy } from "node:util/types";

import type { DurableMemoryWorkKind } from "../../../core/consolidate/state-machine";
import type {
  OperationalTelemetryEmitter,
  OperationalWorkKind,
} from "../../../core/observability/operational-telemetry";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";

const SOURCE_PORT: unique symbol = Symbol("durable-memory-work-backlog-source");
const MAX_COUNT = 1_000_000_000;
const MAX_AGE_MS = 86_400_000;

export const DURABLE_MEMORY_BACKLOG_WORK_KINDS = Object.freeze([
  "formation", "promotion", "identity_cluster", "predicate_batch",
] as const satisfies readonly DurableMemoryWorkKind[]);

export interface DurableMemoryWorkBacklogRow {
  readonly work_kind: OperationalWorkKind;
  readonly ready: number;
  readonly leased: number;
  readonly retry_wait: number;
  readonly dead: number;
  readonly oldest_ready_age_ms: number | null;
}

export interface DurableMemoryWorkBacklogSnapshot {
  readonly version: "durable-memory-work-backlog-snapshot-v1";
  readonly rows: readonly Readonly<DurableMemoryWorkBacklogRow>[];
}

export interface DurableMemoryWorkBacklogSource {
  readonly [SOURCE_PORT]: true;
  snapshot(context: AuthorizedLedgerWriteContext): Promise<DurableMemoryWorkBacklogSnapshot>;
}

export type DurableMemoryWorkBacklogSourceImplementation = (
  context: AuthorizedLedgerWriteContext,
) => Promise<unknown>;

export type DurableMemoryWorkBacklogEmissionOutcome = Readonly<{
  kind: "available" | "unavailable";
}>;

const fail = (code: string): never => {
  throw new TypeError(`durable memory work backlog ${code}`);
};

const exactRecord = (
  value: unknown,
  expected: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) fail(code);
  const actual = (keys as string[]).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length
    || actual.some((key, index) => key !== wanted[index])) fail(code);
  for (const key of actual) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const count = (value: unknown): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value)
    || value < 0 || value > MAX_COUNT) fail("invalid_snapshot");
  return value;
};

const age = (value: unknown, ready: number): number | null => {
  if (value === null && ready === 0) return null;
  if (typeof value !== "number" || !Number.isSafeInteger(value)
    || value < 0 || value > MAX_AGE_MS || ready === 0) fail("invalid_snapshot");
  return value;
};

const parseSnapshot = (value: unknown): DurableMemoryWorkBacklogSnapshot => {
  const root = exactRecord(value, ["version", "rows"], "invalid_snapshot");
  if (root["version"] !== "durable-memory-work-backlog-snapshot-v1"
    || !Array.isArray(root["rows"]) || isProxy(root["rows"])
    || Object.getPrototypeOf(root["rows"]) !== Array.prototype
    || root["rows"].length !== DURABLE_MEMORY_BACKLOG_WORK_KINDS.length) {
    fail("invalid_snapshot");
  }
  const arrayKeys = Reflect.ownKeys(root["rows"]);
  if (arrayKeys.length !== root["rows"].length + 1) fail("invalid_snapshot");
  const rows = DURABLE_MEMORY_BACKLOG_WORK_KINDS.map((expectedKind, index) => {
    const descriptor = Object.getOwnPropertyDescriptor(root["rows"], String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail("invalid_snapshot");
    const row = exactRecord(descriptor.value, [
      "work_kind", "ready", "leased", "retry_wait", "dead", "oldest_ready_age_ms",
    ], "invalid_snapshot");
    if (row["work_kind"] !== expectedKind) fail("invalid_snapshot");
    const ready = count(row["ready"]);
    return Object.freeze({
      work_kind: expectedKind,
      ready,
      leased: count(row["leased"]),
      retry_wait: count(row["retry_wait"]),
      dead: count(row["dead"]),
      oldest_ready_age_ms: age(row["oldest_ready_age_ms"], ready),
    });
  });
  return Object.freeze({
    version: "durable-memory-work-backlog-snapshot-v1",
    rows: Object.freeze(rows),
  });
};

export const defineDurableMemoryWorkBacklogSource = (
  implementation: DurableMemoryWorkBacklogSourceImplementation,
): DurableMemoryWorkBacklogSource => {
  if (typeof implementation !== "function" || isProxy(implementation)) fail("invalid_source");
  return Object.freeze({
    [SOURCE_PORT]: true as const,
    async snapshot(contextValue): Promise<DurableMemoryWorkBacklogSnapshot> {
      const context = assertAuthorizedLedgerWriteContext(contextValue);
      if (context.capability !== "memories.work.execute") fail("capability_denied");
      return parseSnapshot(await implementation(context));
    },
  });
};

const emitUnavailable = (telemetry: OperationalTelemetryEmitter): void => {
  for (const workKind of DURABLE_MEMORY_BACKLOG_WORK_KINDS) {
    telemetry.emit({
      version: "operational-telemetry-v1",
      family: "backlog",
      work_kind: workKind,
      outcome: "unavailable",
      ready: null,
      leased: null,
      retry_wait: null,
      dead: null,
      oldest_ready_age_ms: null,
    });
  }
};

/**
 * Emits a complete snapshot or four explicit unavailable events. A partial
 * source result is never converted into a fabricated zero.
 */
export const emitDurableMemoryWorkBacklogTelemetry = async (
  source: DurableMemoryWorkBacklogSource,
  context: AuthorizedLedgerWriteContext,
  telemetry: OperationalTelemetryEmitter,
): Promise<DurableMemoryWorkBacklogEmissionOutcome> => {
  let snapshot: DurableMemoryWorkBacklogSnapshot;
  try {
    snapshot = await source.snapshot(context);
  } catch {
    emitUnavailable(telemetry);
    return Object.freeze({ kind: "unavailable" as const });
  }
  for (const row of snapshot.rows) {
    telemetry.emit({
      version: "operational-telemetry-v1",
      family: "backlog",
      work_kind: row.work_kind,
      outcome: "available",
      ready: row.ready,
      leased: row.leased,
      retry_wait: row.retry_wait,
      dead: row.dead,
      oldest_ready_age_ms: row.oldest_ready_age_ms,
    });
  }
  return Object.freeze({ kind: "available" as const });
};
