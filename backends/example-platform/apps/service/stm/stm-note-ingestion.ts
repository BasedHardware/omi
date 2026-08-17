import { isProxy } from "node:util/types";

import type { MemoryStrategyAssignmentBundle } from "../../../core/consolidate/strategy-assignment";
import type { RegisteredDurableMemoryWorkExecutionPolicy } from "../../../core/consolidate/execution-policy";
import { ingestConversation } from "../../../core/extract/ingest";
import type { GraphSnapshot } from "../../../core/retrieve";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import { getWritingContext } from "../../../core/retrieve/writing-context";
import type { SourceIdentityRef } from "../../../core/schema";
import {
  STM_NOTE_SOURCE_SCHEMA_VERSION,
  parseUserAssertedStmNote,
  sealUserAssertedStmNote,
  type UserAssertedStmNote,
} from "../../../core/stm/note";
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

export interface StmNoteFormationMaterializationRequest {
  readonly note: UserAssertedStmNote;
  readonly graph_snapshot: GraphSnapshot;
  readonly source_language: string;
  readonly account_timezone: string;
  readonly reference_clock_query_at: string;
  readonly policy_version: string;
  readonly predicate_alias_generation: string;
  readonly authorization_generation: string;
  readonly stm_generation: string;
}

export interface StmNoteFormationIngestionRequest extends StmNoteFormationMaterializationRequest {
  readonly strategy_assignment: Readonly<MemoryStrategyAssignmentBundle>;
  readonly execution_policy: Readonly<RegisteredDurableMemoryWorkExecutionPolicy>;
  readonly accepted_at_event_time: number;
}

export type StmNoteFormationIngestionOutcome = FormationWorkIngestionOutcome;

export interface StmNoteFormationIngestionPort {
  accept(
    context: AuthorizedLedgerWriteContext,
    request: StmNoteFormationIngestionRequest,
  ): Promise<StmNoteFormationIngestionOutcome>;
}

interface FormationAcceptancePort {
  accept(
    context: AuthorizedLedgerWriteContext,
    request: FormationWorkIngestionRequest,
  ): Promise<FormationWorkIngestionOutcome>;
}

const fail = (code: string): never => { throw new TypeError(`stm note ingestion ${code}`); };

const exactRecord = (
  value: unknown,
  keys: readonly string[],
  code: string,
): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail(code);
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !/^[\x21-\x7e]{1,256}$/.test(value)) fail(code);
  return value;
};

const timestamp = (value: unknown, code: string): string => {
  const parsed = token(value, code);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(parsed)
    || Number.isNaN(Date.parse(parsed))) fail(code);
  return parsed;
};

