import { describe, expect, test } from "bun:test";

import {
  DERIVED_GROUP_DREAM_VERSION,
  derivedGroupDreamProjectionContractDigest,
} from "../../../core/consolidate/derived-group-dream";
import {
  DURABLE_MEMORY_WORK_VERSION,
  acceptDurableMemoryWork,
  leaseDurableMemoryWork,
} from "../../../core/consolidate/state-machine";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import { DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION } from "./derived-group-dream-contract";
import {
  derivedGroupDreamWorkInputManifest,
  parseDerivedGroupDreamInputSnapshot,
} from "./derived-group-dream-work-adapter";
import {
  defineDerivedGroupDreamWorkInputRepository,
  derivedGroupDreamWorkInputStageRequestDigest,
  materializeStagedDerivedGroupDreamWorkInput,
} from "./derived-group-dream-work-input-repository";

const digest = (character: string): string => character.repeat(64);
const ref = (prefix: string, character: string): string => `${prefix}_${digest(character)}`;
const owner = "account:alice";
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability: "memories.work.accept" | "memories.work.execute") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: capability === "memories.work.accept" ? "scheduler:one" : "worker:one",
  account_id: owner, application_id: "app:dream", credential_id: "credential:one",
  credential_generation: 1, capability, grant_id: "grant:one", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 90, expires_at_epoch_seconds: 900,
  authorization_state_digest: digest("a"),
}, 100);

const snapshot = () => parseDerivedGroupDreamInputSnapshot({
  version: DERIVED_GROUP_DREAM_INPUT_SNAPSHOT_VERSION,
  owner_account_id: owner,
  job_id: "job:dream:one",
  input_frontier: digest("f"),
  projection_contract_digest: derivedGroupDreamProjectionContractDigest({
    strategy_version: "dream:v1",
    code_version: "code:v1",
  }),
  original_claims: [
    {
      claim_revision_id: "claim:one:r1",
      proposition_id: "proposition:one",
      evidence_ref: ref("atevidence1", "a"),
    },
    {
      claim_revision_id: "claim:two:r1",
      proposition_id: "proposition:two",
      evidence_ref: ref("atevidence1", "b"),
    },
  ],
  group_memberships: [{
    group_key: "group:launch-week",
    proposition_ids: ["proposition:one", "proposition:two"],
  }],
  people_cluster_beliefs: [{
    cluster_about_ref: ref("about1", "a"),
    cluster_entity_target_ref: ref("attrtarget1", "a"),
    member_evidence_refs: [ref("atevidence1", "a"), ref("atevidence1", "b")],
    belief_contract_digest: digest("1"),
    aggregation_contract_digest: digest("2"),
    calibration_contract_digest: digest("3"),
  }],
  created_at_event_time: 1_700_000_000,
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
    work_kind: "derived_group_dream",
    input_frontier: input.input_frontier,
    input_digest: durableMemoryWorkInputManifestDigest(derivedGroupDreamWorkInputManifest(input)),
    execution_contract_digest: digest("c"),
    accepted_at_event_time: 100,
    max_attempts: 2,
  });
};

const request = () => {
  const body = { pending_job: pending(), snapshot: snapshot() };
  return { ...body, request_digest: derivedGroupDreamWorkInputStageRequestDigest(body) };
};

describe("derived group dream input repository contract", () => {
  test("stages exact input, replays it, and reloads it for a later worker process", async () => {
    let stored: ReturnType<typeof materializeStagedDerivedGroupDreamWorkInput> | null = null;
    const repository = defineDerivedGroupDreamWorkInputRepository({
      async stage(_authorized, value) {
        const expected = materializeStagedDerivedGroupDreamWorkInput(value);
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
        snapshot: { job_id: "job:dream:one", original_claims: [{}, {}] },
      });
  });

  test("changed snapshot, hostile request, and wrong capability fail before implementation", async () => {
    let calls = 0;
    const repository = defineDerivedGroupDreamWorkInputRepository({
      async stage(_authorized, value) {
        calls += 1;
        return { kind: "staged", input: materializeStagedDerivedGroupDreamWorkInput(value) };
      },
      async load() { calls += 1; return { kind: "not_found" }; },
    });
    const changed = {
      ...request(),
      snapshot: {
        ...snapshot(),
        original_claims: [
          ...snapshot().original_claims,
          {
            claim_revision_id: "claim:three:r1",
            proposition_id: "proposition:three",
            evidence_ref: ref("atevidence1", "c"),
          },
        ],
      },
    };
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
