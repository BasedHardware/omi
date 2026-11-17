-- Keep the dispatch identity after registry retirement. Lease expiry and
-- restored admissions must never turn an ambiguous send into another POST.
ALTER TABLE units ADD COLUMN provider_effect_id uuid;
CREATE FUNCTION typed_provider_effect_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.provider_effect_id IS NOT NULL
    AND NEW.provider_effect_id IS DISTINCT FROM OLD.provider_effect_id THEN
  RAISE EXCEPTION 'provider effect identity is immutable' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER typed_provider_effect_immutable BEFORE UPDATE ON units
 FOR EACH ROW EXECUTE FUNCTION typed_provider_effect_immutable();

-- A result transition cannot leave the START row unresolved in another COMMIT.
-- COMPLETE deletes it only after the guarded unit/counter/outbox mutation.
CREATE FUNCTION typed_provider_effect_completion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.provider_effect_id IS NOT NULL AND NEW.state='result_ready'
    AND EXISTS (SELECT 1 FROM privacy_effect_inflight WHERE effect_id=NEW.provider_effect_id) THEN
  RAISE EXCEPTION 'provider terminal result requires grouped effect COMPLETE' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER typed_provider_effect_completion AFTER INSERT OR UPDATE ON units
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION typed_provider_effect_completion();
