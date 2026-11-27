# Held vendor units are re-woken when their deferred wake is lost

**What changed.** Batch maintenance (`/v2/enrichment/sweep`, every two minutes on backend-integration) now runs
`FirestoreProviderSttOutbox.sweep_held` after `sweep_running`.
- It pages up to 100 `vendor_held` jobs per pass by the `(state, enqueued_at)` index.
- It re-arms the provider-STT outbox row of each hold whose `vendor_hold.redrive_at` is more than 600 s overdue,
  only when the staged audio is provably inside the 60-day lifecycle under the input-retention contract
  (`input_retention.staged_enqueue`: `audio_staged_at`, else the legacy enqueue time, staging bucket only).
  An invalid staging clock or audio staged before the cutoff is never re-armed; it is counted as
  `provider_stt_held_expired`, and the hold's owner records its expiry.
- The rearm is the same fenced transaction the stranded-running sweep uses (#26120): the job is still held, the
  owner matches, the privacy fence holds, and the open row is due, unleased and not woken in the last 600 s.
- A redriven unit still goes through the paid-once bound (`check_new_attempt`).

**Why.** A held unit's redrive rides one deferred Cloud Task on its outbox row. When that wake was lost, only the
open-row sweep could re-arm it. That sweep reads 100 of the 434,882 open rows (mostly the allowance backlog,
SCA-4089) per pass with a per-instance cursor, so it never reached them. On 2026-11-27, 376 unsupported-language
units (10.1 audio-h) had been held 8–22 days, with `redrive_at` 196–334 h overdue, which blocked the
batch-vendor-routing ramp (SCA-5183).

**Kill switch.** `BATCH_VENDOR_HELD_REDRIVE_ENABLED=false` (default on) stops held redrives. The router then skips
this sweep, so a deliberately parked hold goes stale and the guards measure it as a wedge.

**Cost.** At most 100 job reads per pass (72k a day), plus a 3-read rearm transaction per overdue unit. Draining
the 376 units costs at most about 10.1 audio-h × $0.12 ≈ $1.25 of Soniox, once.

**Verification.**
- Firestore emulator: `tests/integration/test_provider_stt_outbox_emulator.py`, which covers paging, overdue-only
  rearm, a missing or closed row recreated due now, the ancient skip, and the second pass being a no-op.
- Unit: `tests/unit/test_provider_stt_held_sweep.py` and `tests/unit/test_enrichment_route.py` (failure isolation,
  kill switch).
- Production readback: `max by (reason) (omi_batch_pipeline_vendor_held_units)` falls from 376 toward 0, and
  `omi_batch_pipeline_vendor_held_oldest_age_seconds` drops below a day.
