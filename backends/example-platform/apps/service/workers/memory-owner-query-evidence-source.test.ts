import { describe, expect, test } from "bun:test";

import type { GraphSnapshot } from "../../../core/retrieve";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import { createReaderScopedOpaqueCodecs } from "../codecs/opaque-refs";
import { defineMemoryOwnerQueryEvidenceSource } from "./memory-owner-query-evidence-source";

const hex = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();
const context = (capability = "memories.experiments.shadow") => issuer.issue({
  context_version: "authorized-ledger-write-context-v1",
  principal_id: "worker:owner-query-source", account_id: "account:alice",
  application_id: "app:evaluator", credential_id: "credential:evaluator",
  credential_generation: 1, capability, grant_id: "grant:evaluator", grant_version: 1,
  account_epoch: 7, destination_activation_revision: 17, lifecycle_state: "active",
  deletion_epoch: null, authentication_strength: "service-workload",
  issued_at_epoch_seconds: 100, expires_at_epoch_seconds: 200,
  authorization_state_digest: hex("a"),
}, 150);

const claim = (id: string, evidenceId: string, subject: string) => ({
  revision_id: id,
  commit_sequence: 1,
  placement_status: "canonical" as const,
  claim: {
    claim_lineage_id: `lineage:${id}`,
    claim_revision_id: id,
    owner_account_id: "account:alice",
    predicate: "states",
    arguments: [],
    temporal_scope: { observed_at: "2026-08-11T00:00:00Z", precision: "instant" },
    evidence_refs: [evidenceId],
    policy_labels: [`subject:${subject}`, "sensitivity:generic", "capture:voice"],
    source_language: "en",
    scope: { locality: "durable" as const, scope_ref: null },
    lifecycle: "canonical" as const,
    canonical_claim_id: `canonical:${id}`,
    source_provisional_revision_ids: [],
  },
});

const event = (id: string, evidenceId: string) => ({
  revision_id: `event:${id}`,
  event: {
    event_id: `event-id:${id}`,
    event_revision_id: `event:${id}`,
    owner_account_id: "account:alice",
    capture_session_id: `capture:${id}`,
    stream_id: "stream:voice",
    event_kind: "transcript",
    payload_schema_ref: "transcript:v1",
    schema_version: "v1",
    payload: {},
    event_time: "2026-08-11T00:00:00Z",
    ingest_time: "2026-08-11T00:00:01Z",
    source_sequence: 1,
    evidence_addressable_refs: [evidenceId],
    source_trust: "test",
    policy_labels: [],
    canonical_redacted_hash: `hash:${id}`,
  },
});

const evidence = (id: string, excerpt: string) => ({
  revision_id: `${id}:r1`,
  commit_sequence: 1,
  evidence: {
    evidence_id: id,
    event_revision_id: `event:${id}`,
    source_unit_ref: `unit:${id}`,
    range: { start: 0, end: excerpt.length },
    excerpt,
    source_identity_ref: null,
    speaker_rendering: null,
    source_local_mention_ref: null,
    state: "active" as const,
    source_trust: "test",
    policy_labels: [],
    source_independence_key: `capture:${id}`,
  },
});

const graph = (): GraphSnapshot => ({
  owner_account_id: "account:alice",
  graph_generation: 11,
  claims: [
    claim("claim:owner", "evidence:shared", "owner"),
    claim("claim:bystander-shared", "evidence:shared", "bystander"),
    claim("claim:bystander-only", "evidence:bystander", "bystander"),
    claim("claim:purged", "evidence:purged", "owner"),
  ],
  entities: [],
  events: [
    event("evidence:shared", "evidence:shared"),
    event("evidence:bystander", "evidence:bystander"),
    event("evidence:purged", "evidence:purged"),
  ],
  evidence: [
    evidence("evidence:shared", "We both discussed Omi."),
    evidence("evidence:bystander", "Nora works elsewhere."),
    evidence("evidence:purged", "This must stay absent."),
  ],
  liveness_causes: {
    purged_claim_revision_ids: ["claim:purged"],
    forgotten_claim_revision_ids: [],
  },
  adjacency: [],
});

const request = {
  source_kind: "authorized_graph_snapshot" as const,
  source_ref: "source:owner-query",
  input_frontier: "frontier:owner-query",
};

const sourceFor = (graphForCall: (call: number) => GraphSnapshot, encoder?: () => string) => {
  let loads = 0;
  let encodes = 0;
  const source = defineMemoryOwnerQueryEvidenceSource({
    load_graph: async (authorized, selected) => {
      loads += 1;
      return {
        kind: "found",
        owner_account_id: authorized.account_id,
        account_epoch: authorized.account_epoch,
        source_ref: selected.source_ref,
        input_frontier: selected.input_frontier,
        query_text: "What do I know about Omi?",
        account_timezone: "America/New_York",
        graph_snapshot: graphForCall(loads),
      };
    },
    encode_trace_ref: ({ reader_projection_digest, evidence_closure_digest }) => {
      encodes += 1;
      if (encoder) return encoder();
      return createReaderScopedOpaqueCodecs({
        root_secret: new Uint8Array(32).fill(9),
        reader_projection_digest,
      }).encodeTraceRef(evidence_closure_digest);
    },
  });
  return { source, counts: () => ({ loads, encodes }) };
};

