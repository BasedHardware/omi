# Pending work and processing attention

Processing attention, pending-work projection and reprocess deduplication are
always active in every environment. Both GET endpoints retain `enabled: true`
for client compatibility. `HOME_STEP_PROJECTION` is an existing default-on
presentation kill switch shared with conversation list `home_step`. It also gates
`home_processing_today` in pending-work and its expanded candidate sources.
Off returns false, uses the legacy `status == processing` query and omits
`home_step`. Mobile, web conversation-gallery and macOS clients retain old Home placement until an enabled snapshot
explicitly confirms true; absent fields, 404s, read errors and account changes
restore old placement. There are no PostHog calls. Backend must ship before
clients can apply the new placement; the backend flag remains default-on.

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

The pending conversation response remains capped at 100. With the switch on,
three single-field candidate queries read `status in [processing, merging]`,
`home_transcription_deadline_at > now` and `summary_due_at > 0`, each initially
capped at 100. Duplicate ids, deleted/discarded, completed finalization and
dead-letter jobs are excluded. Stored unfinished jobs remain pending beyond
Home's presentation wait; this wait never completes a job. Live-owner and
stored-terminal exclusions may advance the candidate cursor to fill the page;
stale completed debt alone never triggers an unbounded history walk. Supplemental
queries use the default single-field index order (earliest due first).
No composite index or collection-group query is needed.

The attention projection reads at most 100 active documents, plus at most two
direct reads per attention item. Folder/date/list-page filters are not involved.
The unseen count describes this bounded window; GET attention-items, seen-all
and retry-all use the full active set. Sync duration is unchanged.

Flutter chooses the user's current **local recorded day**, using `started_at`
(or `created_at`), including recordings that cross midnight: after midnight they
move to Processing in Activity. A foreground civil-clock check and resume
recheck update both surfaces. Relay 9e09f1 (David, 2026-11-10 11:53Z) overrides the earlier failed Home UI:
**no failed conversation appears on any conversation Home surface**. Failed status, failed Home
projection and failed episode members appear only in Activity with retry, on any
day. Ledger entries keep the existing keyed retry; projected failures without a
ledger item use the existing fenced conversation reprocess endpoint. Activity
merges pending/episode members and loaded conversations, deduplicates ledger ids,
and lets a finished conversation override stale pending data. A retry failure
leaves the row and action available; success updates the shared conversation
provider and restores normal Home placement.

Pending conversation items now optionally echo `home_step` while the switch is
on, including `failed` for expired presentation waits. This keeps an unloaded old
job reachable in Activity without a new query or stored lifecycle state. Catch-up
and On the Way exclude these projected failures when the switch is confirmed on;
the raw pending view remains available to Activity. Off/failure restores the
previous consumers and failed Home placement.
Ready rows return to their recorded Home day. Search, folders, stars and selection retain exact matches except failed Home rows under this ruling. Queued work is labelled Transcribing, not Writing notes.

Limits: pending is a bounded window, not an all-history backlog. Loaded Home
conversations supplement Activity independently of the pending cap, so every
loaded row hidden for its date is available there. Episode-only composition debt
outside Home's loaded episode range and legacy empty completed rows without debt
stamps are not discovered by these candidate queries. Fetching all such history
requires a separate bounded/paged episode/debt API; no history scan is introduced.
Existing catching-up and On the Way consumers intentionally include server work
through note completion (including summary debt); their duration describes the
recording awaiting completion, not bytes remaining to transfer. Older clients
retain that broad interpretation; no released wire discriminator is changed.

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

Relay 714b03 expands the failed placement to web `/conversations` (an Activity tab in the gallery) and native macOS Conversations (the existing Memory hub Activity destination). Web `/home` remains its chat/tasks/goals destination. These clients also require explicit pending-work confirmation and restore previous placement after failed reads; missing/false fields disable placement. They retain server Home projections through list/detail/search reconciliation and retry. macOS supplements loaded rows with failures found only by search, clearing this supplement at account reset. All clients use their existing reprocess endpoint and shared state refresh. Native Activity filters these failures from the chronological spine to avoid duplicate rows. No second chat, new backend query, new flag or persisted job state is introduced.
