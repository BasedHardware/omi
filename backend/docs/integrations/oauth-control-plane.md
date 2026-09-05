# Outbound OAuth control plane

Status: approval-independent implementation seam; production admission is closed.

This design owns delegated credentials that let Omi read data from an external
provider. It does not replace Omi sign-in, Omi's first-party developer OAuth,
inbound app OAuth, or task-provider OAuth. Those are separate trust boundaries
even when they share PKCE/state helpers.

The live Python backend is the serving authority. The TypeScript rewrite may
adopt these ports later, but is not a launch dependency and must not read live
Python credential rows directly.

## Product and provider boundaries

Product authorization uses only these capabilities:

- `calendar.events.read`
- `mail.messages.read`

Provider scopes are an implementation detail in
`utils/external_oauth/scopes.py`. Calendar and Gmail are separate grant
families, clients, projects, consent attempts, credentials, and lifecycle rows:

| Connector | Exact scopes | Client alias |
| --- | --- | --- |
| Google Calendar | `openid`, `email`, `calendar.events.readonly` | `google_calendar_prod` |
| Gmail | `openid`, `email`, `gmail.readonly` | `google_gmail_prod` |

The alias registry canonicalizes Google's documented `userinfo.email` alias.
Any other added scope, or any missing scope, rejects activation. Gmail remains
a restricted-scope integration: `gmail.readonly` requires both Google OAuth
verification and current CASA evidence when Omi's backend receives the data.

The provider kill switch and deployment evidence live in
`config/external_oauth_admission.json`. The checked-in manifest is deliberately
disabled and contains no project/client evidence. A production process must not
construct routes, workers, or consumers unless `admit_connector` validates:

1. exact project-number, OAuth-client, redirect-URI, and scope digests;
2. current Google verification evidence;
3. current CASA evidence for Gmail; and
4. an explicit per-connector `enabled: true` switch.

No environment variable alone enables a connector.

## Required ports and dependency direction

`utils/external_oauth/contracts.py` defines the boundary:

- `OAuthProviderPort` constructs the fixed authorization URL and performs code
  exchange, refresh, principal validation, and revoke.
- `ExternalSecretExecutor` creates/destroys encrypted versions and executes a
  callback only inside a purpose-bound lease. It never returns token bytes.
- `ExternalConnectionRepository` owns metadata, attempts, generations,
  lifecycle CAS, and tombstones.
- `ExternalAuthorizationComposer` proves both Omi product authorization and an
  active provider grant.
- `MailReadPort` and `CalendarReadPort` return normalized product DTOs.

Routes and support/admin/status modules depend on semantic ports and nonsecret
DTOs. They must not import `vault.py`, provider token response types, or a KMS
adapter. Provider HTTP executors may receive a secret only through a lease.

The current PR supplies a concurrency-capable in-memory repository and fake
provider to freeze behavior. A production Firestore repository and Google
exchange adapter are intentionally not registered until cloud facts, IAM, and
reviewed infrastructure exist.

## Records and cardinality

A production repository must create these separate collections. None may store
plaintext token bytes.

- `external_connections`: random immutable `connection_id` and
  `external_owner_id`, current Omi-account mapping, connector, grant family,
  provider/client aliases, immutable first provider subject, masked identity,
  lifecycle state, monotonic generation, scope-registry revision/digest,
  deletion epoch, timestamps, and sanitized error code.
- `external_provider_grants`: requested/effective canonical scopes, registry
  revision, provider grant status, consent timestamps, verification evidence
  revision.
- `oauth_consent_attempts`: SHA-256 state hash, exact connection/owner/
  connector/client/scope/generation bindings, fixed return-target ID, expiry,
  consume/result fields, and encrypted attempt-secret reference.
- `external_secret_versions`: AES-256-GCM ciphertext/nonce, KMS-wrapped random
  DEK, KMS key version, AAD digest, generation/version/status.
- `external_auth_operations`: leased refresh/revoke/delete work, attempt,
  next-retry, retention deadline, typed outcome, idempotency key, generation and
  deletion epoch.
- `external_auth_audit_events`: immutable content-free lifecycle/security
  events with a shared run/operation ID.

Enforce at most one non-terminal connection per
`(external_owner_id, connector, grant_family)`. `external_owner_id` is a random,
migration-stable identity and must not be derived from email or provider `sub`.
Connection ID and the first activated provider `sub` never change. A generation
only increases. Different-sub reconnect requires explicit replace-account;
never silently switch the browser-selected Google account.

## Secret custody

`EnvelopeSecretExecutor` uses a random 256-bit DEK for every secret version and
AES-256-GCM. AAD binds:

`external_owner_id + connection_id + provider + client_alias + generation + secret_version`.

Only Cloud KMS wraps/unwraps the DEK in production. There is no local-key or
plaintext fallback. KMS errors, AAD mismatch, stale generation, missing
authorization, or missing adapter fail closed. Cloud KMS rewrap may change the
KEK only while AAD is unchanged; an AAD migration requires a bounded trusted
decrypt/re-encrypt worker.

