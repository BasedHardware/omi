import { describe, expect, test } from "bun:test";

import { createAuthorizedLedgerWriteContextIssuer } from "../auth/authorized-context-internal";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import {
  LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
  LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
  defineListenFormationOutboxConsumer,
  type ListenFormationOutboxLease,
  type ListenFormationOutboxPayload,
  type ListenFormationOutboxRepository,
} from "./formation-outbox-consumer";
import {
  sealListenFormationFinalization,
  type ListenFormationIngestionRequest,
} from "./formation-ingestion";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../stores/listen-store";

const digest = (character: string): string => character.repeat(64);
const issuer = createAuthorizedLedgerWriteContextIssuer();

const context = (capability = "memories.work.accept"): AuthorizedLedgerWriteContext =>
  issuer.issue({
    context_version: "authorized-ledger-write-context-v1",
    principal_id: "principal:listen-consumer",
    account_id: "account:alice",
    application_id: "app:listen-consumer",
    credential_id: "credential:listen-consumer",
    credential_generation: 1,
    capability,
    grant_id: "grant:listen-consumer",
    grant_version: 1,
    account_epoch: 7,
    destination_activation_revision: 1,
    lifecycle_state: "active",
    deletion_epoch: null,
    authentication_strength: "service-workload",
    issued_at_epoch_seconds: 100,
    expires_at_epoch_seconds: 200,
    authorization_state_digest: digest("a"),
  }, 150);

const session = (): ListenSessionRecord => Object.freeze({
  id: "listen-session:one",
  conversationId: "conversation:one",
  clientConversationId: null,
  startedAt: "2026-08-13T12:00:00.000Z",
  updatedAt: "2026-08-13T12:01:00.000Z",
  endedAt: "2026-08-13T12:01:00.000Z",
  status: "completed",
  source: "omi",
  codec: "pcm16",
  sampleRate: 16_000,
  channels: 1,
});

const segment = (): ListenTranscriptSegment => Object.freeze({
  id: "segment:one", text: "A bounded transcript.", is_user: true, start: 0, end: 1,
});

const finalization = sealListenFormationFinalization({
  owner_account_id: "account:alice", session: session(), segments: [segment()],
});

const lease = (): ListenFormationOutboxLease => Object.freeze({
  version: LISTEN_FORMATION_OUTBOX_LEASE_VERSION,
  owner_account_id: "account:alice",
  outbox_id: "listen-outbox:one",
  finalization_id: finalization.finalization_id,
  formation_work_id: finalization.formation_work_id,
  finalization_digest: finalization.finalization_digest,
  payload_digest: digest("b"),
  lease_fence: 1,
});

const payload = (overrides: Partial<ListenFormationOutboxPayload> = {}): ListenFormationOutboxPayload => ({
  version: LISTEN_FORMATION_OUTBOX_PAYLOAD_VERSION,
  owner_account_id: "account:alice",
  outbox_id: "listen-outbox:one",
  finalization_id: finalization.finalization_id,
  formation_work_id: finalization.formation_work_id,
  finalization_digest: finalization.finalization_digest,
  payload_digest: digest("b"),
  finalization,
  ...overrides,
});

const ingestionRequest = (): ListenFormationIngestionRequest => ({
  finalization,
  graph_snapshot: {
  owner_account_id: "account:alice", graph_generation: 7,
  claims: [], entities: [], predicates: [], identity_authorizations: [], adjacency: [],
  },
  source_language: "en", account_timezone: "America/New_York",
  reference_clock_query_at: "2026-08-13T12:01:01.000Z", policy_version: "policy:listen:v1",
  predicate_alias_generation: "predicate-alias:7", authorization_generation: "authorization:7",
  stm_generation: "stm:7", strategy_assignment: {}, execution_policy: {}, accepted_at_event_time: 101,
} as unknown as ListenFormationIngestionRequest);

type Events = { readonly name: string; readonly value?: unknown }[];

const repository = (
  events: Events,
  claim: unknown = { kind: "claimed", lease: lease() },
  loaded: unknown = { kind: "found", payload: payload() },
): ListenFormationOutboxRepository => ({
  async claimNext() { events.push({ name: "claim" }); return claim as never; },
  async load(_context, value) { events.push({ name: "load", value }); return loaded as never; },
  async markAccepted(_context, _lease, value) { events.push({ name: "ack", value }); return { kind: "accepted" }; },
  async recordFailure(_context, value, request) {
    events.push({ name: "failure", value: request });
    return { kind: "recorded" };
  },
});

const consumer = (
  events: Events,
  overrides: Partial<Parameters<typeof defineListenFormationOutboxConsumer>[0]> = {},
) => defineListenFormationOutboxConsumer({
  repository: repository(events),
  load_ingestion_request: async () => ingestionRequest(),
  formation: {
    async accept(_context, request) {
      events.push({ name: "formation", value: request });
      return { kind: "accepted", job: { accepted_work_digest: digest("d") } } as never;
    },
  },
  ...overrides,
});

