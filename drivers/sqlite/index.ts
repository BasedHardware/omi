import { compareStrings } from "../../core/order";
import { Database } from "bun:sqlite";
import {
  canonicalizeRedacted,
  sha256CanonicalRedacted,
  GraphTransitionValidationError,
  validateAtomicGraphTransition,
  type AtomicGraphTransition,
  type ClaimRevision,
  type EntityRevision,
  type EvidenceRevision,
  type EventRevision,
  type GraphRevision,
  type IdentityRevision,
  type IdentityAuthorizationRevision,
  type LedgerPort,
  type MentionRevision,
  type CoreferenceSupportRevision,
  type PredicateRevision,
  type PredicateAssertionRevision,
  type PlacementArtifact,
} from "../../core/ledger";
import { liveCommittedClaims, retrieveCommittedGraph, type CommittedClaim, type GraphSnapshot, type RetrievalRequest, type RetrievalResult } from "../../core/retrieve";
import { identityConstraintConflicts } from "../../core/resolve/entities";
import { authorizeIdentity } from "../../core/resolve/identity-authority";
import type { IdentityConstraint } from "../../core/schema";

export class IdempotencyConflictError extends Error {}
export class GraphHeadConflictError extends Error {}
export type LivenessFenceCause = "purged" | "forgotten";
export type CrashPoint = "after_authorization" | "after_constraint" | "after_claims" | "after_adjacency" | "after_consumed_markers" | "after_ledger";

const revisionContent = (revision: GraphRevision) => revision.kind === "claim" ? revision.claim : revision.kind === "entity" ? revision.entity : revision.kind === "predicate" ? revision.predicate : revision.kind === "predicate_assertion" ? revision.assertion : revision.kind === "identity" ? revision.constraint : revision.kind === "event" ? revision.event : revision.kind === "evidence" ? revision.evidence : revision.kind === "mention" ? revision.mention : revision.kind === "identity_authorization" ? revision.authorization : revision.support;

/** The only imperative T9 shell. No model port is accepted or invoked by this driver. */
export class SqliteLedger implements LedgerPort {
  constructor(private readonly db: Database) { this.migrate(); }