Provision distinct service identities/roles for callback exchange, read,
refresh, revoke/delete, and rewrap. Ciphertext read must not imply KMS decrypt.
The revocation role can unwrap a fenced generation only for a fixed Google
revoke request bound to operation ID and deletion epoch. It cannot refresh,
read content, or return plaintext.

Backup restore must restore connection heads, tombstones, deletion epochs, and
revocation dispositions before any secret becomes leasable. A pre-disconnect or
pre-deletion backup must not resurrect authority.

## Consent and callback

Authorization start creates 256-bit state, PKCE S256 verifier/challenge, and an
OIDC nonce. Firestore receives only the state hash. PKCE verifier and nonce are
encrypted as short-lived attempt material. The attempt is bound to initiating
owner, connector, client, scope digest, connection generation, expiry, and a
fixed return-target identifier; a caller cannot supply an arbitrary redirect.

Callback consumption is atomic. Exactly one worker can claim the attempt and
exchange the code. Concurrent/replayed callbacks receive only a sanitized
completion class and never exchange again. Before activation the provider
adapter must validate OIDC issuer/audience/nonce/subject and the exact effective
scope set. A new grant never inherits an old refresh token.

## Lifecycle and revocation policy

`utils/external_oauth/lifecycle.py` is the executable transition source. The
allowed state transitions are:

- `pending_consent -> active | cancelled | expired`
- `active -> reauth_required | blocked_by_admin | revoke_pending |
  deletion_pending | revoked`
- `reauth_required -> pending_consent | blocked_by_admin | revoke_pending |
  deletion_pending | revoked`
- `blocked_by_admin -> pending_consent | revoke_pending | deletion_pending |
  revoked`
- `revoke_pending -> revoked | revocation_failed | deletion_pending`
- `revocation_failed -> revoke_pending | deletion_pending`
- `deletion_pending -> deletion_pending | revoked`

`revoked`, `cancelled`, and `expired` are closed terminal rows. A future
connection gets a new connection ID. Refresh and exchange are leased operations,
not connection states.

Moving to reauth/admin/revoke/delete fences reads and increments generation.
Revoke/delete states expose only revoke-purpose authority. Disconnect retry
delays are 1m, 5m, 30m, 2h, 6h, then 6h with escalation after 2h. Seven days is
a normal-disconnect review deadline, never permission to discard the only
revoke credential. Account deletion has a 24-hour privacy deadline, after which
the ratified disposition destroys ciphertext and retains only an
`upstream_revoke_unconfirmed_credentials_destroyed` tombstone.

The only terminal revocation dispositions are provider-confirmed revoke,
provider-proven invalid credential, dated security-owner decommission approval,
or the ratified 24-hour account-deletion disposition. Retry exhaustion is not a
terminal disposition.

Reconnect is permitted only after the old grant is provider-proven invalid or
project-wide revocation completes. Revoking a project grant after replacement
authorization can revoke the replacement too, so ordering is mandatory.

## Provider HTTP and semantic reads

`google_reads.py` fixes Google hosts and paths, disables redirects, bounds
response size, and returns only `MailMessage` or `CalendarEvent` DTOs. Tokens,
provider envelopes, arbitrary URLs, and toolkit identifiers do not escape.
Production adapters must additionally pin TLS defaults, reject private-address
or DNS-rebinding results, use shared backend async clients/semaphores, classify
retryable status with bounded budgets and `Retry-After`, and recheck generation
and deletion epoch before returning normalized data.

## Legacy containment and migration

The generic `PUT /v1/integrations/{app_key}` retains deprecated credential
fields only for released-client schema compatibility, but rejects every
registered server-OAuth provider key before persistence. It therefore cannot
inject or replace an OAuth credential. `GET /v1/task-integrations` returns
typed status projections rather than stored dictionaries.

`migrations/008_external_oauth_legacy_disposition.py` is a pure classification
helper and performs no database I/O. The safe default for the broad/plaintext
legacy `google_calendar` grant is revoke then explicit consent into separate
Calendar/Gmail clients. Do not copy or merge it into the new vault. If an
approved per-account exception cannot revoke immediately, the only alternative
is vault-only legacy quarantine: no reads, refresh, route exposure, or migration
into a new grant.

## Production gates and rollback

Before any cohort opens, all of the following need independent evidence:

1. redacted GCP inventory proves separate sign-in, Calendar, and Gmail projects
   and exact clients/redirects;
2. Calendar verification and Gmail verification plus CASA are current;
3. reviewed Firestore repository/transactions/indexes and immutable audit sink;
4. dedicated KMS key, Data Access logs, least-authority IAM identities, Secret
   Manager client secrets, and ciphertext-only database/IAM review;
5. KMS rotation, backup/restore anti-resurrection, concurrent callback/refresh,
   revoke retry/deadline, account-deletion, provider outage, and stale-generation
   drills;
6. producer-side and consumer-side observations share a run ID; and
7. compatibility clients pass with no credential fields in OpenAPI or responses.

Rollback closes connector/cohort switches, stops new starts and semantic reads,
and leaves encrypted/fenced credentials for controlled revoke/recovery. It must
never copy credentials back to legacy plaintext fields. Existing legacy
Calendar users remain untouched until an explicit per-account migration or
re-consent decision.
