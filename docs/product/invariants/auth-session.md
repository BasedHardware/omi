# INV-AUTH-1: Desktop Firebase session truth

**Status:** locked
**Statement:** Desktop macOS treats `AuthSessionCoordinator` as the single owner
of Firebase session death. Definitive credential loss must invalidate the light
session (tokens + signed-in UI) without nuclear sign-out teardown.

Persisted auth booleans and Firebase `currentUser` are restore hints only. The
runtime may expose authenticated surfaces only after a credential validates for
the current launch.

The effective runtime owner (Firebase uid or non-production automation override)
changes through one exclusive async transition. Owner-bound local mutation
leases remain held through physical SQLite commit/rollback; the transition
closes the prior `RewindDatabase` pool, configures the next owner's lazy-open
target, and purges every cached pool/directory/encoder before it publishes one
content-free MainActor invalidation or admits new-owner work. A suspended
initializer may not publish a pool after its owner/generation is stale.

Owner replacement is also a hard voice boundary. Before persisted defaults
mutate, the transition exposes no authorized owner, terminalizes the canonical
`VoiceTurnCoordinator` turn, stops microphone/STT/playback drivers, drains every
detached realtime transport queue, and purges warm-session context. That
authorization revocation remains active through the synchronous MainActor
invalidation; the replacement owner becomes visible only after old projections
have cleared and immediately before parked mutation leases are admitted.

The same boundary owns the local agent runtime. It waits for Node's correlated
previous-owner revocation receipt, drains all Swift physical-tool tasks to
completion, and confirms the old child process has exited before defaults can
expose the next account. Every delayed owner-bound continuation uses an
immutable authorization generation, so an A→signed-out→A sequence still revokes
the original A session even though the uid string matches again.

Every async restore, sign-in, refresh, listener validation, invalidation, and
sign-out completion carries a monotonic `AuthSessionAttempt`. Token writes and
deletes, persisted owner/session changes, and auth-phase publication revalidate
that attempt at their commit boundary. Starting a newer attempt immediately
revokes older completions and their refresh single-flight; stale work is a no-op
and cannot clear newer credentials, resurrect an old session, or change the
newer's phase. A replacement sign-in publishes its credentials and durable owner
defaults in one fenced synchronous commit after the previous owner's authority
is revoked; a B token is never visible to an A-authorized token reader. Sign-out
clears its generation-owned credentials before awaiting the owner/storage
transition, leaving no post-await token deletion that can race a newer sign-in.

Owner-bound background sync follows the same rule: every AgentSync start/stop
advances a generation, cursors are keyed by effective owner, and delayed token,
HTTP, database, or re-upload continuations must match the exact generation
before changing cursors, failure/backoff state, or the active VM session.

User-bound UI workflows capture one nonempty owner at their production entry
point and carry it through every await, API/cache mutation, rollback, and
presentation. A missing owner grants no authority. Notification cards and pill
terminal journal writes carry immutable provenance, so a late owner-A result is
rejected before any owner-B lookup, render, or journal mutation.

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
- Change `auth_userId` or the effective automation owner outside
  `RuntimeOwnerIdentity.performEffectiveOwnerTransition`.
- Configure, close, reopen, or cache a production per-owner SQLite pool outside
  the effective-owner boundary; lazy initialization must use the target sealed
  by that transition and epoch-check any cached pool.
- Publish tokens, owner defaults, user profile fields, or `AuthState` from an
  async auth completion whose `AuthSessionAttempt` is no longer current.
- Let a stopped/replaced AgentSync generation update the next owner's VM,
  cursors, token-refresh timestamp, or retry/backoff state.
- Treat matching uid strings as sufficient authority for delayed agent, tool,
  quota, profile, or API work; the original authorization generation must still
  be current at the physical commit and response-publication boundaries.
- Treat a preflight owner check or a check inside a GRDB updates closure as
  commit authority; the lease must cover GRDB's subsequent physical commit.

## Surfaces

- `AuthSessionCoordinator`, `AuthService` restore/refresh/listener paths
- `AuthState` phase and `SessionRecoveryView` authenticated-surface gate
- `DesktopKeychainStore` and legacy credential migration
- `APIClient` session-scoped 401 handling
- `ChatProvider` bridge-start and send-time auth UX
- `EffectiveOwnerTransitionFence`, owner-bound local storage effects, and
  owner-derived floating/journal projections
- `VoiceTurnCoordinator`, `PushToTalkManager`, and `RealtimeHubController`
  physical teardown at the effective-owner boundary
- `RewindDatabase`, `RewindIndexer`, `RewindStorage`, and per-owner storage/cache
  actors retargeted synchronously by `RuntimeOwnerIdentity`
- Codemagic signed-artifact smoke before beta publication

## Guard tests

- `desktop/macos/Desktop/Tests/AuthSessionCoordinatorTests.swift`
- `desktop/macos/Desktop/Tests/APIClientAuthRecoveryTests.swift`
- `desktop/macos/Desktop/Tests/ChatErrorStateTests.swift`
- `desktop/macos/Desktop/Tests/AuthTokenStorageTests.swift`
- `desktop/macos/Desktop/Tests/AuthStorageCanaryTests.swift`
- `desktop/macos/Desktop/Tests/ChatToolExecutorSQLTests.swift`
- `desktop/macos/Desktop/Tests/LocalMutationAuthorizationTests.swift`
- `desktop/macos/Desktop/Tests/TasksStoreOwnerBoundaryTests.swift`
- `desktop/macos/Desktop/Tests/FloatingOwnerProjectionTests.swift`
- `desktop/macos/Desktop/Tests/AuthSessionAttemptFenceTests.swift`
- `desktop/macos/Desktop/Tests/EffectiveOwnerDatabaseBoundaryTests.swift`
- `desktop/macos/Desktop/Tests/RuntimeOwnerIdentityTests.swift`
- `desktop/macos/Desktop/Tests/PushToTalkStateMachineTests.swift`
- `desktop/macos/Desktop/Tests/RewindDatabaseLifecycleTests.swift`
- `desktop/macos/Desktop/Tests/AgentSyncBatchQueryTests.swift`
- `desktop/macos/tests/test-signed-artifact-smoke.sh`
- `.github/scripts/check_desktop_auth_session.py` — ratchet on 401 handlers

## Path globs

- `desktop/macos/Desktop/Sources/AuthService.swift`
- `desktop/macos/Desktop/Sources/AuthSessionCoordinator.swift`
- `desktop/macos/Desktop/Sources/Auth/*.swift`
- `desktop/macos/Desktop/Sources/DesktopKeychainStore.swift`
- `desktop/macos/Desktop/Sources/OmiApp.swift`
- `desktop/macos/Desktop/Sources/Chat/RuntimeOwnerIdentity.swift`
- `desktop/macos/Desktop/Sources/Services/LocalMutationAuthorization.swift`
- `desktop/macos/Desktop/Sources/Rewind/Core/RewindDatabase.swift`
- `desktop/macos/Desktop/Sources/FileIndexing/FileIndexerService.swift`
- `desktop/macos/Desktop/Sources/AgentSyncService.swift`
- `desktop/macos/Desktop/Sources/APIClient.swift`
- `desktop/macos/Desktop/Sources/Providers/ChatProvider.swift`
- `desktop/macos/scripts/smoke-signed-desktop-artifact.sh`
- `codemagic.yaml`

## PR rule

Name `INV-AUTH-1` when changing session invalidation policy, 401 handling, or
chat auth recovery UX on the globs above.
