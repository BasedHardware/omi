import { describe, expect, test } from "bun:test";

import type { GraphSnapshot } from "../../../core/retrieve";
import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../stores/listen-store";
import { defineMemoryEvaluationEvidenceSource } from
  "../stores/memory-evaluation-evidence-source";
import {
  ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
  defineAttributionBeliefShadowProducer,
} from "../workers/attribution-belief-shadow-producer";
import {
  MEMORY_STRATEGY_VERSION,
  registerMemoryStrategy,
} from "../../../core/consolidate/strategy-assignment";
import {
  materializeListenFormationSnapshot,
  sealListenFormationFinalization,
} from "./formation-ingestion";
import {
  LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION,
  materializeListenAttributionBeliefInputs,
} from "./attribution-belief-input";

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

const session = (): ListenSessionRecord => Object.freeze({
  id: "listen-session:one",
  conversationId: "conversation:one",
  clientConversationId: null,
  startedAt: "2026-08-12T12:00:00.000Z",
  updatedAt: "2026-08-12T12:01:00.000Z",
  endedAt: "2026-08-12T12:01:00.000Z",
  status: "completed",
  source: "omi",
  codec: "pcm16",
  sampleRate: 16_000,
  channels: 1,
});

const graph = (): GraphSnapshot => ({
  owner_account_id: "account:alice",
  graph_generation: 7,
  claims: [], entities: [], predicates: [], identity_authorizations: [], adjacency: [],
});

const snapshot = (values: readonly ListenTranscriptSegment[] = segments()) => materializeListenFormationSnapshot({
  finalization: sealListenFormationFinalization({
    owner_account_id: "account:alice", session: session(), segments: values,
  }),
  graph_snapshot: graph(),
  source_language: "en",
  account_timezone: "America/New_York",
  reference_clock_query_at: "2026-08-12T12:01:01.000Z",
  policy_version: "policy:listen:v1",
  predicate_alias_generation: "predicate-alias:7",
  authorization_generation: "authorization:7",
  stm_generation: "stm:7",
});

const strategy = () => registerMemoryStrategy({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: "strategy:listen-belief:test",
  work_kind: "identity_cluster",
  coordinates: {
    strategy_version: "listen-belief:v1", model_version: "calibrator:test:v1",
    prompt_version: "belief:prompt:v1", policy_version: "belief:policy:v1",
    code_version: "belief:code:v1", schema_version: "belief:schema:v1",
    tokenizer_version: "none", tool_version: "none",
    result_contract_version: ATTRIBUTION_BELIEF_SHADOW_RESULT_VERSION,
    speaker_strategy_version: "none", boundary_strategy_version: "none",
  },
});