  private migrate(): void {
    // Production concurrency defaults. WAL lets concurrent readers proceed
    // while a writer holds the write lock, and busy_timeout makes a second
    // connection wait (instead of failing immediately with SQLITE_BUSY) when
    // the write lock is briefly held. On :memory: databases -- every test
    // constructs one -- `journal_mode = WAL` is a documented no-op that
    // reports "memory"; we consume the pragma's result row and never assert
    // on it, so both file-backed and in-memory construction succeed.
    this.db.exec("PRAGMA busy_timeout = 5000;");
    this.db.query("PRAGMA journal_mode = WAL;").get();
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
      CREATE TABLE IF NOT EXISTS predicate_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, predicate_id TEXT NOT NULL,
        content_json TEXT NOT NULL, content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS predicate_assertion_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, predicate_id TEXT NOT NULL,
        content_json TEXT NOT NULL, content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS identity_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL, constraint_id TEXT NOT NULL,
        authorization_revision_id TEXT NOT NULL REFERENCES identity_authorization_revisions(revision_id),
        UNIQUE(owner_account_id, revision_id)
      );
      CREATE TABLE IF NOT EXISTS event_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS evidence_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, event_revision_id TEXT NOT NULL,
        content_json TEXT NOT NULL, content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS mention_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, claim_revision_id TEXT NOT NULL,
        content_json TEXT NOT NULL, content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS identity_authorization_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL, authorization_id TEXT NOT NULL,
        lifecycle TEXT NOT NULL, UNIQUE(owner_account_id, authorization_id, revision_id)
      );
      CREATE TABLE IF NOT EXISTS coreference_support_revisions (
        revision_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS identity_support_revisions (
        revision_id TEXT PRIMARY KEY, support_ref TEXT NOT NULL, owner_account_id TEXT NOT NULL,
        content_json TEXT NOT NULL, content_hash TEXT NOT NULL, commit_id TEXT NOT NULL,
        UNIQUE(commit_id, support_ref)
      );
      CREATE TABLE IF NOT EXISTS candidate_derivation_artifacts (
        artifact_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, content_json TEXT NOT NULL,
        commit_id TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS generated_adjacency (
        claim_revision_id TEXT NOT NULL, entity_id TEXT NOT NULL, role_slot_id TEXT NOT NULL,
        commit_id TEXT NOT NULL, PRIMARY KEY (claim_revision_id, entity_id, role_slot_id)
      );
      /* Source-local roles are retrievable coordinates, never entity edges. */
      CREATE TABLE IF NOT EXISTS source_local_claim_roles (
        claim_revision_id TEXT NOT NULL, source_local_ref TEXT NOT NULL, role_slot_id TEXT NOT NULL,
        commit_id TEXT NOT NULL, PRIMARY KEY (claim_revision_id, source_local_ref, role_slot_id)
      );
      CREATE TABLE IF NOT EXISTS consumed_markers (
        provisional_revision_id TEXT PRIMARY KEY, commit_id TEXT NOT NULL, disposition TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS placement_artifacts (
        artifact_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, kind TEXT NOT NULL,
        provisional_revision_id TEXT NOT NULL, canonical_claim_revision_id TEXT, margin TEXT,
        risk_markers_json TEXT NOT NULL, unit_boundary_decision TEXT NOT NULL, scope_locality TEXT, commit_id TEXT NOT NULL
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
      CREATE TABLE IF NOT EXISTS claim_liveness_fences (
        owner_account_id TEXT NOT NULL, claim_revision_id TEXT NOT NULL,
        cause TEXT NOT NULL CHECK (cause IN ('purged', 'forgotten')),
        PRIMARY KEY (owner_account_id, claim_revision_id, cause)
      );
      /* Append-only D48 overlays.  They retain old rows for audit but make them
         ineligible for active identity and retrieval projections. */
      CREATE TABLE IF NOT EXISTS identity_quarantine_records (
        migration_id TEXT NOT NULL, owner_account_id TEXT NOT NULL, identity_revision_id TEXT NOT NULL,
        dependency_status TEXT NOT NULL, policy_version TEXT NOT NULL, reason TEXT NOT NULL,
        PRIMARY KEY (migration_id, identity_revision_id),
        FOREIGN KEY (identity_revision_id) REFERENCES identity_revisions(revision_id)
      );
      CREATE TABLE IF NOT EXISTS claim_quarantine_records (
        migration_id TEXT NOT NULL, owner_account_id TEXT NOT NULL, claim_revision_id TEXT NOT NULL,
        dependency_status TEXT NOT NULL, policy_version TEXT NOT NULL, reason TEXT NOT NULL,
        PRIMARY KEY (migration_id, claim_revision_id),
        FOREIGN KEY (claim_revision_id) REFERENCES claim_revisions(revision_id)
      );
    `);
  }

  async appendTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }> {
    return this.append(plan);
  }

  /**
   * Bounded optimistic-concurrency retry for two writers on one owner.
   *
   * Reads the current graph head, asks `planFor` to produce a transition
   * against that parent, and attempts the append. When another writer lands a
   * commit between the head read and the append, `append` throws
   * GraphHeadConflictError; this method then re-reads the head and calls
   * `planFor` again with the NEW parent, up to `attempts` times (default 3),
   * rethrowing the last conflict when the budget is exhausted.
   *
   * The callback takes the parent commit because the plan's derivation must be
   * REBUILT against the new head, never mutated: `parent_commit` is baked into
   * the derivation record at `prepareDerivation` time, and any placement or
   * identity decision the caller made may depend on graph state that the
   * intervening commit changed. Patching `parent_commit` on a stale plan would
   * commit decisions derived from a head that no longer exists.
   *
   * This is strictly a retry loop around `appendTransitionPlan`: witness
   * verification, validation, and idempotency behave exactly as they do there,
   * and every non-conflict error propagates immediately without a retry.
   */
  async appendWithHeadRetry(ownerAccountId: string, planFor: (parentCommit: string | null) => AtomicGraphTransition | Promise<AtomicGraphTransition>, opts?: { attempts?: number }): Promise<{ commit_id: string; sequence: number; idempotent: boolean }> {
    const attempts = Math.max(1, opts?.attempts ?? 3);
    let conflict: GraphHeadConflictError | undefined;
    for (let attempt = 0; attempt < attempts; attempt++) {
      const parent = this.graphHead(ownerAccountId)?.commit_id ?? null;
      const plan = await planFor(parent);
      try {
        return await this.appendTransitionPlan(plan);
      } catch (error) {
        if (!(error instanceof GraphHeadConflictError)) throw error;
        conflict = error;
      }
    }
    throw conflict;
  }

  async replayTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }> {
    return this.append(plan);
  }

  async repairTransitionPlan(plan: AtomicGraphTransition): Promise<{ commit_id: string; sequence: number; idempotent: boolean }> {
    return this.append(plan);
  }

  /** Monotone D35 erasure: there is intentionally no API to remove a fence. */
  recordLivenessFence(ownerAccountId: string, claimRevisionId: string, cause: LivenessFenceCause): void {
    this.db.query("INSERT OR IGNORE INTO claim_liveness_fences VALUES (?, ?, ?)").run(ownerAccountId, claimRevisionId, cause);
  }

  purgeClaim(ownerAccountId: string, claimRevisionId: string): void {
    this.recordLivenessFence(ownerAccountId, claimRevisionId, "purged");
  }

  forgetClaim(ownerAccountId: string, claimRevisionId: string): void {
    this.recordLivenessFence(ownerAccountId, claimRevisionId, "forgotten");
  }

  /**
   * Storage-side verification of the caller's immutable witness set.
   *
   * `committed_revisions` is REPLAYABLE AUTHORITY: the core validator will
   * revalidate a witnessed identity authorization and accept it exactly like a
   * newly minted one.  Core is storage-agnostic and therefore cannot tell a
   * genuine carried authorization from a fabricated or stale copy -- a forged
   * revision says `lifecycle: "active"` about itself just as convincingly as a
   * real one does.  Only this boundary can, so every witness is checked against
   * the durable row before validation is allowed to trust it:
   *   - it must exist under its own revision id with the SAME content hash, and
   *   - an identity authorization must additionally still be the HEAD revision
   *     of its authorization_id and still be active, so a superseded or revoked
   *     authorization cannot be replayed from an old copy.
   * Mention/claim/evidence/event witnesses are lineage inputs rather than
   * authority, so they are checked for existence and integrity only.
   */
  private verifyCommittedWitnesses(plan: AtomicGraphTransition): void {
    const witnessTables: Partial<Record<GraphRevision["kind"], string>> = {
      identity_authorization: "identity_authorization_revisions",
      mention: "mention_revisions",
      claim: "claim_revisions",
      evidence: "evidence_revisions",
      event: "event_revisions",
    };
    for (const revision of plan.committed_revisions ?? []) {
      const table = witnessTables[revision.kind];
      if (!table) continue;
      const row = this.db.query(`SELECT content_hash FROM ${table} WHERE revision_id = ?`).get(revision.revision_id) as { content_hash: string } | null;
      if (!row) throw new GraphTransitionValidationError(`witnessed revision is not committed: ${revision.revision_id}`);
      if (row.content_hash !== sha256CanonicalRedacted(revisionContent(revision) as never)) throw new GraphTransitionValidationError(`witnessed revision does not match its committed content: ${revision.revision_id}`);
      if (revision.kind !== "identity_authorization") continue;
      const head = this.db.query("SELECT revision_id, lifecycle FROM identity_authorization_revisions WHERE owner_account_id = ? AND authorization_id = ? ORDER BY rowid DESC LIMIT 1").get(revision.authorization.owner_account_id, revision.authorization.authorization_id) as { revision_id: string; lifecycle: string } | null;
      if (!head || head.revision_id !== revision.revision_id) throw new GraphTransitionValidationError(`witnessed identity authorization is not the durable head of its authorization: ${revision.revision_id}`);
      if (head.lifecycle !== "active") throw new GraphTransitionValidationError(`witnessed identity authorization is no longer active: ${revision.revision_id}`);
    }
  }

  append(plan: AtomicGraphTransition, crashAt?: CrashPoint): { commit_id: string; sequence: number; idempotent: boolean } {
    // Witness verification runs BEFORE validation: the validator would
    // otherwise revalidate a forged authorization against its own fields.
    this.verifyCommittedWitnesses(plan);
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
      // The candidate plan is not an authority island: compare every incoming
      // relation against the durable active closure under the same SQLite
      // transaction before anything is written.
      const durableConstraints = (this.db.query("SELECT content_json FROM (SELECT i.content_json, i.constraint_id, ROW_NUMBER() OVER (PARTITION BY i.constraint_id ORDER BY d.sequence DESC, i.rowid DESC) AS head_rank FROM identity_revisions i JOIN derivation_commits d ON d.commit_id = i.commit_id WHERE i.owner_account_id = ?) WHERE head_rank = 1").all(commit.owner_account_id) as { content_json: string }[])
        .map((row) => JSON.parse(row.content_json) as IdentityConstraint);
      const incomingConstraints = plan.revisions.filter((revision): revision is IdentityRevision => revision.kind === "identity").map((revision) => revision.constraint);
      const closure = [...durableConstraints];
      for (const constraint of incomingConstraints) {
        // A same-constraint revision is an owner-authorized reversal/update,
        // not a second simultaneously-active relation.
        const prior = closure.findIndex((item) => item.constraint_id === constraint.constraint_id);
        if (prior >= 0) closure.splice(prior, 1);
        if (identityConstraintConflicts(closure, constraint)) throw new GraphTransitionValidationError(`durable active identity conflict: ${constraint.constraint_id}`);
        closure.push(constraint);
      }
      // Constraints refer to persisted authorization revisions.  Write the
      // parent first even when callers supplied revisions in another order.
      for (const revision of plan.revisions.filter((item) => item.kind === "identity_authorization")) {
        this.writeRevision(revision, commit.commit_id);
        if (crashAt === "after_authorization") throw new Error("injected crash after authorization");
      }
      for (const support of plan.derived_identity_support ?? plan.identity_authority_context?.identity_support ?? []) {
        // This value is derived by the trusted extraction path before it reaches
        // persistence; legacy model/caller support labels are still rejected.
        const durableSupport = { support_ref: support.support_ref, owner_account_id: support.owner_account_id, evidence_ref: support.evidence_ref, claim_revision_id: support.claim_revision_id, source_independence_key: support.source_independence_key, support_origin: support.support_origin ?? "independent" };
        const content = canonicalizeRedacted(durableSupport as never);
        this.db.query("INSERT INTO identity_support_revisions VALUES (?, ?, ?, ?, ?, ?)").run(`${commit.commit_id}:${support.support_ref}`, support.support_ref, support.owner_account_id, content, sha256CanonicalRedacted(durableSupport as never), commit.commit_id);
      }
      for (const revision of plan.revisions.filter((item) => item.kind !== "identity_authorization" && item.kind !== "identity")) this.writeRevision(revision, commit.commit_id);
      for (const revision of plan.revisions.filter((item) => item.kind === "identity")) {
        this.writeRevision(revision, commit.commit_id);
        if (crashAt === "after_constraint") throw new Error("injected crash after constraint");
      }
      if (crashAt === "after_claims") throw new Error("injected crash after claims");
      for (const edge of plan.adjacency) this.db.query("INSERT INTO generated_adjacency VALUES (?, ?, ?, ?)").run(edge.claim_revision_id, edge.entity_id, edge.role_slot_id, commit.commit_id);
      if (crashAt === "after_adjacency") throw new Error("injected crash after adjacency");
      for (const result of plan.placement.results) this.db.query("INSERT INTO consumed_markers VALUES (?, ?, ?)").run(result.input_provisional_revision_id, commit.commit_id, result.disposition);
      for (const artifact of plan.artifacts) {
        if (artifact.kind === "candidate_derivation") this.db.query("INSERT INTO candidate_derivation_artifacts VALUES (?, ?, ?, ?)").run(artifact.artifact_id, artifact.owner_account_id, canonicalizeRedacted(artifact as never), commit.commit_id);
        else this.db.query("INSERT INTO placement_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(artifact.artifact_id, commit.owner_account_id, artifact.kind, artifact.provisional_revision_id, artifact.canonical_claim_revision_id, artifact.margin, JSON.stringify(artifact.risk_markers), artifact.unit_boundary_decision, artifact.scope_locality, commit.commit_id);
      }
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
      for (const argument of revision.claim.arguments) if (argument.value.kind === "source_local_ref") {
        this.db.query("INSERT INTO source_local_claim_roles VALUES (?, ?, ?, ?)").run(revision.revision_id, argument.value.ref, argument.slot_id, commitId);
      }
    } else if (revision.kind === "entity") {
      this.db.query("INSERT INTO entity_revisions VALUES (?, ?, ?, ?, ?)").run(revision.revision_id, revision.entity.owner_account_id, json, hash, commitId);
    } else if (revision.kind === "predicate") {
      const predicate = revision as PredicateRevision;
      const prior = this.db.query("SELECT content_hash FROM predicate_revisions WHERE revision_id = ?").get(predicate.revision_id) as { content_hash: string } | null;
      if (prior && prior.content_hash !== hash) throw new GraphTransitionValidationError(`predicate revision conflicts with immutable vocabulary object: ${predicate.revision_id}`);
      if (!prior) this.db.query("INSERT INTO predicate_revisions VALUES (?, ?, ?, ?, ?, ?)").run(predicate.revision_id, predicate.predicate.owner_account_id, predicate.predicate.predicate_id, json, hash, commitId);
    } else if (revision.kind === "predicate_assertion") {
      const assertion = revision as PredicateAssertionRevision;
      this.db.query("INSERT INTO predicate_assertion_revisions VALUES (?, ?, ?, ?, ?, ?)").run(assertion.revision_id, assertion.assertion.owner_account_id, assertion.assertion.predicate_id, json, hash, commitId);
    } else if (revision.kind === "identity") {
      const authorizationId = revision.constraint.identity_authorization?.authorization_id;
      if (!authorizationId) throw new Error(`identity constraint lacks persisted authorization: ${revision.revision_id}`);
      const authorization = this.db.query("SELECT revision_id FROM identity_authorization_revisions WHERE owner_account_id = ? AND authorization_id = ? ORDER BY rowid DESC LIMIT 1").get(revision.constraint.owner_account_id, authorizationId) as { revision_id: string } | null;
      if (!authorization) throw new Error(`identity constraint authorization is not persisted: ${revision.revision_id}`);
      this.db.query("INSERT INTO identity_revisions VALUES (?, ?, ?, ?, ?, ?, ?)").run(revision.revision_id, revision.constraint.owner_account_id, json, hash, commitId, revision.constraint.constraint_id, authorization.revision_id);
    } else if (revision.kind === "event") {
      this.db.query("INSERT INTO event_revisions VALUES (?, ?, ?, ?, ?)").run(revision.revision_id, revision.event.owner_account_id, json, hash, commitId);
    } else if (revision.kind === "evidence") {
      const evidence = revision as EvidenceRevision;
      this.db.query("INSERT INTO evidence_revisions VALUES (?, ?, ?, ?, ?, ?)").run(evidence.revision_id, "", evidence.evidence.event_revision_id, json, hash, commitId);
    } else if (revision.kind === "mention") {
      const mention = revision as MentionRevision;
      this.db.query("INSERT INTO mention_revisions VALUES (?, ?, ?, ?, ?, ?)").run(mention.revision_id, mention.mention.owner_account_id, mention.mention.claim_revision_id, json, hash, commitId);
    } else if (revision.kind === "identity_authorization") {
      const authorization = revision as IdentityAuthorizationRevision;
      this.db.query("INSERT INTO identity_authorization_revisions VALUES (?, ?, ?, ?, ?, ?, ?)").run(authorization.revision_id, authorization.authorization.owner_account_id, json, hash, commitId, authorization.authorization.authorization_id, authorization.authorization.lifecycle);
    } else {
      const support = revision as CoreferenceSupportRevision;
      this.db.query("INSERT INTO coreference_support_revisions VALUES (?, ?, ?, ?, ?)").run(support.revision_id, support.support.owner_account_id, json, hash, commitId);
    }
  }

  /**
   * The COMPLETE owner-scoped revision set, deliberately not head-selected.
   *
   * Identity constraints and mentions are keyed views, so they head-rank in SQL.
   * Claims must not: D46/G3 requires the reader grant to be applied BEFORE
   * lineage head selection, so that a head a reader may not see cannot suppress
   * an older member of the same lineage that the reader may see. Pre-selecting
   * here would be owner-blind and would silently delete that older member for
   * every reader. Anything that wants "one live head per lineage" calls
   * `liveClaims` (owner view) or `project` (reader view) -- never `.claims`.
   */
  snapshot(ownerAccountId: string): GraphSnapshot {
    const head = this.db.query("SELECT sequence FROM graph_heads WHERE owner_account_id = ?").get(ownerAccountId) as { sequence: number } | null;
    const claims = (this.db.query("SELECT c.revision_id, c.placement_status, c.content_json, d.sequence AS commit_sequence FROM claim_revisions c JOIN derivation_commits d ON d.commit_id = c.commit_id WHERE c.owner_account_id = ? AND NOT EXISTS (SELECT 1 FROM claim_quarantine_records q WHERE q.owner_account_id = c.owner_account_id AND q.claim_revision_id = c.revision_id) ORDER BY d.sequence, c.revision_id").all(ownerAccountId) as { revision_id: string; placement_status: ClaimRevision["placement_status"]; content_json: string; commit_sequence: number }[])
      .map((row) => ({ revision_id: row.revision_id, placement_status: row.placement_status, claim: JSON.parse(row.content_json), commit_sequence: row.commit_sequence }));
    const entities = (this.db.query("SELECT revision_id, content_json FROM entity_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, entity: JSON.parse(row.content_json) }));
    const predicates = (this.db.query("SELECT revision_id, content_json FROM predicate_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, predicate: JSON.parse(row.content_json) }));
    const predicate_assertions = (this.db.query("SELECT revision_id, content_json FROM predicate_assertion_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, assertion: JSON.parse(row.content_json) }));
    const identity_constraints = (this.db.query("SELECT revision_id, content_json FROM (SELECT i.revision_id, i.content_json, i.owner_account_id, ROW_NUMBER() OVER (PARTITION BY i.constraint_id ORDER BY d.sequence DESC, i.rowid DESC) AS head_rank FROM identity_revisions i JOIN derivation_commits d ON d.commit_id = i.commit_id WHERE i.owner_account_id = ?) WHERE head_rank = 1 AND NOT EXISTS (SELECT 1 FROM identity_quarantine_records q WHERE q.owner_account_id = owner_account_id AND q.identity_revision_id = revision_id) ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, constraint: JSON.parse(row.content_json) }));
    const mentionRows = (this.db.query("SELECT m.revision_id, m.content_json, d.sequence AS commit_sequence FROM mention_revisions m JOIN derivation_commits d ON d.commit_id=m.commit_id WHERE m.owner_account_id = ? ORDER BY d.sequence, m.revision_id").all(ownerAccountId) as { revision_id: string; content_json: string; commit_sequence: number }[]);
    const latestMentions = new Map<string, { revision_id: string; mention: import("../../core/schema").Mention; commit_sequence: number }>();
    for (const row of mentionRows) { const mention = JSON.parse(row.content_json) as import("../../core/schema").Mention; latestMentions.set(mention.mention_id, { revision_id: row.revision_id, mention, commit_sequence: row.commit_sequence }); }
    const mentions = [...latestMentions.values()].sort((left, right) => compareStrings(left.revision_id, right.revision_id)).map(({ revision_id, mention }) => ({ revision_id, mention }));
    const identity_authorizations = (this.db.query("SELECT revision_id, content_json FROM identity_authorization_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, authorization: JSON.parse(row.content_json) }));
    const identity_support = (this.db.query("SELECT content_json FROM identity_support_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { content_json: string }[])
      .map((row) => JSON.parse(row.content_json));
    const events = (this.db.query("SELECT revision_id, content_json FROM event_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, event: JSON.parse(row.content_json) }));
    // Evidence is owner-scoped through its event. Old schemas did not persist an owner on evidence.
    // Preserve lexical result ordering to prove projection never relies on it;
    // `commit_sequence` is the sole evidence-head ordering authority.
    const evidence = (this.db.query("SELECT e.revision_id, e.content_json, d.sequence AS commit_sequence FROM evidence_revisions e JOIN derivation_commits d ON d.commit_id = e.commit_id WHERE e.event_revision_id IN (SELECT revision_id FROM event_revisions WHERE owner_account_id = ?) ORDER BY e.revision_id").all(ownerAccountId) as { revision_id: string; content_json: string; commit_sequence: number }[])
      .map((row) => ({ revision_id: row.revision_id, evidence: JSON.parse(row.content_json), commit_sequence: row.commit_sequence }));
    const adjacency = this.db.query("SELECT claim_revision_id, entity_id, role_slot_id FROM generated_adjacency WHERE claim_revision_id IN (SELECT revision_id FROM claim_revisions WHERE owner_account_id = ?) ORDER BY claim_revision_id, entity_id, role_slot_id").all(ownerAccountId) as GraphSnapshot["adjacency"];
    const source_local_roles = this.db.query("SELECT claim_revision_id, source_local_ref, role_slot_id FROM source_local_claim_roles WHERE claim_revision_id IN (SELECT revision_id FROM claim_revisions WHERE owner_account_id = ?) ORDER BY claim_revision_id, source_local_ref, role_slot_id").all(ownerAccountId) as NonNullable<GraphSnapshot["source_local_roles"]>;
    const fences = this.db.query("SELECT claim_revision_id, cause FROM claim_liveness_fences WHERE owner_account_id = ? ORDER BY claim_revision_id, cause").all(ownerAccountId) as { claim_revision_id: string; cause: LivenessFenceCause }[];
    return { owner_account_id: ownerAccountId, graph_generation: head?.sequence ?? 0, claims, entities, predicates, predicate_assertions, identity_constraints, mentions, identity_authorizations, identity_support, events, evidence,
      liveness_causes: { purged_claim_revision_ids: fences.filter((fence) => fence.cause === "purged").map((fence) => fence.claim_revision_id), forgotten_claim_revision_ids: fences.filter((fence) => fence.cause === "forgotten").map((fence) => fence.claim_revision_id) }, adjacency, source_local_roles, placement_artifacts: this.placementArtifacts(ownerAccountId) };
  }

  retrieve(request: RetrievalRequest): RetrievalResult { return retrieveCommittedGraph(this.snapshot(request.owner_account_id), request); }

  /** Owner view: exactly one live revision per `claim_lineage_id`. A reprojected
   * claim replaces its predecessor here rather than appearing beside it. */
  liveClaims(ownerAccountId: string): readonly CommittedClaim[] { return liveCommittedClaims(this.snapshot(ownerAccountId)); }

  /** Head-selection accounting. `canonical_revisions > live_canonical_heads` is
   * exactly the duplicate-live-head condition, which was previously invisible
   * because nothing counted revisions and lineages apart. */
  claimHeadCounts(ownerAccountId: string): { canonical_revisions: number; claim_lineages: number; live_claims: number; live_canonical_heads: number } {
    const snapshot = this.snapshot(ownerAccountId);
    const live = liveCommittedClaims(snapshot);
    return {
      canonical_revisions: snapshot.claims.filter((item) => item.placement_status === "canonical").length,
      claim_lineages: new Set(snapshot.claims.map((item) => item.claim.claim_lineage_id)).size,
      live_claims: live.length,
      live_canonical_heads: live.filter((item) => item.placement_status === "canonical").length,
    };
  }

  placementArtifacts(ownerAccountId: string): readonly PlacementArtifact[] {
    return (this.db.query("SELECT artifact_id, kind, provisional_revision_id, canonical_claim_revision_id, margin, risk_markers_json, unit_boundary_decision, scope_locality FROM placement_artifacts WHERE owner_account_id = ? ORDER BY artifact_id").all(ownerAccountId) as (Omit<PlacementArtifact, "risk_markers"> & { risk_markers_json: string })[])
      .map(({ risk_markers_json, ...artifact }) => ({ ...artifact, risk_markers: JSON.parse(risk_markers_json) as PlacementArtifact["risk_markers"] }));
  }

  /** Rebuild/audit path: re-project durable support and recheck every lineage
   * edge instead of trusting the authorization JSON embedded in a constraint. */
  auditIdentityAuthority(ownerAccountId: string): { authorizations: number; supports: number } {
    const supports = (this.db.query("SELECT s.content_json FROM identity_support_revisions s JOIN derivation_commits d ON d.commit_id = s.commit_id WHERE s.owner_account_id = ? ORDER BY d.sequence, s.rowid").all(ownerAccountId) as { content_json: string }[])
      .map((row) => JSON.parse(row.content_json) as import("../../core/resolve/identity-authority").ImmutableIdentitySupport);
    const supportByRef = new Map(supports.map((support) => [support.support_ref, support]));
    const claims = new Set((this.db.query("SELECT revision_id FROM claim_revisions WHERE owner_account_id = ?").all(ownerAccountId) as { revision_id: string }[]).map((row) => row.revision_id));
    const events = new Set((this.db.query("SELECT revision_id FROM event_revisions WHERE owner_account_id = ?").all(ownerAccountId) as { revision_id: string }[]).map((row) => row.revision_id));
    const evidence = (this.db.query("SELECT e.revision_id, e.content_json FROM evidence_revisions e WHERE e.event_revision_id IN (SELECT revision_id FROM event_revisions WHERE owner_account_id = ?)").all(ownerAccountId) as { revision_id: string; content_json: string }[])
      .map((row) => ({ revision_id: row.revision_id, evidence: JSON.parse(row.content_json) as { evidence_id: string; event_revision_id: string; source_independence_key: string } }));
    const authorizationRows = this.db.query("SELECT content_json FROM identity_authorization_revisions WHERE owner_account_id = ? AND lifecycle = 'active'").all(ownerAccountId) as { content_json: string }[];
    for (const row of authorizationRows) {
      const authorization = JSON.parse(row.content_json) as import("../../core/schema").IdentityAuthorization;
      if (authorization.support.kind !== "consolidation_adjudication") continue;
      for (const supportRef of authorization.support.support_refs) {
        const support = supportByRef.get(supportRef);
        const linkedEvidence = support && evidence.find((item) => item.revision_id === support.evidence_ref || item.evidence.evidence_id === support.evidence_ref);
        if (!support || support.owner_account_id !== ownerAccountId || !claims.has(support.claim_revision_id) || !linkedEvidence || linkedEvidence.evidence.source_independence_key !== support.source_independence_key || !events.has(linkedEvidence.evidence.event_revision_id)) {
          throw new GraphTransitionValidationError(`unresolvable durable identity support lineage: ${supportRef}`);
        }
      }
      const admitted = authorizeIdentity(authorization, { owner_account_id: ownerAccountId, endpoints: authorization.endpoints, relation: authorization.relation, evaluated_frontier: authorization.evaluated_frontier }, { owner_confirmations: [], producer_assertions: [], standing_policies: [], identity_support: supports });
      if (!admitted.authorized) throw new GraphTransitionValidationError(`inadmissible durable identity support set: ${admitted.reason}`);
    }
    return { authorizations: authorizationRows.length, supports: supportByRef.size };
  }

  /** Read before a session invokes models: changed later outputs must not collide. */
  findCommitByIdempotencyKey(idempotencyKey: string): { commit_id: string; sequence: number; input_version_digest: string } | null {
    return this.db.query("SELECT commit_id, sequence, input_version_digest FROM derivation_commits WHERE idempotency_key = ?").get(idempotencyKey) as { commit_id: string; sequence: number; input_version_digest: string } | null;
  }

  graphHead(ownerAccountId: string): { commit_id: string; sequence: number } | null {
    return this.db.query("SELECT commit_id, sequence FROM graph_heads WHERE owner_account_id = ?").get(ownerAccountId) as { commit_id: string; sequence: number } | null;
  }

  isProvisionalConsumed(provisionalRevisionId: string): boolean {
    return !!this.db.query("SELECT provisional_revision_id FROM consumed_markers WHERE provisional_revision_id = ?").get(provisionalRevisionId);
  }

  /** I8's append-only legacy overlay.  A row is retained only when it carries
   * typed endpoints plus a structurally supported authorization.  Unknown
   * lineage is quarantined by its whole producing transition, never guessed. */
  quarantineLegacyIdentity(policyVersion = "d48-identity-authority-v1"): { identity_records: number; claim_records: number } {
    const migrationId = `identity-quarantine:${policyVersion}`;
    const unsupported = this.db.query("SELECT i.revision_id, i.owner_account_id, i.commit_id, i.content_json FROM identity_revisions i WHERE NOT EXISTS (SELECT 1 FROM identity_quarantine_records q WHERE q.migration_id = ? AND q.identity_revision_id = i.revision_id)").all(migrationId) as { revision_id: string; owner_account_id: string; commit_id: string; content_json: string }[];
    let identityRecords = 0;
    let claimRecords = 0;
    const transaction = this.db.transaction(() => {
      for (const row of unsupported) {
        const constraint = JSON.parse(row.content_json) as import("../../core/schema").IdentityConstraint;
        const authorization = constraint.identity_authorization;
        const supported = !!constraint.endpoints && !!authorization && authorization.lifecycle === "active" && authorization.owner_account_id === constraint.owner_account_id && authorization.relation === constraint.relation && authorization.endpoints.every((endpoint) => constraint.endpoints!.some((candidate) => JSON.stringify(candidate) === JSON.stringify(endpoint)));
        if (supported) continue;
        const identityInsert = this.db.query("INSERT OR IGNORE INTO identity_quarantine_records VALUES (?, ?, ?, ?, ?, ?)").run(migrationId, row.owner_account_id, row.revision_id, "unsupported_identity", policyVersion, "legacy constraint lacks independently verifiable D48 authorization/lineage");
        identityRecords += identityInsert.changes;
        // A canonical placement emitted in the same untrusted transition is
        // causally ambiguous; keep it for audit but exclude it from retrieval.
        const claims = this.db.query("SELECT revision_id FROM claim_revisions WHERE commit_id = ? AND owner_account_id = ? AND placement_status = 'canonical'").all(row.commit_id, row.owner_account_id) as { revision_id: string }[];
        for (const claim of claims) {
          const claimInsert = this.db.query("INSERT OR IGNORE INTO claim_quarantine_records VALUES (?, ?, ?, ?, ?, ?)").run(migrationId, row.owner_account_id, claim.revision_id, "dependent_canonical_placement", policyVersion, `depends on unsupported identity transition ${row.commit_id}`);
          claimRecords += claimInsert.changes;
        }
      }
    });
    transaction();
    return { identity_records: identityRecords, claim_records: claimRecords };
  }

  mentions(ownerAccountId: string): readonly import("../../core/schema").Mention[] {
    return (this.db.query("SELECT content_json FROM mention_revisions WHERE owner_account_id = ? ORDER BY revision_id").all(ownerAccountId) as { content_json: string }[]).map((row) => JSON.parse(row.content_json));
  }

  counts(): Record<string, number> {
    const tables = ["claim_revisions", "entity_revisions", "identity_revisions", "event_revisions", "evidence_revisions", "mention_revisions", "identity_authorization_revisions", "identity_support_revisions", "coreference_support_revisions", "candidate_derivation_artifacts", "generated_adjacency", "consumed_markers", "placement_artifacts", "derivation_attempts", "derivation_commits", "graph_heads", "claim_liveness_fences", "identity_quarantine_records", "claim_quarantine_records"];
    return Object.fromEntries(tables.map((table) => [table, (this.db.query(`SELECT COUNT(*) AS count FROM ${table}`).get() as { count: number }).count]));
  }
}
