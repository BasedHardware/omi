# Persisted chat history reads

The deployed service mounts `GET /v1/chat-messages` through the same admission,
readiness and drain boundary as the other REST routes. It verifies the original
Firebase identity and requires a registered active credential with the exact
`chat.read` grant. A `memories.read`, `tasks.read` or `conversations.read` grant
does not confer this read permission. Missing or revoked grants return 403; they
never become an empty successful transcript. Deployment still needs the
authoritative account, control, credential and grant records described in
`deployed-entry.md`.

Migration 0055 adds account-owned chat message rows and generation events. History
uses the insertion snapshot and opaque HMAC cursor already used by the local
service. An empty granted account is an honest empty page with the existing
attachment capability advertisement. Assistant rows require a unique terminal
generation event; an orphan or mismatched terminal is 503 rather than a completed
answer. Human rows keep `generationOutcome: null`.

`POST /v1/chat-messages` and generation SSE are not mounted. Unmounted writes stay
404 `{error:"not_found"}`. Do not invent chat quotas or mount admission until a
real entitlement producer exists.

Verification uses `bun run check:deployed` for grant denial, empty-page shape,
projection fail-closed behavior, route pairing and the production import
closure, and `bun run test:postgres` for actual application-role reads, account
isolation, unique-terminal assistant outcomes and grant revocation. Docker is
required for that real PostgreSQL 18.4 gate. These tests use isolated synthetic
identities; they do not activate a deployed user or prove live generation.
Do not apply migration 55 or deploy this entry until the existing operator
migration sequence can run against based-hardware-dev. A process built from this
manifest will not become ready against a database that still has only
migrations 1–54.
