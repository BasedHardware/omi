# Finalization capture-reliability fixes (2026-11-12)

Evidence: `omi-workspace` run `data/run-2026-11-12-capture-reliability/findings-finalization.md` (ro-prod, read-only).

## What changed

1. **Empty-summary refusals complete on the minimum.** A `SERVER_RECOVERY` run whose enrichment returned no
   structure now completes on `build_deterministic_minimum_structured` when the relevance verdict is `keep`, the
   transcript decodes and is non-empty, the conversation is plain (no photos, reminder, app selection or release
   probe), and the stored structure is replaceable (not rich, and untitled or `server_minimum`). Every other case keeps
   `RecoveryStructureUnavailableError`. Flag: `LISTEN_FINALIZATION_EMPTY_STRUCTURE_MINIMUM_ENABLED`, on unless set
   `false`/`0`/`off`/`no`. Guard log outcome: `selfheal_guard outcome=minimum_fallback`.
   The enrichment failure class is not logged: the empty result is returned without an exception, so no class
   reaches the guard without a larger refactor.
2. **Replay has an exit for refused accounts.** An exhausted replay whose account is in deletion or cutover is
   terminal-fenced (`_fenced_finalization_update`, `finalization_outcome=fenced`) instead of re-dispatched. No
   account-owned write happens.
3. **Due-marker sweep.** `reconcile_listen_finalization_jobs` re-marks queued or leased jobs older than 24 h with no
   `reconcile_after_at` as due, before the candidate page is read. It runs one bounded page per status, rotated
   through a persisted cursor (`conversation_recovery_state/due_marker_<status>`), on the existing
   `status` + `created_at` index. Counter: `listen_finalization_due_marker_sweep_total{outcome=remarked|skipped|error}`.
4. **Dead-letter family exported.** `omi_conversation_finalization_dead_letter_total` is allowlisted in both sync
   exporter files and the pinned contract list.

No Firestore index is added.
