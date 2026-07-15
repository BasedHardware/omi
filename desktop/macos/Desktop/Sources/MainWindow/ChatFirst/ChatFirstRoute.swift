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

  /// Maps every legacy-compatible automation name to its mounted cohort route.
  /// This is visibility-only: dispatch remains owned by `DesktopHomeView` so
  /// callers retain the legacy adapter while the old shell is active.
  static func automationVisibilityDestination(named target: String) -> ChatFirstRoute? {
    if let primary = primaryAutomationDestination(named: target) {
      return primary
    }
    let normalized = target.lowercased().replacingOccurrences(of: "-", with: "_")
    switch normalized {
    case "dashboard", "home": return .more(.dashboard)
    case "focus": return .more(.focus)
    case "insight": return .more(.insight)
    case "rewind": return .more(.rewind)
    case "apps", "integrations": return .more(.apps)
    case "permissions": return .more(.permissions)
    case "help": return .more(.help)
    case "settings": return .more(.settings)
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

  /// This identifier is intentionally retained only in the in-memory
  /// navigation contract. The non-production automation bridge can prove the
  /// exact focus acknowledgement without sending it to analytics or persisting
  /// it across launches.
  var entityID: String {
    switch self {
    case .task(let id), .goal(let id), .capture(let id, _), .memory(let id): return id
    }
  }
}

/// A route-safe, strongly typed origin for the one normal user turn created
/// by a page's "Discuss in Chat" affordance. Pages never construct model
/// prompts from display strings or pass raw URLs into Chat.
enum ChatFirstDiscussionContext: Equatable, Sendable {
  case tasks
  case goals
  case goal(id: String)
  case capture(id: String, momentTimestamp: TimeInterval?)

  var userMessage: String {
    switch self {
    case .tasks:
      return "Help me review my current tasks."
    case .goals:
      return "Help me create a goal."
    case .goal(let id):
      return "Help me continue working on goal \(id)."
    case .capture(let id, let momentTimestamp):
      if let momentTimestamp {
        return "Discuss Omi capture \(id) at \(Int(momentTimestamp)) seconds."
      }
      return "Discuss Omi capture \(id)."
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
  /// The destination currently mounted by SwiftUI. This is deliberately
  /// separate from `route`: navigation commands are not complete until the
  /// requested target has actually appeared.
  @Published private(set) var visibleRoute: ChatFirstRoute?
  @Published private(set) var pendingFocus: ChatFirstPendingFocus?
  /// A related-entity link can intentionally land in a different primary
  /// destination (for example, a Goal's task list). This is transient like the
  /// focus itself and is never restored across launches.
  @Published private(set) var pendingFocusDestination: ChatFirstRoute?
  @Published private(set) var lastAcknowledgedFocusKind: String?
  /// Test-only bridge state for proving route focus reaches the intended
  /// entity. This is neither persisted nor emitted in analytics.
  @Published private(set) var focusedEntityID: String?
  @Published private(set) var isFocusedEntityAcknowledged: Bool
  @Published private(set) var isSidebarCollapsed: Bool

  private let defaults: UserDefaults
  private let analytics: @MainActor (ChatFirstAnalyticsEvent) -> Void

  init(
    defaults: UserDefaults = .standard,
    analytics: (@MainActor (ChatFirstAnalyticsEvent) -> Void)? = nil
  ) {
    self.defaults = defaults
    self.analytics = analytics ?? { event in
      AnalyticsManager.shared.chatFirst(event)
    }
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
    pendingFocusDestination = nil
    visibleRoute = nil
    lastAcknowledgedFocusKind = nil
    focusedEntityID = nil
    isFocusedEntityAcknowledged = false
  }

  func selectPrimary(
    _ destination: ChatFirstRoute,
    origin: ChatFirstAnalyticsEvent.RouteOrigin = .sidebar
  ) {
    guard destination.isPrimaryDestination else { return }
    route = destination
    visibleRoute = nil
    clearFocus()
    persistNavigation()
    analytics(.routeEntered(route: analyticsRoute(destination), origin: origin))
  }

  func selectMore(_ page: ChatFirstMorePage) {
    route = .more(page)
    visibleRoute = nil
    clearFocus()
    persistNavigation()
    analytics(.routeEntered(route: .more, origin: .more))
  }

  /// Used by a typed rich-Chat link. Unlike direct navigation it carries the
  /// focus until the destination calls `acknowledgeFocus` after visible load.
  func open(focus: ChatFirstPendingFocus) {
    open(focus: focus, destination: focus.route)
  }

  /// Preserves the typed focus contract while allowing a relationship link to
  /// choose its destination. Destinations must remain in the cohort primary
  /// navigation; no legacy page can receive a pending focus.
  func open(focus: ChatFirstPendingFocus, destination: ChatFirstRoute) {
    guard destination.isPrimaryDestination else { return }
    route = destination
    visibleRoute = nil
    pendingFocus = focus
    pendingFocusDestination = destination
    focusedEntityID = focus.entityID
    isFocusedEntityAcknowledged = false
    persistNavigation()
    analytics(.routeEntered(route: analyticsRoute(destination), origin: .chatDeeplink))
  }

  /// Routes first, then records exactly one ordinary main-Chat user turn.
  /// `ChatProvider` remains the single journal owner; navigation stores no
  /// transcript copy or separate session identity.
  func discuss(_ context: ChatFirstDiscussionContext, using chatProvider: ChatProvider) {
    selectPrimary(.chat, origin: .chatDeeplink)
    Task {
      _ = await chatProvider.sendMessage(context.userMessage)
    }
  }

  @discardableResult
  func acknowledgeFocus(_ focus: ChatFirstPendingFocus) -> Bool {
    guard route == pendingFocusDestination, pendingFocus == focus else { return false }
    pendingFocus = nil
    pendingFocusDestination = nil
    lastAcknowledgedFocusKind = focus.stableName
    focusedEntityID = focus.entityID
    isFocusedEntityAcknowledged = true
    return true
  }

  /// Called by the mounted destination, never by the navigation command. This
  /// gives the non-production bridge an exact-target-visible acknowledgement
  /// without persisting a second navigation state or emitting entity data.
  func markRouteVisible(_ destination: ChatFirstRoute) {
    guard route == destination else { return }
    visibleRoute = destination
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

  private func clearFocus() {
    pendingFocus = nil
    pendingFocusDestination = nil
    focusedEntityID = nil
    isFocusedEntityAcknowledged = false
  }

  private func analyticsRoute(_ route: ChatFirstRoute) -> ChatFirstAnalyticsEvent.Route {
    switch route {
    case .chat: return .chat
    case .conversations: return .conversations
    case .tasks: return .tasks
    case .goals: return .goals
    case .memories: return .memories
    case .more: return .more
    }
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
