import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";
import type { Database } from "bun:sqlite";

import { compareStrings } from "../../core/order";
import type { GraphSnapshot } from "../../core/retrieve";
import type { AcceptedCoverageState } from "../../core/retrieve/recall-integrity";
import { validateProvisionalClaim } from "../../core/schema/claim-validation";
import { EvidenceSchema, L1EventSchema, type Evidence } from "../../core/schema";
import { validateStrict } from "../../core/schema/json";
import { compareStmOrder } from "../../core/stm";
import type { DurableStmItem } from "./stm";
import type { SqliteLedger } from "./index";

type PlainJson = null | boolean | number | string | readonly PlainJson[] | { readonly [key: string]: PlainJson };

const INTERNAL_REF = /^[\x21-\x7e]{1,512}$/;
const ACCEPTED_STATES = new Set<AcceptedCoverageState>([
  "searched",
  "no_eligible",
  "pending",
  "unavailable",
  "stale",
  "bypassed",
  "source_bound",
  "time_bound",
  "policy_bound",
]);
const MAX_BOUND = Number.MAX_SAFE_INTEGER - 1;

const fail = (message: string): never => { throw new TypeError(`SQLite QA recall read: ${message}`); };

const compareCodeUnits = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

/**
 * The accepted-source port is the only caller-controlled value boundary in
 * this adapter. Detach it before inspecting semantic fields. A value may be
 * reached only once: shared-reference aliases are rejected rather than copied,
 * because an alias can otherwise smuggle identity and TOCTOU assumptions into
 * later application code.
 */
const detachPlainJson = (input: unknown): PlainJson => {
  const seen = new WeakSet<object>();
  const copy = (value: unknown): PlainJson => {
    if (value === null || typeof value === "string" || typeof value === "boolean") return value;
    if (typeof value === "number") {
      if (!Number.isFinite(value)) return fail("accepted state rejects non-finite numbers");
      return Object.is(value, -0) ? 0 : value;
    }
    if (typeof value !== "object") return fail("accepted state accepts plain JSON only");
    if (isProxy(value)) return fail("accepted state rejects proxies");
    if (seen.has(value)) return fail("accepted state rejects cycles and shared aliases");
    seen.add(value);

    const isArray = Array.isArray(value);
    const prototype = Object.getPrototypeOf(value);
    if (isArray ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) {
      return fail("accepted state rejects non-plain objects");
    }
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const keys = Reflect.ownKeys(descriptors);
    if (keys.some((key) => typeof key === "symbol")) return fail("accepted state rejects symbol keys");

    if (isArray) {
      const stringKeys = keys as string[];
      const dataKeys = stringKeys.filter((key) => key !== "length");
      if (dataKeys.length !== value.length
        || dataKeys.some((key, index) => key !== String(index))) {
        return fail("accepted state rejects sparse or decorated arrays");
      }
      const output: PlainJson[] = [];
      for (const key of dataKeys) {
        const descriptor = descriptors[key];
        if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
          return fail("accepted state rejects accessors and hidden fields");
        }
        output.push(copy(descriptor.value));
      }
      return Object.freeze(output);
    }

    const output = Object.create(null) as Record<string, PlainJson>;
    for (const key of (keys as string[]).sort(compareCodeUnits)) {
      const descriptor = descriptors[key];
      if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
        return fail("accepted state rejects accessors and hidden fields");
      }
      output[key] = copy(descriptor.value);
    }
    return Object.freeze(output);
  };
  return copy(input);
};

const isRecord = (value: PlainJson): value is { readonly [key: string]: PlainJson } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const hasExactKeys = (value: PlainJson, expected: readonly string[]): value is { readonly [key: string]: PlainJson } => {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value).sort(compareCodeUnits);
  const wanted = [...expected].sort(compareCodeUnits);
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
};

