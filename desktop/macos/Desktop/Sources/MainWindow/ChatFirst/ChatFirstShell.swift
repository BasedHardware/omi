import AppKit
import OmiTheme
import SwiftUI

/// Universal main-window shell. It shares the existing data owners with the
/// legacy shell but owns no second chat state, task state, or navigation index.
struct ChatFirstShell: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  /// Nil until the server-owned control resolves, and permanently nil for an
  /// account it does not cover. The shell mounts either way; only the
  /// capability-gated features below wait on it.
  let capability: ChatFirstCapabilityProjection?
  @Binding var selectedSettingsSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingID: String?
  @ObservedObject private var promptMaterializationCoordinator = ChatFirstPromptMaterializationCoordinator.shared
  @StateObject private var automationRuntime: ChatFirstAutomationRuntime
  @AppStorage(MemoryHubDestination.storageKey) private var memoryDestinationRawValue =
    MemoryHubDestination.memories.rawValue
  @AppStorage("topBarNewSince") private var topBarNewSinceRaw: Double = 0

  init(
    navigation: ChatFirstShellNavigation,
    appState: AppState,
    viewModelContainer: ViewModelContainer,
    capability: ChatFirstCapabilityProjection?,
    selectedSettingsSection: Binding<SettingsContentView.SettingsSection>,
    highlightedSettingID: Binding<String?>
  ) {
    self.navigation = navigation
    self.appState = appState
    self.viewModelContainer = viewModelContainer
    self.capability = capability
    _selectedSettingsSection = selectedSettingsSection
    _highlightedSettingID = highlightedSettingID
    _automationRuntime = StateObject(
      wrappedValue: ChatFirstAutomationRuntime(
        navigation: navigation,
        goalsStore: viewModelContainer.canonicalGoalsStore,
        tasksStore: viewModelContainer.tasksStore,
        chatProvider: viewModelContainer.chatProvider
      )
    )
  }

  var body: some View {
    // No ground of its own — the window has none either (`ShellWindowChrome`), so the
    // panels below are the glass, and a scrim here would spend the passthrough budget twice.
    VStack(spacing: 0) {
      DesktopTopBar(
        selectedIndex: modernTopBarSelection,
        memoryDestinationRawValue: $memoryDestinationRawValue,
        appState: appState,
        memoriesViewModel: viewModelContainer.memoriesViewModel,
        tasksStore: viewModelContainer.tasksStore,
        sinceDate: topBarSinceDate
      )
      // Route-specific identity guarantees every semantic navigation change
      // mounts a fresh destination root and runs its visibility acknowledgement.
      // Without it, SwiftUI can structurally reuse compatible branches (notably
      // Home and More pages), leaving the automation contract stale even though
      // the requested route is selected.
      destination
        // Attached *inside* the identified subtree: a modifier above `.id` keeps
        // its identity across the replacement and never observes the outgoing
        // destination's disappearance.
        .onDisappear { ChatSwitchPerfLog.mark("oldDestinationGone") }
        .id(navigation.route.stableName)
    }
    // The top bar occupies the hidden title-bar band; the window's top edge is the glass.
    .padding(.top, GlassShell.titlebarClearance)
    .environmentObject(navigation)
    .onAppear {
      promptMaterializationCoordinator.activate(using: viewModelContainer.chatProvider)
      activateCapabilityGatedFeatures()
      automationRuntime.install()
      syncMemoryDestination(for: navigation.route)
      syncSettingsSection(for: navigation.route)
      AnalyticsManager.shared.chatFirst(
        .routeEntered(route: navigation.route.analyticsRoute, origin: .shellLaunch)
      )
    }
    .onDisappear { automationRuntime.uninstall() }
    // The capability resolves after the shell is already on screen, so the
    // gated features engage here rather than only at mount.
    .onChange(of: capability) { _, _ in activateCapabilityGatedFeatures() }
    .onChange(of: navigation.route) { _, route in
      syncMemoryDestination(for: route)
      syncSettingsSection(for: route)
    }
    .onChange(of: navigation.pendingFocus) { _, _ in
      syncMemoryDestination(for: navigation.route)
    }
    .onChange(of: navigation.pendingConversation?.id) { _, _ in
      syncMemoryDestination(for: navigation.route)
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopMeetingConversationDidComplete)) { _ in
      _ = promptMaterializationCoordinator.meetingConversationDidComplete(
        windowForeground: isMainWindowForeground
      )
    }
    .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationOpenMemoryAtlasRequested)) { _ in
      memoryDestinationRawValue = MemoryHubDestination.brainMap.rawValue
      navigation.selectPrimary(.memories)
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      guard let window = NSApp.mainWindow, window.isKeyWindow, window.isVisible else { return }
      promptMaterializationCoordinator.mainWindowDidBecomeForeground()
    }
    .onReceive(NotificationCenter.default.publisher(for: NSWindow.didBecomeKeyNotification)) { notification in
      guard let window = notification.object as? NSWindow,
        window === NSApp.mainWindow,
        window.isVisible
      else { return }
      promptMaterializationCoordinator.mainWindowDidBecomeForeground()
    }
    .onEscapeKey(priority: .navigation) {
      guard navigation.route != .chat else { return false }
      OmiMotion.withGated(.easeOut(duration: 0.12)) {
        _ = navigation.handleEscapeNavigation()
      }
      return true
    }
  }

  private func activateCapabilityGatedFeatures() {
    guard let capability else { return }
    viewModelContainer.canonicalGoalsStore.activate(capability: capability)
  }

  private var isMainWindowForeground: Bool {
    guard NSApp.isActive, let window = NSApp.mainWindow else { return false }
    return window.isKeyWindow && window.isVisible
  }

  @ViewBuilder
  private var destination: some View {
    ChatFirstPageGlassLane(route: navigation.route) {
      routeDestination
    }
  }

  @ViewBuilder
  private var routeDestination: some View {
    switch navigation.route {
    case .chat, .more(.dashboard):
      chatDestination
        .accessibilityIdentifier("chat-first-route-chat")
        .onAppear {
          ChatSwitchPerfLog.mark("chatRouteAppear")
          navigation.markRouteVisible(navigation.route)
          automationRuntime.registerChatPage(
            requestPromptMaterialization: {
              promptMaterializationCoordinator.mainWindowDidBecomeForeground()
            }
          )
        }
        .onDisappear { automationRuntime.unregisterChatPage() }
    case .conversations, .memories, .more(.rewind):
      memoryHubDestination
        .accessibilityIdentifier("chat-first-route-\(navigation.route.stableName)")
        .onAppear { navigation.markRouteVisible(navigation.route) }
        .task(id: pendingMemoryFocusID) { await resolvePendingMemoryFocus() }
    case .tasks:
      ChatFirstRestoredTasksHost(
        navigation: navigation,
        viewModel: viewModelContainer.tasksViewModel,
        tasksStore: viewModelContainer.tasksStore,
        chatProvider: viewModelContainer.chatProvider,
        chatCoordinator: viewModelContainer.taskChatCoordinator,
        automationRuntime: automationRuntime
      )
      .accessibilityIdentifier("chat-first-route-tasks")
      .onAppear { navigation.markRouteVisible(.tasks) }
    case .goals:
      ChatFirstGoalsPage(
        navigation: navigation,
        goalsStore: viewModelContainer.canonicalGoalsStore,
        tasksStore: viewModelContainer.tasksStore,
        chatProvider: viewModelContainer.chatProvider,
        automationRuntime: automationRuntime
      )
      .accessibilityIdentifier("chat-first-route-goals")
      .onAppear { navigation.markRouteVisible(.goals) }
    case .more(let page):
      moreDestination(page)
        .accessibilityIdentifier("chat-first-route-more-\(page.stableName)")
        .onAppear { navigation.markRouteVisible(.more(page)) }
    case .dailyRecap(let ref):
      DailyRecapPage(ref: ref, navigation: navigation)
        .accessibilityIdentifier("chat-first-route-daily-recap")
        .onAppear { navigation.markRouteVisible(navigation.route) }
    }
  }

  private var pendingMemoryFocusID: String? {
    guard case .memory(let id) = navigation.pendingFocus else { return nil }
    return id
  }

  private func resolvePendingMemoryFocus() async {
    guard case .memory(let id) = navigation.pendingFocus else { return }
    guard await viewModelContainer.memoriesViewModel.openMemory(id: id) else { return }
    guard
      let focus = ChatFirstMemoryFocusPolicy.focusToAcknowledge(
        pendingFocus: navigation.pendingFocus,
        visibleMemoryID: id
      )
    else { return }
    _ = navigation.acknowledgeFocus(focus)
  }

  private var topBarSinceDate: Date {
    topBarNewSinceRaw > 0 ? Date(timeIntervalSince1970: topBarNewSinceRaw) : Date()
  }

  private var chatDestination: some View {
    QueryShellHome(
      viewModel: viewModelContainer.dashboardViewModel,
      homeStatusStore: viewModelContainer.homeStatusStore,
      appState: appState,
      appProvider: viewModelContainer.appProvider,
      chatProvider: viewModelContainer.chatProvider,
      memoriesViewModel: viewModelContainer.memoriesViewModel,
      taskChatCoordinator: viewModelContainer.taskChatCoordinator,
      chatFirstRichBlockContext: richBlockContext
    )
  }

  private var memoryHubDestination: some View {
    ChatFirstMemoryHubHost(
      navigation: navigation,
      appState: appState,
      viewModelContainer: viewModelContainer,
      destinationRawValue: $memoryDestinationRawValue,
      onSelectDestination: selectHubDestination,
      automationRuntime: automationRuntime
    )
  }

  private var settingsDestination: some View {
    HStack(spacing: 0) {
      SettingsSidebar(
        selectedSection: $selectedSettingsSection,
        highlightedSettingId: $highlightedSettingID,
        onBack: { _ = navigation.handleEscapeNavigation() },
        appState: appState
      )
      SettingsPage(
        appState: appState,
        selectedSection: $selectedSettingsSection,
        highlightedSettingId: $highlightedSettingID,
        chatProvider: viewModelContainer.chatProvider
      )
    }
  }

  private var richBlockContext: ChatFirstRichBlockContext {
    ChatFirstRichBlockContext(
      navigation: navigation,
      tasksStore: viewModelContainer.tasksStore,
      chatProvider: viewModelContainer.chatProvider,
      canonicalGoalsStore: viewModelContainer.canonicalGoalsStore,
      promptMaterializationCoordinator: promptMaterializationCoordinator
    )
  }

  private var modernTopBarSelection: Binding<Int> {
    Binding(
      get: { ChatFirstModernNavigationPolicy.topBarIndex(for: navigation.route) },
      set: { rawValue in
        guard let route = ChatFirstModernNavigationPolicy.route(forTopBarIndex: rawValue) else {
          return
        }
        switch route {
        case .conversations:
          // The hub's one pill says `Brain`, so it opens the Brain spine — not whichever hub view
          // happened to be persisted last, and not the Conversations route this index maps back
          // from. Routing through the same writer the chip row uses keeps one path responsible for
          // moving both halves of the state.
          selectHubDestination(.activity)
        case .chat, .tasks, .memories, .goals:
          navigation.selectPrimary(route)
        case .more(let page):
          navigation.selectMore(page)
        case .dailyRecap:
          // Not reachable — `route(forTopBarIndex:)` never returns a recap —
          // and a recap is not a top-bar destination even if it were.
          return
        }
      }
    )
  }

  /// Applying a Memory hub selection here moves **both** halves of this shell's state: the persisted
  /// hub destination and the typed route that decides which host is mounted. Writing only the first
  /// leaves the shell rendering Conversations while it believes it is on Memories.
  private func selectHubDestination(_ destination: MemoryHubDestination) {
    memoryDestinationRawValue = destination.rawValue
    navigation.selectPrimary(MemoryHubSelectionPolicy.chatFirstRoute(for: destination))
  }

  private func syncMemoryDestination(for route: ChatFirstRoute) {
    if route == .more(.rewind) {
      memoryDestinationRawValue = MemoryHubDestination.rewind.rawValue
      return
    }
    if route == .conversations || navigation.pendingConversation != nil {
      memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue
      return
    }
    if case .capture = navigation.pendingFocus {
      memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue
      return
    }
    if route == .memories, case .memory = navigation.pendingFocus {
      memoryDestinationRawValue = MemoryHubDestination.memories.rawValue
      return
    }
    guard
      let destination = ChatFirstMemoryRoutePolicy.destination(
        afterSelecting: route,
        current: MemoryHubDestination(rawValue: memoryDestinationRawValue) ?? .memories
      )
    else {
      return
    }
    memoryDestinationRawValue = destination.rawValue
  }

  private func syncSettingsSection(for route: ChatFirstRoute) {
    guard route == .more(.permissions) else { return }
    selectedSettingsSection = .permissions
  }

  @ViewBuilder
  private func moreDestination(_ page: ChatFirstMorePage) -> some View {
    switch page {
    case .dashboard:
      chatDestination
    case .rewind:
      memoryHubDestination
    case .apps:
      ChatFirstAppsHost(
        appProvider: viewModelContainer.appProvider,
        appState: appState,
        connectorStatusStore: viewModelContainer.homeStatusStore.connectorStatusStore,
        handlesAutomationPresentations: viewModelContainer.isInitialLoadComplete
      )
    case .permissions, .settings:
      settingsDestination
    }
  }

}

