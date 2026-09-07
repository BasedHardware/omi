# Persisted chat history reads

The deployed service mounts `GET /v1/chat-messages` through the same admission,
readiness and drain boundary as the other REST routes. It verifies the original
Firebase identity and requires a registered active credential with the exact
`chat.read` grant. History defaults to the main session (`chat_session_id` null
or blank). One optional `chatSessionId` filters that named session the same way
Worker history does; unknown extra keys remain 400. A `memories.read`,
`tasks.read` or `conversations.read` grant
does not confer this read permission. Missing or revoked grants return 403; they
never become an empty successful transcript. Deployment still needs the
authoritative account, control, credential and grant records described in
`deployed-entry.md`.

Migration 0055 adds account-owned chat message rows and generation events.
Migration 0057 adds the session-filtered history read and grouped conversation
session list. History uses the insertion snapshot and opaque HMAC cursor already
used by the local service; that cursor binds the requested session so a named
page cannot continue as main history. An empty granted account is an honest empty
page with the existing attachment capability advertisement. Assistant rows require
a unique terminal generation event; an orphan or mismatched terminal is 503 rather
than a completed answer. Human rows keep `generationOutcome: null`.

`POST /v1/chat-messages`, generation SSE, cancellation, and attachments are
explicit unmounted write doors. They return nested 404
`{error:{code:"not_found",retryable:false,action:"none"}}` without admission,
grants, or storage. Do not invent chat quotas or mount admission until a real
entitlement producer exists.

Verification uses `bun run check:deployed` for grant denial, empty-page shape,
projection fail-closed behavior, string generation frames, route pairing and the
production import closure, and `bun run test:postgres` for actual application-role
reads, account isolation, unique-terminal assistant outcomes, grant revocation
and conversation-list composition of granted `chat:` sessions, including named
sessions only after history GET can serve them. Docker is
required for that real PostgreSQL 18.4 gate. These tests use isolated synthetic
identities; they do not activate a deployed user or prove live generation.
Do not apply migrations 55-57 or deploy this entry until the existing operator
migration sequence can run against based-hardware-dev. A process built from this
manifest will not become ready against a database that still has only
migrations 1–54.