const canonicalJson = (value: PlainJson): string => {
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.entries(value).sort(([left], [right]) => compareCodeUnits(left, right))
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalJson(item)}`).join(",")}}`;
};

const canonicalBytes = (value: PlainJson): number => new TextEncoder().encode(canonicalJson(value)).byteLength;
const canonicalDigest = (value: PlainJson): string => createHash("sha256").update(canonicalJson(value)).digest("hex");

const deepFreeze = <Value>(value: Value): Value => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nested of Object.values(value)) deepFreeze(nested);
    Object.freeze(value);
  }
  return value;
};

const requireSafeBound = (value: number, name: string): number => {
  if (!Number.isSafeInteger(value) || value < 0) return fail(`${name} must be a non-negative safe integer`);
  // The SQL item query uses limit + 1. Applying the same arithmetic ceiling to
  // both knobs also keeps every accumulated byte count exactly representable.
  if (value > MAX_BOUND) return fail(`${name} is too large`);
  return value;
};

const requireTimezone = (value: string): string => {
  if (typeof value !== "string" || value.length === 0) return fail("account_timezone must be non-empty");
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(0);
  } catch {
    return fail("account_timezone is invalid");
  }
  return value;
};

const requireString = (value: unknown, name: string): string => {
  if (typeof value !== "string" || value.length === 0) return fail(`${name} must be a non-empty string`);
  return value;
};

const requireNonnegativeInteger = (value: unknown, name: string): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    return fail(`${name} must be a non-negative safe integer`);
  }
  return value;
};

const parseJson = (value: unknown, name: string): unknown => {
  if (typeof value !== "string") return fail(`${name} must be JSON text`);
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return fail(`${name} is malformed JSON`);
  }
};

const parseUniqueStringArray = (value: unknown, name: string): readonly string[] => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.length === 0)) {
    return fail(`${name} must be an array of non-empty strings`);
  }
  if (new Set(value).size !== value.length) return fail(`${name} must be unique`);
  return Object.freeze([...value]);
};

const parseArgumentOrigins = (value: unknown): Readonly<Record<string, "suggested" | "independent">> => {
  if (typeof value !== "object" || value === null || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) {
    return fail("argument_origins_json must be a plain object");
  }
  const output: Record<string, "suggested" | "independent"> = Object.create(null);
  for (const [key, origin] of Object.entries(value)) {
    if (!key || (origin !== "suggested" && origin !== "independent")) {
      return fail("argument_origins_json contains an invalid entry");
    }
    output[key] = origin;
  }
  return Object.freeze(output);
};

// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
interface StmSqlRow {
  readonly id: unknown;
  readonly session_id: unknown;
  readonly event_time_watermark: unknown;
  readonly capture_sequence: unknown;
  readonly revision_lineage: unknown;
  readonly ingest_sequence: unknown;
  readonly entity_refs_json: unknown;
  readonly lexical_terms_json: unknown;
  readonly vector_key: unknown;
  readonly predicate_id: unknown;
  readonly bytes: unknown;
  readonly claim_json: unknown;
  readonly evidence_json: unknown;
  readonly argument_origins_json: unknown;
  readonly settled_window_id: unknown;
}

// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
const decodeStmRow = (row: StmSqlRow, ownerAccountId: string, durable: GraphSnapshot): DurableStmItem => {
  const id = requireString(row.id, "STM row id");
  const claimValue = parseJson(row.claim_json, "claim_json");
  if (!validateProvisionalClaim(claimValue)) return fail("STM row contains an invalid provisional claim");
  if (claimValue.owner_account_id !== ownerAccountId) return fail("STM claim owner does not match the coherent load owner");
  // The current harness producer (`itemFor`) writes this exact identity. It is
  // the only safe row-to-claim binding available in the disposable schema.
  if (id !== claimValue.claim_revision_id) return fail("STM row id does not match its claim revision id");

  const evidenceValue = parseJson(row.evidence_json, "evidence_json");
  if (!Array.isArray(evidenceValue) || !evidenceValue.every((item) => validateStrict(EvidenceSchema, item))) {
    return fail("STM row contains invalid evidence");
  }
  const evidence = evidenceValue as Evidence[];
  const claimRefs = claimValue.evidence_refs;
  if (new Set(claimRefs).size !== claimRefs.length) return fail("STM claim evidence references must be unique");
  const evidenceIds = evidence.map((item) => item.evidence_id);
  if (new Set(evidenceIds).size !== evidenceIds.length) return fail("STM evidence ids must be unique");
  const orderedClaimRefs = [...claimRefs].sort(compareStrings);
  const orderedEvidenceIds = [...evidenceIds].sort(compareStrings);
  if (orderedClaimRefs.length !== orderedEvidenceIds.length
    || orderedClaimRefs.some((ref, index) => ref !== orderedEvidenceIds[index])) {
    return fail("STM evidence must exactly match the claim evidence references");
  }

  for (const item of evidence) {
    if (item.state !== "active") return fail("STM evidence is not active");
    const events = (durable.events ?? []).filter((candidate) =>
      candidate.revision_id === item.event_revision_id
      && candidate.event.event_revision_id === item.event_revision_id);
    if (events.length !== 1) return fail("STM evidence does not resolve to exactly one durable event revision");
    const event = events[0]!.event;
    if (!validateStrict(L1EventSchema, event)) return fail("STM evidence resolves to an invalid durable event");
    if (event.owner_account_id !== ownerAccountId) return fail("STM evidence resolves to a cross-owner durable event");
    if (event.evidence_addressable_refs.filter((ref) => ref === item.evidence_id).length !== 1) {
      return fail("STM evidence is not uniquely addressable from its durable event");
    }
  }

  const eventTimeWatermark = requireString(row.event_time_watermark, "event_time_watermark");
  if (eventTimeWatermark !== claimValue.temporal_scope.observed_at) {
    return fail("STM event-time watermark does not match the claim observation time");
  }
  return {
    id,
    session_id: requireString(row.session_id, "session_id"),
    event_time_watermark: eventTimeWatermark,
    capture_sequence: requireNonnegativeInteger(row.capture_sequence, "capture_sequence"),
    revision_lineage: requireString(row.revision_lineage, "revision_lineage"),
    ingest_sequence: requireNonnegativeInteger(row.ingest_sequence, "ingest_sequence"),
    entity_refs: parseUniqueStringArray(parseJson(row.entity_refs_json, "entity_refs_json"), "entity_refs_json"),
    lexical_terms: parseUniqueStringArray(parseJson(row.lexical_terms_json, "lexical_terms_json"), "lexical_terms_json"),
    vector_key: requireString(row.vector_key, "vector_key"),
    predicate_id: requireString(row.predicate_id, "predicate_id"),
    bytes: requireNonnegativeInteger(row.bytes, "bytes"),
    claim: claimValue,
    evidence: Object.freeze([...evidence]),
    argument_origins: parseArgumentOrigins(parseJson(row.argument_origins_json, "argument_origins_json")),
    settled_window_id: requireString(row.settled_window_id, "settled_window_id"),
  };
};

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export interface SqliteQaRecallLimits {
  readonly max_items: number;
  readonly max_bytes: number;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export interface AcceptedRecentState<Candidate> {
  readonly state: AcceptedCoverageState;
  readonly declared_frontier: string | null;
  readonly searched_frontier: string | null;
  readonly candidates: readonly Candidate[];
}

/**
 * An ingestion-owned test port supplies accepted material and its coverage.
 * This adapter deliberately defines no acceptance predicate and owns no table.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
export type AcceptedRecentStatePort<Candidate> = (
  db: Database,
  ownerAccountId: string,
  limits: SqliteQaRecallLimits,
) => unknown;

// domain-pending(DIV-DOMCORE-006)
export interface SqliteQaStmStoragePosition {
  readonly event_time_watermark: string;
  readonly capture_sequence: number;
  readonly revision_lineage: string;
  readonly ingest_sequence: number;
  readonly id: string;
}

// domain-pending(DIV-DOMCORE-006)
export type SqliteQaStmBound = "item_limit" | "byte_limit";

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export interface SqliteQaRecallLoad<Candidate> {
  readonly owner_account_id: string;
  readonly account_timezone: string;
  readonly durable_snapshot: GraphSnapshot;
  readonly stm_rows: readonly DurableStmItem[];
  readonly accepted_state: AcceptedRecentState<Candidate>;
  readonly internal_coverage: {
    readonly applied_limits: SqliteQaRecallLimits;
    readonly durable: {
      readonly graph_generation: string | number;
      readonly ledger_head: { readonly commit_id: string; readonly sequence: number } | null;
      readonly ledger_head_digest: string;
    };
    readonly stm: {
      readonly selected_items: number;
      readonly selected_bytes: number;
      readonly last_selected_position: SqliteQaStmStoragePosition | null;
      readonly next_unselected_position: SqliteQaStmStoragePosition | null;
      readonly has_more: boolean;
      readonly bounds_reached: readonly SqliteQaStmBound[];
    };
    readonly accepted: {
      readonly state: AcceptedCoverageState;
      readonly declared_frontier: string | null;
      readonly searched_frontier: string | null;
      readonly selected_items: number;
      readonly selected_bytes: number;
    };
  };
  /** Identity of the exact detached, coherent source load; never a wire cursor. */
  readonly coherent_snapshot_digest: string;
}

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export interface SqliteQaRecallLoaderOptions<Candidate> {
  readonly db: Database;
  readonly ledger: SqliteLedger;
  readonly owner_account_id: string;
  readonly account_timezone: string;
  readonly limits: SqliteQaRecallLimits;
  readonly accepted_recent_state_port?: AcceptedRecentStatePort<Candidate>;
}

