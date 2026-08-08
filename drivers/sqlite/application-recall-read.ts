// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
import { createHash } from "node:crypto";
import { isProxy } from "node:util/types";
import { Database } from "bun:sqlite";

import { compareStrings } from "../../core/order";
import type { GraphSnapshot } from "../../core/retrieve";
import type { AcceptedCoverageState } from "../../core/retrieve/recall-integrity";
import { validateCanonicalClaim, validateProvisionalClaim } from "../../core/schema/claim-validation";
import {
  EntitySchema,
  EvidenceSchema,
  IdentityAuthorizationSchema,
  IdentityConstraintSchema,
  L1EventSchema,
  MentionSchema,
  PredicateAssertionSchema,
  PredicateSchema,
  type Evidence,
} from "../../core/schema";
import { validateStrict } from "../../core/schema/json";
import { compareStmOrder } from "../../core/stm";
import type { DurableStmItem } from "./stm";
import { SqliteLedger } from "./index";

type PlainJson = null | boolean | number | string
  | readonly PlainJson[]
  | { readonly [key: string]: PlainJson };

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
/** Full-set sort is deliberately finite even though output limits are separate. */
export const SQLITE_QA_STM_SCAN_CEILING = 1_024;

const fail = (message: string): never => { throw new TypeError(`SQLite QA recall read: ${message}`); };

const compareCodeUnits = (left: string, right: string): number => left < right ? -1 : left > right ? 1 : 0;

/**
 * Detach every persisted/fixture JSON boundary before inspecting semantic
 * fields. A value may be reached only once: shared-reference aliases are
 * rejected rather than copied, because an alias can otherwise smuggle identity
 * and TOCTOU assumptions into later application code.
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
  // Keep every accumulated byte count and downstream bound arithmetic exactly
  // representable even at adversarial configuration values.
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

const requireJsonArray = (value: PlainJson, name: string): readonly PlainJson[] => {
  if (!Array.isArray(value)) return fail(`durable snapshot ${name} must be an array`);
  return value;
};

const requireExactRecord = (
  value: PlainJson,
  keys: readonly string[],
  name: string,
): { readonly [key: string]: PlainJson } => {
  if (!hasExactKeys(value, keys)) return fail(`durable snapshot ${name} has an invalid shape`);
  return value;
};

const requireOwned = (value: PlainJson, ownerAccountId: string, name: string): void => {
  if (!isRecord(value) || value["owner_account_id"] !== ownerAccountId) {
    fail(`durable snapshot ${name} owner mismatch`);
  }
};

const requireRevision = (value: PlainJson, name: string): string =>
  requireString(value, `durable snapshot ${name} revision_id`);

/**
 * `SqliteLedger.snapshot` parses persisted JSON. Its TypeScript return type is
 * therefore not a runtime trust boundary. Validate the complete QA projection
 * before any row lineage or digest uses it.
 */
