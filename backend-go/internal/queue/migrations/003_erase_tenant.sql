-- Bind table names to the queue's installation schema, including installations
-- outside public. The definer never resolves an object via the caller's path.
DO $migration$
BEGIN
    EXECUTE format($ddl$
        CREATE FUNCTION %1$I.queue_erase_tenant(tenant text)
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $body$
        DECLARE
            remote_completed boolean;
        BEGIN
            -- A transaction-wide snapshot could miss an admission that commits
            -- while we wait for its shared lock.
            IF current_setting('transaction_isolation') NOT IN ('read committed', 'read uncommitted') THEN
                RAISE EXCEPTION 'queue erasure requires read committed isolation' USING ERRCODE = '25000';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended(tenant,447119));
            DELETE FROM %1$I.queue_tenants WHERE uid=tenant;
            INSERT INTO %1$I.queue_erasure(tenant_hash)
            VALUES ((SELECT sha256(erasure_salt || convert_to(tenant,'UTF8')) FROM %1$I.queue_settings))
            ON CONFLICT (tenant_hash) DO UPDATE SET tenant_hash=EXCLUDED.tenant_hash
            RETURNING completed INTO remote_completed;
            RETURN remote_completed;
        END
        $body$
    $ddl$, current_schema());
END
$migration$;

-- Migrate installs the function and its ACL in one transaction. Provisioning
-- the recovery role and granting it EXECUTE are separate access changes.
REVOKE ALL ON FUNCTION queue_erase_tenant(text) FROM PUBLIC;
