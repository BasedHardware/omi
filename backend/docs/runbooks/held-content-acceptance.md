# Held-content custody acceptance and graduation plan

Owner: subscription/backend; expansion and production approval: David.
Decision: DEC-BTR-005, graduate, 2026-10-20. Gate 1 due 2026-10-30;
server-gate retirement target 2026-11-12. This is a local-code acceptance
protocol and a **proposed** ramp, not evidence of production activation.

## Gate 1: hermetic acceptance

Run from a task checkout with its own Python 3.11 backend environment:

```sh
/path/to/omi-workspace/bin/omi-heavy run -- nice -n 10 env \
  BACKEND_PYTEST_WORKERS=4 \
  BACKEND_UNIT_TEST_FILE_LIST="$PWD/backend/tests/held_content_acceptance.txt" \
  bash backend/test.sh
```

The file list is the repeatable suite; each file has its own pytest process.
All identities, PCM and storage objects are synthetic. Unit conftest rejects
ambient Google credentials, and tests inject storage/Firestore/provider seams.
No dev URL is an isolation boundary: dev shares the production customer data
plane, and its load balancer can route listen/default requests to production.
Do not supply cloud credentials or contact a remote backend for this suite.
No GCP tier is required or used.

| Behaviour | Required evidence (test names; paths relative to `backend/tests/unit/`) |
| --- | --- |
| At-cap audio retained | `test_sync_cap_hold.py::test_hold_persists_encrypted_audio_before_manifest_and_never_expires`: decrypt exact source bytes, upload precedes manifest/summary, no application TTL, upload failure cannot acknowledge. `test_live_cap_hold.py::test_receive_cap_transition_and_resume_have_no_gap_or_paid_overlap`: denied capture goes to custody, with no paid/held overlap. `test_cap_hold_durability.py::test_failed_fragment_does_not_consume_slot_and_retry_reuses_identity`: failed publication retains PCM and identity. |
| On-device choice | `test_budget_choice_routes.py::test_choice_round_trip_replay_and_funded_resume_with_real_store[on_device]`: real HTTP + choice transaction, persisted choice replayed once, GET reports on_device, no processing/usage/audio records created. `test_held_content.py::test_conflicting_retry_cannot_overwrite_first_choice`: a conflicting retry cannot replace consent. |
| Funded resume | `test_budget_choice_routes.py::test_choice_round_trip_replay_and_funded_resume_with_real_store[upgrade]`: upgrade intent stays held until the allowance resolver admits managed processing. `test_sync_cap_hold_recovery.py::test_execution_denial_keeps_checkpoint_and_audio_without_stt`, `test_reset_or_upgrade_reuses_sync_and_settles_stable_usage_key`, `test_usage_failure_reuses_persisted_transcription_receipt`: no denied dispatch; funded work settles with the same usage key after restart. `test_processing_backlog.py::test_reset_keeps_backlog_waiting_and_estimates_from_totals`: funding/reset alone is not consent. |
| Deletion | `test_held_content_deletion.py::test_erasure_removes_source_fragments_frozen_pieces_and_sidecars_before_manifest`, `test_erasure_failure_retains_manifest_and_retry_removes_remaining_objects`, `test_account_storage_purge_covers_held_orphans_and_preserves_neighbour`, `test_account_wipe_enumerates_custody_and_choice_subcollections_even_without_root`: remove all held artifacts, retain retry authority on failure, preserve the v4 purged publication barrier, purge owner orphans and discover nested records even without a root document. |
| UTC-month rollover | `test_held_content.py::test_budget_period_uses_utc_month`; `test_live_cap_hold.py::test_capture_month_boundary_flushes_exact_frames`; `test_budget_choice_routes.py::test_new_month_expires_dont_ask_and_rejects_stale_replay`, `test_rollover_during_allowance_read_rejects_choice_without_mutation`; `test_processing_backlog.py::test_reserved_attempt_does_not_dispatch_if_month_rolls_during_claim`: UTC buckets split exact frames, preference expires, stale writes fail and prior consent cannot spend the new month. |

