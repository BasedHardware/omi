import Foundation
import Combine

/// Chat-first navigation deliberately does not reuse the legacy sidebar's raw
/// integer values. The legacy adapter below is the only compatibility boundary
/// while both shells are live.
enum ChatFirstRoute: Hashable, Codable, Sendable {
  case chat
  case conversations
  case tasks
  case goals
  case memories
  case more(ChatFirstMorePage)

  var stableName: String {
    switch self {
    case .chat: return "chat"
    case .conversations: return "conversations"
    case .tasks: return "tasks"
    case .goals: return "goals"
    case .memories: return "memories"
    case .more(let page): return "more.\(page.stableName)"
    }
  }

  var title: String {
    switch self {
    case .chat: return "Chat"
    case .conversations: return "Conversations"
    case .tasks: return "Tasks"
    case .goals: return "Goals"
    case .memories: return "Memories"
    case .more(let page): return page.title
    }
  }

  var isPrimaryDestination: Bool {
    switch self {
    case .chat, .conversations, .tasks, .goals, .memories: return true
    case .more: return false
    }
  }

  static let primaryDestinations: [ChatFirstRoute] = [
    .chat, .conversations, .tasks, .goals, .memories,
  ]

  /// Automation reuses the stable names of primary destinations. Legacy-only
  /// locations deliberately return nil here and continue through the legacy
  /// sidebar adapter in `DesktopHomeView`.
  static func primaryAutomationDestination(named target: String) -> ChatFirstRoute? {
    let normalized = target.lowercased().replacingOccurrences(of: "-", with: "_")
    switch normalized {
    case "chat": return .chat
    case "conversations": return .conversations
    case "tasks": return .tasks
    case "goals": return .goals
    case "memories": return .memories
    default: return nil
    }
  }
}

enum ChatFirstMorePage: String, CaseIterable, Codable, Hashable, Sendable {
  case dashboard
  case focus
  case insight
  case rewind
  case apps
  case permissions
  case help
  case settings

  var stableName: String { rawValue }

  var title: String {
    switch self {
    case .dashboard: return "Dashboard"
    case .focus: return "Focus"
    case .insight: return "Insights"
    case .rewind: return "Rewind"
    case .apps: return "Apps"
    case .permissions: return "Permissions"
    case .help: return "Help from Founder"
    case .settings: return "Settings"
    }
  }

  var systemImage: String {
    switch self {
    case .dashboard: return "house.fill"
    case .focus: return "eye.fill"
    case .insight: return "lightbulb.fill"
    case .rewind: return "clock.arrow.circlepath"
    case .apps: return "puzzlepiece.fill"
    case .permissions: return "exclamationmark.triangle.fill"
    case .help: return "bubble.left.fill"
    case .settings: return "gearshape.fill"
    }
  }
}

enum ChatFirstPendingFocus: Equatable, Sendable {
  case task(id: String)
  case goal(id: String)
  case capture(id: String, momentTs: TimeInterval?)
  case memory(id: String)

  var route: ChatFirstRoute {
    switch self {
    case .task: return .tasks
    case .goal: return .goals
    case .capture: return .conversations
    case .memory: return .memories
    }
  }

  var stableName: String {
    switch self {
    case .task: return "task"
    case .goal: return "goal"
    case .capture: return "capture"
    case .memory: return "memory"
    }
  }
}

private struct ChatFirstPersistedNavigation: Codable, Equatable {
  var route: ChatFirstRoute
  var isSidebarCollapsed: Bool
}

/// Root-owned navigation and focus state for the cohort-only shell. The only
/// persisted values are route and collapse preference; a focus request is a
/// transient deep-link contract and must be acknowledged by the destination
/// only after that entity is visible.
@MainActor
final class ChatFirstShellNavigation: ObservableObject {
  static let storageKey = "chatFirstShell.windowNavigation.v1"

  @Published private(set) var route: ChatFirstRoute
  @Published private(set) var pendingFocus: ChatFirstPendingFocus?
  @Published private(set) var lastAcknowledgedFocusKind: String?
  @Published private(set) var isSidebarCollapsed: Bool

