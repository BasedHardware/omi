import AppKit
import SwiftUI
import OmiTheme

/// Cohort-only main-window shell. It shares the existing data owners with the
/// legacy shell but owns no second chat state, task state, or navigation index.
struct ChatFirstShell: View {
  @ObservedObject var navigation: ChatFirstShellNavigation
  @ObservedObject var appState: AppState
  let viewModelContainer: ViewModelContainer
  @Binding var selectedSettingsSection: SettingsContentView.SettingsSection
  @Binding var highlightedSettingID: String?
  @StateObject private var promptMaterializationCoordinator = ChatFirstPromptMaterializationCoordinator()

  var body: some View {
    HStack(spacing: 0) {
      ChatFirstSidebar(navigation: navigation)

      ZStack {
        RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
          .fill(OmiColors.backgroundPrimary)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous)
              .stroke(OmiColors.border.opacity(0.3), lineWidth: 1)
          )

        destination
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.windowRadius, style: .continuous))
      }
      .padding(OmiSpacing.md)
    }
    .background(OmiColors.backgroundPrimary)
    .environmentObject(navigation)
    .onAppear {
      promptMaterializationCoordinator.activate(using: viewModelContainer.chatProvider)
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
          promptMaterializationCoordinator: promptMaterializationCoordinator
        )
      )
      .accessibilityIdentifier("chat-first-route-chat")
    case .conversations:
      CaptureArchivePage(
        navigation: navigation,
        chatProvider: viewModelContainer.chatProvider
      )
        .accessibilityIdentifier("chat-first-route-conversations")
    case .tasks:
      ChatFirstTasksPage(
        navigation: navigation,
        tasksStore: viewModelContainer.tasksStore,
        chatProvider: viewModelContainer.chatProvider
      )
      .accessibilityIdentifier("chat-first-route-tasks")
    case .goals:
      ChatFirstDeferredDestination(
        title: "Goals",
        message: "Your canonical goals will appear here."
      )
      .accessibilityIdentifier("chat-first-route-goals")
    case .memories:
      MemoriesPage(
        viewModel: viewModelContainer.memoriesViewModel,
        graphViewModel: viewModelContainer.memoryGraphViewModel
      )
      .accessibilityIdentifier("chat-first-route-memories")
    case .more(let page):
      moreDestination(page)
        .accessibilityIdentifier("chat-first-route-more-\(page.stableName)")
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

private struct ChatFirstSidebar: View {
  @ObservedObject var navigation: ChatFirstShellNavigation

  private let expandedWidth: CGFloat = 228
  private let collapsedWidth: CGFloat = 68

  private var width: CGFloat {
    navigation.isSidebarCollapsed ? collapsedWidth : expandedWidth
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "circle.fill")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(OmiColors.textPrimary)
          .accessibilityHidden(true)

        if !navigation.isSidebarCollapsed {
          Text("Omi")
            .scaledFont(size: OmiType.heading, weight: .bold)
            .foregroundStyle(OmiColors.textPrimary)
        }

        Spacer(minLength: 0)

        Button {
          navigation.toggleSidebar()
        } label: {
          Image(systemName: navigation.isSidebarCollapsed ? "sidebar.right" : "sidebar.left")
            .scaledFont(size: OmiType.body, weight: .medium)
            .frame(width: 30, height: 30)
        }
        .buttonStyle(.plain)
        .foregroundStyle(OmiColors.textSecondary)
        .accessibilityLabel(navigation.isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar")
        .accessibilityIdentifier("chat-first-sidebar-collapse")
      }
      .padding(.horizontal, navigation.isSidebarCollapsed ? OmiSpacing.md : OmiSpacing.lg)
      .padding(.top, OmiSpacing.lg)
      .padding(.bottom, OmiSpacing.xl)

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(ChatFirstRoute.primaryDestinations, id: \.self) { route in
          primaryItem(route)
        }
      }
      .padding(.horizontal, OmiSpacing.sm)

      Spacer(minLength: OmiSpacing.lg)

      Menu {
        ForEach(ChatFirstMorePage.allCases, id: \.self) { page in
          Button {
            navigation.selectMore(page)
          } label: {
            Label(page.title, systemImage: page.systemImage)
          }
          .accessibilityIdentifier("chat-first-more-\(page.stableName)")
        }
      } label: {
        sidebarLabel(
          title: "More",
          icon: "ellipsis.circle",
          selected: !navigation.route.isPrimaryDestination
        )
      }
      .menuStyle(.borderlessButton)
      .accessibilityLabel("More destinations")
      .accessibilityIdentifier("chat-first-sidebar-more")
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.bottom, OmiSpacing.lg)
    }
    .frame(width: width)
    .frame(maxHeight: .infinity)
    .background(OmiColors.backgroundSecondary.opacity(0.84))
    .animation(OmiMotion.gated(.easeOut(duration: 0.16)), value: navigation.isSidebarCollapsed)
  }

  @ViewBuilder
  private func primaryItem(_ route: ChatFirstRoute) -> some View {
    Button {
      navigation.selectPrimary(route)
    } label: {
      sidebarLabel(
        title: route.title,
        icon: icon(for: route),
        selected: navigation.route == route
      )
    }
    .buttonStyle(.plain)
    .accessibilityLabel(route.title)
    .accessibilityIdentifier("chat-first-sidebar-\(route.stableName)")
  }

  private func sidebarLabel(title: String, icon: String, selected: Bool) -> some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.body, weight: .medium)
        .frame(width: 20)
        .accessibilityHidden(true)

      if !navigation.isSidebarCollapsed {
        Text(title)
          .scaledFont(size: OmiType.body, weight: selected ? .semibold : .regular)
          .lineLimit(1)
      }

      Spacer(minLength: 0)
    }
    .foregroundStyle(selected ? OmiColors.textPrimary : OmiColors.textSecondary)
    .padding(.horizontal, navigation.isSidebarCollapsed ? OmiSpacing.md : OmiSpacing.sm)
    .frame(height: 42)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(selected ? OmiColors.backgroundTertiary.opacity(0.9) : Color.clear)
    )
    .contentShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous))
  }

  private func icon(for route: ChatFirstRoute) -> String {
    switch route {
    case .chat: return "bubble.left.and.bubble.right.fill"
    case .conversations: return "text.bubble.fill"
    case .tasks: return "checklist"
    case .goals: return "target"
    case .memories: return "brain"
    case .more: return "ellipsis.circle"
    }
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
