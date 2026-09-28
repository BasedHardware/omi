-- Derived-group recall read seam: account-scoped, capability-gated reads of the
-- rebuildable group projections and attribution belief revisions that
-- `persist_derived_group_dream_materialization` (0043) already commits.
--
-- This adds no table, no route, no grant issuer, and no scheduler. It is the
-- first SQL surface to *check* `memories.read`, which is the scope the dark
-- query doors already declare. Neither function mutates, and neither returns a
-- row outside the session's own account.
--
-- Scope of that guarantee, stated exactly: for
-- `memory_attribution_belief_revisions` the definer function is the only door,
-- because 0043 revokes and never grants it. For the group projections it is
-- NOT the only door — `0022-product-projection-writer-grants.sql` already
-- grants `omi_platform_application` a direct `SELECT` on
-- `memory_product_group_projections` and `memory_product_group_members`, and
-- the schema has no row-level security. So this capability check binds callers
-- that come through this function; it does not fence the role. Closing that
-- gap means revoking the direct grant, which is a separate decision.
--
-- Both functions take an explicit row bound. Recall must never answer from a
-- silently truncated group set, so the caller asks for one more row than it
-- can accept and fails closed on overflow rather than paging blindly.

CREATE FUNCTION omi_memory.read_derived_group_projections(
  requested_account_id text,
  requested_limit integer
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

  IF requested_limit IS NULL OR requested_limit < 1 OR requested_limit > 4096 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'derived group projection read bound invalid';
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
  ORDER BY g.group_projection_id
  LIMIT requested_limit;
END;
$$;

CREATE FUNCTION omi_memory.read_attribution_belief_revisions(
  requested_account_id text,
  requested_limit integer
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

  IF requested_limit IS NULL OR requested_limit < 1 OR requested_limit > 4096 THEN
    RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'attribution belief read bound invalid';
  END IF;

  RETURN QUERY
  SELECT
    b.account_id, b.belief_revision_id, b.belief_lineage_id, b.belief_kind,
    b.graph_frontier, b.revision_contract_version, b.revision_json,
    b.content_hash
  FROM omi_memory.memory_attribution_belief_revisions AS b
  WHERE b.account_id = requested_account_id
  ORDER BY b.belief_revision_id
  LIMIT requested_limit;
END;
$$;

REVOKE ALL ON FUNCTION omi_memory.read_derived_group_projections(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.read_attribution_belief_revisions(text, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.read_derived_group_projections(text, integer)
  TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.read_attribution_belief_revisions(text, integer)
  TO omi_platform_application;
