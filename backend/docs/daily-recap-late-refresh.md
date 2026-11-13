# Legacy daily recap late-input refresh

## Cause evidence

The legacy producer returned a complete recap before reading its inputs unless
NOTES_PACKET_V2_MODE served the owner. Late transcript/summary publication could
therefore leave a complete-looking recap stale indefinitely. The seven-day
backfill called the same producer and inherited that guard.

Source: `omi-knowledge-base/projects/omi-100m-plan/evidence/2026-11-11-quality-late-recap-cause.md`,
re-verified against Omi main `d25780aeeb42ac626c8f31554a3c0323dffcea5b`.
No production access or incidence queries were used for this implementation.
The executable regression is `tests/unit/test_daily_summary_late_refresh.py`;
the real route/storage checks are in `testing/e2e/test_daily_summary_validation.py`.

## Scope and review corrections

Implements section 3 of `findings-recap-late-refresh-scope.md` (refactor-lead,
2026-11-11), with quality-lead's `recap-scope-review.md` corrections taking
precedence. The supplied source documents were under `/tmp/omi-homestep-push/`.

- Default-on `DAILY_RECAP_LATE_INPUT_REFRESH_ENABLED`; terminal state is on,
  kill switch is `false`. Neither wave-2 mode is enabled or required.
- Keep the existing date window, noon split, delivery hour, prompt, validation,
  account-deletion, usage-budget and input eligibility gates. No user-visible text change.
- Fingerprint conversation membership, `sync_content_revision`, `content_revision`,
  `notes_llm_output_hash`, `summary_completed_at`, and eligibility provenance
  (`discarded`, `deleted`, `is_locked`, `content_kind`, `relevance_decision`,
  `sync_relevance_user_kept`). For legacy unversioned writers, hash summary
  title/overview/sections, app content, action descriptions and event content.
  Exclude generic `revision`, server update time, stars, folders, checkboxes,
  event-created state, locations and geocoding. No transcripts enter the digest.
- Use a separate `late_input_fingerprint_v1` field so the wave-2 fingerprint
  cannot be mistaken for this narrower identity.
- The first scheduled pass over a complete legacy recap without the narrow
  fingerprint never calls the model. It stores the current eligible-input fingerprint.
  Fresh adoption requires a parseable `generated_at` and, on every returned window
  row, parseable `created_at` and `summary_completed_at` at or before that time.
  No wave-2 fingerprint is required. Missing/unparseable stamps, a late row or
  completion, or ordinal content revisions greater than one schedule durable debt;
  a later admitted scan attempts repair. Unknown age is debt; `created_at` on the
  recap is not a substitute for missing `generated_at`.
  This evidence cannot reconstruct sources removed before the first adoption.
- Persist repair debt on `daily_summary_generation/{date}`. Preserve it when
  status changes. Reserve before every scheduled refresh model attempt in the transactional
  `daily_summary_refresh_budget/{UTC-date}` counter: at most two per owner per
  UTC day across all recap dates/workers; failures/conflicts consume attempts.
  The existing three-backfill-generation tick cap and job/user budgets still apply.
- Re-read the window after generation; reject changed candidates and retain debt.
  CAS the recap fingerprint in the content-write transaction. Never replace the
  recap document or patch visibility, creation time or delivery receipt. Patch
  `read_contract_version`, `action_items_coverage` and `memories_learned_coverage`
  with generated content so readers interpret the replacement consistently.
  Fingerprints use the eligible, non-discarded, bounded rows actually passed to
  the model, including on the verification read. A change between that read and
  commit leaves the original fingerprint for the next scheduled comparison.
  `late_refresh_verify_pending` is no longer written: the comparison itself is the
  verification mechanism. Repair debt, unlike that removed field, is read.
  A full 100-row window emits `window_truncated`; coverage beyond it is unknown.
- Same recap ID/deep link. Silence is a per-call result, never a persisted flag.
  A refresh alone never pushes, including an on-demand-created day without a
  receipt. An explicitly owed retry (`retry_delivery`) can still send the first
  successful push and persist its receipt; subsequent retries honor that receipt.
  Authenticated response models remove internal fingerprints, worker flags and
  delivery state. Explicit on-demand regeneration does not consume the scheduled
  refresh budget; it still marks repair debt until a verified commit.
  Backfill never pushes. Deleting an input removes it from subsequent generated
  content. If all inputs disappear, retain the legacy recap without a model call;
  this change does not introduce a purge policy.

## Bounds and telemetry

Automatic scans cover the current recap day and the existing seven-day backfill.
Historical recaps older than that window remain unrepaired automatically, including
obligations that age out. Fleet-wide first-pass incidence is unmeasured. Adoption itself has zero model
calls; later scheduled repairs are bounded by two attempts per owner per UTC day.
The initial backlog may age out under that cap. There is no extra-spend estimate.
Fresh adoption adds an input-window read and a transaction; unchanged scans add
input-window and marker reads. A refresh adds a second input read and bounded writes.

`omi_daily_summary_late_refresh_total{outcome}` has only these labels:
`adopted_fresh`, `adopted_stale_scheduled`, `refreshed`, `refresh_skipped_cap`,
`refresh_skipped_unchanged`, `refresh_conflict`, `window_truncated`.
Refresh calls use recipient outcome `refreshed`, never `generated`. The wave-2
`daily_recap_inputs` shadow agree/disagree series continues for its existing cohort. No identity/content labels or logs
are added. Rollback: set the kill switch to `false` to restore blind reuse of
complete legacy recaps; stored recaps, privacy and delivery state remain intact.
