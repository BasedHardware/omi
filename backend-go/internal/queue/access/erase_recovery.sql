-- Separately approved DBA migration. Not embedded in Store.Migrate.
-- The approver supplies queue_schema and recovery_role as psql identifiers.
-- The role must already exist and have no direct queue table privileges.
\set ON_ERROR_STOP on
BEGIN;
GRANT USAGE ON SCHEMA :"queue_schema" TO :"recovery_role";
GRANT EXECUTE ON FUNCTION :"queue_schema".queue_erase_tenant(text) TO :"recovery_role";
COMMIT;
