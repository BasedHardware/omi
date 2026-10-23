# Mobile release process

This is the repository-side contract for shipping the Flutter mobile app. It
describes admission and evidence; it does not grant store credentials or
replace the Codemagic/App Store Connect/Google Play owner runbooks.

## Release identity

Production mobile tags must use:

```text
v<major>.<minor>.<patch>+<positive-build>-ios-cm
v<major>.<minor>.<patch>+<positive-build>-android-cm
v<major>.<minor>.<patch>+<positive-build>-mobile-cm
```

`-ios-cm` may enter the iOS workflow, `-android-cm` may enter Android, and the
historical `-mobile-cm` form remains valid for either platform. The workflow
validates the tag, checked-out commit, and tag-resolved commit before invoking
Flutter. A malformed tag, platform mismatch, or source mismatch stops the
build.

## Admission evidence

The release source must have both of these successful checks on the exact SHA:

1. the first-attempt `Release Eligibility` push run on `main`;
2. the `Mobile Release Eligibility` aggregate from `Mobile App Checks`.

The aggregate deliberately treats conditionally inapplicable mobile jobs as
`skipped`, while failures, cancellations, pending results, wrong repositories,
wrong workflows, reruns, and wrong SHAs fail admission. The offline contract
and fixture tests live in `.github/scripts/verify_mobile_release_admission.py`.

## Store and distribution behavior

Automatic internal builds fail closed when an App Store Connect or Google Play
version lookup fails or returns malformed data. A successful empty response is
still allowed to seed from `pubspec.yaml`; a command failure is never turned
into build zero.

The internal dispatcher advances an iOS or Android baseline only after explicit
platform-matched distribution evidence. Upload/build completion alone is not a
distribution receipt. The current destination policy remains TestFlight
internal for iOS and Play internal with alpha promotion for Android.

## Release notes

User-facing mobile PRs author one JSON fragment per change under
`app/changelog/unreleased/` (`{"change": "..."}`; `{"kind": "none"}` for
internal-only edits). The `check-mobile-changelog.py` gate enforces this on the
PR diff and, identically, on the post-merge push where no PR metadata exists.
Authoring rules live in `app/changelog/README.md`.

Fragments are aggregated at release time, not continuously:
`python3 .github/scripts/mobile-changelog.py collect --version X.Y.Z` validates
every unreleased fragment, writes `app/changelog/releases/<version>.json`, and
removes the consumed fragments. Collecting the same marketing version again
appends new lines after the ones already collected; nothing rewrites or
compresses the authored text in the durable release file.

Store submission text is derived on demand with
`store-notes --version X.Y.Z --store ios|android` (or the `store_notes()`
function, used by `app/scripts/mobile_store_promote.py`). iOS gets
newline-separated bullets capped at 4000 characters; Android gets a
`; `-joined plain-text summary capped at 500 characters. Fitting the budget
only drops or truncates the derived text — the release file is never touched.
A release collected from only `none` fragments yields exactly
"Bug fixes and improvements".

Manual promotion: the `mobile-store-promote` Codemagic lane runs only on an
explicit trigger, requires `CONFIRM=submit-for-review`, selects an
already-uploaded build, and attaches the derived notes as the store "What's
New" text. Deriving notes never submits anything; a missing or invalid release
file fails the promotion closed.

## Daily store train

`.github/workflows/mobile_daily_train.yml` (workflow_dispatch; the fixed 14:00
UTC schedule was removed 2026-10-14 — dispatch is owned by the operator-side
release gate, a daily agent cron that audits the candidate against the live
baseline and only dispatches on a green verdict; manual dispatch with
`dry_run` remains available) starts the Codemagic `mobile-daily-train` workflow
on `main`, which runs `app/scripts/mobile_daily_train.py --platform both`.

Self-driving release posture (since 2026-10-14, intraday exposure ladder since
2026-10-17): the train no longer stops at a human queue point. iOS submissions
use `AFTER_APPROVAL` release type with the automatic phased rollout enabled and
explicitly attached post-submission (pausable in App Store Connect as the
post-release brake). Android candidates go to production as a staged rollout
at 1% (`inProgress`, `userFraction 0.01`; haltable in Play Console). The
posture lives in the constants at the top of `mobile_daily_train.py`
(`RELEASE_TYPE`, `PHASED_RELEASE`, `STAGED_ROLLOUT_FRACTION`,
`STAGED_ROLLOUT_LADDER`, `IOS_PHASED_JUMP_HOURS`, `ROLLOUT_HOP_MIN_HOURS`);
setting them to `MANUAL` / `False` / `None` restores the queue-for-a-human
behavior. Nothing here releases without the store's own approval; the gate's
evidence audit always runs first.

