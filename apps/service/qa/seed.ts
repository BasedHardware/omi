// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
import { Database } from "bun:sqlite";

import type {
  CanonicalClaim,
  Entity,
  Evidence,
  L1Event,
  Predicate,
  SourceIdentityRef,
} from "../../../core/schema";
import { SqliteLedger } from "../../../drivers/sqlite";
import { SqliteStmStore } from "../../../drivers/sqlite/stm";

/**
 * Fixed UTC instant for every seeded memory's base event/observation time.
 *
 * A fixed UTC seed alone is not enough: the client groups memories into calendar
 * days in LOCAL time, so Today/Tomorrow/Later assertions drift with the test
 * runner's host zone unless `account_timezone` is pinned explicitly via options.
 */
export const QA_FIXTURE_TIME_ANCHOR_UTC = "2026-08-07T12:00:00.000Z";

const ANCHOR_MS = Date.parse(QA_FIXTURE_TIME_ANCHOR_UTC);

const GENERIC_POLICY_LABELS = Object.freeze([
  "subject:generic",
  "sensitivity:generic",
  "capture:generic",
] as const);

/** Tables the seeder writes (or that must be empty for a true restore). */
const QA_SEED_TABLES = Object.freeze([
  "claim_quarantine_records",
  "identity_quarantine_records",
  "identity_revisions",
  "claim_revisions",
  "entity_revisions",
  "predicate_revisions",
  "predicate_assertion_revisions",
  "event_revisions",
  "evidence_revisions",
  "mention_revisions",
  "identity_authorization_revisions",
  "coreference_support_revisions",
  "identity_support_revisions",
  "candidate_derivation_artifacts",
  "generated_adjacency",
  "source_local_claim_roles",
  "consumed_markers",
  "placement_artifacts",
  "derivation_attempts",
  "derivation_commits",
  "graph_heads",
  "claim_liveness_fences",
  "stm_items",
  "stm_mentions",
] as const);

// domain-pending(DIV-DOMCORE-001)
export interface SeedQaSnapshotOptions {
  readonly owner_account_id: string;
  readonly memory_count: number;
  /** IANA timezone used for local-day grouping; validated like the QA recall loader. */
  readonly account_timezone: string;
}

const fail = (message: string): never => {
  throw new TypeError(`QA snapshot seed: ${message}`);
};

/** Same validation as `requireTimezone` in drivers/sqlite/application-recall-read.ts. */
const requireTimezone = (value: string): string => {
  if (typeof value !== "string" || value.length === 0) return fail("account_timezone must be non-empty");
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(0);
  } catch {
    return fail("account_timezone is invalid");
  }
  return value;
};

const requireOwner = (value: unknown): string => {
  if (typeof value !== "string" || value.length === 0) return fail("owner_account_id must be a non-empty string");
  return value;
};

const requireMemoryCount = (value: unknown): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    return fail("memory_count must be a non-negative safe integer");
  }
  return value;
};

const ensureSchema = (db: Database): void => {
  if (typeof db !== "object" || db === null || Object.getPrototypeOf(db) !== Database.prototype) {
    return fail("db must be a native bun:sqlite Database");
  }
  // Constructors own migrations; side effects are schema-only and deterministic.
  new SqliteLedger(db);
  new SqliteStmStore(db);
};

const padIndex = (index: number): string => String(index).padStart(6, "0");

/**
 * Places each seeded memory on its OWN local day, stepping backwards from the
 * anchor.
 *
 * The step is a whole day, not an hour, for two reasons. First, the served
 * memory is a temporal LEAF node - the deepest temporal grouping, which is the
 * day - so an hourly spread collapses every seeded memory into a single served
 * item and a page of N memories can never be exercised. Second, the client
 * groups memories into days in LOCAL time, so day-per-memory is what actually
 * exercises that grouping. The anchor is 12:00 UTC precisely so that a whole-day
 * step lands on a distinct local calendar day across the common test zones
 * rather than straddling midnight.
 */
const DAY_MS = 86_400_000;
const fixtureInstant = (index: number): string =>
  new Date(ANCHOR_MS - index * DAY_MS).toISOString();