describe("Listen attribution belief input", () => {
  test("turns noisy is_user observations into dependent evidence, never owner authority", () => {
    const inputs = materializeListenAttributionBeliefInputs(snapshot());
    expect(inputs).toHaveLength(2);
    expect(inputs.every((input) => input.version === "attribution-belief-shadow-input-v1")).toBeTrue();
    expect(inputs.every((input) => input.graph_frontier === inputs[0]!.graph_frontier)).toBeTrue();
    expect(inputs[0]!.hypothesis_candidates.map((item) => item.kind)).toEqual([
      "owner", "source_local", "unknown",
    ]);
    const observedOwner = inputs.find((input) => input.evidence_factors.length === 1)!;
    const observedOther = inputs.find((input) => input.evidence_factors.length === 2)!;
    expect(observedOwner.evidence_factors[0]!.direction).toBe("support");
    expect(observedOther.evidence_factors.map((item) => item.direction).sort()).toEqual([
      "counter", "support",
    ]);
    expect(new Set(inputs.flatMap((input) => input.evidence_factors)
      .map((item) => item.independence_group_ref)).size).toBe(1);
    expect(inputs.every((input) => input.previous_revision === null)).toBeTrue();
    const encoded = JSON.stringify(inputs);
    expect(encoded).not.toContain("I am planning the Atlas launch");
    expect(encoded).not.toContain("A second speaker prefers Friday");
    expect(encoded).not.toContain("person:owner");
    expect(encoded).not.toContain("subject:owner");
    expect(LISTEN_ATTRIBUTION_EVIDENCE_CONTRACT_VERSION).toBe("listen-attribution-evidence-v1");
  });

  test("feeds the exact text-free observation into the shadow calibrator", async () => {
    const input = materializeListenAttributionBeliefInputs(snapshot())[0]!;
    const source = defineMemoryEvaluationEvidenceSource(async (context, request) => ({
      kind: "found", owner_account_id: context.account_id, account_epoch: context.account_epoch,
      source_kind: request.source_kind, source_ref: request.source_ref,
      input_frontier: request.input_frontier, payload: input,
    }));
    const authorized = createAuthorizedLedgerWriteContextIssuer().issue({
        context_version: "authorized-ledger-write-context-v1",
        principal_id: "worker:belief-test", account_id: "account:alice",
        application_id: "app:belief-test", credential_id: "credential:belief-test",
        credential_generation: 1, capability: "memories.experiments.shadow",
        grant_id: "grant:belief-test", grant_version: 1, account_epoch: 7,
        destination_activation_revision: 1, lifecycle_state: "active", deletion_epoch: null,
        authentication_strength: "service-workload", issued_at_epoch_seconds: 100,
        expires_at_epoch_seconds: 200, authorization_state_digest: "a".repeat(64),
      }, 150);
    const copied = await source.load(authorized, {
      source_kind: "formation_input_snapshot",
      source_ref: "listen-belief:one",
      input_frontier: input.graph_frontier,
    });
    if (copied.kind !== "found") throw new Error("missing copied Listen belief input");
    let calls = 0;
    const produced = await defineAttributionBeliefShadowProducer({
      resolve_calibrator: async () => ({ calibrate: async (request) => {
        calls += 1;
        expect(JSON.stringify(request)).not.toContain("Atlas launch");
        return { probabilities: request.hypotheses.map((hypothesis) => ({
          hypothesis_id: hypothesis.hypothesis_id,
          probability_micros: hypothesis.kind === "owner" ? 650_000
            : hypothesis.kind === "unknown" ? 200_000 : 150_000,
        })) };
      } }),
    })({
      copied_input: copied.copied_input,
      strategy: strategy(),
      evaluation_role: "candidate",
      repeat_ordinal: 0,
    });
    expect(produced.kind).toBe("produced");
    expect(calls).toBe(1);
  });

  test("aggregates related channel evidence without pretending same-capture factors are independent", () => {
    const values = Object.freeze([
      ...segments(),
      Object.freeze({
        id: "segment:three", text: "I also prefer the morning.", is_user: true,
        start: 8, end: 10,
      }),
    ]);
    const inputs = materializeListenAttributionBeliefInputs(snapshot(values));
    expect(inputs).toHaveLength(2);
    const ownerChannel = inputs.find((input) => input.evidence_factors.length === 2
      && input.evidence_factors.every((factor) => factor.direction === "support"))!;
    expect(ownerChannel.evidence_factors).toHaveLength(2);
    expect(new Set(ownerChannel.evidence_factors.map((item) => item.evidence_ref)).size).toBe(2);
    expect(new Set(ownerChannel.evidence_factors.map((item) => item.independence_group_ref)).size).toBe(1);
    expect(JSON.stringify(ownerChannel)).not.toContain("prefer the morning");
  });

  test("rejects a changed noisy bit whose source-local channel does not match", () => {
    const original = snapshot();
    const events = original.events.map((event, index) => index === 0 ? {
      ...event,
      payload: { ...(event.payload as Record<string, unknown>), observed_is_user: false },
    } : event);
    expect(() => materializeListenAttributionBeliefInputs({ ...original, events }))
      .toThrow("invalid_source_coordinate");
  });

  test("rejects hidden target evidence and hostile payload accessors", () => {
    const original = snapshot();
    const hidden = original.evidence.map((evidence, index) => index === 0
      ? { ...evidence, state: "security_hidden" as const } : evidence);
    expect(() => materializeListenAttributionBeliefInputs({ ...original, evidence: hidden }))
      .toThrow("invalid_listen_observation");
    const payload = { ...(original.events[0]!.payload as Record<string, unknown>) };
    let getterCalls = 0;
    Object.defineProperty(payload, "observed_is_user", {
      enumerable: true,
      get: () => { getterCalls += 1; throw new Error("must not execute"); },
    });
    const events = [{ ...original.events[0]!, payload }, ...original.events.slice(1)];
    expect(() => materializeListenAttributionBeliefInputs({ ...original, events }))
      .toThrow("invalid_result");
    expect(getterCalls).toBe(0);
  });

  test("rejects authority-bearing identity on any later observation", () => {
    const values = Object.freeze([
      segments()[0]!,
      Object.freeze({
        id: "segment:three", text: "I also prefer the morning.", is_user: true,
        start: 8, end: 10,
      }),
    ]);
    const original = snapshot(values);
    const evidence = original.evidence.map((item, index) => index === 1 ? {
      ...item,
      source_identity_ref: {
        ...item.source_identity_ref!,
        producer: { producer_ref: "person:owner", contract_ref: "authority:forged" },
      },
    } : item);
    expect(() => materializeListenAttributionBeliefInputs({ ...original, evidence }))
      .toThrow("invalid_listen_observation");
  });

  test("rejects event identity substitution and cross-session observations", () => {
    const original = snapshot();
    const source = original.evidence[1]!.source_identity_ref!;
    const mismatchedPayload = original.events.map((event, index) => index === 1 ? {
      ...event,
      payload: {
        ...(event.payload as Record<string, unknown>),
        source_identity_ref: {
          namespace_instance_ref: source.namespace_instance_ref,
          local_key: "observed-channel:is-user",
          producer: { ...source.producer },
          asserted_identity: { ...source.asserted_identity },
        },
      },
    } : event);
    expect(() => materializeListenAttributionBeliefInputs({
      ...original, events: mismatchedPayload,
    })).toThrow("invalid_listen_observation");

    const crossSession = original.events.map((event, index) => index === 1
      ? { ...event, capture_session_id: "listen-session:other" } : event);
    expect(() => materializeListenAttributionBeliefInputs({
      ...original, events: crossSession,
    })).toThrow("invalid_listen_observation");
  });

  test("rejects a caller-supplied independence group that differs from the capture", () => {
    const original = snapshot();
    const evidence = original.evidence.map((item, index) => index === 1
      ? { ...item, source_independence_key: "capture:forged-independent-session" }
      : item);
    expect(() => materializeListenAttributionBeliefInputs({ ...original, evidence }))
      .toThrow("invalid_listen_observation");
  });
});
