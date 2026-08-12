import {
  defineAuthoritativeLedgerRepository,
  type AuthoritativeLedgerAppend,
  type AuthoritativeLedgerAppendOutcome,
  type AuthoritativeLedgerRepository,
} from "../../apps/service/stores/authoritative-ledger-repository";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import {
  sha256CanonicalRedacted,
  type AtomicGraphTransition,
  type CanonicalJson,
  type GraphRevision,
} from "../../core/ledger";
import { identityConstraintConflicts } from "../../core/resolve/entities";
import type { IdentityConstraint } from "../../core/schema";
import type { CheckedOutPostgresConnection, PostgresTransactionPool, SqlValue } from "./connection";
import {
  PostgresRepositoryError,
  withAuthorizedSerializableConnectionTransaction,
  type PostgresTransactionObservability,
} from "./transaction";

interface ReceiptRow extends Record<string, unknown> {
  readonly request_digest: string;
  readonly state: "reserved" | "finalized";
  readonly commit_id: string | null;
  readonly sequence: string | number | bigint | null;
  readonly attempt_id: string | null;
  readonly parent_commit_id: string | null;
  readonly input_digest: string | null;
  readonly input_version_digest: string | null;
  readonly output_digest: string | null;
  readonly success_kind: string | null;
  readonly origin_kind: string | null;
  readonly formation_work_id: string | null;
  readonly non_formation_reason: string | null;
  readonly record_json: unknown;
}

interface HeadRow extends Record<string, unknown> {
  readonly commit_id: string | null;
  readonly sequence: string | number | bigint;
}

const supportedReason = new Set([
  "repair", "manual_liveness", "historical_replay",
] as const);
const jsonBytes = (value: unknown): Uint8Array => {
  const encoded = JSON.stringify(value);
  if (encoded === undefined) throw new PostgresRepositoryError("transition_invalid");
  return new TextEncoder().encode(encoded);
};

const revisionContent = (revision: GraphRevision): CanonicalJson =>
  (revision.kind === "claim" ? revision.claim
    : revision.kind === "entity" ? revision.entity
      : revision.kind === "predicate" ? revision.predicate
        : revision.kind === "predicate_assertion" ? revision.assertion
          : revision.kind === "identity" ? revision.constraint
            : revision.kind === "event" ? revision.event
              : revision.kind === "evidence" ? revision.evidence
                : revision.kind === "mention" ? revision.mention
                  : revision.kind === "identity_authorization" ? revision.authorization
                    : revision.support) as unknown as CanonicalJson;

const executeRequired = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  text: string,
  values: readonly SqlValue[],
): Promise<void> => {
  const result = await connection.execute({ name, text, values });
  if (result.rowCount !== 1) throw new PostgresRepositoryError("persistence_failed");
};

const ensureIdentity = async (
  connection: CheckedOutPostgresConnection,
  name: string,
  table: string,
  columns: readonly string[],
  values: readonly SqlValue[],
): Promise<void> => {
  const placeholders = columns.map((_, index) => `$${index + 1}`).join(", ");
  const result = await connection.execute({
    name,
    text: `INSERT INTO omi_memory.${table} (${columns.join(", ")}) VALUES (${placeholders}) ON CONFLICT DO NOTHING`,
    values,
  });
  if (result.rowCount !== 0 && result.rowCount !== 1) {
    throw new PostgresRepositoryError("persistence_failed");
  }
};

const safeCounter = (value: unknown): number => {
  if (typeof value === "string" && !/^(?:0|[1-9][0-9]*)$/.test(value)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  if (typeof value !== "string" && typeof value !== "number" && typeof value !== "bigint") {
    throw new PostgresRepositoryError("persistence_failed");
  }
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < 0) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return number;
};

const assertQualificationTransition = (request: AuthoritativeLedgerAppend): void => {
  const transition = request.transition;
  const commit = transition.derivation.commit;
  if (request.origin.kind !== "non_formation" || !supportedReason.has(request.origin.reason as never)
    || commit.success_kind !== "successful_empty"
    || commit.input_revision_ids.length !== 0
    || commit.output_revision_ids.length !== 0
    || commit.output_revisions.length !== 0
    || transition.revisions.length !== 0
    || transition.adjacency.length !== 0
    || transition.artifacts.length !== 0
    || transition.placement.results.length !== 0
    || Object.keys(transition.placement.allocations).length !== 0
    || transition.committed_revisions !== undefined
    || transition.identity_authority_context !== undefined
    || transition.derived_identity_support !== undefined) {
    throw new PostgresRepositoryError("transition_invalid");
  }
};

interface WitnessRow extends Record<string, unknown> {
  readonly content_hash: string;
  readonly lifecycle: string | null;
  readonly head_revision_id: string | null;
}