const detachPlainTree = <T>(value: T, code: string): T => {
  try {
    return structuredClone(value);
  } catch {
    return fail(code);
  }
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

const integratorSourceIdentity = (
  note: Readonly<UserAssertedStmNote>,
): SourceIdentityRef => Object.freeze({
  namespace_instance_ref: `integrator-write:${sha256CanonicalContent({
    owner_account_id: note.owner_account_id,
    write_id: note.write_id,
    write_door: note.metadata.write_door,
  })}`,
  local_key: "integrator-channel:submitter",
  producer: Object.freeze({ producer_ref: null, contract_ref: null }),
  asserted_identity: Object.freeze({ domain: null, scope_ref: null }),
});

export const materializeStmNoteFormationSnapshot = (
  requestValue: StmNoteFormationMaterializationRequest,
): Readonly<FormationInputSnapshot> => {
  const request = exactRecord(requestValue, [
    "note", "graph_snapshot", "source_language", "account_timezone",
    "reference_clock_query_at", "policy_version", "predicate_alias_generation",
    "authorization_generation", "stm_generation",
  ], "invalid_request");
  const note = parseUserAssertedStmNote(request["note"]);
  const graph = detachPlainTree(request["graph_snapshot"] as GraphSnapshot, "invalid_graph_snapshot");
  const frontier = graphFrontier(graph, note.owner_account_id);
  const sourceLanguage = token(request["source_language"], "invalid_request");
  const accountTimezone = token(request["account_timezone"], "invalid_request");
  const queryAt = timestamp(request["reference_clock_query_at"], "invalid_request");
  const policyVersion = token(request["policy_version"], "invalid_request");
  const predicateAliasGeneration = token(request["predicate_alias_generation"], "invalid_request");
  const authorizationGeneration = token(request["authorization_generation"], "invalid_request");
  const stmGeneration = token(request["stm_generation"], "invalid_request");
  const ingested = ingestConversation({
    owner_account_id: note.owner_account_id,
    capture_session_id: note.note_id,
    stream_id: `stm-note:${note.note_digest}`,
    source_trust: "user_asserted",
    event_kind: "capture.integrator/stm-note",
    payload_schema_ref: STM_NOTE_SOURCE_SCHEMA_VERSION,
    utterances: [{
      source_unit_ref: note.write_id,
      source_identity_ref: integratorSourceIdentity(note),
      speaker_rendering: null,
      mention_ref: "integrator-channel:submitter",
      text: note.content,
      event_time: note.metadata.submitted_at,
      ingest_time: note.metadata.submitted_at,
    }],
  });
  const events = ingested.events.map((event) => Object.freeze({
    ...event,
    payload: Object.freeze({
      ...event.payload,
      source_identity_ref: integratorSourceIdentity(note),
      write_door: note.metadata.write_door,
      client_write_ref: note.metadata.client_write_ref,
      note_digest: note.note_digest,
      capture_kind: "user_asserted_stm_note",
    }),
  }));
  const evidence = ingested.evidence.map((item) => Object.freeze({
    ...item,
    source_identity_ref: integratorSourceIdentity(note),
  }));
  const context = getWritingContext(graph, {
    account_timezone: accountTimezone,
    policy_version: policyVersion,
    predicate_alias_generation: predicateAliasGeneration,
    authorization_generation: authorizationGeneration,
    stm_generation: stmGeneration,
    window: { text: note.content },
  });
  return parseFormationInputSnapshot({
    version: FORMATION_INPUT_SNAPSHOT_VERSION,
    owner_account_id: note.owner_account_id,
    work_id: note.formation_work_id,
    session_id: note.note_id,
    input_frontier: String(frontier),
    graph_frontier: frontier,
    observed_at: note.metadata.submitted_at,
    source_language: sourceLanguage,
    account_timezone: accountTimezone,
    reference_clock: { query_at: queryAt, capture_at: note.metadata.submitted_at },
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
    identity_authority_context: null,
  });
};

export const defineStmNoteIngestion = (
  formation: FormationAcceptancePort,
): StmNoteFormationIngestionPort => {
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
    async accept(contextValue, requestValue) {
      const authorized = assertAuthorizedLedgerWriteContext(contextValue);
      if (authorized.capability !== "memories.work.accept") fail("capability_denied");
      const request = exactRecord(requestValue, [
        "note", "graph_snapshot", "source_language", "account_timezone",
        "reference_clock_query_at", "policy_version", "predicate_alias_generation",
        "authorization_generation", "stm_generation", "strategy_assignment",
        "execution_policy", "accepted_at_event_time",
      ], "invalid_request");
      if (request["graph_snapshot"] === null || typeof request["graph_snapshot"] !== "object") {
        fail("invalid_graph_snapshot");
      }
      const note = parseUserAssertedStmNote(request["note"]);
      if (note.owner_account_id !== authorized.account_id) fail("owner_mismatch");
      const snapshot = materializeStmNoteFormationSnapshot({
        note,
        graph_snapshot: request["graph_snapshot"] as GraphSnapshot,
        source_language: request["source_language"],
        account_timezone: request["account_timezone"],
        reference_clock_query_at: request["reference_clock_query_at"],
        policy_version: request["policy_version"],
        predicate_alias_generation: request["predicate_alias_generation"],
        authorization_generation: request["authorization_generation"],
        stm_generation: request["stm_generation"],
      });
      return acceptFormation(contextValue, {
        snapshot,
        strategy_assignment: request["strategy_assignment"] as Readonly<MemoryStrategyAssignmentBundle>,
        execution_policy: request["execution_policy"] as Readonly<RegisteredDurableMemoryWorkExecutionPolicy>,
        accepted_at_event_time: request["accepted_at_event_time"] as number,
      });
    },
  });
};
