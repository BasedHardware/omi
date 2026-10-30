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
