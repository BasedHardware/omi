# INV-DATA-1: Production-family customer data-plane continuity

**Status:** locked

This revision is proposed as of 2026-08-01. It must remain unchanged for seven
days, with its routing and qualification guards, before a follow-up can lock it.

**Statement:** A production-family artifact preserves one canonical customer
identity/data plane: Stable, Beta, internal, alpha, TestFlight, and Play Internal
use production Firebase Auth and Firestore (`based-hardware`) and preserve the
same UID, recordings, conversations, integrations, and sync state. On macOS,
Stable is `com.omi.computer-macos`; Beta is the separately-installable
`com.omi.computer-macos.beta` dogfood identity. Beta's separate local storage is
intentional isolation, not a separate cloud account or Firestore universe.

Stable is pinned to the production Python and desktop APIs. Beta is pinned to the
development Python (`api.omiapi.com`) and desktop (`desktop-backend-dt5lrfkkoa`)
serving endpoints, while its OAuth authority remains production (`api.omi.me`).
This is the sole allowed serving-plane split: it must not select another Firebase
project, account universe, or arbitrary endpoint.

The debug-only `local_prod` mobile profile is a developer-workflow exception,
not a serving-plane split: an explicit `OMI_APP_PROFILE=local_prod` dart-define
pairs production Firebase identity with a developer-chosen backend endpoint for
local development. Release builds reject the profile at startup, so no shipped
artifact can select it.

A release channel controls *eligibility, rollout exposure, diagnostics, and
feature availability*. It MUST NOT select a different account or customer-data
universe. TestFlight detection, an Android dart define, an update-channel
preference, a launch environment, or a bundled environment file is not
authority to redirect a production-family package.

The routing authority matrix is:

| Surface | Production-family authority |
| --- | --- |
| Flutter API | `https://api.omi.me/` |
| macOS Stable Python / desktop API | `https://api.omi.me/` / `https://desktop-backend-hhibjajaja-uc.a.run.app/` |
| macOS Beta Python / desktop API | `https://api.omiapi.com/` / `https://desktop-backend-dt5lrfkkoa-uc.a.run.app/` |
| macOS Beta OAuth API | `https://api.omi.me/` |
| macOS production identities | Stable: `com.omi.computer-macos`; Beta: `com.omi.computer-macos.beta` |
| macOS Firebase/Firestore config | the shipped production customer project (`based-hardware`) |

## MUST NOT

- Route Stable, mobile, or any other production-family artifact to development,
  staging, a beta API, or any arbitrary endpoint through a build define, CI
  variable, runtime preference, update channel, process environment, or bundled
  `.env` value. Beta's two fixed development serving authorities and the
  debug-only `local_prod` developer profile are the sole exceptions.
- Route Beta OAuth, Firebase Auth, Firebase API-key binding, or Firestore to a
  development project or endpoint. Beta must ignore `OMI_AUTH_API_URL`.
- Treat `OMI_BETA_RELEASE_RING`, `STAGING_API_URL`, `api-beta.omi.me`, or an
  equivalent beta/staging selector as a production-family routing mechanism.
- Publish an external preview under a production-family identity. An external
  preview needs a reserved preview identity plus signed metadata that explicitly
  selects its permitted data plane; malformed metadata fails closed to the
  production plane.
- Change a protected authority or Firebase/Firestore project as incidental
  release-pipeline work.

## Deliberate migration exception

A customer data-plane migration is not a beta rollout. It requires an explicit
`INV-DATA-1` PR citation, architecture and product review, identity/data
continuity evidence, a rollback plan, and an artifact-level assertion of the
new immutable authority before it can ship. The fixed Beta serving-plane split
above is not a customer data-plane migration. A separate development/test app
identity and test credentials may use non-production services; it must not
reuse a production-family identity.

## Guard tests

- `app/test/unit/env_test.dart` — production startup rejects non-canonical API
  routing; `local_prod` is rejected in release builds.
- `desktop/macos/Desktop/Tests/APIClientRoutingTests.swift` — Stable remains
  production-routed; Beta resolves only its fixed development serving endpoints
  and production auth despite contaminated values.
- `desktop/macos/Desktop/Tests/ExternalPreviewBuildTests.swift` — preview
  identities require signed backend metadata and fail closed.
- `.github/scripts/check-mobile-production-routing.py` — exact production
  Codemagic assignments and no legacy beta/staging routing selector.
- `.github/scripts/test_check_mobile_production_routing.py` — mutation contract
  for missing, conflicting, staging, arbitrary, and legacy assignments.
- Signed mobile and desktop artifact smoke remains release evidence; static CI
  guards are tripwires, not a substitute for artifact verification.
- `backend/scripts/probe_beta_uid_continuity.py` — the non-human production
  Firebase probe creates a bounded sentinel through production, reads that
  exact record through Beta's fixed development Python endpoint, then deletes
  it through production before qualification can promote Beta.

## Path globs

- `codemagic.yaml`
- `app/lib/env/env.dart`
- `app/lib/main.dart`
- `app/lib/startup_routing.dart`
- `app/lib/utils/environment_detector.dart`
- `app/lib/firebase_options*.dart`
- `app/android/**/google-services.json`
- `app/ios/**/GoogleService-Info.plist`
- `desktop/macos/Desktop/Sources/AppBuild.swift`
- `desktop/macos/Desktop/Sources/DesktopBackendEnvironment.swift`
- `desktop/macos/Desktop/Sources/GoogleService-Info*.plist`
- `backend/charts/desktop-backend/**` (retired: this chart may not return)
- `.github/workflows/gcp_*.yml` (retired: no GKE desktop-backend deployment authority may return)
- `.github/workflows/desktop_backend_*.yml`
- `.github/scripts/check-mobile-production-routing.py`
- `.github/scripts/test_check_mobile_production_routing.py`
- `docs/runbooks/desktop-backend-cloud-run-ownership.md`

## PR rule

Name `INV-DATA-1` in every PR that changes a path above. State whether the
change preserves the existing authority or is the explicit migration exception.
