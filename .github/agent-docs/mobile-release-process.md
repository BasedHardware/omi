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

`.github/workflows/mobile_daily_train.yml` (14:00 UTC, or `workflow_dispatch`
with `dry_run`) starts the Codemagic `mobile-daily-train` workflow on `main`,
which runs `app/scripts/mobile_daily_train.py --platform both`. The train
queues builds for a **human** release; it never releases anything itself.

iOS (App Store Connect, versions are read per state because the unfiltered
listing only returns live versions):

- live = newest `READY_FOR_SALE` version; candidate = highest TestFlight
  marketing version above it with a processed (`VALID`, not expired) build, and
  that version's highest build number. No candidate → nothing to do.
- Anything `WAITING_FOR_REVIEW`, `IN_REVIEW`, `WAITING_FOR_EXPORT_COMPLIANCE`,
  `PENDING_APPLE_RELEASE` or `PROCESSING_FOR_APP_STORE` → hold; one submission
  is in flight at a time.
- `PENDING_DEVELOPER_RELEASE` (approved, not released): if the candidate build
  is already attached to it, leave it for the human. Otherwise cancel its
  completed review submission (`PATCH /v1/reviewSubmissions/{id}
  canceled=true`, i.e. `app-store-connect review-submissions cancel`), wait for
  `DEVELOPER_REJECTED`, then submit the candidate. A pending version newer than
  every TestFlight build, or two pending versions, stops the train.
- Submission: `builds submit-to-app-store --release-type MANUAL
  --no-phased-release` with `--app-store-version-localizations` carrying the
  derived iOS notes for every locale of the live version (a bare `--whats-new`
  covers only the primary locale and Apple rejects the submission). The run
  ends only after the new version reads `WAITING_FOR_REVIEW`.

Android (Google Play): candidate = highest version code on the `internal` and
`alpha` tracks whose release name version is newer than the live `production`
release. It is written to `production` as a `draft` release
(`mobile_store_promote.submit_android(..., status="draft")`); a human presses
Release in Play Console. A later run overwrites the draft with the newer build;
a draft already holding the candidate code is left alone.

Release notes: the train runs `collect` for the candidate version in its
checkout (unreleased fragments fold into `releases/<version>.json` without a
commit, so notes are never empty); it logs the `collect` command to commit the
same lines to `main`. No release file and no fragments fails the platform. The
run ends with one `TRAIN SUMMARY:` line; any platform failure exits non-zero.

Rollback: revert the `codemagic.yaml` workflow additions to retire a lane, and
delete `app/changelog/releases/<version>.json` to drop a collected release.
Neither affects builds already uploaded to a store.

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

No workflow in this document releases a build to users: the daily train stops at
App Review (manual release) and at a Play production draft, and the manual lane
needs an explicit confirmation.
