-- P2.1 expand-only PostgreSQL authority: account root, subordinate control,
-- credential bindings, and exact application grants.
--
-- `omi_platform_application` is provisioned by deployment/test infrastructure.
-- Migrations deliberately do not create cluster-global roles.

CREATE SCHEMA IF NOT EXISTS omi_memory;

CREATE TABLE omi_memory.platform_schema_migrations (
  version bigint PRIMARY KEY CHECK (version > 0),
  name text NOT NULL UNIQUE CHECK (name <> ''),
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  applied_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

CREATE TABLE omi_memory.platform_accounts (
  account_id text PRIMARY KEY
    CHECK (length(account_id) BETWEEN 1 AND 128)
    CHECK (account_id ~ '^[!-~]+$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

CREATE TABLE omi_memory.account_control_revisions (
  account_id text NOT NULL,
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  account_generation text NOT NULL
    CHECK (account_generation IN ('legacy', 'migrating', 'new', 'rolled_back_stranded')),
  account_epoch bigint CHECK (account_epoch IS NULL OR account_epoch >= 0),
  lifecycle_state text NOT NULL
    CHECK (lifecycle_state IN ('active', 'deletion_pending', 'deleted')),
  deletion_epoch bigint CHECK (deletion_epoch IS NULL OR deletion_epoch >= 0),
  observed_at timestamptz NOT NULL,
  record_schema_version text NOT NULL CHECK (record_schema_version <> ''),
  record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (account_id, control_revision),
  UNIQUE (account_id, control_revision, account_epoch),
  UNIQUE (
    account_id, control_revision, deletion_epoch, account_generation, lifecycle_state
  ),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id),
  CHECK (
    (lifecycle_state = 'active' AND deletion_epoch IS NULL)
    OR (lifecycle_state IN ('deletion_pending', 'deleted') AND deletion_epoch IS NOT NULL)
  )
);

CREATE TABLE omi_memory.account_control_heads (
  account_id text PRIMARY KEY,
  control_revision bigint NOT NULL CHECK (control_revision >= 0),
  activated_epoch bigint CHECK (activated_epoch IS NULL OR activated_epoch >= 0),
  activation_control_revision bigint CHECK (
    activation_control_revision IS NULL OR activation_control_revision >= 0
  ),
  conflict_reason text,
  conflict_at_control_revision bigint CHECK (
    conflict_at_control_revision IS NULL OR conflict_at_control_revision >= 0
  ),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  FOREIGN KEY (account_id, control_revision)
    REFERENCES omi_memory.account_control_revisions (account_id, control_revision),
  FOREIGN KEY (account_id, activation_control_revision, activated_epoch)
    REFERENCES omi_memory.account_control_revisions
      (account_id, control_revision, account_epoch),
  FOREIGN KEY (account_id, conflict_at_control_revision)
    REFERENCES omi_memory.account_control_revisions (account_id, control_revision),
  CHECK ((activated_epoch IS NULL) = (activation_control_revision IS NULL)),
  CHECK ((conflict_reason IS NULL) = (conflict_at_control_revision IS NULL))
);

CREATE TABLE omi_memory.application_credential_revisions (
  account_id text NOT NULL,
  principal_id text NOT NULL CHECK (principal_id <> ''),
  application_id text NOT NULL CHECK (application_id <> ''),
  credential_id text NOT NULL CHECK (credential_id <> ''),
  credential_generation bigint NOT NULL CHECK (credential_generation >= 0),
  credential_kind text NOT NULL CHECK (credential_kind <> ''),
  lifecycle text NOT NULL CHECK (lifecycle IN ('active', 'inactive', 'revoked')),
  authentication_strength text NOT NULL CHECK (authentication_strength <> ''),
  expires_at timestamptz,
  record_schema_version text NOT NULL CHECK (record_schema_version <> ''),
  record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, application_id, credential_id, credential_generation),
  FOREIGN KEY (account_id)
    REFERENCES omi_memory.platform_accounts (account_id)
);

CREATE TABLE omi_memory.application_credential_heads (
  account_id text NOT NULL,
  application_id text NOT NULL,
  credential_id text NOT NULL,
  credential_generation bigint NOT NULL CHECK (credential_generation >= 0),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, application_id, credential_id),
  FOREIGN KEY (account_id, application_id, credential_id, credential_generation)
    REFERENCES omi_memory.application_credential_revisions
      (account_id, application_id, credential_id, credential_generation)
);

CREATE TABLE omi_memory.application_grant_revisions (
  account_id text NOT NULL,
  application_id text NOT NULL CHECK (application_id <> ''),
  credential_id text NOT NULL CHECK (credential_id <> ''),
  credential_generation bigint NOT NULL CHECK (credential_generation >= 0),
  capability text NOT NULL CHECK (capability <> ''),
  grant_id text NOT NULL CHECK (grant_id <> ''),
  grant_version bigint NOT NULL CHECK (grant_version >= 0),
  lifecycle text NOT NULL CHECK (lifecycle IN ('active', 'inactive', 'revoked')),
  enabled boolean NOT NULL,
  scopes jsonb NOT NULL CHECK (jsonb_typeof(scopes) = 'array'),
  record_schema_version text NOT NULL CHECK (record_schema_version <> ''),
  record_json jsonb NOT NULL CHECK (jsonb_typeof(record_json) = 'object'),
  content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, grant_id, grant_version),
  UNIQUE (
    account_id, application_id, credential_id, credential_generation,
    capability, grant_id, grant_version
  ),
  FOREIGN KEY (account_id, application_id, credential_id, credential_generation)
    REFERENCES omi_memory.application_credential_revisions
      (account_id, application_id, credential_id, credential_generation)
);

