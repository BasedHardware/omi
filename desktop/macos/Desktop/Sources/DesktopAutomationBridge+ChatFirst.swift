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
    cached: @Sendable () async -> T,
    mounted: @Sendable () async throws -> T
  ) async throws -> T {
    switch resolve(waitForVisibility: waitForVisibility) {
    case .routeAcknowledged:
      return await cached()
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
      cached: { await cachedAutomationSnapshot() },
      mounted: { try await waitForNavigationTarget(payload) }
    )
  }

  func waitForNavigationTarget(
    _ payload: DesktopAutomationNavigationRequest
  ) async throws -> DesktopAutomationSnapshot {
    let expectedChatFirstRoute = ChatFirstRoute.automationVisibilityDestination(named: payload.target)?.stableName
    let expectedLegacyTitle = legacyAutomationDestinationTitle(named: payload.target)
    let deadline = Date().addingTimeInterval(5)

    while Date() < deadline {
      let snapshot = await liveAutomationSnapshot()
      if !snapshot.snapshotStale,
        DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
          shellVariant: snapshot.shellVariant,
          selectedTab: snapshot.selectedTab,
          visibleChatFirstRoute: snapshot.visibleChatFirstRoute,
          expectedChatFirstRoute: expectedChatFirstRoute,
          expectedLegacyTitle: expectedLegacyTitle
        )
      {
        return snapshot
      }
      try await Task.sleep(nanoseconds: 50_000_000)
    }
    throw DesktopAutomationActionError.invalidParams("navigation_target_not_visible")
  }

  private func legacyAutomationDestinationTitle(named target: String) -> String? {
    switch target.lowercased().replacingOccurrences(of: "-", with: "_") {
    case "dashboard", "home": return "Home"
    case "conversations": return "Conversations"
    case "chat": return "Chat"
    case "memories": return "Memories"
    case "tasks": return "Tasks"
    case "focus": return "Focus"
    case "insight": return "Insights"
    case "rewind": return "Rewind"
    case "apps", "integrations": return "Apps"
    case "settings": return "Settings"
    case "permissions": return "Permissions"
    case "help": return "Help from Founder"
    default: return nil
    }
  }
}

/// Shared legacy and cohort visibility comparison retained separately from the
/// HTTP bridge so it has no access to rollout state beyond the sampled snapshot.
enum DesktopAutomationNavigationVisibilityPolicy {
  static func isTargetVisible(
    shellVariant: String?,
    selectedTab: String?,
    visibleChatFirstRoute: String?,
    expectedChatFirstRoute: String?,
    expectedLegacyTitle: String?
  ) -> Bool {
    switch shellVariant {
    case "chat_first":
      return expectedChatFirstRoute != nil && visibleChatFirstRoute == expectedChatFirstRoute
    case "legacy":
      return expectedLegacyTitle != nil && selectedTab == expectedLegacyTitle
    default:
      return false
    }
  }
}
