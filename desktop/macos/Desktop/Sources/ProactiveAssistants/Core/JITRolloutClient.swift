import Foundation

/// Shared backend rollout authority for canonical memory and knowledge tools.
actor JITRolloutClient {
  static let shared = JITRolloutClient()
  static var backendBaseURL: String { DesktopBackendEnvironment.rustBackendURL() }
  private let session: URLSession
  private let baseURL: () -> String
  private let jitAuthorization: @Sendable (_ ownerID: String) async throws -> String
  private let now: @Sendable () -> Date
  private var jitFlagsCache: (ownerID: String, flags: JITProactivityFlags, expiresAt: Date)?

  init(
    session: URLSession = .shared,
    baseURL: @escaping () -> String = { JITRolloutClient.backendBaseURL },
    now: @escaping @Sendable () -> Date = { Date() },
    jitAuthorization: (@Sendable (_ ownerID: String) async throws -> String)? = nil
  ) {
    self.session = session
    self.baseURL = baseURL
    self.now = now
    self.jitAuthorization =
      jitAuthorization ?? { ownerID in
        let authService = await MainActor.run { AuthService.shared }
        return try await authService.getAuthHeader(expectedUserId: ownerID)
      }
  }

  /// Read the authenticated backend rollout authority. Any transport or
  /// decoding failure is represented as unknown; clients never self-enrol.
  func jitProactivityFlags(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> JITProactivityFlags {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      return JITProactivityFlags(rollout: .unknown, killSwitch: .unknown)
    }
    if let cached = jitFlagsCache,
      cached.ownerID == authorizationSnapshot.ownerID,
      cached.expiresAt > now()
    {
      return cached.flags
    }
    if jitFlagsCache?.ownerID != authorizationSnapshot.ownerID {
      jitFlagsCache = nil
    }
    let root = baseURL().hasSuffix("/") ? baseURL() : baseURL() + "/"
    guard let url = URL(string: root + "v1/jit/rollout-decision") else {
      return JITProactivityFlags(rollout: .unknown, killSwitch: .unknown)
    }
    do {
      let header = try await jitAuthorization(authorizationSnapshot.ownerID)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        return JITProactivityFlags(rollout: .unknown, killSwitch: .unknown)
      }
      var request = URLRequest(url: url)
      request.httpMethod = "GET"
      request.setValue(header, forHTTPHeaderField: "Authorization")
      request.timeoutInterval = 10
      let (data, response) = try await session.data(for: request)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode),
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
      else {
        return cacheUnknownJITFlags(ownerID: authorizationSnapshot.ownerID)
      }
      // The server-computed `effective` verdict owns admission; the raw
      // rollout + kill-switch pair stays as the older-server fallback. An
      // absent `kill_switch` is compatibility, not an unknown-off veto.
      let flags = JITProactivityFlags(
        rollout: Self.jitState(object["rollout"]),
        killSwitch: Self.jitState(object["kill_switch"]),
        effective: Self.jitState(object["effective"]),
        killSwitchPresent: object["kill_switch"] != nil,
        budgetContractVersion: object["budget_contract_version"] as? String)
      let rawTTL = object["cache_ttl_seconds"] as? Int ?? 60
      let ttl = min(max(rawTTL, 15), 15 * 60)
      jitFlagsCache = (
        authorizationSnapshot.ownerID, flags, now().addingTimeInterval(TimeInterval(ttl))
      )
      return flags
    } catch {
      return cacheUnknownJITFlags(ownerID: authorizationSnapshot.ownerID)
    }
  }

  private func cacheUnknownJITFlags(ownerID: String) -> JITProactivityFlags {
    let flags = JITProactivityFlags(rollout: .unknown, killSwitch: .unknown)
    jitFlagsCache = (ownerID, flags, now().addingTimeInterval(15))
    return flags
  }

  static func jitState(_ value: Any?) -> JITProactivityRolloutState {
    // Wire contract: backend TriState serializes exactly `enabled`/`disabled`/
    // `unknown`. Anything else — including retired spellings — fails closed.
    switch (value as? String)?.lowercased() {
    case "enabled": return .enabled
    case "disabled": return .disabled
    default: return .unknown
    }
  }

}
