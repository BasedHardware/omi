import Foundation

/// Cohort-shell visibility proof for the non-production automation bridge.
/// The bridge reports success only after the target route has actually mounted.
extension DesktopAutomationBridge {
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