Intraday exposure ladder (the agreed ~12-hour profile, 2026-10-17): Apple's
phased release is fixed at 1% on day 1 and 100% on day 7, and Play hops the
ladder one step per advancing run. To reach full exposure in about 12 hours
without widening early exposure, the train advances the already-released
rollouts itself between gate runs (Codemagic `mobile-rollout-advance`,
dispatched every 4 hours by `.github/workflows/mobile_rollout_watch.yml` via
`dispatch_mobile_rollout_watch.py`; the train runs with
`TRAIN_ADVANCE_ROLLOUTS=true` / `--advance-rollouts`, which never submits or
stages a candidate):

- iOS: when the live version's phased rollout (read via
  `GET appStoreVersionPhasedRelease`, whose `startDate` is the timing anchor)
  has been `ACTIVE` for `IOS_PHASED_JUMP_HOURS` (12h), the train sets it to
  `COMPLETE` (`PATCH appStoreVersionPhasedReleases/{id}`) — Apple's "release to
  everyone" — taking exposure from ~1% to 100%, and reads the state back. Only
  `ACTIVE` jumps: `PAUSED` is the operator brake, and any other state holds;
  unreadable state fails closed (holds).
- Android: the staged rollout hops one ladder step
  (`STAGED_ROLLOUT_LADDER`: 1% -> 10% -> 50% -> 100%) per
  `ROLLOUT_HOP_MIN_HOURS` (4h) window. A `halted` rollout always waits for a
  human.
- Receipts make the windows real: every advancing Android action stamps a
  minute-precision gate receipt into the Play release name
  (`1.0.554 (gate 2026-10-17-1307)`; legacy date-only receipts still parse).
  A retry inside the window reads the receipt and holds position instead of
  hopping twice; receipts live in server-side Play state and survive
  ephemeral build machines. A staged release with no receipt (renamed in
  Play Console, or in flight from before receipts) is not hopped: the train
  stamps a receipt at the current fraction and holds for the window.

Audited-candidate pins: the operator release gate audits a specific
platform/version/build before dispatching. Those identifiers travel with the
dispatch as optional `pin_ios` / `pin_android` workflow inputs
(`TRAIN_PIN_IOS` / `TRAIN_PIN_ANDROID`, `X.Y.Z/build`, or `none` — an audited
no-candidate verdict) and the train fails closed — no submission, no rollout
start — when the store no longer matches the audited verdict: a newer build
that appeared in the audit→dispatch gap is unaudited and refused, and a
pinned build that vanished fails closed too. The self-driving posture removed
the old human queue's final interception point; the pin is its replacement.
An unset pin leaves the platform unpinned (how the gate dispatches today);
making pins mandatory belongs to the gate, which lives outside this repo.

Gate receipts: see "Intraday exposure ladder" above — every advancing Android
action stamps a minute-precision receipt into the Play release name so a
retry inside an observation window cannot hop twice.

### One iOS version with Apple at a time

A version that is `WAITING_FOR_REVIEW`, `IN_REVIEW`, waiting for export
compliance, processing, or approved and unreleased (`PENDING_DEVELOPER_RELEASE`
or `PENDING_APPLE_RELEASE`) is never withdrawn or developer-rejected to make
room for a newer build. Withdrawing restarts Apple's queue: on 2026-10-23 three
overnight withdrawals (1.0.571 at 04:44Z, 1.0.572 at 12:03Z, 1.0.573 at 15:14Z
UTC), each made to ship a newer build, kept every one of them out of the store.
A newer build waits for the next train after the in-flight version is released;
urgent fixes ask Apple to expedite the version already in review. The train
holds on these states, `mobile_store_promote.py` refuses an iOS submission while
another version is in them, and an exception needs Nik's explicit go-ahead in
chat naming the version to withdraw.

iOS (App Store Connect, versions are read per state because the unfiltered
listing only returns live versions):

- live = newest `READY_FOR_SALE` version; candidate = highest TestFlight
  marketing version above it with a processed (`VALID`, not expired) build, and
  that version's highest build number. No candidate → nothing to do.
- Anything `WAITING_FOR_REVIEW`, `IN_REVIEW`, `WAITING_FOR_EXPORT_COMPLIANCE`,
  `PENDING_APPLE_RELEASE` or `PROCESSING_FOR_APP_STORE` → hold; one submission
  is in flight at a time.
- `PENDING_DEVELOPER_RELEASE` (approved, not released): the train attaches the
  phased rollout to the pending version and releases it via
  `POST /v1/appStoreVersionReleaseRequests` (verified live 2026-10-17 on
  1.0.564 — Apple honors the endpoint for COMPLETE review submissions even
  though it refuses to cancel them, 409), so the version starts at day-1 1%
  exposure with the pause brake available, and the newer candidate can then
  be submitted. As on submit, a duplicate-attach rejection is tolerated only
  when the read-back confirms the phased resource exists. A paused live phased rollout defers the release (plain hold).
  A pending version newer than every TestFlight build, or two pending
  versions, stops the train.
