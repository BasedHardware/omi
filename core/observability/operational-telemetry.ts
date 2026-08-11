import { isProxy } from "node:util/types";

const MAX_DURATION_MS = 86_400_000;
const MAX_COUNT = 1_000_000_000;
const MAX_ATTEMPT = 1_000_000;
const MAX_SAFE = Number.MAX_SAFE_INTEGER;

export type ServiceOperation =
  | "health"
  | "readiness"
  | "domain_read"
  | "domain_write"
  | "mcp"
  | "listen"
  | "chat"
  | "other";
export type ServiceOutcome = "success" | "denied" | "invalid" | "unavailable" | "failure";
export type HttpStatusClass = "2xx" | "4xx" | "5xx";

export type DatabaseStage = "pool_acquire" | "transaction" | "migration" | "query";
export type DatabaseOutcome =
  | "success"
  | "timeout"
  | "serialization_retryable"
  | "stale_authority"
  | "unavailable"
  | "failure";

export type OperationalWorkKind = "formation" | "promotion" | "identity_cluster" | "predicate_batch";
export type WorkerStage = "lease" | "produce" | "stage" | "append" | "deliver" | "recover";
export type WorkerOutcome =
  | "success"
  | "idle"
  | "retryable"
  | "dead"
  | "stale_lease"
  | "authorization_denied"
  | "failure";

export type FenceDoor = "read" | "write" | "work" | "projection";
export type FenceOutcome =
  | "admitted"
  | "authentication"
  | "authorization"
  | "entitlement"
  | "stale_epoch"
  | "control_unavailable"
  | "stale_lease"
  | "deletion_dominant";

export interface ServiceOperationalTelemetryEvent {
  readonly version: "operational-telemetry-v1";
  readonly family: "service";
  readonly operation: ServiceOperation;
  readonly outcome: ServiceOutcome;
  readonly status_class: HttpStatusClass | null;
  readonly duration_ms: number;
  readonly in_flight: number;
}

export interface DatabasePoolSnapshot {
  readonly active: number;
  readonly idle: number;
  readonly waiting: number;
}

export interface DatabaseOperationalTelemetryEvent {
  readonly version: "operational-telemetry-v1";
  readonly family: "database";
  readonly stage: DatabaseStage;
  readonly outcome: DatabaseOutcome;
  readonly duration_ms: number;
  readonly pool: Readonly<DatabasePoolSnapshot> | null;
}

export interface WorkerOperationalTelemetryEvent {
  readonly version: "operational-telemetry-v1";
  readonly family: "worker";
  readonly work_kind: OperationalWorkKind;
  readonly stage: WorkerStage;
  readonly outcome: WorkerOutcome;
  readonly duration_ms: number;
  readonly attempt: number | null;
  readonly producer_calls: number;
  readonly materialization_attempts: number;
}

export interface FenceOperationalTelemetryEvent {
  readonly version: "operational-telemetry-v1";
  readonly family: "fence";
  readonly door: FenceDoor;
  readonly outcome: FenceOutcome;
  readonly preserved_envelope: boolean;
}

export interface BacklogOperationalTelemetryEvent {
  readonly version: "operational-telemetry-v1";
  readonly family: "backlog";
  readonly work_kind: OperationalWorkKind;
  readonly outcome: "available" | "unavailable";
  readonly ready: number | null;
  readonly leased: number | null;
  readonly retry_wait: number | null;
  readonly dead: number | null;
  readonly oldest_ready_age_ms: number | null;
}

export type OperationalTelemetryEvent =
  | ServiceOperationalTelemetryEvent
  | DatabaseOperationalTelemetryEvent
  | WorkerOperationalTelemetryEvent
  | FenceOperationalTelemetryEvent
  | BacklogOperationalTelemetryEvent;

export type OperationalTelemetrySink = (event: OperationalTelemetryEvent) => void;
export type OperationalTelemetryEmitResult = "emitted" | "not_emitted";

export interface OperationalTelemetryHealth {
  readonly version: "operational-telemetry-health-v1";
  readonly emitted: number;
  readonly rejected: number;
  readonly dropped: number;
}

export interface OperationalTelemetryEmitter {
  emit(input: unknown): OperationalTelemetryEmitResult;
  health(): OperationalTelemetryHealth;
}

