import { describe, expect, test } from "bun:test";

import { createOperationalTelemetryEmitter } from "../../../core/observability/operational-telemetry";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkBacklogSource,
  emitDurableMemoryWorkBacklogTelemetry,
} from "./durable-memory-work-backlog";

const context = () => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one", account_id: "account:one", application_id: "app:worker",
  credential_id: "credential:one", credential_generation: 1,
  capability: "memories.work.execute", grant_id: "grant:one", grant_version: 1,
  account_epoch: 2, destination_activation_revision: 3, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 10, expires_at_epoch_seconds: 20,
  authorization_state_digest: "a".repeat(64),
}, 15);

const snapshot = () => ({
  version: "durable-memory-work-backlog-snapshot-v1" as const,
  rows: [
    { work_kind: "formation", ready: 2, leased: 1, retry_wait: 3, dead: 4, oldest_ready_age_ms: 5000 },
    { work_kind: "promotion", ready: 0, leased: 0, retry_wait: 0, dead: 0, oldest_ready_age_ms: null },
    { work_kind: "identity_cluster", ready: 0, leased: 0, retry_wait: 0, dead: 0, oldest_ready_age_ms: null },
    { work_kind: "predicate_batch", ready: 0, leased: 0, retry_wait: 0, dead: 0, oldest_ready_age_ms: null },
  ],
});

describe("durable memory work backlog telemetry", () => {
  test("emits one complete detached snapshot in fixed work-kind order", async () => {
    const events: unknown[] = [];
    const source = defineDurableMemoryWorkBacklogSource(async () => snapshot());
    const telemetry = createOperationalTelemetryEmitter((event) => events.push(event));

    await expect(emitDurableMemoryWorkBacklogTelemetry(source, context(), telemetry))
      .resolves.toEqual({ kind: "available" });
    expect(events).toHaveLength(4);
    expect(events[0]).toEqual({
      version: "operational-telemetry-v1", family: "backlog", work_kind: "formation",
      outcome: "available", ready: 2, leased: 1, retry_wait: 3, dead: 4,
      oldest_ready_age_ms: 5000,
    });
    expect(events.slice(1).every((event) => Object.isFrozen(event))).toBe(true);
  });

  test("malformed or unavailable source emits nulls and never fabricated zeros", async () => {
    for (const implementation of [
      async () => ({ ...snapshot(), rows: snapshot().rows.slice(0, 3) }),
      async () => { throw new Error("provider secret"); },
    ]) {
      const events: unknown[] = [];
      const telemetry = createOperationalTelemetryEmitter((event) => events.push(event));
      await expect(emitDurableMemoryWorkBacklogTelemetry(
        defineDurableMemoryWorkBacklogSource(implementation), context(), telemetry,
      )).resolves.toEqual({ kind: "unavailable" });
      expect(events).toHaveLength(4);
      expect(events.every((event) => JSON.stringify(event).includes("\"outcome\":\"unavailable\"")
        && !JSON.stringify(event).includes(":0"))).toBe(true);
    }
  });

  test("rejects incoherent age, wrong order, extras, and accessor rows", async () => {
    const invalid = [
      { ...snapshot(), rows: snapshot().rows.map((row, index) => index === 0
        ? { ...row, ready: 0, oldest_ready_age_ms: 1 } : row) },
      { ...snapshot(), rows: [...snapshot().rows].reverse() },
      { ...snapshot(), extra: "secret" },
    ];
    for (const value of invalid) {
      await expect(defineDurableMemoryWorkBacklogSource(async () => value).snapshot(context()))
        .rejects.toThrow("invalid_snapshot");
    }
    let invoked = false;
    const hostile = snapshot();
    Object.defineProperty(hostile.rows[0]!, "ready", { get: () => { invoked = true; return 1; } });
    await expect(defineDurableMemoryWorkBacklogSource(async () => hostile).snapshot(context()))
      .rejects.toThrow("invalid_snapshot");
    expect(invoked).toBe(false);
  });
});