/// Chat-first passes through every destination that owns search/content panels. Older single-panel
/// destinations receive the shared lane exactly once at the shell boundary.
enum ChatFirstPageGlassLanePolicy {
  static func shouldWrap(_ route: ChatFirstRoute) -> Bool {
    switch route {
    case .chat, .conversations, .memories, .more(.dashboard), .more(.rewind):
      return false
    case .tasks, .more(.apps):
      return false
    case .goals, .more(.permissions), .more(.settings), .dailyRecap:
      return true
    }
  }

}

/// Applies Chat-first's glass decision without translating it through the legacy sidebar policy.
///
/// The legacy Conversations index is also the Memory-hub index. Translating `.conversations` to that
/// index and asking `PageGlassLane` to decide again let a persisted hub destination turn a required
/// panel into pass-through. This component makes the modern route policy the single authority and
/// hands its "shared" answer to the unconditional panel.
struct ChatFirstPageGlassLane<Content: View>: View {
  let route: ChatFirstRoute
  @ViewBuilder var content: () -> Content

  var body: some View {
    if ChatFirstPageGlassLanePolicy.shouldWrap(route) {
      PageGlassLanePanel(content: content)
    } else {
      content()
    }
  }
}

/// Keeps the navigation response responsive while the marketplace's relatively
/// expensive catalog grid is composed. The route mounts a small loading surface
/// first, then yields one frame before constructing the existing AppsPage.
private struct ChatFirstAppsHost: View {
  @ObservedObject var appProvider: AppProvider
  let appState: AppState
  @ObservedObject var connectorStatusStore: ImportConnectorStatusStore
  let handlesAutomationPresentations: Bool
  @State private var hasPresentedCatalog = false

