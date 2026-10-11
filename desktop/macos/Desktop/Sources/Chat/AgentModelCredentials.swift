import Foundation

/// The only credential-bearing agent IPC is a response to one admitted model
/// request. No credential is retained by the runtime or placed in its environment.
struct AgentModelCredentials: Sendable {
  let headers: [String: String]?
  let failureCode: String?

  @MainActor
  static func resolve(ownerID: String, forceRefresh: Bool) async -> Self {
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      authorization.ownerID == ownerID
    else { return Self(headers: nil, failureCode: "authentication") }
    return await resolve(
      isCurrent: { RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) },
      fetch: {
        let header: String
        if let faultToken = AgentRuntimeCredentialPolicy.hermeticFaultModelToken(
          isNonProduction: AppBuild.isNonProduction, bundleIdentifier: AppBuild.bundleIdentifier)
        {
          header = "Bearer \(faultToken)"
        } else {
          header = try await AuthService.shared.getAuthHeader(forceRefresh: forceRefresh, expectedUserId: ownerID)
        }
        var headers = ["Authorization": header]
        let byok = AgentRuntimeProcess.usableBYOKEnvironment()
        for (key, value) in byok.values {
          headers["X-BYOK-" + key.replacingOccurrences(of: "OMI_BYOK_", with: "")] = value
        }
        return headers
      })
  }

  /// Re-check the session generation after suspension, including same-owner
  /// sign-out/sign-in. Failed refreshes leave no cache or disabled refresher.
  @MainActor
  static func resolve(
    isCurrent: () -> Bool,
    fetch: () async throws -> [String: String]
  ) async -> Self {
    guard isCurrent() else { return Self(headers: nil, failureCode: "authentication") }
    do {
      let headers = try await fetch()
      guard isCurrent() else { return Self(headers: nil, failureCode: "authentication") }
      return Self(headers: headers, failureCode: nil)
    } catch {
      let authFailure: Bool
      switch error {
      case AuthError.notSignedIn, AuthError.invalidCredential, AuthError.userChangedDuringRequest:
        authFailure = true
      default:
        authFailure = false
      }
      return Self(headers: nil, failureCode: authFailure ? "authentication" : "transport_interruption")
    }
  }
}
