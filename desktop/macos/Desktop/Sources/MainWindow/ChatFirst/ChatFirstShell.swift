import AppKit
import OmiTheme
import SwiftUI

/// Cohort-only main-window shell. It shares the existing data owners with the
/// legacy shell but owns no second chat state, task state, or navigation index.
struct ChatFirstShell: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  @ObservedObject var appState: AppState
  let viewModelContainer: ViewModelContainer
  let capability: ChatFirstCapabilityProjection
  @Binding var selectedSettingsSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingID: String?
  @StateObject private var promptMaterializationCoordinator = ChatFirstPromptMaterializationCoordinator()
  @StateObject private var automationRuntime: ChatFirstAutomationRuntime
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
    ZStack {
      RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
        .fill(OmiColors.backgroundPrimary)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
            .stroke(OmiColors.border.opacity(0.3), lineWidth: 1)
        )

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
        destination
      }
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous))
    }
    .padding(OmiSpacing.md)
    .background(OmiColors.backgroundPrimary)
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
    .onExitCommand {
      guard navigation.route != .chat else { return }
      OmiMotion.withGated(.easeOut(duration: 0.12)) {
        navigation.selectPrimary(.chat)
      }
    }
  }

  @ViewBuilder
  private var destination: some View {
    switch navigation.route {
    case .chat:
      ChatPage(
        appProvider: viewModelContainer.appProvider,
        chatProvider: viewModelContainer.chatProvider,
        chatFirstRichBlockContext: ChatFirstRichBlockContext(
          navigation: navigation,
          tasksStore: viewModelContainer.tasksStore,
          chatProvider: viewModelContainer.chatProvider,
          canonicalGoalsStore: viewModelContainer.canonicalGoalsStore,
          promptMaterializationCoordinator: promptMaterializationCoordinator
        )
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
      CaptureArchivePage(
        navigation: navigation,
        chatProvider: viewModelContainer.chatProvider,
        automationRuntime: automationRuntime
      )
      .accessibilityIdentifier("chat-first-route-conversations")
      .onAppear { navigation.markRouteVisible(.conversations) }
    case .tasks:
      ChatFirstTasksPage(
        navigation: navigation,
        tasksStore: viewModelContainer.tasksStore,
        chatProvider: viewModelContainer.chatProvider,
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
      MemoriesPage(viewModel: viewModelContainer.memoriesViewModel)
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

  private var modernTopBarSelection: Binding<Int> {
    Binding(
      get: { ChatFirstModernNavigationPolicy.topBarIndex(for: navigation.route) },
      set: { rawValue in
        if rawValue == SidebarNavItem.conversations.rawValue {
          let destination =
            MemoryHubDestination(rawValue: memoryDestinationRawValue) ?? .memories
          navigation.selectPrimary(destination == .conversations ? .conversations : .memories)
          return
        }
        guard let route = ChatFirstModernNavigationPolicy.route(forTopBarIndex: rawValue) else {
          return
        }
        switch route {
        case .chat, .conversations, .tasks, .memories, .goals:
          navigation.selectPrimary(route)
        case .more(let page):
          navigation.selectMore(page)
        }
      }
    )
  }

  private func syncMemoryDestination(for route: ChatFirstRoute) {
    switch route {
    case .memories:
      memoryDestinationRawValue = MemoryHubDestination.memories.rawValue
    case .conversations:
      memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue
    default:
      break
    }
  }

  @ViewBuilder
  private func moreDestination(_ page: ChatFirstMorePage) -> some View {
    switch page {
    case .dashboard:
      DashboardPage(
        viewModel: viewModelContainer.dashboardViewModel,
        homeStatusStore: viewModelContainer.homeStatusStore,
        appState: appState,
        appProvider: viewModelContainer.appProvider,
        chatProvider: viewModelContainer.chatProvider,
        memoriesViewModel: viewModelContainer.memoriesViewModel,
        taskChatCoordinator: viewModelContainer.taskChatCoordinator,
        onOpenPrimaryChat: {
          navigation.selectPrimary(.chat)
        },
        selectedIndex: legacySelectionBinding
      )
    case .focus:
      FocusPage()
    case .insight:
      InsightPage()
    case .rewind:
      RewindPage(appState: appState)
    case .apps:
      AppsPage(
        appProvider: viewModelContainer.appProvider,
        appState: appState,
        connectorStatusStore: viewModelContainer.homeStatusStore.connectorStatusStore,
        handlesAutomationPresentations: viewModelContainer.isInitialLoadComplete
      )
    case .permissions:
      PermissionsPage(appState: appState)
    case .help:
      HelpPage()
    case .settings:
      SettingsPage(
        appState: appState,
        selectedSection: $selectedSettingsSection,
        highlightedSettingId: $highlightedSettingID,
        chatProvider: viewModelContainer.chatProvider
      )
    }
  }

  /// Existing Dashboard callbacks still speak in legacy sidebar items. Keep
  /// that compatibility at this one boundary while the cohort shell itself is
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
    case .chat: return .chat
    case .conversations: return .conversations
    case .tasks: return .tasks
    case .memories: return .memories
    case .goals: return .dashboard
    case .more(let page):
      switch page {
      case .dashboard: return .dashboard
      case .focus: return .focus
      case .insight: return .insight
      case .rewind: return .rewind
      case .apps: return .apps
      case .permissions: return .permissions
      case .help: return .help
      case .settings: return .settings
      }
    }
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
        .foregroundStyle(OmiColors.textTertiary)
      Text(title)
        .scaledFont(size: OmiType.title, weight: .bold)
        .foregroundStyle(OmiColors.textPrimary)
      Text(message)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(OmiColors.textSecondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(OmiColors.backgroundPrimary)
  }
}