  var body: some View {
    Group {
      if hasPresentedCatalog {
        AppsPage(
          appProvider: appProvider,
          appState: appState,
          connectorStatusStore: connectorStatusStore,
          handlesAutomationPresentations: handlesAutomationPresentations
        )
      } else {
        TransparentWindowStatusPanel {
          VStack(spacing: OmiSpacing.md) {
            ProgressView().controlSize(.small)
            Text("Loading apps…")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundStyle(Ink.secondary)
          }
        }
      }
    }
    .task {
      // Give the loading surface one render pass before the catalog materializes.
      try? await Task.sleep(nanoseconds: 100_000_000)
      hasPresentedCatalog = true
    }
  }
}

enum ChatFirstMemoryRoutePolicy {
  static func destination(
    afterSelecting route: ChatFirstRoute,
    current: MemoryHubDestination
  ) -> MemoryHubDestination? {
    switch route {
    case .memories:
      // Every hub view that *lives* on the memory route survives the transition. This used to
      // whitelist `.brainMap` by name, so when `.activity` was added as a fourth hub view the
      // route sync silently rewrote it back to `.memories` — the click landed on Memories no
      // matter which view you asked for. Deriving the answer from the one route mapping keeps
      // the sync and the selection from drifting apart again.
      return MemoryHubSelectionPolicy.chatFirstRoute(for: current) == .memories ? current : .memories
    case .conversations:
      return .conversations
    default:
      return nil
    }
  }
}