const validateDurableSnapshot = (value: PlainJson, ownerAccountId: string): GraphSnapshot => {
  const snapshot = requireExactRecord(value, [
    "owner_account_id", "graph_generation", "claims", "entities", "predicates",
    "predicate_assertions", "identity_constraints", "mentions", "identity_authorizations",
    "identity_support", "events", "evidence", "liveness_causes", "adjacency",
    "source_local_roles", "placement_artifacts",
  ], "root");
  if (snapshot["owner_account_id"] !== ownerAccountId) return fail("durable snapshot owner mismatch");

  for (const item of requireJsonArray(snapshot["claims"]!, "claims")) {
    const row = requireExactRecord(item, ["revision_id", "claim", "placement_status", "commit_sequence"], "claim revision");
    const revisionId = requireRevision(row["revision_id"]!, "claim");
    const claim = row["claim"];
    if (!validateProvisionalClaim(claim) && !validateCanonicalClaim(claim)) return fail("durable snapshot contains an invalid claim");
    requireOwned(claim as unknown as PlainJson, ownerAccountId, "claim");
    if (claim.claim_revision_id !== revisionId) return fail("durable claim wrapper/revision mismatch");
    if (!["canonical", "consumed", "provisional_unresolved_subject", "provisional_abstained"].includes(String(row["placement_status"]))) {
      return fail("durable snapshot claim placement status is invalid");
    }
    requireNonnegativeInteger(row["commit_sequence"], "durable claim commit_sequence");
  }

  for (const item of requireJsonArray(snapshot["entities"]!, "entities")) {
    const row = requireExactRecord(item, ["revision_id", "entity"], "entity revision");
    const revisionId = requireRevision(row["revision_id"]!, "entity");
    if (!validateStrict(EntitySchema, row["entity"])) return fail("durable snapshot contains an invalid entity");
    requireOwned(row["entity"]!, ownerAccountId, "entity");
    if ((row["entity"] as { entity_revision_id: string }).entity_revision_id !== revisionId) return fail("durable entity wrapper/revision mismatch");
  }

  const schemaCollections = [
    ["predicates", "predicate", PredicateSchema],
    ["predicate_assertions", "assertion", PredicateAssertionSchema],
    ["identity_constraints", "constraint", IdentityConstraintSchema],
    ["mentions", "mention", MentionSchema],
    ["identity_authorizations", "authorization", IdentityAuthorizationSchema],
  ] as const;
  for (const [collectionName, payloadName, schema] of schemaCollections) {
    for (const item of requireJsonArray(snapshot[collectionName]!, collectionName)) {
      const row = requireExactRecord(item, ["revision_id", payloadName], `${payloadName} revision`);
      requireRevision(row["revision_id"]!, payloadName);
      if (!validateStrict(schema, row[payloadName])) return fail(`durable snapshot contains an invalid ${payloadName}`);
      requireOwned(row[payloadName]!, ownerAccountId, payloadName);
    }
  }

  const eventRevisionIds = new Set<string>();
  for (const item of requireJsonArray(snapshot["events"]!, "events")) {
    const row = requireExactRecord(item, ["revision_id", "event"], "event revision");
    const revisionId = requireRevision(row["revision_id"]!, "event");
    if (!validateStrict(L1EventSchema, row["event"])) return fail("durable snapshot contains an invalid event");
    requireOwned(row["event"]!, ownerAccountId, "event");
    if ((row["event"] as { event_revision_id: string }).event_revision_id !== revisionId) return fail("durable event wrapper/revision mismatch");
    if (eventRevisionIds.has(revisionId)) return fail("durable snapshot contains duplicate event revisions");
    eventRevisionIds.add(revisionId);
  }

  for (const item of requireJsonArray(snapshot["evidence"]!, "evidence")) {
    const row = requireExactRecord(item, ["revision_id", "evidence", "commit_sequence"], "evidence revision");
    requireRevision(row["revision_id"]!, "evidence");
    if (!validateStrict(EvidenceSchema, row["evidence"])) return fail("durable snapshot contains invalid evidence");
    const durableEvidence = row["evidence"] as unknown as Evidence;
    if (!eventRevisionIds.has(durableEvidence.event_revision_id)) return fail("durable evidence has no owner-scoped event revision");
    requireNonnegativeInteger(row["commit_sequence"], "durable evidence commit_sequence");
  }

  for (const item of requireJsonArray(snapshot["identity_support"]!, "identity_support")) {
    const allowed = hasExactKeys(item, ["support_ref", "owner_account_id", "evidence_ref", "claim_revision_id", "source_independence_key"])
      || hasExactKeys(item, ["support_ref", "owner_account_id", "evidence_ref", "claim_revision_id", "source_independence_key", "support_origin"]);
    if (!allowed || !isRecord(item)) return fail("durable snapshot identity support has an invalid shape");
    requireOwned(item, ownerAccountId, "identity support");
    for (const key of ["support_ref", "evidence_ref", "claim_revision_id", "source_independence_key"]) {
      requireString(item[key], `durable identity support ${key}`);
    }
    if ("support_origin" in item && item["support_origin"] !== "suggested" && item["support_origin"] !== "independent") {
      return fail("durable identity support origin is invalid");
    }
  }

  const liveness = requireExactRecord(snapshot["liveness_causes"]!, ["purged_claim_revision_ids", "forgotten_claim_revision_ids"], "liveness causes");
  parseUniqueStringArray(liveness["purged_claim_revision_ids"], "durable purged claim ids");
  parseUniqueStringArray(liveness["forgotten_claim_revision_ids"], "durable forgotten claim ids");

  for (const item of requireJsonArray(snapshot["adjacency"]!, "adjacency")) {
    const row = requireExactRecord(item, ["claim_revision_id", "entity_id", "role_slot_id"], "adjacency");
    for (const key of ["claim_revision_id", "entity_id", "role_slot_id"]) requireString(row[key], `durable adjacency ${key}`);
  }
  for (const item of requireJsonArray(snapshot["source_local_roles"]!, "source_local_roles")) {
    const row = requireExactRecord(item, ["claim_revision_id", "source_local_ref", "role_slot_id"], "source-local role");
    for (const key of ["claim_revision_id", "source_local_ref", "role_slot_id"]) requireString(row[key], `durable source-local role ${key}`);
  }
  for (const item of requireJsonArray(snapshot["placement_artifacts"]!, "placement_artifacts")) {
    const row = requireExactRecord(item, ["artifact_id", "kind", "provisional_revision_id", "canonical_claim_revision_id", "margin", "risk_markers", "unit_boundary_decision", "scope_locality"], "placement artifact");
    requireString(row["artifact_id"], "durable placement artifact_id");
    requireString(row["provisional_revision_id"], "durable placement provisional_revision_id");
    if (!["confirmation_queue", "abstention_set", "auto_placement_log"].includes(String(row["kind"]))) return fail("durable placement kind is invalid");
    if (row["canonical_claim_revision_id"] !== null) requireString(row["canonical_claim_revision_id"], "durable placement canonical revision");
    if (row["margin"] !== null && !["low", "medium", "high"].includes(String(row["margin"]))) return fail("durable placement margin is invalid");
    const risks = requireJsonArray(row["risk_markers"]!, "placement risk markers");
    if (risks.some((risk) => typeof risk !== "string" || !["new_entity", "resolved_pronoun", "low_margin"].includes(risk))) return fail("durable placement risk marker is invalid");
    if (row["unit_boundary_decision"] !== "accept_ltm" && row["unit_boundary_decision"] !== "abstain") return fail("durable placement decision is invalid");
    if (row["scope_locality"] !== null && row["scope_locality"] !== "durable" && row["scope_locality"] !== "source_local") return fail("durable placement locality is invalid");
  }

  return value as unknown as GraphSnapshot;
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
  readonly claim_json: unknown;
  readonly evidence_json: unknown;
  readonly argument_origins_json: unknown;
  readonly settled_window_id: unknown;
}

