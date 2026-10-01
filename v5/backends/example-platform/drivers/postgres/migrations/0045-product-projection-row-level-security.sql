-- Close the projector-role read fence.
--
-- `0022` grants `omi_platform_application` a direct `SELECT` on the product
-- projection tables, for transactional validation and replay. That SELECT is
-- load-bearing, so it cannot simply be revoked. But with no row-level security
-- it also means any code holding the application role can read projection rows
-- for ANY account, going around the `memories.read` capability check that the
-- `0044` SECURITY DEFINER readers enforce. The capability check bound callers
-- coming through the function; it did not fence the role.
--
-- Row-level security keyed to the transaction-local `omi.account_id` closes
-- that gap without touching the grant. `omi.account_id` is set by
-- `SET_LOCAL_AUTHORITY_CONTEXT` in `drivers/postgres/transaction.ts` and is
-- validated against the database-locked authority row before any statement
-- runs, so it is not a caller assertion.
--
-- `current_setting('omi.account_id', true)` is NULL when unset, and
-- `account_id = NULL` is NULL rather than true, so an unauthorized session sees
-- zero rows rather than everything. This fails closed.
--
-- The table owner is exempt from row-level security unless FORCE is set, which
-- is deliberate here: the SECURITY DEFINER writers and readers
-- (`persist_derived_group_dream_materialization`, `read_derived_group_projections`,
-- `read_attribution_belief_revisions`) run as the owner and must keep working.
-- They enforce their own account and capability checks.
--
-- This adds no grant, route, role, or policy for any other principal.

DO $rls$
DECLARE
  target text;
BEGIN
  FOREACH target IN ARRAY ARRAY[
    'memory_product_propositions',
    'memory_product_membership_revisions',
    'memory_product_membership_claim_lineages',
    'memory_product_projection_revisions',
    'memory_product_projection_payloads',
    'memory_product_projection_citations',
    'memory_product_projection_citation_evidence_refs',
    'memory_product_redirects',
    'memory_product_redirect_successors',
    'memory_product_group_projections',
    'memory_product_group_members',
    'memory_product_operation_receipts'
  ]
  LOOP
    EXECUTE format(
      'ALTER TABLE omi_memory.%I ENABLE ROW LEVEL SECURITY', target);
    EXECUTE format(
      'CREATE POLICY %I ON omi_memory.%I FOR ALL TO omi_platform_application '
      'USING (account_id = current_setting(''omi.account_id'', true)) '
      'WITH CHECK (account_id = current_setting(''omi.account_id'', true))',
      target || '_own_account', target);
  END LOOP;
END
$rls$;
