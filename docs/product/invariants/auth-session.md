# INV-AUTH-1: Desktop Firebase session truth

**Status:** locked
**Statement:** Desktop macOS treats `AuthSessionCoordinator` as the single owner
of Firebase session death. Definitive credential loss must invalidate the light
session (tokens + signed-in UI) without nuclear sign-out teardown.

## MUST NOT

- Preserve `isSignedIn=true` when refresh and post-refresh HTTP 401 prove the
  Firebase session is dead (ghost sessions).
- Map bridge/API auth failures to dead-end `"AI not available: Please sign in…"`
  banners when `ChatErrorState.authRequired` applies.
- Use `AuthBackoffTracker` or ad-hoc polling backoff instead of session
  invalidation for session-scoped HTTP 401s.
- Invalidate the Firebase session for BYOK/provider credential 401s or voice-only
  credential failures (`CredentialHealthManager` scope).

## Surfaces

- `AuthSessionCoordinator`, `AuthService` restore/refresh/listener paths
- `APIClient` session-scoped 401 handling
- `ChatProvider` bridge-start and send-time auth UX

## Guard tests

- `desktop/macos/Desktop/Tests/AuthSessionCoordinatorTests.swift`
- `desktop/macos/Desktop/Tests/APIClientAuthRecoveryTests.swift`
- `desktop/macos/Desktop/Tests/ChatErrorStateTests.swift`
- `.github/scripts/check_desktop_auth_session.py` — ratchet on 401 handlers

## Path globs

- `desktop/macos/Desktop/Sources/AuthService.swift`
- `desktop/macos/Desktop/Sources/AuthSessionCoordinator.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`

## PR rule

Name `INV-AUTH-1` when changing session invalidation policy, 401 handling, or
chat auth recovery UX on the globs above.