const stampCanonicalStmBytes = (input: Omit<DurableStmItem, "bytes">): DurableStmItem => {
  let bytes = 0;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const detached = detachPlainJson({ ...input, bytes });
    const computed = canonicalBytes(detached);
    if (computed === bytes) return detached as unknown as DurableStmItem;
    bytes = computed;
  }
  return fail("STM canonical byte count did not converge");
};

// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
const decodeStmRow = (row: StmSqlRow, ownerAccountId: string, durable: GraphSnapshot): DurableStmItem => {
  const id = requireString(row.id, "STM row id");
  const sessionId = requireString(row.session_id, "session_id");
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
    const detachedItem = detachPlainJson(item);
    const durableEvidence = (durable.evidence ?? []).filter((candidate) =>
      canonicalJson(detachPlainJson(candidate.evidence)) === canonicalJson(detachedItem));
    if (durableEvidence.length !== 1) return fail("STM evidence does not equal exactly one durable evidence revision");
    const events = (durable.events ?? []).filter((candidate) =>
      candidate.revision_id === item.event_revision_id
      && candidate.event.event_revision_id === item.event_revision_id);
    if (events.length !== 1) return fail("STM evidence does not resolve to exactly one durable event revision");
    const event = events[0]!.event;
    if (!validateStrict(L1EventSchema, event)) return fail("STM evidence resolves to an invalid durable event");
    if (event.owner_account_id !== ownerAccountId) return fail("STM evidence resolves to a cross-owner durable event");
    if (event.capture_session_id !== sessionId) return fail("STM row session does not match its durable event capture session");
    if (event.evidence_addressable_refs.filter((ref) => ref === item.evidence_id).length !== 1) {
      return fail("STM evidence is not uniquely addressable from its durable event");
    }
  }

  const eventTimeWatermark = requireString(row.event_time_watermark, "event_time_watermark");
  if (eventTimeWatermark !== claimValue.temporal_scope.observed_at) {
    return fail("STM event-time watermark does not match the claim observation time");
  }
  return stampCanonicalStmBytes({
    id,
    session_id: sessionId,
    event_time_watermark: eventTimeWatermark,
    capture_sequence: requireNonnegativeInteger(row.capture_sequence, "capture_sequence"),
    revision_lineage: requireString(row.revision_lineage, "revision_lineage"),
    ingest_sequence: requireNonnegativeInteger(row.ingest_sequence, "ingest_sequence"),
    entity_refs: parseUniqueStringArray(parseJson(row.entity_refs_json, "entity_refs_json"), "entity_refs_json"),
    lexical_terms: parseUniqueStringArray(parseJson(row.lexical_terms_json, "lexical_terms_json"), "lexical_terms_json"),
    vector_key: requireString(row.vector_key, "vector_key"),
    predicate_id: requireString(row.predicate_id, "predicate_id"),
    claim: claimValue,
    evidence: Object.freeze([...evidence]),
    argument_origins: parseArgumentOrigins(parseJson(row.argument_origins_json, "argument_origins_json")),
    settled_window_id: requireString(row.settled_window_id, "settled_window_id"),
  });
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
      readonly eligible_items: number;
      readonly scan_ceiling: number;
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
  readonly owner_account_id: string;
  readonly account_timezone: string;
  readonly limits: SqliteQaRecallLimits;
  /**
   * Hermetic QA data only. It is detached and frozen at factory construction;
   * no callback, accepted-state storage, or acceptance semantics are selected.
   */
  readonly accepted_fixture_state?: AcceptedRecentState<Candidate>;
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

