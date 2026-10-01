CREATE SEQUENCE omi_memory.listen_conversation_ingest_sequence AS bigint MAXVALUE 9007199254740991;
ALTER TABLE omi_memory.listen_capture_sessions ADD COLUMN conversation_sequence bigint;
WITH ordered AS (
  SELECT account_id,session_id,row_number() OVER (ORDER BY started_at,account_id,session_id) AS sequence
  FROM omi_memory.listen_capture_sessions
)
UPDATE omi_memory.listen_capture_sessions u SET conversation_sequence=ordered.sequence
FROM ordered WHERE u.account_id=ordered.account_id AND u.session_id=ordered.session_id;
SELECT setval('omi_memory.listen_conversation_ingest_sequence',coalesce(max(conversation_sequence),1),count(*)>0)
FROM omi_memory.listen_capture_sessions;
ALTER TABLE omi_memory.listen_capture_sessions ALTER COLUMN conversation_sequence SET NOT NULL;
ALTER TABLE omi_memory.listen_capture_sessions ALTER COLUMN conversation_sequence SET DEFAULT nextval('omi_memory.listen_conversation_ingest_sequence');
ALTER TABLE omi_memory.listen_capture_sessions ADD UNIQUE(conversation_sequence);
CREATE TABLE omi_memory.listen_conversation_read_revisions (
  account_id text PRIMARY KEY REFERENCES omi_memory.platform_accounts(account_id),
  revision bigint NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991)
);
INSERT INTO omi_memory.listen_conversation_read_revisions(account_id,revision)
SELECT account_id,count(*) FROM omi_memory.listen_capture_sessions GROUP BY account_id;
CREATE FUNCTION omi_memory.bump_listen_conversation_read_revision()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
BEGIN
  INSERT INTO omi_memory.listen_conversation_read_revisions(account_id,revision) VALUES(NEW.account_id,1)
    ON CONFLICT(account_id) DO UPDATE SET revision=omi_memory.listen_conversation_read_revisions.revision+1;
  RETURN NEW;
END $function$;
REVOKE ALL ON FUNCTION omi_memory.bump_listen_conversation_read_revision() FROM PUBLIC;
CREATE TRIGGER listen_conversation_upload_revision AFTER INSERT OR UPDATE OF upload_completed_at
ON omi_memory.listen_capture_audio_uploads FOR EACH ROW EXECUTE FUNCTION omi_memory.bump_listen_conversation_read_revision();
CREATE TRIGGER listen_conversation_transcript_revision AFTER INSERT OR UPDATE
ON omi_memory.listen_audio_transcriptions FOR EACH ROW EXECUTE FUNCTION omi_memory.bump_listen_conversation_read_revision();
CREATE TRIGGER listen_conversation_intent_revision AFTER INSERT
ON omi_memory.listen_conversation_finalization_intents FOR EACH ROW EXECUTE FUNCTION omi_memory.bump_listen_conversation_read_revision();
CREATE FUNCTION omi_memory.read_listen_conversation_snapshot()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,omi_memory AS $function$
DECLARE v_account text:=nullif(current_setting('omi.account_id',true),''); v_records jsonb; v_revision bigint;
BEGIN
  IF v_account IS NULL OR nullif(current_setting('omi.principal_id',true),'') IS NULL
    OR current_setting('omi.capability',true) IS DISTINCT FROM 'conversations.read' THEN
    RAISE EXCEPTION USING ERRCODE='P1005',MESSAGE='conversation_authority_denied';
  END IF;
  SELECT revision INTO v_revision FROM omi_memory.listen_conversation_read_revisions WHERE account_id=v_account;
  SELECT coalesce(jsonb_agg(to_jsonb(record) ORDER BY record.sequence),'[]'::jsonb) INTO v_records FROM (
    SELECT s.conversation_sequence AS sequence,s.session_id,s.conversation_id,s.source,u.session_id IS NOT NULL AS device,
      s.started_at,coalesce(u.upload_completed_at,f.ended_at) AS ended_at,
      coalesce(t.updated_at,u.upload_completed_at,f.ended_at) AS updated_at,
      CASE WHEN u.session_id IS NULL THEN 'completed' ELSE coalesce(t.state,'queued') END AS state,
      coalesce(i.locked,false) AS locked,
      CASE WHEN u.session_id IS NULL THEN (
        SELECT coalesce(left(string_agg(left(segment.text_content,240),' ' ORDER BY segment.ordinal),240),'')
        FROM omi_memory.listen_capture_segments segment
        WHERE segment.account_id=s.account_id AND segment.session_id=s.session_id AND segment.ordinal<240
      ) WHEN t.state='completed' AND jsonb_typeof(t.provider_result->'segments')='array' THEN (
        SELECT coalesce(left(string_agg(left(segment.value->>'text',240),' ' ORDER BY segment.ordinal),240),'')
        FROM jsonb_array_elements(t.provider_result->'segments') WITH ORDINALITY AS segment(value,ordinal)
        WHERE segment.ordinal<=240
      ) ELSE NULL END AS excerpt
    FROM omi_memory.listen_capture_sessions s
    LEFT JOIN omi_memory.listen_capture_audio_uploads u USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_audio_transcriptions t USING(account_id,session_id)
    LEFT JOIN omi_memory.listen_conversation_finalization_intents i ON i.account_id=s.account_id AND i.conversation_id=s.conversation_id
    LEFT JOIN omi_memory.listen_formation_finalizations f ON f.account_id=s.account_id AND f.session_id=s.session_id
    WHERE s.account_id=v_account AND (u.upload_completed_at IS NOT NULL OR i.finalization_id IS NOT NULL)
    ORDER BY s.conversation_sequence LIMIT 10001
  ) AS record;
  RETURN jsonb_build_object('revision',coalesce(v_revision,0),'records',v_records);
