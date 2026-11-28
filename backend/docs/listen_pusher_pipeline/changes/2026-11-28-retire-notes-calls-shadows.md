# Retire the notes-packet and calls-recap shadows

**What changed.** `NOTES_PACKET_V2_MODE` and `CALLS_RECAP_MODE` are bound to an explicit `off` on every runtime
that reads them. Before this change neither key was set, so both ran as an implicit `shadow`. No runtime sets a
`*_SERVE_PERCENT` or `*_SERVE_UID_SHA256S` cohort key, so no account was served the new path, and every user
already got the legacy output. The code paths are deleted in a follow-up PR.

The `off` bindings cover these runtimes:

- GKE `backend-listen` and `pusher`, dev and prod (Helm values, plus the `gke` sections of
  `backend/deploy/runtime_env.yaml`).
- Cloud Run `backend`, `backend-sync`, `backend-sync-backfill` and `backend-integration`, dev and prod. These
  cover finalization, notes, episodes, open loops and the recap API.
- The Cloud Run job `notifications-job`, dev and prod. It runs the daily recap through
  `utils/other/notifications.py` and `utils/other/daily_recap.py`.

The x-connector-sync, frame-request-retention and day3-reengagement-email jobs import notes modules but never
call a reader, so they need no binding.

**Contract.** These are rollout env vars. The listen and pusher env contract lives in
[`listen_pusher_pipeline.mdx`](../../listen_pusher_pipeline.mdx), section "2.1 Durable finalization ownership".
Finalization called the calls-recap boundary projection there. Under `off` that projection returns the
conversation unchanged and reads no boundary store.

**Why.** David ruled on 2026-11-28 to retire both. The 24-hour readouts showed 57% agreement for the notes
packet and 6% for calls recap.

**Output.** Unchanged for every user. Outside a serve cohort, shadow work only computed and discarded comparisons.
`off` also stops the calls-recap boundary-store reads on each finalization, and the shadow comparison metrics
(`omi_notes_refactor_shadow_total`, `omi_calls_refactor_shadow_total`) for these checks.

**Rollback.** Revert the PR, or set either key back to `shadow`. Until the code deletion lands, `shadow` restores
the comparisons.

**Readback.** On each serving revision and the notifications job, read the env and confirm both keys are `off`.
Then confirm that `omi_notes_refactor_shadow_total{check="packet"}` and
`omi_calls_refactor_shadow_total{check="call_metadata"}` stop increasing.
