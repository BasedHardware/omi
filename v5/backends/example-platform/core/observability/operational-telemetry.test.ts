import { describe, expect, test } from "bun:test";

import {
  buildOperationalTelemetryEvent,
  createOperationalTelemetryEmitter,
  type OperationalTelemetryEvent,
} from "./operational-telemetry";

const service = () => ({
  version: "operational-telemetry-v1",
  family: "service",
  operation: "domain_read",
  outcome: "success",
  status_class: "2xx",
  duration_ms: 17,
  in_flight: 2,
});

const database = () => ({
  version: "operational-telemetry-v1",
  family: "database",
  stage: "transaction",
  outcome: "success",
  duration_ms: 23,
  pool: { active: 2, idle: 3, waiting: 0 },
});

const worker = () => ({
  version: "operational-telemetry-v1",
  family: "worker",
  work_kind: "formation",
  stage: "append",
  outcome: "success",
  duration_ms: 31,
  attempt: 2,
  producer_calls: 1,
  materialization_attempts: 2,
});

const fence = () => ({
  version: "operational-telemetry-v1",
  family: "fence",
  door: "write",
  outcome: "stale_epoch",
  preserved_envelope: true,
});

const backlog = () => ({
  version: "operational-telemetry-v1",
  family: "backlog",
  work_kind: "formation",
  outcome: "available",
  ready: 4,
  leased: 2,
  retry_wait: 1,
  dead: 3,
  oldest_ready_age_ms: 71,
});

describe("content-safe operational telemetry", () => {
  test("builds one exact detached deeply frozen event per family", () => {
    const databaseInput = database();
    const events = [service(), databaseInput, worker(), fence(), backlog()].map(
      buildOperationalTelemetryEvent,
    );
    databaseInput.pool.active = 999;

    expect(events.map((event) => event.family)).toEqual([
      "service", "database", "worker", "fence", "backlog",
    ]);
    for (const event of events) expect(Object.isFrozen(event)).toBe(true);
    expect(Object.isFrozen((events[1] as { pool: object }).pool)).toBe(true);
    expect((events[1] as { pool: { active: number } }).pool.active).toBe(2);
    expect(JSON.stringify(events)).toBe(JSON.stringify([
      service(), database(), worker(), fence(), backlog(),
    ]));
  });

  test("rejects extras, missing keys, unknown enums, and contradictions", () => {
    expect(() => buildOperationalTelemetryEvent({ ...service(), owner_id: "secret" })).toThrow();
    const missing = service() as Record<string, unknown>;
    delete missing.in_flight;
    expect(() => buildOperationalTelemetryEvent(missing)).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...service(), operation: "raw-route" })).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...service(), outcome: "failure" })).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...fence(), outcome: "admitted" })).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...worker(), outcome: "idle" })).toThrow();
  });

  test("rejects invalid numeric boundaries", () => {
    for (const value of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, 1_000_000_001]) {
      expect(() => buildOperationalTelemetryEvent({ ...service(), in_flight: value })).toThrow();
    }
    expect(() => buildOperationalTelemetryEvent({ ...service(), duration_ms: 86_400_001 })).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...worker(), attempt: 0 })).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...worker(), attempt: null })).toThrow();
  });

  test("backlog unavailable is never a fabricated zero and ready age is coherent", () => {
    const unavailable = { ...backlog(), outcome: "unavailable", ready: null, leased: null,
      retry_wait: null, dead: null, oldest_ready_age_ms: null };
    expect(buildOperationalTelemetryEvent(unavailable).family).toBe("backlog");
    expect(() => buildOperationalTelemetryEvent({ ...unavailable, ready: 0 })).toThrow();
    expect(() => buildOperationalTelemetryEvent({ ...backlog(), ready: 0 })).toThrow();
    expect(buildOperationalTelemetryEvent({ ...backlog(), ready: 0, oldest_ready_age_ms: null }).family)
      .toBe("backlog");
  });

  test("rejects accessors, proxies, classes, and nested accessors without execution", () => {
    let accessed = false;
    const accessor = service() as Record<string, unknown>;
    Object.defineProperty(accessor, "duration_ms", {
      enumerable: true,
      get: () => { accessed = true; return 1; },
    });
    expect(() => buildOperationalTelemetryEvent(accessor)).toThrow();
    expect(accessed).toBe(false);

    const proxy = new Proxy(service(), { ownKeys: () => { throw new Error("trap"); } });
    expect(() => buildOperationalTelemetryEvent(proxy)).toThrow();

    class EventClass {}
    expect(() => buildOperationalTelemetryEvent(Object.assign(new EventClass(), service()))).toThrow();

    const nested = database();
    Object.defineProperty(nested.pool, "active", {
      enumerable: true,
      get: () => { accessed = true; return 1; },
    });
    expect(() => buildOperationalTelemetryEvent(nested)).toThrow();
    expect(accessed).toBe(false);
  });

  test("serialized events contain none of the hostile content corpus", () => {
    const encoded = JSON.stringify([
      buildOperationalTelemetryEvent(service()),
      buildOperationalTelemetryEvent(database()),
      buildOperationalTelemetryEvent(worker()),
      buildOperationalTelemetryEvent(fence()),
      buildOperationalTelemetryEvent(backlog()),
    ]);
    for (const sentinel of [
      "owner:alice", "Bearer secret", "SELECT * FROM memories", "patient discussed anxiety",
      "provider echoed prompt", "\u001b[31m", "stack at service.ts:99", "/v1/memories?query=",
    ]) expect(encoded).not.toContain(sentinel);
  });

  test("emitter isolates missing, throwing, async, and malformed sinks", async () => {
    const missing = createOperationalTelemetryEmitter();
    expect(missing.emit(service())).toBe("not_emitted");
    expect(missing.health()).toEqual({
      version: "operational-telemetry-health-v1", emitted: 0, rejected: 0, dropped: 1,
    });

    const throwing = createOperationalTelemetryEmitter(() => { throw new Error("raw secret"); });
    expect(throwing.emit(service())).toBe("not_emitted");
    expect(throwing.emit({ ...service(), raw_error: "raw secret" })).toBe("not_emitted");
    expect(throwing.health()).toEqual({
      version: "operational-telemetry-health-v1", emitted: 0, rejected: 1, dropped: 1,
    });

    const asyncSink = createOperationalTelemetryEmitter((() => Promise.reject(new Error("secret"))) as never);
    expect(asyncSink.emit(service())).toBe("not_emitted");
    await Promise.resolve();
    expect(asyncSink.health().dropped).toBe(1);
  });

  test("valid sink receives only the verified event and health is independent", () => {
    const events: OperationalTelemetryEvent[] = [];
    const emitter = createOperationalTelemetryEmitter((event) => { events.push(event); });
    expect(emitter.emit(service())).toBe("emitted");
    expect(emitter.emit(database())).toBe("emitted");
    expect(events).toEqual([
      buildOperationalTelemetryEvent(service()),
      buildOperationalTelemetryEvent(database()),
    ]);
    expect(Object.isFrozen(emitter.health())).toBe(true);
    expect(emitter.health()).toEqual({
      version: "operational-telemetry-health-v1", emitted: 2, rejected: 0, dropped: 0,
    });
  });

  test("identical operations have byte-identical events without an owner coordinate", () => {
    const first = buildOperationalTelemetryEvent(service());
    const second = buildOperationalTelemetryEvent(service());
    expect(JSON.stringify(first)).toBe(JSON.stringify(second));
    expect(JSON.stringify(first)).not.toContain("owner");
  });
});