const verifyCommittedWitnesses = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  transition: AtomicGraphTransition,
): Promise<void> => {
  const allowed = new Set<GraphRevision["kind"]>([
    "identity_authorization", "mention", "claim", "evidence", "event",
  ]);
  for (const witness of transition.committed_revisions ?? []) {
    if (!allowed.has(witness.kind)) continue;
    const rows = await connection.query<WitnessRow>({
      name: "ledger.witness_verify",
      text: `
SELECT r.content_hash,
       CASE WHEN r.revision_kind = 'identity_authorization' THEN ia.lifecycle ELSE NULL END AS lifecycle,
       CASE WHEN r.revision_kind = 'identity_authorization' THEN (
         SELECT ia2.revision_id
         FROM omi_memory.memory_identity_authorization_revisions AS ia2
         JOIN omi_memory.memory_revisions AS r2
           ON r2.account_id = ia2.account_id AND r2.revision_id = ia2.revision_id
         JOIN omi_memory.memory_derivation_commits AS c2
           ON c2.account_id = r2.account_id AND c2.commit_id = r2.commit_id
         WHERE ia2.account_id = ia.account_id
           AND ia2.authorization_id = ia.authorization_id
         ORDER BY c2.sequence DESC, ia2.revision_id DESC
         LIMIT 1
       ) ELSE NULL END AS head_revision_id
FROM omi_memory.memory_revisions AS r
LEFT JOIN omi_memory.memory_identity_authorization_revisions AS ia
  ON ia.account_id = r.account_id AND ia.revision_id = r.revision_id
WHERE r.account_id = $1 AND r.revision_id = $2 AND r.revision_kind = $3
`,
      values: [accountId, witness.revision_id, witness.kind],
    });
    const row = rows[0];
    if (rows.length !== 1 || !row
      || row.content_hash !== sha256CanonicalRedacted(revisionContent(witness))) {
      throw new PostgresRepositoryError("transition_invalid");
    }
    if (witness.kind === "identity_authorization"
      && (row.lifecycle !== "active" || row.head_revision_id !== witness.revision_id)) {
      throw new PostgresRepositoryError("transition_invalid");
    }
  }
};

interface IdentityClosureRow extends Record<string, unknown> {
  readonly content_json: unknown;
}

const verifyIdentityClosure = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  transition: AtomicGraphTransition,
): Promise<void> => {
  const incoming = transition.revisions
    .filter((revision): revision is Extract<GraphRevision, { kind: "identity" }> => revision.kind === "identity")
    .map((revision) => revision.constraint);
  if (incoming.length === 0) return;
  const rows = await connection.query<IdentityClosureRow>({
    name: "ledger.identity_closure",
    text: `
SELECT content_json
FROM (
  SELECT r.content_json, i.constraint_id,
         ROW_NUMBER() OVER (
           PARTITION BY i.constraint_id ORDER BY c.sequence DESC, i.revision_id DESC
         ) AS head_rank
  FROM omi_memory.memory_identity_revisions AS i
  JOIN omi_memory.memory_revisions AS r
    ON r.account_id = i.account_id AND r.revision_id = i.revision_id
  JOIN omi_memory.memory_derivation_commits AS c
    ON c.account_id = r.account_id AND c.commit_id = r.commit_id
  WHERE i.account_id = $1
) AS ranked
WHERE head_rank = 1
ORDER BY constraint_id
`,
    values: [accountId],
  });
  const closure: IdentityConstraint[] = [];
  for (const row of rows) {
    if (row.content_json === null || typeof row.content_json !== "object" || Array.isArray(row.content_json)) {
      throw new PostgresRepositoryError("persistence_failed");
    }
    closure.push(row.content_json as IdentityConstraint);
  }
  for (const constraint of incoming) {
    const prior = closure.findIndex((item) => item.constraint_id === constraint.constraint_id);
    if (prior >= 0) closure.splice(prior, 1);
    if (identityConstraintConflicts(closure, constraint)) {
      throw new PostgresRepositoryError("transition_invalid");
    }
    closure.push(constraint);
  }
};

const replayOutcome = (
  row: ReceiptRow,
  request: AuthoritativeLedgerAppend,
): AuthoritativeLedgerAppendOutcome => {
  if (row.request_digest !== request.append_attempt.request_digest) {
    return Object.freeze({ kind: "idempotency_conflict" as const });
  }
  const commit = request.transition.derivation.commit;
  const expectedRecord = { ...commit, sequence: safeCounter(row.sequence) };
  const expectedFormationWorkId = request.origin.kind === "formation"
    ? request.origin.outcome.work_id : null;
  const expectedNonFormationReason = request.origin.kind === "non_formation"
    ? request.origin.reason : null;
  if (row.state !== "finalized" || typeof row.commit_id !== "string" || row.commit_id.length === 0
    || row.sequence === null
    || row.commit_id !== commit.commit_id
    || row.attempt_id !== commit.attempt_id
    || row.parent_commit_id !== commit.parent_commit
    || row.input_digest !== commit.input_digest
    || row.input_version_digest !== commit.input_version_digest
    || row.output_digest !== commit.output_digest
    || row.success_kind !== commit.success_kind
    || row.origin_kind !== request.origin.kind
    || row.formation_work_id !== expectedFormationWorkId
    || row.non_formation_reason !== expectedNonFormationReason
    || row.record_json === null || typeof row.record_json !== "object" || Array.isArray(row.record_json)
    || sha256CanonicalRedacted(row.record_json as CanonicalJson)
      !== sha256CanonicalRedacted(expectedRecord as unknown as CanonicalJson)) {
    throw new PostgresRepositoryError("persistence_failed");
  }
  return Object.freeze({
    kind: "replayed" as const,
    commit_id: row.commit_id,
    sequence: safeCounter(row.sequence),
  });
};