- Submission: `builds submit-to-app-store` with
  `--app-store-version-localizations` carrying the derived iOS notes for
  every locale of the live version (a bare `--whats-new` covers only the
  primary locale and Apple rejects the submission). The run ends only after
  the new version reads `WAITING_FOR_REVIEW`, and the phased rollout is
  attached to the new version (`POST appStoreVersionPhasedReleases`;
  a duplicate-attach rejection is tolerated only when the read-back confirms
  the resource exists). Under the self-driving posture the submission carries
  `--release-type AFTER_APPROVAL --phased-release`
  (`RELEASE_TYPE` / `PHASED_RELEASE` constants), so the version releases on
  Apple's approval; pausing the phased rollout in App Store Connect is the
  post-release brake, and the intraday ladder completes it after the 12-hour
  window. (Historical MANUAL shape: a `PENDING_DEVELOPER_RELEASE` version
  waited for a human console press; that posture is now only the rollback,
  see `RELEASE_TYPE`.)

Android (Google Play): candidate = highest version code on the `internal` and
`alpha` tracks whose release name version is newer than the live `production`
release. Under the self-driving posture (`STAGED_ROLLOUT_FRACTION = 0.01`) the
candidate is written to `production` as a staged rollout
(`mobile_store_promote.submit_android(..., status="inProgress",
user_fraction=0.01)`), haltable in Play Console. While a rollout is
in flight, the intraday ladder promotes it one hop per observation window
(1% -> 10% -> 50% -> completed), a HALTED rollout (`status: "halted"` or a missing
`userFraction`) always waits for a human, and a newer internal build waits
for the rollout to complete (Play allows only one staged release at a time).
A legacy Play draft holding the selected code converts straight into the
staged rollout. Setting `STAGED_ROLLOUT_FRACTION = None` restores the
queue-for-human behavior: candidates are written as `draft` releases (a human
presses Release in Play Console), and any rollout already in flight is parked
for a human instead of being advanced further.

Release notes: the train runs `collect` for a **new** candidate version in
its checkout (unreleased fragments fold into `releases/<version>.json`
without a commit, so notes are never empty); it logs the `collect` command to
commit the same lines to `main`. Ladder hops of an in-flight rollout never
collect: they re-use the What's-New text Play already holds for that rollout
(the durable release file is only a no-collect fallback), so fragments
authored for the *next* version are never misattributed to the one mid-flight.
No release file and no fragments fails the platform. The run ends with one
`TRAIN SUMMARY:` line; any platform failure exits non-zero.

Rollback: revert the `codemagic.yaml` workflow additions to retire a lane,
set the posture constants back (`RELEASE_TYPE = "MANUAL"`,
`PHASED_RELEASE = False`, `STAGED_ROLLOUT_FRACTION = None`) to restore the
queue-for-human train, and delete `app/changelog/releases/<version>.json` to
drop a collected release. Store-side brakes (a paused iOS phased rollout, a
halted Play rollout) and builds already uploaded to a store are unaffected by
repo-side rollback.

## Operator prerequisites

- GitHub branch protection must require the intended release-eligibility and
  mobile aggregate checks before tag admission is enabled.
- Tagged Codemagic workflows need a read-only `GITHUB_TOKEN` (or equivalent
  Codemagic environment variable) for `collect_mobile_release_admission.py`.
  The collector authenticates the GitHub run/check evidence before the local
  verifier accepts it; a missing token fails the tag build closed.
- Codemagic internal dispatch passes an evaluated source-SHA pin as an
  environment variable; the internal workflow compares it with its checked-out
  `HEAD` before doing build work. A branch move therefore fails closed.
- The dispatcher fetches Codemagic build details and requires a normalized,
  platform-matched post-publish receipt before a platform baseline advances.
  iOS requires every App Store Connect task to succeed; Android requires the
  settled Codemagic publishing action. Missing, failed, or unknown evidence
  keeps that platform pending.
- App Store Connect beta-group membership and automatic distribution are
  operator-owned. An uploaded/processed IPA is not proof that the intended
  group can receive it; verify the configured group and its capabilities in
  App Store Connect when investigating a failed post-publish task.

No workflow in this document bypasses store approval or operator brakes:
both stores' own review must approve before anything ships, iOS rolls out in
phases pausable in App Store Connect, Android's staged rollout is haltable in
Play Console, and the manual lane needs an explicit confirmation. What changed
on 2026-10-14 is the queue point: after approval, releases proceed without a
further human console press (previously: manual developer release on iOS and
a Play production draft).
