import Foundation

struct DesktopAutomationNavigationRequest: Codable {
  let target: String
  let settingsSection: String?
  let highlightedSettingId: String?
  let activateApp: Bool?
  let settleMs: Int?
  /// When true (the compatibility default), `/navigate` waits until the
  /// destination's mounted view reports visibility. Non-production
  /// responsiveness probes can set false to measure command acknowledgement
  /// separately from potentially expensive destination loading.
  let waitForVisibility: Bool?
}

/// The single handoff from the HTTP bridge into the mounted SwiftUI shell. Keeping activation in the
/// same value as the route prevents a cursor-free request from silently defaulting back to foreground
/// activation when it crosses NotificationCenter.
enum DesktopAutomationNavigationDelivery {
  static func resolvesActivation(explicit: Bool?) -> Bool {
    explicit ?? false
  }

  static func userInfo(
    for payload: DesktopAutomationNavigationRequest,
    activateApp: Bool
  ) -> [String: Any] {
    [
      "target": payload.target,
      "settingsSection": payload.settingsSection as Any,
      "highlightedSettingId": payload.highlightedSettingId as Any,
      "activateApp": activateApp,
    ]
  }
}

/// Selects whether `/navigate` measures command acknowledgement or waits for
/// the destination view to mount. The default remains the historical mounted
/// visibility contract; responsiveness probes explicitly opt into the faster
/// acknowledgement phase and then wait on state independently.
enum DesktopAutomationNavigationResponseMode: Equatable {
  case routeAcknowledged
  case mountedVisible

  static func resolve(waitForVisibility: Bool?) -> Self {
    waitForVisibility == false ? .routeAcknowledged : .mountedVisible
  }

  static func snapshot<T: Sendable>(
    waitForVisibility: Bool?,
    cached: @Sendable () async throws -> T,
    mounted: @Sendable () async throws -> T
  ) async throws -> T {
    switch resolve(waitForVisibility: waitForVisibility) {
    case .routeAcknowledged:
      return try await cached()
    case .mountedVisible:
      return try await mounted()
    }
  }
}

/// Cohort-shell visibility proof for the non-production automation bridge.
/// The bridge reports success only after the target route has actually mounted.
extension DesktopAutomationBridge {
  /// `dispatchNavigation` posts on MainActor, and the root navigation reducer
  /// projects its typed route before returning. Keep this acknowledgement
  /// distinct from mounted-view visibility so probes do not treat a heavy
  /// destination finishing its load as first input feedback.
  func navigationSnapshot(
    for payload: DesktopAutomationNavigationRequest
  ) async throws -> DesktopAutomationSnapshot {
    try await DesktopAutomationNavigationResponseMode.snapshot(
      waitForVisibility: payload.waitForVisibility,
      cached: {
        // The fast acknowledgement path must not report success for a target
        // the shell cannot route: callers can otherwise treat a no-op as an
        // accepted navigation. Reject unknown targets before returning cached.
        try self.validateKnownNavigationTarget(payload)
        return await cachedAutomationSnapshot()
      },
      mounted: { try await waitForNavigationTarget(payload) }
    )
  }

  /// Confirms the target resolves to a known destination so the acknowledgement
  /// path cannot mask an unknown route as success.
  private func validateKnownNavigationTarget(
    _ payload: DesktopAutomationNavigationRequest
  ) throws {
    guard ChatFirstRoute.automationVisibilityDestination(named: payload.target) != nil else {
      throw DesktopAutomationActionError.invalidParams("unknown_navigation_target")
    }
  }

  func waitForNavigationTarget(
    _ payload: DesktopAutomationNavigationRequest
  ) async throws -> DesktopAutomationSnapshot {
    let expectedChatFirstRoute = ChatFirstRoute.automationVisibilityDestination(named: payload.target)?.stableName
    let deadline = Date().addingTimeInterval(5)

    while Date() < deadline {
      let snapshot = await liveAutomationSnapshot()
      if !snapshot.snapshotStale,
        DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
          shellVariant: snapshot.shellVariant,
          visibleChatFirstRoute: snapshot.visibleChatFirstRoute,
          expectedChatFirstRoute: expectedChatFirstRoute
        )
      {
        return snapshot
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw DesktopAutomationActionError.invalidParams("navigation_target_not_visible")
  }

}

/// Visibility comparison retained separately from the HTTP bridge so it has no
/// access to shell state beyond the sampled snapshot.
enum DesktopAutomationNavigationVisibilityPolicy {
  static func isTargetVisible(
    shellVariant: String?,
    visibleChatFirstRoute: String?,
    expectedChatFirstRoute: String?
  ) -> Bool {
    guard shellVariant == DesktopAutomationSnapshot.singleShellVariant else { return false }
    return expectedChatFirstRoute != nil && visibleChatFirstRoute == expectedChatFirstRoute
  }
}
