# Conversation enrichment effect recovery

Durable conversation finalization separates the persisted conversation from
the derived data that makes it searchable. An active version 2 finalization
job must not report success until every required vector effect has either
completed or been recovered by a later lease owner.

## Required effect plan

Version 2 finalization jobs use two stable required effect keys:

1. `structured_vector`
2. `transcript_vectors`

A version 2 finalization job stores the plan version, the server-owned
conversation-row incarnation, a per-job vector generation, completed key
names, and the transcript vector count. The row incarnation binds work to one
lifetime of the Firestore source. The vector generation keeps physical index
records and cleanup isolated between finalization revisions on that row.
These are content-free ownership and cleanup coordinates. The job does not
store transcript text, extracted content, provider responses, raw exceptions,
request headers, or credentials.

Transcript-vector indexing can be disabled when a job first reaches the
stage. The worker records a count of zero before completing the no-op. If it
is enabled, the worker records the deterministic chunk count before the first
provider write. Every retry follows that stored count, even when a deployment
changes the feature flag between attempts.

Memory extraction and persistence, action-item persistence, folder assignment,
goal updates, audio preparation, task-provider auto-sync, FCM notifications,
and the conversation-created webhook remain outside the durable effect ledger.
They run only from the original processing bundle. A completed retry does not
rebuild or replay that bundle. External app integrations keep their existing
stable fanout idempotency key and required-delivery contract.

## Lease and checkpoint contract

The worker first claims the finalization job and then claims the fanout lease
against the completed conversation row and revision. For each missing required
effect, it:

1. Persists transcript cleanup coordinates before that effect starts.
2. Executes the effect on the post-processing executor.
3. Waits for the effect to return or drain after cancellation.
4. Re-reads the job and its exact conversation binding in one Firestore
   transaction.
5. Checkpoints the effect name while presenting the current dispatch
   generation and lease epoch.

The same revalidation runs after an effect raises because a remote batch can
partially commit before returning an error. If the conversation is gone,
belongs to another row incarnation, or admits a newer revision, the worker
deletes the old job's structured vector and every predeclared transcript
vector by exact ID. Cleanup does not depend on the provider's eventually
consistent list view. Only after cleanup succeeds does a second transaction
confirm that the old job still does not own the source and terminally fence
its leased fanout. Cleanup failure leaves the job retryable.

A heartbeat renews the job lease while conversation processing and required
effects are running. A failed or rejected renewal marks the worker as having
lost ownership. The worker then refuses to checkpoint an effect, call external
integrations, or complete fanout.

A cancelled request keeps the heartbeat running until any in-flight
post-processing mutation returns. It then revalidates the conversation and
performs missing-row vector cleanup before surfacing cancellation. This
prevents another worker from reclaiming the lease while the cancelled worker
can still change an index.

A stale worker cannot checkpoint an effect or complete fanout. Fanout
completion also verifies that both required keys are present. This keeps a
late worker from publishing terminal success after another worker has
reclaimed the lease.

## Retry behavior

Retry preserves completed effect keys. The next lease owner rebuilds the plan
from the persisted conversation, skips completed keys, and executes only the
missing suffix.

Before a final failed attempt dead-letters an incomplete version 2 plan, it
deletes that job's exact structured and transcript vector generation using the
persisted transcript count. Cleanup failure leaves the job nonterminal for
recovery. Version 1 jobs and version 2 jobs with both required checkpoints keep
their existing vectors.

Version 2 conversation and transcript vector IDs include the job's persisted
vector generation. Replaying a missing stage replaces the same physical
generation. A newer revision on the same row receives a different vector
generation, so cleanup from an older job cannot target newer records. A delete
followed by recreation of the same conversation ID receives a new row
incarnation and a new vector generation.

Conversation search reads the logical conversation ID from vector metadata
and deduplicates mixed legacy and version 2 physical records. The storage
migration therefore cannot return one conversation twice.