const persistDerivationInputs = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  commitId: string,
  transition: AtomicGraphTransition,
): Promise<void> => {
  for (let ordinal = 0; ordinal < transition.derivation.attempt.input_revisions.length; ordinal += 1) {
    const input = transition.derivation.attempt.input_revisions[ordinal]!;
    await executeRequired(connection, "ledger.input_insert", `
INSERT INTO omi_memory.memory_derivation_inputs
  (account_id, commit_id, ordinal, input_ref, content_hash)
VALUES ($1, $2, $3, $4, $5)
`, [accountId, commitId, ordinal, input.revision_id, input.content_hash]);
  }
};

const persistRevisionRoots = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  revisions: readonly GraphRevision[],
): Promise<void> => {
  for (const revision of revisions) {
    if (revision.kind === "event") {
      await ensureIdentity(connection, "ledger.event_identity", "memory_event_identities",
        ["account_id", "event_id"], [accountId, revision.event.event_id]);
    } else if (revision.kind === "evidence") {
      await ensureIdentity(connection, "ledger.evidence_identity", "memory_evidence_identities",
        ["account_id", "evidence_id"], [accountId, revision.evidence.evidence_id]);
    } else if (revision.kind === "claim") {
      await ensureIdentity(connection, "ledger.claim_lineage", "memory_claim_lineages",
        ["account_id", "claim_lineage_id"], [accountId, revision.claim.claim_lineage_id]);
    } else if (revision.kind === "entity") {
      await ensureIdentity(connection, "ledger.entity_identity", "memory_entity_identities",
        ["account_id", "entity_id"], [accountId, revision.entity.entity_id]);
    } else if (revision.kind === "predicate") {
      const identityVersion = revision.predicate.identity_version ?? "name-slots-v1";
      const inserted = await connection.execute({
        name: "ledger.predicate_identity",
        text: `
INSERT INTO omi_memory.memory_predicate_identities
  (account_id, predicate_id, identity_version)
VALUES ($1, $2, $3)
ON CONFLICT DO NOTHING
`,
        values: [accountId, revision.predicate.predicate_id, identityVersion],
      });
      if (inserted.rowCount === 0) {
        const rows = await connection.query<{ identity_version: string }>({
          name: "ledger.predicate_identity_verify",
          text: `
SELECT identity_version
FROM omi_memory.memory_predicate_identities
WHERE account_id = $1 AND predicate_id = $2
`,
          values: [accountId, revision.predicate.predicate_id],
        });
        if (rows.length !== 1 || rows[0]?.identity_version !== identityVersion) {
          throw new PostgresRepositoryError("transition_invalid");
        }
      } else if (inserted.rowCount !== 1) {
        throw new PostgresRepositoryError("persistence_failed");
      }
    } else if (revision.kind === "identity_authorization") {
      await ensureIdentity(connection, "ledger.authorization_identity", "memory_identity_authorization_identities",
        ["account_id", "authorization_id"], [accountId, revision.authorization.authorization_id]);
      if (revision.authorization.superseded_by !== null) {
        await ensureIdentity(connection, "ledger.authorization_superseding_identity", "memory_identity_authorization_identities",
          ["account_id", "authorization_id"], [accountId, revision.authorization.superseded_by]);
      }
    }
  }
};

const persistGenericRevisions = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  commitId: string,
  schemaVersion: string,
  revisions: readonly GraphRevision[],
): Promise<void> => {
  for (const revision of revisions) {
    const content = revisionContent(revision);
    await executeRequired(connection, "ledger.revision_insert", `
INSERT INTO omi_memory.memory_revisions
  (account_id, revision_id, revision_kind, commit_id, schema_version,
   content_json, content_hash)
VALUES ($1, $2, $3, $4, $5,
        convert_from($6::bytea, 'UTF8')::jsonb, $7)
`, [
      accountId, revision.revision_id, revision.kind, commitId, schemaVersion,
      jsonBytes(content), sha256CanonicalRedacted(content),
    ]);
  }
};

const persistPrimaryRevisionSubtypes = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  revisions: readonly GraphRevision[],
): Promise<void> => {
  const rank: Readonly<Record<GraphRevision["kind"], number>> = {
    event: 0, evidence: 1, claim: 2, entity: 3, predicate: 4,
    predicate_assertion: 5, identity_authorization: 6, mention: 7,
    coreference_support: 8, identity: 9,
  };
  for (const revision of [...revisions].sort((left, right) => rank[left.kind] - rank[right.kind])) {
    if (revision.kind === "event") {
      await executeRequired(connection, "ledger.event_revision_insert", `
INSERT INTO omi_memory.memory_event_revisions
  (account_id, revision_id, event_id, event_revision_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, revision.event.event_id, revision.event.event_revision_id]);
    } else if (revision.kind === "evidence") {
      await executeRequired(connection, "ledger.evidence_revision_insert", `
INSERT INTO omi_memory.memory_evidence_revisions
  (account_id, revision_id, evidence_id, event_revision_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, revision.evidence.evidence_id, revision.evidence.event_revision_id]);
    } else if (revision.kind === "claim") {
      await executeRequired(connection, "ledger.claim_revision_insert", `
INSERT INTO omi_memory.memory_claim_revisions
  (account_id, revision_id, claim_lineage_id, claim_revision_id,
   canonical_claim_id, lifecycle, placement_status)
VALUES ($1, $2, $3, $4, $5, $6, $7)
`, [
        accountId, revision.revision_id, revision.claim.claim_lineage_id,
        revision.claim.claim_revision_id,
        revision.claim.lifecycle === "canonical" ? revision.claim.canonical_claim_id : null,
        revision.claim.lifecycle, revision.placement_status,
      ]);
    } else if (revision.kind === "entity") {
      await executeRequired(connection, "ledger.entity_revision_insert", `
INSERT INTO omi_memory.memory_entity_revisions
  (account_id, revision_id, entity_id, entity_revision_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, revision.entity.entity_id, revision.entity.entity_revision_id]);
    } else if (revision.kind === "predicate") {
      await executeRequired(connection, "ledger.predicate_revision_insert", `
INSERT INTO omi_memory.memory_predicate_revisions
  (account_id, revision_id, predicate_id, predicate_revision_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, revision.predicate.predicate_id, revision.predicate.predicate_revision_id]);
    } else if (revision.kind === "predicate_assertion") {
      await executeRequired(connection, "ledger.predicate_assertion_insert", `
INSERT INTO omi_memory.memory_predicate_assertion_revisions
  (account_id, revision_id, assertion_id, predicate_id,
   target_predicate_id, supersedes_assertion_id)
VALUES ($1, $2, $3, $4, $5, $6)
`, [
        accountId, revision.revision_id, revision.assertion.assertion_id,
        revision.assertion.predicate_id, revision.assertion.target_predicate_id,
        revision.assertion.supersedes_assertion_id,
      ]);
    }
  }
};

