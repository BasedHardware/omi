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

import type { CanonicalClaim, Evidence, L1Event, SourceIdentityRef } from "../../core/schema";
import { SqliteLedger } from "../../drivers/sqlite/index";
import { SqliteStmStore } from "../../drivers/sqlite/stm";

export interface QaSeedOptions {
  readonly owner_account_id: string;
  readonly account_timezone: string;
  readonly claim_count: number;
  /**
   * Physical insertion order of the seeded rows. The seeded *content* is
   * identical either way — only the order the rows hit the tables differs.
   *
   * This exists so a proof can show server order is independent of insertion
   * history rather than merely repeatable, which is a much weaker claim. Row
   * identity, ids, and timestamps stay a pure function of the logical index.
   */
  readonly insertion_order?: "ascending" | "descending";
  /**
   * Logical indices to seed with a non-generic policy label. Such a claim is
   * durably present but invisible to the application-default projection, which
   * is what makes hidden-present versus physically-absent testable.
   */
  readonly hidden_indices?: readonly number[];
}

export interface QaSeedResult {
  readonly owner_account_id: string;
  readonly claim_revision_ids: readonly string[];
  readonly evidence_ids: readonly string[];
  readonly event_revision_ids: readonly string[];
  readonly graph_generation: number;
}

const pad4 = (index: number): string => String(index).padStart(4, "0");

const requireOwner = (value: string): string => {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError("QA seed owner_account_id must be a non-empty string");
  }
  return value;
};

const requireTimezone = (value: string): string => {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError("QA seed account_timezone must be a non-empty string");
  }
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format(0);
  } catch {
    throw new TypeError("QA seed account_timezone is invalid");
  }
  return value;
};

const requireClaimCount = (value: number): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new TypeError("QA seed claim_count must be a non-negative safe integer");
  }
  return value;
};

/** Calendar instant derived only from the row index (no wall clock). */
const observedAtFor = (index: number): string => {
  const dayOffset = index;
  const month = String((Math.floor(dayOffset / 28) % 12) + 1).padStart(2, "0");
  const day = String((dayOffset % 28) + 1).padStart(2, "0");
  const hour = String(index % 24).padStart(2, "0");
  return `2026-${month}-${day}T${hour}:00:00.000Z`;
};

const identityFor = (owner: string, index: number): SourceIdentityRef => ({
  namespace_instance_ref: `namespace:qa:${owner}:${pad4(index)}`,
  local_key: `local:qa:${pad4(index)}`,
  producer: { producer_ref: "qa-seed-producer", contract_ref: "qa-seed-contract" },
  asserted_identity: { domain: null, scope_ref: null },
});

const eventFor = (owner: string, index: number, evidenceId: string, eventRevisionId: string): L1Event => {
  const observedAt = observedAtFor(index);
  return {
    event_id: `qa-event:${owner}:${pad4(index)}`,
    event_revision_id: eventRevisionId,
    owner_account_id: owner,
    capture_session_id: `qa-session:${owner}:${pad4(index)}`,
    stream_id: "qa-seed-stream",
    event_kind: "text",
    payload_schema_ref: "qa-seed-text-v1",
    schema_version: "v1",
    payload: { seed_index: index },
    event_time: observedAt,
    ingest_time: observedAt,
    source_sequence: index,
    evidence_addressable_refs: [evidenceId],
    source_trust: "qa-seed",
    policy_labels: [],
    canonical_redacted_hash: `qa-event-hash:${owner}:${pad4(index)}`,
  };
};

const evidenceFor = (owner: string, index: number, evidenceId: string, eventRevisionId: string): Evidence => ({
  evidence_id: evidenceId,
  event_revision_id: eventRevisionId,
  source_unit_ref: `qa-unit:${pad4(index)}`,
  range: { start: 0, end: 8 },
  excerpt: `qa seed ${pad4(index)}`,
  source_identity_ref: identityFor(owner, index),
  speaker_rendering: null,
  source_local_mention_ref: null,
  state: "active",
  source_trust: "qa-seed",
  policy_labels: [],
  source_independence_key: `qa-source:${owner}:${pad4(index)}`,
});

// domain-pending(DIV-DOMCORE-008)
const claimFor = (
  owner: string,
  timezone: string,
  index: number,
  claimRevisionId: string,
  evidenceId: string,
): CanonicalClaim => {
  const observedAt = observedAtFor(index);
  return {
    claim_lineage_id: `qa-lineage:${owner}:${pad4(index)}`,
    claim_revision_id: claimRevisionId,
    owner_account_id: owner,
    predicate: "qa_seed_predicate",
    arguments: [{
      slot_id: "subject",
      role: "subject",
      value: { kind: "source_local_ref", ref: `qa-source-local:${owner}:${pad4(index)}` },
    }],
    temporal_scope: {
      observed_at: observedAt,
      precision: "instant",
      valid_time: {
        typed_expression: { kind: "absolute", granularity: "instant", value: observedAt },
        resolved_interval: {
          kind: "instant",
          start: observedAt,
          end: observedAt,
          timezone,
          granularity: "instant",
        },
        derivation: { resolver_version: "qa-seed-v1", timezone },
      },
    },
    evidence_refs: [evidenceId],
    policy_labels: [],
    source_language: "en",
    scope: { locality: "durable", scope_ref: null },
    lifecycle: "canonical",
    canonical_claim_id: `qa-canonical:${owner}:${pad4(index)}`,
    source_provisional_revision_ids: [],
  };
};

