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
  "firebase_application_credential_bindings",
  "firebase_identity_bindings",
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
  "memory_formation_work_inputs",
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
  "memory_legacy_proposition_mappings",
  "memory_mention_revisions",
  "memory_migration_item_tombstones",
  "memory_product_group_members",
  "memory_product_group_projections",
  "memory_product_membership_claim_lineages",
  "memory_product_membership_revisions",
  "memory_product_operation_receipts",
  "memory_product_projection_citation_evidence_refs",
  "memory_product_projection_citations",
  "memory_product_projection_payloads",
  "memory_product_projection_revisions",
  "memory_product_propositions",
  "memory_product_redirect_successors",
  "memory_product_redirects",
  "memory_query_evaluation_inputs",
  "memory_work_acceptances",
  "memory_work_execution_policies",
  "memory_work_heads",
  "memory_work_input_manifest",
  "memory_work_outbox_events",
  "memory_work_success_results",
  "memory_work_state_revisions",
  "memory_work_staged_results",
  "memory_placement_artifacts",
  "memory_predicate_batch_work_inputs",
  "memory_predicate_assertion_revisions",
  "memory_predicate_identities",
  "memory_predicate_revisions",
  "memory_revisions",
  "memory_source_local_claim_roles",
  "memory_strategy_assignment_bundles",
  "memory_strategy_assignment_policies",
  "memory_strategy_baseline_read_groundings",
  "memory_strategy_candidate_read_groundings",
  "memory_strategy_definitions",
  "memory_strategy_evaluation_baselines",
  "memory_strategy_evaluation_pairs",
  "memory_strategy_policy_shadows",
  "memory_strategy_shadow_results",
  "memory_strategy_shadow_assignments",
  "platform_accounts",
  "platform_schema_migrations",
] as const;

