# Daily Recap recovery

The scheduled notifications job generates the current day and walks back at
most seven days, with a three-new-record cap per recipient pass. That bound
does not cover every missing day after a long outage. The job fixes on main
restore scheduling; they do not make the older days reachable in mobile UI.

## One creation authority

All clients use `POST /v1/users/daily-summaries` with an explicit `YYYY-MM-DD`
account-local calendar date. The endpoint returns the existing record for that
date or generates and persists a missing one through the shared notifications
generation function. It does not require an FCM token, send a push, enable the
daily schedule, or replace the original conversations. The older
`daily-summary-settings/test` route remains a released-client boundary; it is
not a creation path for these in-tree clients.

- Mobile: `DailyRecapRecoveryAction` is reachable from Daily Recaps and from
  Settings → Notifications even with zero recaps or the schedule disabled.
  `DailySummaryCreationApi` uses the shared typed HTTP/auth path and refuses a
  late result after an account switch. Success opens the returned record; the
  recap list reloads server pagination rather than inventing an older first-page
  row. Successful recovery invalidates mounted Home readers even when recovery
  was opened from Settings and Home previously had no recaps. A read generation
  rejects older responses; failed reads preserve cards and expose retry.
- Web: Conversations → Generate recap uses `useRecaps.generateForDate`, updates
  the existing store/cache once per ID, and opens the result. Account generation
  and widget lifetime fence late results. Owner-scoped cache keys keep account
  snapshots separate. Initial reads, refreshes, and pagination share one read
  lease; a successful creation/deletion forces older reads to re-read the server
  before adoption. Creation errors leave the list intact. Read failures are
  visible in Conversations with a recap-specific retry.
- macOS: the existing day-row create action already uses this endpoint through
  `APIClient.createDailySummary`; no parallel route is added.

400 is an empty/ineligible day, 409 is in-flight generation, 429 is a cooldown,
402 is a plan gate, and transport/server/decode failures are errors. None is a
successful empty recap. Controls prevent duplicate submissions and keep the
selected day for a manual retry. Date selection is bounded to the past year;
the server remains authoritative for account-timezone/future-date validation.

## Implementation and verification

Tracked by [#11821](https://github.com/BasedHardware/omi/issues/11821).

- [x] Expose recovery in the reachable mobile settings and recap page.
- [x] Expose web creation in the existing conversation/recap destination.
- [x] Migrate the unused token-dependent client helpers to the shared endpoint.
- [x] Test response identity, status handling, cancellation, single flight,
  cache de-duplication, and account-switch rejection in the existing CI runners.
- [x] Publish recovery to Home and fence older recap reads across mutations.
- [x] Reconcile restored uploads without a job handle through retained-file retry.
- [x] Test retained file → upload → polling → confirmed processing and persistence.
- [x] Display failed/processing outcomes honestly on both Offline Sync screens.
- [ ] Release the mobile and web clients after merge.

## Recording synchronization boundary

`LocalWalSyncImpl.reconcileUploadedWals` is the owner of uploaded recording
recovery. Uploaded rows with a blank/missing job handle cannot be polled: retained
audio re-enters the existing deduplicated upload path without spending retry
budget, while missing local audio stays visible as unavailable. Both changes
persist before notification; account changes fence asynchronous file checks.
Accepted jobs remain processing until the terminal-policy boundary confirms
completion. A valid empty/silent completion remains complete, without endless
re-upload or a fabricated conversation claim.

Offline Sync rows say **Processed** after confirmed processing. The legacy
summary and empty-pending state do not claim all work is complete while another
recording needs attention. Local-copy retention copy states the deletion period
without promising a cloud audio copy. These changes do not alter retention,
upload batching, account capacity controls, or the customer's cloud-storage setting.

The backend's October scheduler/gateway/retry fixes are already deployed. This
change requires mobile and web releases after merge and uses existing backend
contracts. Existing #21347 read-validation work and #21319 pendant batching work
remain separate; neither is proven to match this report. Account outcome checks
remain tracked by [#21360](https://github.com/BasedHardware/omi/issues/21360).

## Featurebase status reporting

Check current `origin/main` against each symptom before calling a report fixed.
For each required part, record its issue/PR, whether the actual code is on main,
whether it covers the symptom fully, and whether the relevant backend or client
release contains it. A backend deployment does not publish a mobile UI change.
An open read-validation PR does not repair scheduling, historical gaps, or sync.

The October 3 outage has scheduling/gateway/retry fixes on main and production
deploy evidence. Historical recovery needs these client controls. An unspecified
sync complaint cannot be matched to a particular fix without its observable
failure. A bounded server trace can verify the sampled stored rows, not every
phone-local recording. Do not promise historical regeneration or full recording
recovery unless the corresponding account outcome has actually been checked.