/// Adapts typed focus and automation to the one Memory hub. It never owns a
/// second Conversations, Memories, or Rewind presentation.
@MainActor
private struct ChatFirstMemoryHubHost: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  @Binding var destinationRawValue: Int
  let onSelectDestination: (MemoryHubDestination) -> Void
  let automationRuntime: ChatFirstAutomationRuntime?
  @StateObject private var captureRepository = CaptureArchiveRepository()
  @State private var visibleConversation: ServerConversation?

  private var pendingCaptureToken: String {
    guard case .capture(let id, let momentTimestamp) = navigation.pendingFocus else { return "none" }
    let moment = momentTimestamp.map { String($0) } ?? ""
    return "\(id):\(moment)"
  }

  var body: some View {
    MemoryHubPage(
      appState: appState,
      viewModelContainer: viewModelContainer,
      memoriesViewModel: viewModelContainer.memoriesViewModel,
      destinationRawValue: $destinationRawValue,
      onSelectDestination: onSelectDestination,
      onOpenConversationRecord: { conversation in
        destinationRawValue = MemoryHubDestination.conversations.rawValue
        navigation.open(conversation: conversation, destination: .memories)
      },
      initialConversation: navigation.pendingConversation ?? captureRepository.selectedCapture,
      initialCaptureMomentTimestamp: captureMoment,
      onCaptureFocusResolved: acknowledgeCaptureFocus,
      onDiscussInChat: { conversation in
        navigation.stageCaptureReference(conversation, using: viewModelContainer.chatProvider)
      },
      onOpenLinkedTask: { taskID in
        navigation.open(focus: .task(id: taskID))
      },
      onConversationSelectionChanged: { visibleConversation = $0 }
    )
    .task(id: pendingCaptureToken) {
      await resolvePendingCaptureFocusIfNeeded()
    }
    .onAppear { registerAutomationActions() }
    .onDisappear { automationRuntime?.unregisterCapturePage() }
  }

  private var captureMoment: TimeInterval? {
    guard let conversation = navigation.pendingConversation ?? captureRepository.selectedCapture else {
      return nil
    }
    return CaptureConversationFocusRoutingPolicy.initialMoment(
      for: navigation.pendingFocus,
      conversationID: conversation.id
    )
  }

  private func resolvePendingCaptureFocusIfNeeded() async {
    guard case .capture(let id, _) = navigation.pendingFocus else { return }
    captureRepository.clearSelection()
    _ = await captureRepository.loadDetail(id: id)
  }

  private func acknowledgeCaptureFocus(_ didResolve: Bool) {
    guard let conversation = visibleConversation,
      let focus = CaptureConversationFocusRoutingPolicy.resolvedFocus(
        for: navigation.pendingFocus,
        conversationID: conversation.id,
        didResolve: didResolve
      )
    else { return }
    _ = navigation.acknowledgeFocus(focus)
  }

  private func registerAutomationActions() {
    automationRuntime?.registerCapturePage(
      openCapture: {
        await captureRepository.loadInitial()
        guard let capture = captureRepository.captures.first else { return false }
        captureRepository.select(capture)
        let detail = await captureRepository.loadDetail(id: capture.id)
        return detail != nil || captureRepository.selectedCapture?.id == capture.id
      },
      discussCapture: {
        guard let conversation = visibleConversation, conversation.source == .omi else { return false }
        navigation.stageCaptureReference(conversation, using: viewModelContainer.chatProvider)
        return true
      },
      detailIsVisible: {
        visibleConversation?.source == .omi
      }
    )
  }
}