describe("Listen formation outbox consumer", () => {
  test("requires accept authority and is idle without an outbox", async () => {
    const events: Events = [];
    const service = consumer(events, {
      repository: repository(events, { kind: "none_available" }),
    });
    await expect(service.runNext(context("memories.work.execute"))).resolves.toEqual({
      kind: "stopped", stop_code: "authorization_or_context", leased: 0, formation_calls: 0,
    });
    await expect(service.runNext(context())).resolves.toEqual({
      kind: "idle", leased: 0, formation_calls: 0,
    });
    expect(events.map((event) => event.name)).toEqual(["claim"]);
  });

  test("loads exact dependencies, accepts once, then acknowledges the lease", async () => {
    const events: Events = [];
    const service = consumer(events);
    await expect(service.runNext(context())).resolves.toEqual({
      kind: "accepted", result: "accepted", leased: 1, formation_calls: 1,
    });
    expect(events.map((event) => event.name)).toEqual(["claim", "load", "formation", "ack"]);
    const request = events.find((event) => event.name === "formation")!.value as Record<string, unknown>;
    expect(request.source_language).toBe("en");
    expect(request.account_timezone).toBe("America/New_York");
    expect(request.graph_snapshot).toEqual(ingestionRequest().graph_snapshot);
    expect(JSON.stringify(request)).not.toContain("person:owner");
  });

  test("a formation exception records retryable failure and never acknowledges", async () => {
    const events: Events = [];
    const service = consumer(events, {
      formation: {
        async accept() { throw new Error("provider transcript secret"); },
      },
    });
    await expect(service.runNext(context())).resolves.toEqual({
      kind: "failed", leased: 1, formation_calls: 1,
    });
    expect(events.map((event) => event.name)).toEqual(["claim", "load", "failure"]);
    expect(JSON.stringify(events)).not.toContain("provider transcript secret");
  });

  test("hostile leases and mismatched payloads fail before formation", async () => {
    const events: Events = [];
    const malformed = consumer(events, {
      repository: repository(events, {
        kind: "claimed", lease: { ...lease(), lease_fence: -1 },
      }),
    });
    await expect(malformed.runNext(context())).resolves.toEqual({
      kind: "stopped", stop_code: "invalid_lease", leased: 1, formation_calls: 0,
    });
    const mismatchEvents: Events = [];
    const mismatch = consumer(mismatchEvents, {
      repository: repository(mismatchEvents, { kind: "claimed", lease: lease() },
        { kind: "found", payload: payload({ payload_digest: digest("c") }) }),
    });
    await expect(mismatch.runNext(context())).resolves.toEqual({
      kind: "failed", leased: 1, formation_calls: 0,
    });
    expect(mismatchEvents.map((event) => event.name)).toEqual(["claim", "load", "failure"]);
  });

  test("loader output is exact and a stale ack remains a typed stop", async () => {
    const events: Events = [];
    const staleRepository: ListenFormationOutboxRepository = {
      ...repository(events),
      async markAccepted() { return { kind: "stale_lease" }; },
    };
    const service = consumer(events, { repository: staleRepository });
    await expect(service.runNext(context())).resolves.toEqual({
      kind: "stopped", stop_code: "stale_lease", leased: 1, formation_calls: 1,
    });
    const hostileEvents: Events = [];
    const hostile = consumer(hostileEvents, {
      load_ingestion_request: async () => new Proxy(ingestionRequest(), {}),
    });
    await expect(hostile.runNext(context())).resolves.toEqual({
      kind: "failed", leased: 1, formation_calls: 0,
    });
  });

  test("a crash after formation acceptance replays the same work before one acknowledgement", async () => {
    let claimCount = 0;
    let formationCount = 0;
    let acknowledgementCount = 0;
    const crashRepository: ListenFormationOutboxRepository = {
      async claimNext() {
        claimCount += 1;
        return { kind: "claimed", lease: { ...lease(), lease_fence: claimCount } };
      },
      async load(_context, claimedLease) {
        return { kind: "found", payload: payload({
          outbox_id: claimedLease.outbox_id,
          finalization_id: claimedLease.finalization_id,
          formation_work_id: claimedLease.formation_work_id,
          finalization_digest: claimedLease.finalization_digest,
          payload_digest: claimedLease.payload_digest,
        }) };
      },
      async markAccepted() {
        acknowledgementCount += 1;
        if (acknowledgementCount === 1) throw new Error("simulated process loss before ack");
        return { kind: "accepted" };
      },
      async recordFailure() { return { kind: "recorded" }; },
    };
    const service = consumer([], {
      repository: crashRepository,
      formation: {
        async accept() {
          formationCount += 1;
          return {
            kind: formationCount === 1 ? "accepted" : "replayed",
            job: { accepted_work_digest: digest("d") },
          } as never;
        },
      },
    });

    await expect(service.runNext(context())).resolves.toEqual({
      kind: "stopped", stop_code: "storage_retryable", leased: 1, formation_calls: 1,
    });
    await expect(service.runNext(context())).resolves.toEqual({
      kind: "accepted", result: "replayed", leased: 1, formation_calls: 1,
    });
    expect({ claimCount, formationCount, acknowledgementCount }).toEqual({
      claimCount: 2, formationCount: 2, acknowledgementCount: 2,
    });
  });
});
