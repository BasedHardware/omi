# The custody-commit availability shed: a blip no longer voids a window

Shipped 2026-11-05. One durable audio window commit runs four GCS operations
as single explicit attempts (`timeout=10, retry=None`): the media upload, its
generation read, the manifest upload, and its generation read. A momentary
availability blip on any single one of them used to void the entire commit.

## Root cause (prod evidence)

The Loop S prod-log sensor's second-largest pusher signature (~1,000
tracebacks per 30 minutes, 2026-11-05 window) is the `finish_receive` →
`_queue_private_cloud_chunk` traceback family. The shutdown tail logs it for
every durable window commit that raises anything other than a queue-wait
timeout or a client disconnect — and the commit path was the only audio
custody boundary with no availability handling at all:

- `utils/other/storage.py::archive_capture_bytes` uploads each immutable
  object with `blob.upload_from_string(..., if_generation_match=0,
  timeout=10, retry=None)` — one attempt, deliberately outside the SDK's
  silent retry budget.
- `utils/other/audio_outbox.py::_generation` pins the object with
  `blob.reload(timeout=10, retry=None)` — also one attempt.

Every other boundary in the audio lane already classifies and sheds the same
faults: the session-admission reads have their bounded shed
(`routers/pusher.py`), the pack-listing boundary has the SDK replay tuple
(`utils/storage_retry_types.py`), and `utils/firestore_transient_types.py`
carries the availability classifier the rest of the database tree retries
on. The metrics vocabulary even reserved a `transient` custody-failure
reason for "any failure after its bounded retry budget" — with no code that
ever produced it.

The failure mechanics compounded one blip: at the shutdown tail the commit
failure closes the session 1011 and leaves the producer unacknowledged (the
client must reconnect and replay the window); mid-session it latches the
`durable_commit_unresolved` custody fence, so every later window of that
session is refused unseen and the tail then raises the fence RuntimeError —
more tracebacks for the same original blip. Note the budget-saturation
cause that fills the same signature was fixed separately (trigger-lane
budget isolation, 2026-11-05); this change removes the availability-blip
cause, so a transient storage fault no longer terminates custody capture.

## The change

- `utils/other/audio_outbox.py` adds
  `_commit_op_with_transient_shed`: each of the four GCS ops inside
  `commit_capture` is re-attempted up to 3 times behind a short doubling
  backoff (0.1s, 0.2s) when a single attempt answers with a member of
  `utils.storage_retry_types.STORAGE_RETRYABLE_TYPES` (the tuple the storage
  SDK's own default retry replays: 429/500/502/503/504 plus connection
  resets) or the `requests` transport family that carries them.
- Every retry is strictly faithful to custody: the uploads are
  content-addressed with create-if-absent preconditions, so an attempt that
  landed answers the retry with `PreconditionFailed` and the existing digest
  acceptance keeps the first immutable generation (no ciphertext rotation,
  no second billable object, no double-counted metric); the generation reads
  are read-only. A retry never re-runs a step that already committed — once
  the media generation is pinned, only the manifest side can re-attempt.
- Exhaustion raises the last transient unchanged, marked
  `custody_shed_exhausted`, so the commit's failure accounting records
  `record_failure('commit', reason='transient')` instead of the unlabeled
  default. Deterministic refusals (conversation-tombstone deletion, identity
  collision, digest mismatch, quota-free 4xx) and cancels are never absorbed:
  they propagate on the first attempt exactly as before.
- `utils/other/audio_outbox_metrics.py` adds
  `omi_audio_custody_commit_transient_retries_total` and
  `omi_audio_custody_commit_shed_exhausted_total`, labeled by op
  (`media_upload`, `media_generation`, `manifest_upload`,
  `manifest_generation`), with scraped zero baselines, so pod-start
  cold-channel churn stays measurable without touching the loud
  commit-failure boundary.

The loud fail-closed semantics are untouched: a commit that exhausts the
shed still leaves the producer unacknowledged, the session still ends 1011
with a hold, and nothing is ever acknowledged that is not committed.

Failure-Class: FC-single-attempt-custody-commit-ops-void-windows-on-availability-blips

## Tests

`backend/tests/unit/test_audio_custody_commit_transient_shed.py` pins the
shed helper contract (replay-set membership, budget, backoff schedule,
exhausted mark, non-transient pass-through), every op wiring site in
`commit_capture` for every replay-set member, the custody invariants that
survive a recovered blip (content-addressed retries, digest acceptance of a
landed attempt, identity collision loudness, tombstone refusals un-shedded,
no re-upload of pinned objects), the parity of committed receipt bytes with
and without blips, the metrics contract, and the pusher session behavior at
window boundaries and the shutdown tail: a session whose first upload blips
once now ACKs every window and ends clean, where the previous code failed
the session 1011 and left nothing committed. The suite is red on any tree
without the shed (it imports the shed symbols).