const SERVICE_OPERATIONS: ReadonlySet<string> = new Set<ServiceOperation>([
  "health", "readiness", "domain_read", "domain_write", "mcp", "listen", "chat", "other",
]);
const SERVICE_OUTCOMES: ReadonlySet<string> = new Set<ServiceOutcome>([
  "success", "denied", "invalid", "unavailable", "failure",
]);
const STATUS_CLASSES: ReadonlySet<string> = new Set<HttpStatusClass>(["2xx", "4xx", "5xx"]);
const DATABASE_STAGES: ReadonlySet<string> = new Set<DatabaseStage>([
  "pool_acquire", "transaction", "migration", "query",
]);
const DATABASE_OUTCOMES: ReadonlySet<string> = new Set<DatabaseOutcome>([
  "success", "timeout", "serialization_retryable", "stale_authority", "unavailable", "failure",
]);
const WORK_KINDS: ReadonlySet<string> = new Set<OperationalWorkKind>([
  "formation", "promotion", "identity_cluster", "predicate_batch",
]);
const WORKER_STAGES: ReadonlySet<string> = new Set<WorkerStage>([
  "lease", "produce", "stage", "append", "deliver", "recover",
]);
const WORKER_OUTCOMES: ReadonlySet<string> = new Set<WorkerOutcome>([
  "success", "idle", "retryable", "dead", "stale_lease", "authorization_denied", "failure",
]);
const FENCE_DOORS: ReadonlySet<string> = new Set<FenceDoor>(["read", "write", "work", "projection"]);
const FENCE_OUTCOMES: ReadonlySet<string> = new Set<FenceOutcome>([
  "admitted", "authentication", "authorization", "entitlement", "stale_epoch",
  "control_unavailable", "stale_lease", "deletion_dominant",
]);

const exactRecord = (
  value: unknown,
  expectedKeys: readonly string[],
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) {
    throw new TypeError("operational telemetry event invalid");
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError("operational telemetry event invalid");
  }
  const keys = Reflect.ownKeys(value);
  if (keys.length !== expectedKeys.length
    || keys.some((key) => typeof key !== "string" || !expectedKeys.includes(key))) {
    throw new TypeError("operational telemetry event invalid");
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      throw new TypeError("operational telemetry event invalid");
    }
  }
  return value as Record<string, unknown>;
};

const member = <Value extends string>(
  value: unknown,
  values: ReadonlySet<string>,
): Value => {
  if (typeof value !== "string" || !values.has(value)) {
    throw new TypeError("operational telemetry event invalid");
  }
  return value as Value;
};

const integer = (value: unknown, maximum = MAX_COUNT): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0 || value > maximum) {
    throw new TypeError("operational telemetry event invalid");
  }
  return value;
};

const nullableInteger = (value: unknown, maximum = MAX_COUNT): number | null =>
  value === null ? null : integer(value, maximum);

const taggedRecord = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) {
    throw new TypeError("operational telemetry event invalid");
  }
  const prototype = Object.getPrototypeOf(value);
  const family = Object.getOwnPropertyDescriptor(value, "family");
  if ((prototype !== Object.prototype && prototype !== null)
    || !family || !("value" in family) || !family.enumerable) {
    throw new TypeError("operational telemetry event invalid");
  }
  return value as Record<string, unknown>;
};

const parseService = (value: unknown): ServiceOperationalTelemetryEvent => {
  const event = exactRecord(value, [
    "version", "family", "operation", "outcome", "status_class", "duration_ms", "in_flight",
  ]);
  if (event.version !== "operational-telemetry-v1" || event.family !== "service") {
    throw new TypeError("operational telemetry event invalid");
  }
  const outcome = member<ServiceOutcome>(event.outcome, SERVICE_OUTCOMES);
  const statusClass = event.status_class === null
    ? null
    : member<HttpStatusClass>(event.status_class, STATUS_CLASSES);
  if (outcome === "success" ? statusClass !== "2xx" : statusClass === "2xx") {
    throw new TypeError("operational telemetry event invalid");
  }
  return Object.freeze({
    version: "operational-telemetry-v1",
    family: "service",
    operation: member<ServiceOperation>(event.operation, SERVICE_OPERATIONS),
    outcome,
    status_class: statusClass,
    duration_ms: integer(event.duration_ms, MAX_DURATION_MS),
    in_flight: integer(event.in_flight),
  });
};

const parsePool = (value: unknown): Readonly<DatabasePoolSnapshot> | null => {
  if (value === null) return null;
  const pool = exactRecord(value, ["active", "idle", "waiting"]);
  return Object.freeze({
    active: integer(pool.active),
    idle: integer(pool.idle),
    waiting: integer(pool.waiting),
  });
};

const parseDatabase = (value: unknown): DatabaseOperationalTelemetryEvent => {
  const event = exactRecord(value, ["version", "family", "stage", "outcome", "duration_ms", "pool"]);
  if (event.version !== "operational-telemetry-v1" || event.family !== "database") {
    throw new TypeError("operational telemetry event invalid");
  }
  return Object.freeze({
    version: "operational-telemetry-v1",
    family: "database",
    stage: member<DatabaseStage>(event.stage, DATABASE_STAGES),
    outcome: member<DatabaseOutcome>(event.outcome, DATABASE_OUTCOMES),
    duration_ms: integer(event.duration_ms, MAX_DURATION_MS),
    pool: parsePool(event.pool),
  });
};