const identity = (index: number): SourceIdentityRef => ({
  namespace_instance_ref: `namespace:qa:${padIndex(index)}`,
  local_key: `local:qa:${padIndex(index)}`,
  producer: { producer_ref: "qa-seed-producer", contract_ref: "qa-seed-contract" },
  asserted_identity: { domain: null, scope_ref: null },
});

// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
const buildMemory = (
  ownerAccountId: string,
  accountTimezone: string,
  index: number,
): {
  readonly event: L1Event;
  readonly evidence: Evidence;
  readonly entity: Entity;
  readonly claim: CanonicalClaim;
  readonly commit_id: string;
  readonly sequence: number;
} => {
  const token = padIndex(index);
  const observedAt = fixtureInstant(index);
  const eventRevisionId = `event-revision:qa:${token}`;
  const evidenceId = `evidence:qa:${token}`;
  const entityId = `entity:qa:${token}`;
  const claimRevisionId = `claim:qa:${token}`;
  const provisionalRevisionId = `provisional:qa:${token}`;
  const commitId = `commit:qa:${token}`;
  const predicateId = "predicate:qa:memory";

  const event: L1Event = {
    event_id: `event:qa:${token}`,
    event_revision_id: eventRevisionId,
    owner_account_id: ownerAccountId,
    capture_session_id: `session:qa:${token}`,
    stream_id: "qa-seed-stream",
    event_kind: "text",
    payload_schema_ref: "qa-seed-text-v1",
    schema_version: "v1",
    payload: { fixture_index: index },
    event_time: observedAt,
    ingest_time: observedAt,
    source_sequence: index,
    evidence_addressable_refs: [evidenceId],
    source_trust: "qa-seed",
    policy_labels: [...GENERIC_POLICY_LABELS],
    canonical_redacted_hash: `hash:qa:event:${token}`,
  };

  const evidence: Evidence = {
    evidence_id: evidenceId,
    event_revision_id: eventRevisionId,
    source_unit_ref: `unit:qa:${token}`,
    range: { start: 0, end: 16 },
    excerpt: `qa memory ${token}`,
    source_identity_ref: identity(index),
    speaker_rendering: null,
    source_local_mention_ref: null,
    state: "active",
    source_trust: "qa-seed",
    policy_labels: [...GENERIC_POLICY_LABELS],
    source_independence_key: `source:qa:${token}`,
  };

  // domain-pending(DIV-DOMCORE-007)
  const entity: Entity = {
    entity_id: entityId,
    owner_account_id: ownerAccountId,
    entity_revision_id: `entity-revision:qa:${token}`,
    handle: `qa-entity-${token}`,
    labels: ["qa-seed"],
  };

  // domain-pending(DIV-DOMCORE-008)
  const claim: CanonicalClaim = {
    claim_lineage_id: `lineage:qa:${token}`,
    claim_revision_id: claimRevisionId,
    owner_account_id: ownerAccountId,
    predicate_id: predicateId,
    predicate: "qa_memory",
    arguments: [{
      slot_id: "subject",
      role: "subject",
      value: { kind: "entity_ref", ref: entityId },
    }],
    temporal_scope: {
      observed_at: observedAt,
      precision: "instant",
      valid_time: {
        typed_expression: {
          kind: "absolute",
          granularity: "instant",
          value: observedAt,
        },
        resolved_interval: {
          kind: "instant",
          start: observedAt,
          end: observedAt,
          timezone: accountTimezone,
          granularity: "instant",
        },
        derivation: {
          resolver_version: "qa-seed-v1",
          timezone: accountTimezone,
        },
      },
    },
    evidence_refs: [evidenceId],
    policy_labels: [...GENERIC_POLICY_LABELS],
    source_language: "en",
    scope: { locality: "durable", scope_ref: entityId },
    lifecycle: "canonical",
    canonical_claim_id: `canonical:qa:${token}`,
    source_provisional_revision_ids: [provisionalRevisionId],
  };

  return { event, evidence, entity, claim, commit_id: commitId, sequence: index + 1 };
};

const sharedPredicate = (ownerAccountId: string): Predicate => ({
  predicate_id: "predicate:qa:memory",
  owner_account_id: ownerAccountId,
  predicate_revision_id: "predicate-revision:qa:memory",
  identity_name: "qa_memory",
  display_name: "qa_memory",
  lifecycle: "canonical",
  slot_ids: ["subject"],
});

