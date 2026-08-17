import { isProxy } from "node:util/types";

import type { MemoryStrategyAssignmentBundle } from "../../../core/consolidate/strategy-assignment";
import type { RegisteredDurableMemoryWorkExecutionPolicy } from "../../../core/consolidate/execution-policy";
import { EVIDENCE_EXCERPT_BUDGET, ingestConversation } from "../../../core/extract/ingest";
import type { GraphSnapshot } from "../../../core/retrieve";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { getWritingContext } from "../../../core/retrieve/writing-context";
import type { SourceIdentityRef } from "../../../core/schema";
import {
  assertAuthorizedLedgerWriteContext,
  type AuthorizedLedgerWriteContext,
} from "../auth/authorized-context";
import type {
  FormationWorkIngestionOutcome,
  FormationWorkIngestionRequest,
} from "../workers/formation-work-ingestion";
import {
  FORMATION_INPUT_SNAPSHOT_VERSION,
  parseFormationInputSnapshot,
  type FormationInputSnapshot,
} from "../workers/formation-work-producer";
import type { ListenSessionRecord, ListenTranscriptSegment } from "../stores/listen-store";

export const LISTEN_FORMATION_FINALIZATION_VERSION =
  "listen-formation-finalization-v1" as const;
export const LISTEN_FORMATION_SOURCE_SCHEMA_VERSION =
  "listen-formation-source-v1" as const;
export const LISTEN_FORMATION_MAX_SEGMENTS = 4_096;
export const LISTEN_FORMATION_MAX_TEXT_CODE_UNITS = 1_000_000;

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const SOURCE = /^[\x20-\x7e]{0,256}$/;

type TerminalListenStatus = Exclude<ListenSessionRecord["status"], "active">;
type CaptureCompleteness = "complete" | "incomplete_entitlement_exhausted" | "retained_interrupted";

export interface SealedListenFormationSegment extends ListenTranscriptSegment {
  readonly ordinal: number;
}

export interface ListenFormationFinalization {
  readonly version: typeof LISTEN_FORMATION_FINALIZATION_VERSION;
  readonly owner_account_id: string;
  readonly finalization_id: string;
  readonly formation_work_id: string;
  readonly session_id: string;
  readonly conversation_id: string;
  readonly terminal_status: TerminalListenStatus;
  readonly capture_completeness: CaptureCompleteness;
  readonly started_at: string;
  readonly ended_at: string;
  readonly source: string | null;
  readonly segments: readonly Readonly<SealedListenFormationSegment>[];
  readonly transcript_digest: string;
  readonly finalization_digest: string;
}

export interface ListenFormationMaterializationRequest {
  readonly finalization: ListenFormationFinalization;
  readonly graph_snapshot: GraphSnapshot;
  readonly source_language: string;
  readonly account_timezone: string;
  readonly reference_clock_query_at: string;
  readonly policy_version: string;
  readonly predicate_alias_generation: string;
  readonly authorization_generation: string;
  readonly stm_generation: string;
}

export interface ListenFormationIngestionRequest extends ListenFormationMaterializationRequest {
  readonly strategy_assignment: Readonly<MemoryStrategyAssignmentBundle>;
  readonly execution_policy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
  readonly accepted_at_event_time: number;
}

export type ListenFormationIngestionOutcome =
  | FormationWorkIngestionOutcome
  | Readonly<{ kind: "ineligible"; reason: "interrupted" | "empty_transcript" }>;

export interface ListenFormationIngestionPort {
  accept(
    context: AuthorizedLedgerWriteContext,
    request: ListenFormationIngestionRequest,
  ): Promise<ListenFormationIngestionOutcome>;
}

interface FormationAcceptancePort {
  accept(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkIngestionRequest,
  ): Promise<FormationWorkIngestionOutcome>;
}

const fail = (code: string): never => {
  throw new TypeError(`listen formation ingestion ${code}`);
};

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) fail(code);
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) fail(code);
  const actual = Reflect.ownKeys(value);
  if (actual.some((key) => typeof key !== "string")
    || actual.length !== keys.length
    || [...actual as string[]].sort().some((key, index) => key !== [...keys].sort()[index])) fail(code);
  const output: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
    output[key] = descriptor.value;
  }
  return output;
};

const denseArray = (value: unknown, code: string): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype) fail(code);
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")
    || keys.length !== value.length + 1 || !keys.includes("length")) fail(code);
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value;
};

/** Detach one exact persistence-shaped tree while permitting repeated input
 * references to become independent JSON occurrences. */
