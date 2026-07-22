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
  // MARK: - Auth Persistence (UserDefaults for dev builds)

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
