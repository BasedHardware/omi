# Batch-lane storm gate: the bare transaction lanes join the shared damper

Every batch-pipeline transaction used to split into two contention shapes:
the store, projection, retention, pump, scheduler and purge lanes ran the
bounded engine (`run_with_transaction_contention_retry`) with the shared
per-label storm damper, while four lanes still handed their body to a bare
`client.transaction()`:

- the privacy fence — `advance_privacy_generation` /
  `finish_privacy_purge` on the `batch_pipeline_privacy` control document
  (`database/batch_pipeline_privacy.py`),
- the lease revocations — `quarantine_fenced`
  (`database/batch_pipeline_recovery.py`) and `cancel_fenced_recovery`
  (`database/batch_pipeline_quarantine_recovery.py`),
- the voice-evidence receipts — `load_reference` and `publish`
  (`database/batch_voice_evidence.py`).

A bare transaction replays ONE transaction id inside the SDK's commit loop.
Inside an armed storm window that is the exact collision the shared damper
already measured: the id is retired mid-wave, an expiry surfaces as an
anonymous fault, and an exhaustion carries no label and no window — so the
lane re-strikes into the same hot `control`/`jobs`/`results`/`owners`/
`artifacts` rows the store labels storm on, multiplying the window every
other lane is trying to space out.

## What changed

`database/batch_pipeline_store.py` owns one shared doctrine,
`run_batch_pipeline_transaction`: entry consult (sleeps the label's residual
window, fleet-adopted and spill share-capped, before the first attempt — the
first attempt itself is never gated), bounded five-attempt ladder with one
fresh transaction per rung, mid-ladder gate that re-peeks the residual and
engages the capped wave ladder from the third failed rung, exhaustion that
arms the label and stamps the applied window onto `retry_after`, and a
commit that clears the ladder only when no concurrent arm bumped the
generation. The purge chain's `run_purge_transaction` (run 338) delegates to
the same doctrine and keeps its own module logger and labels.

The four lanes resolve their damper per call through
`batch_lane_storm_damper(namespace)` — both kill switches
(`BATCH_PIPELINE_CONTENTION_RETRY_ENABLED`,
`BATCH_PIPELINE_CONTENTION_STORM_DAMPER_ENABLED`) read per call, so a
dormant damper is `None` and the lane stays byte-for-byte the bare bounded
ladder. The privacy fence uses its own partition key
(`batch_pipeline_privacy`): the control document is not a namespaced batch
row, and purge bursts write it while every unit admission asserts it inside
the same window, so it damps in its own process-shared registry slot with
its own fleet mirror instead of borrowing a stage namespace's windows.

## Labels

Every join carries a static per-site label so the `*_backoff` lines and any
exhaustion stay attributable per site:

| Lane | Label |
| --- | --- |
| Privacy fence advance | `batch_privacy_generation_advance` |
| Privacy fence finish | `batch_privacy_purge_finish` |
| Recovery revoke | `batch_recovery_fenced_revoke` |
| Quarantine-recovery cancel | `batch_quarantine_recovery_cancel` |
| Voice-evidence receipt read | `batch_voice_evidence_receipt_read` |
| Voice-evidence publish write | `batch_voice_evidence_publish_write` |

Each lane's backoff lines are logged under the lane's own module logger,
like the purge chain's.

## Failure-Class

Failure-Class: FC-bare-batch-pipeline-lanes-collide-inside-armed-storm-window

The class: a lane that writes the shared hot rows without the bounded
engine and the shared damper collides inside the armed storm window the
other lanes damp, multiplying contention the platform already measured.
The joins close it for the last bare batch-pipeline lanes; the emitter
grids cross-verify the doctrine cell by cell against the same model walk
the purge grids used.
