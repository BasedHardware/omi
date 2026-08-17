import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import { sha256CanonicalRedacted, type CanonicalJson } from "../../core/ledger";
import { compareStrings } from "../../core/order";
import type { GraphSnapshot } from "../../core/retrieve";
import type {
  CanonicalClaim, Entity, Evidence, IdentityAuthorization, IdentityConstraint,
  L1Event, Mention, Predicate, PredicateAssertion, ProvisionalClaim,
} from "../../core/schema";
import type { ImmutableIdentitySupport } from "../../core/resolve/identity-authority";
import type { PostgresTransactionPool } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

interface RevisionRow extends Record<string, unknown> {
  readonly revision_id: string;
  readonly revision_kind: string;
  readonly content_json: unknown;
  readonly content_hash: string;
  readonly commit_sequence: string | number | bigint;
  readonly placement_status: string | null;
  readonly head_rank: string | number | bigint;
}

interface AdjacencyRow extends Record<string, unknown> {
  readonly claim_revision_id: string;
  readonly entity_id: string;
  readonly role_slot_id: string;
}

const counter = (value: unknown): number => {
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value !== "string" && typeof value !== "number" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return parsed;
};

const content = (row: RevisionRow): Record<string, unknown> => {
  if (row.content_json === null || typeof row.content_json !== "object"
    || Array.isArray(row.content_json)) throw new PostgresRepositoryError("persistence_failed");
  const value = row.content_json as Record<string, unknown>;
  if (row.content_hash !== sha256CanonicalRedacted(value as CanonicalJson)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return value;
};

const textArray = (value: unknown): readonly string[] => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze([...value] as string[]);
};

const placementRiskMarkers = (
  value: unknown,
): readonly ("new_entity" | "resolved_pronoun" | "low_margin")[] => {
  const values = textArray(value);
  if (values.some((item) => !["new_entity", "resolved_pronoun", "low_margin"].includes(item))) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return values as readonly ("new_entity" | "resolved_pronoun" | "low_margin")[];
};

export interface PostgresAuthoritativeGraphSnapshotRepository {
  load(context: AuthorizedLedgerWriteContext): Promise<GraphSnapshot>;
  loadWithAttestation(context: AuthorizedLedgerWriteContext): Promise<Readonly<{
    snapshot: GraphSnapshot;
    db_now_epoch_seconds: number;
  }>>;
  loadCurrentParent(
    context: AuthorizedLedgerWriteContext,
  ): Promise<Readonly<{ kind: "found"; parent_commit: string | null }>>;
}

/**
 * Inert owner-internal reconstruction seam. It deliberately reuses the exact
 * write-authority transaction fence until a separately ratified read/rebuild
 * capability exists; it is not composed into an application route.
 */
