-- Derived-group recall read seam: account-scoped, capability-gated reads of the
-- rebuildable group projections and attribution belief revisions that
-- `persist_derived_group_dream_materialization` (0043) already commits.
--
-- This adds no table, no route, no grant issuer, and no scheduler. It is the
-- first SQL surface gated on `memories.read`, which is the scope the dark query
-- doors already declare. Reads stay owner-scoped and append-only-observing:
-- neither function mutates, and neither can widen an account boundary.

CREATE FUNCTION omi_memory.read_derived_group_projections(
  requested_account_id text
)
RETURNS TABLE (
  account_id text,
  group_projection_id text,
  input_frontier text,
  projection_contract_digest text,
  result_digest text,
  created_at_event_time bigint,
  content_hash text,
  proposition_ids text[]
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.read'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'derived group projection read denied';
  END IF;

  RETURN QUERY
  SELECT
    g.account_id, g.group_projection_id, g.input_frontier,
    g.projection_contract_digest, g.result_digest, g.created_at_event_time,
    g.content_hash,
    COALESCE((
      SELECT array_agg(m.proposition_id ORDER BY m.member_ordinal)
      FROM omi_memory.memory_product_group_members AS m
      WHERE m.account_id = g.account_id
        AND m.group_projection_id = g.group_projection_id
    ), ARRAY[]::text[])
  FROM omi_memory.memory_product_group_projections AS g
  WHERE g.account_id = requested_account_id
  ORDER BY g.group_projection_id;
END;
$$;

CREATE FUNCTION omi_memory.read_attribution_belief_revisions(
  requested_account_id text
)
RETURNS TABLE (
  account_id text,
  belief_revision_id text,
  belief_lineage_id text,
  belief_kind text,
  graph_frontier text,
  revision_contract_version text,
  revision_json jsonb,
  content_hash text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $$
BEGIN
  IF current_setting('omi.account_id', true) IS DISTINCT FROM requested_account_id
     OR current_setting('omi.capability', true) IS DISTINCT FROM 'memories.read'
     OR nullif(current_setting('omi.principal_id', true), '') IS NULL
  THEN
    RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'attribution belief read denied';
  END IF;

  RETURN QUERY
  SELECT
    b.account_id, b.belief_revision_id, b.belief_lineage_id, b.belief_kind,
    b.graph_frontier, b.revision_contract_version, b.revision_json,
    b.content_hash
  FROM omi_memory.memory_attribution_belief_revisions AS b
  WHERE b.account_id = requested_account_id
  ORDER BY b.belief_revision_id;
END;
$$;

REVOKE ALL ON FUNCTION omi_memory.read_derived_group_projections(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_attribution_belief_revisions(text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_derived_group_projections(text)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.read_attribution_belief_revisions(text)
  TO omi_platform_application;