const snapshotDataProperties = (
  input: unknown,
  required: readonly string[],
  optional: readonly string[],
  name: string,
): Readonly<Record<string, unknown>> => {
  if (typeof input !== "object" || input === null || Array.isArray(input) || isProxy(input)) {
    return fail(`${name} must be a non-proxy plain object`);
  }
  const prototype = Object.getPrototypeOf(input);
  if (prototype !== Object.prototype && prototype !== null) return fail(`${name} must be a plain object`);
  const descriptors = Object.getOwnPropertyDescriptors(input);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key === "symbol")) return fail(`${name} rejects symbol keys`);
  const actual = (keys as string[]).sort(compareCodeUnits);
  const allowed = [...required, ...optional].sort(compareCodeUnits);
  if (required.some((key) => !actual.includes(key)) || actual.some((key) => !allowed.includes(key))) {
    return fail(`${name} has an invalid shape`);
  }
  const output: Record<string, unknown> = Object.create(null);
  for (const key of actual) {
    const descriptor = descriptors[key];
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) {
      return fail(`${name} rejects accessors and hidden fields`);
    }
    output[key] = descriptor.value;
  }
  return Object.freeze(output);
};

const NATIVE_DATABASE_PREPARE = Database.prototype.prepare;
const NATIVE_DATABASE_EXEC = Database.prototype.exec;
const NATIVE_DATABASE_TRANSACTION = Database.prototype.transaction;
const NATIVE_DATABASE_IN_TRANSACTION = Object.getOwnPropertyDescriptor(
  Database.prototype,
  "inTransaction",
)?.get;

