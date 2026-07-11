# INV-AUTH-1: Desktop Firebase session truth

**Status:** locked
**Statement:** Desktop macOS treats `AuthSessionCoordinator` as the single owner
of Firebase session death. Definitive credential loss must invalidate the light
session (tokens + signed-in UI) without nuclear sign-out teardown.

Persisted auth booleans and Firebase `currentUser` are restore hints only. The
runtime may expose authenticated surfaces only after a credential validates for
the current launch.

## MUST NOT

- Preserve `isSignedIn=true` when refresh and post-refresh HTTP 401 prove the
  Firebase session is dead (ghost sessions).
- Map bridge/API auth failures to dead-end `"AI not available: Please sign in…"`
  banners when `ChatErrorState.authRequired` applies.
- Use `AuthBackoffTracker` or ad-hoc polling backoff instead of session
  invalidation for session-scoped HTTP 401s.
- Invalidate the Firebase session for BYOK/provider credential 401s or voice-only
  credential failures (`CredentialHealthManager` scope).
- Treat `auth_isSignedIn=true` or cached Firebase identity as sufficient proof
  that the runtime is authenticated.
- Delete a legacy credential until the replacement Keychain payload has been
  written, read back exactly, and committed by a successful forced refresh.
- Publish a beta artifact without running its signed-app Keychain canary.

## Surfaces

- `AuthSessionCoordinator`, `AuthService` restore/refresh/listener paths
- `AuthState` phase and `SessionRecoveryView` authenticated-surface gate
- `DesktopKeychainStore` and legacy credential migration
- `APIClient` session-scoped 401 handling
- `ChatProvider` bridge-start and send-time auth UX
- Codemagic signed-artifact smoke before beta publication

## Guard tests

- `desktop/macos/Desktop/Tests/AuthSessionCoordinatorTests.swift`
- `desktop/macos/Desktop/Tests/APIClientAuthRecoveryTests.swift`
- `desktop/macos/Desktop/Tests/ChatErrorStateTests.swift`
- `desktop/macos/Desktop/Tests/AuthTokenStorageTests.swift`
- `desktop/macos/Desktop/Tests/AuthStorageCanaryTests.swift`
- `desktop/macos/tests/test-signed-artifact-smoke.sh`
- `.github/scripts/check_desktop_auth_session.py` — ratchet on 401 handlers and
  authenticated `session.data` bypasses of the shared refresh/invalidate path

## Path globs

- `desktop/macos/Desktop/Sources/AuthService.swift`
- `desktop/macos/Desktop/Sources/AuthSessionCoordinator.swift`
- `desktop/macos/Desktop/Sources/Auth/*.swift`
- `desktop/macos/Desktop/Sources/DesktopKeychainStore.swift`
- `desktop/macos/Desktop/Sources/OmiApp.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/scripts/smoke-signed-desktop-artifact.sh`
- `codemagic.yaml`

## PR rule

Name `INV-AUTH-1` when changing session invalidation policy, 401 handling, or
chat auth recovery UX on the globs above.
