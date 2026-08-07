// MARK: - Navigation Item Model
enum SidebarNavItem: Int, CaseIterable {
  case dashboard = 0
  case conversations = 1
  case memories = 3
  case tasks = 4
  case rewind = 7
  case apps = 8
  case settings = 9
  case permissions = 10
  case help = 12
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
    case .help: return "Help from Founder"
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
    case .permissions: return "exclamationmark.triangle.fill"
    case .help: return "bubble.left.fill"
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