describe("owner-projected query evidence source", () => {
  test("derives exact supporting classes after liveness and emits only opaque coordinates", async () => {
    const fixture = sourceFor(graph);
    const loaded = await fixture.source.load(context(), request);
    expect(loaded.kind).toBe("found");
    if (loaded.kind !== "found") throw new Error("fixture source unavailable");
    const payload = loaded.copied_input.payload as unknown as {
      candidates: readonly { trace_ref: string; text: string; contributing_subject_classes: readonly string[] }[];
      reader_projection_digest: string;
      projected_content_digest: string;
    };
    expect(payload.candidates).toHaveLength(2);
    expect(payload.candidates.map((candidate) => [candidate.text, candidate.contributing_subject_classes]).sort())
      .toEqual([
        ["Nora works elsewhere.", ["bystander"]],
        ["We both discussed Omi.", ["bystander", "owner"]],
      ]);
    expect(payload.reader_projection_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(payload.projected_content_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(payload.candidates.every((candidate) => /^tr1_[a-f0-9]{64}$/.test(candidate.trace_ref))).toBe(true);
    const bytes = JSON.stringify(loaded.copied_input.payload);
    for (const forbidden of [
      "account:alice", "claim:owner", "claim:bystander", "evidence:shared",
      "event:evidence", "capture:evidence", "This must stay absent",
    ]) expect(bytes).not.toContain(forbidden);
    expect(fixture.counts()).toEqual({ loads: 1, encodes: 2 });
  });

  test("equivalent graph permutations have one copied-input digest", async () => {
    const forward = sourceFor(graph);
    const reverseGraph = (): GraphSnapshot => {
      const value = graph();
      return {
        ...value,
        claims: [...value.claims].reverse(),
        events: [...value.events!].reverse(),
        evidence: [...value.evidence!].reverse(),
      };
    };
    const reversed = sourceFor(reverseGraph);
    const left = await forward.source.load(context(), request);
    const right = await reversed.source.load(context(), request);
    expect(left.kind).toBe("found");
    expect(right.kind).toBe("found");
    if (left.kind === "found" && right.kind === "found") {
      expect(left.copied_input.input_digest).toBe(right.copied_input.input_digest);
      expect(left.copied_input.payload).toEqual(right.copied_input.payload);
    }
  });

  test("graph/text drift changes the copied identity for producer revalidation", async () => {
    const fixture = sourceFor((call) => {
      const value = graph();
      if (call === 2) value.evidence = value.evidence!.map((item) => item.evidence.evidence_id === "evidence:shared"
        ? evidence("evidence:shared", "We discussed a different fact.")
        : item);
      return value;
    });
    const first = await fixture.source.load(context(), request);
    const second = await fixture.source.load(context(), request);
    expect(first.kind).toBe("found");
    expect(second.kind).toBe("found");
    if (first.kind === "found" && second.kind === "found") {
      expect(first.copied_input.input_digest).not.toBe(second.copied_input.input_digest);
    }
  });

  test("an owner graph with no live cited evidence produces an explicit empty candidate set", async () => {
    const fixture = sourceFor(() => ({
      owner_account_id: "account:alice", graph_generation: 12,
      claims: [], entities: [], events: [], evidence: [evidence("evidence:unused", "Unused evidence.")], adjacency: [],
    }));
    const loaded = await fixture.source.load(context(), request);
    expect(loaded.kind).toBe("found");
    if (loaded.kind === "found") {
      expect((loaded.copied_input.payload as unknown as { candidates: unknown[] }).candidates).toEqual([]);
    }
    expect(fixture.counts()).toEqual({ loads: 1, encodes: 0 });
  });

  test("cross-owner graph and trace collisions fail closed", async () => {
    const foreign = sourceFor(() => {
      const value = graph();
      value.evidence = value.evidence!.map((item, index) => index === 0
        ? { ...item, evidence: { ...item.evidence, owner_account_id: "account:bob" } } as never
        : item);
      return value;
    });
    await expect(foreign.source.load(context(), request)).resolves.toEqual({ kind: "source_unavailable" });
    expect(foreign.counts()).toEqual({ loads: 1, encodes: 0 });

    const collision = sourceFor(graph, () => `tr1_${hex("1")}`);
    await expect(collision.source.load(context(), request)).resolves.toEqual({ kind: "source_unavailable" });
    expect(collision.counts()).toEqual({ loads: 1, encodes: 2 });
  });

  test("graph and candidate budgets fail closed instead of truncating", async () => {
    const oversized = sourceFor(() => {
      const rows = Array.from({ length: 8 }, (_, index) => `evidence:large:${index}`);
      return {
        owner_account_id: "account:alice",
        graph_generation: 13,
        claims: rows.map((id, index) => claim(`claim:large:${index}`, id, "owner")),
        entities: [],
        events: rows.map((id) => event(id, id)),
        evidence: rows.map((id) => evidence(id, "x".repeat(63_000))),
        adjacency: [],
      };
    });
    await expect(oversized.source.load(context(), request)).resolves.toEqual({ kind: "source_unavailable" });
    expect(oversized.counts().encodes).toBeLessThan(8);
  });

  test("graph accessors are rejected without execution", async () => {
    let getterCalls = 0;
    const hostile = graph() as GraphSnapshot;
    Object.defineProperty(hostile, "claims", {
      enumerable: true,
      get() { getterCalls += 1; return []; },
    });
    const fixture = sourceFor(() => hostile);
    await expect(fixture.source.load(context(), request)).resolves.toEqual({ kind: "source_unavailable" });
    expect(getterCalls).toBe(0);
    expect(fixture.counts()).toEqual({ loads: 1, encodes: 0 });
  });

  test("wrong capability is rejected before loader or codec", async () => {
    const fixture = sourceFor(graph);
    await expect(fixture.source.load(context("memories.work.execute"), request)).rejects.toThrow("capability_denied");
    expect(fixture.counts()).toEqual({ loads: 0, encodes: 0 });
  });
});