describe("P2/P3/P4/P5 PostgreSQL schema contract", () => {
  test("contains exactly the reviewed expand-only surface", () => {
    expect(tables.map((table) => table.name).sort()).toEqual([...expectedTables].sort());
    expect(allSql).not.toMatch(/CREATE\s+(?:TABLE|TYPE).*\b(?:search|embedding|experiment)/i);
    expect(allSql).not.toMatch(/\b(?:pgvector|tsvector|CREATE\s+ROLE|server_version|postgres:\d+)\b/i);
    expect(allSql).not.toContain("ON DELETE CASCADE");
  });

  test("makes every authority relationship structurally account-scoped", () => {
    for (const table of tables) {
      if (table.name === "platform_schema_migrations") continue;
      expect(table.body, table.name).toMatch(/\baccount_id\s+text\b/);
      if (table.name === "firebase_identity_bindings") {
        expect(table.body).toContain("PRIMARY KEY (firebase_project_id, firebase_uid)");
      } else {
        expect(table.body, table.name)
          .toMatch(/account_id\s+text\s+PRIMARY KEY|PRIMARY KEY\s*\(\s*account_id\b/);
      }

      for (const key of table.body.matchAll(/\b(PRIMARY KEY|UNIQUE)\s*\(([^)]*)\)/g)) {
        const firstCoordinate = key[2]!.split(",")[0]!.trim();
        if (table.name === "firebase_identity_bindings"
          && key[1] === "PRIMARY KEY"
          && firstCoordinate === "firebase_project_id") continue;
        expect(firstCoordinate, `${table.name} key`).toBe("account_id");
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

  test("binds one global Firebase identity to one account and one account-scoped credential", () => {
    const identity = tables.find((table) => table.name === "firebase_identity_bindings")!;
    expect(identity.body).toContain("PRIMARY KEY (firebase_project_id, firebase_uid)");
    expect(identity.body).toContain(
      "UNIQUE (account_id, firebase_project_id, firebase_uid, principal_id)",
    );
    expect(identity.body).toContain("FOREIGN KEY (account_id, source_control_revision)");
    expect(identity.body).toContain(
      "REFERENCES omi_memory.account_control_revisions (account_id, control_revision)",
    );

    const application = tables.find(
      (table) => table.name === "firebase_application_credential_bindings",
    )!;
    expect(application.body).toContain(
      "PRIMARY KEY (account_id, firebase_project_id, firebase_uid, application_id)",
    );
    expect(application.body).toContain(
      "FOREIGN KEY (account_id, firebase_project_id, firebase_uid, principal_id)",
    );
    expect(application.body).toContain(
      "(account_id, firebase_project_id, firebase_uid, principal_id)",
    );
    expect(application.body).toContain(
      "FOREIGN KEY (account_id, application_id, credential_id)",
    );
    expect(application.body).toContain(
      "REFERENCES omi_memory.application_credential_heads",
    );
  });

  test("exposes only the fixed Firebase authorization lookup for the new binding tables", () => {
    const signature = "omi_memory.lookup_firebase_application_authorization(text, text, text, text)";
    const functionSql = migrationSql.find((migration) => migration.version === 12)!.sql;
    expect(allSql).toContain("CREATE FUNCTION omi_memory.lookup_firebase_application_authorization(");
    expect(allSql).toContain("SECURITY DEFINER\nSET search_path = pg_catalog, omi_memory");
    expect(functionSql).not.toContain("FOR SHARE");
    expect(allSql).toContain(`REVOKE ALL ON FUNCTION ${signature}`);
    expect(allSql).toContain(`GRANT EXECUTE ON FUNCTION ${signature}`);
    expect(allSql).not.toMatch(
      /GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE)[^;]*omi_memory\.firebase_(?:identity|application_credential)_bindings/i,
    );
    const parameters = functionSql.slice(
      functionSql.indexOf("CREATE FUNCTION"),
      functionSql.indexOf(")\nRETURNS TABLE"),
    );
    expect(parameters).toContain("requested_firebase_project_id text");
    expect(parameters).toContain("requested_firebase_uid text");
    expect(parameters).toContain("requested_application_id text");
    expect(parameters).toContain("requested_capability text");
    for (const forbidden of [
      "requested_account_id",
      "requested_principal_id",
      "requested_credential_id",
      "requested_grant_id",
      "requested_account_epoch",
      "requested_control_revision",
    ]) expect(parameters).not.toContain(forbidden);
    for (const relation of [
      "firebase_identity_bindings",
      "firebase_application_credential_bindings",
      "platform_accounts",
      "account_control_heads",
      "account_control_revisions",
      "application_credential_heads",
      "application_credential_revisions",
      "application_grant_heads",
      "application_grant_revisions",
    ]) expect(functionSql).toContain(`omi_memory.${relation}`);
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
    expect(allSql).toContain("ALTER COLUMN commit_id SET NOT NULL");
    expect(allSql).toContain("memory_claim_liveness_fences_commit_fk");
    expect(allSql).toContain("FOREIGN KEY (account_id, commit_id)");

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
    expect(updateGrants).toHaveLength(3);
    expect(updateGrants[0]).toContain("UPDATE (commit_id, sequence, updated_at)");
    expect(updateGrants[0]).toContain("omi_memory.memory_graph_heads");
    expect(updateGrants[0]).not.toContain("INSERT");
    expect(updateGrants[1]).toContain("UPDATE (state, commit_id, finalized_at)");
    expect(updateGrants[1]).toContain("omi_memory.memory_idempotency_receipts");
    expect(updateGrants[2]).toContain("UPDATE (state_revision, state_digest, updated_at)");
    expect(updateGrants[2]).toContain("omi_memory.memory_work_heads");
    expect(grants.join("\n")).not.toContain("omi_memory.platform_schema_migrations TO omi_platform_application");
    const workGrants = grants.filter((grant) => /omi_memory\.memory_work_/.test(grant));
    expect(workGrants).toHaveLength(7);
    expect(workGrants.join("\n")).toContain("memory_work_acceptances");
    expect(workGrants.join("\n")).toContain("memory_work_execution_policies");
    expect(workGrants.join("\n")).toContain("memory_work_input_manifest");
    expect(workGrants.join("\n")).toContain("memory_work_state_revisions");
    expect(workGrants.join("\n")).toContain("memory_work_heads");
    expect(workGrants.join("\n")).toContain("INSERT ON omi_memory.memory_work_outbox_events");
    expect(workGrants.join("\n")).not.toMatch(/DELETE|memory_work_(?:staged_results|success_results)/);
    const grantsBeforeProductWriter = migrationSql
      .filter((migration) => migration.version < 22)
      .flatMap((migration) => migration.sql.match(/GRANT[\s\S]*?;/g) ?? []);
    expect(grantsBeforeProductWriter.join("\n"))
      .not.toMatch(/omi_memory\.memory_(?:product_|legacy_proposition|migration_item)/);
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

    const executionPolicy = tables.find(
      (table) => table.name === "memory_work_execution_policies",
    )!;
    expect(executionPolicy.body).toContain("durable-memory-work-execution-policy-v1");
    expect(executionPolicy.body).toContain("lease_duration_seconds BETWEEN 1 AND 3600");
    expect(executionPolicy.body).toContain("retry_delays_seconds jsonb NOT NULL");
    expect(allSql).toContain("memory_work_acceptances_execution_policy_required");
    expect(allSql).toContain("memory_work_acceptances_execution_policy_fk");
    expect(allSql).toContain("NOT VALID");

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

  test("makes durable-work success atomic with its exact graph origin, receipt, state, and outbox", () => {
    expect(allSql).toContain("'promotion', 'identity_consolidation', 'predicate_alignment'");
    expect(allSql).toContain("ADD COLUMN origin_code text GENERATED ALWAYS AS");
    expect(allSql).toContain("UNIQUE (account_id, commit_id, sequence, origin_code, success_kind)");
    expect(allSql).toContain("UNIQUE (account_id, commit_id, request_digest, state)");

    const success = tables.find((table) => table.name === "memory_work_success_results")!;
    expect(success.body).toContain("terminal_state = 'succeeded'");
    expect(success.body).toContain("formation_work_id text GENERATED ALWAYS AS");
    expect(success.body).toContain("CASE WHEN work_kind = 'formation' THEN job_id ELSE NULL END");
    expect(success.body).toContain("result_kind = 'successful_empty'");
    expect(success.body).toContain("graph_commit_id IS NULL");
    expect(success.body).toContain("result_kind = 'successful'");
    expect(success.body).toContain("graph_success_kind = 'success'");
    expect(success.body).toContain("append_receipt_state = 'finalized'");
    expect(success.body).toContain("work_kind = 'formation' AND origin_code = 'formation'");
    expect(success.body).toContain("work_kind = 'promotion' AND origin_code = 'promotion'");
    expect(success.body).toContain("origin_code = 'identity_consolidation'");
    expect(success.body).toContain("origin_code = 'predicate_alignment'");
    expect(success.body).toContain("memory_work_acceptances");
    expect(success.body).toContain("memory_work_state_revisions");
    expect(success.body).toContain("memory_derivation_commits");
    expect(success.body).toContain("memory_formation_outcomes");
    expect(success.body).toContain("memory_idempotency_receipts");
    expect(success.body).not.toMatch(/payload|model_output|prompt|query|answer|error/i);

    expect(allSql).toContain("memory_work_outbox_events_success_result_fk");
    expect(allSql).toContain("REFERENCES omi_memory.memory_work_success_results");
    expect(allSql).toContain("Deliberately no application or worker grant");
    expect(allSql).not.toMatch(/GRANT[^;]*omi_memory\.memory_work_success_results/s);
  });

  test("stages one sensitive normalized result and makes every success reference it", () => {
    const staged = tables.find((table) => table.name === "memory_work_staged_results")!;
    expect(staged.body).toContain("result_version = 'durable-memory-work-result-v1'");
    expect(staged.body).toContain("PRIMARY KEY (account_id, job_id)");
    expect(staged.body).toContain("staged_result_id ~ '^mwr1_[0-9a-f]{64}$'");
    expect(staged.body).toContain("produced_state = 'leased'");
    expect(staged.body).toContain("CHECK (produced_attempt = produced_lease_fence)");
    expect(staged.body).toContain("memory_work_acceptances");
    expect(staged.body).toContain("memory_work_state_revisions");
    expect(staged.body).toContain("jsonb_typeof(normalized_result_json) = 'object'");
    expect(staged.body).toContain("octet_length(normalized_result_json::text) <= 524288");
    expect(staged.body).not.toMatch(/raw_provider|provider_output|error_message|last_error/i);

    expect(allSql).toContain("memory_work_success_results_staged_result_fk");
    expect(allSql).toContain("REFERENCES omi_memory.memory_work_staged_results");
    expect(allSql).toContain("result_digest = staged_result_digest");
    expect(allSql).toContain("Deliberately no application or worker grant");
    expect(allSql).not.toMatch(/GRANT[^;]*omi_memory\.memory_work_staged_results/s);
    expect(allSql).toContain("CREATE FUNCTION omi_memory.read_durable_work_staged_result");
    expect(allSql).toContain("CREATE FUNCTION omi_memory.insert_durable_work_staged_result");
    expect(allSql).toContain("SECURITY DEFINER");
    expect(allSql).toContain("current_setting('omi.account_id', true)");
    expect(allSql).toContain("current_setting('omi.capability', true)");
    expect(allSql).toContain("current_setting('omi.principal_id', true)");
    expect(allSql).toContain("IS DISTINCT FROM 'memories.work.execute'");
    expect(allSql).toContain("s.state_revision = h.state_revision");
    expect(allSql).toContain("s.lease_fence = requested_produced_lease_fence");
    expect(allSql).toContain("s.lease_expires_at_event_time");
    expect(allSql).toContain(
      "GRANT EXECUTE ON FUNCTION omi_memory.read_durable_work_staged_result(text, text)",
    );
    expect(allSql).not.toMatch(/GRANT\s+(?:SELECT|INSERT)[^;]*memory_work_staged_results/s);
    expect(allSql).toContain("CREATE FUNCTION omi_memory.read_durable_work_success_bundle");
    expect(allSql).toContain("CREATE FUNCTION omi_memory.insert_durable_work_success_result");
    expect(allSql).toContain("s.state_digest = requested_leased_state_digest");
    expect(allSql).toContain("s.worker_id = requested_worker_id");
    expect(allSql).toContain("current_setting('omi.principal_id', true)");
    expect(allSql).toContain(
      "GRANT EXECUTE ON FUNCTION omi_memory.read_durable_work_success_bundle(text, text)",
    );
    expect(allSql).not.toMatch(
      /GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE)[^;]*memory_work_success_results/s,
    );
  });

  test("stages exact sensitive formation input before acceptance and fences restart reads", () => {
    const input = tables.find((table) => table.name === "memory_formation_work_inputs")!;
    expect(input.body).toContain("formation-work-staged-input-v1");
    expect(input.body).toContain("staged_input_id ~ '^fwi1_[0-9a-f]{64}$'");
    expect(input.body).toContain("PRIMARY KEY (account_id, job_id)");
    expect(input.body).toContain("snapshot_version = 'formation-input-snapshot-v1'");
    expect(input.body).toContain("jsonb_typeof(snapshot_json) = 'object'");
    expect(input.body).toContain("octet_length(snapshot_json::text) <= 524288");
    expect(allSql).toContain("memory_formation_acceptance_requires_input");
    expect(allSql).toContain("DEFERRABLE INITIALLY DEFERRED");
    expect(allSql).toContain("CREATE FUNCTION omi_memory.read_formation_work_input");
    expect(allSql).toContain("CREATE FUNCTION omi_memory.insert_formation_work_input");
    expect(allSql).toContain("capability NOT IN ('memories.work.accept', 'memories.work.execute')");
    expect(allSql).toContain("s.worker_id = current_setting('omi.principal_id', true)");
    expect(allSql).toContain("GRANT EXECUTE ON FUNCTION omi_memory.read_formation_work_input");
    expect(allSql).not.toMatch(
      /GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE)[^;]*memory_formation_work_inputs/s,
    );
  });

  test("stages exact predicate-batch input before acceptance and fences restart reads", () => {
    const input = tables.find((table) => table.name === "memory_predicate_batch_work_inputs")!;
    expect(input.body).toContain("predicate-batch-work-staged-input-v1");
    expect(input.body).toContain("staged_input_id ~ '^pwi1_[0-9a-f]{64}$'");
    expect(input.body).toContain("PRIMARY KEY (account_id, job_id)");
    expect(input.body).toContain("snapshot_version = 'predicate-batch-input-snapshot-v1'");
    expect(input.body).toContain("jsonb_typeof(snapshot_json) = 'object'");
    expect(input.body).toContain("octet_length(snapshot_json::text) <= 524288");
    expect(allSql).toContain("memory_predicate_batch_acceptance_requires_input");
    expect(allSql).toContain("CREATE FUNCTION omi_memory.read_predicate_batch_work_input");
    expect(allSql).toContain("CREATE FUNCTION omi_memory.insert_predicate_batch_work_input");
    expect(allSql).toContain("capability NOT IN ('memories.work.accept', 'memories.work.execute')");
    expect(allSql).toContain("s.worker_id = current_setting('omi.principal_id', true)");
    expect(allSql).toContain("GRANT EXECUTE ON FUNCTION omi_memory.read_predicate_batch_work_input");
    expect(allSql).not.toMatch(
      /GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE)[^;]*memory_predicate_batch_work_inputs/s,
    );
  });

  test("binds accepted work to one authority strategy while shadows remain non-authoritative", () => {
    const definitions = tables.find((table) => table.name === "memory_strategy_definitions")!;
    expect(definitions.body).toContain("execution_contract_digest text NOT NULL");
    expect(definitions.body).toContain("result_contract_version text NOT NULL");
    expect(definitions.body).toContain("speaker_strategy_version text NOT NULL");
    expect(definitions.body).toContain("boundary_strategy_version text NOT NULL");

    const policy = tables.find((table) => table.name === "memory_strategy_assignment_policies")!;
    expect(policy.body).toContain("policy_version = 'memory-strategy-assignment-policy-v1'");
    expect(policy.body).toContain("unit_kind IN ('account', 'session', 'work')");
    expect(policy.body).toContain("key_version text NOT NULL");
    const policyShadows = tables.find((table) => table.name === "memory_strategy_policy_shadows")!;
    expect(policyShadows.body).toContain("basis_points BETWEEN 0 AND 10000");

    const bundles = tables.find((table) => table.name === "memory_strategy_assignment_bundles")!;
    expect(bundles.body).toContain("assignment_bundle_id ~ '^msb1_[0-9a-f]{64}$'");
    expect(bundles.body).toContain("unit_digest text NOT NULL");
    expect(bundles.body).not.toMatch(/unit_ref|session_id|prompt|transcript|evidence|query|answer|model_output/i);

    const shadows = tables.find((table) => table.name === "memory_strategy_shadow_assignments")!;
    expect(shadows.body).toContain("CHECK (bucket < basis_points)");
    expect(shadows.body).not.toMatch(/job_id|commit_id|revision_id|projection/i);

    const acceptance = tables.find((table) => table.name === "memory_work_acceptances")!;
    expect(allSql).toContain("memory_work_acceptances_authority_assignment_fk");
    expect(allSql).toContain("authority_strategy_id, execution_contract_digest");
    expect(acceptance.body).not.toContain("shadow");
    const acceptanceRuntime = migrationSql.find((entry) => entry.version === 14)!.sql;
    for (const table of [
      "memory_strategy_definitions",
      "memory_strategy_assignment_policies",
      "memory_strategy_policy_shadows",
      "memory_strategy_assignment_bundles",
      "memory_strategy_shadow_assignments",
    ]) {
      expect(acceptanceRuntime).toContain(`GRANT SELECT, INSERT ON omi_memory.${table}`);
    }
    expect(acceptanceRuntime).not.toMatch(/GRANT[^;]*\b(?:UPDATE|DELETE|TRUNCATE)\b/s);
    expect(acceptanceRuntime).not.toMatch(/GRANT[^;]*memory_work_(?:staged_results|success_results|outbox_events)/s);
  });

  test("keeps repeated paired evaluation results physically outside memory authority", () => {
    const baselines = tables.find((table) => table.name === "memory_strategy_evaluation_baselines")!;
    const candidates = tables.find((table) => table.name === "memory_strategy_shadow_results")!;
    const pairs = tables.find((table) => table.name === "memory_strategy_evaluation_pairs")!;
    expect(baselines.body).toContain("result_version = 'memory-evaluation-result-v1'");
    expect(baselines.body).toContain("authority_assignment_id, authority_strategy_id");
    expect(candidates.body).toContain("memory_strategy_shadow_assignments");
    expect(candidates.body).toContain("repeat_ordinal BETWEEN 0 AND 999");
    expect(candidates.body).toContain("octet_length(normalized_result_json::text) <= 524288");
    expect(pairs.body).toContain("pair_version = 'memory-evaluation-pair-v1'");
    expect(pairs.body).toContain("input_frontier_digest");
    expect(pairs.body).not.toMatch(/\binput_frontier\s+text\b/);
    expect(pairs.body).toContain("baseline_strategy_id <> candidate_strategy_id");
    expect(pairs.body).not.toMatch(/normalized_result_json|response_digest|prompt|transcript|query|answer/i);
    for (const table of [baselines, candidates, pairs]) {
      expect(table.body).not.toMatch(/graph_commit|projection_revision|memory_work_success/i);
    }
    expect(allSql).toContain("Deliberately no application, worker, evaluator, or migration-runner grant");
    const experimentRuntime = migrationSql.find((entry) => entry.version === 23)!.sql;
    for (const table of [
      "memory_strategy_evaluation_baselines",
      "memory_strategy_shadow_results",
      "memory_strategy_evaluation_pairs",
    ]) {
      expect(experimentRuntime).toContain(`GRANT SELECT, INSERT ON omi_memory.${table}`);
    }
    expect(experimentRuntime).not.toMatch(/GRANT[^;]*\b(?:UPDATE|DELETE|TRUNCATE)\b/s);
  });

  test("widens retrieval and composition only inside the isolated experiment plane", () => {
    const migration = migrationSql.find((entry) => entry.version === 10)!.sql;
    const widenedTables = [
      "memory_strategy_definitions",
      "memory_strategy_assignment_policies",
      "memory_strategy_policy_shadows",
      "memory_strategy_assignment_bundles",
      "memory_strategy_shadow_assignments",
      "memory_strategy_evaluation_baselines",
      "memory_strategy_shadow_results",
    ];
    for (const table of widenedTables) {
      expect(migration).toContain(`ALTER TABLE omi_memory.${table}`);
      expect(migration).toContain(`DROP CONSTRAINT ${table}_work_kind_check`);
      expect(migration).toContain(`ADD CONSTRAINT ${table}_work_kind_check`);
    }
    expect((migration.match(/'retrieval', 'composition'/g) ?? [])).toHaveLength(7);
    expect(migration).not.toMatch(/ALTER TABLE omi_memory\.memory_(?:work_|graph_|product_|derivation_)/);
    expect(migration).not.toMatch(/\b(?:GRANT|CREATE ROLE|CREATE FUNCTION|CREATE TRIGGER|DELETE|UPDATE)\b/);
    const acceptance = tables.find((table) => table.name === "memory_work_acceptances")!;
    expect(acceptance.body).toContain("'formation', 'promotion', 'identity_cluster', 'predicate_batch'");
    expect(acceptance.body).not.toMatch(/retrieval|composition/);
  });

  test("keeps finalized read grounding one-to-one, sensitive, and outside authority", () => {
    const baseline = tables.find((table) => table.name === "memory_strategy_baseline_read_groundings")!;
    const candidate = tables.find((table) => table.name === "memory_strategy_candidate_read_groundings")!;
    for (const table of [baseline, candidate]) {
      expect(table.body).toContain("artifact_version = 'finalized-query-grounding-v1'");
      expect(table.body).toContain("result_contract_version = 'memory-read-evaluation-result-v1'");
      expect(table.body).toContain("UNIQUE (account_id, evaluation_result_id)");
      expect(table.body).toContain("jsonb_array_length(rows_json) = grounded_reference_count");
      expect(table.body).toContain("projection_authorization_digest text NOT NULL");
      expect(table.body).toContain("reader_projection_digest text NOT NULL");
      expect(table.body).toContain("projected_content_digest text NOT NULL");
      expect(table.body).not.toMatch(/\b(?:query_text|answer_text|transcript|excerpt|evidence_id|claim_revision_id)\b/i);
      expect(table.body).not.toMatch(/graph_commit|projection_revision|memory_work_success/i);
    }
    expect(baseline.body).toContain("memory_strategy_evaluation_baselines");
    expect(candidate.body).toContain("memory_strategy_shadow_results");
    expect(allSql).toContain("A grounding artifact cannot authorize a graph/product/read result or memory work");
    const experimentRuntime = migrationSql.find((entry) => entry.version === 23)!.sql;
    for (const table of [
      "memory_strategy_baseline_read_groundings",
      "memory_strategy_candidate_read_groundings",
    ]) {
      expect(experimentRuntime).toContain(`GRANT SELECT, INSERT ON omi_memory.${table}`);
    }
    expect(experimentRuntime).not.toMatch(/GRANT[^;]*\b(?:UPDATE|DELETE|TRUNCATE)\b/s);
  });

  test("keeps restart-safe query inputs sensitive, snapshot-bound, and outside graph authority", () => {
    const input = tables.find((table) => table.name === "memory_query_evaluation_inputs")!;
    expect(input.body).toContain("input_version = 'memory-query-evaluation-input-v1'");
    expect(input.body).toContain("graph_snapshot_digest text NOT NULL");
    expect(input.body).toContain("graph_generation bigint NOT NULL");
    expect(input.body).toContain("query_text text NOT NULL");
    expect(input.body).toContain("account_timezone text NOT NULL");
    expect(input.body).not.toMatch(/graph_snapshot_json|answer|prompt|grade|label|statistic/i);
    const runtime = migrationSql.find((entry) => entry.version === 24)!.sql;
    expect(runtime).toContain("GRANT SELECT, INSERT ON omi_memory.memory_query_evaluation_inputs");
    expect(runtime).not.toMatch(/GRANT[^;]*\b(?:UPDATE|DELETE|TRUNCATE)\b/s);
    expect(runtime).not.toMatch(/GRANT[^;]*memory_(?:graph|product|work_|revisions)/s);
  });

  test("persists P4 product state with only the sealed writer's append grants", () => {
    const mapping = tables.find((table) => table.name === "memory_legacy_proposition_mappings")!;
    expect(mapping.body).toContain("PRIMARY KEY (account_id, legacy_source_id)");
    expect(mapping.body).toContain("allocation_contract = 'random_opaque_v1'");
    expect(mapping.body).toContain("UNIQUE (account_id, proposition_id)");

    const tombstone = tables.find((table) => table.name === "memory_migration_item_tombstones")!;
    expect(tombstone.body).toContain("PRIMARY KEY (account_id, legacy_source_id)");
    expect(tombstone.body).toContain("tombstone_operation_id text NOT NULL");

    const proposition = tables.find((table) => table.name === "memory_product_propositions")!;
    expect(proposition.body).toContain("product_contract_version = 'product-projection-v1'");
    expect(proposition.body).toContain("birth_claim_lineage_id text NOT NULL");
    expect(proposition.body).toContain("FOREIGN KEY (account_id, birth_commit_id, birth_commit_sequence)");
    expect(proposition.body).toContain("origin IN ('native', 'legacy_mapping')");
    expect(proposition.body).toContain("memory_legacy_proposition_mappings");
    expect(proposition.body).toContain("proposition_id !~ '^grp1_[0-9a-f]{64}$'");

    const membership = tables.find((table) => table.name === "memory_product_membership_revisions")!;
    expect(membership.body).toContain("membership_revision_id ~ '^pmr1_[0-9a-f]{64}$'");
    expect(membership.body).toContain("'birth', 'ledger_consolidation', 'correction', 'product_successor'");
    expect(membership.body).toContain("FOREIGN KEY (account_id, proposition_id, parent_membership_revision_id)");
    expect(membership.body).toContain("FOREIGN KEY (account_id, graph_commit_id, graph_commit_sequence)");
    expect(membership.body).toContain("cause = 'birth' AND revision_sequence = 1");

    const membershipLineages = tables.find((table) => table.name === "memory_product_membership_claim_lineages")!;
    expect(membershipLineages.body).toContain("FOREIGN KEY (account_id, claim_lineage_id)");
    expect(membershipLineages.body).toContain("UNIQUE (account_id, membership_revision_id, claim_lineage_id)");

    const projection = tables.find((table) => table.name === "memory_product_projection_revisions")!;
    expect(projection.body).toContain("projection_revision_id ~ '^pvr1_[0-9a-f]{64}$'");
    expect(projection.body).toContain("UNIQUE (account_id, proposition_id, projection_sequence)");
    expect(projection.body).toContain("account_id, proposition_id, membership_revision_id, graph_frontier");
    expect(projection.body).toContain("graph_commit_id, graph_commit_sequence");
    expect(allSql).toContain("memory_product_projection_revisions_payload_fk");
    expect(allSql).toContain("DEFERRABLE INITIALLY DEFERRED");

    const payload = tables.find((table) => table.name === "memory_product_projection_payloads")!;
    expect(payload.body).toContain("rendered_content_json jsonb NOT NULL");
    expect(payload.body).toContain("rendered_content_digest text NOT NULL");

    const citations = tables.find((table) => table.name === "memory_product_projection_citations")!;
    expect(citations.body).toContain("memory_product_membership_claim_lineages");
    expect(citations.body).toContain("account_id, claim_lineage_id, claim_revision_id");
    const citationEvidence = tables.find((table) => table.name === "memory_product_projection_citation_evidence_refs")!;
    expect(citationEvidence.body).toContain("account_id, claim_revision_id, evidence_id");
    expect(citationEvidence.body).toContain("memory_claim_evidence_refs");

    const redirects = tables.find((table) => table.name === "memory_product_redirects")!;
    expect(redirects.body).toContain("UNIQUE (account_id, source_proposition_id)");
    expect(redirects.body).toContain("operation IN ('merge', 'split')");
    const successors = tables.find((table) => table.name === "memory_product_redirect_successors")!;
    expect(successors.body).toContain("CHECK (source_proposition_id <> successor_proposition_id)");

    const groups = tables.filter((table) => table.name.startsWith("memory_product_group_"));
    expect(groups).toHaveLength(2);
    expect(groups.map((table) => table.name).sort()).toEqual([
      "memory_product_group_members", "memory_product_group_projections",
    ]);
    expect(groups.find((table) => table.name === "memory_product_group_projections")!.body)
      .toContain("FOREIGN KEY (account_id, graph_commit_id, graph_commit_sequence)");
    for (const table of tables.filter((candidate) => !candidate.name.startsWith("memory_product_group_"))) {
      expect(table.body, `${table.name} cannot depend on grouping`).not.toContain("group_projection_id");
    }

    const receipts = tables.find((table) => table.name === "memory_product_operation_receipts")!;
    expect(receipts.body).toContain("PRIMARY KEY (account_id, request_digest)");
    expect(receipts.body).toContain("UNIQUE (account_id, operation, operation_identity)");
    expect(receipts.body).toContain("operation IN (\n    'birth', 'membership', 'projection', 'redirect', 'group'");
    expect(receipts.body).toContain("receipt_contract_version = 'product-operation-receipt-v1'");
    expect(receipts.body).toContain("account_id, graph_commit_id, graph_commit_sequence");
    expect(allSql).toContain("product-projection runtime idempotency substrate");
    expect(allSql).toContain("Deliberately no application, projector, reader, worker, or migration-copier");

    const baseProductSql = migrationSql.find((migration) => migration.version === 5)!.sql;
    expect(baseProductSql).toContain("Deliberately no application, migration-copier, projector, or worker grant");
    expect(baseProductSql).not.toMatch(/GRANT[^;]*omi_memory\.memory_(?:product_|legacy_proposition|migration_item)/s);
    const writerGrantSql = migrationSql.find((migration) => migration.version === 22)!.sql;
    expect(writerGrantSql).toContain("P4 inert projector-writer grants");
    for (const table of tables.filter((candidate) => candidate.name.startsWith("memory_product_"))) {
      expect(writerGrantSql).toContain(
        `GRANT SELECT, INSERT ON omi_memory.${table.name} TO omi_platform_application;`,
      );
    }
    const writerGrantStatements = writerGrantSql.replace(/^--.*$/gm, "");
    expect(writerGrantStatements).not.toMatch(/\b(?:UPDATE|DELETE|TRUNCATE|CREATE|ALTER|DROP)\b/);
    expect(writerGrantSql).not.toMatch(/memory_(?:legacy_proposition|migration_item)/);
  });
});
