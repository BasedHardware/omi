# Persisted conversation reads

The deployed service mounts `GET /v1/conversations` through the same admission,
readiness and drain boundary as the other REST routes. It verifies the original
Firebase identity and requires a registered active credential with the exact
`conversations.read` grant. A `memories.read` or `listen.capture.write` grant does
not confer this read permission. Deployment still needs the authoritative account,
control, credential and grant records described in `deployed-entry.md`.

Migration 0050 adds durable conversation ordering and account read revisions. The
reader projects actual completed device uploads and canonical Listen finalization
intents. An upload that is queued, running or failed remains visible so its
transcript can be inspected or explicitly resumed with fresh authentication.
Unpublished provider results never become an overview. Successful no-speech
transcription is an empty completed recording. A persisted locked finalization
intent remains processing; this reader does not invent memory-processing success.

Device IDs use `recording:<session UUID>`, matching the app's transcript detail
path. Non-device finalized Listen sessions retain their canonical conversation
IDs. Both use the existing ratified conversation projection, server-originated
private/unstarred defaults, and the existing legacy offset response when explicitly
requested. No conversation mutation routes are mounted by this adapter.

The signed cursor is bound to the real credential, grant, account epoch and account
read revision. A changed recording state, newly visible upload or finalization
invalidates an earlier cursor; clients must refresh instead of silently omitting a
session that opened earlier but only became visible between pages. Account order
survives process restarts. The SQL result is limited to 10,001 bounded summaries;
the reader fails closed above 10,000 records rather than claiming a truncated list
is complete. SQL keyset pagination with a persisted snapshot is the next scaling
step when an account exceeds this bound.

This is the persisted Listen/recording list, not a production chat history store.
Chat conversations, editable metadata, folders and star mutations still need their
own actual persisted domain composition. Full transcript data remains on the
existing account-scoped device-session transcript route.

Verification uses `bun run check:deployed` for projection, expiry/cancellation,
route and shell contracts, and `bun run test:postgres` for actual application-role
reads, queued/failed/completed records, cursor invalidation, grant revocation and
account isolation. The PostgreSQL harness also verifies schema backup/restore and
Bun/Node driver parity. These tests use isolated synthetic identities; they do not
activate a deployed user or prove physical-device capture.