export const createPostgresAuthoritativeGraphSnapshotRepository = (options: {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}): PostgresAuthoritativeGraphSnapshotRepository => {
  let repository: PostgresAuthoritativeGraphSnapshotRepository;
  repository = Object.freeze({
  load: async (context: AuthorizedLedgerWriteContext) =>
    (await repository.loadWithAttestation(context)).snapshot,
  loadCurrentParent: async (context: AuthorizedLedgerWriteContext) =>
    withAuthorizedSerializableConnectionTransaction(
    options.pool,
    context,
    async ({ authority, connection }) => {
      const rows = await connection.query<{
        commit_id: string | null;
        sequence: string | number | bigint;
      }>({
        name: "snapshot.graph_parent",
        text: `SELECT commit_id, sequence
               FROM omi_memory.memory_graph_heads
               WHERE account_id = $1`,
        values: [authority.account_id],
      });
      if (rows.length !== 1 || !rows[0]) {
        throw new PostgresRepositoryError("persistence_failed");
      }
      const sequence = counter(rows[0].sequence);
      const parent = rows[0].commit_id;
      if ((sequence === 0 && parent !== null)
        || (sequence > 0 && (typeof parent !== "string" || parent.length === 0))) {
        throw new PostgresRepositoryError("persistence_failed");
      }
      return Object.freeze({ kind: "found" as const, parent_commit: parent });
    },
    options.observability,
  ),
  loadWithAttestation: async (context: AuthorizedLedgerWriteContext) =>
    withAuthorizedSerializableConnectionTransaction(
    options.pool,
    context,
    async ({ authority, connection, dbNowEpochSeconds }) => {
      const accountId = authority.account_id;
      const heads = await connection.query<{ sequence: string | number | bigint }>({
        name: "snapshot.graph_head",
        text: `SELECT sequence FROM omi_memory.memory_graph_heads WHERE account_id = $1`,
        values: [accountId],
      });
      if (heads.length !== 1 || !heads[0]) throw new PostgresRepositoryError("persistence_failed");

      const rows = await connection.query<RevisionRow>({
        name: "snapshot.revisions",
        text: `
SELECT r.revision_id, r.revision_kind, r.content_json, r.content_hash,
       c.sequence AS commit_sequence, cr.placement_status,
       CASE
         WHEN r.revision_kind = 'identity' THEN
           ROW_NUMBER() OVER (
             PARTITION BY ir.constraint_id ORDER BY c.sequence DESC, r.revision_id DESC
           )
         WHEN r.revision_kind = 'mention' THEN
           ROW_NUMBER() OVER (
             PARTITION BY mr.mention_id ORDER BY c.sequence DESC, r.revision_id DESC
           )
         ELSE 1
       END AS head_rank
FROM omi_memory.memory_revisions AS r
JOIN omi_memory.memory_derivation_commits AS c
  ON c.account_id = r.account_id AND c.commit_id = r.commit_id
LEFT JOIN omi_memory.memory_claim_revisions AS cr
  ON cr.account_id = r.account_id AND cr.revision_id = r.revision_id
LEFT JOIN omi_memory.memory_identity_revisions AS ir
  ON ir.account_id = r.account_id AND ir.revision_id = r.revision_id
LEFT JOIN omi_memory.memory_mention_revisions AS mr
  ON mr.account_id = r.account_id AND mr.revision_id = r.revision_id
WHERE r.account_id = $1
ORDER BY c.sequence, r.revision_id
`,
        values: [accountId],
      });

      const claims: GraphSnapshot["claims"] extends readonly (infer Item)[] ? Item[] : never = [];
      const entities: NonNullable<GraphSnapshot["entities"]>[number][] = [];
      const predicates: NonNullable<GraphSnapshot["predicates"]>[number][] = [];
      const predicateAssertions: NonNullable<GraphSnapshot["predicate_assertions"]>[number][] = [];
      const identities: NonNullable<GraphSnapshot["identity_constraints"]>[number][] = [];
      const mentions: NonNullable<GraphSnapshot["mentions"]>[number][] = [];
      const authorizations: NonNullable<GraphSnapshot["identity_authorizations"]>[number][] = [];
      const events: NonNullable<GraphSnapshot["events"]>[number][] = [];
      const evidence: NonNullable<GraphSnapshot["evidence"]>[number][] = [];
      for (const row of rows) {
        const value = content(row);
        if ("owner_account_id" in value && value["owner_account_id"] !== accountId) {
          throw new PostgresRepositoryError("persistence_failed");
        }
        const revisionId = row.revision_id;
        const sequence = counter(row.commit_sequence);
        switch (row.revision_kind) {
          case "claim":
            if (!["canonical", "consumed", "provisional_unresolved_subject", "provisional_abstained"]
              .includes(row.placement_status ?? "")) throw new PostgresRepositoryError("persistence_failed");
            claims.push({ revision_id: revisionId, claim: value as unknown as CanonicalClaim | ProvisionalClaim,
              placement_status: row.placement_status as never, commit_sequence: sequence });
            break;
          case "entity": entities.push({ revision_id: revisionId, entity: value as unknown as Entity }); break;
          case "predicate": predicates.push({ revision_id: revisionId, predicate: value as unknown as Predicate }); break;
          case "predicate_assertion": predicateAssertions.push({ revision_id: revisionId, assertion: value as unknown as PredicateAssertion }); break;
          case "identity": if (counter(row.head_rank) === 1) identities.push({ revision_id: revisionId, constraint: value as unknown as IdentityConstraint }); break;
          case "mention": if (counter(row.head_rank) === 1) mentions.push({ revision_id: revisionId, mention: value as unknown as Mention }); break;
          case "identity_authorization": authorizations.push({ revision_id: revisionId, authorization: value as unknown as IdentityAuthorization }); break;
          case "event": events.push({ revision_id: revisionId, event: value as unknown as L1Event }); break;
          case "evidence": evidence.push({ revision_id: revisionId, evidence: value as unknown as Evidence, commit_sequence: sequence }); break;
          case "coreference_support": break;
          default: throw new PostgresRepositoryError("persistence_failed");
        }
      }

      const supportRows = await connection.query<{ content_json: unknown; content_hash: string }>({
        name: "snapshot.identity_support",
        text: `SELECT content_json, content_hash FROM omi_memory.memory_identity_support
               WHERE account_id = $1 ORDER BY support_ref`,
        values: [accountId],
      });
      const identitySupport = supportRows.map((row) => {
        const revision: RevisionRow = {
          revision_id: "support", revision_kind: "support", content_json: row.content_json,
          content_hash: row.content_hash, commit_sequence: 0, placement_status: null, head_rank: 1,
        };
        return content(revision) as unknown as ImmutableIdentitySupport;
      });
      const adjacencyRows = await connection.query<AdjacencyRow>({
        name: "snapshot.adjacency",
        text: `SELECT claim_revision_id, entity_id, role_slot_id
               FROM omi_memory.memory_generated_adjacency WHERE account_id = $1
               ORDER BY claim_revision_id, entity_id, role_slot_id`,
        values: [accountId],
      });
      const adjacency: GraphSnapshot["adjacency"] = adjacencyRows.map((row) => Object.freeze({
        claim_revision_id: row.claim_revision_id,
        entity_id: row.entity_id,
        role_slot_id: row.role_slot_id,
      }));
      const sourceLocalRoles = await connection.query<NonNullable<GraphSnapshot["source_local_roles"]>[number]>({
        name: "snapshot.source_local_roles",
        text: `SELECT claim_revision_id, source_local_ref, role_slot_id
               FROM omi_memory.memory_source_local_claim_roles WHERE account_id = $1
               ORDER BY claim_revision_id, source_local_ref, role_slot_id`,
        values: [accountId],
      });
      const fences = await connection.query<{ claim_revision_id: string; cause: "purged" | "forgotten" }>({
        name: "snapshot.liveness",
        text: `SELECT claim_revision_id, cause FROM omi_memory.memory_claim_liveness_fences
               WHERE account_id = $1 ORDER BY claim_revision_id, cause`,
        values: [accountId],
      });
      const artifactRows = await connection.query<{
        artifact_id: string; artifact_kind: "confirmation_queue" | "abstention_set" | "auto_placement_log";
        provisional_revision_id: string; canonical_claim_revision_id: string | null;
        margin: "low" | "medium" | "high" | null; risk_markers: unknown;
        unit_boundary_decision: "accept_ltm" | "abstain"; scope_locality: "durable" | "source_local" | null;
      }>({
        name: "snapshot.placement_artifacts",
        text: `SELECT artifact_id, artifact_kind, provisional_revision_id,
                      canonical_claim_revision_id, margin, risk_markers,
                      unit_boundary_decision, scope_locality
               FROM omi_memory.memory_placement_artifacts WHERE account_id = $1
               ORDER BY artifact_id`,
        values: [accountId],
      });
      const placementArtifacts = artifactRows.map((row) => Object.freeze({
        artifact_id: row.artifact_id, kind: row.artifact_kind,
        provisional_revision_id: row.provisional_revision_id,
        canonical_claim_revision_id: row.canonical_claim_revision_id,
        margin: row.margin, risk_markers: placementRiskMarkers(row.risk_markers),
        unit_boundary_decision: row.unit_boundary_decision,
        scope_locality: row.scope_locality,
      }));
      const byRevision = <Item extends { readonly revision_id: string }>(items: Item[]): Item[] =>
        items.sort((left, right) => compareStrings(left.revision_id, right.revision_id));

      const snapshot = Object.freeze({
        owner_account_id: accountId, graph_generation: counter(heads[0].sequence),
        claims: Object.freeze(claims), entities: Object.freeze(byRevision(entities)),
        predicates: Object.freeze(byRevision(predicates)), predicate_assertions: Object.freeze(byRevision(predicateAssertions)),
        identity_constraints: Object.freeze(byRevision(identities)), mentions: Object.freeze(byRevision(mentions)),
        identity_authorizations: Object.freeze(byRevision(authorizations)), identity_support: Object.freeze(identitySupport),
        events: Object.freeze(byRevision(events)), evidence: Object.freeze(byRevision(evidence)),
        liveness_causes: Object.freeze({
          purged_claim_revision_ids: Object.freeze(fences.filter((row) => row.cause === "purged").map((row) => row.claim_revision_id)),
          forgotten_claim_revision_ids: Object.freeze(fences.filter((row) => row.cause === "forgotten").map((row) => row.claim_revision_id)),
        }),
        adjacency: Object.freeze([...adjacency]), source_local_roles: Object.freeze([...sourceLocalRoles]),
        placement_artifacts: Object.freeze(placementArtifacts),
      } satisfies GraphSnapshot);
      return Object.freeze({ snapshot, db_now_epoch_seconds: dbNowEpochSeconds });
    },
    options.observability,
  ),
  });
  return repository;
};
