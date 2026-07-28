import Foundation

extension APIClient {
  /// Controls retry and session invalidation at the authentication boundary.
  /// Owner-bound requests also reject responses that arrive after an account
  /// switch, even when the original credential was otherwise valid.
  struct RequestAuthPolicy: Sendable {
    var signOutOn401: Bool
    var recordsAuthRetryTelemetry: Bool = true

    /// When true, a post-refresh HTTP 401 is returned to the caller instead of
    /// throwing `.unauthorized`, so provider-shaped bodies can be inspected.
    var returnsPersistent401Response: Bool = false
    var expectedAuthOwnerId: String? = nil
    var authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil

    static let `default` = RequestAuthPolicy(signOutOn401: true)
    static let sessionPreserving = RequestAuthPolicy(signOutOn401: false)
    static let providerCredentialBoundary = RequestAuthPolicy(
      signOutOn401: false,
      recordsAuthRetryTelemetry: false,
      returnsPersistent401Response: true
    )

    static func ownerBound(_ ownerId: String) -> RequestAuthPolicy {
      RequestAuthPolicy(
        signOutOn401: false,
        recordsAuthRetryTelemetry: true,
        returnsPersistent401Response: false,
        expectedAuthOwnerId: ownerId
      )
    }

    static func ownerBound(_ snapshot: RuntimeOwnerAuthorizationSnapshot) -> RequestAuthPolicy {
      RequestAuthPolicy(
        signOutOn401: false,
        recordsAuthRetryTelemetry: true,
        returnsPersistent401Response: false,
        expectedAuthOwnerId: snapshot.ownerID,
        authorizationSnapshot: snapshot
      )
    }
  }

  /// Resolves the single owner authority for a request before any token lookup
  /// or network I/O. Supplying both forms is allowed only when they identify
  /// the same owner; a caller must never be able to pair owner A's precondition
  /// with owner B's immutable authorization snapshot.
  func resolvedRequestAuthPolicy(
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    fallback: RequestAuthPolicy = .default
  ) throws -> RequestAuthPolicy {
    if let authorizationSnapshot {
      if let expectedOwnerId {
        let normalizedExpectedOwnerId =
          expectedOwnerId
          .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedExpectedOwnerId.isEmpty,
          normalizedExpectedOwnerId == authorizationSnapshot.ownerID
        else {
          throw AuthError.userChangedDuringRequest
        }
      }
      return .ownerBound(authorizationSnapshot)
    }
    if let expectedOwnerId { return .ownerBound(expectedOwnerId) }
    return fallback
  }
}
