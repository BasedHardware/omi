# Pending work and processing attention

Processing attention, pending-work projection and reprocess deduplication are
always active in every environment. Both GET endpoints retain `enabled: true`
for client compatibility. There are no feature switches or PostHog calls.

The authenticated `/v1/pending-work` and `/v1/attention-items` GET responses
follow `.agent-scratch/pending-contract.md`. Seen/dismiss return 204. Unknown
items return 404 and non-retryable/stale items return 409 with
`{"state":"not_retryable"}`. Single retry accepts `Idempotency-Key` and returns
200 `{operation_id, state}`; keyed replay of a failed attempt includes
`state: failed`. Existing reprocess retains its Conversation response and
deduplicates only active work; it does not use attention's keyed replay policy.

Conversation dead-letter, conversation terminal state and deterministic
attention item creation share the existing fenced Firestore transaction.
Attention id hashes finalization revision, sync content revision and job id;
uid and conversation scope the item and retry claim collections. A terminal
minimum title is not a successful summary. Read-time reconciliation resolves
items whose owner disappeared, was soft deleted, or acquired an overview;
there is no sweep or migration of historical failures. Seen/dismiss writes
are immediately available to the next read. Concurrent resolution can appear
one read later. Claim status is read from the common claim ledger, including
claims made by the old reprocess endpoint.

The projection reads at most 100 `status == processing` conversations and 100
active attention documents, plus at most two direct reads per attention item.
Live capture, discarded/deleted, completed and dead-letter rows are excluded.
These queries use Firestore's default collection single-field indexes on
`conversations.status` and `processing_attention_items.active`; no composite
index or collection-group index is needed. Folder/date/list-page filters are
not involved. The pending projection's unseen count describes this bounded
window; GET attention-items, seen-all and retry-all use the full active set.
The projection's windowed count is an addition to the shared contract.

Sync jobs remain Redis-owned. New jobs enter
a stage-scoped, per-user sorted set (latest 100 ids, 24h TTL); projection reads
at most 100 jobs, removing missing/terminal entries. Older jobs are not
backfilled. Redis indexing failure records fallback telemetry
and leaves the existing sync job usable through its normal status endpoint.
The projection's sync duration is zero because this job metadata does not
provide a reliable captured duration. Produced ids come from new_memories and
updated_memories when the job result is available.

Paid work remains synchronous, matching existing user reprocess behavior.
Retry-all atomically reserves claims and its immutable response before running
owned work; replay returns that original response, so its in_progress states
can outlive actual processing. Read attention items for current states.
Batch workers continue after an individual processing error. Reprocess
concurrency losers return the currently persisted Conversation without
starting work or waiting. Once that attempt succeeds or fails, a later explicit
reprocess starts a new numbered attempt even when the input generation is
unchanged. The single active writer is shared across app_id selections: a
concurrent selection joins the first admitted writer to avoid competing
summary writes. A later selection runs normally after the writer finishes.

A generation's ledger holds one current attempt, its monotonically increasing
attempt counter, attempt history, and per-key mappings. A failed attempt is
eligible for a new attempt with a new key (or no key). Keys joining an active
attempt remain pinned to it after failure; replay never starts paid work.
Retry-all keys similarly replay the immutable batch response. GET attention
reads current attempt status and keeps failed items retryable.

The lease is 1800 seconds (30 minutes), matching the existing sync run lock.
This exceeds the normal 1500-second durable processing request budget in
main.py by five minutes; the structure/prompt model calls use the foreground
60-second timeout. An expired in-progress lease can be replaced by a new
attempt. Expiry presumes an abandoned worker, rather than cancelling an
external provider request. Completion checks the current operation identity
transactionally so a late abandoned worker cannot change the newer attempt
or resolve its attention item. Keyed replay of an abandoned attempt reports
failed once another caller has reclaimed it.

No queue scheduling or priority changes are made.
