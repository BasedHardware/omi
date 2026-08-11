import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  expireDurableMemoryWorkLease,
  failDurableMemoryWork,
  leaseDurableMemoryWork,
  succeedDurableMemoryWork,
  type AcceptedDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  defineDurableMemoryWorkAcceptanceRepository,
  defineDurableMemoryWorkExecutionRepository,
  durableMemoryWorkAcceptanceRequestDigest,
  durableMemoryWorkInputManifestDigest,
  type DurableMemoryWorkAcceptanceRequest,
  type DurableMemoryWorkInputManifestEntry,
} from "./durable-memory-work-repository";

const digest = (character: string): string => character.repeat(64);

const context = (
  capability: "memories.work.accept" | "memories.work.execute",
  principal = capability === "memories.work.execute" ? "worker:one" : "principal:acceptor",
  owner = "account:alice",
  epoch = 7,
) => createAuthorizedLedgerWriteContextIssuer().issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: principal,
  account_id: owner,
  application_id: capability === "memories.work.execute" ? "app:worker" : "app:ingestion",
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

const manifest = (): readonly DurableMemoryWorkInputManifestEntry[] => [
  {
    input_kind: "graph_frontier",
    input_ref: "frontier:one",
    input_digest: sha256CanonicalContent({ graph_frontier: "frontier:one" }),
  },
  {
    input_kind: "evidence_revision",
    input_ref: "evidence:one",
    input_digest: digest("b"),
  },
];

const accepted = (
  overrides: Partial<AcceptedDurableMemoryWork> = {},
  inputs = manifest(),
): AcceptedDurableMemoryWork => ({
  version: DURABLE_MEMORY_WORK_VERSION,
  job_id: "job:formation:one",
  owner_account_id: "account:alice",
  account_epoch: 7,
  lifecycle_state: "active",
  deletion_epoch: null,
  work_kind: "formation",
  input_frontier: "frontier:one",
  input_digest: durableMemoryWorkInputManifestDigest(inputs),
  execution_contract_digest: digest("c"),
  accepted_at_event_time: 100,
  max_attempts: 2,
  ...overrides,
});

const acceptanceRequest = (
  work = accepted(),
  inputs = manifest(),
): DurableMemoryWorkAcceptanceRequest => {
  const pending = acceptDurableMemoryWork(work);
  return {
    accepted_work: work,
    input_manifest: inputs,
    request_digest: durableMemoryWorkAcceptanceRequestDigest(pending, inputs),
  };
};

