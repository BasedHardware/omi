# INV-DATA-1: Production-family customer data-plane continuity

**Status:** locked

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

A release channel controls *eligibility, rollout exposure, diagnostics, and
feature availability*. It MUST NOT select a different account or customer-data
universe. TestFlight detection, an Android dart define, an update-channel
preference, a launch environment, or a bundled environment file is not
authority to redirect a production-family package.

The routing authority matrix is:

| Surface | Production-family authority |
| --- | --- |
| Flutter API | `https://api.omi.me/` |
| Flutter agent WebSocket | `wss://agent.omi.me/v1/agent/ws` |
| macOS Stable Python / desktop API | `https://api.omi.me/` / `https://desktop-backend-hhibjajaja-uc.a.run.app/` |
| macOS Beta Python / desktop API | `https://api.omiapi.com/` / `https://desktop-backend-dt5lrfkkoa-uc.a.run.app/` |
| macOS Beta OAuth API | `https://api.omi.me/` |
| macOS production identities | Stable: `com.omi.computer-macos`; Beta: `com.omi.computer-macos.beta` |
| macOS Firebase/Firestore config | the shipped production customer project (`based-hardware`) |

## MUST NOT

- Route Stable, mobile, or any other production-family artifact to development,
  staging, a beta API, or any arbitrary endpoint through a build define, CI
  variable, runtime preference, update channel, process environment, or bundled
  `.env` value. Beta's two fixed development serving authorities are the sole exception.
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
  and agent routing.
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
- `backend/charts/**` (retired: no GKE desktop-backend chart may return)
- `.github/workflows/**` (retired: no GKE desktop-backend deployment authority may return)
- `.github/scripts/check-mobile-production-routing.py`
- `.github/scripts/test_check_mobile_production_routing.py`
- `docs/runbooks/desktop-backend-cloud-run-ownership.md`

## PR rule

Name `INV-DATA-1` in every PR that changes a path above. State whether the
change preserves the existing authority or is the explicit migration exception.