const persistAuthorizationAndMentionSubtypes = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  revisions: readonly GraphRevision[],
): Promise<void> => {
  for (const revision of revisions) {
    if (revision.kind !== "identity_authorization") continue;
    await executeRequired(connection, "ledger.authorization_revision_insert", `
INSERT INTO omi_memory.memory_identity_authorization_revisions
  (account_id, revision_id, authorization_id, lifecycle,
   superseded_by_authorization_id)
VALUES ($1, $2, $3, $4, $5)
`, [
      accountId, revision.revision_id, revision.authorization.authorization_id,
      revision.authorization.lifecycle, revision.authorization.superseded_by,
    ]);
    for (let ordinal = 0; ordinal < revision.authorization.endpoints.length; ordinal += 1) {
      const endpoint = revision.authorization.endpoints[ordinal]!;
      if (endpoint.kind !== "entity") continue;
      await executeRequired(connection, "ledger.authorization_entity_endpoint_insert", `
INSERT INTO omi_memory.memory_identity_authorization_entity_endpoints
  (account_id, authorization_revision_id, endpoint_ordinal, entity_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, ordinal, endpoint.entity_id]);
    }
  }
  for (const revision of revisions) {
    if (revision.kind !== "mention") continue;
    await executeRequired(connection, "ledger.mention_revision_insert", `
INSERT INTO omi_memory.memory_mention_revisions
  (account_id, revision_id, mention_id, claim_revision_id, evidence_id, entity_id)
VALUES ($1, $2, $3, $4, $5, $6)
`, [
      accountId, revision.revision_id, revision.mention.mention_id,
      revision.mention.claim_revision_id, revision.mention.evidence_id,
      revision.mention.entity_id,
    ]);
  }
  for (const revision of revisions) {
    if (revision.kind !== "coreference_support") continue;
    await executeRequired(connection, "ledger.coreference_revision_insert", `
INSERT INTO omi_memory.memory_coreference_support_revisions
  (account_id, revision_id, coreference_support_id,
   antecedent_mention_id, anaphor_mention_id)
VALUES ($1, $2, $3, $4, $5)
`, [
      accountId, revision.revision_id, revision.support.coreference_support_id,
      revision.support.antecedent_mention_id, revision.support.anaphor_mention_id,
    ]);
    for (let ordinal = 0; ordinal < revision.support.evidence_refs.length; ordinal += 1) {
      await executeRequired(connection, "ledger.coreference_evidence_insert", `
INSERT INTO omi_memory.memory_coreference_support_evidence_refs
  (account_id, coreference_support_revision_id, evidence_ordinal, evidence_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, ordinal, revision.support.evidence_refs[ordinal]!]);
    }
  }
};

