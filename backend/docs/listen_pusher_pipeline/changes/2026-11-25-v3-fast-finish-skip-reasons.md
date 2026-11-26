# Fast-finish skip reasons

A production readback on backend-integration (2026-11-25, 100 min) showed 10 manual finishes
(`omi_conversations_v3_batch_manual_end_total`: 8 `promoted`, 2 `multi_unit_deferred`) but only one
fast-finish attempt (`omi_conversations_v3_fast_finish_total{outcome="written"}`). Record admission's
manual-finish hook (`utils/batch_pipeline/live.py`, `_manual_finish_admitted`) returned silently before
the pass, so nothing said why. This serves SCA-4084.

- New counter `omi_conversations_v3_fast_finish_skipped_total{reason}`, incremented once at that early
  return. Reasons are a fixed set: `mode_off` (`CONVERSATIONS_V3_FAST_FINISH=off`), `already_started`
  (this process already started a pass for the recording), or the first failing predicate from the new
  `fast_finish.candidate_rejection(row)`: `not_recording`, `no_manual_end`, `status_in_progress`,
  `status_processing`, `status_other`, `no_private_cloud_sync`, `protection_level`,
  `projection_revision`, `audio_partial`, `deleted`, `discarded`, `locked`, `custom_stt`. No uid,
  conversation id or content is ever a label.
- `fast_finish.candidate(row)` is now `candidate_rejection(row) is None`, so the screen and its reason
  cannot drift. A unit test checks it against the previous expression on every combination of the
  fields it reads.
- Owners outside the cohort still pass this screen and are counted `not_enabled` by
  `omi_conversations_v3_fast_finish_total`, as before.
- The counter is added to the `cloud_run_gmp_sync.yaml` keep rule (`cloud_run_gmp_sidecar.yaml` already
  keeps `omi_.*`).

Observability only: no behaviour change, no flag, no additional Firestore reads or writes. Rollback is
a revert.

[Pipeline contract](../../listen_pusher_pipeline.mdx)
