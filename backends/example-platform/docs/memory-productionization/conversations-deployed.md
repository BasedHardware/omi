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
survives process restarts. Migration 0053 retains opaque cursor positions in an
account-owned table; the public signed cursor never contains the internal sequence.
Each envelope read selects at most the requested limit plus two anchor/lookahead
records before loading transcript excerpts. The existing explicit offset mode
retains its bounded 5,000 offset and 5,000 limit. Account history size no longer
causes all reads to fail at 10,000 records.

Cursor positions bind the exact signed token hash, canonical reader/grant/epoch
bindings and account revision. They expire with the 900-second signed cursor.
Issuance prunes up to 256 expired positions and caps retained metadata at 10,000
positions per account; capacity returns unavailable rather than evicting an active
cursor. This is an operational request-volume ceiling, not a conversation-count
limit. Account deletion disposes these rows with product projections. Signature,
authorization and expiry validation precede position lookup; the complete read and
cursor save remain in the authorized transaction with its final clock and abort
checks. Pre-migration cursors without a retained position require a fresh first page.
Migration 0053 removes the old whole-account function and introduces a distinct
metadata read; an old process calling the retired function fails unavailable rather
than returning an empty successful history during a mixed-revision rollout.

This is the persisted Listen/recording list, plus granted chat sessions.
Envelope reads that also hold `chat.read` merge those sessions with Listen rows by
`updatedAt` descending then `id` ascending, matching Worker
`readConversations` / `paginateConversations`. Each page returns at most the
requested `limit`. The signed union cursor is a distinct policy from the Listen
sequence cursor; it binds the chat snapshot sequence as well as the Listen
revision so a chat write or recording-state change invalidates continuation.
A Listen-sequence cursor cannot continue on the union path. The last item may be
a `chat:` or Listen row; the position table stores that identity instead of a
fake Listen sequence. Missing `chat.read`, revoked grants, and empty chat history
never invent `chat:chat-main`. Without `chat.read`, later pages keep the Listen
sequence path. Chat writes, editable metadata, folders and star mutations still
need their own persisted domain composition. Full recording transcript data
remains on the existing account-scoped device-session transcript route.

Verification uses `bun run check:deployed` for projection, expiry/cancellation,
route and shell contracts, and `bun run test:postgres` for actual application-role
reads, queued/failed/completed records, cursor invalidation, grant revocation and
account isolation, histories above 10,000 records, bounded page materialization,
restart-safe continuation, cursor expiry and metadata disposal. The PostgreSQL harness also verifies schema backup/restore and
Bun/Node driver parity. These tests use isolated synthetic identities; they do not
activate a deployed user or prove physical-device capture.
