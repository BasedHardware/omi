import { describe, expect, test } from "bun:test";

import type { GraphSnapshot } from "../../../core/retrieve";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../stores/listen-store";
import { formationWorkInputManifest } from "../workers/formation-work-producer";
import { durableMemoryWorkInputManifestDigest } from "../stores/durable-memory-work-repository";
import {
  defineListenFormationIngestion,
  materializeListenFormationSnapshot,
  sealListenFormationFinalization,
} from "./formation-ingestion";

const session = (
  status: ListenSessionRecord["status"] = "completed",
): ListenSessionRecord => Object.freeze({
  id: "listen-session:one",
  conversationId: "conversation:one",
  clientConversationId: null,
  startedAt: "2026-08-12T12:00:00.000Z",
  updatedAt: "2026-08-12T12:01:00.000Z",
  endedAt: status === "active" ? null : "2026-08-12T12:01:00.000Z",
  status,
  source: "omi",
  codec: "pcm16",
  sampleRate: 16_000,
  channels: 1,
});

const segments = (): readonly ListenTranscriptSegment[] => Object.freeze([
  Object.freeze({
    id: "segment:one", text: "I am planning the Atlas launch.", is_user: true,
    start: 1, end: 3,
  }),
  Object.freeze({
    id: "segment:two", text: "A second speaker prefers Friday.", is_user: false,
    start: 4, end: 7,
  }),
]);

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
  principal_id: "principal:listen-formation",
  account_id: "account:alice",
  application_id: "app:listen-formation",
  credential_id: "credential:listen-formation",
  credential_generation: 1,
  capability,
  grant_id: "grant:listen-formation",
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

const finalization = (
  status: ListenSessionRecord["status"] = "completed",
  values: readonly ListenTranscriptSegment[] = segments(),
) => sealListenFormationFinalization({
  owner_account_id: "account:alice",
  session: session(status),
  segments: values,
});

const materializationRequest = (overrides: Record<string, unknown> = {}) => ({
  finalization: finalization(),
  graph_snapshot: graph(),
  source_language: "en",
  account_timezone: "America/New_York",
  reference_clock_query_at: "2026-08-12T12:01:01.000Z",
  policy_version: "policy:listen:v1",
  predicate_alias_generation: "predicate-alias:7",
  authorization_generation: "authorization:7",
  stm_generation: "stm:7",
  ...overrides,
});