Acceptance scope: backend custody and wire semantics using fakes. On-device
choice switches **new** client recordings to an already supported local engine;
it neither downloads nor locally transcribes server-held backlog. No mobile
rendering/engine/device acceptance or deployed durability/index/scheduler claim
is made by these tests. Cap-hold [durability prerequisites](cap-hold-durability.md#deployment-prerequisites)
remain mandatory before release probes.

The current provider contract also does not guarantee exactly-once vendor spend.
A death after vendor acceptance but before result checkpoint may require one
additional funded request; a second ambiguity retains audio for reconciliation.
See the [documented uncertainty bound](cap-hold-durability.md#provider-spend-and-uncertainty).
Any observed duplicate is a ramp stop pending explanation, even within that bound.

## Gate 2: cohort mechanism

As inspected on 2026-10-20, `utils/held_content_flags.py` is **env-only**:
`HELD_CONTENT_ENABLED=true` plus exact `X-Omi-Held-Content: 1`. It takes no UID,
reads no runtime cohort, and does not change STT dispatch eligibility.

[PR #22810](https://github.com/BasedHardware/omi/pull/22810) was OPEN at inspected
head `ef29c43c3eaa5537f126bdbbcd80485a35e94632`. It proposes a process-wide
60-second stale-while-refresh token snapshot from
`rollout_cohorts/stt-cap-dispatch`, fenced by `environment`, with `tokens` such as
`uid:<PRIVATE_PROBE_UID>,pct:5`. Missing document falls back to the STT env;
malformed documents deny, and read failures retain the last snapshot.
It is not held-choice wiring and must not be assumed merged or deployed.

The choice API uses that pattern on a **separate** `rollout_cohorts/held-content`
document. `HELD_CONTENT_ENABLED` is the kill switch and is read before the cache.
A process that has not completed a refresh denies (cold start). A confirmed-absent
document falls back to `HELD_CONTENT_COHORT` (empty denies). Malformed or
wrong-environment documents deny. A refresh failure keeps the last snapshot and
never replaces it with a wider env value. Serving checks do not wait on Firestore.
Excluded accounts are rejected before usage and choice reads. This does not point
held-content at the STT document and does not turn the kill switch on.

For a stable account cohort: use private probe tokens, then probe union `pct:5`,
`pct:25`, `all`, identical across API replicas. Percent is a stable **UID bucket**
among capable accounts; it is not a guarantee of request-volume share. Observe
both selected capable users and capable request volume. Capability header alone
is not proof that a client has a working on-device engine.

Env-only alternative: an approved API revision with the flag true can receive
5%/25%/100% traffic, while the control remains false. That yields request-level
sampling with possible 404/200 alternation for one user; it cannot deliver a
stable 25% user cohort. If the prerequisite cannot land, explicitly approve this
alternative and require client 404 fallback/retry acceptance before using it.
For the required **5% API canary**, use 5% revision traffic and probe-only tokens
at first; then set that revision's held cohort to `all` so its capable requests
are exposed. Do not also apply `pct:5` (that would multiply exposure to ~0.25%).
After its watch, move the qualified image to all API replicas with `pct:25`, then
`all`; verify the observed denominator at every transition.

## Watches, metrics and stop rules

Before any expansion, record the exact running `OMI_BACKEND_RELEASE_SHA` (or
image digest/source), effective gate/cohort source on every participant, and a
new release-specific metric/log line. Verify the current custody reader,
ready indexes, scheduler receipt and restart recovery using only an approved
agent-owned release-probe fixture. Never put private UIDs in source, logs used
as public evidence, or PR text. Production writes and flag changes require
David's approval; this plan supplies no such approval.

Use the previous 24 hours and a concurrent capability-matched control as baseline.
Separate capped/waiting/no-consent audio from explicitly consented, funded,
original-lane-eligible recovery; an intentionally waiting item is not a stall.
The operator must have the following dashboard/alerts before starting the watch.
Every promotion gate below requires a fresh fleet snapshot:
`max(omi_held_content_fleet_snapshot_timestamp_seconds) > time() - 300`.
Read each fleet gauge from the newest snapshot:

`max(<gauge> and on (instance) (omi_held_content_fleet_snapshot_timestamp_seconds == on () group_left() max(omi_held_content_fleet_snapshot_timestamp_seconds)))`

Do not `sum()` these gauges, and do not `max()` the gauge itself.

| Signal | Promotion gate at **every** step, over a complete 24 h watch |
| --- | --- |
| Lost capture | `omi_held_content_capture_total{kind="lost"}`, `{kind="byte_mismatch"}`, `{kind="frame_mismatch"}`, and `{kind="ack_without_authority"}` stay at zero new events. Any loss stops immediately. Track volatile PCM separately: the last unpublished <=15 seconds is not an acknowledged custody guarantee. |
| Choice API and capability | `omi_held_content_choice_5xx_total` no more than baseline +0.1 percentage point. p95 of `omi_held_content_choice_latency_seconds` no more than 1.2x baseline (`histogram_quantile(0.95, sum by (le, method) (rate(omi_held_content_choice_latency_seconds_bucket[5m])))`). `omi_held_content_choice_total{outcome="no_capability"}` is the dark/excluded 404 path, not a 200. `{outcome="stale_period_409"}` may be non-zero at the UTC boundary and must not accompany a write. `{outcome="intent_only"}` counts upgrade writes; `{outcome="ok"}` is the other success. A managed grant from an upgrade choice increments `{outcome="intent_only"}` on the read and stops the step. Expected other 409/429 outcomes are not this series. |
| Recovery completion and held age | `omi_held_content_recovery_total{result="completed"}` / `{result="attempt"}` >= 99% within the predeclared visit/lease/discovery budget. `omi_held_content_oldest_age_seconds`, `omi_held_content_pending_count`, `omi_held_content_pending_seconds`, `omi_held_content_undated_pending_count`, and `omi_held_content_backlog_items` are one fleet snapshot from the `cap-hold-durable-redrive` scheduler (holds count + seconds sum, dated-hold count where `listed_at` > 0, oldest `listed_at` via `limit(1)`, and the sum of `processing_backlog.count` where `state="processing"`). Read each with the newest-snapshot expression above. An empty population is 0. `omi_held_content_undated_pending_count` > 0 fails the gate. If pending is above zero and no dated hold exists, `omi_held_content_oldest_age_seconds` is the sentinel -1, not 0; age 0 is an empty population or a hold listed at the snapshot clock. No unexplained oldest-age growth; no progress for two discovery rotations after lease expiry pages the owner. Hold the step if the denominator is too small; synthetic completion is mandatory. |
| Spend and reconciliation | Zero unexplained duplicate usage keys or repeat provider dispatch, no increase in `omi_stt_cap_recovery_reconciliation_total{outcome="redispatched"}` / `failed`; any lost or doubly funded probe audio stops immediately. Preserve receipts/audio for investigation. Compare vendor usage with internal accepted seconds; internal counters alone are not invoice proof. |
| Custody maintenance and deletion | `omi_held_content_erasure_total{outcome="failure"}` stays at zero new events after the retry budget. `{outcome="post_delete_publication"}` stays at zero: it increments only when a publish observes a `purged` receipt and returns before any manifest commit or upload. `event=cap_hold_redrive` progresses with no repeated `worker_deferred`, `seal_deferred`, `cleanup_deferred`, or `fleet_snapshot_deferred`. No launch-config errors; stable live STT and sync/client 5xx. |

Existing signals include `omi_stt_cap_provider_audio_seconds_total`,
`omi_stt_cap_recovery_reconciliation_total`,
`omi_stt_cap_launch_config_errors_total`, and structured `event=cap_hold_redrive`
logs. Held-content series above are armed without UID, hold ID, content, or
session labels. Age, undated-pending, and backlog gauges come from that one
scheduler snapshot, not from sweep pages or recovery. Expected fleet-snapshot cost is about one aggregation read per 1000 index entries, on a small held population, every 2 minutes; revisit a hard ceiling if pending count stays above 100k.
A missing
`omi_held_content_fleet_snapshot_timestamp_seconds`, or
`max(omi_held_content_fleet_snapshot_timestamp_seconds)` that is not greater
than `time() - 300`, fails every promotion gate. Do not promote on absent
gauges. Do not scan held manifests on a request.
Cohort source is `omi_held_content_cohort_source` (`doc`, `env`, or `none`) and
`omi_held_content_cohort_percent`. Refresh failures are
`omi_held_content_cohort_refresh_failures_total{reason="read|schedule"}`.
The deadline is not permission to promote with missing telemetry or no samples.

## Proposed calendar (all UTC)

| Date / watch | Action, owned by David or his explicitly authorized operator |
| --- | --- |
| By Oct 30 | Gate-1 suite green, Grok review and approved merge; independent cohort adapter and watch telemetry ready; qualify capable probe clients and deployed custody prerequisites. Record any blocker rather than enabling early. |
| Oct 31 12:00 – Nov 1 12:00 | Capable release-probe clients only; 24 h including the 00:00 UTC month boundary. Explicitly test stale choice, new-month consent, deletion and restart recovery. |
| Nov 1 12:00 – Nov 2 12:00 | 5% API canary revision; capable requests on that revision only, with full watch above. |
| Nov 2 12:00 – Nov 3 12:00 | Qualified image on every API replica; stable 25% capable account cohort, full 24 h watch. |
| Nov 3 12:00 – Nov 4 12:00 | 100% capable traffic, full 24 h watch. |
| Nov 4 – Nov 11 | Continue observation; reconcile vendor spend and resolve any uncertainty. Keep rollback ready. |
| Nov 11 12:00 – Nov 12 12:00 | Approved follow-up removes the HELD_CONTENT_ENABLED server gate and temporary exposure cohort, retains capability/entitlement/consent checks; 24 h post-change watch completes Nov 12. Retire registry row in that change. |

Any stop resets that step's 24 h clock after the fix. If the calendar no longer
fits, report the concrete blocker and new decision date; never skip a watch.

Rollback before gate removal: set `HELD_CONTENT_ENABLED=false` on every API
revision or route traffic to a qualified flag-off revision. A cohort-document
rollback may lag 60 seconds or retain stale state during read failure; use the
env kill/revision traffic rollback for an urgent stop. Confirm new requests return
404 and observe the running revision/config receipt. Keep current custody readers,
sealing/cleanup redrive, held objects, choices and usage/ingest receipts. Do not
revoke already accepted work by deleting data; dispatch admission has separate
switches and approvals. If pausing paid dispatch is required, follow its own
runbook. After gate retirement, rollback uses the last qualified gate-bearing
image with its flag false, retaining every durability-compatible reader.
