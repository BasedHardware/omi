import { describe, expect, test } from "bun:test";

import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
  succeedDurableMemoryWork,
  type DurableMemoryWorkKind,
} from "../../../core/consolidate/state-machine";
import {
  formationCandidateManifestDigest,
  parseFormationOutcomeEnvelope,
} from "../../../core/consolidate/formation-outcome";
import { prepareDerivation, type AtomicGraphTransition } from "../../../core/ledger";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  authoritativeAppendRequestDigest,
  type AuthoritativeAppendOrigin,
  type AuthoritativeLedgerAppend,
} from "./authoritative-ledger-repository";
import {
  durableMemoryWorkNormalizedResultDigest,
  durableMemoryWorkResultStageRequestDigest,
  materializeStagedDurableMemoryWorkResult,
  type DurableMemoryWorkResultStageBody,
} from "./durable-memory-work-result-repository";
import {
  defineDurableMemoryWorkSuccessRepository,
  durableMemoryWorkSuccessOutboxId,
  durableMemoryWorkSuccessRequestDigest,
  type DurableMemoryWorkSuccessBody,
  type DurableMemoryWorkSuccessRequest,
} from "./durable-memory-work-success-repository";

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

const jobIdFor = (kind: DurableMemoryWorkKind): string => `job:${kind}:one`;

const leasedJob = (kind: DurableMemoryWorkKind = "formation") => leaseDurableMemoryWork(
  acceptDurableMemoryWork({
    version: DURABLE_MEMORY_WORK_VERSION,
    job_id: jobIdFor(kind),
    owner_account_id: "account:alice",
    account_epoch: 7,
    lifecycle_state: "active",
    deletion_epoch: null,
    work_kind: kind,
    input_frontier: "frontier:one",
    input_digest: digest("b"),
    execution_contract_digest: digest("c"),
    accepted_at_event_time: 100,
    max_attempts: 2,
  }),
  "worker:one",
  101,
  20,
);

const graphTransition = (kind: DurableMemoryWorkKind): AtomicGraphTransition => ({
  placement: { offline_experiment: true, allocations: {}, results: [] },
  derivation: prepareDerivation({
    attempt_id: `attempt:${kind}:one`,
    commit_id: `commit:${kind}:one`,
    owner_account_id: "account:alice",
    parent_commit: null,
    idempotency_key: `append:${kind}:one`,
    input_revisions: [],
    output_revisions: [],
    versions: {
      strategy_version: "strategy:v1",
      model_version: "none",
      prompt_version: "none",
      policy_version: "policy:v1",
      code_version: "code:v1",
      schema_version: "schema:v1",
      tokenizer_version: "none",
      tool_version: "tool:v1",
    },
    success_kind: "success",
  }),
  revisions: [],
  adjacency: [],
  artifacts: [],
});

const originFor = (kind: DurableMemoryWorkKind, responseDigest: string): AuthoritativeAppendOrigin => {
  if (kind === "formation") {
    return {
      kind: "formation",
      outcome: parseFormationOutcomeEnvelope({
        contract_version: "memory-formation-outcome-v2",
        owner_account_id: "account:alice",
        work_id: jobIdFor(kind),
        input_frontier: "frontier:one",
        response_digest: responseDigest,
        candidate_count: 0,
        candidate_manifest_digest: formationCandidateManifestDigest(0),
        coordinates: {
          contract_version: "memory-formation-outcome-v2",
          strategy_version: "strategy:v1",
          model_version: "model:v1",
          prompt_version: "prompt:v1",
          policy_version: "policy:v1",
          code_version: "code:v1",
          schema_version: "schema:v1",
          tokenizer_version: "tokenizer:v1",
          tool_version: "tool:v1",
          speaker_strategy_version: "speaker:v1",
          boundary_strategy_version: "boundary:v1",
        },
        extraction_outcomes: [],
        placement_outcomes: [],
      }),
    };
  }
  return {
    kind: "non_formation",
    reason: kind === "promotion"
      ? "promotion"
      : kind === "identity_cluster"
        ? "identity_consolidation"
        : "predicate_alignment",
  };
};

const authoritativeAppend = (
  kind: DurableMemoryWorkKind,
  responseDigest = digest("d"),
): AuthoritativeLedgerAppend => {
  const transition = graphTransition(kind);
  const origin = originFor(kind, responseDigest);
  return {
    append_attempt: {
      idempotency_key: transition.derivation.commit.idempotency_key,
      expected_parent_commit: transition.derivation.commit.parent_commit,
      request_digest: authoritativeAppendRequestDigest(transition, origin),
    },
    origin,
    transition,
  };
};

