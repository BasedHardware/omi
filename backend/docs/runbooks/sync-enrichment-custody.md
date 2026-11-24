# Sync enrichment custody

The sync reprocess outbox owns accepted summary debt. A Cloud Task is only its
wake; an ACK never implies that a summary exists.

- A merged donor transfers to the same owner's canonical outbox in one
  transaction, with privacy/redirect revalidation, earliest admission/deadline,
  active-lease preservation and canonical empty-output budget preservation.
  Only the normal canonical callback may claim/publish a summary receipt.
- Open live capture and unresolved redirects persist a deferred disposition
  and a later wake before ACK. `summary_deadline_at` remains the original
  deadline even when the next scheduling time is later.
- Active-lease duplicates and stale/completed wakes ACK. A scoped heartbeat
  retains the processing lease; the durable watchdog recovers after expiry.
- First-summary watchdogs read Cloud Tasks **BASIC** metadata. A present task
  retains its name, including legacy repair-generation names. Only NotFound
  permits a replacement name; permission/transport errors retain debt and log
  an error. Runtime identities need `cloudtasks.tasks.get` (Cloud Tasks viewer).
- Task probes have a three-second timeout and no SDK retry loop. Shared CAS
  checkpoints space probes by five minutes. A pass limits probes to 100, scans
  to ten pages and elapsed work to ten seconds plus an in-flight RPC. The
  durable `sync_reprocess_scan/cursor` keyset position advances between passes
  and wraps at exhaustion, so a valid prefix cannot hide later missing wakes.
  Both the C3 enrichment maintenance entry and the legacy sync entry use this
  checkpoint. It carries inspection progress, never ownership or a lease.

The incident's real callback/state-machine regressions live in
`tests/unit/test_sync_enrichment_custody.py`; atomicity, forced contention and
loopback HTTP behavior use
`tests/integration/test_sync_enrichment_custody_emulator.py` with anonymous
demo-project Firestore and an outbound-network guard.

Rollback to the preceding immutable backend image preserves canonical and
deferred outbox rows; the old reader ignores new checkpoint/disposition fields.
Do not delete outbox documents, queued tasks or accepted deadlines. The old
image reintroduces the retry/backoff defect. Batch recovery queue isolation can
separately be rolled back by clearing `BATCH_PIPELINE_RECOVERY_TASKS_QUEUE` on
integration; it never changes the stable paid provider intent.

## Scoped operator re-wake

`scripts/redrive_stalled_enrichment.py` accepts a private JSON list of outbox
keys and defaults to read-only inspection. Apply requires the plan SHA-256,
`prod-operator`, an explicit run id and pages of at most 25 (default one).
Start with one owner's one-row canary and verify its ordinary worker persists
the title and releases the hold before advancing the fleet pages.

Each transaction rechecks an untitled completed row held over one hour, no
active outbox lease or terminal budget, all linked batch jobs committed, and
the normal account/conversation privacy fence. It increments `wake_generation`
and enqueues through the existing named-task tooling after commit. It never
edits conversation content, retries transcription or changes accepted deadlines.
On enqueue failure, stop and rerun the same page and run id: that reuses the
repair name. Do not mint a new run id to hide a failure. Re-wakes are redundant
hints; a pinned run id refuses a different id. The normal worker's lease,
revision and paid-output fences still apply.
