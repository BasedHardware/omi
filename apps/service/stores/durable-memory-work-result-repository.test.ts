import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  expireDurableMemoryWorkLease,
  leaseDurableMemoryWork,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkResultRepository,
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  materializeStagedDurableMemoryWorkResult,
  type DurableMemoryWorkResultStageBody,
  type DurableMemoryWorkResultStageRequest,
  type StagedDurableMemoryWorkResult,
} from "./durable-memory-work-result-repository";

const digest = (character: string): string => character.repeat(64);

const context = (
  capability = "memories.work.execute",
  principal = "worker:one",
  owner = "account:alice",
  epoch = 7,
) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: principal,
  account_id: owner,
  application_id: "app:worker",
  credential_id: "credential:one",
  credential_generation: 4,
  capability,
  grant_id: "grant:one",
  grant_version: 9,
  account_epoch: epoch,
  destination_activation_revision: 17,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: digest("a"),
}, 150);

const leased = (kind: DurableMemoryWorkKind = "formation") => leaseDurableMemoryWork(
  acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: `job:${kind}:one`,
    owner_account_id: "account:alice",
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: kind,
    input_frontier: "frontier:one",
    input_digest: digest("b"),
    execution_contract_digest: digest("c"),
    accepted_at_event_time: 100,
    max_attempts: 3,
  }),
  "worker:one",
  101,
  20,
);

const stageRequest = (
  job = leased(),
  result: Record<string, unknown> = { claims: [{ candidate_ref: "candidate:1" }] },
): DurableMemoryWorkResultStageRequest => {
  const resultContractVersion = "formation-result:v1";
  const normalizedResultDigest = durableMemoryWorkNormalizedResultDigest(
    resultContractVersion,
    result as never,
  );
  const body: DurableMemoryWorkResultStageBody = {
    leased_job: job,
    result_contract_version: resultContractVersion,
    response_digest: digest("d"),
    normalized_result_digest: normalizedResultDigest,
    normalized_result: result as never,
  };
  return { ...body, request_digest: durableMemoryWorkResultStageRequestDigest(body) };
};