END $function$;
REVOKE ALL ON FUNCTION omi_memory.read_listen_conversation_snapshot() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.read_listen_conversation_snapshot() TO omi_platform_application;

GRANT USAGE ON SEQUENCE omi_memory.listen_conversation_ingest_sequence TO omi_platform_application;
CREATE INDEX listen_conversation_account_sequence ON omi_memory.listen_capture_sessions(account_id,conversation_sequence);
CREATE OR REPLACE FUNCTION omi_memory.cleanup_surface_tables(p_surface text)
RETURNS TABLE(table_name text)
LANGUAGE sql
IMMUTABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT mapping.table_name
  FROM (VALUES
    ('product_projections', 'listen_conversation_read_revisions'),
    ('staged_results', 'listen_audio_transcriptions'),
    ('staged_results', 'listen_capture_audio_uploads'),
    ('staged_results', 'listen_capture_audio_chunks'),
    ('product_projections', 'task_records'),
    ('product_projections', 'task_sequences'),
    ('product_projections', 'task_write_receipts'),
    ('product_projections', 'task_stragglers'),
    ('product_projections', 'memory_render_responses'),
    ('durable_work', 'memory_work_acceptances'),
    ('durable_work', 'memory_work_execution_policies'),
    ('durable_work', 'memory_work_heads'),
    ('durable_work', 'memory_work_input_manifest'),
    ('durable_work', 'memory_work_outbox_events'),
    ('durable_work', 'memory_work_state_revisions'),
    ('durable_work', 'memory_work_success_results'),
    ('staged_results', 'memory_work_staged_results'),
    ('staged_results', 'memory_formation_work_inputs'),
    ('staged_results', 'memory_predicate_batch_work_inputs'),
    ('staged_results', 'memory_derived_group_dream_work_inputs'),
    ('staged_results', 'memory_query_evaluation_inputs'),
    ('staged_results', 'memory_listen_attribution_belief_inputs'),
    ('staged_results', 'memory_candidate_derivation_artifacts'),
    ('staged_results', 'listen_capture_sessions'),
    ('staged_results', 'listen_capture_session_state_revisions'),
    ('staged_results', 'listen_capture_segments'),
    ('staged_results', 'listen_formation_finalizations'),
    ('staged_results', 'listen_conversation_finalization_intents'),
    ('staged_results', 'listen_formation_outbox'),
    ('staged_results', 'listen_formation_delivery_revisions'),
    ('staged_results', 'listen_formation_delivery_heads'),
    ('authoritative_memory', 'memory_attribution_belief_revisions'),
    ('authoritative_memory', 'memory_claim_evidence_refs'),
    ('authoritative_memory', 'memory_claim_lineages'),
    ('authoritative_memory', 'memory_claim_liveness_fences'),
    ('authoritative_memory', 'memory_claim_predicate_refs'),
    ('authoritative_memory', 'memory_claim_revisions'),
    ('authoritative_memory', 'memory_claim_source_provisionals'),
    ('authoritative_memory', 'memory_claim_supersessions'),
    ('authoritative_memory', 'memory_consumed_markers'),
    ('authoritative_memory', 'memory_coreference_support_evidence_refs'),
    ('authoritative_memory', 'memory_coreference_support_revisions'),
    ('authoritative_memory', 'memory_derivation_attempts'),
    ('authoritative_memory', 'memory_derivation_commits'),
    ('authoritative_memory', 'memory_derivation_inputs'),
    ('authoritative_memory', 'memory_entity_identities'),
    ('authoritative_memory', 'memory_entity_revisions'),
    ('authoritative_memory', 'memory_event_identities'),
    ('authoritative_memory', 'memory_event_revisions'),
    ('authoritative_memory', 'memory_evidence_identities'),
    ('authoritative_memory', 'memory_evidence_revisions'),
    ('authoritative_memory', 'memory_formation_extraction_evidence'),
    ('authoritative_memory', 'memory_formation_extraction_outcomes'),
    ('authoritative_memory', 'memory_formation_placement_outcomes'),
    ('authoritative_memory', 'memory_formation_outcomes'),
    ('authoritative_memory', 'memory_generated_adjacency'),
    ('authoritative_memory', 'memory_graph_heads'),
    ('authoritative_memory', 'memory_idempotency_receipts'),
    ('authoritative_memory', 'memory_identity_authorization_identities'),
    ('authoritative_memory', 'memory_identity_authorization_entity_endpoints'),
    ('authoritative_memory', 'memory_identity_authorization_revisions'),
    ('authoritative_memory', 'memory_identity_authorization_support'),
    ('authoritative_memory', 'memory_identity_constraint_entity_endpoints'),
    ('authoritative_memory', 'memory_identity_revisions'),
    ('authoritative_memory', 'memory_identity_support'),
    ('authoritative_memory', 'memory_mention_revisions'),
    ('authoritative_memory', 'memory_placement_artifacts'),
    ('authoritative_memory', 'memory_predicate_assertion_revisions'),
    ('authoritative_memory', 'memory_predicate_identities'),
    ('authoritative_memory', 'memory_predicate_revisions'),
    ('authoritative_memory', 'memory_revisions'),
    ('authoritative_memory', 'memory_source_local_claim_roles'),
    ('account_access', 'application_credential_heads'),
    ('account_access', 'application_credential_revisions'),
    ('account_access', 'application_grant_heads'),
    ('account_access', 'application_grant_revisions'),
    ('account_access', 'firebase_application_credential_bindings'),
    ('account_access', 'firebase_identity_bindings'),
    ('experiment_results', 'memory_strategy_assignment_bundles'),
    ('experiment_results', 'memory_strategy_assignment_policies'),
    ('experiment_results', 'memory_strategy_baseline_read_groundings'),
    ('experiment_results', 'memory_strategy_candidate_read_groundings'),
    ('experiment_results', 'memory_strategy_definitions'),
    ('experiment_results', 'memory_strategy_evaluation_baselines'),
    ('experiment_results', 'memory_strategy_evaluation_pairs'),
    ('experiment_results', 'memory_strategy_policy_shadows'),
    ('experiment_results', 'memory_strategy_shadow_assignments'),
    ('experiment_results', 'memory_strategy_shadow_results'),
    ('product_projections', 'memory_product_membership_claim_lineages'),
    ('product_projections', 'memory_product_membership_revisions'),
    ('product_projections', 'memory_product_operation_receipts'),
    ('product_projections', 'memory_product_projection_citation_evidence_refs'),
    ('product_projections', 'memory_product_projection_citations'),
    ('product_projections', 'memory_product_projection_payloads'),
    ('product_projections', 'memory_product_projection_revisions'),
    ('product_projections', 'memory_product_propositions'),
    ('product_projections', 'memory_product_redirect_successors'),
    ('product_projections', 'memory_product_redirects'),
    ('rebuildable_groups_indexes', 'memory_product_group_members'),
    ('rebuildable_groups_indexes', 'memory_product_group_projections'),
    ('migration_state', 'memory_legacy_proposition_mappings'),
    ('migration_state', 'memory_migration_item_tombstones')
  ) AS mapping(surface, table_name)
  WHERE mapping.surface = p_surface
  ORDER BY mapping.table_name
$function$;
