import Foundation

// MARK: - Navigation Item Model
enum SidebarNavItem: Int, CaseIterable {
  case dashboard = 0
  case conversations = 1
  case chat = 2
  case memories = 3
  case tasks = 4
  case focus = 5
  case insight = 6
  case rewind = 7
  case apps = 8
  case settings = 9
  case permissions = 10
  case projections = 11
  case help = 12
  var title: String {
    switch self {
    case .dashboard: return "Home"
    case .conversations: return "Conversations"
    case .chat: return "Chat"
    case .memories: return "Memories"
    case .tasks: return "Tasks"
    case .focus: return "Focus"
    case .insight: return "Insights"
    case .rewind: return "Rewind"
    case .apps: return "Apps"
    case .settings: return "Settings"
    case .permissions: return "Permissions"
    case .projections: return "Omens"
    case .help: return "Help from Founder"
    }
  }
  var icon: String {
    switch self {
    case .dashboard: return "house.fill"
    case .conversations: return "text.bubble.fill"
    case .chat: return "bubble.left.and.bubble.right.fill"
    case .memories: return "brain"
    case .tasks: return "checklist"
    case .focus: return "eye.fill"
    case .insight: return "lightbulb.fill"
    case .rewind: return "clock.arrow.circlepath"
    case .apps: return "puzzlepiece.fill"
    case .settings: return "gearshape.fill"
    case .permissions: return "exclamationmark.triangle.fill"
    case .projections: return "sparkles.rectangle.stack.fill"
    case .help: return "bubble.left.fill"
    }
  }
  /// Minimum tier level required to access this item (0 = always available)
  var requiredTier: Int {
    switch self {
    case .conversations, .rewind: return 1
    case .memories: return 2
    case .tasks: return 3
    case .chat: return 4
    case .dashboard: return 5
    case .apps: return 6
    default: return 0
    }
  }

  /// Items shown in the main navigation (top section)
  static var mainItems: [SidebarNavItem] {
    mainItems(
      bundleIdentifier: Bundle.main.bundleIdentifier,
      productionOmensRolloutEnabled: false)
  }

  static func mainItems(
    bundleIdentifier: String?,
    productionOmensRolloutEnabled: Bool
  ) -> [SidebarNavItem] {
    let items: [SidebarNavItem] = [
      .dashboard, .conversations, .memories, .tasks, .focus, .insight, .projections, .rewind, .apps,
    ]
    let resolvedBundleIdentifier = bundleIdentifier ?? ""
    let omensAreUnavailable =
      AppBuild.isExternalPreviewBundleIdentifier(resolvedBundleIdentifier)
      || (AppBuild.productionFamilyBundleIdentifiers.contains(resolvedBundleIdentifier)
        && !productionOmensRolloutEnabled)
    if omensAreUnavailable {
      return items.filter { $0 != .projections }
    }
    return items
  }
}