describe("durable work acceptance repository", () => {
  test("persists one exact pending job and normalized manifest behind acceptance authority", async () => {
    const calls: unknown[] = [];
    const repository = defineDurableMemoryWorkAcceptanceRepository(async (authorized, request) => {
      calls.push([authorized, request]);
      expect(request.input_manifest.map((item) => item.input_kind))
        .toEqual(["evidence_revision", "graph_frontier"]);
      return { kind: "accepted", job: request.pending_job };
    });
    const outcome = await repository.accept(context("memories.work.accept"), acceptanceRequest());
    expect(outcome.kind).toBe("accepted");
    if (outcome.kind === "accepted") {
      expect(outcome.job.state).toBe("pending");
      expect(Object.isFrozen(outcome.job)).toBe(true);
    }
    expect(calls).toHaveLength(1);
    expect(Object.keys(repository)).toEqual(["accept"]);
    expect("query" in repository).toBe(false);
    expect("execute" in repository).toBe(false);
  });

  test("manifest ordering is canonical while every manifest byte remains identity-bearing", () => {
    const forward = manifest();
    const reversed = [...forward].reverse();
    expect(durableMemoryWorkInputManifestDigest(forward))
      .toBe(durableMemoryWorkInputManifestDigest(reversed));
    expect(durableMemoryWorkAcceptanceRequestDigest(
      acceptDurableMemoryWork(accepted({}, forward)), forward,
    )).toBe(durableMemoryWorkAcceptanceRequestDigest(
      acceptDurableMemoryWork(accepted({}, reversed)), reversed,
    ));
    const changed = forward.map((item) => item.input_kind === "evidence_revision"
      ? { ...item, input_digest: digest("d") }
      : item);
    expect(durableMemoryWorkInputManifestDigest(changed))
      .not.toBe(durableMemoryWorkInputManifestDigest(forward));
  });

  test("wrong capability, owner, epoch, frontier, manifest, or request digest never reaches an adapter", async () => {
    let calls = 0;
    const repository = defineDurableMemoryWorkAcceptanceRepository(async (_context, request) => {
      calls += 1;
      return { kind: "accepted", job: request.pending_job };
    });
    await expect(repository.accept(context("memories.work.execute"), acceptanceRequest()))
      .rejects.toThrow("capability_denied");
    await expect(repository.accept(context("memories.work.accept"), acceptanceRequest(
      accepted({ owner_account_id: "account:bob" }),
    ))).rejects.toThrow("owner_mismatch");
    await expect(repository.accept(context("memories.work.accept"), acceptanceRequest(
      accepted({ account_epoch: 8 }),
    ))).rejects.toThrow("epoch_mismatch");

    const noFrontier = manifest().filter((item) => item.input_kind !== "graph_frontier");
    await expect(repository.accept(context("memories.work.accept"), acceptanceRequest(
      accepted({}, noFrontier), noFrontier,
    ))).rejects.toThrow("frontier_mismatch");
    const duplicate = [...manifest(), manifest()[0]!];
    await expect(repository.accept(context("memories.work.accept"), {
      accepted_work: accepted(),
      input_manifest: duplicate,
      request_digest: digest("0"),
    })).rejects.toThrow("invalid_manifest");

    const request = acceptanceRequest();
    await expect(repository.accept(context("memories.work.accept"), {
      ...request,
      request_digest: digest("0"),
    })).rejects.toThrow("request_digest_mismatch");
    await expect(repository.accept(context("memories.work.accept"), {
      ...request,
      accepted_work: { ...request.accepted_work, input_digest: digest("f") },
      request_digest: digest("0"),
    })).rejects.toThrow("manifest_digest_mismatch");
    expect(calls).toBe(0);
  });

  test("hostile containers and forged adapter jobs fail content-safely", async () => {
    let calls = 0;
    const request = acceptanceRequest();
    const repository = defineDurableMemoryWorkAcceptanceRepository(async (_context, normalized) => {
      calls += 1;
      return { kind: "accepted", job: { ...normalized.pending_job, raw_error: "secret" } };
    });
    await expect(repository.accept(context("memories.work.accept"), new Proxy(request, {
      get: () => { throw new Error("must not execute"); },
    }))).rejects.toThrow("invalid_acceptance");
    expect(calls).toBe(0);

    await expect(repository.accept(context("memories.work.accept"), request))
      .rejects.toThrow("invalid_job_output");
    expect(calls).toBe(1);
  });

  test("replay must return the exact pending acceptance and denial shapes are closed", async () => {
    const exact = defineDurableMemoryWorkAcceptanceRepository(async (_context, request) => ({
      kind: "replayed",
      job: request.pending_job,
    }));
    await expect(exact.accept(context("memories.work.accept"), acceptanceRequest()))
      .resolves.toMatchObject({ kind: "replayed", job: { state: "pending" } });

    const changed = defineDurableMemoryWorkAcceptanceRepository(async (_context, request) => ({
      kind: "replayed",
      job: acceptDurableMemoryWork({
        ...request.accepted_work,
        job_id: "job:other",
      }),
    }));
    await expect(changed.accept(context("memories.work.accept"), acceptanceRequest()))
      .rejects.toThrow("invalid_outcome");

    const denied = defineDurableMemoryWorkAcceptanceRepository(async () => ({
      kind: "stale_context",
      reason: "stale_epoch",
    }));
    await expect(denied.accept(context("memories.work.accept"), acceptanceRequest()))
      .resolves.toEqual({ kind: "stale_context", reason: "stale_epoch" });
  });
});