const detachPlainTree = <Value>(value: Value, code: string): Value => {
  const ancestors = new WeakSet<object>();
  let nodes = 0;
  const visit = (node: unknown, depth: number): unknown => {
    nodes += 1;
    if (nodes > 200_000 || depth > 64) fail(code);
    if (node === null || typeof node === "string" || typeof node === "boolean") return node;
    if (typeof node === "number") {
      if (!Number.isFinite(node)) fail(code);
      return node;
    }
    if (typeof node !== "object" || isProxy(node) || ancestors.has(node)) fail(code);
    const prototype = Object.getPrototypeOf(node);
    const array = Array.isArray(node);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
      fail(code);
    }
    ancestors.add(node);
    if (array) {
      const values = denseArray(node, code);
      const output = values.map((item) => visit(item, depth + 1));
      ancestors.delete(node);
      return output;
    }
    const keys = Reflect.ownKeys(node);
    if (keys.some((key) => typeof key !== "string")) fail(code);
    const output: Record<string, unknown> = {};
    for (const key of keys as string[]) {
      const descriptor = Object.getOwnPropertyDescriptor(node, key);
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
      output[key] = visit(descriptor.value, depth + 1);
    }
    ancestors.delete(node);
    return output;
  };
  return visit(value, 0) as Value;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const timestamp = (value: unknown, code: string): string => {
  const result = token(value, code);
  const millis = Date.parse(result);
  if (!Number.isFinite(millis)) fail(code);
  return result;
};

const digestCoordinate = (kind: string, owner: string, session: string): string =>
  `${kind}:${sha256CanonicalContent({ owner_account_id: owner, session_id: session })}`;

const completeness = (status: TerminalListenStatus): CaptureCompleteness => {
  if (status === "completed") return "complete";
  if (status === "entitlement_exhausted") return "incomplete_entitlement_exhausted";
  return "retained_interrupted";
};

const terminalSession = (value: unknown): Readonly<ListenSessionRecord> => {
  const root = exactRecord(value, [
    "id", "conversationId", "clientConversationId", "startedAt", "updatedAt", "endedAt",
    "status", "source", "codec", "sampleRate", "channels",
  ], "invalid_session");
  const status = root["status"];
  if (status !== "completed" && status !== "entitlement_exhausted" && status !== "interrupted") {
    fail("invalid_session");
  }
  if (root["endedAt"] === null) fail("invalid_session");
  const source = root["source"];
  if (source !== null && (typeof source !== "string" || !SOURCE.test(source))) fail("invalid_session");
  if (root["clientConversationId"] !== null) token(root["clientConversationId"], "invalid_session");
  if (!Number.isSafeInteger(root["sampleRate"]) || (root["sampleRate"] as number) <= 0
    || !Number.isSafeInteger(root["channels"]) || (root["channels"] as number) <= 0) {
    fail("invalid_session");
  }
  const session: ListenSessionRecord = {
    id: token(root["id"], "invalid_session"),
    conversationId: token(root["conversationId"], "invalid_session"),
    clientConversationId: root["clientConversationId"] as string | null,
    startedAt: timestamp(root["startedAt"], "invalid_session"),
    updatedAt: timestamp(root["updatedAt"], "invalid_session"),
    endedAt: timestamp(root["endedAt"], "invalid_session"),
    status,
    source: source as string | null,
    codec: token(root["codec"], "invalid_session"),
    sampleRate: root["sampleRate"] as number,
    channels: root["channels"] as number,
  };
  if (Date.parse(session.endedAt!) < Date.parse(session.startedAt)) fail("invalid_session");
  return Object.freeze(session);
};

const sealedSegments = (value: unknown): readonly Readonly<SealedListenFormationSegment>[] => {
  const values = denseArray(value, "invalid_segments");
  if (values.length > LISTEN_FORMATION_MAX_SEGMENTS) fail("too_many_segments");
  let textUnits = 0;
  const ids = new Set<string>();
  const output = values.map((item, ordinal) => {
    const root = exactRecord(item, ["id", "text", "is_user", "start", "end"], "invalid_segment");
    const id = token(root["id"], "invalid_segment");
    const text = root["text"];
    if (typeof text !== "string" || text.length === 0 || text.length > EVIDENCE_EXCERPT_BUDGET) {
      fail("invalid_segment_text");
    }
    if (typeof root["is_user"] !== "boolean"
      || typeof root["start"] !== "number" || !Number.isFinite(root["start"])
      || typeof root["end"] !== "number" || !Number.isFinite(root["end"])
      || (root["start"] as number) < 0 || (root["end"] as number) < (root["start"] as number)) {
      fail("invalid_segment");
    }
    if (ids.has(id)) fail("duplicate_segment_id");
    ids.add(id);
    textUnits += text.length;
    if (textUnits > LISTEN_FORMATION_MAX_TEXT_CODE_UNITS) fail("transcript_too_large");
    return Object.freeze({
      ordinal,
      id,
      text,
      is_user: root["is_user"] as boolean,
      start: root["start"] as number,
      end: root["end"] as number,
    });
  });
  return Object.freeze(output);
};

