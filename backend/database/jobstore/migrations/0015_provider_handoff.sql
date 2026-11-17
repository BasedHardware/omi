-- Typed provider custody retains original admission metadata, not a second
-- runnable document queue. Terminal sealing joins the unit/counter transaction.
ALTER TABLE units ADD COLUMN source jsonb NOT NULL DEFAULT '{}';
ALTER TABLE units ADD COLUMN settled_at float8;

CREATE FUNCTION typed_provider_source_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.source IS DISTINCT FROM OLD.source
   OR (OLD.settled_at IS NOT NULL AND NEW.settled_at IS DISTINCT FROM OLD.settled_at) THEN
  RAISE EXCEPTION 'typed provider source/terminal time is immutable' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER typed_provider_source_immutable BEFORE UPDATE ON units
 FOR EACH ROW EXECUTE FUNCTION typed_provider_source_immutable();