Direct and merged-source deletion first mark the source as pending vector
cleanup, which prevents a queued finalization fanout from starting. A live
synchronous processor or leased finalization job makes the first deletion
attempt retryable; its transaction still sets the pending fence so that owner
can drain without admitting new fanout. A later deletion attempt captures the
current row incarnation, vector generation, and transcript count, then purges
both legacy IDs and that generation before removing subcollections and the
Firestore source. Cleanup ownership is revalidated between vector namespaces
and before source removal. A required cleanup failure leaves the source
available for an idempotent retry. No vector deletion runs after source
removal, so a same-ID recreation cannot lose its shared version 1 IDs.

Cleanup-owner expiry is not automatic takeover authority. A delayed provider
delete can outlive its lease, so another request must continue returning a
retryable busy result. After an operator has confirmed that the owning process
is terminated, it can call
`force_release_expired_conversation_vector_cleanup_after_confirmed_termination`
with the exact row incarnation and owner token. The transaction rejects an
unexpired lease, a replacement row, or a different owner.

Account deletion marks and projects every current conversation before its
Firestore wipe, then purges the captured legacy and generated records.
Generated transcript records use the persisted count for exact-ID cleanup,
while legacy transcript records retain their separate prefix cleanup. The
worker retains every cleanup claim until the authoritative Firestore wipe
succeeds. A failed wipe releases those claims before recording the retryable
failure.

## Compatibility

Jobs without a plan version are treated as version 1. While its fanout remains
claimable, a version 1 worker waits for the vector leaf calls before external
fanout but does not write effect checkpoints. An already-completed version 1
fanout preserves its acknowledgement and does not replay shared vector IDs.
Version 1 keeps the existing fanout key, job ID, stable vector IDs, and
optional-store behavior. It does not use per-job generation-scoped vector IDs
or claim that legacy stable IDs can be cleaned safely after same-ID
recreation. When no vector store is configured, the vector helpers retain
their existing fallback instead of turning the job into a deterministic
failure.

The rollout uses two explicit modes:

1. `standby` is the default. Deploy this mode to every finalization producer
   and worker first: backend-listen, pusher, backend, backend-sync,
   backend-sync-backfill, and backend-integration. Jobs retain the version 1
   storage shape, so an older worker cannot consume a version 2 ledger that it
   does not understand. Standby also preserves the version 1 job ID, fanout
   key, vector IDs, and optional-store behavior. Conversation rows may already
   carry an unused server-owned incarnation in standby.
2. `active` is enabled with
   `CONVERSATION_FINALIZATION_EFFECT_PLAN_MODE=active` only after every worker
   supports version 2. New jobs then store the plan version and completed
   effect keys. Active version 2 requires an initialized vector store and
   retries rather than checkpointing a vector stage when that dependency is
   unavailable.

Before switching to `active`, confirm that every finalization worker has an
initialized Pinecone index and that nonterminal version 1 jobs have drained.

Activation is a binary rollback barrier. After any version 2 job exists, every
worker must remain version 2 aware. Configuration can return to `standby` for
new jobs, but deploy rollbacks must keep a version 2 aware binary until all
existing version 2 jobs are drained or resolved.

An invalid or missing mode fails closed to `standby`.

## Verification signals

When investigating incomplete enrichment:

- Confirm that the finalization job is nonterminal while a required effect is
  failing.
- Confirm that `completed_effects` contains only the fixed key names above.
- Confirm that a new lease skips keys already present in the ledger.
- Confirm that `transcript_vector_count` is set before transcript writes and
  remains unchanged across retries.
- Confirm that cleanup issues exact old-generation IDs and does not call the
  provider list API.
- Confirm that a newer revision receives a different vector generation and
  survives cleanup of the old job.
- Confirm that a recreated conversation has a different row incarnation and
  vector generation.
- Confirm that deletion marks the source before vector cleanup and leaves the
  source intact when required cleanup fails.
- Confirm that a live pre-fanout processor or leased finalizer returns a
  retryable deletion result and cannot admit new fanout after the pending fence.
- Confirm that an expired cleanup owner remains exclusive until an operator
  confirms termination and releases that exact incarnation and owner token.
- Confirm that account deletion keeps cleanup claims through the Firestore
  source wipe and releases them when that wipe fails.
- Confirm that external integrations and fanout completion occur only after
  the required key set is complete.
- Confirm that repeated deterministic failures reach the existing
  `dead_letter` terminal state rather than a false successful completion.