export const sealListenFormationFinalization = (input: {
  readonly owner_account_id: string;
  readonly session: ListenSessionRecord;
  readonly segments: readonly ListenTranscriptSegment[];
}): Readonly<ListenFormationFinalization> => {
  const root = exactRecord(input, ["owner_account_id", "session", "segments"], "invalid_finalization");
  const owner = token(root["owner_account_id"], "invalid_finalization");
  const session = terminalSession(root["session"]);
  const segments = sealedSegments(root["segments"]);
  const transcriptDigest = sha256CanonicalContent({
    contract_version: LISTEN_FORMATION_SOURCE_SCHEMA_VERSION,
    owner_account_id: owner,
    session_id: session.id,
    conversation_id: session.conversationId,
    terminal_status: session.status,
    started_at: session.startedAt,
    ended_at: session.endedAt,
    source: session.source,
    segments,
  });
  const finalizationId = digestCoordinate("listen-finalization", owner, session.id);
  const formationWorkId = digestCoordinate("listen-formation-work", owner, session.id);
  const base = {
    version: LISTEN_FORMATION_FINALIZATION_VERSION,
    owner_account_id: owner,
    finalization_id: finalizationId,
    formation_work_id: formationWorkId,
    session_id: session.id,
    conversation_id: session.conversationId,
    terminal_status: session.status as TerminalListenStatus,
    capture_completeness: completeness(session.status as TerminalListenStatus),
    started_at: session.startedAt,
    ended_at: session.endedAt!,
    source: session.source,
    segments,
    transcript_digest: transcriptDigest,
  };
  return Object.freeze({
    ...base,
    finalization_digest: sha256CanonicalContent({
      contract_version: LISTEN_FORMATION_FINALIZATION_VERSION,
      ...base,
    }),
  });
};

const parseFinalization = (value: unknown): Readonly<ListenFormationFinalization> => {
  const root = exactRecord(value, [
    "version", "owner_account_id", "finalization_id", "formation_work_id", "session_id",
    "conversation_id", "terminal_status", "capture_completeness", "started_at", "ended_at",
    "source", "segments", "transcript_digest", "finalization_digest",
  ], "invalid_finalization");
  if (root["version"] !== LISTEN_FORMATION_FINALIZATION_VERSION) fail("invalid_finalization");
  const reconstructed = sealListenFormationFinalization({
    owner_account_id: token(root["owner_account_id"], "invalid_finalization"),
    session: {
      id: token(root["session_id"], "invalid_finalization"),
      conversationId: token(root["conversation_id"], "invalid_finalization"),
      clientConversationId: null,
      startedAt: timestamp(root["started_at"], "invalid_finalization"),
      updatedAt: timestamp(root["ended_at"], "invalid_finalization"),
      endedAt: timestamp(root["ended_at"], "invalid_finalization"),
      status: root["terminal_status"] as TerminalListenStatus,
      source: root["source"] as string | null,
      codec: "sealed",
      sampleRate: 1,
      channels: 1,
    },
    segments: denseArray(root["segments"], "invalid_finalization").map((item) => {
      const segment = exactRecord(item, ["ordinal", "id", "text", "is_user", "start", "end"], "invalid_finalization");
      return {
        id: segment["id"], text: segment["text"], is_user: segment["is_user"],
        start: segment["start"], end: segment["end"],
      } as ListenTranscriptSegment;
    }),
  });
  if (root["finalization_id"] !== reconstructed.finalization_id
    || root["formation_work_id"] !== reconstructed.formation_work_id
    || root["capture_completeness"] !== reconstructed.capture_completeness
    || root["transcript_digest"] !== reconstructed.transcript_digest
    || root["finalization_digest"] !== reconstructed.finalization_digest) fail("finalization_digest_mismatch");
  return reconstructed;
};

