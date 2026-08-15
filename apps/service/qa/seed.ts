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
  // storage-provenance-ok(SQL table name in the QA fixture writer; the seeder populates storage and is never on the read path, so nothing here can reach a wire value)
  "graph_heads",
  "claim_liveness_fences",
  "stm_items",
  "stm_mentions",
] as const);

// domain-pending(DIV-DOMCORE-001)
export interface SeedMemoryContent {
  readonly excerpt: string;
  readonly handle: string;
  readonly predicate: string;
  /** Literal subject phrase the QA synthesizer emits into served summary text. */
  readonly subject_literal: string;
}

export interface SeedQaSnapshotOptions {
  readonly owner_account_id: string;
  readonly memory_count: number;
  /** IANA timezone used for local-day grouping; validated like the QA recall loader. */
  readonly account_timezone: string;
  /**
   * Memories seeded as REAL durable rows that the authorization projection then
   * hides, because their policy labels are not all generic.
   *
   * They exist so a test can prove that a record hidden by authorization is
   * byte-identical on the wire to a record that was never there. Each hidden
   * memory shares a local day with a visible one, so the served day-node exists
   * in both fixture sets and only its membership differs - which is the case where a
   * leak would actually show up in the synthesized text.
   */
  readonly hidden_memory_count?: number;
  /**
   * Optional per-day content. Omitted, the historical QA rows are unchanged.
   * When present, length must equal `memory_count` and `hidden_memory_count`
   * must be 0: the demo persona reuses this writer without rewording QA rows.
   */
  readonly contents?: readonly SeedMemoryContent[];
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

const requireContents = (
  value: unknown,
  memoryCount: number,
  hiddenCount: number,
): readonly SeedMemoryContent[] | undefined => {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) return fail("contents must be an array when provided");
  if (hiddenCount !== 0) {
    return fail("contents cannot be combined with hidden_memory_count");
  }
  if (value.length !== memoryCount) {
    return fail("contents length must equal memory_count");
  }
  const contents: SeedMemoryContent[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null || Array.isArray(item)) {
      return fail("contents entries must be plain objects");
    }
    const record = item as Record<string, unknown>;
    const excerpt = record["excerpt"];
    const handle = record["handle"];
    const predicate = record["predicate"];
    const subjectLiteral = record["subject_literal"];
    if (typeof excerpt !== "string" || excerpt.length === 0
      || typeof handle !== "string" || handle.length === 0
      || typeof predicate !== "string" || predicate.length === 0
      || typeof subjectLiteral !== "string" || subjectLiteral.length === 0) {
      return fail("contents entries need non-empty excerpt, handle, predicate, and subject_literal");
    }
    contents.push(Object.freeze({
      excerpt,
      handle,
      predicate,
      subject_literal: subjectLiteral,
    }));
  }
  return Object.freeze(contents);
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

/** Day-stepped UTC instant from the fixed QA fixture anchor. No wall clock. */
export const qaFixtureInstant = fixtureInstant;

const identity = (token: string, family: "qa" | "demo"): SourceIdentityRef => ({
  namespace_instance_ref: `namespace:${family}:${token}`,
  local_key: `local:${family}:${token}`,
  producer: { producer_ref: `${family}-seed-producer`, contract_ref: `${family}-seed-contract` },
  asserted_identity: { domain: null, scope_ref: null },
});

// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
const buildMemory = (
  ownerAccountId: string,
  accountTimezone: string,
  dayIndex: number,
  commitSequence: number,
  hidden: boolean,
  content: SeedMemoryContent | undefined,
): {
  readonly event: L1Event;
  readonly evidence: Evidence;
  readonly entity: Entity;
  readonly claim: CanonicalClaim;
  readonly commit_id: string;
  readonly sequence: number;
} => {
  const family = content === undefined ? "qa" : "demo";
  const token = `${hidden ? "h" : ""}${padIndex(dayIndex)}`;
  const observedAt = fixtureInstant(dayIndex);
  // A non-generic label is exactly what applicationVisibleClosure filters on.
  // domain-pending(DIV-DOMCORE-008)
  const policyLabels = hidden
    ? ["subject:generic", "sensitivity:private", "capture:generic"]
    : [...GENERIC_POLICY_LABELS];
  const eventRevisionId = `event-revision:${family}:${token}`;
  const evidenceId = `evidence:${family}:${token}`;
  const entityId = `entity:${family}:${token}`;
  const claimRevisionId = `claim:${family}:${token}`;
  const provisionalRevisionId = `provisional:${family}:${token}`;
  const commitId = `commit:${family}:${token}`;
  const predicateId = `predicate:${family}:memory`;
  const excerpt = content?.excerpt ?? `qa memory ${token}`;
  const handle = content?.handle ?? `qa-entity-${token}`;
  const predicateName = content?.predicate ?? "qa_memory";
  const subjectValue = content === undefined
    ? { kind: "entity_ref" as const, ref: entityId }
    : { kind: "literal" as const, value: content.subject_literal };

  const event: L1Event = {
    event_id: `event:${family}:${token}`,
    event_revision_id: eventRevisionId,
    owner_account_id: ownerAccountId,
    capture_session_id: `session:${family}:${token}`,
    stream_id: `${family}-seed-stream`,
    event_kind: "text",
    payload_schema_ref: `${family}-seed-text-v1`,
    schema_version: "v1",
    payload: { fixture_index: dayIndex, fixture_hidden: hidden },
    event_time: observedAt,
    ingest_time: observedAt,
    source_sequence: commitSequence,
    evidence_addressable_refs: [evidenceId],
    source_trust: `${family}-seed`,
    policy_labels: [...policyLabels],
    canonical_redacted_hash: `hash:${family}:event:${token}`,
  };

  const evidence: Evidence = {
    evidence_id: evidenceId,
    event_revision_id: eventRevisionId,
    source_unit_ref: `unit:${family}:${token}`,
    range: { start: 0, end: content === undefined ? 16 : excerpt.length },
    excerpt,
    source_identity_ref: identity(token, family),
    speaker_rendering: null,
    source_local_mention_ref: null,
    state: "active",
    source_trust: `${family}-seed`,
    policy_labels: [...policyLabels],
    source_independence_key: `source:${family}:${token}`,
  };

  // domain-pending(DIV-DOMCORE-007)
  const entity: Entity = {
    entity_id: entityId,
    owner_account_id: ownerAccountId,
    entity_revision_id: `entity-revision:${family}:${token}`,
    handle,
    labels: [`${family}-seed`],
  };

  // domain-pending(DIV-DOMCORE-008)
  const claim: CanonicalClaim = {
    claim_lineage_id: `lineage:${family}:${token}`,
    claim_revision_id: claimRevisionId,
    owner_account_id: ownerAccountId,
    predicate_id: predicateId,
    predicate: predicateName,
    arguments: [{
      slot_id: "subject",
      role: "subject",
      value: subjectValue,
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
          resolver_version: `${family}-seed-v1`,
          timezone: accountTimezone,
        },
      },
    },
    evidence_refs: [evidenceId],
    policy_labels: [...policyLabels],
    source_language: "en",
    scope: { locality: "durable", scope_ref: entityId },
    lifecycle: "canonical",
    canonical_claim_id: `canonical:${family}:${token}`,
    source_provisional_revision_ids: [provisionalRevisionId],
  };

  return { event, evidence, entity, claim, commit_id: commitId, sequence: commitSequence + 1 };
};