const request = (
  kind: DurableMemoryWorkKind,
  resultKind: "successful" | "successful_empty" = "successful",
): DurableMemoryWorkSuccessRequest => {
  const job = leasedJob(kind);
  const normalizedResult = { outcome: resultKind };
  const resultContractVersion = `${kind}-result:v1`;
  const normalizedResultDigest = durableMemoryWorkNormalizedResultDigest(
    resultContractVersion,
    normalizedResult,
  );
  const stageBody: DurableMemoryWorkResultStageBody = {
    leased_job: job,
    result_contract_version: resultContractVersion,
    response_digest: digest("d"),
    normalized_result_digest: normalizedResultDigest,
    normalized_result: normalizedResult,
  };
  const stagedResult = materializeStagedDurableMemoryWorkResult({
    ...stageBody,
    request_digest: durableMemoryWorkResultStageRequestDigest(stageBody),
  });
  const append = resultKind === "successful" ? authoritativeAppend(kind) : null;
  const body: DurableMemoryWorkSuccessBody = {
    leased_job: job,
    result_kind: resultKind,
    response_digest: digest("d"),
    result_digest: append?.append_attempt.request_digest ?? normalizedResultDigest,
    staged_result: stagedResult,
    authoritative_append: append,
  };
  return { ...body, request_digest: durableMemoryWorkSuccessRequestDigest(body) };
};

const committedResult = (input: DurableMemoryWorkSuccessRequest, at = 105) => ({
  kind: "committed" as const,
  job: succeedDurableMemoryWork(
    input.leased_job,
    { worker_id: input.leased_job.lease!.worker_id, fence: input.leased_job.lease!.fence },
    at,
    input.result_kind,
    input.response_digest,
    input.result_digest,
  ),
  commit_id: input.authoritative_append?.transition.derivation.commit.commit_id ?? null,
  sequence: input.authoritative_append === null ? null : 1,
  outbox_id: durableMemoryWorkSuccessOutboxId(input),
});

