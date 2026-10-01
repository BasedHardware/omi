-- P8 fixed production startup-readiness inspection.
--
-- This exposes only immutable migration coordinates plus whether the exact
-- configured restored database generation currently has a released head. It
-- is startup evidence, not account, credential, grant, or action authority.

CREATE FUNCTION omi_memory.inspect_production_runtime_readiness(
  requested_database_generation_digest text
)
RETURNS TABLE (
  server_version_num text,
  database_generation_released boolean,
  migration_version bigint,
  migration_name text,
  migration_sha256 text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT
    current_setting('server_version_num')::text,
    EXISTS (
      SELECT 1
      FROM omi_memory.postgres_restore_admission_heads AS head
      JOIN omi_memory.postgres_restore_admission_revisions AS release
        ON release.database_generation_digest = head.database_generation_digest
       AND release.release_revision = head.release_revision
      WHERE requested_database_generation_digest ~ '^[0-9a-f]{64}$'
        AND head.database_generation_digest = requested_database_generation_digest
        AND release.state = 'released'
    ),
    migration.version,
    migration.name,
    migration.sha256
  FROM omi_memory.platform_schema_migrations AS migration
  ORDER BY migration.version;
$function$;

REVOKE ALL ON FUNCTION omi_memory.inspect_production_runtime_readiness(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION omi_memory.inspect_production_runtime_readiness(text)
  TO omi_platform_application;
