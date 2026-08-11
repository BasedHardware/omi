import { readFileSync } from "node:fs";

import { describe, expect, test } from "bun:test";

import { POSTGRES_MIGRATIONS } from "./manifest";

const directory = new URL("./", import.meta.url);
const migrationSql = POSTGRES_MIGRATIONS.map((migration) => ({
  ...migration,
  sql: readFileSync(new URL(migration.fileName, directory), "utf8"),
}));
const allSql = migrationSql.map((migration) => migration.sql).join("\n");

interface TableDefinition {
  readonly name: string;
  readonly body: string;
}

const tableDefinitions = (sql: string): readonly TableDefinition[] => {
  const definitions: TableDefinition[] = [];
  const start = /CREATE TABLE omi_memory\.([a-z0-9_]+)\s*\(/g;
  for (let match = start.exec(sql); match; match = start.exec(sql)) {
    let depth = 1;
    let cursor = start.lastIndex;
    let quoted = false;
    for (; cursor < sql.length && depth > 0; cursor += 1) {
      const character = sql[cursor]!;
      if (character === "'" && sql[cursor - 1] !== "\\") quoted = !quoted;
      if (quoted) continue;
      if (character === "(") depth += 1;
      if (character === ")") depth -= 1;
    }
    if (depth !== 0) throw new Error(`unterminated CREATE TABLE ${match[1]}`);
    definitions.push({ name: match[1]!, body: sql.slice(start.lastIndex, cursor - 1) });
    start.lastIndex = cursor;
  }
  return definitions;
};

const tables = tableDefinitions(allSql);
const expectedTables = [
  "account_control_heads",
  "account_control_revisions",
  "account_terminal_deletion_exports",
  "application_credential_heads",
  "application_credential_revisions",
  "application_grant_heads",
  "application_grant_revisions",
  "memory_candidate_derivation_artifacts",
  "memory_claim_evidence_refs",
  "memory_claim_lineages",
  "memory_claim_liveness_fences",
  "memory_claim_predicate_refs",
  "memory_claim_revisions",
  "memory_claim_source_provisionals",
  "memory_claim_supersessions",
  "memory_consumed_markers",
  "memory_coreference_support_evidence_refs",
  "memory_coreference_support_revisions",
  "memory_derivation_attempts",
  "memory_derivation_commits",
  "memory_derivation_inputs",
  "memory_entity_identities",
  "memory_entity_revisions",
  "memory_event_identities",
  "memory_event_revisions",
  "memory_evidence_identities",
  "memory_evidence_revisions",
  "memory_formation_extraction_evidence",
  "memory_formation_extraction_outcomes",
  "memory_formation_outcomes",
  "memory_formation_placement_outcomes",
  "memory_generated_adjacency",
  "memory_graph_heads",
  "memory_idempotency_receipts",
  "memory_identity_authorization_identities",
  "memory_identity_authorization_entity_endpoints",
  "memory_identity_authorization_revisions",
  "memory_identity_authorization_support",
  "memory_identity_constraint_entity_endpoints",
  "memory_identity_revisions",
  "memory_identity_support",
  "memory_mention_revisions",
  "memory_work_acceptances",
  "memory_work_heads",
  "memory_work_input_manifest",
  "memory_work_outbox_events",
  "memory_work_state_revisions",
  "memory_placement_artifacts",
  "memory_predicate_assertion_revisions",
  "memory_predicate_identities",
  "memory_predicate_revisions",
  "memory_revisions",
  "memory_source_local_claim_roles",
  "platform_accounts",
  "platform_schema_migrations",
] as const;

describe("P2/P3 PostgreSQL schema contract", () => {
  test("contains exactly the reviewed expand-only surface", () => {
    expect(tables.map((table) => table.name).sort()).toEqual([...expectedTables].sort());
    expect(allSql).not.toMatch(/CREATE\s+(?:TABLE|TYPE).*\b(?:proposition|projection|citation|search|embedding|experiment)/i);
    expect(allSql).not.toMatch(/\b(?:pgvector|tsvector|CREATE\s+ROLE|server_version|postgres:\d+)\b/i);
    expect(allSql).not.toContain("ON DELETE CASCADE");
  });

  test("makes every authority relationship structurally account-scoped", () => {
    for (const table of tables) {
      if (table.name === "platform_schema_migrations") continue;
      expect(table.body, table.name).toMatch(/\baccount_id\s+text\b/);
      expect(table.body, table.name).toMatch(/account_id\s+text\s+PRIMARY KEY|PRIMARY KEY\s*\(\s*account_id\b/);

      for (const key of table.body.matchAll(/\b(?:PRIMARY KEY|UNIQUE)\s*\(([^)]*)\)/g)) {
        expect(key[1]!.split(",")[0]!.trim(), `${table.name} key`).toBe("account_id");
      }
      for (const foreignKey of table.body.matchAll(
        /FOREIGN KEY\s*\(([^)]*)\)\s+REFERENCES\s+(omi_memory\.[a-z0-9_]+)\s*\(([^)]*)\)/g,
      )) {
        expect(foreignKey[1]!.split(",")[0]!.trim(), `${table.name} foreign key`).toBe("account_id");
        expect(foreignKey[2], `${table.name} qualified target`).toStartWith("omi_memory.");
        expect(foreignKey[3]!.split(",")[0]!.trim(), `${table.name} target key`).toBe("account_id");
      }
      expect([...table.body.matchAll(/FOREIGN KEY/g)].length, `${table.name} parsed foreign keys`)
        .toBe([...table.body.matchAll(/FOREIGN KEY\s*\([^)]*\)\s+REFERENCES\s+omi_memory\.[a-z0-9_]+\s*\([^)]*\)/g)].length);
    }
  });

  test("persists the exact principal, credential generation, and grant revision coordinates", () => {
    const credential = tables.find((table) => table.name === "application_credential_revisions")!;
    expect(credential.body).toContain("principal_id text NOT NULL");
    expect(credential.body).toContain("credential_generation bigint NOT NULL");
    const grant = tables.find((table) => table.name === "application_grant_revisions")!;
    expect(grant.body).toContain("capability text NOT NULL");
    expect(grant.body).toContain("grant_id text NOT NULL");
    expect(grant.body).toContain("grant_version bigint NOT NULL");
    expect(grant.body).toContain("lifecycle IN ('active', 'inactive', 'revoked')");
  });

  test("locks authority through one fixed security-definer function without table mutation grants", () => {
    expect(allSql).toContain("CREATE FUNCTION omi_memory.lock_authority_state(");
    expect(allSql).toContain("SECURITY DEFINER\nSET search_path = pg_catalog, omi_memory");
    expect(allSql).toContain("FOR SHARE OF a, ach, ac, ch, cr, gh, gr");
    expect(allSql).toContain("AND cr.principal_id = requested_principal_id");
    expect(allSql).toContain("REVOKE ALL ON FUNCTION omi_memory.lock_authority_state");
    expect(allSql).toContain("GRANT EXECUTE ON FUNCTION omi_memory.lock_authority_state");
    const grants = allSql.match(/GRANT[\s\S]*?;/g) ?? [];
    expect(grants.join("\n")).not.toMatch(/UPDATE[^;]*omi_memory\.(?:account_control|application_credential|application_grant)/);
  });

  test("seeds one lockable sequence-zero graph head for every account", () => {
    expect(allSql).toContain("INSERT INTO omi_memory.memory_graph_heads (account_id)");
    expect(allSql).toContain("SELECT account_id FROM omi_memory.platform_accounts");
    expect(allSql).toContain("AFTER INSERT ON omi_memory.platform_accounts");
    expect(allSql).toContain("RETURN NEW;\nEND;\n$function$;");
    expect(allSql).toContain("CHECK ((commit_id IS NULL AND sequence = 0) OR (commit_id IS NOT NULL AND sequence > 0))");
    const heads = tables.find((table) => table.name === "memory_graph_heads")!;
    expect(heads.body).toContain("FOREIGN KEY (account_id, commit_id, sequence)");
    expect(heads.body).toContain("(account_id, commit_id, sequence)");
  });

  test("keeps liveness closed and identity-support provenance relational", () => {
    const liveness = tables.find((table) => table.name === "memory_claim_liveness_fences")!;
    expect(liveness.body).toContain("cause IN ('purged', 'forgotten')");
    expect((allSql.match(/cause IN \('purged', 'forgotten'\)/g) ?? []).length).toBe(1);

    const support = tables.find((table) => table.name === "memory_identity_support")!;
    expect(support.body).toContain("FOREIGN KEY (account_id, claim_revision_id)");
    expect(support.body).toContain("FOREIGN KEY (account_id, evidence_revision_id, event_revision_id)");
    expect(support.body).toContain("(account_id, revision_id, event_revision_id)");
    expect(support.body).toContain("support_origin IN ('suggested', 'independent')");

    const authorizationSupport = tables.find((table) => table.name === "memory_identity_authorization_support")!;
    expect(authorizationSupport.body).toContain("FOREIGN KEY (account_id, authorization_revision_id)");
    expect(authorizationSupport.body).toContain("FOREIGN KEY (account_id, support_ref)");
  });

  test("normalizes the bounded cross-record relation surface", () => {
    const requiredRelationships = [
      ["memory_claim_evidence_refs", "evidence_id"],
      ["memory_claim_source_provisionals", "source_provisional_revision_id"],
      ["memory_claim_supersessions", "superseded_claim_revision_id"],
      ["memory_claim_predicate_refs", "predicate_id"],
      ["memory_coreference_support_evidence_refs", "evidence_id"],
      ["memory_identity_authorization_entity_endpoints", "entity_id"],
      ["memory_identity_constraint_entity_endpoints", "entity_id"],
    ] as const;
    for (const [tableName, coordinate] of requiredRelationships) {
      const table = tables.find((candidate) => candidate.name === tableName)!;
      expect(table.body, tableName).toContain(`FOREIGN KEY (account_id, ${coordinate})`);
    }

    const mention = tables.find((table) => table.name === "memory_mention_revisions")!;
    expect(mention.body).toContain("entity_id text");
    expect(mention.body).toContain("FOREIGN KEY (account_id, entity_id)");

    const predicateAssertion = tables.find((table) => table.name === "memory_predicate_assertion_revisions")!;
    expect(predicateAssertion.body).toContain("FOREIGN KEY (account_id, supersedes_assertion_id)");
    const identityAuthorization = tables.find((table) => table.name === "memory_identity_authorization_revisions")!;
    expect(identityAuthorization.body).toContain("FOREIGN KEY (account_id, superseded_by_authorization_id)");

    expect(allSql).toContain("Source-identity endpoints");
    expect(allSql).toContain("have no P2.1 relational authority target");
  });

  test("makes formation accounting total and terminal deletion subordinate", () => {
    const commits = tables.find((table) => table.name === "memory_derivation_commits")!;
    expect(commits.body).toContain("origin_kind IN ('formation', 'non_formation')");
    expect(commits.body).toContain("formation_work_id IS NOT NULL");
    expect(commits.body).toContain("non_formation_reason IS NOT NULL");
    expect(allSql).toContain("memory_derivation_commits_formation_outcome_fk");
    expect(allSql).toContain("DEFERRABLE INITIALLY DEFERRED");

    const terminalExport = tables.find((table) => table.name === "account_terminal_deletion_exports")!;
    expect(terminalExport.body).toContain("terminal_lifecycle_state = 'deleted'");
    expect(terminalExport.body).toContain(
      "account_id, control_revision, deletion_epoch, account_generation,\n    terminal_lifecycle_state",
    );
    expect(terminalExport.body).toContain(
      "account_id, control_revision, deletion_epoch, account_generation,\n    lifecycle_state",
    );
  });

  test("grants the application only append and named mutable coordinates", () => {
    const grants = allSql.match(/GRANT[\s\S]*?;/g) ?? [];
    expect(grants.length).toBeGreaterThan(0);
    expect(grants.join("\n")).not.toMatch(/\b(?:ALL|DELETE|TRUNCATE|CREATE|ALTER|DROP)\b/);
    const updateGrants = grants.filter((grant) => /\bUPDATE\b/.test(grant));
    expect(updateGrants).toHaveLength(2);
    expect(updateGrants[0]).toContain("UPDATE (commit_id, sequence, updated_at)");
    expect(updateGrants[0]).toContain("omi_memory.memory_graph_heads");
    expect(updateGrants[0]).not.toContain("INSERT");
    expect(updateGrants[1]).toContain("UPDATE (state, commit_id, finalized_at)");
    expect(updateGrants[1]).toContain("omi_memory.memory_idempotency_receipts");
    expect(grants.join("\n")).not.toContain("omi_memory.platform_schema_migrations TO omi_platform_application");
    expect(grants.join("\n")).not.toMatch(/omi_memory\.memory_work_/);
  });

  test("persists only closed, fenced, content-safe P3 work and outbox coordinates", () => {
    const acceptance = tables.find((table) => table.name === "memory_work_acceptances")!;
    expect(acceptance.body).toContain("work_version = 'durable-memory-work-v1'");
    expect(acceptance.body).toContain("'formation', 'promotion', 'identity_cluster', 'predicate_batch'");
    expect(acceptance.body).toContain("accepted_work_digest text NOT NULL");
    expect(acceptance.body).toContain("execution_contract_digest text NOT NULL");
    expect(acceptance.body).toContain("max_attempts BETWEEN 1 AND 100");
    expect(acceptance.body).toContain("lifecycle_state = 'active'");
    expect(acceptance.body).toContain("deletion_epoch IS NULL");

    const state = tables.find((table) => table.name === "memory_work_state_revisions")!;
    expect(state.body).toContain("'pending', 'leased', 'retryable_failed', 'succeeded', 'dead_letter'");
    expect(state.body).toContain("CHECK (lease_fence = attempt)");
    expect(state.body).toContain("lease_expires_at_event_time > leased_at_event_time");
    expect(state.body).toContain("next_eligible_event_time > failed_at_event_time");
    expect(state.body).toContain("'successful', 'successful_empty'");
    expect(state.body).not.toMatch(/model_output|last_error|error_message|raw_|payload|jsonb/i);

    const outbox = tables.find((table) => table.name === "memory_work_outbox_events")!;
    expect(outbox.body).toContain("'memory_work_succeeded', 'memory_work_dead_letter'");
    expect(outbox.body).toContain("terminal_state_digest text NOT NULL");
    expect(outbox.body).toContain("terminal_state IN ('succeeded', 'dead_letter')");
    expect(outbox.body).toContain("terminal_state = 'succeeded' AND result_digest IS NOT NULL");
    expect(outbox.body).toContain("terminal_state = 'dead_letter' AND result_digest IS NULL");
    expect(outbox.body).not.toMatch(/payload|body|model|prompt|evidence|query|answer|error/i);
  });
});
