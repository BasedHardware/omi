## Summary

Apply David's accepted 2026-11-09 flag rulings using the recorded 03:20Z production snapshot. Remove 17 rollout controls and preserve their current production behavior. Paid mobile visible restore stays off; the STT router stays on for all managed sessions with its health, capacity and withdrawal gates retained. Registry rows move to `retired`, and the pipeline flag budget falls from 165 to 161. The redundant Episodes cohort allowlist is removed with full admission.

All 42 retirement-list registry rows and all 103 registry-only rows remain unchanged in this lane. The lead combines the independent lanes before opening the PR. No production data, flags or deployments were accessed or modified here.

## Mixed-service exceptions

Do not graduate these five controls: reachable readers disagree in the supplied production snapshot. Keep their existing code and deployment wiring and review them on **2026-11-23**:

- `LIVE_CAPTURE_WINDOW_MERGE_UNION`
- `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS`
- `SONIOX_WIRE_LEDGER`
- `SONIOX_CAPTURE_AXIS_DIAGNOSTICS`
- `FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED`

Reader traces: `backend/docs/listen_pusher_pipeline/changes/2026-11-09-flag-graduation.md`. Scope audit and recovery validation: `data/run-2026-11-09-flag-graduation-recovery/README.md`.

## Product invariants affected

Preserves INV-MEM-4: canonical promotion remains the Long-term mutation authority. Preserves INV-TASK-2: capture and Suggested-task acceptance authority are unchanged. This change makes existing recorded production paths permanent.

## Validation

See the dated recovery evidence for exact commands and terminal results. No live checks are authorized for this lane. Rollback is a source revert; this change does not introduce a ramp.