describe("atomic durable-work success repository", () => {
  test("successful-empty still commits an exact terminal state and outbox without a graph append", async () => {
    const calls: unknown[] = [];
    const repository = defineDurableMemoryWorkSuccessRepository(async (authorized, normalized) => {
      calls.push([authorized, normalized]);
      return committedResult(normalized);
    });
    await expect(repository.commit(context(), request("formation", "successful_empty")))
      .resolves.toMatchObject({
        kind: "committed",
        job: { state: "succeeded", outcome: { result_kind: "successful_empty" } },
        commit_id: null,
        sequence: null,
      });
    expect(calls).toHaveLength(1);
    expect(Object.keys(repository)).toEqual(["commit"]);
    for (const forbidden of ["query", "execute", "connection", "clock", "lease", "retry", "model"]) {
      expect(forbidden in repository).toBe(false);
    }
  });

  test("each durable work kind accepts only its honest graph origin", async () => {
    const seen: string[] = [];
    const repository = defineDurableMemoryWorkSuccessRepository(async (_authorized, normalized) => {
      seen.push(normalized.leased_job.work_kind);
      return committedResult(normalized);
    });
    for (const kind of ["formation", "promotion", "identity_cluster", "predicate_batch"] as const) {
      await expect(repository.commit(context(), request(kind))).resolves.toMatchObject({
        kind: "committed",
        commit_id: `commit:${kind}:one`,
        sequence: 1,
      });
    }
    expect(seen).toEqual(["formation", "promotion", "identity_cluster", "predicate_batch"]);

    const wrong = request("promotion");
    const wrongAppend = authoritativeAppend("predicate_batch");
    const wrongBody = { ...wrong, authoritative_append: wrongAppend };
    await expect(repository.commit(context(), {
      ...wrongBody,
      result_digest: wrongAppend.append_attempt.request_digest,
      request_digest: durableMemoryWorkSuccessRequestDigest({
        ...wrongBody,
        result_digest: wrongAppend.append_attempt.request_digest,
      }),
    })).rejects.toThrow("origin_mismatch");
  });

  test("capability, tenant, epoch, lease owner, result shape, and request identity fail before adapter", async () => {
    let calls = 0;
    const repository = defineDurableMemoryWorkSuccessRepository(async (_authorized, normalized) => {
      calls += 1;
      return committedResult(normalized);
    });
    const valid = request("formation");
    await expect(repository.commit(context("memories.write"), valid)).rejects.toThrow("capability_denied");
    await expect(repository.commit(context(undefined, undefined, "account:bob"), valid)).rejects.toThrow("owner_mismatch");
    await expect(repository.commit(context(undefined, undefined, undefined, 8), valid)).rejects.toThrow("epoch_mismatch");
    await expect(repository.commit(context(undefined, "worker:two"), valid)).rejects.toThrow("stale_lease");
    await expect(repository.commit(context(), { ...valid, result_kind: "successful_empty" }))
      .rejects.toThrow("unexpected_graph_append");
    await expect(repository.commit(context(), { ...valid, authoritative_append: null }))
      .rejects.toThrow("missing_graph_append");
    await expect(repository.commit(context(), { ...valid, result_digest: digest("f") }))
      .rejects.toThrow("result_append_mismatch");
    await expect(repository.commit(context(), {
      ...valid,
      staged_result: { ...valid.staged_result, job_id: "job:other" },
    })).rejects.toThrow("staged_result_mismatch");
    await expect(repository.commit(context(), { ...valid, request_digest: digest("0") }))
      .rejects.toThrow("request_digest_mismatch");
    expect(calls).toBe(0);
  });

  test("formation success binds work id, frontier, owner, response, and total outcome", async () => {
    let calls = 0;
    const repository = defineDurableMemoryWorkSuccessRepository(async (_authorized, normalized) => {
      calls += 1;
      return committedResult(normalized);
    });
    const valid = request("formation");
    const mutations = [
      { work_id: "job:formation:other" },
      { input_frontier: "frontier:other" },
      { response_digest: digest("f") },
    ];
    for (const mutation of mutations) {
      if (valid.authoritative_append!.origin.kind !== "formation") throw new Error("test fixture");
      const outcome = parseFormationOutcomeEnvelope({
        ...valid.authoritative_append!.origin.outcome,
        ...mutation,
      });
      const transition = valid.authoritative_append!.transition;
      const origin = { kind: "formation" as const, outcome };
      const append = {
        append_attempt: {
          ...valid.authoritative_append!.append_attempt,
          request_digest: authoritativeAppendRequestDigest(transition, origin),
        },
        origin,
        transition,
      };
      const body = {
        ...valid,
        authoritative_append: append,
        result_digest: append.append_attempt.request_digest,
      };
      await expect(repository.commit(context(), {
        ...body,
        request_digest: durableMemoryWorkSuccessRequestDigest(body),
      })).rejects.toThrow("origin_mismatch");
    }
    expect(calls).toBe(0);
  });

  test("request digest covers job fence, response/result, append identity, origin, and result kind", () => {
    const base = request("promotion");
    const baseDigest = base.request_digest;
    const changed = [
      { ...base, response_digest: digest("f") },
      { ...base, result_kind: "successful_empty" as const, authoritative_append: null },
      {
        ...base,
        leased_job: {
          ...base.leased_job,
          lease: { ...base.leased_job.lease!, expires_at_event_time: 122 },
        },
      },
    ];
    for (const candidate of changed) {
      expect(durableMemoryWorkSuccessRequestDigest(candidate)).not.toBe(baseDigest);
    }
    expect(request("identity_cluster").request_digest).not.toBe(baseDigest);
  });

  test("forged adapter outcomes cannot substitute terminal job, graph commit, sequence, outbox, or raw fields", async () => {
    const valid = request("promotion");
    const forged = [
      { ...committedResult(valid), job: { ...committedResult(valid).job, job_id: "job:other" } },
      { ...committedResult(valid), commit_id: "commit:other" },
      { ...committedResult(valid), sequence: 0 },
      { ...committedResult(valid), outbox_id: "mwo1_" + digest("f") },
      {
        ...committedResult(valid), job: {
          ...committedResult(valid).job,
          outcome: {
            ...committedResult(valid).job.outcome!,
            succeeded_at_event_time: valid.leased_job.lease!.expires_at_event_time,
          },
        },
      },
      { ...committedResult(valid), raw_error: "sensitive" },
    ];
    for (const outcome of forged) {
      const repository = defineDurableMemoryWorkSuccessRepository(async () => outcome);
      await expect(repository.commit(context(), valid)).rejects.toThrow("invalid_outcome");
    }
  });
});
