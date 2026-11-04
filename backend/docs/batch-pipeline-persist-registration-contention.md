# Batch pipeline: persist-phase artifact registration replays contention

The GPU worker's persist stage registers every durable artifact — results,
native audio, voice evidence, recovery payloads — through
`register_batch_artifact`, a read-write Firestore transaction over the hot
segment job and the batch privacy fence. Under merge/admission load a
read-time `Aborted` inside that transaction escaped to the worker as a raw
`google.api_core.exceptions.Aborted` and failed the whole unit: the worker
logged `batch_worker_failed error_class=Aborted stage=persist`, the
scheduler walked the unit back through its bounded retry ladder, and a
fresh GPU pass re-decoded, re-ran VAD/ASR/diarization and re-persisted —
for a commit nobody ever made. The completion phase hit the identical
class (`expire_completed_segment`) and already replays it through the
shared bounded budget; the persist phase simply never migrated.

## What changed

- `register_batch_artifact` runs its transaction under
  `run_retention_transaction`, the same bounded, fresh-transaction budget
  the completion phase uses, under the attributable operation label
  `batch_artifact_register`. Contention log lines for the persist phase
  now read `operation=batch_artifact_register` instead of blending into
  the unlabeled default.
- `run_retention_transaction` grew an optional `operation_name` parameter
  (default `batch_retention`), so existing callers keep their historical
  log attribution byte-for-byte.
- Each replay attempt constructs a fresh transaction
  (`max_attempts=1`): the outer budget is the only commit-contention
  budget, exactly like every other batch store transaction.
- The register body itself is unchanged. It already rereads every
  document at the top of the transaction — job state, projection binding,
  privacy fence, artifact reference — so every fresh attempt re-derives
  the lease, privacy-generation, retention-window and token-binding
  decisions it needs. Nothing is replayed past a state change: a lease
  that was lost, a privacy generation that moved, a token that rotated or
  a voice window that closed between attempts still refuses on the second
  attempt with the same typed error as before.

## Contracts that do not change

- `BATCH_PIPELINE_CONTENTION_RETRY_ENABLED=false` restores the bare
  single-shot commit (`register(client.transaction())`): one transaction,
  SDK-native commit-abort handling only, no jitter sleeps. This is the
  rollback path.
- Non-contention failures were never replayed and still are not:
  `BatchPrivacyBlocked` (including `result_lease_lost`), owner mismatch,
  missing-job refusals, unknown artifact kinds and the voice retention
  window `PermissionError` all surface on the first attempt.
- The atomicity and idempotency shape is unchanged: the artifact id is
  still the deterministic `sha256(segment_id + uri)` identity, a lost-ack
  re-registration still takes the no-write existing-document path, and
  `mirror_refresh` still runs exactly once, after the winning commit.
- Worker-visible persist failure behavior is unchanged for everything
  that is not contention: any persist exception still fails exactly its
  own unit, sibling persisted results stay intact, and the scheduler's
  retry ladder and quarantine accounting see the same failure records.

## Runbook

Contention on the persist path now surfaces as
`firestore_transaction_contention operation=batch_artifact_register`
lines (`outcome=retry`, then `outcome=recovered`, or `outcome=exhausted`
after the shared five-attempt budget) instead of raw
`batch_worker_failed error_class=Aborted stage=persist` events. An
`outcome=exhausted` line means five fresh transactions all aborted on the
same documents: look for a writer storm against that segment's job doc or
the owner's privacy document, not for a persist defect.

Failure-Class: FC-persist-registration-read-abort-fails-gpu-unit-and-requeues-it