const sharedPredicate = (ownerAccountId: string, family: "qa" | "demo"): Predicate => ({
  predicate_id: `predicate:${family}:memory`,
  owner_account_id: ownerAccountId,
  predicate_revision_id: `predicate-revision:${family}:memory`,
  identity_name: family === "qa" ? "qa_memory" : "noted",
  display_name: family === "qa" ? "qa_memory" : "noted",
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
  const hiddenCount = options.hidden_memory_count === undefined
    ? 0
    : requireMemoryCount(options.hidden_memory_count);
  if (hiddenCount > memoryCount) {
    return fail("hidden_memory_count cannot exceed memory_count, since each hidden memory shares a day with a visible one");
  }
  const contents = requireContents(options.contents, memoryCount, hiddenCount);
  const family = contents === undefined ? "qa" : "demo";

  ensureSchema(db);
  resetQaSnapshot(db);

  if (memoryCount === 0) return;

  // Visible memories occupy days 0..memoryCount-1. Each hidden memory reuses one
  // of those same days so the served day-node exists in BOTH fixture sets and only
  // its membership differs.
  const plan: readonly { readonly dayIndex: number; readonly hidden: boolean }[] = [
    ...Array.from({ length: memoryCount }, (_, index) => ({ dayIndex: index, hidden: false })),
    ...Array.from({ length: hiddenCount }, (_, index) => ({ dayIndex: index, hidden: true })),
  ];

  const predicate = sharedPredicate(ownerAccountId, family);
  let parentCommit: string | null = null;
  let headCommitId = "";
  let headSequence = 0;

  const write = db.transaction(() => {
    for (let index = 0; index < plan.length; index += 1) {
      const step = plan[index]!;
      const memory = buildMemory(
        ownerAccountId,
        accountTimezone,
        step.dayIndex,
        index,
        step.hidden,
        step.hidden ? undefined : contents?.[step.dayIndex],
      );
      const { event, evidence, entity, claim, commit_id: commitId, sequence } = memory;
      const rowToken = `${step.hidden ? "h" : ""}${padIndex(step.dayIndex)}`;

      db.query(
        "INSERT INTO derivation_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
      ).run(
        commitId,
        ownerAccountId,
        parentCommit,
        sequence,
        `idempotency:${family}:${rowToken}`,
        `input:${family}:${rowToken}`,
        `input-version:${family}:${rowToken}`,
        `output:${family}:${rowToken}`,
        "success",
        JSON.stringify({ commit_id: commitId, fixture_row: rowToken }),
      );

      if (index === 0) {
        db.query("INSERT INTO predicate_revisions VALUES (?, ?, ?, ?, ?, ?)").run(
          predicate.predicate_revision_id,
          ownerAccountId,
          predicate.predicate_id,
          JSON.stringify(predicate),
          `hash:${family}:predicate:memory`,
          commitId,
        );
      }

      db.query("INSERT INTO event_revisions VALUES (?, ?, ?, ?, ?)").run(
        event.event_revision_id,
        ownerAccountId,
        JSON.stringify(event),
        `hash:${family}:event:${rowToken}`,
        commitId,
      );

      db.query("INSERT INTO evidence_revisions VALUES (?, ?, ?, ?, ?, ?)").run(
        `evidence-revision:${family}:${rowToken}`,
        ownerAccountId,
        event.event_revision_id,
        JSON.stringify(evidence),
        `hash:${family}:evidence:${rowToken}`,
        commitId,
      );

      // domain-pending(DIV-DOMCORE-007)
      db.query("INSERT INTO entity_revisions VALUES (?, ?, ?, ?, ?)").run(
        entity.entity_revision_id,
        ownerAccountId,
        JSON.stringify(entity),
        `hash:${family}:entity:${rowToken}`,
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
        `hash:${family}:claim:${rowToken}`,
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

    // storage-provenance-ok(SQL table name in the QA fixture writer; this INSERT creates fixture storage and is never on the read path)
    db.query("INSERT INTO graph_heads VALUES (?, ?, ?)").run(
      ownerAccountId,
      headCommitId,
      headSequence,
    );
  });
  write();
};
