import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkExecutionRepository,
  type DurableMemoryWorkLeaseNextOutcome,
} from "../stores/durable-memory-work-repository";
import { defineFormationWorkDispatch } from "./formation-work-dispatch";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.work.execute") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:one",
  account_id: "account:alice",
  application_id: "app:worker",
  credential_id: "credential:one",
  credential_generation: 1,
  capability,
  grant_id: "grant:one",
  grant_version: 1,
  account_epoch: 7,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const leased = () => leaseDurableMemoryWork(acceptDurableMemoryWork({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:formation:one",
  owner_account_id: "account:alice",
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "formation",
  input_frontier: "0",
  input_digest: digest("b"),
  execution_contract_digest: digest("c"),
  accepted_at_event_time: 100,
  max_attempts: 3,
}), "worker:one", 101, 20);

const repository = (lease: DurableMemoryWorkLeaseNextOutcome) =>
  defineDurableMemoryWorkExecutionRepository({
  leaseNext: async () => lease,
  load: async () => ({ kind: "not_found" }),
  recordFailure: async () => ({ kind: "ineligible_state" }),
  recoverExpired: async () => ({ kind: "not_expired" }),
  });

describe("formation work one-shot dispatch", () => {
  test("idle never invokes the formation executor", async () => {
    let calls = 0;
    const dispatch = defineFormationWorkDispatch({
      execution_repository: repository({ kind: "none_available" }),
      formation: { run: async () => { calls += 1; throw new Error("must not run"); } },
    });
    await expect(dispatch.runNext(context())).resolves.toEqual({
      kind: "idle", leased: 0, producer_calls: 0, materialization_attempts: 0,
    });
    expect(calls).toBe(0);
    expect(Object.keys(dispatch)).toEqual(["runNext"]);
  });

  test("one lease invokes one executor and returns only a content-safe summary", async () => {
    let calls = 0;
    const dispatch = defineFormationWorkDispatch({
      execution_repository: repository({ kind: "leased", job: leased() }),
      formation: {
        run: async () => {
          calls += 1;
          return {
            kind: "failure_recorded",
            error_code: "model_timeout",
            outcome: { kind: "recorded", job: leased() },
            producer_calls: 1,
            materialization_attempts: 0,
          };
        },
      },
    });
    const outcome = await dispatch.runNext(context());
    expect(outcome).toEqual({
      kind: "completed", result: "failure_recorded", error_code: "model_timeout",
      leased: 1, producer_calls: 1, materialization_attempts: 0,
    });
    expect(JSON.stringify(outcome)).not.toMatch(/job:|account:|commit:|outcome/);
    expect(calls).toBe(1);
  });

  test("authority and storage stops happen before executor access", async () => {
    for (const [leaseOutcome, expected] of [
      [{ kind: "serialization_retryable" }, "storage_retryable"],
      [{ kind: "authorization_denied", reason: "grant_inactive" }, "authorization_or_context"],
      [{ kind: "stale_context", reason: "expired_context" }, "authorization_or_context"],
    ] as const) {
      let calls = 0;
      const dispatch = defineFormationWorkDispatch({
        execution_repository: repository(leaseOutcome),
        formation: { run: async () => { calls += 1; throw new Error("must not run"); } },
      });
      await expect(dispatch.runNext(context())).resolves.toEqual({
        kind: "stopped", stop_code: expected, leased: 0,
        producer_calls: 0, materialization_attempts: 0,
      });
      expect(calls).toBe(0);
    }

    const denied = defineFormationWorkDispatch({
      execution_repository: repository({ kind: "none_available" }),
      formation: { run: async () => { throw new Error("must not run"); } },
    });
    await expect(denied.runNext(context("memories.work.accept"))).resolves.toMatchObject({
      kind: "stopped", stop_code: "authorization_or_context", leased: 0,
    });
  });

  test("dependency exceptions are contained without exposing raw errors", async () => {
    const leaseFailure = defineFormationWorkDispatch({
      execution_repository: defineDurableMemoryWorkExecutionRepository({
        leaseNext: async () => { throw new Error("database included secret transcript"); },
        load: async () => ({ kind: "not_found" }),
        recordFailure: async () => ({ kind: "ineligible_state" }),
        recoverExpired: async () => ({ kind: "not_expired" }),
      }),
      formation: { run: async () => { throw new Error("must not run"); } },
    });
    await expect(leaseFailure.runNext(context())).resolves.toEqual({
      kind: "stopped", stop_code: "storage_retryable", leased: 0,
      producer_calls: 0, materialization_attempts: 0,
    });

    const executionFailure = defineFormationWorkDispatch({
      execution_repository: repository({ kind: "leased", job: leased() }),
      formation: { run: async () => { throw new Error("provider included secret transcript"); } },
    });
    const outcome = await executionFailure.runNext(context());
    expect(outcome).toEqual({
      kind: "stopped", stop_code: "storage_retryable", leased: 1,
      producer_calls: 0, materialization_attempts: 0,
    });
    expect(JSON.stringify(outcome)).not.toContain("secret transcript");
  });
});