describe("durable work normalized-result repository", () => {
  test("stages one detached immutable normalized result behind the exact worker lease", async () => {
    const calls: unknown[] = [];
    const repository = defineDurableMemoryWorkResultRepository({
      load: async () => ({ kind: "missing" }),
      stage: async (authorized, request) => {
        calls.push([authorized, request]);
        return { kind: "staged", result: materializeStagedDurableMemoryWorkResult(request) };
      },
    });
    const source = { claims: [{ candidate_ref: "candidate:1" }] };
    const outcome = await repository.stage(context(), stageRequest(leased(), source));
    expect(outcome.kind).toBe("staged");
    if (outcome.kind === "staged") {
      expect(outcome.result.staged_result_id).toMatch(/^mwr1_[0-9a-f]{64}$/);
      expect(outcome.result.producer_worker_id).toBe("worker:one");
      expect(Object.isFrozen(outcome.result.normalized_result)).toBe(true);
      expect(Object.isFrozen((outcome.result.normalized_result["claims"] as unknown[])[0])).toBe(true);
      source.claims[0]!.candidate_ref = "mutated";
      expect(outcome.result.normalized_result).toEqual({ claims: [{ candidate_ref: "candidate:1" }] });
    }
    expect(calls).toHaveLength(1);
    expect(Object.keys(repository).sort()).toEqual(["load", "stage"]);
    for (const forbidden of ["query", "execute", "connection", "clock", "model", "retry", "grant"]) {
      expect(forbidden in repository).toBe(false);
    }
  });

  test("canonical object-key order is stable while contract, response, value, and lease state remain identity-bearing", () => {
    const forward = stageRequest(leased(), { z: 1, a: { y: true, x: false } });
    const reordered = stageRequest(leased(), { a: { x: false, y: true }, z: 1 });
    expect(forward.normalized_result_digest).toBe(reordered.normalized_result_digest);
    expect(forward.request_digest).toBe(reordered.request_digest);
    const changedValue = stageRequest(leased(), { a: { x: true, y: true }, z: 1 });
    expect(changedValue.normalized_result_digest).not.toBe(forward.normalized_result_digest);
    expect({ ...forward, result_contract_version: "formation-result:v2" })
      .not.toEqual(forward);
    expect(durableMemoryWorkResultStageRequestDigest({
      ...forward,
      response_digest: digest("e"),
    })).not.toBe(forward.request_digest);
    const changedLease = {
      ...leased(),
      lease: { ...leased().lease!, expires_at_event_time: 122 },
    };
    expect(durableMemoryWorkResultStageRequestDigest({
      ...forward,
      leased_job: changedLease,
    })).not.toBe(forward.request_digest);
  });

  test("wrong capability, tenant, epoch, worker, digest, and hostile result never reaches storage", async () => {
    let calls = 0;
    const repository = defineDurableMemoryWorkResultRepository({
      load: async () => ({ kind: "missing" }),
      stage: async (_authorized, request) => {
        calls += 1;
        return { kind: "staged", result: materializeStagedDurableMemoryWorkResult(request) };
      },
    });
    const valid = stageRequest();
    await expect(repository.stage(context("memories.write"), valid)).rejects.toThrow("capability_denied");
    await expect(repository.stage(context(undefined, undefined, "account:bob"), valid)).rejects.toThrow("owner_mismatch");
    await expect(repository.stage(context(undefined, undefined, undefined, 8), valid)).rejects.toThrow("epoch_mismatch");
    await expect(repository.stage(context(undefined, "worker:two"), valid)).rejects.toThrow("stale_lease");
    await expect(repository.stage(context(), { ...valid, normalized_result_digest: digest("f") }))
      .rejects.toThrow("result_digest_mismatch");
    await expect(repository.stage(context(), { ...valid, request_digest: digest("0") }))
      .rejects.toThrow("request_digest_mismatch");

    const shared = { secret: "same" };
    const aliased = {
      ...valid,
      normalized_result: { left: shared, right: shared },
      normalized_result_digest: digest("f"),
      request_digest: digest("0"),
    };
    await expect(repository.stage(context(), aliased)).rejects.toThrow("invalid_result");
    const proxy = new Proxy({ secret: "blocked" }, { get: () => { throw new Error("must not execute"); } });
    await expect(repository.stage(context(), { ...valid, normalized_result: proxy as never }))
      .rejects.toThrow("invalid_result");
    const sparse = new Array(1);
    for (const hostile of [
      [],
      new (class Result { value = "class"; })(),
      { nested: sparse },
      { nested: Object.defineProperty({}, "secret", { enumerable: true, get: () => {
        throw new Error("must not execute");
      } }) },
    ]) {
      await expect(repository.stage(context(), { ...valid, normalized_result: hostile as never }))
        .rejects.toThrow("invalid_result");
    }
    await expect(repository.stage(context(), {
      ...valid,
      normalized_result: { oversized: "x".repeat(512 * 1024) },
    })).rejects.toThrow("result_too_large");
    expect(calls).toBe(0);
  });

  test("a later lease for the same accepted work loads the earlier immutable stage", async () => {
    const originalRequest = stageRequest();
    const stored = materializeStagedDurableMemoryWorkResult(originalRequest);
    const recovered = expireDurableMemoryWorkLease(originalRequest.leased_job, 121, 122);
    const laterLease = leaseDurableMemoryWork(recovered, "worker:two", 122, 20);
    const repository = defineDurableMemoryWorkResultRepository({
      load: async () => ({ kind: "found", result: stored }),
      stage: async () => ({ kind: "idempotency_conflict" }),
    });
    await expect(repository.load(context(undefined, "worker:two"), { leased_job: laterLease }))
      .resolves.toMatchObject({
        kind: "found",
        result: {
          produced_attempt: 1,
          produced_lease_fence: 1,
          producer_worker_id: "worker:one",
        },
      });
  });

  test("stage replay must return exact bytes and load cannot forge immutable coordinates or raw fields", async () => {
    const valid = stageRequest();
    const exact = materializeStagedDurableMemoryWorkResult(valid);
    const forged: StagedDurableMemoryWorkResult[] = [
      { ...exact, job_id: "job:other" },
      { ...exact, normalized_result_digest: digest("f") },
      { ...exact, staged_result_id: "mwr1_" + digest("e") },
    ];
    for (const result of forged) {
      const repository = defineDurableMemoryWorkResultRepository({
        load: async () => ({ kind: "found", result }),
        stage: async () => ({ kind: "replayed", result }),
      });
      await expect(repository.load(context(), { leased_job: valid.leased_job }))
        .rejects.toThrow();
      await expect(repository.stage(context(), valid)).rejects.toThrow();
    }
    const raw = defineDurableMemoryWorkResultRepository({
      load: async () => ({ kind: "found", result: { ...exact, raw_provider_output: "secret" } }),
      stage: async () => ({ kind: "replayed", result: exact }),
    });
    await expect(raw.load(context(), { leased_job: valid.leased_job }))
      .rejects.toThrow("invalid_staged_result");
  });
});
