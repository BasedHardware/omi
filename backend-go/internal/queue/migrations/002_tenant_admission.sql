-- A waiting admission must see an erase that committed while it waited. Each
-- statement in this VOLATILE function gets its own READ COMMITTED snapshot.
CREATE FUNCTION queue_acquire_tenant(tenant text)
RETURNS boolean
LANGUAGE plpgsql VOLATILE
AS $$
BEGIN
    PERFORM pg_advisory_lock_shared(hashtextextended(tenant,447119));
    RETURN NOT EXISTS (
        SELECT 1 FROM queue_erasure
        WHERE tenant_hash=(SELECT sha256(erasure_salt || convert_to(tenant,'UTF8')) FROM queue_settings)
    );
END;
$$;