const graphFrontier = (snapshot: GraphSnapshot, owner: string): number => {
  if (snapshot === null || typeof snapshot !== "object" || isProxy(snapshot)
    || snapshot.owner_account_id !== owner) fail("graph_owner_mismatch");
  const frontier = snapshot.graph_generation;
  const parsed = typeof frontier === "number" ? frontier
    : typeof frontier === "string" && /^(?:0|[1-9][0-9]*)$/.test(frontier)
      ? Number(frontier) : Number.NaN;
  if (!Number.isSafeInteger(parsed) || parsed < 0) fail("invalid_graph_frontier");
  return parsed;
};

const eventTime = (startedAt: string, offsetSeconds: number): string => {
  const value = Date.parse(startedAt) + offsetSeconds * 1_000;
  if (!Number.isFinite(value)) fail("invalid_segment_time");
  try { return new Date(value).toISOString(); }
  catch { return fail("invalid_segment_time"); }
};

const sourceIdentity = (
  finalization: Readonly<ListenFormationFinalization>,
  observedUser: boolean,
): SourceIdentityRef => Object.freeze({
  namespace_instance_ref: `listen-session:${sha256CanonicalContent({
    owner_account_id: finalization.owner_account_id,
    session_id: finalization.session_id,
  })}`,
  local_key: observedUser ? "observed-channel:is-user" : "observed-channel:not-user",
  producer: Object.freeze({ producer_ref: null, contract_ref: null }),
  asserted_identity: Object.freeze({ domain: null, scope_ref: null }),
});

export const materializeListenFormationSnapshot = (
  requestValue: ListenFormationMaterializationRequest,
): Readonly<FormationInputSnapshot> => {
  const request = exactRecord(requestValue, [
    "finalization", "graph_snapshot", "source_language", "account_timezone",
    "reference_clock_query_at", "policy_version", "predicate_alias_generation",
    "authorization_generation", "stm_generation",
  ], "invalid_request");
  const finalization = parseFinalization(request["finalization"]);
  if (finalization.terminal_status === "interrupted") fail("ineligible_interrupted");
  if (finalization.segments.length === 0) fail("ineligible_empty_transcript");
  const graph = detachPlainTree(request["graph_snapshot"] as GraphSnapshot, "invalid_graph_snapshot");
  const frontier = graphFrontier(graph, finalization.owner_account_id);
  const sourceLanguage = token(request["source_language"], "invalid_request");
  const accountTimezone = token(request["account_timezone"], "invalid_request");
  const queryAt = timestamp(request["reference_clock_query_at"], "invalid_request");
  const policyVersion = token(request["policy_version"], "invalid_request");
  const predicateAliasGeneration = token(request["predicate_alias_generation"], "invalid_request");
  const authorizationGeneration = token(request["authorization_generation"], "invalid_request");
  const stmGeneration = token(request["stm_generation"], "invalid_request");
  const utterances = finalization.segments.map((segment) => ({
    source_unit_ref: segment.id,
    source_identity_ref: sourceIdentity(finalization, segment.is_user),
    speaker_rendering: null,
    mention_ref: segment.is_user ? "observed-channel:is-user" : "observed-channel:not-user",
    text: segment.text,
    event_time: eventTime(finalization.started_at, segment.start),
    ingest_time: finalization.ended_at,
  }));
  const ingested = ingestConversation({
    owner_account_id: finalization.owner_account_id,
    capture_session_id: finalization.session_id,
    stream_id: `listen:${sha256CanonicalContent({
      owner_account_id: finalization.owner_account_id,
      session_id: finalization.session_id,
    })}`,
    source_trust: "listen-finalized",
    event_kind: "capture.transcript/listen-segment",
    payload_schema_ref: LISTEN_FORMATION_SOURCE_SCHEMA_VERSION,
    utterances,
  });
  const events = ingested.events.map((event, index) => Object.freeze({
    ...event,
    payload: Object.freeze({
      ...event.payload,
      source_identity_ref: sourceIdentity(
        finalization,
        finalization.segments[index]!.is_user,
      ),
      observed_is_user: finalization.segments[index]!.is_user,
      segment_start_seconds: finalization.segments[index]!.start,
      segment_end_seconds: finalization.segments[index]!.end,
      capture_completeness: finalization.capture_completeness,
      finalization_digest: finalization.finalization_digest,
      conversation_id: finalization.conversation_id,
      terminal_status: finalization.terminal_status,
      source: finalization.source,
    }),
  }));
  // `ingestConversation` intentionally keeps the caller's identity object on
  // both the event and evidence. The durable snapshot is a detached plain tree
  // (no repeated object identity), so remint the same typed coordinate for the
  // evidence occurrence instead of relaxing that persistence boundary.
  const evidence = ingested.evidence.map((item, index) => Object.freeze({
    ...item,
    source_identity_ref: sourceIdentity(
      finalization,
      finalization.segments[index]!.is_user,
    ),
  }));
  const context = getWritingContext(graph, {
    account_timezone: accountTimezone,
    policy_version: policyVersion,
    predicate_alias_generation: predicateAliasGeneration,
    authorization_generation: authorizationGeneration,
    stm_generation: stmGeneration,
    window: { text: finalization.segments.map((segment) => segment.text).join("\n") },
  });
  return parseFormationInputSnapshot({
    version: FORMATION_INPUT_SNAPSHOT_VERSION,
    owner_account_id: finalization.owner_account_id,
    work_id: finalization.formation_work_id,
    session_id: finalization.session_id,
    input_frontier: String(frontier),
    graph_frontier: frontier,
    observed_at: finalization.ended_at,
    source_language: sourceLanguage,
    account_timezone: accountTimezone,
    reference_clock: { query_at: queryAt, capture_at: finalization.ended_at },
    context,
    predicate_registry: Object.freeze((graph.predicates ?? []).map(({ predicate }) => predicate.predicate_id)),
    entity_registry: Object.freeze(graph.entities.map(({ entity }) => entity.entity_id)),
    target_evidence_ids: Object.freeze(evidence.map((item) => item.evidence_id)),
    evidence,
    events,
    entities: Object.freeze(graph.entities.map(({ entity }) => entity)),
    identity_authorizations: Object.freeze(
      (graph.identity_authorizations ?? []).map(({ authorization }) => authorization),
    ),
    // The graph reconstruction port does not yet reconstruct the complete
    // owner-confirmation/producer-policy authority context. Never pretend that
    // authorization rows alone prove owner identity.
    identity_authority_context: null,
  });
};

