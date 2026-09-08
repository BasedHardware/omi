import AppKit
import Combine
import Foundation

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
  /// The day's full recap. Carries identity only, never content: the page
  /// re-reads the record through the shared store or the API, so a relaunch
  /// onto a persisted recap route re-fetches (or degrades gracefully) instead
  /// of restoring stale text. Not a primary destination — no sidebar chip and
  /// no automation name routes here; only an opening recap row does.
  case dailyRecap(DailyRecapRouteRef)

  var stableName: String {
    switch self {
    case .chat: return "chat"
    case .conversations: return "conversations"
    case .tasks: return "tasks"
    case .goals: return "goals"
    case .memories: return "memories"
    case .more(let page): return "more.\(page.stableName)"
    case .dailyRecap: return "daily-recap"
    }
  }

  var analyticsRoute: ChatFirstAnalyticsEvent.Route {
    switch self {
    case .chat: return .chat
    case .conversations: return .conversations
    case .tasks: return .tasks
    case .goals: return .goals
    case .memories: return .memories
    case .more: return .more
    case .dailyRecap: return .dailyRecap
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
    case .dailyRecap: return "Daily recap"
    }
  }

  var isPrimaryDestination: Bool {
    switch self {
    case .chat, .conversations, .tasks, .goals, .memories: return true
    case .more, .dailyRecap: return false
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
    case "conversations": return .memories
    case "tasks": return .tasks
    case "goals": return .goals
    case "memories": return .memories
    default: return nil
    }
  }

  /// Maps every legacy-compatible automation name to its mounted Chat-first route.
  /// Dashboard/Home are aliases for the canonical Chat surface: dispatch remains
  /// owned by `DesktopHomeView`, but the cohort never mounts a second Dashboard
  /// Home for either legacy name.
  static func automationVisibilityDestination(named target: String) -> ChatFirstRoute? {
    if let primary = primaryAutomationDestination(named: target) {
      return primary
    }
    let normalized = target.lowercased().replacingOccurrences(of: "-", with: "_")
    switch normalized {
    case "dashboard", "home": return .chat
    // `help` used to name a "Help from Founder" page no shell mounted. Getting
    // help from a person lives in Settings → About (the Community card), so the
    // legacy name resolves to the destination that actually exists.
    case "help": return .more(.settings)
    case "rewind": return .more(.rewind)
    case "apps", "integrations": return .more(.apps)
    case "permissions": return .more(.permissions)
    case "settings": return .more(.settings)
    default: return nil
    }
  }
}

extension ChatFirstRoute {
  /// True for the automation names that mean "get help from a person". The root
  /// pre-selects the About section for these before routing to Settings.
  static func isHelpAutomationTarget(_ target: String) -> Bool {
    target.lowercased().replacingOccurrences(of: "-", with: "_") == "help"
  }
}

/// Identity for a recap route: which record, which day. Both are stable wire
/// values, so the persisted route survives a relaunch and the page it opens
/// can re-fetch (or fall back) from them alone.
struct DailyRecapRouteRef: Hashable, Codable, Sendable {
  var recordID: String
  var date: String
}

enum ChatFirstMorePage: String, CaseIterable, Codable, Hashable, Sendable {
  case dashboard
  case rewind
  case apps
  case permissions
  case settings

  var stableName: String { rawValue }

  var title: String {
    switch self {
    case .dashboard: return "Dashboard"
    case .rewind: return "Rewind"
    case .apps: return "Apps"
    case .permissions: return "Permissions"
    case .settings: return "Settings"
    }
  }

