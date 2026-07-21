# INV-DATA-1: Production-family customer data-plane continuity

**Status:** locked

**Statement:** A production-family Omi artifact has exactly one customer data
plane. Stable, internal, alpha, beta, TestFlight, Play Internal, and the
separately installable macOS **Omi Beta** app all use the canonical production
API, agent endpoint, desktop API, Firebase/Firestore identity, and account
universe. A user who installs an earlier build must see the same account,
recordings, conversations, integrations, and sync state as on stable.

A release channel controls *eligibility, rollout exposure, diagnostics, and
feature availability*. It MUST NOT select a different account or customer-data
universe. TestFlight detection, an Android dart define, an update-channel
preference, a launch environment, or a bundled environment file is not
authority to redirect a production-family package.

The canonical current production routing is:

| Surface | Production-family authority |
| --- | --- |
| Flutter API | `https://api.omi.me/` |
| Flutter agent WebSocket | `wss://agent.omi.me/v1/agent/ws` |
| macOS Python API | `https://api.omi.me/` |
| macOS desktop API | `https://desktop-backend-hhibjajaja-uc.a.run.app/` |
| macOS beta identity | `com.omi.computer-macos.beta`, in `AppBuild.productionFamilyBundleIdentifiers` |
| macOS Firebase/Firestore config | the shipped production customer project (`based-hardware`) |

## MUST NOT

- Route a production-family artifact to staging, development, a beta API, or
  any arbitrary endpoint through a build define, CI variable, runtime
  preference, update channel, process environment, or bundled `.env` value.
- Treat `OMI_BETA_RELEASE_RING`, `STAGING_API_URL`, `api-beta.omi.me`, or an
  equivalent beta/staging selector as a production-family routing mechanism.
- Treat the macOS beta bundle identity as a development identity. Its separate
  local storage and update channel do not create separate customer data.
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
new immutable authority before it can ship. A separate development/test app
identity and test credentials may use non-production services; it must not
reuse a production-family identity.

## Guard tests

- `app/test/unit/env_test.dart` — production startup rejects non-canonical API
  and agent routing.
- `desktop/macos/Desktop/Tests/APIClientRoutingTests.swift` — stable and Omi
  Beta resolve only canonical production endpoints despite contaminated process
  values.
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
- `desktop/macos/Backend-Rust/charts/desktop-backend/*values.yaml`
- `.github/scripts/check-mobile-production-routing.py`
- `.github/scripts/test_check_mobile_production_routing.py`

## PR rule

Name `INV-DATA-1` in every PR that changes a path above. State whether the
change preserves the existing authority or is the explicit migration exception.