export const defineListenFormationIngestion = (
  formation: FormationAcceptancePort,
): ListenFormationIngestionPort => {
  if (formation === null || typeof formation !== "object" || Array.isArray(formation)
    || isProxy(formation) || Object.getPrototypeOf(formation) !== Object.prototype) {
    fail("invalid_formation_port");
  }
  const acceptDescriptor = Object.getOwnPropertyDescriptor(formation, "accept");
  if (!acceptDescriptor || !("value" in acceptDescriptor)
    || typeof acceptDescriptor.value !== "function" || !acceptDescriptor.enumerable) {
    fail("invalid_formation_port");
  }
  const acceptFormation = acceptDescriptor.value.bind(formation) as FormationAcceptancePort["accept"];
  return Object.freeze({
  async accept(context, requestValue) {
    const authorized = assertAuthorizedLedgerWriteContext(context);
    if (authorized.capability !== "memories.work.accept") fail("capability_denied");
    const request = exactRecord(requestValue, [
      "finalization", "graph_snapshot", "source_language", "account_timezone",
      "reference_clock_query_at", "policy_version", "predicate_alias_generation",
      "authorization_generation", "stm_generation", "strategy_assignment",
      "execution_policy", "accepted_at_event_time",
    ], "invalid_request");
    const finalization = parseFinalization(request["finalization"]);
    if (finalization.owner_account_id !== authorized.account_id) fail("owner_mismatch");
    if (finalization.terminal_status === "interrupted") {
      return Object.freeze({ kind: "ineligible" as const, reason: "interrupted" as const });
    }
    if (finalization.segments.length === 0) {
      return Object.freeze({ kind: "ineligible" as const, reason: "empty_transcript" as const });
    }
    const snapshot = materializeListenFormationSnapshot({
      finalization,
      graph_snapshot: request["graph_snapshot"] as GraphSnapshot,
      source_language: request["source_language"] as string,
      account_timezone: request["account_timezone"] as string,
      reference_clock_query_at: request["reference_clock_query_at"] as string,
      policy_version: request["policy_version"] as string,
      predicate_alias_generation: request["predicate_alias_generation"] as string,
      authorization_generation: request["authorization_generation"] as string,
      stm_generation: request["stm_generation"] as string,
    });
    return acceptFormation(authorized, {
      snapshot,
      strategy_assignment: request["strategy_assignment"] as Readonly<MemoryStrategyAssignmentBundle>,
      execution_policy: request["execution_policy"] as Readonly<RegisteredDurableMemoryWorkExecutionPolicy>,
      accepted_at_event_time: request["accepted_at_event_time"] as number,
    });
  },
  });
};