CREATE TABLE omi_memory.application_grant_heads (
  account_id text NOT NULL,
  application_id text NOT NULL,
  credential_id text NOT NULL,
  credential_generation bigint NOT NULL CHECK (credential_generation >= 0),
  capability text NOT NULL,
  grant_id text NOT NULL,
  grant_version bigint NOT NULL CHECK (grant_version >= 0),
  updated_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (
    account_id, application_id, credential_id, credential_generation, capability
  ),
  FOREIGN KEY (
    account_id, application_id, credential_id, credential_generation,
    capability, grant_id, grant_version
  ) REFERENCES omi_memory.application_grant_revisions (
    account_id, application_id, credential_id, credential_generation,
    capability, grant_id, grant_version
  )
);

-- The application role must lock mutable authority heads without receiving
-- UPDATE privilege on the subordinate control projection. This fixed-shape
-- function owns only that lock/read operation; every coordinate is explicit.
CREATE FUNCTION omi_memory.lock_authority_state(
  requested_account_id text,
  requested_principal_id text,
  requested_application_id text,
  requested_credential_id text,
  requested_credential_generation bigint,
  requested_capability text,
  requested_grant_id text
)
RETURNS TABLE (
  account_id text,
  principal_id text,
  application_id text,
  credential_id text,
  credential_generation bigint,
  capability text,
  grant_id text,
  grant_version bigint,
  account_epoch bigint,
  control_conflict_reason text,
  control_conflict_at_revision bigint,
  destination_activation_epoch bigint,
  destination_activation_revision bigint,
  lifecycle_state text,
  deletion_epoch bigint,
  account_generation text,
  credential_lifecycle text,
  grant_lifecycle text,
  grant_enabled boolean,
  authentication_strength text,
  credential_expires_at_epoch_seconds bigint,
  control_revision bigint,
  control_content_hash text,
  credential_content_hash text,
  grant_content_hash text,
  db_now_epoch_seconds bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT
    a.account_id,
    cr.principal_id,
    cr.application_id,
    cr.credential_id,
    cr.credential_generation,
    gr.capability,
    gr.grant_id,
    gr.grant_version,
    ac.account_epoch,
    ach.conflict_reason,
    ach.conflict_at_control_revision,
    ach.activated_epoch,
    ach.activation_control_revision,
    ac.lifecycle_state,
    ac.deletion_epoch,
    ac.account_generation,
    cr.lifecycle,
    gr.lifecycle,
    gr.enabled,
    cr.authentication_strength,
    CASE WHEN cr.expires_at IS NULL THEN NULL
      ELSE floor(extract(epoch FROM cr.expires_at))::bigint
    END,
    ac.control_revision,
    ac.content_hash,
    cr.content_hash,
    gr.content_hash,
    floor(extract(epoch FROM transaction_timestamp()))::bigint
  FROM omi_memory.platform_accounts AS a
  JOIN omi_memory.account_control_heads AS ach
    ON ach.account_id = a.account_id
  JOIN omi_memory.account_control_revisions AS ac
    ON ac.account_id = ach.account_id
   AND ac.control_revision = ach.control_revision
  JOIN omi_memory.application_credential_heads AS ch
    ON ch.account_id = a.account_id
   AND ch.application_id = requested_application_id
   AND ch.credential_id = requested_credential_id
  JOIN omi_memory.application_credential_revisions AS cr
    ON cr.account_id = ch.account_id
   AND cr.application_id = ch.application_id
   AND cr.credential_id = ch.credential_id
   AND cr.credential_generation = ch.credential_generation
  JOIN omi_memory.application_grant_heads AS gh
    ON gh.account_id = a.account_id
   AND gh.application_id = requested_application_id
   AND gh.credential_id = requested_credential_id
   AND gh.credential_generation = requested_credential_generation
   AND gh.capability = requested_capability
  JOIN omi_memory.application_grant_revisions AS gr
    ON gr.account_id = gh.account_id
   AND gr.application_id = gh.application_id
   AND gr.credential_id = gh.credential_id
   AND gr.credential_generation = gh.credential_generation
   AND gr.capability = gh.capability
   AND gr.grant_id = gh.grant_id
   AND gr.grant_version = gh.grant_version
  WHERE a.account_id = requested_account_id
    AND cr.principal_id = requested_principal_id
    AND gr.grant_id = requested_grant_id
  FOR SHARE OF a, ach, ac, ch, cr, gh, gr
$function$;

REVOKE ALL ON SCHEMA omi_memory FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA omi_memory FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lock_authority_state(text, text, text, text, bigint, text, text) FROM PUBLIC;

GRANT USAGE ON SCHEMA omi_memory TO omi_platform_application;
GRANT SELECT ON omi_memory.platform_accounts TO omi_platform_application;
GRANT SELECT ON omi_memory.account_control_revisions TO omi_platform_application;
GRANT SELECT ON omi_memory.account_control_heads TO omi_platform_application;
GRANT SELECT ON omi_memory.application_credential_revisions TO omi_platform_application;
GRANT SELECT ON omi_memory.application_credential_heads TO omi_platform_application;
GRANT SELECT ON omi_memory.application_grant_revisions TO omi_platform_application;
GRANT SELECT ON omi_memory.application_grant_heads TO omi_platform_application;
GRANT EXECUTE ON FUNCTION omi_memory.lock_authority_state(text, text, text, text, bigint, text, text)
  TO omi_platform_application;