/**
 * Clears every table the seeder touches (including autoincrement markers) so a
 * subsequent seed is byte-identical to a fresh seed of the same options.
 */
export const resetQaSnapshot = (db: Database): void => {
  ensureSchema(db);
  db.exec("PRAGMA foreign_keys = OFF;");
  try {
    for (const table of QA_SEED_TABLES) {
      db.query(`DELETE FROM ${table}`).run();
    }
    const hasSequence = db.query(
      "SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'",
    ).get();
    if (hasSequence) db.query("DELETE FROM sqlite_sequence").run();
  } finally {
    db.exec("PRAGMA foreign_keys = ON;");
  }
};

/**
 * Populate `db` with a deterministic owner-scoped durable corpus for QA recall.
 * Same options always yield byte-identical row content (no wall clock, randomness,
 * network, env, or uuid generation).
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
export const seedQaSnapshot = (db: Database, options: SeedQaSnapshotOptions): void => {
  if (typeof options !== "object" || options === null || Array.isArray(options)) {
    return fail("options must be a plain object");
  }
  const ownerAccountId = requireOwner(options.owner_account_id);
  const memoryCount = requireMemoryCount(options.memory_count);
  const accountTimezone = requireTimezone(options.account_timezone);

  ensureSchema(db);
  resetQaSnapshot(db);

  if (memoryCount === 0) return;

  const predicate = sharedPredicate(ownerAccountId);
  let parentCommit: string | null = null;
  let headCommitId = "";
  let headSequence = 0;

  const write = db.transaction(() => {
    for (let index = 0; index < memoryCount; index += 1) {
      const memory = buildMemory(ownerAccountId, accountTimezone, index);
      const { event, evidence, entity, claim, commit_id: commitId, sequence } = memory;

      db.query(
        "INSERT INTO derivation_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      ).run(
        commitId,
        ownerAccountId,
        parentCommit,
        sequence,
        `idempotency:qa:${padIndex(index)}`,
        `input:qa:${padIndex(index)}`,
        `input-version:qa:${padIndex(index)}`,
        `output:qa:${padIndex(index)}`,
        "success",
        JSON.stringify({ commit_id: commitId, fixture_index: index }),
      );

      if (index === 0) {
        db.query("INSERT INTO predicate_revisions VALUES (?, ?, ?, ?, ?, ?)").run(
          predicate.predicate_revision_id,
          ownerAccountId,
          predicate.predicate_id,
          JSON.stringify(predicate),
          "hash:qa:predicate:memory",
          commitId,
        );
      }

      db.query("INSERT INTO event_revisions VALUES (?, ?, ?, ?, ?)").run(
        event.event_revision_id,
        ownerAccountId,
        JSON.stringify(event),
        `hash:qa:event:${padIndex(index)}`,
        commitId,
      );

      db.query("INSERT INTO evidence_revisions VALUES (?, ?, ?, ?, ?, ?)").run(
        `evidence-revision:qa:${padIndex(index)}`,
        ownerAccountId,
        event.event_revision_id,
        JSON.stringify(evidence),
        `hash:qa:evidence:${padIndex(index)}`,
        commitId,
      );

      // domain-pending(DIV-DOMCORE-007)
      db.query("INSERT INTO entity_revisions VALUES (?, ?, ?, ?, ?)").run(
        entity.entity_revision_id,
        ownerAccountId,
        JSON.stringify(entity),
        `hash:qa:entity:${padIndex(index)}`,
        commitId,
      );

      // domain-pending(DIV-DOMCORE-008)
      db.query("INSERT INTO claim_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)").run(
        claim.claim_revision_id,
        ownerAccountId,
        claim.lifecycle,
        "canonical",
        claim.temporal_scope.observed_at,
        JSON.stringify(claim),
        `hash:qa:claim:${padIndex(index)}`,
        commitId,
      );

      db.query("INSERT INTO generated_adjacency VALUES (?, ?, ?, ?)").run(
        claim.claim_revision_id,
        entity.entity_id,
        "subject",
        commitId,
      );

      parentCommit = commitId;
      headCommitId = commitId;
      headSequence = sequence;
    }

    db.query("INSERT INTO graph_heads VALUES (?, ?, ?)").run(
      ownerAccountId,
      headCommitId,
      headSequence,
    );
  });
  write();
};
