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
service. An empty granted account is an honest empty page. Production GET
advertises `maxAttachmentsPerMessage: 0` and an empty MIME list because
attachment storage is not mounted; the local write composition still uses the
existing attachment capability advertisement. Assistant rows require a unique terminal
generation event; an orphan or mismatched terminal is 503 rather than a completed
answer. Human rows keep `generationOutcome: null`.

`POST /v1/chat-messages` and generation SSE are not mounted. Unmounted writes stay
404 `{error:"not_found"}`. Do not invent chat quotas or mount admission until a
real entitlement producer exists. PostgreSQL now has an unmounted `chat.write`
authorization lookup and a serializable admission/finalization repository against
migration 0055 tables. Adapter existence does not enable a route. A `chat.read`
grant, revoked grant, or missing grant never confers write. An unmounted storage
foundation can persist caller-supplied reservation metadata on the same PostgreSQL
connection as the message and accepted event. A missing metadata object (`null`)
refuses. Tests may inject synthetic catalog/subscription/period/unit strings; those
strings are not paid authorization, do not enforce a budget, and are not a
source-owned producer or settlement. Exact replay of an already-stored message is
storage-only and does not insert another reservation row. There is no external
Settings counter and no compensating decrement. Migration 0057 GRANTs
`chat_messages` SELECT/INSERT/UPDATE, `chat_generation_events` SELECT/INSERT,
`chat_admission_reservations` SELECT/INSERT, and the identity sequence under
existing `chat.write` RLS. Do not apply shared migrations from this work. POST/SSE
stay unmounted.

Chat entitlement ownership, from existing source (not a new ledger):
`backend/utils/subscription.py:get_chat_quota_snapshot` and
`enforce_chat_quota` read Firestore via `database.users.get_user_valid_subscription`
and monthly counters in `database.user_usage.get_monthly_chat_usage`. The product
question writer is `database.llm_usage.record_chat_quota_question` /
`release_chat_quota_question` (idempotent event doc, UTC day, plan bucket).
Gateway `llm_gateway/gateway/executor.py:reserve_jit_attempt` /
`settle_jit_attempt` is JIT QA spend only and cannot authorize subscriber chat.
Display names come from Firebase Auth (`utils.users.get_user_display_name`), not
PostgreSQL grants. Compatible portable admission must call that source-owned
reserve/settle pair; snapshots and PG reservation metadata rows are not that
producer. No authenticated transport for that pair exists in example-platform.

Verification uses `bun run check:deployed` for grant denial, empty-page shape,
projection fail-closed behavior, string generation frames, route pairing and the
production import closure, and `bun run test:postgres` for actual application-role
reads, account isolation, unique-terminal assistant outcomes, grant revocation
and conversation-list composition of `chat:chat-main`. Docker is
required for that real PostgreSQL 18.4 gate. These tests use isolated synthetic
identities; they do not activate a deployed user or prove live generation.
Do not apply migrations 55-57 or deploy this entry until the existing operator
migration sequence can run against based-hardware-dev. A process built from this
manifest will not become ready against a database that still has only
migrations 1–54.