/**
 * Bind the exact Bun SQLite receiver to native prototype operations once. The
 * original caller-owned object is never dynamically dispatched through after
 * this point, including by the internally constructed `SqliteLedger`.
 */
const captureNativeDatabase = (input: unknown): Database => {
  if (typeof input !== "object" || input === null || isProxy(input)
    || Object.getPrototypeOf(input) !== Database.prototype) {
    return fail("db must have the exact native SQLite Database prototype");
  }
  for (const name of ["query", "prepare", "exec", "transaction", "close", "inTransaction"] as const) {
    if (Object.prototype.hasOwnProperty.call(input, name)) return fail(`db rejects own ${name} shadows`);
  }
  if (typeof NATIVE_DATABASE_PREPARE !== "function" || typeof NATIVE_DATABASE_EXEC !== "function"
    || typeof NATIVE_DATABASE_TRANSACTION !== "function" || typeof NATIVE_DATABASE_IN_TRANSACTION !== "function") {
    return fail("native SQLite Database operations are unavailable");
  }

  const database = input as Database;
  try {
    Reflect.apply(NATIVE_DATABASE_IN_TRANSACTION, database, []);
  } catch {
    return fail("db is not a live native SQLite Database");
  }

  const facade = Object.create(null) as Record<PropertyKey, unknown>;
  Object.defineProperties(facade, {
    query: {
      // `Database.query` returns a shared mutable statement cached by SQL text.
      // `prepare` returns a fresh statement, kept private behind this facade,
      // so caller-held cached statements and their writable get/all/run methods
      // can never alias a ledger or coherent-loader statement.
      value: ((sql: string) => Reflect.apply(NATIVE_DATABASE_PREPARE, database, [sql])) as Database["query"],
      enumerable: true,
    },
    exec: {
      value: ((sql: string) => Reflect.apply(NATIVE_DATABASE_EXEC, database, [sql])) as Database["exec"],
      enumerable: true,
    },
    transaction: {
      value: ((callback: () => unknown) => Reflect.apply(NATIVE_DATABASE_TRANSACTION, database, [callback])) as Database["transaction"],
      enumerable: true,
    },
    inTransaction: {
      get: () => Reflect.apply(NATIVE_DATABASE_IN_TRANSACTION, database, []),
      enumerable: true,
    },
  });
  return Object.freeze(facade) as unknown as Database;
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
  const configured = snapshotDataProperties(
    options,
    ["db", "owner_account_id", "account_timezone", "limits"],
    ["accepted_fixture_state"],
    "loader options",
  );
  const nativeDb = captureNativeDatabase(configured["db"]);
  const ownerAccountId = requireString(configured["owner_account_id"], "owner_account_id");
  const accountTimezone = requireTimezone(requireString(configured["account_timezone"], "account_timezone"));
  const configuredLimits = snapshotDataProperties(configured["limits"], ["max_items", "max_bytes"], [], "limits");
  const limits = Object.freeze({
    max_items: requireSafeBound(configuredLimits["max_items"] as number, "max_items"),
    max_bytes: requireSafeBound(configuredLimits["max_bytes"] as number, "max_bytes"),
  });
  const defaultAccepted = {
    state: "unavailable",
    declared_frontier: null,
    searched_frontier: null,
    candidates: [],
  } as const;
  // A QA fixture is inert data, snapshotted once. Loader calls can never invoke
  // caller code or query a caller-selected accepted-state store.
  const acceptedFixture = configured["accepted_fixture_state"];
  const accepted = decodeAcceptedState<Candidate>(
    acceptedFixture === undefined ? defaultAccepted : acceptedFixture,
    limits,
  );

  // QA-only composition owns schema preparation. Constructing the ledger here
  // (after all configuration checks, before any coherent load) is the binding:
  // its private facade uses native methods bound to the exact Database captured
  // above, so callers cannot pair ledger reads from one database with STM reads
  // from another. `SqliteLedger` migration/PRAGMA side effects happen only at
  // factory time.
  const ledger = new SqliteLedger(nativeDb);

  return () => {
    if (nativeDb.inTransaction) return fail("coherent load cannot start inside another transaction");
    const read = nativeDb.transaction((): SqliteQaRecallLoad<Candidate> => {
      if (!nativeDb.inTransaction) return fail("coherent source reads require one active transaction");
      const changesBefore = totalChanges(nativeDb);

      const ledgerHead = ledger.graphHead(ownerAccountId);
      const durable = validateDurableSnapshot(asPlainJson(ledger.snapshot(ownerAccountId)), ownerAccountId);
      const graphGeneration = durable.graph_generation ?? 0;
      if ((typeof graphGeneration !== "string" || graphGeneration.length === 0)
        && (typeof graphGeneration !== "number" || !Number.isSafeInteger(graphGeneration) || graphGeneration < 0)) {
        return fail("durable snapshot graph generation is invalid");
      }
      if (graphGeneration !== (ledgerHead?.sequence ?? 0)) {
        return fail("durable snapshot generation does not match its ledger head");
      }

      // Owner and decided-row exclusion occur before the finite scan count.
      // Foreign, consumed, and ledger-decided-but-undrained rows cannot move
      // the selected prefix or exhaust its scan budget.
      // domain-pending(DIV-DOMCORE-006)
      // domain-pending(DIV-DOMCORE-008)
      const malformedOwnerlessRow = nativeDb.query(`
        SELECT 1 AS present
        FROM stm_items
        WHERE consumed = 0 AND json_valid(claim_json) = 0
        LIMIT 1
      `).get();
      // The disposable table has no separate owner column. Invalid claim JSON
      // therefore cannot be attributed safely; reject database integrity rather
      // than silently treating the row as foreign or letting it move a prefix.
      if (malformedOwnerlessRow) return fail("STM contains malformed ownerless claim JSON");

      const eligibleCountRow = nativeDb.query(`
        SELECT COUNT(*) AS count
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
      `).get(ownerAccountId, ownerAccountId) as { count?: unknown } | null;
      const eligibleCount = requireNonnegativeInteger(eligibleCountRow?.count, "eligible STM row count");
      if (eligibleCount > SQLITE_QA_STM_SCAN_CEILING) return fail("eligible STM rows exceed the QA scan ceiling");

      // SQL performs only owner and ledger-decision eligibility. No SQLite
      // collation or pre-limit prefix is trusted: the complete eligible owner
      // set is detached, validated, and sorted by the core comparator first.
      const rawRows = nativeDb.query(`
        SELECT id, session_id, event_time_watermark, capture_sequence, revision_lineage,
          ingest_sequence, entity_refs_json, lexical_terms_json, vector_key, predicate_id,
          claim_json, evidence_json, argument_origins_json, settled_window_id
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
      `).all(ownerAccountId, ownerAccountId) as StmSqlRow[];
      if (rawRows.length !== eligibleCount) return fail("eligible STM count changed inside the coherent transaction");

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
          eligible_items: eligibleCount,
          scan_ceiling: SQLITE_QA_STM_SCAN_CEILING,
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

      if (!nativeDb.inTransaction) return fail("coherent transaction ended before load completion");
      if (totalChanges(nativeDb) !== changesBefore) return fail("coherent QA load attempted to mutate SQLite");
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
