import { describe, expect, test } from "bun:test";

import type { GraphSnapshot } from "../../../core/retrieve";
import { sealUserAssertedStmNote } from "../../../core/stm/note";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import type { FormationWorkIngestionRequest } from "../workers/formation-work-ingestion";
import { formationWorkInputManifest } from "../workers/formation-work-producer";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  defineStmNoteIngestion,
  materializeStmNoteFormationSnapshot,
} from "./stm-note-ingestion";

const graph = (owner = "account:alice", generation: number | string = 7): GraphSnapshot => ({
  owner_account_id: owner,
  graph_generation: generation,
  claims: [],
  entities: [],
  predicates: [],
  identity_authorizations: [],
  adjacency: [],
});

const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.work.accept"): AuthorizedLedgerWriteContext => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "principal:stm-note",
  account_id: "account:alice",
  application_id: "app:stm-note",
  credential_id: "credential:stm-note",
  credential_generation: 1,
  capability,
  grant_id: "grant:stm-note",
  grant_version: 1,
  account_epoch: 7,
  destination_activation_revision: 1,
  lifecycle_state: "active",
  deletion_epoch: null,
  authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100,
  expires_at_epoch_seconds: 200,
  authorization_state_digest: "a".repeat(64),
}, 150);

const note = (content = "Met Alex at the product launch.") => sealUserAssertedStmNote({
  owner_account_id: "account:alice",
  write_id: "write:one",
  content,
  metadata: Object.freeze({
    write_door: "mcp",
    client_write_ref: "legacy-memory:42",
    submitted_at: "2026-08-13T18:00:00.000Z",
  }),
});

const materializationRequest = (overrides: Record<string, unknown> = {}) => ({
  note: note(),
  graph_snapshot: graph(),
  source_language: "en",
  account_timezone: "America/New_York",
  reference_clock_query_at: "2026-08-13T18:00:01.000Z",
  policy_version: "policy:stm-note:v1",
  predicate_alias_generation: "predicate-alias:7",
  authorization_generation: "authorization:7",
  stm_generation: "stm:7",
  ...overrides,
});

describe("stm note ingestion", () => {
  test("maps integrator content to a user_asserted formation snapshot without owner authority", () => {
    const snapshot = materializeStmNoteFormationSnapshot(materializationRequest());

    expect(snapshot.work_id).toBe(note().formation_work_id);
    expect(snapshot.input_frontier).toBe("7");
    expect(snapshot.target_evidence_ids).toHaveLength(1);
    expect(snapshot.evidence[0]?.source_trust).toBe("user_asserted");
    expect(snapshot.evidence[0]?.source_identity_ref?.producer).toEqual({
      producer_ref: null, contract_ref: null,
    });
    expect(snapshot.evidence[0]?.source_identity_ref?.asserted_identity).toEqual({
      domain: null, scope_ref: null,
    });
    expect(snapshot.evidence[0]?.policy_labels.some((label) => label.startsWith("subject:"))).toBeFalse();
    expect(snapshot.identity_authority_context).toBeNull();
    expect(JSON.stringify(snapshot)).not.toContain("subject:owner");
    expect(JSON.stringify(snapshot)).not.toContain("person:owner");
    expect(snapshot.events[0]?.payload).toEqual(expect.objectContaining({
      capture_kind: "user_asserted_stm_note",
      write_door: "mcp",
      client_write_ref: "legacy-memory:42",
    }));
  });

  test("changed content under the same write id becomes an idempotency conflict at formation acceptance", () => {
    const first = materializeStmNoteFormationSnapshot(materializationRequest());
    const changed = materializeStmNoteFormationSnapshot(materializationRequest({
      note: note("Met Alex again after the keynote."),
    }));
    expect(changed.work_id).toBe(first.work_id);
    expect(durableMemoryWorkInputManifestDigest(formationWorkInputManifest(changed)))
      .not.toBe(durableMemoryWorkInputManifestDigest(formationWorkInputManifest(first)));
  });

  test("accept delegates once to formation acceptance and rejects wrong capability", async () => {
    const accepted: FormationWorkIngestionRequest[] = [];
    const ingestion = defineStmNoteIngestion({
      async accept(_context, request) {
        accepted.push(request);
        return Object.freeze({ kind: "accepted" as const, job_id: request.snapshot.work_id });
      },
    });
    const request = {
      ...materializationRequest(),
      strategy_assignment: Object.freeze({ owner_account_id: "account:alice" }),
      execution_policy: Object.freeze({ work_kind: "formation" }),
      accepted_at_event_time: 1_000,
    };
    await expect(ingestion.accept(context("memories.work.execute"), request as never))
      .rejects.toThrow("capability_denied");
    await ingestion.accept(context(), request as never);
    expect(accepted).toHaveLength(1);
    expect(accepted[0]?.snapshot.work_id).toBe(note().formation_work_id);
  });
});
