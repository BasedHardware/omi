import { Database } from "bun:sqlite";
import {
  canonicalizeRedacted,
  sha256CanonicalRedacted,
  validateAtomicGraphTransition,
  type AtomicGraphTransition,
  type ClaimRevision,
  type EntityRevision,
  type GraphRevision,
  type IdentityRevision,
  type LedgerPort,
} from "../../core/ledger";
import { retrieveCommittedGraph, type GraphSnapshot, type RetrievalRequest, type RetrievalResult } from "../../core/retrieve";

export class IdempotencyConflictError extends Error {}
export class GraphHeadConflictError extends Error {}
export type CrashPoint = "after_claims" | "after_adjacency" | "after_consumed_markers" | "after_ledger";

const revisionContent = (revision: GraphRevision) => revision.kind === "claim" ? revision.claim : revision.kind === "entity" ? revision.entity : revision.constraint;

/** The only imperative T9 shell. No model port is accepted or invoked by this driver. */
export class SqliteLedger implements LedgerPort {
  constructor(readonly db: Database) { this.migrate(); }

  private migrate(): void {
    this.db.exec(`
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS claim_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, lifecycle TEXT NOT NULL,
        placement_status TEXT NOT NULL, observed_at TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS entity_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS identity_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS generated_adjacency (
        claim_revision_id TEXT NOT NULL, entity_id TEXT NOT NULL, role_slot_id TEXT NOT NULL,
        commit_id TEXT NOT NULL, PRIMARY KEY (claim_revision_id, entity_id, role_slot_id)
      );
      CREATE TABLE IF NOT EXISTS consumed_markers (
        provisional_revision_id TEXT PRIMARY KEY, commit_id TEXT NOT NULL, disposition TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS derivation_attempts (
        attempt_id TEXT PRIMARY KEY, commit_id TEXT NOT NULL, owner_account_id TEXT NOT NULL,
        input_version_digest TEXT NOT NULL, record_json TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS derivation_commits (
        commit_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, parent_commit TEXT,
        sequence INTEGER NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
        input_digest TEXT NOT NULL, input_version_digest TEXT NOT NULL, output_digest TEXT NOT NULL,
        success_kind TEXT NOT NULL, record_json TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS graph_heads (
        owner_account_id TEXT PRIMARY KEY, commit_id TEXT NOT NULL, sequence INTEGER NOT NULL
      );
    `);
  }

  appendTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }> {
    return Promise.resolve(this.append(plan));
  }

  append(plan: AtomicGraphTransition, crashAt?: CrashPoint): { commit_id: string; sequence: number; idempotent: boolean } {
    validateAtomicGraphTransition(plan);
    const commit = plan.derivation.commit;
    const transaction = this.db.transaction(() => {
      const existing = this.db.query("SELECT commit_id, sequence, input_version_digest FROM derivation_commits WHERE idempotency_key = ?").get(commit.idempotency_key) as { commit_id: string; sequence: number; input_version_digest: string } | null;
      if (existing) {
        if (existing.input_version_digest === commit.input_version_digest) return { commit_id: existing.commit_id, sequence: existing.sequence, idempotent: true };
        throw new IdempotencyConflictError(`idempotency key reused with a different input/version digest: ${commit.idempotency_key}`);
      }
      const head = this.db.query("SELECT commit_id, sequence FROM graph_heads WHERE owner_account_id = ?").get(commit.owner_account_id) as { commit_id: string; sequence: number } | null;
      if ((head?.commit_id ?? null) !== commit.parent_commit) throw new GraphHeadConflictError(`stale parent commit: expected ${head?.commit_id ?? "null"}, received ${commit.parent_commit ?? "null"}`);
      const sequence = (head?.sequence ?? 0) + 1;
      for (const revision of plan.revisions) this.writeRevision(revision, commit.commit_id);
      if (crashAt === "after_claims") throw new Error("injected crash after claims");
      for (const edge of plan.adjacency) this.db.query("INSERT INTO generated_adjacency VALUES (?, ?, ?, ?)").run(edge.claim_revision_id, edge.entity_id, edge.role_slot_id, commit.commit_id);
      if (crashAt === "after_adjacency") throw new Error("injected crash after adjacency");
      for (const result of plan.placement.results) this.db.query("INSERT INTO consumed_markers VALUES (?, ?, ?)").run(result.input_provisional_revision_id, commit.commit_id, result.disposition);
      if (crashAt === "after_consumed_markers") throw new Error("injected crash after consumed markers");
      const committed = { ...commit, sequence };
      this.db.query("INSERT INTO derivation_attempts VALUES (?, ?, ?, ?, ?)").run(plan.derivation.attempt.attempt_id, commit.commit_id, commit.owner_account_id, commit.input_version_digest, canonicalizeRedacted(plan.derivation.attempt as never));
      this.db.query("INSERT INTO derivation_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(commit.commit_id, commit.owner_account_id, commit.parent_commit, sequence, commit.idempotency_key, commit.input_digest, commit.input_version_digest, commit.output_digest, commit.success_kind, canonicalizeRedacted(committed as never));
      if (crashAt === "after_ledger") throw new Error("injected crash after ledger");
      this.db.query("INSERT INTO graph_heads VALUES (?, ?, ?) ON CONFLICT(owner_account_id) DO UPDATE SET commit_id = excluded.commit_id, sequence = excluded.sequence").run(commit.owner_account_id, commit.commit_id, sequence);
      return { commit_id: commit.commit_id, sequence, idempotent: false };
    });
    return transaction();
  }

  private writeRevision(revision: GraphRevision, commitId: string): void {
    const content = revisionContent(revision);
    const json = canonicalizeRedacted(content as never);
    const hash = sha256CanonicalRedacted(content as never);
    if (revision.kind === "claim") {
      this.db.query("INSERT INTO claim_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)").run(revision.revision_id, revision.claim.owner_account_id, revision.claim.lifecycle, revision.placement_status, revision.claim.temporal_scope.observed_at, json, hash, commitId);
    } else if (revision.kind === "entity") {
      this.db.query("INSERT INTO entity_revisions VALUES (?, ?, ?, ?, ?)").run(revision.revision_id, revision.entity.owner_account_id, json, hash, commitId);
    } else {
      this.db.query("INSERT INTO identity_revisions VALUES (?, ?, ?, ?, ?)").run(revision.revision_id, revision.constraint.owner_account_id, json, hash, commitId);
    }
  }

  snapshot(ownerAccountId: string): GraphSnapshot {
    const claims = (this.db.query("SELECT revision_id, placement_status, content_json FROM claim_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; placement_status: ClaimRevision["placement_status"]; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, placement_status: row.placement_status, claim: JSON.parse(row.content_json) }));
    const entities = (this.db.query("SELECT revision_id, content_json FROM entity_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, entity: JSON.parse(row.content_json) }));
    const adjacency = this.db.query("SELECT claim_revision_id, entity_id, role_slot_id FROM generated_adjacency WHERE claim_revision_id IN (SELECT revision_id FROM claim_revisions WHERE owner_account_id = ?) ORDER BY claim_revision_id, entity_id, role_slot_id").all(ownerAccountId) as GraphSnapshot["adjacency"];
    return { owner_account_id: ownerAccountId, claims, entities, adjacency };
  }

  retrieve(request: RetrievalRequest): RetrievalResult { return retrieveCommittedGraph(this.snapshot(request.owner_account_id), request); }

  counts(): Record<string, number> {
    const tables = ["claim_revisions", "entity_revisions", "identity_revisions", "generated_adjacency", "consumed_markers", "derivation_attempts", "derivation_commits", "graph_heads"];
    return Object.fromEntries(tables.map((table) => [table, (this.db.query(`SELECT COUNT(*) AS count FROM ${table}`).get() as { count: number }).count]));
  }
}