describe("durable work execution control repository", () => {
  const pending = () => acceptDurableMemoryWork(accepted());
  const leased = () => leaseDurableMemoryWork(pending(), "worker:one", 100, 10);

  test("surface exposes fenced control only and deliberately cannot mark success", () => {
    const repository = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async () => ({ kind: "none_available" }),
      load: async () => ({ kind: "not_found" }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    });
    expect(Object.keys(repository).sort())
      .toEqual(["leaseNext", "load", "recordFailure", "recoverExpired"]);
    for (const forbidden of ["succeed", "success", "finish", "finalize", "query", "execute", "connection"]) {
      expect(forbidden in repository).toBe(false);
    }
  });

  test("lease selection is closed and returned work belongs to the context principal", async () => {
    let calls = 0;
    const repository = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async (authorized, request) => {
        calls += 1;
        expect(request).toEqual({ work_kinds: ["formation", "promotion"] });
        return {
          kind: "leased",
          job: leaseDurableMemoryWork(pending(), authorized.principal_id, 100, 10),
        };
      },
      load: async () => ({ kind: "not_found" }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    });
    await expect(repository.leaseNext(context("memories.work.execute"), {
      work_kinds: ["formation", "promotion"],
    })).resolves.toMatchObject({ kind: "leased", job: { lease: { worker_id: "worker:one" } } });
    await expect(repository.leaseNext(context("memories.work.accept"), {
      work_kinds: ["formation"],
    })).rejects.toThrow("capability_denied");
    await expect(repository.leaseNext(context("memories.work.execute"), {
      work_kinds: ["promotion", "formation"],
    })).rejects.toThrow("invalid_lease_request");
    await expect(repository.leaseNext(context("memories.work.execute"), {
      work_kinds: ["formation", "formation"],
    })).rejects.toThrow("invalid_lease_request");
    expect(calls).toBe(1);
  });

  test("a driver cannot return another worker, owner, epoch, state, or raw field", async () => {
    const base = {
      load: async () => ({ kind: "not_found" }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    };
    const wrongWorker = defineDurableMemoryWorkExecutionRepository({
      ...base,
      leaseNext: async () => ({
        kind: "leased",
        job: leaseDurableMemoryWork(pending(), "worker:two", 100, 10),
      }),
    });
    await expect(wrongWorker.leaseNext(context("memories.work.execute"), { work_kinds: ["formation"] }))
      .rejects.toThrow("invalid_outcome");

    const foreign = defineDurableMemoryWorkExecutionRepository({
      ...base,
      leaseNext: async () => ({
        kind: "leased",
        job: leaseDurableMemoryWork(acceptDurableMemoryWork(accepted({
          owner_account_id: "account:bob",
        })), "worker:one", 100, 10),
      }),
    });
    await expect(foreign.leaseNext(context("memories.work.execute"), { work_kinds: ["formation"] }))
      .rejects.toThrow("owner_mismatch");

    const raw = defineDurableMemoryWorkExecutionRepository({
      ...base,
      leaseNext: async () => ({ kind: "leased", job: { ...leased(), raw: "secret" } }),
    });
    await expect(raw.leaseNext(context("memories.work.execute"), { work_kinds: ["formation"] }))
      .rejects.toThrow("invalid_job_output");

    const wrongKind = defineDurableMemoryWorkExecutionRepository({
      ...base,
      leaseNext: async () => ({
        kind: "leased",
        job: leaseDurableMemoryWork(acceptDurableMemoryWork(accepted({
          work_kind: "promotion",
        })), "worker:one", 100, 10),
      }),
    });
    await expect(wrongKind.leaseNext(context("memories.work.execute"), { work_kinds: ["formation"] }))
      .rejects.toThrow("invalid_outcome");
  });

  test("load is owner/epoch-bound and cannot substitute another job id", async () => {
    const repository = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async () => ({ kind: "none_available" }),
      load: async () => ({ kind: "found", job: pending() }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    });
    await expect(repository.load(context("memories.work.execute"), {
      job_id: "job:formation:one",
    })).resolves.toMatchObject({ kind: "found", job: { state: "pending" } });
    await expect(repository.load(context("memories.work.execute"), {
      job_id: "job:other",
    })).rejects.toThrow("invalid_outcome");
    await expect(repository.load(context("memories.work.execute", "worker:one", "account:alice", 8), {
      job_id: "job:formation:one",
    })).rejects.toThrow("epoch_mismatch");
  });

  test("recordFailure binds principal fence and closed error to retry/dead output", async () => {
    const repository = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async () => ({ kind: "none_available" }),
      load: async () => ({ kind: "not_found" }),
      recordFailure: async (_authorized, request) => ({
        kind: "recorded",
        job: failDurableMemoryWork(
          leased(),
          { worker_id: "worker:one", fence: request.lease_fence },
          105,
          request.error_code,
          120,
        ),
      }),
      recoverExpired: async () => ({ kind: "not_expired" }),
    });
    await expect(repository.recordFailure(context("memories.work.execute"), {
      job_id: "job:formation:one",
      lease_fence: 1,
      error_code: "model_timeout",
    })).resolves.toMatchObject({
      kind: "recorded",
      job: { state: "retryable_failed", outcome: { error_code: "model_timeout" } },
    });
    await expect(repository.recordFailure(context("memories.work.execute"), {
      job_id: "job:formation:one",
      lease_fence: 0,
      error_code: "model_timeout",
    })).rejects.toThrow("invalid_failure_request");
    await expect(repository.recordFailure(context("memories.work.execute"), {
      job_id: "job:formation:one",
      lease_fence: 1,
      error_code: "raw provider error" as never,
    })).rejects.toThrow("invalid_failure_request");
  });

  test("expired recovery can only return typed worker_lost retry/dead work", async () => {
    const repository = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async () => ({ kind: "none_available" }),
      load: async () => ({ kind: "not_found" }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({
        kind: "recovered",
        job: expireDurableMemoryWorkLease(leased(), 110, 120),
      }),
    });
    await expect(repository.recoverExpired(context("memories.work.execute"), {
      job_id: "job:formation:one",
    })).resolves.toMatchObject({
      kind: "recovered",
      job: { state: "retryable_failed", outcome: { error_code: "worker_lost" } },
    });

    const forgedSuccess = defineDurableMemoryWorkExecutionRepository({
      leaseNext: async () => ({ kind: "none_available" }),
      load: async () => ({ kind: "not_found" }),
      recordFailure: async () => ({ kind: "ineligible_state" }),
      recoverExpired: async () => ({
        kind: "recovered",
        job: succeedDurableMemoryWork(
          leased(), { worker_id: "worker:one", fence: 1 }, 105,
          "successful_empty", digest("d"), digest("e"),
        ),
      }),
    });
    await expect(forgedSuccess.recoverExpired(context("memories.work.execute"), {
      job_id: "job:formation:one",
    })).rejects.toThrow("invalid_outcome");
  });
});