/// The mature Tasks page remains the sole owner of editing, drag/reorder,
/// nesting, keyboard, suggested-task, and task-thread behavior. This adapter
/// carries only chat-first routing and automation state.
@MainActor
private struct ChatFirstRestoredTasksHost: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  @ObservedObject var viewModel: TasksViewModel
  @ObservedObject var tasksStore: TasksStore
  let chatProvider: ChatProvider
  let chatCoordinator: TaskChatCoordinator
  let automationRuntime: ChatFirstAutomationRuntime?

  private var pendingFocusToken: String {
    switch navigation.pendingFocus {
    case .task(let id): return "task:\(id)"
    case .goal(let id): return "goal:\(id)"
    default: return "none"
    }
  }

  var body: some View {
    TasksPage(
      viewModel: viewModel,
      chatCoordinator: chatCoordinator,
      chatProvider: chatProvider,
      onOpenRewindEvidence: { screenshotID in
        RewindCitationFocusState.shared.request(screenshotID)
        navigation.selectMore(.rewind)
      }
    )
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .task(id: pendingFocusToken) {
      await viewModel.loadTasksForFirstUse()
      switch navigation.pendingFocus {
      case .task(let id):
        guard let task = await taskForFocus(id: id) else { return }
        await reveal(task, acknowledging: .task(id: id))
      case .goal(let id):
        var task = tasksStore.tasks.first(where: { $0.goalId == id && !$0.isRetired })
        if task == nil {
          await tasksStore.loadCompletedTasks()
          task = tasksStore.tasks.first(where: { $0.goalId == id && !$0.isRetired })
        }
        if task == nil,
          let detail = try? await APIClient.shared.getCanonicalGoalDetail(goalID: id),
          let relatedTaskID = detail.tasks.first?.id
        {
          task = await taskForFocus(id: relatedTaskID)
        }
        guard let task else { return }
        await reveal(task, acknowledging: .goal(id: id))
      default:
        return
      }
    }
    .onAppear { registerAutomationActions() }
    .onDisappear { automationRuntime?.unregisterTasksPage() }
  }

  private func taskForFocus(id: String) async -> TaskActionItem? {
    if let task = tasksStore.tasks.first(where: { $0.id == id && !$0.isRetired }) {
      return task
    }
    // Straight off the wire, so legacy `deleted` may be absent and retirement
    // only stated through canonical lifecycle status. Cache reads above and
    // below are already normalized (`ActionItemRecord.from` stores `isRetired`).
    if let task = try? await APIClient.shared.getActionItem(id: id), !task.isRetired {
      return task
    }
    await tasksStore.loadCompletedTasks()
    return tasksStore.tasks.first(where: { $0.id == id && !$0.isRetired })
  }

  private func reveal(_ task: TaskActionItem, acknowledging focus: ChatFirstPendingFocus) async {
    viewModel.revealTaskForNavigation(task)
    await Task.yield()
    guard viewModel.displayTasks.contains(where: { $0.id == task.id }) else { return }
    viewModel.keyboardSelectedTaskId = task.id
    guard await waitForScrollProxy(timeoutMs: 1_500) else { return }
    guard let scrollProxy = viewModel.scrollProxy else { return }
    scrollProxy.scrollTo(task.id, anchor: .center)
    try? await Task.sleep(nanoseconds: 100_000_000)
    guard !Task.isCancelled, viewModel.keyboardSelectedTaskId == task.id else { return }
    _ = navigation.acknowledgeFocus(focus)
  }

  /// Poll until TasksPage mounts and assigns its ScrollViewReader proxy.
  private func waitForScrollProxy(timeoutMs: Int) async -> Bool {
    if viewModel.scrollProxy != nil { return true }
    let steps = max(1, timeoutMs / 50)
    for _ in 0..<steps {
      guard !Task.isCancelled else { return false }
      try? await Task.sleep(nanoseconds: 50_000_000)
      if viewModel.scrollProxy != nil { return true }
    }
    return viewModel.scrollProxy != nil
  }

  private func registerAutomationActions() {
    automationRuntime?.registerTasksPage(
      toggleTask: {
        guard let task = tasksStore.tasks.first(where: { !$0.isRetired && !$0.completed }) else {
          return false
        }
        let intendedCompletion = !task.completed
        AnalyticsManager.shared.chatFirst(.taskMutation(lifecycle: .attempt, mutation: .completion))
        await tasksStore.toggleTask(task)
        let reconciled = tasksStore.tasks.first { $0.id == task.id && !$0.isRetired }
        AnalyticsManager.shared.chatFirst(
          .taskMutation(
            lifecycle: reconciled?.completed == intendedCompletion ? .success : .rollback,
            mutation: .completion
          )
        )
        return reconciled?.completed == intendedCompletion
      }
    )
  }
}