  var systemImage: String {
    switch self {
    case .dashboard: return "house.fill"
    case .rewind: return "clock.arrow.circlepath"
    case .apps: return "puzzlepiece.fill"
    case .permissions: return PermissionNavSymbol.filled
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
    case .capture: return .memories
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

  var userMessage: String {
    switch self {
    case .tasks:
      return "Help me review my current tasks."
    case .goals:
      return "Help me create a goal."
    case .goal(let id):
      return "Help me continue working on goal \(id)."
    }
  }
}

private struct ChatFirstPersistedNavigation: Codable, Equatable {
  var route: ChatFirstRoute
  var isSidebarCollapsed: Bool
}

/// Root-owned navigation and focus state for the universal shell. The only
/// persisted values are route and collapse preference; a focus request is a
/// transient deep-link contract and must be acknowledged by the destination
/// only after that entity is visible.
@MainActor
final class ChatFirstShellNavigation: ObservableObject {
  static let storageKey = "chatFirstShell.windowNavigation.v1"

  /// The one navigation owner. The main window binds it, and the auxiliary Chat
  /// surfaces (task panel, floating/notch) bind the same instance so a content
  /// block tapped anywhere routes the single shell rather than a private copy.
  static let shared = ChatFirstShellNavigation()

  @Published private(set) var route: ChatFirstRoute
  /// The destination currently mounted by SwiftUI. This is deliberately
  /// separate from `route`: navigation commands are not complete until the
  /// requested target has actually appeared.
  @Published private(set) var visibleRoute: ChatFirstRoute?
  @Published private(set) var pendingFocus: ChatFirstPendingFocus?
  /// A conversation fetched by ID for a Chat-first conversation link. Unlike
  /// the paginated list, this transient value is the exact server record the
  /// user validated and asked to open.
  @Published private(set) var pendingConversation: ServerConversation?
  /// The primary route the reader was on when a recap row opened the recap
  /// page. The page's back chevron returns there. Transient like a focus —
  /// never persisted, reset on owner change, and only ever a primary route.
  @Published private(set) var dailyRecapOrigin: ChatFirstRoute?
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
  private var goalLinkResolutionGeneration: UInt = 0
  private var conversationLinkResolutionGeneration: UInt = 0
  private nonisolated(unsafe) var ownerChangeObserver: NSObjectProtocol?

  init(
    defaults: UserDefaults = .standard,
    analytics: (@MainActor (ChatFirstAnalyticsEvent) -> Void)? = nil
  ) {
    self.defaults = defaults
    self.analytics =
      analytics ?? { event in
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
    pendingConversation = nil
    pendingFocusDestination = nil
    dailyRecapOrigin = nil
    visibleRoute = nil
    lastAcknowledgedFocusKind = nil
    focusedEntityID = nil
    isFocusedEntityAcknowledged = false
    ownerChangeObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: nil
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.resetOwnerScopedTransientState()
      }
    }
  }

  deinit {
    if let ownerChangeObserver {
      NotificationCenter.default.removeObserver(ownerChangeObserver)
    }
  }

  func selectPrimary(
    _ destination: ChatFirstRoute,
    origin: ChatFirstAnalyticsEvent.RouteOrigin = .sidebar
  ) {
    guard destination.isPrimaryDestination else { return }
    // A direct tab selection supersedes any exact conversation deep-link that
    // has not yet been consumed by the Conversations host — and any recap page
    // it may have been the back target of.
    pendingConversation = nil
    dailyRecapOrigin = nil
    // Selecting the already-mounted tab is a no-op. Clearing visibleRoute here
    // used to leave the automation state permanently "not visible" because
    // SwiftUI correctly did not remount the unchanged destination.
    if route == destination {
      invalidateLinkResolutions()
      clearFocus()
      return
    }
    invalidateLinkResolutions()
    ChatSwitchPerfLog.beginSwitch(destination: "selectPrimary:\(destination.stableName)")
    route = destination
    visibleRoute = nil
    clearFocus()
    persistNavigation()
    analytics(.routeEntered(route: destination.analyticsRoute, origin: origin))
  }

  @discardableResult
  func handleEscapeNavigation() -> Bool {
    if case .dailyRecap = route {
      closeDailyRecap()
      return true
    }
    guard route != .chat else { return false }
    selectPrimary(.chat)
    return true
  }

  func selectMore(_ page: ChatFirstMorePage) {
    pendingConversation = nil
    dailyRecapOrigin = nil
    if route == .more(page) {
      invalidateLinkResolutions()
      clearFocus()
      return
    }
    invalidateLinkResolutions()
    ChatSwitchPerfLog.beginSwitch(destination: "selectMore:\(page.stableName)")
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
  /// choose its destination. Destinations must remain in the Chat-first primary
  /// navigation; no legacy page can receive a pending focus.
  func open(focus: ChatFirstPendingFocus, destination: ChatFirstRoute) {
    guard destination.isPrimaryDestination else { return }
    presentMainWindowIfNeeded()
    pendingConversation = nil
    invalidateLinkResolutions()
    route = destination
    visibleRoute = nil
    pendingFocus = focus
    pendingFocusDestination = destination
    focusedEntityID = focus.entityID
    isFocusedEntityAcknowledged = false
    persistNavigation()
    analytics(.routeEntered(route: destination.analyticsRoute, origin: .chatDeeplink))
  }

  /// Opens a conversation whose detail was already validated by ID. Keeping
  /// the fetched record on the navigation owner lets the Conversations page
  /// present it even when the paginated list does not currently contain it.
  ///
  /// Every caller defaults to the Memory hub, which owns the only
  /// ConversationsPageHost and navigation chrome.
  func open(conversation: ServerConversation) {
    open(conversation: conversation, destination: .memories)
  }

  func open(conversation: ServerConversation, destination: ChatFirstRoute) {
    guard destination.isPrimaryDestination else { return }
    guard !conversation.id.isEmpty else { return }
    presentMainWindowIfNeeded()
    invalidateLinkResolutions()
    route = destination
    visibleRoute = nil
    pendingFocus = nil
    pendingFocusDestination = nil
    focusedEntityID = nil
    isFocusedEntityAcknowledged = false
    pendingConversation = conversation
    dailyRecapOrigin = nil
    persistNavigation()
    analytics(.routeEntered(route: destination.analyticsRoute, origin: .chatDeeplink))
  }

  /// Opens the day's recap page from a recap row (Chat transcript or Activity).
  /// The route records the primary surface the reader came from, so the page's
  /// back chevron returns there instead of always bouncing to Chat.
  func openDailyRecap(_ ref: DailyRecapRouteRef) {
    presentMainWindowIfNeeded()
    // Capture the origin BEFORE the route moves — it is where the reader is.
    let origin = route.isPrimaryDestination ? route : ChatFirstRoute.chat
    invalidateLinkResolutions()
    route = .dailyRecap(ref)
    visibleRoute = nil
    pendingFocus = nil
    pendingFocusDestination = nil
    focusedEntityID = nil
    isFocusedEntityAcknowledged = false
    pendingConversation = nil
    dailyRecapOrigin = origin
    persistNavigation()
    analytics(.routeEntered(route: .dailyRecap, origin: .chatDeeplink))
  }

  /// The recap page's back chevron, and Escape while on it: back to the surface
  /// that opened the recap, or Chat when that surface is gone.
  func closeDailyRecap() {
    guard case .dailyRecap = route else { return }
    let origin = dailyRecapOrigin ?? .chat
    dailyRecapOrigin = nil
    selectPrimary(origin, origin: .sidebar)
  }

  /// A Goal link validates asynchronously before it opens a typed focus. The
  /// root navigation owner fences overlapping link validations so a late result
  /// cannot replace the route selected by a newer link request.
  func beginGoalLinkResolution() -> UInt {
    invalidateLinkResolutions()
    return goalLinkResolutionGeneration
  }

  func isCurrentGoalLinkResolution(_ generation: UInt) -> Bool {
    goalLinkResolutionGeneration == generation
  }

  @discardableResult
  func completeGoalLinkResolution(goalID: String, generation: UInt) -> Bool {
    guard isCurrentGoalLinkResolution(generation) else { return false }
    open(focus: .goal(id: goalID))
    return true
  }

  /// A conversation detail fetch can outlive the user's current route. The
  /// generation belongs to the root navigation owner so a late response
  /// cannot pull the user back to Conversations after a newer selection.
  func beginConversationLinkResolution() -> UInt {
    invalidateConversationLinkResolutions()
    return conversationLinkResolutionGeneration
  }

  func isCurrentConversationLinkResolution(_ generation: UInt) -> Bool {
    conversationLinkResolutionGeneration == generation
  }

  @discardableResult
  func completeConversationLinkResolution(
    conversation: ServerConversation,
    generation: UInt
  ) -> Bool {
    guard isCurrentConversationLinkResolution(generation) else { return false }
    open(conversation: conversation)
    return true
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

  /// Opens the canonical main chat with a conversation source staged in its
  /// composer. The existing draft is intentionally untouched and no turn is
  /// submitted until the user types and presses Send.
  func stageCaptureReference(
    _ conversation: ServerConversation,
    using chatProvider: ChatProvider,
    momentTimestamp: TimeInterval? = nil
  ) {
    let preview =
      conversation.structured.overview.isEmpty
      ? (conversation.transcriptSegments.first?.text ?? "")
      : conversation.structured.overview
    chatProvider.stageComposerReference(
      ChatComposerReference(
        kind: .conversation,
        sourceID: conversation.id,
        title: conversation.displayTitle,
        preview: preview,
        momentTimestampMs: momentTimestamp.map { Int($0 * 1_000) }
      ))
    selectPrimary(.chat, origin: .chatDeeplink)
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
    case .dashboard: selectPrimary(.chat)
    case .conversations: selectPrimary(.memories)
    case .memories: selectPrimary(.memories)
    case .tasks: selectPrimary(.tasks)
    case .rewind: selectMore(.rewind)
    case .apps: selectMore(.apps)
    case .settings: selectMore(.settings)
    case .permissions: selectMore(.permissions)
    }
  }

  /// A typed deep link can originate from a surface that is not the main window
  /// (a content block in the notch or the task panel). Bring the window forward
  /// so the destination this call selects is actually on screen. Already-key is
  /// the common case and stays a no-op.
  private func presentMainWindowIfNeeded() {
    // `NSApp` is an implicitly unwrapped optional and is genuinely nil in a unit
    // test host, so it is read through an explicit optional rather than touched.
    let application: NSApplication? = NSApp
    guard let application else { return }
    if let window = application.mainWindow, window.isKeyWindow, window.isVisible { return }
    AppDelegate.summonWindowTarget()?.openMainAppWindow()
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

  /// Persisted route preference is owner-neutral, but fetched records and
  /// entity focus are not. An in-place account switch must invalidate both the
  /// values and any async link resolution that could repopulate them.
  private func resetOwnerScopedTransientState() {
    invalidateLinkResolutions()
    pendingConversation = nil
    dailyRecapOrigin = nil
    clearFocus()
    lastAcknowledgedFocusKind = nil
  }

  private func invalidateLinkResolutions() {
    goalLinkResolutionGeneration &+= 1
    conversationLinkResolutionGeneration &+= 1
  }

  private func invalidateConversationLinkResolutions() {
    conversationLinkResolutionGeneration &+= 1
  }

}

/// An immutable per-root sampling result for the server-owned chat-first
/// capability. It never selects a shell — there is exactly one — and only says
/// whether the capability-gated kernel features may engage this launch. A
/// failed, missing, stale, or owner-mismatched control response resolves to
/// capability-off; content blocks still render either way.
struct ChatFirstCapabilitySample: Equatable {
  private(set) var isResolved = false
  private(set) var projection: ChatFirstCapabilityProjection?
  private(set) var sampledOwnerID: String?

  mutating func resolve(
    control: OmiAPI.TaskWorkflowControl?,
    requestedOwnerID: String?,
    ownerIsStillCurrent: Bool
  ) {
    guard !isResolved else { return }
    isResolved = true
    guard let ownerID = requestedOwnerID, !ownerID.isEmpty, ownerIsStillCurrent else {
      projection = nil
      return
    }
    sampledOwnerID = ownerID
    guard let control else {
      projection = nil
      return
    }
    projection = ChatFirstCapabilityProjection(control: control)
  }

  mutating func ownerDidChange(to ownerID: String?) {
    guard let sampledOwnerID else { return }
    guard sampledOwnerID == ownerID else {
      projection = nil
      return
    }
  }

  mutating func failClosed() {
    projection = nil
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
