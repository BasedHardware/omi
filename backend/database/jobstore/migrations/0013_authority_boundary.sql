-- A durable authority row must not become an "unregistered" legacy namespace.
-- Reverse certificates are not implemented yet: fail closed in SQL, including
-- callers that bypass the Python transition helper. No session flag opens FS.
-- contract: remove destructive authority privileges and reject destructive SQL;
-- the TRUNCATE trigger below prevents truncation and removes no retained data.
CREATE FUNCTION queue_authority_boundary() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP IN ('DELETE','TRUNCATE') THEN
  RAISE EXCEPTION 'queue authority cannot be removed' USING ERRCODE='42501';
 END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.state <> 'FS_OPEN' OR NEW.epoch <> 0 OR NEW.committed_seq <> 0
     OR NEW.applied_seq <> 0 OR NOT NEW.copier_stopped THEN
   RAISE EXCEPTION 'queue authority must bootstrap closed to PG at epoch zero' USING ERRCODE='42501';
  END IF;
 ELSE
  IF NEW.namespace IS DISTINCT FROM OLD.namespace THEN
   RAISE EXCEPTION 'queue authority namespace is immutable' USING ERRCODE='42501';
  END IF;
  IF NEW.state='FS_OPEN' AND OLD.state <> 'FS_OPEN' THEN
   RAISE EXCEPTION 'verified reverse certificate integration required' USING ERRCODE='42501';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER queue_authority_boundary BEFORE INSERT OR UPDATE OR DELETE ON queue_authority
 FOR EACH ROW EXECUTE FUNCTION queue_authority_boundary();
CREATE TRIGGER queue_authority_no_truncate BEFORE TRUNCATE ON queue_authority
 FOR EACH STATEMENT EXECUTE FUNCTION queue_authority_boundary();
REVOKE DELETE, TRUNCATE ON queue_authority FROM PUBLIC;
