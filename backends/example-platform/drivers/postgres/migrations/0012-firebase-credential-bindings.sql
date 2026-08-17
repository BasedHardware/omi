-- P7/P2 expand-only Firebase identity ingress and application credential
-- binding. The legacy-origin control projection, application credential, and
-- exact grant remain the authorities; this mapping cannot activate any of them.

CREATE TABLE omi_memory.firebase_identity_bindings (
  firebase_project_id text NOT NULL
    CHECK (length(firebase_project_id) BETWEEN 1 AND 256)
    CHECK (firebase_project_id ~ '^[!-~]+$'),
  firebase_uid text NOT NULL
    CHECK (length(firebase_uid) BETWEEN 1 AND 128)
    CHECK (firebase_uid !~ '[[:cntrl:]]'),
  account_id text NOT NULL,
  principal_id text NOT NULL
    CHECK (length(principal_id) BETWEEN 1 AND 256)
    CHECK (principal_id ~ '^[!-~]+$'),
  source_control_revision bigint NOT NULL CHECK (source_control_revision >= 0),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (firebase_project_id, firebase_uid),
  UNIQUE (account_id, firebase_project_id, firebase_uid, principal_id),
  FOREIGN KEY (account_id, source_control_revision)
    REFERENCES omi_memory.account_control_revisions (account_id, control_revision)
);

CREATE TABLE omi_memory.firebase_application_credential_bindings (
  account_id text NOT NULL,
  firebase_project_id text NOT NULL,
  firebase_uid text NOT NULL,
  principal_id text NOT NULL,
  application_id text NOT NULL CHECK (application_id <> ''),
  credential_id text NOT NULL CHECK (credential_id <> ''),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (account_id, firebase_project_id, firebase_uid, application_id),
  FOREIGN KEY (account_id, firebase_project_id, firebase_uid, principal_id)
    REFERENCES omi_memory.firebase_identity_bindings
      (account_id, firebase_project_id, firebase_uid, principal_id),
  FOREIGN KEY (account_id, application_id, credential_id)
    REFERENCES omi_memory.application_credential_heads
      (account_id, application_id, credential_id)
);

-- Fixed pre-authorization lookup. The caller supplies only verified external
-- identity plus server-fixed application/capability; every owner-bearing and
-- mutable authority coordinate comes from the joined persisted rows.
CREATE FUNCTION omi_memory.lookup_firebase_application_authorization(
  requested_firebase_project_id text,
  requested_firebase_uid text,
  requested_application_id text,
  requested_capability text
)
RETURNS TABLE (
  firebase_project_id text,
  firebase_uid text,
  principal_id text,
  account_id text,
  application_id text,
  credential_id text,
  credential_generation bigint,
  credential_lifecycle text,
  authentication_strength text,
  credential_expires_at_epoch_seconds bigint,
  capability text,
  grant_id text,
  grant_version bigint,
  grant_lifecycle text,
  grant_enabled boolean,
  control_revision bigint,
  account_epoch bigint,
  destination_activation_revision bigint,
  destination_activation_epoch bigint,
  control_conflict_reason text,
  control_conflict_at_revision bigint,
  lifecycle_state text,
  deletion_epoch bigint,
  account_generation text,
  control_content_hash text,
  credential_content_hash text,
  grant_content_hash text
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, omi_memory
AS $function$
  SELECT
    fib.firebase_project_id,
    fib.firebase_uid,
    fib.principal_id,
    fib.account_id,
    fab.application_id,
    fab.credential_id,
    cr.credential_generation,
    cr.lifecycle,
    cr.authentication_strength,
    CASE WHEN cr.expires_at IS NULL THEN NULL
      ELSE floor(extract(epoch FROM cr.expires_at))::bigint
    END,
    gr.capability,
    gr.grant_id,
    gr.grant_version,
    gr.lifecycle,
    gr.enabled,
    ac.control_revision,
    ac.account_epoch,
    ach.activation_control_revision,
    ach.activated_epoch,
    ach.conflict_reason,
    ach.conflict_at_control_revision,
    ac.lifecycle_state,
    ac.deletion_epoch,
    ac.account_generation,
    ac.content_hash,
    cr.content_hash,
    gr.content_hash
  FROM omi_memory.firebase_identity_bindings AS fib
  JOIN omi_memory.firebase_application_credential_bindings AS fab
    ON fab.account_id = fib.account_id
   AND fab.firebase_project_id = fib.firebase_project_id
   AND fab.firebase_uid = fib.firebase_uid
   AND fab.principal_id = fib.principal_id
   AND fab.application_id = requested_application_id
  JOIN omi_memory.platform_accounts AS a
    ON a.account_id = fib.account_id
  JOIN omi_memory.account_control_heads AS ach
    ON ach.account_id = fib.account_id
  JOIN omi_memory.account_control_revisions AS ac
    ON ac.account_id = ach.account_id
   AND ac.control_revision = ach.control_revision
  JOIN omi_memory.application_credential_heads AS ch
    ON ch.account_id = fab.account_id
   AND ch.application_id = fab.application_id
   AND ch.credential_id = fab.credential_id
  JOIN omi_memory.application_credential_revisions AS cr
    ON cr.account_id = ch.account_id
   AND cr.application_id = ch.application_id
   AND cr.credential_id = ch.credential_id
   AND cr.credential_generation = ch.credential_generation
   AND cr.principal_id = fib.principal_id
  JOIN omi_memory.application_grant_heads AS gh
    ON gh.account_id = ch.account_id
   AND gh.application_id = ch.application_id
   AND gh.credential_id = ch.credential_id
   AND gh.credential_generation = ch.credential_generation
   AND gh.capability = requested_capability
  JOIN omi_memory.application_grant_revisions AS gr
    ON gr.account_id = gh.account_id
   AND gr.application_id = gh.application_id
   AND gr.credential_id = gh.credential_id
   AND gr.credential_generation = gh.credential_generation
   AND gr.capability = gh.capability
   AND gr.grant_id = gh.grant_id
   AND gr.grant_version = gh.grant_version
  WHERE fib.firebase_project_id = requested_firebase_project_id
    AND fib.firebase_uid = requested_firebase_uid
$function$;

REVOKE ALL ON TABLE omi_memory.firebase_identity_bindings FROM PUBLIC;
REVOKE ALL ON TABLE omi_memory.firebase_application_credential_bindings FROM PUBLIC;
REVOKE ALL ON FUNCTION omi_memory.lookup_firebase_application_authorization(text, text, text, text)
  FROM PUBLIC;

GRANT EXECUTE ON FUNCTION omi_memory.lookup_firebase_application_authorization(text, text, text, text)
  TO omi_platform_application;