const insertDerivation = (
  db: Database,
  commitId: string,
  owner: string,
  sequence: number,
): void => {
  db.query("INSERT INTO derivation_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(
    commitId,
    owner,
    sequence === 1 ? null : `qa-commit:${owner}:${pad4(sequence - 2)}`,
    sequence,
    `qa-idempotency:${owner}:${pad4(sequence - 1)}`,
    `qa-input:${commitId}`,
    `qa-input-version:${commitId}`,
    `qa-output:${commitId}`,
    "success",
    JSON.stringify({ commit_id: commitId, sequence }),
  );
};

/**
 * Hermetic SQLite seed for QA recall. Writes a durable canonical graph by direct
 * inserts (not the ledger append path) so snapshot + application authorization
 * see exactly `claim_count` visible claims.
 */
export const seedQaSnapshot = (db: Database, options: QaSeedOptions): QaSeedResult => {
  const owner = requireOwner(options.owner_account_id);
  const timezone = requireTimezone(options.account_timezone);
  const claimCount = requireClaimCount(options.claim_count);

  // Ensure ledger + STM schemas exist before any row writes.
  new SqliteLedger(db);
  new SqliteStmStore(db);

  const claimRevisionIds: string[] = [];
  const evidenceIds: string[] = [];
  const eventRevisionIds: string[] = [];

  const hidden = new Set(options.hidden_indices ?? []);
  const order = options.insertion_order === "descending"
    ? Array.from({ length: claimCount }, (_, index) => claimCount - 1 - index)
    : Array.from({ length: claimCount }, (_, index) => index);

  for (const index of order) {
    const token = pad4(index);
    const sequence = index + 1;
    const commitId = `qa-commit:${owner}:${token}`;
    const claimRevisionId = `qa-claim:${owner}:${token}`;
    const evidenceId = `qa-evidence:${owner}:${token}`;
    const evidenceRevisionId = `qa-evidence-revision:${owner}:${token}`;
    const eventRevisionId = `qa-event-revision:${owner}:${token}`;

    const event = eventFor(owner, index, evidenceId, eventRevisionId);
    const evidence = evidenceFor(owner, index, evidenceId, eventRevisionId);
    const baseClaim = claimFor(owner, timezone, index, claimRevisionId, evidenceId);
    // A non-generic policy label makes the claim durably present but invisible
    // to the application-default projection.
    const claim: CanonicalClaim = hidden.has(index)
      ? { ...baseClaim, policy_labels: ["sensitivity:restricted"] }
      : baseClaim;

    insertDerivation(db, commitId, owner, sequence);

    db.query("INSERT INTO event_revisions VALUES (?, ?, ?, ?, ?)").run(
      eventRevisionId,
      owner,
      JSON.stringify(event),
      `qa-hash:event:${eventRevisionId}`,
      commitId,
    );
    db.query("INSERT INTO evidence_revisions VALUES (?, ?, ?, ?, ?, ?)").run(
      evidenceRevisionId,
      owner,
      eventRevisionId,
      JSON.stringify(evidence),
      `qa-hash:evidence:${evidenceRevisionId}`,
      commitId,
    );
    db.query("INSERT INTO claim_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)").run(
      claimRevisionId,
      owner,
      claim.lifecycle,
      "canonical",
      claim.temporal_scope.observed_at,
      JSON.stringify(claim),
      `qa-hash:claim:${claimRevisionId}`,
      commitId,
    );
    db.query("INSERT INTO source_local_claim_roles VALUES (?, ?, ?, ?)").run(
      claimRevisionId,
      `qa-source-local:${owner}:${token}`,
      "subject",
      commitId,
    );

    claimRevisionIds[index] = claimRevisionId;
    evidenceIds[index] = evidenceId;
    eventRevisionIds[index] = eventRevisionId;
  }

  const graphGeneration = claimCount;
  if (claimCount === 0) {
    const bootstrapCommitId = `qa-commit:${owner}:bootstrap`;
    db.query("INSERT INTO derivation_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(
      bootstrapCommitId,
      owner,
      null,
      0,
      `qa-idempotency:${owner}:bootstrap`,
      `qa-input:${bootstrapCommitId}`,
      `qa-input-version:${bootstrapCommitId}`,
      `qa-output:${bootstrapCommitId}`,
      "success",
      JSON.stringify({ commit_id: bootstrapCommitId, sequence: 0 }),
    );
    db.query("INSERT INTO graph_heads VALUES (?, ?, ?)").run(owner, bootstrapCommitId, 0);
  } else {
    const headCommitId = `qa-commit:${owner}:${pad4(claimCount - 1)}`;
    db.query("INSERT INTO graph_heads VALUES (?, ?, ?)").run(owner, headCommitId, graphGeneration);
  }

  return {
    owner_account_id: owner,
    claim_revision_ids: claimRevisionIds,
    evidence_ids: evidenceIds,
    event_revision_ids: eventRevisionIds,
    graph_generation: graphGeneration,
  };
};