  private let defaults: UserDefaults

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    if let data = defaults.data(forKey: Self.storageKey),
      let persisted = try? JSONDecoder().decode(ChatFirstPersistedNavigation.self, from: data)
    {
      route = persisted.route
      isSidebarCollapsed = persisted.isSidebarCollapsed
    } else {
      route = .chat
      isSidebarCollapsed = false
    }
    pendingFocus = nil
    lastAcknowledgedFocusKind = nil
  }

  func selectPrimary(_ destination: ChatFirstRoute) {
    guard destination.isPrimaryDestination else { return }
    route = destination
    pendingFocus = nil
    persistNavigation()
  }

  func selectMore(_ page: ChatFirstMorePage) {
    route = .more(page)
    pendingFocus = nil
    persistNavigation()
  }

  /// Used by a typed rich-Chat link. Unlike direct navigation it carries the
  /// focus until the destination calls `acknowledgeFocus` after visible load.
  func open(focus: ChatFirstPendingFocus) {
    route = focus.route
    pendingFocus = focus
    persistNavigation()
  }

  @discardableResult
  func acknowledgeFocus(_ focus: ChatFirstPendingFocus) -> Bool {
    guard route == focus.route, pendingFocus == focus else { return false }
    pendingFocus = nil
    lastAcknowledgedFocusKind = focus.stableName
    return true
  }

  func toggleSidebar() {
    isSidebarCollapsed.toggle()
    persistNavigation()
  }

  func setSidebarCollapsed(_ isCollapsed: Bool) {
    guard isSidebarCollapsed != isCollapsed else { return }
    isSidebarCollapsed = isCollapsed
    persistNavigation()
  }

  /// Compatibility boundary for existing automation names and page callbacks.
  /// No Chat-first route is represented by a legacy raw index internally.
  func selectLegacyDestination(_ item: SidebarNavItem) {
    switch item {
    case .dashboard: selectMore(.dashboard)
    case .conversations: selectPrimary(.conversations)
    case .chat: selectPrimary(.chat)
    case .memories: selectPrimary(.memories)
    case .tasks: selectPrimary(.tasks)
    case .focus: selectMore(.focus)
    case .insight: selectMore(.insight)
    case .rewind: selectMore(.rewind)
    case .apps: selectMore(.apps)
    case .settings: selectMore(.settings)
    case .permissions: selectMore(.permissions)
    case .help: selectMore(.help)
    }
  }

  private func persistNavigation() {
    let persisted = ChatFirstPersistedNavigation(route: route, isSidebarCollapsed: isSidebarCollapsed)
    defaults.set(try? JSONEncoder().encode(persisted), forKey: Self.storageKey)
  }
}

/// An immutable per-root sampling result. A failed, missing, stale, or
/// owner-mismatched control response resolves to legacy. Once resolved for an
/// owner it never live-swaps; owner replacement fails closed for this launch.
enum ChatFirstShellVariant: Equatable {
  case unresolved
  case legacy
  case chatFirst(ChatFirstCapabilityProjection)

  var projection: ChatFirstCapabilityProjection? {
    guard case .chatFirst(let projection) = self else { return nil }
    return projection
  }

  var stableName: String {
    switch self {
    case .unresolved: return "loading"
    case .legacy: return "legacy"
    case .chatFirst: return "chat_first"
    }
  }
}

struct ChatFirstShellCapabilitySample: Equatable {
  private(set) var variant: ChatFirstShellVariant = .unresolved
  private(set) var sampledOwnerID: String?

  mutating func resolve(
    control: OmiAPI.TaskWorkflowControl?,
    requestedOwnerID: String?,
    ownerIsStillCurrent: Bool
  ) {
    guard case .unresolved = variant else { return }
    guard let ownerID = requestedOwnerID, !ownerID.isEmpty, ownerIsStillCurrent else {
      variant = .legacy
      return
    }
    sampledOwnerID = ownerID
    if let control, let projection = ChatFirstCapabilityProjection(control: control) {
      variant = .chatFirst(projection)
    } else {
      variant = .legacy
    }
  }

  mutating func ownerDidChange(to ownerID: String?) {
    guard let sampledOwnerID else { return }
    guard sampledOwnerID == ownerID else {
      variant = .legacy
      return
    }
  }

  mutating func failClosed() {
    variant = .legacy
  }
}

/// The provider owns this tiny bridge handoff. It contains no persistence and
/// only projects an enabled sample to the exact main-Chat surface and owner.
struct ChatFirstMainChatProjectionGate: Equatable {
  private var ownerID: String?
  private var sample: ChatFirstCapabilityProjection?
  private var mainChatWasResolved = false

  mutating func configure(sample: ChatFirstCapabilityProjection?, ownerID: String?) -> Bool {
    guard let ownerID, !ownerID.isEmpty else { return false }
    if mainChatWasResolved {
      return self.ownerID == ownerID && self.sample == sample
    }
    if let configuredOwner = self.ownerID {
      return configuredOwner == ownerID && self.sample == sample
    }
    self.ownerID = ownerID
    self.sample = sample
    return true
  }

  func isConfigured(for ownerID: String?) -> Bool {
    self.ownerID == ownerID && ownerID != nil
  }

  func capability(
    for surface: AgentSurfaceReference,
    ownerID: String?
  ) -> ChatFirstCapabilityProjection? {
    guard surface.surfaceKind == "main_chat", self.ownerID == ownerID else { return nil }
    return sample
  }

  mutating func markResolved(surface: AgentSurfaceReference, ownerID: String?) {
    guard surface.surfaceKind == "main_chat", self.ownerID == ownerID else { return }
    mainChatWasResolved = true
  }
}
