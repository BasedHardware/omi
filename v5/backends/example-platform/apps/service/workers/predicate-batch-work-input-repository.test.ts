import { describe, expect, test } from "bun:test";

import { predicateIdForName, predicateRevisionForObservation } from "../../../core/consolidate/predicate-identity";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
  parsePredicateBatchInputSnapshot,
  predicateBatchWorkInputManifest,
} from "./predicate-batch-work-adapter";
import {
  definePredicateBatchWorkInputRepository,
  materializeStagedPredicateBatchWorkInput,
  predicateBatchWorkInputStageRequestDigest,
} from "./predicate-batch-work-input-repository";

const digest = (character: string): string => character.repeat(64);
const owner = "account:alice";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability: "memories.work.accept" | "memories.work.execute") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: capability === "memories.work.accept" ? "scheduler:one" : "worker:one",
  account_id: owner, application_id: "app:predicate", credential_id: "credential:one",
  credential_generation: 1, capability, grant_id: "grant:one", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 90, expires_at_epoch_seconds: 900,
  authorization_state_digest: digest("a"),
}, 100);

const predicate = (name: string) => predicateRevisionForObservation({
  owner_account_id: owner,
  predicate_id: predicateIdForName(name),
  display_name: name,
  roles: ["subject"],
  lifecycle: "canonical",
}).predicate;

const snapshot = (names = ["uses", "works_with"]) => parsePredicateBatchInputSnapshot({
  version: PREDICATE_BATCH_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner,
  job_id: "job:predicate:one",
  input_frontier: "graph:frontier:one",
  batch_question_digest: digest("b"),
  predicates: names.map(predicate),
});

const pending = () => {
  const input = snapshot();
  return acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: input.job_id,
    owner_account_id: owner,
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: "predicate_batch",
    input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(predicateBatchWorkInputManifest(input)),
    execution_contract_digest: digest("c"),
    accepted_at_event_time: 100,
    max_attempts: 2,
  });
};

const request = () => {
  const body = { pending_job: pending(), snapshot: snapshot() };
  return { ...body, request_digest: predicateBatchWorkInputStageRequestDigest(body) };
};

describe("predicate batch input repository contract", () => {
  test("stages exact input, replays it, and reloads it for a later worker process", async () => {
    let stored: ReturnType<typeof materializeStagedPredicateBatchWorkInput> | null = null;
    const repository = definePredicateBatchWorkInputRepository({
      async stage(_authorized, value) {
        const expected = materializeStagedPredicateBatchWorkInput(value);
        if (stored) return { kind: "replayed", input: stored };
        stored = expected;
        return { kind: "staged", input: expected };
      },
      async load() { return stored ? { kind: "found", input: stored } : { kind: "not_found" }; },
    });
    await expect(repository.stage(context("memories.work.accept"), request()))
      .resolves.toMatchObject({ kind: "staged", input: { snapshot_digest: expect.any(String) } });
    await expect(repository.stage(context("memories.work.accept"), request()))
      .resolves.toMatchObject({ kind: "replayed" });
    const leased = leaseDurableMemoryWork(pending(), "worker:one", 101, 20);
    await expect(repository.load(context("memories.work.execute"), leased))
      .resolves.toMatchObject({
        kind: "found",
        snapshot: { predicates: [{ identity_name: "uses" }, { identity_name: "works_with" }] },
      });
  });

  test("changed snapshot, hostile request, and wrong capability fail before implementation", async () => {
    let calls = 0;
    const repository = definePredicateBatchWorkInputRepository({
      async stage(_authorized, value) {
        calls += 1;
        return { kind: "staged", input: materializeStagedPredicateBatchWorkInput(value) };
      },
      async load() { calls += 1; return { kind: "not_found" }; },
    });
    const changed = { ...request(), snapshot: snapshot(["uses", "likes"]) };
    await expect(repository.stage(context("memories.work.accept"), changed))
      .rejects.toThrow("input_job_mismatch");
    await expect(repository.stage(context("memories.work.execute"), request()))
      .rejects.toThrow("capability_denied");
    await expect(repository.stage(context("memories.work.accept"), {
      ...request(), request_digest: digest("f"),
    })).rejects.toThrow("request_digest_mismatch");
    let getterCalls = 0;
    const hostile = Object.defineProperty({
      snapshot: snapshot(), request_digest: request().request_digest,
    }, "pending_job", {
      enumerable: true,
      get() { getterCalls += 1; return pending(); },
    });
    await expect(repository.stage(context("memories.work.accept"), hostile as never))
      .rejects.toThrow("invalid_shape");
    expect(getterCalls).toBe(0);
    expect(calls).toBe(0);
  });
});
