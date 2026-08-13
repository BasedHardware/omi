import type { DeletionCleanupSurface } from "../../core/control/deletion-cleanup-inventory";

/**
 * Closed PostgreSQL table ownership for deletion inventory v3. Tables absent
 * from this registry are a schema-review failure, not an implicit no-op.
 * External/legacy surfaces intentionally have no PostgreSQL tables here.
 */
export const POSTGRES_DELETION_SURFACE_TABLES = Object.freeze({
  durable_work: Object.freeze([
    "memory_work_acceptances", "memory_work_execution_policies", "memory_work_heads",
    "memory_work_input_manifest", "memory_work_outbox_events", "memory_work_state_revisions",
    "memory_work_success_results",
  ]),
  staged_results: Object.freeze([
    "memory_work_staged_results", "memory_formation_work_inputs",
    "memory_predicate_batch_work_inputs", "memory_query_evaluation_inputs",
    "memory_candidate_derivation_artifacts",
  ]),
  authoritative_memory: Object.freeze([
    "memory_claim_evidence_refs", "memory_claim_lineages", "memory_claim_liveness_fences",
    "memory_claim_predicate_refs", "memory_claim_revisions", "memory_claim_source_provisionals",
    "memory_claim_supersessions", "memory_consumed_markers",
    "memory_coreference_support_evidence_refs", "memory_coreference_support_revisions",
    "memory_derivation_attempts", "memory_derivation_commits", "memory_derivation_inputs",
    "memory_entity_identities", "memory_entity_revisions", "memory_event_identities",
    "memory_event_revisions", "memory_evidence_identities", "memory_evidence_revisions",
    "memory_formation_extraction_evidence", "memory_formation_extraction_outcomes",
    "memory_formation_outcomes", "memory_formation_placement_outcomes",
    "memory_generated_adjacency", "memory_graph_heads", "memory_idempotency_receipts",
    "memory_identity_authorization_identities", "memory_identity_authorization_entity_endpoints",
    "memory_identity_authorization_revisions", "memory_identity_authorization_support",
    "memory_identity_constraint_entity_endpoints", "memory_identity_revisions",
    "memory_identity_support", "memory_mention_revisions", "memory_placement_artifacts",
    "memory_predicate_assertion_revisions", "memory_predicate_identities",
    "memory_predicate_revisions", "memory_revisions", "memory_source_local_claim_roles",
  ]),
  account_access: Object.freeze([
    "application_credential_heads", "application_credential_revisions",
    "application_grant_heads", "application_grant_revisions",
    "firebase_application_credential_bindings", "firebase_identity_bindings",
  ]),
  experiment_results: Object.freeze([
    "memory_strategy_assignment_bundles", "memory_strategy_assignment_policies",
    "memory_strategy_baseline_read_groundings", "memory_strategy_candidate_read_groundings",
    "memory_strategy_definitions", "memory_strategy_evaluation_baselines",
    "memory_strategy_evaluation_pairs", "memory_strategy_policy_shadows",
    "memory_strategy_shadow_assignments", "memory_strategy_shadow_results",
  ]),
  product_projections: Object.freeze([
    "memory_product_membership_claim_lineages", "memory_product_membership_revisions",
    "memory_product_operation_receipts", "memory_product_projection_citation_evidence_refs",
    "memory_product_projection_citations", "memory_product_projection_payloads",
    "memory_product_projection_revisions", "memory_product_propositions",
    "memory_product_redirect_successors", "memory_product_redirects",
  ]),
  rebuildable_groups_indexes: Object.freeze([
    "memory_product_group_members", "memory_product_group_projections",
  ]),
  migration_state: Object.freeze([
    "memory_legacy_proposition_mappings", "memory_migration_item_tombstones",
  ]),
} satisfies Partial<Record<DeletionCleanupSurface, readonly string[]>>);

/** Content-free authority needed to prevent resurrection; never disposable. */
export const POSTGRES_RETAINED_DELETION_SAFETY_TABLES = Object.freeze([
  "platform_schema_migrations",
  "platform_accounts",
  "account_control_revisions",
  "account_control_heads",
  "account_terminal_deletion_exports",
]);
