import SwiftUI

/// Routing target for the redesigned nav rail. Raw values match the existing
/// `SidebarNavItem` routing indices so the rail drives the same `PageContentView`
/// switch; `more` is a new launcher page (see `RedesignMorePage`).
enum RedesignRoute: Int {
  case home = 0
  case conversations = 1
  case chat = 2  // "Ask omi"
  case memories = 3
  case tasks = 4
  case focus = 5
  case insight = 6
  case rewind = 7
  case apps = 8
  case settings = 9
  case permissions = 10
  case help = 12
  case more = 20
  case persona = 21
  case planUsage = 22
  case messages = 23
  case brainMap = 24

  var icon: String {
    switch self {
    case .home: return "house"
    case .conversations: return "waveform"
    case .chat: return "sparkles"
    case .memories: return "brain"
    case .messages: return "message"
    case .tasks: return "checklist"
    case .focus: return "eye"
    case .insight: return "lightbulb"
    case .rewind: return "clock.arrow.circlepath"
    case .apps: return "puzzlepiece"
    case .settings: return "gearshape"
    case .permissions: return "lock.shield"
    case .help: return "bubble.left"
    case .more: return "square.grid.2x2"
    case .persona: return "theatermasks"
    case .planUsage: return "star"
    case .brainMap: return "point.3.connected.trianglepath.dotted"
    }
  }

  var title: String {
    switch self {
    case .home: return "Home"
    case .conversations: return "Conversations"
    case .chat: return "Ask omi"
    case .memories: return "Memory"
    case .messages: return "Messages"
    case .tasks: return "Tasks"
    case .focus: return "Focus"
    case .insight: return "Insights"
    case .rewind: return "Rewind"
    case .apps: return "Apps"
    case .settings: return "Settings"
    case .permissions: return "Permissions"
    case .help: return "Talk to a founder"
    case .more: return "All features"
    case .persona: return "Persona"
    case .planUsage: return "Plan & usage"
    case .brainMap: return "Brain map"
    }
  }
}

/// The 68px minimal icon nav rail — replaces the old sidebar.
struct RedesignRail: View {
  @Binding var selectedIndex: Int
  @ObservedObject var appState: AppState
  @ObservedObject private var insightStorage = InsightStorage.shared

  private let primary: [RedesignRoute] = [
    .home, .chat, .conversations, .memories, .messages, .tasks, .rewind,
  ]

  var body: some View {
    VStack(spacing: 4) {
      // Buddy mark → Home
      Button { select(.home) } label: {
        BuddyRing(diameter: 22, dot: 3, color: Ink.ink)
          .frame(width: 44, height: 40)
      }
      .buttonStyle(.plain)
      .padding(.bottom, 12)

      ForEach(primary, id: \.rawValue) { route in
        RailItem(
          icon: route.icon,
          title: route.title,
          isActive: isActive(route),
          badge: route == .conversations ? insightStorage.unreadCount : 0,
          action: { select(route) })
      }

      Spacer()

      RailItem(icon: RedesignRoute.more.icon, title: RedesignRoute.more.title,
        isActive: isActive(.more), action: { select(.more) })
      RailItem(icon: RedesignRoute.settings.icon, title: RedesignRoute.settings.title,
        isActive: isActive(.settings), action: { select(.settings) })
    }
    .padding(.vertical, 14)
    .frame(width: 68)
    .frame(maxHeight: .infinity)
    .background(Ink.soft)
    .overlay(Rectangle().fill(Ink.hair).frame(width: 1), alignment: .trailing)
  }

  private func isActive(_ route: RedesignRoute) -> Bool {
    // Many pages share one rail icon, mirroring the mockup.
    switch route {
    case .home: return [0, 5, 6].contains(selectedIndex)  // dashboard/focus/insights
    case .memories: return [3, 21, 24].contains(selectedIndex)  // memory/persona/brain-map
    case .settings: return [9, 10, 12, 22].contains(selectedIndex)  // settings/perms/help/plan
    case .more: return selectedIndex == 20 || selectedIndex == 8  // more/apps
    default: return selectedIndex == route.rawValue
    }
  }

  private func select(_ route: RedesignRoute) {
    selectedIndex = route.rawValue
    AnalyticsManager.shared.tabChanged(tabName: route.title)
  }
}

private struct RailItem: View {
  let icon: String
  let title: String
  let isActive: Bool
  var badge: Int = 0
  let action: () -> Void

  @State private var hovering = false

  var body: some View {
    Button(action: action) {
      ZStack {
        RoundedRectangle(cornerRadius: 11, style: .continuous)
          .fill(isActive ? Ink.surface : (hovering ? Ink.surface2 : .clear))
          .overlay(
            isActive
              ? RoundedRectangle(cornerRadius: 11).strokeBorder(Ink.hair, lineWidth: 1) : nil
          )
          .frame(width: 44, height: 44)

        Image(systemName: icon)
          .font(.system(size: 19, weight: .regular))
          .foregroundColor(isActive ? Ink.ink : (hovering ? Ink.body : Ink.faint))

        if badge > 0 {
          Circle().fill(Ink.ink).frame(width: 8, height: 8)
            .offset(x: 13, y: -13)
        }
      }
      .frame(width: 44, height: 44)
      .overlay(alignment: .leading) {
        if isActive {
          RoundedRectangle(cornerRadius: 2).fill(Ink.accent)
            .frame(width: 3, height: 20).offset(x: -12)
        }
      }
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { hovering = $0 }
    .help(title)
    .accessibilityLabel(title)
  }
}