const positionOf = (item: DurableStmItem | undefined): SqliteQaStmStoragePosition | null => item ? Object.freeze({
  event_time_watermark: item.event_time_watermark,
  capture_sequence: item.capture_sequence,
  revision_lineage: item.revision_lineage,
  ingest_sequence: item.ingest_sequence,
  id: item.id,
}) : null;

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
const decodeAcceptedState = <Candidate>(input: unknown, limits: SqliteQaRecallLimits): {
  readonly value: AcceptedRecentState<Candidate>;
  readonly bytes: number;
} => {
  const value = detachPlainJson(input);
  if (!hasExactKeys(value, ["state", "declared_frontier", "searched_frontier", "candidates"])
    || typeof value["state"] !== "string" || !ACCEPTED_STATES.has(value["state"] as AcceptedCoverageState)
    || (value["declared_frontier"] !== null && (typeof value["declared_frontier"] !== "string" || !INTERNAL_REF.test(value["declared_frontier"])))
    || (value["searched_frontier"] !== null && (typeof value["searched_frontier"] !== "string" || !INTERNAL_REF.test(value["searched_frontier"])))
    || !Array.isArray(value["candidates"])) {
    return fail("accepted state has an invalid shape");
  }
  const state = value["state"] as AcceptedCoverageState;
  const declared = value["declared_frontier"] as string | null;
  const searched = value["searched_frontier"] as string | null;
  const candidates = value["candidates"] as readonly PlainJson[];

  if (state === "searched" && (declared === null || searched === null || declared !== searched)) {
    return fail("searched accepted state requires one fully searched declared frontier");
  }
  if (state === "no_eligible" && (searched !== null || candidates.length !== 0)) {
    return fail("no_eligible accepted state cannot carry a searched frontier or candidates");
  }
  if (state === "pending" && (declared === null || declared === searched)) {
    return fail("pending accepted state requires an unsearched declared frontier");
  }
  if (searched !== null && declared === null) return fail("accepted searched frontier requires a declared frontier");
  if (candidates.length > 0 && searched === null) return fail("accepted candidates require a searched frontier");
  if (candidates.length > limits.max_items) return fail("accepted candidates exceed the item limit");

  let bytes = 0;
  for (const candidate of candidates) {
    const size = canonicalBytes(candidate);
    if (size > limits.max_bytes - bytes) return fail("accepted candidates exceed the byte limit");
    bytes += size;
  }
  return Object.freeze({
    value: Object.freeze({
      state,
      declared_frontier: declared,
      searched_frontier: searched,
      candidates: Object.freeze([...(candidates as unknown as Candidate[])]),
    }),
    bytes,
  });
};

