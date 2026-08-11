import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import {
  assertCopiedMemoryEvaluationInput,
  defineMemoryEvaluationEvidenceSource,
} from "./memory-evaluation-evidence-source";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (owner = "account:alice", capability = "memories.experiments.shadow") =>
  issuer.issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: "worker:evaluator",
    account_id: owner,
    application_id: "app:evaluator",
    credential_id: "credential:evaluator",
    credential_generation: 1,
    capability,
    grant_id: "grant:evaluator",
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

const request = {
  source_kind: "formation_input_snapshot" as const,
  source_ref: "source:formation:one",
  input_frontier: "frontier:one",
};

describe("authorized memory evaluation evidence source", () => {
  test("binds copied bytes to owner, epoch, source, and frontier", async () => {
    const payload = { transcript: [{ text: "sensitive source" }] };
    const source = defineMemoryEvaluationEvidenceSource(async (authorized, requested) => ({
      kind: "found",
      owner_account_id: authorized.account_id,
      account_epoch: authorized.account_epoch,
      source_kind: requested.source_kind,
      source_ref: requested.source_ref,
      input_frontier: requested.input_frontier,
      payload,
    }));
    const outcome = await source.load(context(), request);
    expect(outcome).toMatchObject({
      kind: "found",
      copied_input: {
        version: "copied-memory-evaluation-input-v2",
        owner_account_id: "account:alice",
        account_epoch: 7,
        source_kind: "formation_input_snapshot",
        input_frontier: "frontier:one",
      },
    });
    if (outcome.kind !== "found") throw new Error("test source missing");
    payload.transcript[0]!.text = "changed later";
    expect(JSON.stringify(outcome.copied_input.payload)).toContain("sensitive source");
    expect(JSON.stringify(outcome.copied_input.payload)).not.toContain("changed later");
    expect(assertCopiedMemoryEvaluationInput(context(), outcome.copied_input)).toBe(outcome.copied_input);
    expect(() => assertCopiedMemoryEvaluationInput(context("account:bob"), outcome.copied_input))
      .toThrow("copied_input_authority_mismatch");
    expect(Object.keys(source)).toEqual(["load"]);
  });

  test("foreign coordinates and forged copies fail closed", async () => {
    for (const changed of [
      { owner_account_id: "account:bob" },
      { account_epoch: 8 },
      { source_kind: "authorized_graph_snapshot" },
      { source_ref: "source:other" },
      { input_frontier: "frontier:other" },
    ]) {
      const source = defineMemoryEvaluationEvidenceSource(async (authorized, requested) => ({
        kind: "found",
        owner_account_id: authorized.account_id,
        account_epoch: authorized.account_epoch,
        source_kind: requested.source_kind,
        source_ref: requested.source_ref,
        input_frontier: requested.input_frontier,
        payload: { claims: [] },
        ...changed,
      }));
      await expect(source.load(context(), request)).rejects.toThrow("source_coordinate_mismatch");
    }
    const good = defineMemoryEvaluationEvidenceSource(async (authorized, requested) => ({
      kind: "found", owner_account_id: authorized.account_id,
      account_epoch: authorized.account_epoch, source_kind: requested.source_kind,
      source_ref: requested.source_ref, input_frontier: requested.input_frontier,
      payload: { claims: [] },
    }));
    const loaded = await good.load(context(), request);
    if (loaded.kind !== "found") throw new Error("test source missing");
    expect(() => assertCopiedMemoryEvaluationInput(context(), { ...loaded.copied_input }))
      .toThrow("unverified_copied_input");
    await expect(good.load(context("account:alice", "memories.work.execute"), request))
      .rejects.toThrow("capability_denied");
  });

  test("closed source outcomes and exceptions never expose content", async () => {
    for (const raw of [
      { kind: "not_found" },
      { kind: "serialization_retryable" },
      { kind: "authorization_denied", reason: "grant_inactive" },
      { kind: "stale_context", reason: "expired_context" },
    ] as const) {
      const source = defineMemoryEvaluationEvidenceSource(async () => raw);
      await expect(source.load(context(), request)).resolves.toEqual(raw);
    }
    const failing = defineMemoryEvaluationEvidenceSource(async () => {
      throw new Error("database echoed sensitive source");
    });
    const outcome = await failing.load(context(), request);
    expect(outcome).toEqual({ kind: "source_unavailable" });
    expect(JSON.stringify(outcome)).not.toContain("sensitive source");
  });
});