describe("Listen formation ingestion", () => {
  test("seals exact transcript bytes under a stable account/session work coordinate", () => {
    const first = finalization();
    const replay = finalization();
    const changedText = finalization("completed", Object.freeze([
      { ...segments()[0]!, text: "I am planning the Atlas launch next week." },
      segments()[1]!,
    ]));
    const reordered = finalization("completed", Object.freeze([
      segments()[1]!, segments()[0]!,
    ]));

    expect(replay).toEqual(first);
    expect(changedText.formation_work_id).toBe(first.formation_work_id);
    expect(reordered.formation_work_id).toBe(first.formation_work_id);
    expect(changedText.transcript_digest).not.toBe(first.transcript_digest);
    expect(reordered.transcript_digest).not.toBe(first.transcript_digest);
    expect(changedText.finalization_digest).not.toBe(first.finalization_digest);
    expect(reordered.finalization_digest).not.toBe(first.finalization_digest);

    const firstSnapshot = materializeListenFormationSnapshot(materializationRequest({
      finalization: first,
    }));
    const changedSnapshot = materializeListenFormationSnapshot(materializationRequest({
      finalization: changedText,
    }));
    expect(durableMemoryWorkInputManifestDigest(formationWorkInputManifest(changedSnapshot)))
      .not.toBe(durableMemoryWorkInputManifestDigest(formationWorkInputManifest(firstSnapshot)));
  });

  test("maps both noisy is_user values to distinct producer-null source-local channels", () => {
    const snapshot = materializeListenFormationSnapshot(materializationRequest());

    expect(snapshot.work_id).toBe(finalization().formation_work_id);
    expect(snapshot.input_frontier).toBe("7");
    expect(snapshot.target_evidence_ids).toHaveLength(2);
    expect(snapshot.evidence.map((item) => item.source_identity_ref?.local_key)).toEqual([
      "observed-channel:is-user", "observed-channel:not-user",
    ]);
    for (const evidence of snapshot.evidence) {
      expect(evidence.source_identity_ref?.producer).toEqual({
        producer_ref: null, contract_ref: null,
      });
      expect(evidence.source_identity_ref?.asserted_identity).toEqual({ domain: null, scope_ref: null });
      expect(evidence.source_identity_ref?.local_key).not.toContain("owner");
      expect(evidence.speaker_rendering).toBeNull();
      expect(evidence.policy_labels.some((label) => label.startsWith("subject:"))).toBeFalse();
    }
    expect(snapshot.identity_authority_context).toBeNull();
    expect(JSON.stringify(snapshot)).not.toContain("person:owner");
    expect(snapshot.events.map((event) => event.payload)).toEqual([
      expect.objectContaining({
        observed_is_user: true, capture_completeness: "complete",
        terminal_status: "completed",
      }),
      expect.objectContaining({
        observed_is_user: false, capture_completeness: "complete",
        terminal_status: "completed",
      }),
    ]);
  });

  test("marks an entitlement-exhausted seal incomplete without dropping its captured segments", () => {
    const sealed = finalization("entitlement_exhausted");
    const snapshot = materializeListenFormationSnapshot(materializationRequest({ finalization: sealed }));

    expect(sealed.capture_completeness).toBe("incomplete_entitlement_exhausted");
    expect(snapshot.evidence).toHaveLength(2);
    expect(snapshot.events.every((event) =>
      event.payload["capture_completeness"] === "incomplete_entitlement_exhausted")).toBeTrue();
  });

  test("retains interrupted and empty sessions without invoking formation acceptance", async () => {
    let calls = 0;
    const adapter = defineListenFormationIngestion({
      accept: async () => {
        calls += 1;
        return { kind: "idempotency_conflict" } as never;
      },
    });
    const base = {
      ...materializationRequest(),
      strategy_assignment: {} as never,
      execution_policy: {} as never,
      accepted_at_event_time: 1,
    };
    await expect(adapter.accept(context(), {
      ...base, finalization: finalization("interrupted"),
    })).resolves.toEqual({ kind: "ineligible", reason: "interrupted" });
    await expect(adapter.accept(context(), {
      ...base, finalization: finalization("completed", Object.freeze([])),
    })).resolves.toEqual({ kind: "ineligible", reason: "empty_transcript" });
    expect(calls).toBe(0);
  });

  test("submits the exact materialized snapshot and exact scheduling inputs once", async () => {
    const accepted: unknown[] = [];
    const adapter = defineListenFormationIngestion({
      accept: async (_context, request) => {
        accepted.push(request);
        return { kind: "idempotency_conflict" } as never;
      },
    });
    const request = {
      ...materializationRequest(),
      strategy_assignment: { assignment: "sentinel" } as never,
      execution_policy: { policy: "sentinel" } as never,
      accepted_at_event_time: 123,
    };
    await expect(adapter.accept(context(), request))
      .resolves.toEqual({ kind: "idempotency_conflict" });
    expect(accepted).toHaveLength(1);
    expect(accepted[0]).toEqual({
      snapshot: materializeListenFormationSnapshot(materializationRequest()),
      strategy_assignment: request.strategy_assignment,
      execution_policy: request.execution_policy,
      accepted_at_event_time: 123,
    });
  });

  test("rejects changed duplicate, cross-owner, invalid frontier, active, and hostile inputs", async () => {
    expect(() => finalization("completed", Object.freeze([
      segments()[0]!, { ...segments()[0]! },
    ]))).toThrow("duplicate_segment_id");
    expect(() => materializeListenFormationSnapshot(materializationRequest({
      graph_snapshot: graph("account:bob"),
    }))).toThrow("graph_owner_mismatch");
    expect(() => materializeListenFormationSnapshot(materializationRequest({
      graph_snapshot: graph("account:alice", "01"),
    }))).toThrow("invalid_graph_frontier");
    let graphGetterCalls = 0;
    const hostileGraph = { ...graph() } as Record<string, unknown>;
    Object.defineProperty(hostileGraph, "claims", {
      enumerable: true,
      get() { graphGetterCalls += 1; return []; },
    });
    expect(() => materializeListenFormationSnapshot(materializationRequest({
      graph_snapshot: hostileGraph,
    }))).toThrow("invalid_graph_snapshot");
    expect(graphGetterCalls).toBe(0);
    expect(() => sealListenFormationFinalization({
      owner_account_id: "account:alice", session: session("active"), segments: segments(),
    })).toThrow("invalid_session");

    let getterCalls = 0;
    const hostile = { owner_account_id: "account:alice", segments: segments() } as Record<string, unknown>;
    Object.defineProperty(hostile, "session", {
      enumerable: true,
      get() { getterCalls += 1; return session(); },
    });
    expect(() => sealListenFormationFinalization(hostile as never)).toThrow("invalid_finalization");
    expect(getterCalls).toBe(0);
    expect(() => sealListenFormationFinalization(new Proxy({
      owner_account_id: "account:alice", session: session(), segments: segments(),
    }, {}) as never)).toThrow("invalid_finalization");

    const adapter = defineListenFormationIngestion({
      accept: async () => { throw new Error("should_not_run"); },
    });
    const malformed = { ...finalization(), finalization_digest: "f".repeat(64) };
    await expect(adapter.accept(context(), {
      ...materializationRequest(), finalization: malformed,
      strategy_assignment: {} as never, execution_policy: {} as never,
      accepted_at_event_time: 1,
    })).rejects.toThrow("finalization_digest_mismatch");

    let dependencyGetterCalls = 0;
    const hostilePort = {} as Record<string, unknown>;
    Object.defineProperty(hostilePort, "accept", {
      enumerable: true,
      get() { dependencyGetterCalls += 1; return async () => ({}); },
    });
    expect(() => defineListenFormationIngestion(hostilePort as never))
      .toThrow("invalid_formation_port");
    expect(dependencyGetterCalls).toBe(0);
    await expect(adapter.accept(context("memories.work.execute"), {
      ...materializationRequest(),
      strategy_assignment: {} as never, execution_policy: {} as never,
      accepted_at_event_time: 1,
    })).rejects.toThrow("capability_denied");
  });
});
