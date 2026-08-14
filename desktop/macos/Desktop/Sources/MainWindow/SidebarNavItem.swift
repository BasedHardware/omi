// MARK: - Navigation Item Model
enum SidebarNavItem: Int, CaseIterable {
  /// The automation bridge's name for a destination, resolved to the legacy shell's item.
  ///
  /// The counterpart of `ChatFirstRoute.automationVisibilityDestination(named:)`, and it lives here
  /// for the same reason that one lives on the route type: a vocabulary two shells must agree on is a
  /// property of the destination, not of whichever view happened to be holding the `switch`. It was a
  /// `private func` inside `DesktopHomeView`, where nothing could call it and no test could reach it.
  ///
  /// Pure — no shell state, no side effects. Callers own the navigating.
  static func automationDestination(named target: String) -> SidebarNavItem? {
    switch target.lowercased().replacingOccurrences(of: "-", with: "_") {
    // "chat" lands on Home because Home *is* the chat now — the same contract
    // `.navigateToChat` already honours. There is no separate chat destination
    // to route to any more.
    case "dashboard", "home", "chat": return .dashboard
    case "conversations": return .conversations
    case "memories": return .memories
    case "tasks": return .tasks
    case "rewind": return .rewind
    case "apps", "integrations": return .apps
    case "settings": return .settings
    case "permissions": return .permissions
    default: return nil
    }
  }

  case dashboard = 0
  case conversations = 1
  case memories = 3
  case tasks = 4
  case rewind = 7
  case apps = 8
  case settings = 9
  case permissions = 10
  var title: String {
    switch self {
    case .dashboard: return "Home"
    case .conversations: return "Conversations"
    case .memories: return "Memories"
    case .tasks: return "Tasks"
    case .rewind: return "Rewind"
    case .apps: return "Apps"
    case .settings: return "Settings"
    case .permissions: return "Permissions"
    }
  }
  var icon: String {
    switch self {
    case .dashboard: return "house.fill"
    case .conversations: return "text.bubble.fill"
    case .memories: return "brain"
    case .tasks: return "checklist"
    case .rewind: return "clock.arrow.circlepath"
    case .apps: return "puzzlepiece.fill"
    case .settings: return "gearshape.fill"
    case .permissions: return PermissionNavSymbol.filled
    }
  }
  /// Minimum tier level required to access this item (0 = always available)
  var requiredTier: Int {
    switch self {
    case .conversations, .rewind: return 1
    case .memories: return 2
    case .tasks: return 3
    case .dashboard: return 5
    case .apps: return 6
    default: return 0
    }
  }

  /// Items shown in the main navigation (top section)
  static var mainItems: [SidebarNavItem] {
    [.dashboard, .conversations, .memories, .tasks, .rewind, .apps]
  }
}
