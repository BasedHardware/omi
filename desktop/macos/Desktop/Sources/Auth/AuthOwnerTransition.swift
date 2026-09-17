import Foundation

/// Auth state publication fails closed when owner-bound physical storage could
/// not be released before the defaults/token generation changes.
@MainActor
func performAuthOwnerTransition<T: Sendable>(
  context: String,
  plannedNextOwner: @escaping @Sendable (UserDefaults, String?) -> String?,
  _ transition: @escaping @Sendable (UserDefaults) async throws -> T
) async -> T? {
  do {
    return try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: plannedNextOwner,
      transition)
  } catch {
    logError("AUTH: Could not prepare local storage for \(context) owner transition", error: error)
    return nil
  }
}

extension AuthService {
  /// Owner uid preserved after light invalidation: signed-out boolean cleared but
  /// `auth_userId` remains until the user completes re-authentication.
  func preservedReauthOwnerId(from defaults: UserDefaults = .standard) -> String? {
    guard !defaults.bool(forKey: .authIsSignedIn) else { return nil }
    let trimmed =
      defaults.string(forKey: .authUserId)?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }

  func restorePreservedReauthOwner(email: String?) {
    NSLog("OMI AUTH: Restoring preserved re-auth owner")
    AuthState.shared.userEmail = email
    AuthState.shared.transition(to: .needsReauth)
  }

  @MainActor
  func handleFirebaseNilUserWithoutSavedSignedIn() {
    if preservedReauthOwnerId() != nil {
      log("AUTH_LISTENER: Firebase user nil — preserving needsReauth")
      if AuthState.shared.sessionPhase != .needsReauth { AuthState.shared.transition(to: .needsReauth) }
      return
    }
    log("AUTH_LISTENER: No saved session - setting isSignedIn=false")
    AuthState.shared.transition(to: .signedOut)
    AuthState.shared.userEmail = nil
  }

  // MARK: - Auth Persistence (UserDefaults for dev builds)

  /// Revoke the remote session and publish the signed-out credential generation
  /// only after owner-bound storage is safely prepared. A preparation failure
  /// therefore leaves the previous session intact instead of exposing a signed-
  /// out UI with the previous owner's local authority still active.
  @discardableResult
  func commitSignedOutSession(
    attempt: AuthSessionAttempt,
    phase: AuthSessionPhase,
    beforeClearingCredentials: @escaping @MainActor @Sendable () throws -> Void = {},
    prepareLocalStorageTransition:
      @escaping @Sendable (_ previousOwner: String?, _ plannedNextOwner: String?) async throws -> Void = { _, _ in
        RewindIndexer.shared.suspendForOwnerTransition()
        try await RewindStorage.shared.resetForOwnerTransition()
      }
  ) async throws -> Bool {
    let attemptFence = sessionAttemptFence
    let committed = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, previousOwner in
        attemptFence.isCurrent(attempt) ? nil : previousOwner
      },
      prepareLocalStorageTransition: prepareLocalStorageTransition,
      { _ in
        try await MainActor.run {
          try attemptFence.commitIfCurrent(attempt) {
            try beforeClearingCredentials()
            self.clearTokens()
            AuthState.shared.userEmail = nil
            AuthState.shared.transition(to: phase)
            let defaults = UserDefaults.standard
            defaults.set(false, forKey: .authIsSignedIn)
            defaults.removeObject(forKey: .authUserEmail)
            defaults.removeObject(forKey: .authUserId)
            defaults.synchronize()
            return true
          } ?? false
        }
      })
    return committed && sessionAttemptFence.isCurrent(attempt)
  }

  /// Light invalidation: revoke credentials and signed-in UI without changing
  /// the effective runtime owner or tearing down owner-bound storage. Preserves
  /// `auth_userId` so Claude Code / chat sessions can rehydrate after re-auth.
  @discardableResult
  func commitLightInvalidatedSession(
    attempt: AuthSessionAttempt,
    beforeClearingCredentials: @escaping @MainActor @Sendable () throws -> Void = {}
  ) async throws -> Bool {
    let attemptFence = sessionAttemptFence
    let committed = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, previousOwner in
        attemptFence.isCurrent(attempt) ? previousOwner : previousOwner
      },
      prepareLocalStorageTransition: { _, _ in },
      { _ in
        try await MainActor.run {
          try attemptFence.commitIfCurrent(attempt) {
            let defaults = UserDefaults.standard
            let preservedEmail = defaults.string(forKey: .authUserEmail)
            try beforeClearingCredentials()
            self.clearTokens()
            AuthState.shared.userEmail = preservedEmail
            AuthState.shared.transition(to: .needsReauth)
            defaults.set(false, forKey: .authIsSignedIn)
            defaults.synchronize()
            return true
          } ?? false
        }
      })
    return committed && sessionAttemptFence.isCurrent(attempt)
  }

  @discardableResult
  func saveAuthState(
    isSignedIn: Bool,
    email: String?,
    userId: String?,
    attempt: AuthSessionAttempt
  ) async -> Bool {
    let attemptFence = sessionAttemptFence
    guard
      let committed = await performAuthOwnerTransition(
        context: "auth-state",
        plannedNextOwner: { _, previousOwner in
          attemptFence.isCurrent(attempt) ? userId : previousOwner
        },
        { defaults in
          attemptFence.commitIfCurrent(attempt) {
            defaults.set(isSignedIn, forKey: .authIsSignedIn)
            defaults.set(email, forKey: .authUserEmail)
            defaults.set(userId, forKey: .authUserId)
            defaults.synchronize()
            return true
          } ?? false
        })
    else { return false }
    guard committed, sessionAttemptFence.isCurrent(attempt) else { return false }
    NSLog("OMI AUTH: Saved auth state - signedIn: %@, email: %@", isSignedIn ? "true" : "false", email ?? "nil")
    return true
  }

  @discardableResult
  func clearPersistedAuthState(attempt: AuthSessionAttempt) async -> Bool {
    let attemptFence = sessionAttemptFence
    guard
      let committed = await performAuthOwnerTransition(
        context: "sign-out",
        plannedNextOwner: { _, previousOwner in
          attemptFence.isCurrent(attempt) ? nil : previousOwner
        },
        { defaults in
          attemptFence.commitIfCurrent(attempt) {
            defaults.removeObject(forKey: .authIsSignedIn)
            defaults.removeObject(forKey: .authUserEmail)
            defaults.removeObject(forKey: .authUserId)
            defaults.removeObject(forKey: .authIdToken)
            defaults.removeObject(forKey: .authRefreshToken)
            defaults.removeObject(forKey: .authTokenExpiry)
            defaults.removeObject(forKey: .authTokenUserId)
            return true
          } ?? false
        })
    else { return false }
    return committed && sessionAttemptFence.isCurrent(attempt)
  }

  /// The only production path for changing the persisted authenticated uid
  /// outside the larger save/clear auth-state transactions above.
  @discardableResult
  func persistAuthenticatedOwner(
    _ userId: String?,
    attempt: AuthSessionAttempt
  ) async -> Bool {
    let attemptFence = sessionAttemptFence
    guard
      let committed = await performAuthOwnerTransition(
        context: "authenticated-owner",
        plannedNextOwner: { _, previousOwner in
          attemptFence.isCurrent(attempt) ? userId : previousOwner
        },
        { defaults in
          attemptFence.commitIfCurrent(attempt) {
            if let userId {
              defaults.set(userId, forKey: .authUserId)
            } else {
              defaults.removeObject(forKey: .authUserId)
            }
            return true
          } ?? false
        })
    else { return false }
    return committed && sessionAttemptFence.isCurrent(attempt)
  }
}
