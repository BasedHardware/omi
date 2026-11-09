# Pipeline scheduling kills and bounded recovery

This corrects the dark policy in [pipeline attention](../../listen_pusher_pipeline.mdx#pipeline-attention),
per David/coordinator's 2026-11-08 rulings. No switch default, cohort, deployment,
processing reserve or producer grace changes. Skip-silence remains declaration-only,
unwired and default off; wiring and its producer-path test belong to #24913
(owner @Git-on-my-level).

- New deadline/projection admission requires `PIPELINE_ATTENTION_MODE=serve`,
  the owner grant and `PIPELINE_SEAL_FAST_ENABLED=true`. Off/shadow/seal kill
  restores normal notes and episode timing. Saved metadata remains inert while
  killed, and durable work is retained.
- Capture end +1,680 seconds remains the absolute dispatch ceiling for admitted
  valid clocks, with the unchanged 120-second work reserve. A fully sealed,
  fully projected ready capture can run notes before that ceiling without a
  presence lease or promotion. Presence still selects fast record scheduling.
- Pending seal/projection may poll in 60 seconds only until the original
  obligation's first-pending clock +3,600 seconds. A retry/reason change cannot
  reset it. The last short wake is clipped to that bound. Missing legacy budget
  metadata cannot create an unlimited new wait. Exhaustion or kill uses normal
  notes admission and its existing custody, privacy and persistence fences;
  no seal/projection proof is minted. Both pending reasons also join the existing
  stuck-custody hourly classification, including for older in-flight contexts.
- Skipping preview notes first commits native registration and a coalesced,
  durable ordinary notes obligation before capture finalization completes.
  If batch admission fails or dead-letters, the retained preview still reaches
  the ordinary notes worker. A later batch projection uses that same obligation.
  Seal kill retains the original preview finalization path.
- Empty results from accepted pipeline work use the existing atomic three-owned-
  attempt budget even after the seal/projection wait has ended or mode is killed.
  Exhaustion leaves explicit terminal blocked metadata; it preserves existing
  structured content and raw audio. Intentional minimum/quota outcomes retain
  their existing treatment. No empty response is silently acknowledged as notes.
- The record deferral's fresh scheduling clock requires the existing record flag,
  serving mode and owner grant. Every off/denied case uses the original captured
  `now + delay`, with no extra clock read. No new flag is introduced.

Regression coverage in existing suites:

- `test_new_obligation_flags_off_preserve_legacy_hold_and_notes_timing`
- `test_ready_patient_notes_beat_absolute_ceiling_without_sliding_it`
- `test_pipeline_wait_reaches_normal_notes_and_terminal_state_after_one_hour`
- `test_pipeline_pending_reasons_use_existing_slow_retry_classification`
- `test_batch_failure_keeps_durable_preview_notes_fallback`
- `test_seal_flag_or_mode_off_keeps_legacy_preview_notes_path`
- `test_pipeline_empty_after_seal_and_recovery_exhausts_three_attempts`
- `test_pipeline_empty_output_budget_is_durable_with_first_summary_flag_off`
- `test_deferred_record_clock_is_legacy_unless_record_flag_and_cohort_serve`
- Episode kill/expiry tests cover saved deadlines and projection waits too.

These are hermetic scheduling/persistence tests, not provider, device, battery,
production latency or rollout acceptance. All activation requirements remain.
