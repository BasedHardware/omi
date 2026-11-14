-- Serialize every census/progress mutation and original custodian deletion
-- BEFORE its statement, rather than racing an uncommitted first census.
-- Do not acquire/upgrade locks inside triggers: the caller owns the bounded,
-- sorted L_x protocol and reads state in separate statements after grant.
CREATE FUNCTION retained_copy_require_owner_lock() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE value jsonb; owner text;
BEGIN
 IF TG_OP='DELETE' THEN value=to_jsonb(OLD); ELSE value=to_jsonb(NEW); END IF;
 -- The legacy unregistered document-store outbox retains its existing path.
 IF TG_TABLE_NAME='outbox' AND NOT EXISTS (
   SELECT 1 FROM queue_authority WHERE namespace=value->>'namespace') THEN
  RETURN OLD;
 END IF;
 owner=coalesce(value->>'owner_key',value->>'owner_id');
 IF owner IS NULL OR NOT EXISTS (
   SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'
    AND granted AND mode='ExclusiveLock' AND objsubid=1
    AND classid=((privacy_lock_key(owner) >> 32) & 4294967295)::oid
    AND objid=(privacy_lock_key(owner) & 4294967295)::oid) THEN
  RAISE EXCEPTION 'exclusive privacy owner lock required before custody mutation' USING ERRCODE='42501';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER a_retained_copy_census_owner_lock BEFORE INSERT OR UPDATE OR DELETE ON queue_retained_copy_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_retained_copy_handoff_owner_lock BEFORE DELETE ON queue_handoffs
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_retained_copy_unit_owner_lock BEFORE DELETE ON units
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_retained_copy_recording_owner_lock BEFORE DELETE ON recordings
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_retained_copy_custody_owner_lock BEFORE DELETE ON queue_custody
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_retained_copy_journal_owner_lock BEFORE UPDATE OR DELETE ON queue_journal
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
CREATE TRIGGER a_retained_copy_outbox_owner_lock BEFORE DELETE ON outbox
 FOR EACH ROW EXECUTE FUNCTION retained_copy_require_owner_lock();