/// Bridges the typed Chat-first routes to the four primary destinations exposed
/// by the modern top bar. Chat remains Home in this shell; Goals and secondary
/// destinations keep their route while the bar stays on the nearest primary.
enum ChatFirstModernNavigationPolicy {
  static func topBarIndex(for route: ChatFirstRoute) -> Int {
    switch route {
    case .chat, .goals, .dailyRecap: return SidebarNavItem.dashboard.rawValue
    case .conversations, .memories: return SidebarNavItem.conversations.rawValue
    case .tasks: return SidebarNavItem.tasks.rawValue
    case .more(let page):
      switch page {
      case .apps: return SidebarNavItem.apps.rawValue
      case .settings: return SidebarNavItem.settings.rawValue
      case .rewind: return SidebarNavItem.conversations.rawValue
      default: return SidebarNavItem.dashboard.rawValue
      }
    }
  }

  static func route(forTopBarIndex rawValue: Int) -> ChatFirstRoute? {
    switch SidebarNavItem(rawValue: rawValue) {
    case .dashboard: return .chat
    case .conversations: return .conversations
    case .tasks: return .tasks
    case .apps: return .more(.apps)
    case .settings: return .more(.settings)
    case .rewind: return .memories
    default: return nil
    }
  }
}

enum ChatFirstMemoryFocusPolicy {
  static func focusToAcknowledge(
    pendingFocus: ChatFirstPendingFocus?,
    visibleMemoryID: String
  ) -> ChatFirstPendingFocus? {
    guard case .memory(let memoryID) = pendingFocus, memoryID == visibleMemoryID else { return nil }
    return pendingFocus
  }
}

private struct ChatFirstDeferredDestination: View {
  let title: String
  let message: String

  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: "target")
        .scaledFont(size: 36, weight: .medium)
        .foregroundStyle(Ink.secondary)
      Text(title)
        .scaledFont(size: OmiType.title, weight: .bold)
        .foregroundStyle(Ink.primary)
      Text(message)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(Ink.secondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}