const parseWorker = (value: unknown): WorkerOperationalTelemetryEvent => {
  const event = exactRecord(value, [
    "version", "family", "work_kind", "stage", "outcome", "duration_ms", "attempt",
    "producer_calls", "materialization_attempts",
  ]);
  if (event.version !== "operational-telemetry-v1" || event.family !== "worker") {
    throw new TypeError("operational telemetry event invalid");
  }
  const outcome = member<WorkerOutcome>(event.outcome, WORKER_OUTCOMES);
  const attempt = nullableInteger(event.attempt, MAX_ATTEMPT);
  if ((outcome === "idle") !== (attempt === null) || (attempt !== null && attempt < 1)) {
    throw new TypeError("operational telemetry event invalid");
  }
  return Object.freeze({
    version: "operational-telemetry-v1",
    family: "worker",
    work_kind: member<OperationalWorkKind>(event.work_kind, WORK_KINDS),
    stage: member<WorkerStage>(event.stage, WORKER_STAGES),
    outcome,
    duration_ms: integer(event.duration_ms, MAX_DURATION_MS),
    attempt,
    producer_calls: integer(event.producer_calls, MAX_ATTEMPT),
    materialization_attempts: integer(event.materialization_attempts, MAX_ATTEMPT),
  });
};

const parseFence = (value: unknown): FenceOperationalTelemetryEvent => {
  const event = exactRecord(value, ["version", "family", "door", "outcome", "preserved_envelope"]);
  if (event.version !== "operational-telemetry-v1" || event.family !== "fence"
    || typeof event.preserved_envelope !== "boolean") {
    throw new TypeError("operational telemetry event invalid");
  }
  const outcome = member<FenceOutcome>(event.outcome, FENCE_OUTCOMES);
  if (outcome === "admitted" && event.preserved_envelope) {
    throw new TypeError("operational telemetry event invalid");
  }
  return Object.freeze({
    version: "operational-telemetry-v1",
    family: "fence",
    door: member<FenceDoor>(event.door, FENCE_DOORS),
    outcome,
    preserved_envelope: event.preserved_envelope,
  });
};

const parseBacklog = (value: unknown): BacklogOperationalTelemetryEvent => {
  const event = exactRecord(value, [
    "version", "family", "work_kind", "outcome", "ready", "leased", "retry_wait", "dead",
    "oldest_ready_age_ms",
  ]);
  if (event.version !== "operational-telemetry-v1" || event.family !== "backlog"
    || (event.outcome !== "available" && event.outcome !== "unavailable")) {
    throw new TypeError("operational telemetry event invalid");
  }
  const ready = nullableInteger(event.ready);
  const leased = nullableInteger(event.leased);
  const retryWait = nullableInteger(event.retry_wait);
  const dead = nullableInteger(event.dead);
  const oldest = nullableInteger(event.oldest_ready_age_ms, MAX_DURATION_MS);
  if (event.outcome === "unavailable") {
    if (ready !== null || leased !== null || retryWait !== null || dead !== null || oldest !== null) {
      throw new TypeError("operational telemetry event invalid");
    }
  } else if (ready === null || leased === null || retryWait === null || dead === null
    || (ready === 0 ? oldest !== null : oldest === null)) {
    throw new TypeError("operational telemetry event invalid");
  }
  return Object.freeze({
    version: "operational-telemetry-v1",
    family: "backlog",
    work_kind: member<OperationalWorkKind>(event.work_kind, WORK_KINDS),
    outcome: event.outcome,
    ready,
    leased,
    retry_wait: retryWait,
    dead,
    oldest_ready_age_ms: oldest,
  });
};

/** Exact-shaped, content-free event builder. No caller-owned object survives. */
export const buildOperationalTelemetryEvent = (input: unknown): OperationalTelemetryEvent => {
  const root = taggedRecord(input);
  switch (root.family) {
    case "service": return parseService(root);
    case "database": return parseDatabase(root);
    case "worker": return parseWorker(root);
    case "fence": return parseFence(root);
    case "backlog": return parseBacklog(root);
    default: throw new TypeError("operational telemetry event invalid");
  }
};

const incrementSaturated = (value: number): number => value >= MAX_SAFE ? MAX_SAFE : value + 1;

/**
 * The sink is an optional, synchronous enqueue seam. Rejection or sink failure
 * is counted locally and never changes the instrumented operation.
 */
export const createOperationalTelemetryEmitter = (
  sink?: OperationalTelemetrySink,
): OperationalTelemetryEmitter => {
  let emitted = 0;
  let rejected = 0;
  let dropped = 0;
  return Object.freeze({
    emit(input: unknown): OperationalTelemetryEmitResult {
      let event: OperationalTelemetryEvent;
      try {
        event = buildOperationalTelemetryEvent(input);
      } catch {
        rejected = incrementSaturated(rejected);
        return "not_emitted";
      }
      if (!sink) {
        dropped = incrementSaturated(dropped);
        return "not_emitted";
      }
      try {
        const result = sink(event);
        if (result !== undefined) {
          const candidate = result as unknown;
          if (candidate !== null && typeof candidate === "object"
            && typeof Reflect.get(candidate, "then") === "function") {
            void Promise.resolve(candidate).catch(() => {});
          }
          dropped = incrementSaturated(dropped);
          return "not_emitted";
        }
        emitted = incrementSaturated(emitted);
        return "emitted";
      } catch {
        dropped = incrementSaturated(dropped);
        return "not_emitted";
      }
    },
    health(): OperationalTelemetryHealth {
      return Object.freeze({
        version: "operational-telemetry-health-v1",
        emitted,
        rejected,
        dropped,
      });
    },
  });
};