const persistIdentitySupportAndConstraints = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  commitId: string,
  schemaVersion: string,
  transition: AtomicGraphTransition,
): Promise<void> => {
  const allRevisions = [...transition.revisions, ...(transition.committed_revisions ?? [])];
  const evidence = allRevisions.filter(
    (revision): revision is Extract<GraphRevision, { kind: "evidence" }> => revision.kind === "evidence",
  );
  const authorizations = allRevisions.filter(
    (revision): revision is Extract<GraphRevision, { kind: "identity_authorization" }> => revision.kind === "identity_authorization",
  );
  const supports = transition.derived_identity_support ?? [];
  for (const support of supports) {
    const linkedEvidence = evidence.find((revision) =>
      revision.revision_id === support.evidence_ref
      || revision.evidence.evidence_id === support.evidence_ref);
    if (!linkedEvidence) throw new PostgresRepositoryError("transition_invalid");
    const durableSupport = {
      support_ref: support.support_ref,
      owner_account_id: support.owner_account_id,
      evidence_ref: support.evidence_ref,
      claim_revision_id: support.claim_revision_id,
      source_independence_key: support.source_independence_key,
      support_origin: support.support_origin ?? "independent",
    } as const;
    await executeRequired(connection, "ledger.identity_support_insert", `
INSERT INTO omi_memory.memory_identity_support
  (account_id, support_ref, claim_revision_id, evidence_revision_id,
   event_revision_id, source_independence_key, support_origin, commit_id,
   schema_version, content_json, content_hash)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
        convert_from($10::bytea, 'UTF8')::jsonb, $11)
`, [
      accountId, support.support_ref, support.claim_revision_id,
      linkedEvidence.revision_id, linkedEvidence.evidence.event_revision_id,
      support.source_independence_key, support.support_origin ?? "independent",
      commitId, schemaVersion, jsonBytes(durableSupport),
      sha256CanonicalRedacted(durableSupport as unknown as CanonicalJson),
    ]);
  }
  for (const revision of transition.revisions) {
    if (revision.kind !== "identity_authorization"
      || revision.authorization.support.kind !== "consolidation_adjudication") continue;
    for (let ordinal = 0; ordinal < revision.authorization.support.support_refs.length; ordinal += 1) {
      await executeRequired(connection, "ledger.authorization_support_insert", `
INSERT INTO omi_memory.memory_identity_authorization_support
  (account_id, authorization_revision_id, support_ordinal, support_ref)
VALUES ($1, $2, $3, $4)
`, [
        accountId, revision.revision_id, ordinal,
        revision.authorization.support.support_refs[ordinal]!,
      ]);
    }
  }
  for (const revision of transition.revisions) {
    if (revision.kind !== "identity") continue;
    const authorizationId = revision.constraint.identity_authorization?.authorization_id;
    const authorizationRevision = authorizations.find(
      (candidate) => candidate.authorization.authorization_id === authorizationId,
    );
    if (!authorizationRevision) throw new PostgresRepositoryError("transition_invalid");
    await executeRequired(connection, "ledger.identity_revision_insert", `
INSERT INTO omi_memory.memory_identity_revisions
  (account_id, revision_id, constraint_id, authorization_revision_id)
VALUES ($1, $2, $3, $4)
`, [
      accountId, revision.revision_id, revision.constraint.constraint_id,
      authorizationRevision.revision_id,
    ]);
    for (let ordinal = 0; ordinal < (revision.constraint.endpoints?.length ?? 0); ordinal += 1) {
      const endpoint = revision.constraint.endpoints![ordinal]!;
      if (endpoint.kind !== "entity") continue;
      await executeRequired(connection, "ledger.identity_entity_endpoint_insert", `
INSERT INTO omi_memory.memory_identity_constraint_entity_endpoints
  (account_id, identity_revision_id, endpoint_ordinal, entity_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, ordinal, endpoint.entity_id]);
    }
  }
};

const persistClaimRelationsAndArtifacts = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  commitId: string,
  transition: AtomicGraphTransition,
): Promise<void> => {
  for (const revision of transition.revisions) {
    if (revision.kind !== "claim") continue;
    for (let ordinal = 0; ordinal < revision.claim.evidence_refs.length; ordinal += 1) {
      await executeRequired(connection, "ledger.claim_evidence_insert", `
INSERT INTO omi_memory.memory_claim_evidence_refs
  (account_id, claim_revision_id, evidence_ordinal, evidence_id)
VALUES ($1, $2, $3, $4)
`, [accountId, revision.revision_id, ordinal, revision.claim.evidence_refs[ordinal]!]);
    }
    if (revision.claim.lifecycle === "canonical") {
      for (let ordinal = 0; ordinal < revision.claim.source_provisional_revision_ids.length; ordinal += 1) {
        await executeRequired(connection, "ledger.claim_source_provisional_insert", `
INSERT INTO omi_memory.memory_claim_source_provisionals
  (account_id, canonical_claim_revision_id, source_ordinal,
   source_provisional_revision_id)
VALUES ($1, $2, $3, $4)
`, [
          accountId, revision.revision_id, ordinal,
          revision.claim.source_provisional_revision_ids[ordinal]!,
        ]);
      }
      for (let ordinal = 0; ordinal < (revision.claim.supersedes_revision_ids?.length ?? 0); ordinal += 1) {
        await executeRequired(connection, "ledger.claim_supersession_insert", `
INSERT INTO omi_memory.memory_claim_supersessions
  (account_id, claim_revision_id, supersession_ordinal,
   superseded_claim_revision_id)
VALUES ($1, $2, $3, $4)
`, [
          accountId, revision.revision_id, ordinal,
          revision.claim.supersedes_revision_ids![ordinal]!,
        ]);
      }
    }
    if (revision.claim.predicate_id !== undefined) {
      await executeRequired(connection, "ledger.claim_predicate_insert", `
INSERT INTO omi_memory.memory_claim_predicate_refs
  (account_id, claim_revision_id, predicate_id)
VALUES ($1, $2, $3)
`, [accountId, revision.revision_id, revision.claim.predicate_id]);
    }
    for (const argument of revision.claim.arguments) {
      if (argument.value.kind !== "source_local_ref") continue;
      await executeRequired(connection, "ledger.source_local_role_insert", `
INSERT INTO omi_memory.memory_source_local_claim_roles
  (account_id, claim_revision_id, source_local_ref, role_slot_id, commit_id)
VALUES ($1, $2, $3, $4, $5)
`, [accountId, revision.revision_id, argument.value.ref, argument.slot_id, commitId]);
    }
  }
  for (const edge of transition.adjacency) {
    await executeRequired(connection, "ledger.adjacency_insert", `
INSERT INTO omi_memory.memory_generated_adjacency
  (account_id, claim_revision_id, entity_id, role_slot_id, commit_id)
VALUES ($1, $2, $3, $4, $5)
`, [accountId, edge.claim_revision_id, edge.entity_id, edge.role_slot_id, commitId]);
  }
  for (const result of transition.placement.results) {
    await executeRequired(connection, "ledger.consumed_marker_insert", `
INSERT INTO omi_memory.memory_consumed_markers
  (account_id, provisional_revision_id, commit_id, disposition)
VALUES ($1, $2, $3, $4)
`, [accountId, result.input_provisional_revision_id, commitId, result.disposition]);
  }
  for (const artifact of transition.artifacts) {
    if (artifact.kind === "candidate_derivation") {
      await executeRequired(connection, "ledger.candidate_artifact_insert", `
INSERT INTO omi_memory.memory_candidate_derivation_artifacts
  (account_id, artifact_id, source_ref, candidate_entity_id,
   strategy_ref, input_refs, commit_id)
VALUES ($1, $2, $3, $4, $5,
        convert_from($6::bytea, 'UTF8')::jsonb, $7)
`, [
        accountId, artifact.artifact_id, artifact.source_ref,
        artifact.candidate_entity_id, artifact.strategy_ref,
        jsonBytes(artifact.input_refs), commitId,
      ]);
    } else {
      await executeRequired(connection, "ledger.placement_artifact_insert", `
INSERT INTO omi_memory.memory_placement_artifacts
  (account_id, artifact_id, artifact_kind, provisional_revision_id,
   canonical_claim_revision_id, margin, risk_markers,
   unit_boundary_decision, scope_locality, commit_id)
VALUES ($1, $2, $3, $4, $5, $6,
        convert_from($7::bytea, 'UTF8')::jsonb, $8, $9, $10)
`, [
        accountId, artifact.artifact_id, artifact.kind,
        artifact.provisional_revision_id, artifact.canonical_claim_revision_id,
        artifact.margin, jsonBytes(artifact.risk_markers),
        artifact.unit_boundary_decision, artifact.scope_locality, commitId,
      ]);
    }
  }
};

const persistFormationOutcome = async (
  connection: CheckedOutPostgresConnection,
  accountId: string,
  commitId: string,
  request: AuthoritativeLedgerAppend,
): Promise<void> => {
  if (request.origin.kind !== "formation") return;
  const outcome = request.origin.outcome;
  await executeRequired(connection, "ledger.formation_outcome_insert", `
INSERT INTO omi_memory.memory_formation_outcomes
  (account_id, formation_work_id, input_frontier, response_digest,
   contract_version, candidate_count, strategy_coordinates,
   candidate_manifest_digest, content_hash, commit_id)
VALUES ($1, $2, $3, $4, $5, $6,
        convert_from($7::bytea, 'UTF8')::jsonb, $8, $9, $10)
`, [
    accountId, outcome.work_id, outcome.input_frontier, outcome.response_digest,
    outcome.contract_version, outcome.candidate_count, jsonBytes(outcome.coordinates),
    outcome.candidate_manifest_digest,
    sha256CanonicalRedacted(outcome as unknown as CanonicalJson), commitId,
  ]);
  for (let ordinal = 0; ordinal < outcome.extraction_outcomes.length; ordinal += 1) {
    const extraction = outcome.extraction_outcomes[ordinal]!;
    await executeRequired(connection, "ledger.formation_extraction_insert", `
INSERT INTO omi_memory.memory_formation_extraction_outcomes
  (account_id, formation_work_id, ordinal, candidate_ref, outcome_kind,
   claim_revision_id, repair_codes, reason_code, reason_detail)
VALUES ($1, $2, $3, $4, $5, $6,
        CASE WHEN $7::bytea IS NULL THEN NULL
             ELSE convert_from($7::bytea, 'UTF8')::jsonb END,
        $8, $9)
`, [
      accountId, outcome.work_id, ordinal, extraction.candidate_ref,
      extraction.kind,
      extraction.kind === "accepted" ? extraction.claim_revision_id : null,
      extraction.kind === "accepted" ? jsonBytes(extraction.repair_codes) : null,
      extraction.kind === "dropped" ? extraction.reason_code : null,
      // Durable diagnostics are closed-code only. The exact outcome digest
      // still proves the normalized envelope without persisting free-form text.
      null,
    ]);
    if (extraction.kind === "accepted") {
      for (const evidenceId of extraction.evidence_ids) {
        await executeRequired(connection, "ledger.formation_extraction_evidence_insert", `
INSERT INTO omi_memory.memory_formation_extraction_evidence
  (account_id, formation_work_id, extraction_ordinal, evidence_id)
VALUES ($1, $2, $3, $4)
`, [accountId, outcome.work_id, ordinal, evidenceId]);
      }
    }
  }
  for (const placement of outcome.placement_outcomes) {
    await executeRequired(connection, "ledger.formation_placement_insert", `
INSERT INTO omi_memory.memory_formation_placement_outcomes
  (account_id, formation_work_id, input_provisional_revision_id,
   outcome_kind, canonical_claim_revision_id, boundary_decision,
   scope_locality, reason_code, reconsideration_trigger, attempt,
   attempts, max_attempts, error_code, next_eligible_at)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
`, [
      accountId, outcome.work_id, placement.input_provisional_revision_id,
      placement.kind,
      placement.kind === "admitted" ? placement.canonical_claim_revision_id : null,
      placement.kind === "admitted" || placement.kind === "abstained"
        ? placement.boundary_decision : null,
      placement.kind === "admitted" ? placement.scope_locality : null,
      placement.kind === "abstained" ? placement.reason_code : null,
      placement.kind === "abstained" ? placement.reconsideration_trigger : null,
      placement.kind === "retryable_error" ? placement.attempt : null,
      placement.kind === "dead_letter" ? placement.attempts : null,
      placement.kind === "retryable_error" || placement.kind === "dead_letter"
        ? placement.max_attempts : null,
      placement.kind === "retryable_error" || placement.kind === "dead_letter"
        ? placement.error_code : null,
      placement.kind === "retryable_error" ? placement.next_eligible_at : null,
    ]);
  }
};

const appendAuthorized = async (
  pool: PostgresTransactionPool,
  context: AuthorizedLedgerWriteContext,
  request: AuthoritativeLedgerAppend,
  observability: PostgresTransactionObservability,
  qualificationOnly: boolean,
): Promise<AuthoritativeLedgerAppendOutcome> => {
  if (qualificationOnly) assertQualificationTransition(request);
  try {
    return await withAuthorizedSerializableConnectionTransaction(
      pool,
      context,
      async ({ authority, connection }) => {
        const attempt = request.append_attempt;
        const derivation = request.transition.derivation;
        const commit = derivation.commit;
        const receiptValues = [authority.account_id, authority.account_epoch, attempt.idempotency_key] as const;
        const receipts = await connection.query<ReceiptRow>({
          name: "ledger.receipt_lookup",
          text: `
SELECT r.request_digest, r.state, r.commit_id, c.sequence,
       c.attempt_id, c.parent_commit_id, c.input_digest,
       c.input_version_digest, c.output_digest, c.success_kind,
       c.origin_kind, c.formation_work_id, c.non_formation_reason,
       c.record_json
FROM omi_memory.memory_idempotency_receipts AS r
LEFT JOIN omi_memory.memory_derivation_commits AS c
  ON c.account_id = r.account_id AND c.commit_id = r.commit_id
WHERE r.account_id = $1 AND r.account_epoch = $2 AND r.idempotency_key = $3
FOR UPDATE OF r
`,
          values: receiptValues,
        });
        if (receipts.length > 1) throw new PostgresRepositoryError("persistence_failed");
        if (receipts[0]) return replayOutcome(receipts[0], request);

        await verifyCommittedWitnesses(connection, authority.account_id, request.transition);
        await verifyIdentityClosure(connection, authority.account_id, request.transition);

        const reserved = await connection.execute({
          name: "ledger.receipt_reserve",
          text: `
INSERT INTO omi_memory.memory_idempotency_receipts
  (account_id, account_epoch, idempotency_key, request_digest, state)
VALUES ($1, $2, $3, $4, 'reserved')
ON CONFLICT (account_id, account_epoch, idempotency_key) DO NOTHING
`,
          values: [...receiptValues, attempt.request_digest],
        });
        if (reserved.rowCount !== 1) {
          // Another SERIALIZABLE writer won the key after our snapshot.  A
          // caller retry revalidates authority and observes its exact receipt.
          throw new PostgresRepositoryError("retryable_serialization", true);
        }

        const heads = await connection.query<HeadRow>({
          name: "ledger.head_lock",
          text: `
SELECT commit_id, sequence
FROM omi_memory.memory_graph_heads
WHERE account_id = $1
FOR UPDATE
`,
          values: [authority.account_id],
        });
        const head = heads[0];
        if (heads.length !== 1 || !head) throw new PostgresRepositoryError("persistence_failed");
        const headSequence = safeCounter(head.sequence);
        if (head.commit_id !== attempt.expected_parent_commit) {
          throw new PostgresRepositoryError("stale_parent");
        }
        const sequence = headSequence + 1;
        if (!Number.isSafeInteger(sequence)) throw new PostgresRepositoryError("persistence_failed");

        await executeRequired(connection, "ledger.attempt_insert", `
INSERT INTO omi_memory.memory_derivation_attempts
  (account_id, attempt_id, input_digest, input_version_digest, output_digest,
   success_kind, versions, record_json)
VALUES ($1, $2, $3, $4, $5, $6,
        convert_from($7::bytea, 'UTF8')::jsonb,
        convert_from($8::bytea, 'UTF8')::jsonb)
`, [
            authority.account_id,
            derivation.attempt.attempt_id,
            derivation.attempt.input_digest,
            derivation.attempt.input_version_digest,
            derivation.attempt.output_digest,
            derivation.attempt.success_kind,
            jsonBytes(derivation.attempt.versions),
            jsonBytes(derivation.attempt),
          ]);

        const commitRecord = { ...commit, sequence };
        const originKind = request.origin.kind;
        const formationWorkId = request.origin.kind === "formation"
          ? request.origin.outcome.work_id : null;
        const nonFormationReason = request.origin.kind === "non_formation"
          ? request.origin.reason : null;
        await executeRequired(connection, "ledger.commit_insert", `
INSERT INTO omi_memory.memory_derivation_commits
  (account_id, commit_id, attempt_id, parent_commit_id, sequence,
   input_digest, input_version_digest, output_digest, success_kind,
   origin_kind, formation_work_id, non_formation_reason, record_json)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
        $10, $11, $12, convert_from($13::bytea, 'UTF8')::jsonb)
`, [
            authority.account_id,
            commit.commit_id,
            commit.attempt_id,
            commit.parent_commit,
            sequence,
            commit.input_digest,
            commit.input_version_digest,
            commit.output_digest,
            commit.success_kind,
            originKind,
            formationWorkId,
            nonFormationReason,
            jsonBytes(commitRecord),
          ]);

        if (!qualificationOnly) {
          await persistDerivationInputs(
            connection, authority.account_id, commit.commit_id, request.transition,
          );
          await persistRevisionRoots(
            connection, authority.account_id, request.transition.revisions,
          );
          await persistGenericRevisions(
            connection, authority.account_id, commit.commit_id,
            commit.versions.schema_version, request.transition.revisions,
          );
          await persistPrimaryRevisionSubtypes(
            connection, authority.account_id, request.transition.revisions,
          );
          await persistAuthorizationAndMentionSubtypes(
            connection, authority.account_id, request.transition.revisions,
          );
          await persistIdentitySupportAndConstraints(
            connection, authority.account_id, commit.commit_id,
            commit.versions.schema_version, request.transition,
          );
          await persistClaimRelationsAndArtifacts(
            connection, authority.account_id, commit.commit_id, request.transition,
          );
          await persistFormationOutcome(
            connection, authority.account_id, commit.commit_id, request,
          );
        }

        const advanced = await connection.execute({
          name: "ledger.head_advance",
          text: `
UPDATE omi_memory.memory_graph_heads
SET commit_id = $2, sequence = $3, updated_at = transaction_timestamp()
WHERE account_id = $1 AND sequence = $4
  AND commit_id IS NOT DISTINCT FROM $5
`,
          values: [authority.account_id, commit.commit_id, sequence, headSequence, head.commit_id],
        });
        if (advanced.rowCount !== 1) throw new PostgresRepositoryError("stale_parent");

        const finalized = await connection.execute({
          name: "ledger.receipt_finalize",
          text: `
UPDATE omi_memory.memory_idempotency_receipts
SET state = 'finalized', commit_id = $4, finalized_at = transaction_timestamp()
WHERE account_id = $1 AND account_epoch = $2 AND idempotency_key = $3
  AND request_digest = $5 AND state = 'reserved' AND commit_id IS NULL
`,
          values: [
            authority.account_id,
            authority.account_epoch,
            attempt.idempotency_key,
            commit.commit_id,
            attempt.request_digest,
          ],
        });
        if (finalized.rowCount !== 1) throw new PostgresRepositoryError("persistence_failed");
        return Object.freeze({ kind: "committed" as const, commit_id: commit.commit_id, sequence });
      },
      observability,
    );
  } catch (error) {
    if (!(error instanceof PostgresRepositoryError)) throw error;
    switch (error.code) {
      case "expired_context":
      case "stale_epoch":
      case "destination_inactive":
      case "lifecycle_inactive":
        return Object.freeze({ kind: "stale_context" as const, reason: error.code });
      case "credential_inactive":
        return Object.freeze({ kind: "authorization_denied" as const, reason: "credential_inactive" as const });
      case "grant_inactive":
        return Object.freeze({ kind: "authorization_denied" as const, reason: "grant_inactive" as const });
      case "capability_denied":
        return Object.freeze({ kind: "authorization_denied" as const, reason: "capability_denied" as const });
      case "idempotency_conflict":
        return Object.freeze({ kind: "idempotency_conflict" as const });
      case "stale_parent":
        return Object.freeze({ kind: "stale_parent" as const });
      case "retryable_serialization":
        return Object.freeze({ kind: "serialization_retryable" as const });
      default:
        throw error;
    }
  }
};

export interface PostgresSuccessfulEmptyLedgerRepositoryOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Qualification-only persistence kernel for input-empty/output-empty,
 * successful-empty legacy maintenance commits.  It deliberately rejects all
 * graph revisions, formation work, durable-job origins, and service wiring.
 * It is not the canonical PostgreSQL repository and must be replaced or
 * expanded before activation.
 */
export const createPostgresSuccessfulEmptyLedgerRepository = (
  options: PostgresSuccessfulEmptyLedgerRepositoryOptions,
): AuthoritativeLedgerRepository => defineAuthoritativeLedgerRepository(
  (context, request) => appendAuthorized(
    options.pool,
    context,
    request,
    options.observability ?? {},
    true,
  ),
);

export interface PostgresAuthoritativeLedgerRepositoryOptions {
  readonly pool: PostgresTransactionPool;
  readonly observability?: PostgresTransactionObservability;
}

/**
 * Complete inert PostgreSQL append adapter. It supports every graph revision,
 * placement artifact, and total formation outcome in the sealed service port,
 * but is deliberately not composed into a route while activation is false.
 */
export const createPostgresAuthoritativeLedgerRepository = (
  options: PostgresAuthoritativeLedgerRepositoryOptions,
): AuthoritativeLedgerRepository => defineAuthoritativeLedgerRepository(
  (context, request) => appendAuthorized(
    options.pool,
    context,
    request,
    options.observability ?? {},
    false,
  ),
);