const totalChanges = (db: Database): number => {
  const row = db.query("SELECT total_changes() AS count").get() as { count: number };
  return row.count;
};

const asPlainJson = (value: unknown): PlainJson => detachPlainJson(value);

/**
 * Hermetic SQLite composition for QA only. It selects no production store,
 * acceptance semantics, concurrency model, or public frontier representation.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
export const createSqliteQaRecallLoader = <Candidate>(options: SqliteQaRecallLoaderOptions<Candidate>): (() => SqliteQaRecallLoad<Candidate>) => {
  const ownerAccountId = requireString(options.owner_account_id, "owner_account_id");
  const accountTimezone = requireTimezone(options.account_timezone);
  const limits = Object.freeze({
    max_items: requireSafeBound(options.limits.max_items, "max_items"),
    max_bytes: requireSafeBound(options.limits.max_bytes, "max_bytes"),
  });
  const { db, ledger, accepted_recent_state_port: acceptedPort } = options;
  const sqlLimit = limits.max_items + 1;

  return () => {
    const read = db.transaction((): SqliteQaRecallLoad<Candidate> => {
      if (!db.inTransaction) return fail("coherent source reads require one active transaction");
      const changesBefore = totalChanges(db);

      const ledgerHead = ledger.graphHead(ownerAccountId);
      const durable = asPlainJson(ledger.snapshot(ownerAccountId)) as unknown as GraphSnapshot;
      if (durable.owner_account_id !== ownerAccountId) return fail("durable snapshot owner mismatch");
      const graphGeneration = durable.graph_generation ?? 0;
      if ((typeof graphGeneration !== "string" || graphGeneration.length === 0)
        && (typeof graphGeneration !== "number" || !Number.isSafeInteger(graphGeneration) || graphGeneration < 0)) {
        return fail("durable snapshot graph generation is invalid");
      }
      if (graphGeneration !== (ledgerHead?.sequence ?? 0)) {
        return fail("durable snapshot generation does not match its ledger head");
      }

      // Owner and decided-row exclusion occur before LIMIT. A foreign or
      // ledger-decided-but-undrained row cannot move the selected prefix or its
      // internal storage position.
      // domain-pending(DIV-DOMCORE-006)
      // domain-pending(DIV-DOMCORE-008)
      const malformedOwnerlessRow = db.query(`
        SELECT 1 AS present
        FROM stm_items
        WHERE consumed = 0 AND json_valid(claim_json) = 0
        LIMIT 1
      `).get();
      // The disposable table has no separate owner column. Invalid claim JSON
      // therefore cannot be attributed safely; reject database integrity rather
      // than silently treating the row as foreign or letting it move a prefix.
      if (malformedOwnerlessRow) return fail("STM contains malformed ownerless claim JSON");

      const rawRows = db.query(`
        SELECT id, session_id, event_time_watermark, capture_sequence, revision_lineage,
          ingest_sequence, entity_refs_json, lexical_terms_json, vector_key, predicate_id,
          bytes, claim_json, evidence_json, argument_origins_json, settled_window_id
        FROM stm_items AS s
        WHERE s.consumed = 0
          AND CASE WHEN json_valid(s.claim_json)
            THEN json_extract(s.claim_json, '$.owner_account_id') ELSE NULL END = ?
          AND NOT EXISTS (
            SELECT 1
            FROM consumed_markers AS marker
            JOIN derivation_commits AS derivation ON derivation.commit_id = marker.commit_id
            WHERE marker.provisional_revision_id = s.id
              AND derivation.owner_account_id = ?
          )
        ORDER BY event_time_watermark, capture_sequence, revision_lineage, ingest_sequence, id
        LIMIT ?
      `).all(ownerAccountId, ownerAccountId, sqlLimit) as StmSqlRow[];

      const decoded = rawRows.map((row) => decodeStmRow(row, ownerAccountId, durable)).sort(compareStmOrder);
      const selected: DurableStmItem[] = [];
      let selectedBytes = 0;
      let next: DurableStmItem | undefined;
      for (const item of decoded) {
        if (selected.length >= limits.max_items || item.bytes > limits.max_bytes - selectedBytes) {
          next = item;
          break;
        }
        selected.push(item);
        selectedBytes += item.bytes;
      }
      const bounds: SqliteQaStmBound[] = [];
      if (next && selected.length >= limits.max_items) bounds.push("item_limit");
      if (next && next.bytes > limits.max_bytes - selectedBytes) bounds.push("byte_limit");

      const defaultAccepted = {
        state: "unavailable",
        declared_frontier: null,
        searched_frontier: null,
        candidates: [],
      } as const;
      // The port runs under this exact transaction. It is an injected read of
      // already-accepted state; no durable/Event/evidence/derivation field is
      // inspected to infer acceptance.
      // domain-pending(DIV-DOMCORE-001)
      // domain-pending(DIV-DOMCORE-008)
      const accepted = decodeAcceptedState<Candidate>(
        acceptedPort ? acceptedPort(db, ownerAccountId, limits) : defaultAccepted,
        limits,
      );

      const ledgerHeadValue = ledgerHead === null ? null : Object.freeze({
        commit_id: requireString(ledgerHead.commit_id, "ledger head commit_id"),
        sequence: requireNonnegativeInteger(ledgerHead.sequence, "ledger head sequence"),
      });
      const ledgerHeadDigest = canonicalDigest(asPlainJson({
        owner_account_id: ownerAccountId,
        ledger_head: ledgerHeadValue,
      }));
      const internalCoverage = {
        applied_limits: { ...limits },
        durable: {
          graph_generation: graphGeneration,
          ledger_head: ledgerHeadValue,
          ledger_head_digest: ledgerHeadDigest,
        },
        stm: {
          selected_items: selected.length,
          selected_bytes: selectedBytes,
          last_selected_position: positionOf(selected.at(-1)),
          next_unselected_position: positionOf(next),
          has_more: next !== undefined,
          bounds_reached: [...bounds],
        },
        accepted: {
          state: accepted.value.state,
          declared_frontier: accepted.value.declared_frontier,
          searched_frontier: accepted.value.searched_frontier,
          selected_items: accepted.value.candidates.length,
          selected_bytes: accepted.bytes,
        },
      } as const;
      const digestInput = asPlainJson({
        owner_account_id: ownerAccountId,
        account_timezone: accountTimezone,
        durable_snapshot: durable,
        stm_rows: selected,
        accepted_state: accepted.value,
        internal_coverage: internalCoverage,
      });
      const coherentSnapshotDigest = canonicalDigest(digestInput);

      if (totalChanges(db) !== changesBefore) return fail("a read port attempted to mutate SQLite");
      return deepFreeze({
        owner_account_id: ownerAccountId,
        account_timezone: accountTimezone,
        durable_snapshot: durable,
        stm_rows: selected,
        accepted_state: accepted.value,
        internal_coverage: internalCoverage,
        coherent_snapshot_digest: coherentSnapshotDigest,
      });
    });
    return read.deferred();
  };
};
