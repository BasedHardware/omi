import AppKit
import OmiTheme
import SwiftUI

/// Universal main-window shell. It shares the existing data owners with the
/// legacy shell but owns no second chat state, task state, or navigation index.
struct ChatFirstShell: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  let appState: AppState
  let viewModelContainer: ViewModelContainer
  let capability: ChatFirstCapabilityProjection
  @Binding var selectedSettingsSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingID: String?
  @StateObject private var promptMaterializationCoordinator = ChatFirstPromptMaterializationCoordinator()
  @StateObject private var automationRuntime: ChatFirstAutomationRuntime
  @State private var conversationsSelectionGeneration = 0
  @AppStorage(MemoryHubDestination.storageKey) private var memoryDestinationRawValue =
    MemoryHubDestination.memories.rawValue
  @AppStorage("topBarNewSince") private var topBarNewSinceRaw: Double = 0

  init(
    navigation: ChatFirstShellNavigation,
    appState: AppState,
    viewModelContainer: ViewModelContainer,
    capability: ChatFirstCapabilityProjection,
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
        sinceDate: topBarSinceDate,
        onRewind: {
          navigation.selectMore(.rewind)
        }
      )
      // Route-specific identity guarantees every semantic navigation change
      // mounts a fresh destination root and runs its visibility acknowledgement.
      // Without it, SwiftUI can structurally reuse compatible branches (notably
      // Home and More pages), leaving the automation contract stale even though
      // the requested route is selected.
      destination
        .id(navigation.route.stableName)
    }
    // The top bar occupies the hidden title-bar band; the window's top edge is the glass.
    .padding(.top, GlassShell.titlebarClearance)
    .environmentObject(navigation)
    .onAppear {
      promptMaterializationCoordinator.activate(using: viewModelContainer.chatProvider)
      viewModelContainer.canonicalGoalsStore.activate(capability: capability)
      automationRuntime.install()
      syncMemoryDestination(for: navigation.route)
      AnalyticsManager.shared.chatFirst(
        .routeEntered(route: navigation.route.analyticsRoute, origin: .shellLaunch)
      )
    }
    .onDisappear { automationRuntime.uninstall() }
    .onChange(of: navigation.route) { _, route in
      syncMemoryDestination(for: route)
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

  private var isMainWindowForeground: Bool {
    guard NSApp.isActive, let window = NSApp.mainWindow else { return false }
    return window.isKeyWindow && window.isVisible
  }

  @ViewBuilder
  private var destination: some View {
    if ChatFirstPageGlassLanePolicy.shouldWrap(
      navigation.route, memoryDestinationRawValue: memoryDestinationRawValue)
    {
      PageGlassLane(
        selectedIndex: ChatFirstPageGlassLanePolicy.pageGlassLaneIndex(for: navigation.route),
        memoryDestinationRawValue: memoryDestinationRawValue,
        homeOwnsItsPanels: HomeDesignPresentation.queryShellOwnsItsPanels(
          useLegacyHomeDesign: true,
          forceModernPresentation: true)
      ) {
        routeDestination
      }
    } else {
      routeDestination
    }
  }

  @ViewBuilder
  private var routeDestination: some View {
    switch navigation.route {
    case .chat:
      QueryShellHome(
        viewModel: viewModelContainer.dashboardViewModel,
        homeStatusStore: viewModelContainer.homeStatusStore,
        appState: appState,
        appProvider: viewModelContainer.appProvider,
        chatProvider: viewModelContainer.chatProvider,
        memoriesViewModel: viewModelContainer.memoriesViewModel,
        taskChatCoordinator: viewModelContainer.taskChatCoordinator,
        forceModernPresentation: true,
        chatFirstRichBlockContext: richBlockContext,
        selectedIndex: legacySelectionBinding
      )
      .accessibilityIdentifier("chat-first-route-chat")
      .onAppear {
        navigation.markRouteVisible(.chat)
        automationRuntime.registerChatPage(
          requestPromptMaterialization: {
            promptMaterializationCoordinator.mainWindowDidBecomeForeground()
          }
        )
      }
      .onDisappear { automationRuntime.unregisterChatPage() }
    case .conversations:
      // No switcher here either. Every hub page is reached from Activity's chip row, and the
      // `Activity` pill in the top bar is always one click away from this route, so the siblings
      // are two clicks out rather than stranded (INV-NAV-1, `ShellDestination.reach`).
      VStack(alignment: .leading, spacing: 0) {
        HStack {
          ActivityBackButton { selectHubDestination(.activity) }
          Spacer(minLength: 0)
        }
        .padding(.top, 18)
        .padding(.horizontal, 28)
        .padding(.bottom, 6)
        ChatFirstConversationsHost(
          navigation: navigation,
          appState: appState,
          chatProvider: viewModelContainer.chatProvider,
          automationRuntime: automationRuntime,
          explicitSelectionGeneration: conversationsSelectionGeneration
        )
      }
      .accessibilityIdentifier("chat-first-route-conversations")
      .onAppear { navigation.markRouteVisible(.conversations) }
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
    case .memories:
      MemoryHubPage(
        appState: appState,
        viewModelContainer: viewModelContainer,
        memoriesViewModel: viewModelContainer.memoriesViewModel,
        destinationRawValue: $memoryDestinationRawValue,
        onSelectDestination: selectHubDestination,
        // The Activity spine's screenshot rows leave for Rewind through the
        // shell that owns the route — without this the rows are inert here.
        onOpenRewind: { navigation.selectMore(.rewind) },
        // The typed deep link, so a conversation opened from Activity arrives at the Conversations
        // host as a record rather than as an id the host has to find again. `selectPrimary` — what
        // the spine used to call — is the tab-selection primitive and drops pending records by
        // design, which is why the click landed on the list.
        onOpenConversationRecord: { navigation.open(conversation: $0) }
      )
      .accessibilityIdentifier("chat-first-route-memories")
      .onAppear { navigation.markRouteVisible(.memories) }
      .task(id: pendingMemoryFocusID) { await resolvePendingMemoryFocus() }
    case .more(let page):
      moreDestination(page)
        .accessibilityIdentifier("chat-first-route-more-\(page.stableName)")
        .onAppear { navigation.markRouteVisible(.more(page)) }
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
        }
      }
    )
  }

  /// Applying a Memory hub selection here moves **both** halves of this shell's state: the persisted
  /// hub destination and the typed route that decides which host is mounted. Writing only the first
  /// leaves the shell rendering Conversations while it believes it is on Memories.
  private func selectHubDestination(_ destination: MemoryHubDestination) {
    memoryDestinationRawValue = destination.rawValue
    if destination == .conversations {
      conversationsSelectionGeneration &+= 1
    }
    navigation.selectPrimary(MemoryHubSelectionPolicy.chatFirstRoute(for: destination))
  }

  private func syncMemoryDestination(for route: ChatFirstRoute) {
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

  @ViewBuilder
  private func moreDestination(_ page: ChatFirstMorePage) -> some View {
    switch page {
    case .dashboard:
      // Keep the persisted legacy route as a compatibility alias, but render the canonical modern
      // Home surface so a dashboard deep link can never introduce a second chat/composer/transcript.
      QueryShellHome(
        viewModel: viewModelContainer.dashboardViewModel,
        homeStatusStore: viewModelContainer.homeStatusStore,
        appState: appState,
        appProvider: viewModelContainer.appProvider,
        chatProvider: viewModelContainer.chatProvider,
        memoriesViewModel: viewModelContainer.memoriesViewModel,
        taskChatCoordinator: viewModelContainer.taskChatCoordinator,
        forceModernPresentation: true,
        chatFirstRichBlockContext: richBlockContext,
        selectedIndex: legacySelectionBinding
      )
    case .rewind:
      ChatFirstRewindHost(appState: appState)
    case .apps:
      ChatFirstAppsHost(
        appProvider: viewModelContainer.appProvider,
        appState: appState,
        connectorStatusStore: viewModelContainer.homeStatusStore.connectorStatusStore,
        handlesAutomationPresentations: viewModelContainer.isInitialLoadComplete
      )
    case .permissions:
      PermissionsPage(appState: appState)
    case .settings:
      HStack(spacing: 0) {
        SettingsSidebar(
          selectedSection: $selectedSettingsSection,
          highlightedSettingId: $highlightedSettingID,
          onBack: {
            _ = navigation.handleEscapeNavigation()
          },
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
  }

  /// Existing Dashboard callbacks still speak in legacy sidebar items. Keep
  /// that compatibility at this one boundary while the Chat-first shell itself is
  /// entirely route-typed.
  private var legacySelectionBinding: Binding<Int> {
    Binding(
      get: { legacySidebarItem(for: navigation.route).rawValue },
      set: { rawValue in
        guard let item = SidebarNavItem(rawValue: rawValue) else { return }
        navigation.selectLegacyDestination(item)
      }
    )
  }

  private func legacySidebarItem(for route: ChatFirstRoute) -> SidebarNavItem {
    switch route {
    case .chat: return .dashboard
    case .conversations: return .conversations
    case .tasks: return .tasks
    case .memories: return .memories
    case .goals: return .dashboard
    case .more(let page):
      switch page {
      case .dashboard: return .dashboard
      case .rewind: return .rewind
      case .apps: return .apps
      case .permissions: return .permissions
      case .settings: return .settings
      }
    }
  }
}

/// Chat-first keeps Home and Rewind as self-contained surfaces. All other mounted destinations
/// receive the existing shared lane exactly once at the shell boundary.
enum ChatFirstPageGlassLanePolicy {
  static func shouldWrap(_ route: ChatFirstRoute, memoryDestinationRawValue: Int? = nil) -> Bool {
    switch route {
    case .chat, .more(.dashboard), .more(.rewind):
      return false
    case .memories:
      // The memory route mounts the hub, and Activity is the one hub page that builds Home's own
      // two panels. Wrapping it puts glass inside glass and doubles the scrim.
      return MemoryHubDestination(rawValue: memoryDestinationRawValue ?? -1) != .activity
    case .conversations, .tasks, .goals,
      .more(.apps), .more(.permissions), .more(.settings):
      return true
    }
  }

  /// `PageGlassLane` uses this legacy index only to select its shared-panel branch. Goals has no
  /// legacy sidebar item, so its closest existing non-owning list-page index is used.
  static func pageGlassLaneIndex(for route: ChatFirstRoute) -> Int {
    switch route {
    case .chat, .more(.dashboard): return SidebarNavItem.dashboard.rawValue
    case .conversations: return SidebarNavItem.conversations.rawValue
    case .tasks, .goals: return SidebarNavItem.tasks.rawValue
    case .memories: return SidebarNavItem.memories.rawValue
    case .more(.rewind): return SidebarNavItem.rewind.rawValue
    case .more(.apps): return SidebarNavItem.apps.rawValue
    case .more(.permissions): return SidebarNavItem.permissions.rawValue
    case .more(.settings): return SidebarNavItem.settings.rawValue
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
        VStack(spacing: OmiSpacing.md) {
          ProgressView().controlSize(.small)
          Text("Loading apps…")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundStyle(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .task {
      // Give the loading surface one render pass before the catalog materializes.
      try? await Task.sleep(nanoseconds: 100_000_000)
      hasPresentedCatalog = true
    }
  }
}

/// Rewind still consumes live AppState values for permission, recording, and
/// speaker projections. Keep that observation inside the mounted destination
/// so the shell itself can remain isolated from unrelated AppState publishes.
@MainActor
private struct ChatFirstRewindHost: View {
  @ObservedObject var appState: AppState

  var body: some View {
    RewindPage(appState: appState)
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

/// The chat-first shell changes chrome, not destination capability. Keep the
/// established Conversations page as the one feature owner and adapt only its
/// typed route/deep-link and non-production automation contracts here.
@MainActor
private struct ChatFirstConversationsHost: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  let appState: AppState
  let chatProvider: ChatProvider
  let automationRuntime: ChatFirstAutomationRuntime?
  let explicitSelectionGeneration: Int
  @State private var showsCaptureArchive = false

  private var pendingCaptureToken: String {
    guard case .capture(let id, let momentTimestamp) = navigation.pendingFocus else { return "none" }
    let moment = momentTimestamp.map { String($0) } ?? ""
    return "\(id):\(moment)"
  }

  var body: some View {
    Group {
      if showsCaptureArchive || pendingCaptureToken != "none" {
        // Capture links retain their specialized playback/timestamp owner;
        // ordinary Conversations navigation uses the established full editor.
        CaptureArchivePage(
          navigation: navigation,
          chatProvider: chatProvider,
          automationRuntime: automationRuntime
        )
      } else {
        ConversationsPageHost(
          appState: appState,
          initialConversation: navigation.pendingConversation
        )
      }
    }
    .onAppear {
      if pendingCaptureToken != "none" { showsCaptureArchive = true }
    }
    .onChange(of: pendingCaptureToken) { _, token in
      if token != "none" { showsCaptureArchive = true }
    }
    .onChange(of: explicitSelectionGeneration) { _, _ in
      showsCaptureArchive = false
    }
    // **The latch had no second release.** Once any capture link was followed, `showsCaptureArchive`
    // stayed true until a tab was explicitly re-selected, so "open this exact conversation" kept
    // landing in the archive's reduced pane — which reads its own summary and never consumes a
    // pending record. An exact conversation is precisely the "ordinary Conversations navigation"
    // the branch above promises the full editor to, so it releases the latch.
    .onChange(of: navigation.pendingConversation?.id) { _, id in
      if id != nil { showsCaptureArchive = false }
    }
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
      chatProvider: chatProvider
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
    case .chat, .goals: return SidebarNavItem.dashboard.rawValue
    case .conversations, .memories: return SidebarNavItem.conversations.rawValue
    case .tasks: return SidebarNavItem.tasks.rawValue
    case .more(let page):
      switch page {
      case .apps: return SidebarNavItem.apps.rawValue
      case .settings: return SidebarNavItem.settings.rawValue
      case .rewind: return SidebarNavItem.rewind.rawValue
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
    case .rewind: return .more(.rewind)
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
