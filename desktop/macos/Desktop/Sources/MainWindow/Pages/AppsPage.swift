import AppKit
import Combine
@preconcurrency import GRDB
import OmiTheme
import SwiftUI

// MARK: - Safe Dismiss Button
/// A dismiss button that prevents click-through to underlying views on macOS.
/// Uses onTapGesture with async delay to ensure the click is fully consumed before dismissing.
/// The key is to wait for the full mouse event cycle to complete before triggering dismiss.
struct SafeDismissButton: View {
  let dismiss: DismissAction
  var icon: String = "xmark"
  var showBackground: Bool = true

  @State private var isPressed = false

  var body: some View {
    Image(systemName: icon)
      .scaledFont(size: OmiType.body, weight: .medium)
      .foregroundColor(isPressed ? OmiColors.textTertiary : OmiColors.textSecondary)
      .frame(width: 28, height: 28)
      .background(showBackground ? OmiColors.backgroundSecondary : Color.clear)
      .clipShape(Circle())
      .contentShape(Circle())
      .opacity(isPressed ? 0.7 : 1.0)
      .onTapGesture {
        guard !isPressed else { return }  // Prevent double-tap
        isPressed = true

        let mouseLocation = NSEvent.mouseLocation
        log("DISMISS: Tap gesture fired at mouse position: \(mouseLocation)")

        // Consume the click by resigning first responder
        NSApp.keyWindow?.makeFirstResponder(nil)

        // Post a mouse-up event to ensure any pending click is consumed
        if let window = NSApp.keyWindow {
          let event = NSEvent.mouseEvent(
            with: .leftMouseUp,
            location: window.mouseLocationOutsideOfEventStream,
            modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: window.windowNumber,
            context: nil,
            eventNumber: 0,
            clickCount: 1,
            pressure: 0
          )
          if let event = event {
            window.sendEvent(event)
            log("DISMISS: Sent synthetic mouse-up event")
          }
        }

        // Use async with longer delay to ensure mouse event fully completes
        Task { @MainActor in
          log("DISMISS: Starting 250ms delay before dismiss")
          // Longer delay to ensure mouse-up event is fully processed
          try? await Task.sleep(nanoseconds: 250_000_000)  // 250ms
          log("DISMISS: Delay complete, calling dismiss()")
          log("DISMISS: Mouse position before dismiss: \(NSEvent.mouseLocation)")
          dismiss()
          log("DISMISS: dismiss() called")
        }
      }
  }
}

// MARK: - Dismiss Button (Action-based)
/// A dismiss button that takes a closure instead of a DismissAction.
/// Used for overlay-based sheets where the dismiss is controlled externally.
/// A real Button (not a tap gesture) so accessibility exposes it as a labeled
/// "Close" control and keyboard users can reach it.
struct DismissButton: View {
  let action: () -> Void
  var icon: String = "xmark"
  var showBackground: Bool = true
  var accessibilityLabel: String = "Close"

  var body: some View {
    Button {
      log("DISMISS_BUTTON: Activated")

      // Commit any in-progress field editing before tearing the sheet down.
      NSApp.keyWindow?.makeFirstResponder(nil)

      OmiMotion.withGated(.easeOut(duration: 0.2)) {
        action()
      }
    } label: {
      Image(systemName: icon)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textSecondary)
        .frame(width: 28, height: 28)
        .background(showBackground ? OmiColors.backgroundSecondary : Color.clear)
        .clipShape(Circle())
        .contentShape(Circle())
    }
    .buttonStyle(DismissButtonPressStyle())
    .accessibilityLabel(accessibilityLabel)
  }
}

private struct DismissButtonPressStyle: ButtonStyle {
  func makeBody(configuration: ButtonStyleConfiguration) -> some View {
    configuration.label
      .opacity(configuration.isPressed ? 0.7 : 1.0)
  }
}

enum AppsCatalogInitialSection {
  case imports
  case exports
}

struct AppsPage: View {
  @ObservedObject var appProvider: AppProvider
  var appState: AppState? = nil
  @ObservedObject var connectorStatusStore: ImportConnectorStatusStore = ImportConnectorStatusStore()
  @ObservedObject private var automationPresentationCoordinator =
    DesktopAutomationPresentationCoordinator.shared
  var initialSection: AppsCatalogInitialSection = .imports
  var handlesAutomationPresentations = false
  var onDismiss: (() -> Void)? = nil
  var onSelectApp: ((OmiApp) -> Void)? = nil
  var onSelectConnector: ((ImportConnector) -> Void)? = nil
  var onSelectDestination: ((MemoryExportDestination) -> Void)? = nil
  @State private var searchText = ""
  @State private var selectedApp: OmiApp?
  @State private var selectedConnector: ImportConnector?
  @State private var selectedExportDestination: MemoryExportDestination?
  @State private var activeAutomationCommand: DesktopAutomationPresentationCommand?
  @State private var visibleAutomationPresentationTarget: DesktopAutomationPresentationTarget?
  @State private var exportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]
  @State private var viewAllSection: String? = nil  // "featured", "integrations", "notifications"

  var body: some View {
    VStack(spacing: 0) {
      // Search bar
      searchBar
        .padding()

      Divider()
        .background(OmiColors.backgroundTertiary)

      // Content
      if appProvider.isLoading {
        loadingShimmerView
      } else {
        // Always render the page (Imports/Exports are local connectors
        // and must show even when the marketplace API returned no apps).
        // The marketplace sections inside the else branch are each
        // self-gated and skip when empty.
        ScrollView {
          LazyVStack(alignment: .leading, spacing: OmiSpacing.xxl) {
            if hasActiveFilters {
              // Show filtered/search results in a flat grid
              if appProvider.isSearching {
                // Loading state for category filter
                VStack(spacing: OmiSpacing.lg) {
                  ProgressView()
                    .scaleEffect(1.2)
                  Text("Loading...")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
              } else if filteredApps.isEmpty {
                VStack(spacing: OmiSpacing.md) {
                  Image(systemName: "magnifyingglass")
                    .scaledFont(size: 32)
                    .foregroundColor(OmiColors.textTertiary)
                  Text("No apps found")
                    .scaledFont(size: OmiType.subheading, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                }
                .frame(maxWidth: .infinity, minHeight: 200)
              } else {
                // Back button for "See more" view
                if viewAllSection != nil {
                  Button(action: { viewAllSection = nil }) {
                    HStack(spacing: OmiSpacing.xs) {
                      Image(systemName: "chevron.left")
                        .scaledFont(size: OmiType.caption, weight: .medium)
                      Text("Back")
                        .scaledFont(size: OmiType.body, weight: .medium)
                    }
                    .foregroundColor(OmiColors.textSecondary)
                  }
                  .buttonStyle(.plain)
                }

                AppGridSection(
                  title: filterResultsTitle,
                  apps: filteredApps,
                  appProvider: appProvider,
                  onSelectApp: selectApp
                )

                // Infinite scroll: load more when reaching bottom
                if appProvider.hasMoreFilteredApps {
                  HStack {
                    Spacer()
                    if appProvider.isLoadingMore {
                      ProgressView()
                        .scaleEffect(0.8)
                      Text("Loading more...")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                    } else {
                      Color.clear
                        .frame(height: 1)
                        .onAppear {
                          Task {
                            await appProvider.loadMoreFilteredApps()
                          }
                        }
                    }
                    Spacer()
                  }
                  .padding(.vertical, OmiSpacing.lg)
                }
              }
            } else {
              switch initialSection {
              case .imports:
                ImportsSection(statusStore: connectorStatusStore) { connector in
                  selectConnector(connector)
                }

                ExportsSection(statuses: exportStatuses) { destination in
                  selectDestination(destination)
                }
              case .exports:
                ExportsSection(statuses: exportStatuses) { destination in
                  selectDestination(destination)
                }

                ImportsSection(statusStore: connectorStatusStore) { connector in
                  selectConnector(connector)
                }
              }

              // Featured section (apps marked as is_popular in backend)
              if !appProvider.popularApps.isEmpty {
                AppGridSection(
                  title: "Other",
                  apps: Array(appProvider.popularApps.prefix(6)),
                  appProvider: appProvider,
                  onSelectApp: selectApp,
                  showSeeMore: appProvider.popularApps.count > 6,
                  onSeeMore: { viewAllSection = "featured" }
                )
              }

              // Integrations section (external_integration capability)
              if !appProvider.integrationApps.isEmpty {
                AppGridSection(
                  title: "Integrations",
                  apps: Array(appProvider.integrationApps.prefix(6)),
                  appProvider: appProvider,
                  onSelectApp: selectApp,
                  showSeeMore: appProvider.integrationApps.count > 6,
                  onSeeMore: { viewAllSection = "integrations" }
                )
              }

              // Realtime Notifications section (proactive_notification capability)
              if !appProvider.notificationApps.isEmpty {
                AppGridSection(
                  title: "Realtime Notifications",
                  apps: Array(appProvider.notificationApps.prefix(6)),
                  appProvider: appProvider,
                  onSelectApp: selectApp,
                  showSeeMore: appProvider.notificationApps.count > 6,
                  onSeeMore: { viewAllSection = "notifications" }
                )
              }
            }
          }
          .padding()
        }
      }
    }
    .background(OmiColors.backgroundPrimary)
    .onChange(of: searchText) { _, newValue in
      appProvider.searchQuery = newValue
      // Clear filters when searching
      if !newValue.isEmpty {
        viewAllSection = nil
        appProvider.clearCategoryFilter()
      }
      Task {
        // Debounce search
        try? await Task.sleep(for: .milliseconds(300))
        if appProvider.searchQuery == newValue {
          await appProvider.searchApps()
        }
      }
    }
    .dismissableSheet(item: $selectedApp) { app in
      AppDetailSheet(app: app, appProvider: appProvider, onDismiss: { selectedApp = nil })
        .frame(width: 500, height: 650)
        .onAppear {
          AnalyticsManager.shared.appDetailViewed(appId: app.id, appName: app.name)
        }
    }
    .dismissableSheet(item: $selectedConnector) { connector in
      ImportConnectorSheet(
        connector: connector,
        appState: appState,
        statusStore: connectorStatusStore,
        onDismiss: {
          selectedConnector = nil
        }
      )
      .frame(width: 520, height: 620)
      .onAppear {
        automationPresentationDidAppear(.importConnector(connector.id))
      }
      .onDisappear {
        automationPresentationDidDisappear(.importConnector(connector.id))
      }
    }
    .dismissableSheet(item: $selectedExportDestination) { destination in
      ConnectDestinationSheet(
        destination: destination,
        statuses: $exportStatuses,
        onDismiss: {
          selectedExportDestination = nil
        }
      )
      .frame(width: 520, height: 620)
      .onAppear {
        automationPresentationDidAppear(.exportDestination(destination.rawValue))
      }
      .onDisappear {
        automationPresentationDidDisappear(.exportDestination(destination.rawValue))
      }
    }
    .onChange(of: automationPresentationCoordinator.activeCommand?.generation) { _, _ in
      consumeAutomationPresentationCommand()
    }
    .onChange(of: handlesAutomationPresentations) { _, isReady in
      guard isReady else { return }
      consumeAutomationPresentationCommand()
    }
    .onAppear {
      consumeAutomationPresentationCommand()
      // If apps are already loaded, notify sidebar to clear loading indicator
      if !appProvider.isLoading {
        NotificationCenter.default.post(name: .appsPageDidLoad, object: nil)
      }
      // Retry fetch if initial load failed and apps are empty
      if appProvider.apps.isEmpty && !appProvider.isLoading {
        Task {
          await appProvider.fetchApps()
        }
      }
    }
    .onDisappear {
      rejectActiveAutomationPresentationIfNeeded()
    }
    .task {
      await connectorStatusStore.refresh()
      exportStatuses = await MemoryExportService.shared.allStatuses()
    }
    .onChange(of: selectedExportDestination) { _, newValue in
      guard newValue == nil else { return }
      Task {
        exportStatuses = await MemoryExportService.shared.allStatuses()
      }
    }
  }

  private func selectApp(_ app: OmiApp) {
    if let onSelectApp {
      onSelectApp(app)
    } else {
      selectedApp = app
    }
  }

  private func selectConnector(_ connector: ImportConnector) {
    if let onSelectConnector {
      onSelectConnector(connector)
    } else {
      selectedConnector = connector
    }
  }

  private func selectDestination(_ destination: MemoryExportDestination) {
    if let onSelectDestination {
      onSelectDestination(destination)
    } else {
      selectedExportDestination = destination
    }
  }

  private func consumeAutomationPresentationCommand() {
    guard handlesAutomationPresentations else { return }
    guard let command = automationPresentationCoordinator.activeCommand else {
      activeAutomationCommand = nil
      return
    }

    activeAutomationCommand = command
    if visibleAutomationPresentationTarget == command.target {
      acknowledgeAutomationPresentation(command.target)
      return
    }

    selectedApp = nil
    switch command.target {
    case .importConnector(let identifier):
      selectedExportDestination = nil
      guard let connector = ImportConnector.all.first(where: { $0.id == identifier }) else {
        rejectActiveAutomationPresentationIfNeeded()
        return
      }
      selectConnector(connector)
    case .exportDestination(let identifier):
      selectedConnector = nil
      guard let destination = MemoryExportDestination(rawValue: identifier) else {
        rejectActiveAutomationPresentationIfNeeded()
        return
      }
      selectDestination(destination)
    }
  }

  private func automationPresentationDidAppear(
    _ target: DesktopAutomationPresentationTarget
  ) {
    visibleAutomationPresentationTarget = target
    acknowledgeAutomationPresentation(target)
  }

  private func automationPresentationDidDisappear(
    _ target: DesktopAutomationPresentationTarget
  ) {
    guard visibleAutomationPresentationTarget == target else { return }
    visibleAutomationPresentationTarget = nil
  }

  private func acknowledgeAutomationPresentation(
    _ target: DesktopAutomationPresentationTarget
  ) {
    guard handlesAutomationPresentations,
      let command = activeAutomationCommand,
      command.target == target
    else { return }

    if automationPresentationCoordinator.acknowledgeVisible(
      generation: command.generation,
      target: target
    ) {
      activeAutomationCommand = nil
    }
  }

  private func rejectActiveAutomationPresentationIfNeeded() {
    guard handlesAutomationPresentations, let command = activeAutomationCommand else { return }
    _ = automationPresentationCoordinator.rejectUnavailable(
      generation: command.generation,
      target: command.target
    )
    activeAutomationCommand = nil
  }

  private var searchBar: some View {
    ViewThatFits(in: .horizontal) {
      HStack(spacing: OmiSpacing.sm) {
        searchField
          .layoutPriority(1)
        filterControls
        Spacer(minLength: 8)
        createAppButton
        dismissControl
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.sm) {
          searchField
          dismissControl
        }

        HStack(spacing: OmiSpacing.sm) {
          filterControls
          Spacer(minLength: 8)
          createAppButton
        }
      }
    }
  }

  private var searchField: some View {
    HStack {
      Image(systemName: "magnifyingglass")
        .foregroundColor(OmiColors.textTertiary)

      TextField("Search apps...", text: $searchText)
        .textFieldStyle(.plain)
        .foregroundColor(OmiColors.textPrimary)
        .accessibilityLabel("Search apps")

      if !searchText.isEmpty {
        Button(action: { searchText = "" }) {
          Image(systemName: "xmark.circle.fill")
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(OmiSpacing.sm)
    .background(OmiColors.backgroundSecondary)
    .cornerRadius(OmiChrome.smallControlRadius)
  }

  private var filterControls: some View {
    HStack(spacing: OmiSpacing.sm) {
      FilterToggle(
        icon: "arrow.down.circle",
        label: "Installed",
        isActive: appProvider.showInstalledOnly
      ) {
        viewAllSection = nil
        appProvider.showInstalledOnly.toggle()
        Task { await appProvider.searchApps() }
      }

      categoryMenu
    }
  }

  private var categoryMenu: some View {
    Menu {
      Button(action: {
        viewAllSection = nil
        appProvider.clearCategoryFilter()
        Task { await appProvider.searchApps() }
      }) {
        HStack {
          Text("All Categories")
          if appProvider.selectedCategory == nil {
            Image(systemName: "checkmark")
          }
        }
      }

      Divider()

      ForEach(appProvider.categories) { category in
        Button(action: {
          viewAllSection = nil
          appProvider.selectedCategory = category.id
          Task { await appProvider.searchApps() }
        }) {
          HStack {
            Text(category.title)
            if appProvider.selectedCategory == category.id {
              Image(systemName: "checkmark")
            }
          }
        }
      }
    } label: {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "line.3.horizontal.decrease.circle")
          .scaledFont(size: OmiType.caption)
        Text(selectedCategoryLabel)
          .scaledFont(size: OmiType.body)
          .lineLimit(1)
        Image(systemName: "chevron.down")
          .scaledFont(size: OmiType.micro, weight: .medium)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(OmiColors.backgroundSecondary)
      .foregroundColor(OmiColors.textPrimary)
      .cornerRadius(OmiChrome.elementRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(appProvider.selectedCategory != nil ? OmiColors.border : Color.clear, lineWidth: 1)
      )
    }
    .menuStyle(.borderlessButton)
    .tint(OmiColors.textPrimary)
    .fixedSize()
  }

  private var createAppButton: some View {
    SmallHeaderButton(
      icon: "app.badge.fill",
      label: "Create App",
      color: OmiColors.textSecondary
    ) {
      if let url = URL(string: "https://docs.omi.me/docs/developer/apps/Introduction") {
        NSWorkspace.shared.open(url)
      }
    }
  }

  @ViewBuilder
  private var dismissControl: some View {
    if let onDismiss {
      DismissButton(action: onDismiss)
    }
  }

  private var hasActiveFilters: Bool {
    appProvider.hasActiveFilters || viewAllSection != nil
  }

  private var selectedCategoryLabel: String {
    if let categoryId = appProvider.selectedCategory,
      let category = appProvider.categories.first(where: { $0.id == categoryId })
    {
      return category.title
    }
    return "Category"
  }

  /// Apps for the selected filter/search result set or "See more" section.
  private var filteredApps: [OmiApp] {
    // "See more" section takes priority
    if let section = viewAllSection {
      switch section {
      case "featured": return appProvider.popularApps
      case "integrations": return appProvider.integrationApps
      case "notifications": return appProvider.notificationApps
      default: return []
      }
    }
    return appProvider.filteredApps ?? []
  }

  private var filterResultsTitle: String {
    let apps = filteredApps
    // "See more" section title
    if let section = viewAllSection {
      let title =
        switch section {
        case "featured": "Featured"
        case "integrations": "Integrations"
        case "notifications": "Realtime Notifications"
        default: "Apps"
        }
      return "\(title) (\(apps.count))"
    }
    if !searchText.isEmpty {
      return "Search Results (\(apps.count))"
    }
    if let categoryId = appProvider.selectedCategory,
      let category = appProvider.categories.first(where: { $0.id == categoryId })
    {
      return "\(category.title) (\(apps.count))"
    }
    return "Results (\(apps.count))"
  }

  private var loadingShimmerView: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
        // Shimmer sections
        ForEach(0..<3, id: \.self) { _ in
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            ShimmerView()
              .frame(width: 120, height: 24)
              .cornerRadius(OmiChrome.badgeRadius)

            ScrollView(.horizontal, showsIndicators: false) {
              HStack(spacing: OmiSpacing.lg) {
                ForEach(0..<4, id: \.self) { _ in
                  ShimmerAppCard()
                }
              }
            }
          }
        }
      }
      .padding()
    }
  }

  private var emptyView: some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "square.grid.2x2")
        .scaledFont(size: 48)
        .foregroundColor(OmiColors.textTertiary)

      Text("No apps found")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      if !searchText.isEmpty {
        Text("Try a different search term")
          .foregroundColor(OmiColors.textTertiary)

        Button("Clear Search") {
          searchText = ""
        }
        .buttonStyle(.bordered)
      } else {
        Text("Apps will appear here once available")
          .foregroundColor(OmiColors.textTertiary)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

// MARK: - Imports Section

struct ImportConnector: Identifiable {
  let id: String
  let title: String
  let subtitle: String
  let description: String
  let brand: ConnectorBrand
  let statusText: String
  let metricText: String?
  let actionTitle: String
  let isConnected: Bool

  static let all: [ImportConnector] = [
    ImportConnector(
      id: "calendar",
      title: "Calendar",
      subtitle: "Google Calendar",
      description: "Import events and recurring routines.",
      brand: .calendar,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "email",
      title: "Email",
      subtitle: "Gmail",
      description: "Import email history and follow-ups.",
      brand: .gmail,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "local-files",
      title: "Local files",
      subtitle: "This Mac",
      description: "Index documents, code, and working folders.",
      brand: .localFiles,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "apple-notes",
      title: "Apple Notes",
      subtitle: "Private notes",
      description: "Import notes and private written context.",
      brand: .appleNotes,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "x",
      title: "X (Twitter)",
      subtitle: "Your posts & bookmarks",
      description: "Connect your X account so Omi learns from your tweets and bookmarks.",
      brand: .x,
      statusText: "Not connected",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "chatgpt",
      title: "ChatGPT",
      subtitle: "Memory import",
      description: "Paste a memory export into Omi.",
      brand: .chatgpt,
      statusText: "Optional",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
    ImportConnector(
      id: "claude",
      title: "Claude",
      subtitle: "Memory import",
      description: "Paste a memory export into Omi.",
      brand: .claude,
      statusText: "Optional",
      metricText: nil,
      actionTitle: "Connect",
      isConnected: false
    ),
  ]
}

@MainActor
final class ImportConnectorStatusStore: ObservableObject {
  struct ConnectorMetrics {
    var sourceCount: Int?
    var memoryCount: Int?
    var lastSyncedAt: Date?
    var lastDeltaCount: Int?
    var availabilityText: String?
  }

  struct Snapshot {
    let isConnected: Bool
    let actionTitle: String
    let primaryText: String
    let secondaryText: String?
  }

  @Published private var metricsByID: [String: ConnectorMetrics] = [:]
  let connectorDidSync = PassthroughSubject<String, Never>()

  private let defaults: UserDefaults
  private let sourceCountKeyPrefix = "appsImportConnectorSourceCount."
  private let memoryCountKeyPrefix = "appsImportConnectorMemoryCount."
  private let lastSyncedAtKeyPrefix = "appsImportConnectorLastSyncedAt."
  private let lastDeltaCountKeyPrefix = "appsImportConnectorLastDeltaCount."
  private let hasLastDeltaKeyPrefix = "appsImportConnectorHasLastDelta."
  private let availabilityTextKeyPrefix = "appsImportConnectorAvailabilityText."
  private let manualConnectorIDs: Set<String> = ["chatgpt", "claude"]
  private let onboardingChatGPTImportedMemoriesKey = "onboardingChatGPTImportedMemoriesCount"
  private let onboardingClaudeImportedMemoriesKey = "onboardingClaudeImportedMemoriesCount"
  private var sessionUserID: String?

  init(defaults: UserDefaults = .standard, sessionUserID: String? = nil) {
    self.defaults = defaults
    self.sessionUserID = Self.normalizedUserID(
      sessionUserID ?? defaults.string(forKey: .authUserId)
    )
    load()
  }

  func setSessionUserID(_ userID: String?) {
    let userID = Self.normalizedUserID(userID)
    guard userID != sessionUserID else { return }
    sessionUserID = userID
    load()
  }

  func snapshot(for connector: ImportConnector) -> Snapshot {
    let metrics = metricsByID[connector.id] ?? ConnectorMetrics()
    let isConnected = isConnected(connector: connector, metrics: metrics)
    let actionTitle: String
    if manualConnectorIDs.contains(connector.id) {
      actionTitle = isConnected ? "Update" : "Connect"
    } else {
      actionTitle = isConnected ? "Sync now" : "Connect"
    }

    return Snapshot(
      isConnected: isConnected,
      actionTitle: actionTitle,
      primaryText: primaryText(for: connector, metrics: metrics, isConnected: isConnected),
      secondaryText: secondaryText(for: connector, metrics: metrics, isConnected: isConnected)
    )
  }

  func markSynced(
    connectorID: String,
    sourceCount: Int? = nil,
    memoryCount: Int? = nil,
    lastDeltaCount: Int? = nil,
    availabilityText: String? = nil,
    syncedAt: Date = Date()
  ) {
    var metrics = metricsByID[connectorID] ?? ConnectorMetrics()
    if let sourceCount {
      metrics.sourceCount = max(sourceCount, 0)
      defaults.set(metrics.sourceCount, forKey: storageKey(prefix: sourceCountKeyPrefix, connectorID: connectorID))
    }
    if let memoryCount {
      metrics.memoryCount = max(memoryCount, 0)
      defaults.set(metrics.memoryCount, forKey: storageKey(prefix: memoryCountKeyPrefix, connectorID: connectorID))
    }
    metrics.lastSyncedAt = syncedAt
    defaults.set(
      syncedAt.timeIntervalSince1970,
      forKey: storageKey(prefix: lastSyncedAtKeyPrefix, connectorID: connectorID)
    )
    metrics.lastDeltaCount = lastDeltaCount
    defaults.set(
      lastDeltaCount != nil,
      forKey: storageKey(prefix: hasLastDeltaKeyPrefix, connectorID: connectorID)
    )
    if let lastDeltaCount {
      defaults.set(
        lastDeltaCount,
        forKey: storageKey(prefix: lastDeltaCountKeyPrefix, connectorID: connectorID)
      )
    } else {
      defaults.removeObject(forKey: storageKey(prefix: lastDeltaCountKeyPrefix, connectorID: connectorID))
    }
    if let availabilityText {
      metrics.availabilityText = availabilityText
      defaults.set(
        availabilityText,
        forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: connectorID)
      )
    }
    metricsByID[connectorID] = metrics
    connectorDidSync.send(connectorID)
  }

  private func clearStoredMetrics(for connectorID: String) {
    defaults.removeObject(forKey: storageKey(prefix: sourceCountKeyPrefix, connectorID: connectorID))
    defaults.removeObject(forKey: storageKey(prefix: memoryCountKeyPrefix, connectorID: connectorID))
    defaults.removeObject(forKey: storageKey(prefix: lastSyncedAtKeyPrefix, connectorID: connectorID))
    defaults.removeObject(forKey: storageKey(prefix: lastDeltaCountKeyPrefix, connectorID: connectorID))
    defaults.removeObject(forKey: storageKey(prefix: hasLastDeltaKeyPrefix, connectorID: connectorID))
    defaults.removeObject(forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: connectorID))
    metricsByID[connectorID] = ConnectorMetrics()
  }

  func refresh() async {
    refreshPersistedManualImportMetrics()
    await refreshLocalFilesMetrics()
    await refreshAppleNotesMetrics()
  }

  func refreshPersistedManualImportMetrics() {
    hydrateLegacyManualImports()
  }

  private func load() {
    metricsByID = [:]
    guard sessionUserID != nil else { return }
    for connector in ImportConnector.all {
      migrateLegacyMetricsIfNeeded(connectorID: connector.id)
      var metrics = ConnectorMetrics()

      let sourceCountKey = storageKey(prefix: sourceCountKeyPrefix, connectorID: connector.id)
      let memoryCountKey = storageKey(prefix: memoryCountKeyPrefix, connectorID: connector.id)
      let lastSyncedAtKey = storageKey(prefix: lastSyncedAtKeyPrefix, connectorID: connector.id)
      let hasLastDeltaKey = storageKey(prefix: hasLastDeltaKeyPrefix, connectorID: connector.id)
      let lastDeltaCountKey = storageKey(prefix: lastDeltaCountKeyPrefix, connectorID: connector.id)
      let availabilityTextKey = storageKey(prefix: availabilityTextKeyPrefix, connectorID: connector.id)

      if defaults.object(forKey: sourceCountKey) != nil {
        metrics.sourceCount = defaults.integer(forKey: sourceCountKey)
      }
      if defaults.object(forKey: memoryCountKey) != nil {
        metrics.memoryCount = defaults.integer(forKey: memoryCountKey)
      }
      if defaults.object(forKey: lastSyncedAtKey) != nil {
        let timestamp = defaults.double(forKey: lastSyncedAtKey)
        if timestamp > 0 {
          metrics.lastSyncedAt = Date(timeIntervalSince1970: timestamp)
        }
      }
      if defaults.bool(forKey: hasLastDeltaKey) {
        metrics.lastDeltaCount = defaults.integer(forKey: lastDeltaCountKey)
      }
      metrics.availabilityText = defaults.string(forKey: availabilityTextKey)

      metricsByID[connector.id] = metrics
    }

    hydrateLegacyManualImports()

    // A remembered path is not enough to call Apple Notes connected. The
    // status becomes connected only after the reader proves the store is readable.
  }

  private func hydrateLegacyManualImports() {
    guard let sessionUserID else { return }
    let ownerUserID = Self.normalizedUserID(defaults.string(forKey: .onboardingMemoryImportOwnerUserId))
    let legacyChatGPTCount = defaults.integer(forKey: onboardingChatGPTImportedMemoriesKey)
    let legacyClaudeCount = defaults.integer(forKey: onboardingClaudeImportedMemoriesKey)
    if ownerUserID == nil,
      legacyChatGPTCount > 0 || legacyClaudeCount > 0
    {
      defaults.set(sessionUserID, forKey: .onboardingMemoryImportOwnerUserId)
    }

    let resolvedOwnerUserID = Self.normalizedUserID(
      defaults.string(forKey: .onboardingMemoryImportOwnerUserId)
    )
    guard resolvedOwnerUserID == sessionUserID else { return }

    let chatGPTMemoryCountKey = storageKey(prefix: memoryCountKeyPrefix, connectorID: "chatgpt")
    if legacyChatGPTCount > 0,
      defaults.object(forKey: chatGPTMemoryCountKey) == nil
    {
      var metrics = metricsByID["chatgpt"] ?? ConnectorMetrics()
      metrics.memoryCount = legacyChatGPTCount
      metrics.availabilityText = "Imported during onboarding"
      metricsByID["chatgpt"] = metrics
      defaults.set(legacyChatGPTCount, forKey: chatGPTMemoryCountKey)
      defaults.set(
        "Imported during onboarding",
        forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: "chatgpt")
      )
    }

    let claudeMemoryCountKey = storageKey(prefix: memoryCountKeyPrefix, connectorID: "claude")
    if legacyClaudeCount > 0,
      defaults.object(forKey: claudeMemoryCountKey) == nil
    {
      var metrics = metricsByID["claude"] ?? ConnectorMetrics()
      metrics.memoryCount = legacyClaudeCount
      metrics.availabilityText = "Imported during onboarding"
      metricsByID["claude"] = metrics
      defaults.set(legacyClaudeCount, forKey: claudeMemoryCountKey)
      defaults.set(
        "Imported during onboarding",
        forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: "claude")
      )
    }
  }

  private func storageKey(prefix: String, connectorID: String) -> String {
    guard let sessionUserID else { return prefix + connectorID }
    return "\(prefix)user.\(sessionUserID).\(connectorID)"
  }

  private func migrateLegacyMetricsIfNeeded(connectorID: String) {
    guard sessionUserID != nil else { return }
    for prefix in [
      sourceCountKeyPrefix,
      memoryCountKeyPrefix,
      lastSyncedAtKeyPrefix,
      lastDeltaCountKeyPrefix,
      hasLastDeltaKeyPrefix,
      availabilityTextKeyPrefix,
    ] {
      let legacyKey = prefix + connectorID
      let scopedKey = storageKey(prefix: prefix, connectorID: connectorID)
      if defaults.object(forKey: scopedKey) == nil,
        let legacyValue = defaults.object(forKey: legacyKey)
      {
        defaults.set(legacyValue, forKey: scopedKey)
      }
      defaults.removeObject(forKey: legacyKey)
    }
  }

  private static func normalizedUserID(_ userID: String?) -> String? {
    let trimmed = userID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }

  private func refreshLocalFilesMetrics() async {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else { return }

    do {
      let result: (count: Int, lastIndexedAt: Date?) = try await dbQueue.read { db in
        guard
          let row = try Row.fetchOne(
            db,
            sql: """
                  SELECT COUNT(*) AS count, MAX(indexedAt) AS lastIndexedAt
                  FROM indexed_files
              """
          )
        else {
          return (0, nil)
        }
        let count: Int = row["count"] ?? 0
        let lastIndexedAt: Date? = row["lastIndexedAt"]
        return (count, lastIndexedAt)
      }

      var metrics = metricsByID["local-files"] ?? ConnectorMetrics()
      metrics.sourceCount = result.count
      defaults.set(
        result.count,
        forKey: storageKey(prefix: sourceCountKeyPrefix, connectorID: "local-files")
      )
      if metrics.lastSyncedAt == nil, let lastIndexedAt = result.lastIndexedAt {
        metrics.lastSyncedAt = lastIndexedAt
        defaults.set(
          lastIndexedAt.timeIntervalSince1970,
          forKey: storageKey(prefix: lastSyncedAtKeyPrefix, connectorID: "local-files")
        )
      }
      if metrics.lastSyncedAt != nil || result.count > 0 {
        metrics.availabilityText = "On-device index"
        defaults.set(
          "On-device index",
          forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: "local-files")
        )
      } else {
        metrics.availabilityText = nil
        defaults.removeObject(
          forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: "local-files")
        )
      }
      metricsByID["local-files"] = metrics
    } catch {
      log("ImportConnectorStatusStore: Failed to refresh local files metrics: \(error)")
    }
  }

  private func refreshAppleNotesMetrics() async {
    let status = await AppleNotesReaderService.shared.connectionStatus(maxResults: 250)
    switch status {
    case .connected(let noteCount, _):
      var metrics = metricsByID["apple-notes"] ?? ConnectorMetrics()
      metrics.sourceCount = noteCount
      defaults.set(
        noteCount,
        forKey: storageKey(prefix: sourceCountKeyPrefix, connectorID: "apple-notes")
      )
      if metrics.lastSyncedAt == nil {
        let syncedAt = Date()
        metrics.lastSyncedAt = syncedAt
        defaults.set(
          syncedAt.timeIntervalSince1970,
          forKey: storageKey(prefix: lastSyncedAtKeyPrefix, connectorID: "apple-notes")
        )
      }
      metrics.availabilityText = "Private notes accessible"
      defaults.set(
        "Private notes accessible",
        forKey: storageKey(prefix: availabilityTextKeyPrefix, connectorID: "apple-notes")
      )
      metricsByID["apple-notes"] = metrics
    case .needsAccess(_, let reasonCode), .error(_, let reasonCode):
      log("ImportConnectorStatusStore: Apple Notes refresh unavailable code=\(reasonCode)")
      clearStoredMetrics(for: "apple-notes")
    }
  }

  private func isConnected(connector: ImportConnector, metrics: ConnectorMetrics) -> Bool {
    if metrics.lastSyncedAt != nil {
      return true
    }

    return manualConnectorIDs.contains(connector.id) && (metrics.memoryCount ?? 0) > 0
  }

  private func primaryText(
    for connector: ImportConnector,
    metrics: ConnectorMetrics,
    isConnected: Bool
  ) -> String {
    if let sourceCount = metrics.sourceCount {
      if let memoryCount = metrics.memoryCount, memoryCount > 0 {
        return
          "\(sourceCount.formatted()) \(sourceLabel(for: connector, count: sourceCount)) • \(memoryCount.formatted()) memories"
      }
      if isConnected || sourceCount > 0 {
        return "\(sourceCount.formatted()) \(sourceLabel(for: connector, count: sourceCount))"
      }
    }

    if let memoryCount = metrics.memoryCount, memoryCount > 0 {
      return "\(memoryCount.formatted()) memories imported"
    }

    if isConnected, let availabilityText = metrics.availabilityText {
      return availabilityText
    }

    return connector.statusText
  }

  private func secondaryText(
    for connector: ImportConnector,
    metrics: ConnectorMetrics,
    isConnected: Bool
  ) -> String? {
    if let lastSyncedAt = metrics.lastSyncedAt {
      var text = "Synced \(relativeTimestamp(lastSyncedAt))"
      if let lastDeltaCount = metrics.lastDeltaCount, lastDeltaCount > 0 {
        text += " • +\(lastDeltaCount.formatted()) new"
      }
      return text
    }

    if let availabilityText = metrics.availabilityText,
      availabilityText != primaryText(for: connector, metrics: metrics, isConnected: isConnected)
    {
      return availabilityText
    }

    if let metricText = connector.metricText {
      return metricText
    }

    return manualConnectorIDs.contains(connector.id) && isConnected ? "Imported earlier" : nil
  }

  private func sourceLabel(for connector: ImportConnector, count: Int) -> String {
    switch connector.id {
    case "calendar":
      return count == 1 ? "event" : "events"
    case "email":
      return count == 1 ? "email" : "emails"
    case "local-files":
      return count == 1 ? "file indexed" : "files indexed"
    case "apple-notes":
      return count == 1 ? "note" : "notes"
    case "x":
      return count == 1 ? "post" : "posts"
    default:
      return count == 1 ? "item" : "items"
    }
  }

  private func relativeTimestamp(_ date: Date) -> String {
    RelativeDateTimeFormatter().localizedString(for: date, relativeTo: Date())
  }
}

struct ImportsSection: View {
  private let connectors = ImportConnector.all
  @ObservedObject var statusStore: ImportConnectorStatusStore
  let onSelectConnector: (ImportConnector) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Imports")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      LazyVGrid(
        columns: [GridItem(.adaptive(minimum: 260), spacing: OmiSpacing.md)],
        alignment: .leading,
        spacing: OmiSpacing.md
      ) {
        ForEach(connectors) { connector in
          ImportConnectorCard(
            connector: connector,
            snapshot: statusStore.snapshot(for: connector)
          ) {
            onSelectConnector(connector)
          }
        }
      }
    }
  }
}

struct ImportConnectorRow: View {
  let connector: ImportConnector
  let snapshot: ImportConnectorStatusStore.Snapshot
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.md) {
        ConnectorBrandIcon(brand: connector.brand, size: 34, cornerRadius: 9)

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(connector.title)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          Text(connector.description)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.tail)
        }

        Spacer(minLength: 12)

        ImportConnectorActionButton(title: snapshot.actionTitle, isConnected: snapshot.isConnected)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
      .background(isHovering ? OmiColors.backgroundSecondary : Color.clear)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

struct ImportConnectorCard: View {
  let connector: ImportConnector
  let snapshot: ImportConnectorStatusStore.Snapshot
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.md) {
          ConnectorBrandIcon(brand: connector.brand, size: 50, cornerRadius: OmiChrome.smallControlRadius)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text(connector.title)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
              .lineLimit(1)

            Text(connector.subtitle)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
          }

          Spacer()
        }

        Text(connector.description)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(2)
          .multilineTextAlignment(.leading)

        HStack {
          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(snapshot.primaryText)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(snapshot.isConnected ? OmiColors.textSecondary : OmiColors.textTertiary)

            if let secondaryText = snapshot.secondaryText {
              Text(secondaryText)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
                .lineLimit(1)
            }
          }

          Spacer()

          ImportConnectorActionButton(title: snapshot.actionTitle, isConnected: snapshot.isConnected)
        }
      }
      .padding(OmiSpacing.md)
      .background(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
      .cornerRadius(OmiChrome.smallControlRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovering = hovering
    }
  }
}

struct ImportConnectorActionButton: View {
  let title: String
  let isConnected: Bool

  var body: some View {
    Text(title)
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(isConnected ? OmiColors.textPrimary : .black)
      .frame(width: isConnected ? 84 : 72, height: 28)
      .background(isConnected ? OmiColors.backgroundSecondary : Color.white)
      .cornerRadius(OmiChrome.chipRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
          .stroke(OmiColors.border, lineWidth: 1)
      )
  }
}

struct ConnectionModalActionButton: View {
  let title: String
  var isConnected = false

  var body: some View {
    Text(title)
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(isConnected ? OmiColors.textPrimary : .black)
      .lineLimit(1)
      .padding(.horizontal, OmiSpacing.md)
      .frame(minWidth: isConnected ? 84 : 72)
      .frame(height: 28)
      .background(isConnected ? OmiColors.backgroundSecondary : Color.white)
      .cornerRadius(OmiChrome.chipRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
          .stroke(OmiColors.border, lineWidth: 1)
      )
  }
}

struct ImportConnectorSheet: View {
  let connector: ImportConnector
  let appState: AppState?
  @ObservedObject var statusStore: ImportConnectorStatusStore
  let onDismiss: () -> Void

  @ObservedObject private var runner = ConnectorImportRunner.shared
  @State private var draftText = ""
  /// The trimmed draft a run consumed, kept to make success-clearing exact:
  /// only ever wipe the text the run actually imported, never a newer paste.
  @State private var submittedDraft: String?
  @FocusState private var draftFocused: Bool

  private var snapshot: ImportConnectorStatusStore.Snapshot {
    statusStore.snapshot(for: connector)
  }

  private var runState: ConnectorImportRunner.RunState? {
    runner.runs[connector.id]
  }

  private var isRunning: Bool {
    runState?.phase == .running
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      HStack(alignment: .top, spacing: OmiSpacing.md) {
        ConnectorBrandIcon(brand: connector.brand, size: 56, cornerRadius: OmiChrome.controlRadius)

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(connector.title)
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)

          Text(connector.subtitle)
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)

          Text(connector.description)
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textSecondary)
            .padding(.top, OmiSpacing.xxs)
        }

        Spacer()

        DismissButton(action: onDismiss)
      }

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.lg) {
          if connector.id == "chatgpt" || connector.id == "claude" {
            memoryImportContent
          } else {
            connectorActionContent
          }

          statusSection
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    .padding(OmiSpacing.xxl)
    .background(OmiColors.backgroundPrimary)
    .onChange(of: runState?.phase) { _, newPhase in
      // A successful import consumed the pasted draft, so clear it —
      // but only if it is still the submitted text. A reopened sheet
      // (submittedDraft == nil) or a draft edited mid-run must never
      // be wiped by an older run finishing. A failed run keeps the
      // draft so the user can retry without re-pasting.
      if newPhase == .succeeded {
        if draftText.trimmingCharacters(in: .whitespacesAndNewlines) == submittedDraft {
          draftText = ""
        }
        submittedDraft = nil
      }
    }
    .onDisappear {
      // A seen success is done with: clear it so the next open shows
      // the persisted snapshot status instead of stale success text.
      // Failures stay until the next start so they can't be missed.
      runner.acknowledgeSuccess(connectorID: connector.id)
    }
  }

  private var connectorActionContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      if let metricText = connector.metricText {
        Text(metricText)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }

      Button {
        startConnectorImport()
      } label: {
        ConnectionModalActionButton(
          title: primaryActionTitle,
          isConnected: snapshot.isConnected
        )
      }
      .buttonStyle(.plain)
      .disabled(isRunning)

      if connector.id == "local-files" {
        Text("Local files are indexed on-device and used to build your memory graph.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }
    }
  }

  private var memoryImportContent: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text("Open \(connector.title), paste the copied prompt, then drop the full response here.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)

      Button {
        openAndCopyPrompt(for: memorySource)
      } label: {
        ConnectionModalActionButton(title: "Open \(connector.title) and Copy Prompt")
      }
      .buttonStyle(.plain)

      ZStack(alignment: .topLeading) {
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
          .fill(OmiColors.backgroundSecondary)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
              .stroke(
                Color.white.opacity(draftFocused ? 0.18 : 0.08),
                lineWidth: 1
              )
          )

        if draftText.isEmpty {
          Text("Paste the full \(connector.title) response here…")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, draftFieldHorizontalInset)
            .padding(.vertical, draftFieldVerticalInset)
            .allowsHitTesting(false)
        }

        TextEditor(text: $draftText)
          .scrollContentBackground(.hidden)
          .font(.system(size: 13))
          .foregroundColor(OmiColors.textPrimary)
          // NSTextView adds a built-in 5pt line-fragment inset, so
          // subtract it here to align the caret with the placeholder.
          .padding(.horizontal, draftFieldHorizontalInset - 5)
          .padding(.vertical, draftFieldVerticalInset)
          // The running import consumed the text captured at start,
          // so edits mid-run would be ignored — and a success landing
          // from a run started in an earlier sheet instance clears
          // the draft, which must not eat text pasted mid-run.
          // `.disabled` alone doesn't evict an already-focused
          // NSTextView, so `startMemoryLogImport` also drops focus.
          .focused($draftFocused)
          .disabled(isRunning)
      }
      // Collapsed until the user engages, per the macOS convention for
      // paste-blob inputs in compact modals: grow on focus or content.
      .frame(height: draftFieldExpanded ? 200 : 64)
      .omiAnimation(.easeInOut(duration: 0.18), value: draftFieldExpanded)

      Button {
        startMemoryLogImport()
      } label: {
        ConnectionModalActionButton(
          title: isRunning ? "Importing…" : "Import \(connector.title)"
        )
      }
      .buttonStyle(.plain)
      .disabled(isRunning || isDraftEmpty)
    }
  }

  private var memorySource: OnboardingMemoryLogSource {
    connector.id == "chatgpt" ? .chatgpt : .claude
  }

  private var primaryActionTitle: String {
    switch connector.id {
    case "calendar":
      return isRunning ? "Importing…" : (snapshot.isConnected ? "Sync now" : "Connect Calendar")
    case "email":
      return isRunning ? "Importing…" : (snapshot.isConnected ? "Sync now" : "Connect Gmail")
    case "apple-notes":
      return isRunning ? "Importing…" : (snapshot.isConnected ? "Sync now" : "Connect Apple Notes")
    case "x":
      return isRunning ? "Connecting…" : (snapshot.isConnected ? "Sync now" : "Connect X")
    case "local-files":
      return isRunning ? "Reindexing…" : (snapshot.isConnected ? "Reindex Local Files" : "Index Local Files")
    default:
      return isRunning ? "Working…" : connector.actionTitle
    }
  }

  private func startConnectorImport() {
    switch connector.id {
    case "calendar":
      startRun(
        title: "Connecting to Calendar",
        detail: "Reading past events and upcoming commitments for memory extraction."
      ) { progress in
        await ConnectorImportOperations.importCalendar(progress: progress)
      }
    case "email":
      startRun(
        title: "Connecting to Gmail",
        detail: "Reading recent email history and follow-ups from the last year."
      ) { progress in
        await ConnectorImportOperations.importGmail(progress: progress)
      }
    case "x":
      startRun(
        title: "Connecting to X",
        detail: "Opening x.com to authorize access to your posts and bookmarks.",
        availabilityText: "Posts & bookmarks"
      ) { progress in
        await ConnectorImportOperations.connectX(progress: progress)
      }
    case "apple-notes":
      startRun(
        title: "Connecting to Apple Notes",
        detail: "Checking access and preparing to import recent notes.",
        availabilityText: "Private notes accessible"
      ) { progress in
        await ConnectorImportOperations.importAppleNotes(progress: progress)
      }
    case "local-files":
      startRun(
        title: "Indexing local files",
        detail: "Scanning your on-device files so Omi can use them in memory search.",
        availabilityText: "On-device index"
      ) { _ in
        await ConnectorImportOperations.rescanLocalFiles()
      }
    default:
      break
    }
  }

  private var isDraftEmpty: Bool {
    draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  // Collapsed while empty (even when focused, since macOS auto-focuses the
  // editor on open); grows once there is text to paste/type into.
  private var draftFieldExpanded: Bool {
    !draftText.isEmpty
  }

  private let draftFieldHorizontalInset: CGFloat = 14
  private let draftFieldVerticalInset: CGFloat = 12

  private func startMemoryLogImport() {
    // The Import button is disabled while the draft is empty; this guard
    // is the function's precondition, not a reachable UI path.
    let trimmed = draftText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    let source = memorySource
    draftFocused = false
    submittedDraft = trimmed
    startRun(
      title: "Importing \(source.displayName)",
      detail: "Extracting durable memories from the pasted conversation.",
      availabilityText: "Imported manually"
    ) { _ in
      await ConnectorImportOperations.importMemoryLog(text: trimmed, source: source)
    }
  }

  /// Hands the run to the shared runner so it survives this sheet closing.
  /// Marking the connector synced happens inside the runner-owned task,
  /// not in a button closure tied to this sheet's lifetime.
  private func startRun(
    title: String,
    detail: String,
    availabilityText: String? = nil,
    operation: @escaping @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorImportOperations.Outcome
  ) {
    let connectorID = connector.id
    let statusStore = statusStore
    ConnectorImportRunner.shared.start(
      connectorID: connectorID,
      progressTitle: title,
      progressDetail: detail
    ) { progress in
      switch await operation(progress) {
      case .success(let result, let message):
        statusStore.markSynced(
          connectorID: connectorID,
          sourceCount: result.sourceCount,
          memoryCount: result.memoryCount,
          lastDeltaCount: result.newItems,
          availabilityText: availabilityText
        )
        return .success(message: message)
      case .failure(let message):
        return .failure(message: message)
      }
    }
  }

  private func openAndCopyPrompt(for source: OnboardingMemoryLogSource) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(source.prompt, forType: .string)
    NSWorkspace.shared.open(source.prefilledBrowserURL)
  }

  @ViewBuilder
  private var statusSection: some View {
    if let run = runState, run.phase == .running {
      statusCard {
        HStack(alignment: .top, spacing: OmiSpacing.md) {
          ProgressView()
            .controlSize(.small)
            .padding(.top, OmiSpacing.hairline)

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text(run.progressTitle)
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(run.progressDetail)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textSecondary)
              .fixedSize(horizontal: false, vertical: true)

            Text("You can close this window now. Omi keeps importing in the background.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }
    } else if let statusMessage = runState?.statusMessage {
      Text(statusMessage)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.success)
    } else if let errorMessage = runState?.errorMessage {
      Text(UserFacingErrorPresentation.message(from: errorMessage, while: .integration(connector.title)))
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.warning)
    } else if snapshot.isConnected || snapshot.secondaryText != nil {
      statusCard {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          Text("Current import status")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(OmiColors.textTertiary)

          Text(snapshot.primaryText)
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
            .fixedSize(horizontal: false, vertical: true)

          if let secondaryText = snapshot.secondaryText {
            Text(secondaryText)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textSecondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
      }
    } else {
      Text(
        "Start the import here. Once it starts, you can close this window and Omi keeps importing in the background."
      )
      .scaledFont(size: OmiType.caption)
      .foregroundColor(OmiColors.textTertiary)
    }
  }

  private func statusCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    content()
      .padding(OmiSpacing.md)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(OmiColors.backgroundSecondary)
      .cornerRadius(OmiChrome.controlRadius)
  }
}

// MARK: - Shimmer Views

struct ShimmerView: View {
  @State private var isAnimating = false

  var body: some View {
    Rectangle()
      .fill(
        LinearGradient(
          colors: [
            OmiColors.backgroundSecondary,
            OmiColors.backgroundTertiary,
            OmiColors.backgroundSecondary,
          ],
          startPoint: .leading,
          endPoint: .trailing
        )
      )
      .mask(Rectangle())
      .offset(x: isAnimating ? 200 : -200)
      .omiAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false), value: isAnimating)
      .onAppear { isAnimating = true }
  }
}

struct ShimmerAppCard: View {
  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      ShimmerView()
        .frame(width: 60, height: 60)
        .cornerRadius(OmiChrome.smallControlRadius)

      ShimmerView()
        .frame(width: 80, height: 14)
        .cornerRadius(OmiChrome.stripRadius)

      ShimmerView()
        .frame(width: 60, height: 12)
        .cornerRadius(OmiChrome.stripRadius)
    }
    .frame(width: 100)
  }
}

// MARK: - Filter Toggle

struct FilterToggle: View {
  let icon: String
  let label: String
  let isActive: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.caption)
        Text(label)
          .scaledFont(size: OmiType.body)
          .lineLimit(1)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(isActive ? Color.white : OmiColors.backgroundSecondary)
      .foregroundColor(isActive ? Color.black : OmiColors.textSecondary)
      .cornerRadius(OmiChrome.elementRadius)
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isActive ? OmiColors.border : Color.clear, lineWidth: 1)
      )
      .fixedSize(horizontal: true, vertical: false)
    }
    .buttonStyle(.plain)
  }
}

// MARK: - Small Header Button

struct SmallHeaderButton: View {
  let icon: String
  let label: String
  let color: Color
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: icon)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(color)
        Text(label)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
      .cornerRadius(OmiChrome.badgeRadius)
      .fixedSize(horizontal: true, vertical: false)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

// MARK: - Horizontal App Section

struct HorizontalAppSection: View {
  let title: String
  let apps: [OmiApp]
  let appProvider: AppProvider
  let onSelectApp: (OmiApp) -> Void
  var showSeeMore: Bool = false
  var onSeeMore: (() -> Void)? = nil
  var onViewAll: (() -> Void)? = nil

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      Text(title)
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: OmiSpacing.lg) {
          ForEach(apps) { app in
            CompactAppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
          }

          // "See more" button inline with cards
          if showSeeMore, let onSeeMore = onSeeMore {
            Button(action: onSeeMore) {
              VStack(spacing: OmiSpacing.xs) {
                ZStack {
                  RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
                    .fill(OmiColors.backgroundSecondary)
                    .frame(width: 56, height: 56)
                  Image(systemName: "chevron.right")
                    .scaledFont(size: 18, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                }
                Text("See more")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
              .frame(width: 70)
            }
            .buttonStyle(.plain)
          } else if let onViewAll = onViewAll {
            Button(action: onViewAll) {
              VStack(spacing: OmiSpacing.xs) {
                ZStack {
                  RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
                    .fill(OmiColors.backgroundSecondary)
                    .frame(width: 56, height: 56)
                  Image(systemName: "chevron.right")
                    .scaledFont(size: 18, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                }
                Text("View all")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
              .frame(width: 70)
            }
            .buttonStyle(.plain)
          }
        }
      }
    }
  }
}

// MARK: - Grid App Section

struct AppGridSection: View {
  let title: String
  let apps: [OmiApp]
  let appProvider: AppProvider
  let onSelectApp: (OmiApp) -> Void
  var showSeeMore: Bool = false
  var onSeeMore: (() -> Void)? = nil

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text(title)
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        if showSeeMore, let onSeeMore = onSeeMore {
          Button(action: onSeeMore) {
            HStack(spacing: OmiSpacing.xxs) {
              Text("See all")
                .scaledFont(size: OmiType.body, weight: .medium)
              Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.micro, weight: .medium)
            }
            .foregroundColor(OmiColors.textSecondary)
          }
          .buttonStyle(.plain)
        }
      }

      LazyVGrid(
        columns: [
          GridItem(.adaptive(minimum: 220), spacing: OmiSpacing.lg)
        ], spacing: OmiSpacing.lg
      ) {
        ForEach(apps) { app in
          AppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
        }
      }
    }
  }
}

// MARK: - Compact App Card (for horizontal scroll)

struct CompactAppCard: View {
  let app: OmiApp
  let appProvider: AppProvider
  let onSelect: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      VStack(alignment: .center, spacing: OmiSpacing.sm) {
        // App icon
        AsyncImage(url: URL(string: app.image)) { phase in
          switch phase {
          case .success(let image):
            image
              .resizable()
              .aspectRatio(contentMode: .fill)
          default:
            appIconPlaceholder
          }
        }
        .frame(width: 60, height: 60)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.chipRadius))
        .shadow(color: .black.opacity(0.1), radius: 4, y: 2)

        VStack(spacing: OmiSpacing.hairline) {
          Text(app.name)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          // Rating and installs
          HStack(spacing: OmiSpacing.hairline) {
            if let rating = app.formattedRating {
              Image(systemName: "star.fill")
                .scaledFont(size: 8)
                .foregroundColor(.yellow)
              Text(rating)
                .scaledFont(size: OmiType.micro)
                .foregroundColor(OmiColors.textTertiary)
            }
            if let installs = app.formattedInstalls {
              if app.formattedRating != nil {
                Text("·")
                  .scaledFont(size: OmiType.micro)
                  .foregroundColor(OmiColors.textTertiary)
              }
              Text(installs)
                .scaledFont(size: OmiType.micro)
                .foregroundColor(OmiColors.textTertiary)
            }
          }
        }

        // Get/Open button
        SmallAppButton(app: app, appProvider: appProvider, onOpen: onSelect)
      }
      .frame(width: 90)
      .padding(.vertical, OmiSpacing.sm)
      .background(isHovering ? OmiColors.backgroundSecondary.opacity(0.5) : Color.clear)
      .cornerRadius(OmiChrome.smallControlRadius)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }

  private var appIconPlaceholder: some View {
    RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
      .fill(OmiColors.backgroundTertiary)
      .overlay(
        Image(systemName: "app.fill")
          .foregroundColor(OmiColors.textTertiary)
      )
  }
}

// MARK: - Small App Button

struct SmallAppButton: View {
  let app: OmiApp
  let appProvider: AppProvider
  var onOpen: (() -> Void)? = nil

  var body: some View {
    Button(action: {
      if app.enabled {
        // If already enabled, open the app detail
        onOpen?()
      } else {
        // If not enabled, enable it
        Task { await appProvider.toggleApp(app) }
      }
    }) {
      if appProvider.isAppLoading(app.id) {
        ProgressView()
          .scaleEffect(0.6)
          .frame(width: 50, height: 22)
      } else {
        Text(app.enabled ? "Open" : "Install")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(.black)
          .frame(width: 50, height: 22)
          .background(Color.white)
          .cornerRadius(OmiChrome.smallControlRadius)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(OmiColors.border, lineWidth: 1)
          )
      }
    }
    .buttonStyle(.plain)
    .disabled(appProvider.isAppLoading(app.id))
  }
}

// MARK: - App Card (Full)

struct AppCard: View {
  let app: OmiApp
  let appProvider: AppProvider
  let onSelect: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.md) {
          // App icon
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              appIconPlaceholder
            }
          }
          .frame(width: 50, height: 50)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))

          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text(app.name)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)
              .lineLimit(1)

            Text(app.author)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
          }

          Spacer()
        }

        Text(app.description)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(2)
          .multilineTextAlignment(.leading)

        HStack {
          // Rating and installs
          HStack(spacing: OmiSpacing.xs) {
            if let rating = app.formattedRating {
              HStack(spacing: OmiSpacing.hairline) {
                Image(systemName: "star.fill")
                  .scaledFont(size: OmiType.micro)
                  .foregroundColor(.yellow)
                Text(rating)
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }
            if let installs = app.formattedInstalls {
              HStack(spacing: OmiSpacing.hairline) {
                Image(systemName: "arrow.down.circle")
                  .scaledFont(size: OmiType.micro)
                  .foregroundColor(OmiColors.textTertiary)
                Text(installs)
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
              }
            }
          }

          Spacer()

          // Get/Open button
          AppActionButton(app: app, appProvider: appProvider, onOpen: onSelect)
        }
      }
      .padding(OmiSpacing.md)
      .background(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
      .cornerRadius(OmiChrome.smallControlRadius)
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovering = hovering
    }
  }

  private var appIconPlaceholder: some View {
    RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
      .fill(OmiColors.backgroundTertiary)
      .overlay(
        Image(systemName: "app.fill")
          .foregroundColor(OmiColors.textTertiary)
      )
  }
}

// MARK: - App Action Button

struct AppActionButton: View {
  let app: OmiApp
  let appProvider: AppProvider
  var onOpen: (() -> Void)? = nil

  var body: some View {
    Button(action: {
      if app.enabled {
        // If already enabled, open the app detail
        onOpen?()
      } else {
        // If not enabled, enable it
        Task { await appProvider.toggleApp(app) }
      }
    }) {
      if appProvider.isAppLoading(app.id) {
        ProgressView()
          .scaleEffect(0.7)
          .frame(width: 60, height: 28)
      } else {
        Text(app.enabled ? "Open" : "Install")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(.black)
          .frame(width: 60, height: 28)
          .background(Color.white)
          .cornerRadius(OmiChrome.chipRadius)
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.chipRadius)
              .stroke(OmiColors.border, lineWidth: 1)
          )
      }
    }
    .buttonStyle(.plain)
    .disabled(appProvider.isAppLoading(app.id))
  }
}

// MARK: - Filter Sheet

struct AppFilterSheet: View {
  @ObservedObject var appProvider: AppProvider
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text("Filters")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        if hasActiveFilters {
          Button("Clear All") {
            appProvider.clearFilters()
            Task { await appProvider.searchApps() }
          }
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
        }

        DismissButton(action: dismissSheet)
      }
      .padding()

      Divider()
        .background(OmiColors.backgroundTertiary)

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
          // Categories
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Category")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            FlowLayout(spacing: OmiSpacing.sm) {
              ForEach(appProvider.categories) { category in
                FilterChip(
                  label: category.title,
                  isSelected: appProvider.selectedCategory == category.id
                ) {
                  if appProvider.selectedCategory == category.id {
                    appProvider.selectedCategory = nil
                  } else {
                    appProvider.selectedCategory = category.id
                  }
                  Task { await appProvider.searchApps() }
                }
              }
            }
          }

          // Capabilities
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Capability")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            FlowLayout(spacing: OmiSpacing.sm) {
              ForEach(appProvider.capabilities) { capability in
                FilterChip(
                  label: capability.title,
                  isSelected: appProvider.selectedCapability == capability.id
                ) {
                  if appProvider.selectedCapability == capability.id {
                    appProvider.selectedCapability = nil
                  } else {
                    appProvider.selectedCapability = capability.id
                  }
                  Task { await appProvider.searchApps() }
                }
              }
            }
          }

          // Other filters
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Other")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Toggle("Show installed only", isOn: $appProvider.showInstalledOnly)
              .toggleStyle(OmiToggleStyle())
              .foregroundColor(OmiColors.textSecondary)
              .onChange(of: appProvider.showInstalledOnly) { _, _ in
                Task { await appProvider.searchApps() }
              }
          }
        }
        .padding()
      }
    }
    .frame(width: 400, height: 450)
    .background(OmiColors.backgroundPrimary)
  }

  private var hasActiveFilters: Bool {
    appProvider.selectedCategory != nil || appProvider.selectedCapability != nil || appProvider.showInstalledOnly
  }
}

// MARK: - Filter Chip

struct FilterChip: View {
  let label: String
  let isSelected: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Text(label)
        .scaledFont(size: OmiType.body)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(isSelected ? Color.white : OmiColors.backgroundSecondary)
        .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)
        .cornerRadius(OmiChrome.sectionRadius)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.sectionRadius)
            .stroke(isSelected ? OmiColors.border : Color.clear, lineWidth: 1)
        )
    }
    .buttonStyle(.plain)
  }
}

// MARK: - Category Apps Sheet

struct CategoryAppsSheet: View {
  let category: OmiAppCategory
  let appProvider: AppProvider
  let onSelectApp: (OmiApp) -> Void
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var categoryApps: [OmiApp] {
    appProvider.apps(forCategory: category.id)
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        DismissButton(
          action: dismissSheet, icon: "chevron.left", showBackground: false,
          accessibilityLabel: "Back")

        Text(category.title)
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Text("\(categoryApps.count) apps")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding()

      Divider()
        .background(OmiColors.backgroundTertiary)

      ScrollView {
        LazyVGrid(
          columns: [
            GridItem(.flexible(), spacing: OmiSpacing.lg),
            GridItem(.flexible(), spacing: OmiSpacing.lg),
          ], spacing: OmiSpacing.lg
        ) {
          ForEach(categoryApps) { app in
            AppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
          }
        }
        .padding()
      }
    }
    .background(OmiColors.backgroundPrimary)
  }
}

// MARK: - App Detail Sheet

struct AppDetailSheet: View {
  let app: OmiApp
  @ObservedObject var appProvider: AppProvider
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss
  @State private var reviews: [OmiAppReview] = []
  @State private var isLoadingReviews = false
  @State private var showAddReview = false
  @State private var userReview: OmiAppReview?
  @State private var appDetails: OmiAppDetails?
  @State private var isSettingUp = false
  @State private var isSetupCompleted = false
  @State private var setupCheckTask: Task<Void, Never>?

  /// Always read live from appProvider so state survives tab switches and sheet recreations
  var isEnabled: Bool {
    appProvider.apps.first(where: { $0.id == app.id })?.enabled ?? app.enabled
  }

  /// The primary action the detail-sheet button offers, derived once from the
  /// app's enabled + external-integration state. Single source of truth so the
  /// button's label and its action can never diverge: previously an enabled
  /// non-external app rendered an "Open" label whose action fell through to a
  /// destructive `toggleApp` (disable), silently uninstalling the app on tap.
  enum PrimaryAppAction: Equatable {
    case install  // not enabled → install / enable
    case open  // enabled external integration → open in browser
    case hidden  // enabled non-external → no primary action (disable is the trash button)
  }

  nonisolated static func primaryAppAction(isEnabled: Bool, worksExternally: Bool) -> PrimaryAppAction {
    if !isEnabled { return .install }
    return worksExternally ? .open : .hidden
  }

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Spacer()

        DismissButton(action: dismissSheet)
      }
      .padding()

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xl) {
          // App header
          HStack(spacing: OmiSpacing.lg) {
            AsyncImage(url: URL(string: app.image)) { phase in
              switch phase {
              case .success(let image):
                image
                  .resizable()
                  .aspectRatio(contentMode: .fill)
              default:
                RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                  .fill(OmiColors.backgroundTertiary)
              }
            }
            .frame(width: 80, height: 80)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))

            VStack(alignment: .leading, spacing: OmiSpacing.xs) {
              Text(app.name)
                .scaledFont(size: 24, weight: .bold)
                .foregroundColor(OmiColors.textPrimary)

              Text(app.author)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)

              HStack(spacing: OmiSpacing.md) {
                let ratingAvg = appDetails?.ratingAvg ?? app.ratingAvg
                let ratingCount = appDetails?.ratingCount ?? app.ratingCount
                let installs = appDetails?.installs ?? app.installs
                if let ratingAvg, ratingCount > 0 {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "star.fill")
                      .foregroundColor(.yellow)
                    Text(String(format: "%.1f", ratingAvg))
                    Text("(\(ratingCount))")
                  }
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                }
                if installs > 0 {
                  Text("\(installs) installs")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.textSecondary)
                }
              }
            }

            Spacer()

            // Action button
            let primaryAction = Self.primaryAppAction(isEnabled: isEnabled, worksExternally: app.worksExternally)
            HStack(spacing: OmiSpacing.sm) {
              // Only render a primary button when there is a real action:
              // install/enable, or open an external integration. An enabled
              // non-external app has no "open" target — disable is owned by
              // the trash button, so we never show a primary button that
              // would otherwise fire a destructive toggle under an "Open" label.
              if primaryAction != .hidden {
                Button(action: {
                  Task {
                    switch primaryAction {
                    case .open:
                      // Open the external integration in browser
                      openExternalApp()
                    case .install:
                      if app.worksExternally {
                        await handleInstall()
                      } else {
                        await appProvider.toggleApp(app)
                      }
                    case .hidden:
                      break
                    }
                  }
                }) {
                  if appProvider.isAppLoading(app.id) {
                    ProgressView()
                      .frame(width: 100, height: 36)
                  } else if isSettingUp {
                    HStack(spacing: OmiSpacing.xs) {
                      ProgressView()
                        .scaleEffect(0.7)
                      Text("Setting up...")
                        .scaledFont(size: OmiType.caption, weight: .semibold)
                    }
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(width: 120, height: 36)
                  } else {
                    Text(primaryAction == .open ? "Open" : "Install")
                      .scaledFont(size: OmiType.body, weight: .semibold)
                      .foregroundColor(.black)
                      .frame(width: 100, height: 36)
                      .background(Color.white)
                      .cornerRadius(OmiChrome.controlRadius)
                      .overlay(
                        RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                          .stroke(OmiColors.border, lineWidth: 1)
                      )
                  }
                }
                .buttonStyle(.plain)
              }

              // Disable button shown only when app is enabled
              if isEnabled && !appProvider.isAppLoading(app.id) && !isSettingUp {
                Button(action: {
                  Task { await appProvider.toggleApp(app) }
                }) {
                  Image(systemName: "trash")
                    .scaledFont(size: OmiType.body)
                    .foregroundColor(OmiColors.error)
                    .frame(width: 36, height: 36)
                    .background(OmiColors.error.opacity(0.1))
                    .cornerRadius(OmiChrome.controlRadius)
                }
                .buttonStyle(.plain)
              }
            }
          }

          Divider()
            .background(OmiColors.backgroundTertiary)

          // Description
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("About")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(app.description)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
              .fixedSize(horizontal: false, vertical: true)
          }

          // Setup steps (external integration)
          if let integration = appDetails?.externalIntegration, !integration.authSteps.isEmpty {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              ForEach(Array(integration.authSteps.enumerated()), id: \.offset) { index, step in
                Button(action: {
                  if let uid = AuthState.shared.userId,
                    let url = URL(string: "\(step.url)?uid=\(uid)")
                  {
                    NSWorkspace.shared.open(url)
                  }
                }) {
                  HStack(spacing: OmiSpacing.md) {
                    // Step number / checkmark
                    ZStack {
                      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                        .fill(isSetupCompleted ? Color.green.opacity(0.15) : OmiColors.backgroundTertiary)
                        .frame(width: 40, height: 40)
                      if isSetupCompleted {
                        Image(systemName: "checkmark")
                          .scaledFont(size: OmiType.body, weight: .semibold)
                          .foregroundColor(.green)
                      } else {
                        Text("\(index + 1)")
                          .scaledFont(size: OmiType.body, weight: .semibold)
                          .foregroundColor(OmiColors.textSecondary)
                      }
                    }

                    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                      Text(step.name)
                        .scaledFont(size: OmiType.body, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                      Text(isSetupCompleted ? "Completed" : "Click to complete")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(isSetupCompleted ? .green : OmiColors.textTertiary)
                    }

                    Spacer()

                    Image(systemName: "arrow.up.right.square")
                      .scaledFont(size: OmiType.body)
                      .foregroundColor(OmiColors.textTertiary)
                  }
                  .padding(OmiSpacing.md)
                  .background(OmiColors.backgroundSecondary)
                  .cornerRadius(OmiChrome.smallControlRadius)
                }
                .buttonStyle(.plain)
              }
            }
          }

          // Capabilities
          if !app.capabilities.isEmpty {
            VStack(alignment: .leading, spacing: OmiSpacing.sm) {
              Text("Capabilities")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              FlowLayout(spacing: OmiSpacing.sm) {
                ForEach(app.capabilities, id: \.self) { capability in
                  CapabilityBadge(capability: capability)
                }
              }
            }
          }

          // Category
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Category")
              .scaledFont(size: OmiType.subheading, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(app.category.replacingOccurrences(of: "-", with: " ").capitalized)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
          }

          Divider()
            .background(OmiColors.backgroundTertiary)

          // Add Review Section
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            HStack {
              Text("Reviews")
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Spacer()

              if userReview == nil {
                Button(action: { showAddReview = true }) {
                  HStack(spacing: OmiSpacing.xxs) {
                    Image(systemName: "plus")
                      .scaledFont(size: OmiType.caption, weight: .medium)
                    Text("Add Review")
                      .scaledFont(size: OmiType.body, weight: .medium)
                  }
                  .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
              }
            }

            // User's own review (if exists)
            if let userReview = userReview {
              VStack(alignment: .leading, spacing: OmiSpacing.sm) {
                HStack {
                  Text("Your Review")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                  Spacer()

                  Button(action: { showAddReview = true }) {
                    Text("Edit")
                      .scaledFont(size: OmiType.caption, weight: .medium)
                      .foregroundColor(OmiColors.textTertiary)
                  }
                  .buttonStyle(.plain)
                }

                ReviewCard(review: userReview)
              }
            }

            // Other reviews
            let otherReviews = reviews.filter { $0.uid != userReview?.uid }
            if !otherReviews.isEmpty {
              ForEach(otherReviews.prefix(3)) { review in
                ReviewCard(review: review)
              }
            } else if userReview == nil && reviews.isEmpty {
              Text("No reviews yet. Be the first to review this app.")
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.vertical, OmiSpacing.sm)
            }
          }
        }
        .padding()
      }
    }
    .frame(width: 500, height: 600)
    .background(OmiColors.backgroundPrimary)
    .task {
      await loadReviews()
      await loadAppDetails()
      // Resume polling if user completed setup in browser and returned to this sheet
      await resumeSetupPollingIfNeeded()
    }
    .onDisappear {
      setupCheckTask?.cancel()
    }
    .dismissableSheet(isPresented: $showAddReview) {
      AddReviewSheet(
        app: app,
        existingReview: userReview,
        onReviewSubmitted: { review in
          userReview = review
          // Refresh reviews to get updated list
          Task { await loadReviews() }
        },
        onDismiss: { showAddReview = false }
      )
      .frame(width: 400, height: 500)
    }
  }

  private func loadReviews() async {
    isLoadingReviews = true
    defer { isLoadingReviews = false }

    do {
      reviews = try await APIClient.shared.getAppReviews(appId: app.id)
      // Check if current user has a review
      if let currentUserId = AuthState.shared.userId {
        userReview = reviews.first { $0.uid == currentUserId }
      }
    } catch {
      // Silently fail - reviews are optional
    }
  }

  private func loadAppDetails() async {
    do {
      appDetails = try await APIClient.shared.getAppDetails(appId: app.id)
    } catch {
      // Silently fail - details are optional, setup flow will just skip if unavailable
    }
  }

  /// Called on sheet appear — if setup was already completed in browser, enable the app immediately.
  /// If setup is still pending, restart polling so the UI updates when the user finishes in the browser.
  private func resumeSetupPollingIfNeeded() async {
    guard let uid = AuthState.shared.userId,
      let integration = appDetails?.externalIntegration,
      let completionUrl = integration.setupCompletedUrl,
      !completionUrl.isEmpty
    else {
      // No setup URL — if app is already enabled, treat steps as completed
      if isEnabled { isSetupCompleted = true }
      return
    }

    // If already installed, setup must have been completed — mark it without hitting the network
    if isEnabled {
      isSetupCompleted = true
      return
    }

    // Immediate check — if setup already done in browser, mark complete and enable
    let alreadyDone = await APIClient.shared.isAppSetupCompleted(url: completionUrl, uid: uid)
    if alreadyDone {
      isSetupCompleted = true
      await appProvider.enableApp(app)
      return
    }

    // Not done yet — silently poll in background so the step card updates when the user finishes in browser
    // Don't set isSettingUp=true here (that's only for when the user explicitly clicked Install)
    startSetupPolling(completionUrl: completionUrl, uid: uid)
  }

  private func openExternalApp() {
    guard let uid = AuthState.shared.userId else { return }
    let integration = appDetails?.externalIntegration
    // Prefer appHomeUrl, then first auth step URL
    if let homeUrl = integration?.appHomeUrl, !homeUrl.isEmpty, let url = URL(string: homeUrl) {
      NSWorkspace.shared.open(url)
    } else if let authSteps = integration?.authSteps, !authSteps.isEmpty,
      let url = URL(string: "\(authSteps[0].url)?uid=\(uid)")
    {
      NSWorkspace.shared.open(url)
    }
  }

  private func handleInstall() async {
    // Step 1: Try to enable. Backend returns 400 if setup is not yet complete.
    await appProvider.enableApp(app)

    // Step 2: If enable succeeded (no setup required), we're done.
    if isEnabled { return }

    // Step 3: Enable failed — app requires setup first. Open browser and wait.
    // Ensure app details are loaded before navigating to setup.
    if appDetails == nil { await loadAppDetails() }
    await navigateToSetup()
  }

  private func navigateToSetup() async {
    guard let uid = AuthState.shared.userId else { return }
    let integration = appDetails?.externalIntegration

    // Open auth step or setup instructions URL in browser
    if let authSteps = integration?.authSteps, !authSteps.isEmpty {
      let rawUrl = "\(authSteps[0].url)?uid=\(uid)"
      if let url = URL(string: rawUrl) {
        NSWorkspace.shared.open(url)
      }
    } else if let instructionsPath = integration?.setupInstructionsFilePath, !instructionsPath.isEmpty {
      if let url = URL(string: instructionsPath) {
        NSWorkspace.shared.open(url)
      }
    }

    // Poll for completion only if there is a setup_completed_url to check
    if let completionUrl = integration?.setupCompletedUrl, !completionUrl.isEmpty {
      isSettingUp = true
      startSetupPolling(completionUrl: completionUrl, uid: uid)
    }
  }

  private func startSetupPolling(completionUrl: String, uid: String) {
    setupCheckTask?.cancel()
    setupCheckTask = Task {
      var tickCount = 0
      while !Task.isCancelled && tickCount < 100 {
        tickCount += 1
        try? await Task.sleep(nanoseconds: 3_000_000_000)
        if Task.isCancelled { break }

        let completed = await APIClient.shared.isAppSetupCompleted(url: completionUrl, uid: uid)
        if completed {
          await MainActor.run {
            isSetupCompleted = true
            isSettingUp = false
          }
          // Enable the app now that setup is done
          if !isEnabled { await appProvider.enableApp(app) }
          break
        }
      }
      await MainActor.run { isSettingUp = false }
    }
  }
}

// MARK: - Add Review Sheet

struct AddReviewSheet: View {
  let app: OmiApp
  let existingReview: OmiAppReview?
  let onReviewSubmitted: (OmiAppReview) -> Void
  var onDismiss: (() -> Void)? = nil

  @Environment(\.dismiss) private var environmentDismiss
  @State private var selectedRating: Int
  @State private var reviewText: String
  @State private var isSubmitting = false
  @State private var errorMessage: String?

  private let maxReviewLength = 500

  init(
    app: OmiApp, existingReview: OmiAppReview?, onReviewSubmitted: @escaping (OmiAppReview) -> Void,
    onDismiss: (() -> Void)? = nil
  ) {
    self.app = app
    self.existingReview = existingReview
    self.onReviewSubmitted = onReviewSubmitted
    self.onDismiss = onDismiss
    _selectedRating = State(initialValue: existingReview?.score ?? 0)
    _reviewText = State(initialValue: existingReview?.review ?? "")
  }

  private func dismissSheet() {
    if let onDismiss = onDismiss {
      onDismiss()
    } else {
      environmentDismiss()
    }
  }

  var isFormValid: Bool {
    selectedRating > 0 && !reviewText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        // Placeholder for symmetry
        Color.clear
          .frame(width: 28, height: 28)

        Spacer()

        Text(existingReview != nil ? "Edit Review" : "Add Review")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        DismissButton(action: dismissSheet)
      }
      .padding()

      Divider()
        .background(OmiColors.backgroundTertiary)

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
          // App info
          HStack(spacing: OmiSpacing.md) {
            AsyncImage(url: URL(string: app.image)) { phase in
              switch phase {
              case .success(let image):
                image
                  .resizable()
                  .aspectRatio(contentMode: .fill)
              default:
                RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                  .fill(OmiColors.backgroundTertiary)
              }
            }
            .frame(width: 50, height: 50)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))

            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
              Text(app.name)
                .scaledFont(size: OmiType.subheading, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

              Text(app.author)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
            }

            Spacer()
          }

          // Star Rating Picker
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Your Rating")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            StarRatingPicker(rating: $selectedRating)
          }

          // Review Text
          VStack(alignment: .leading, spacing: OmiSpacing.md) {
            HStack {
              Text("Your Review")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

              Spacer()

              Text("\(reviewText.count)/\(maxReviewLength)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(reviewText.count > maxReviewLength ? OmiColors.error : OmiColors.textTertiary)
            }

            ZStack(alignment: .topLeading) {
              TextEditor(text: $reviewText)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 120, maxHeight: 200)
                .padding(OmiSpacing.md)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(OmiChrome.smallControlRadius)
                .overlay(
                  RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                    .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
                )
                .onChange(of: reviewText) { _, newValue in
                  if newValue.count > maxReviewLength {
                    reviewText = String(newValue.prefix(maxReviewLength))
                  }
                }

              if reviewText.isEmpty {
                Text("Share your experience with this app...")
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textTertiary)
                  .padding(.leading, OmiSpacing.lg)
                  .padding(.top, OmiSpacing.xl)
                  .allowsHitTesting(false)
              }
            }
          }

          // Error message
          if let errorMessage = errorMessage {
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "exclamationmark.circle.fill")
                .foregroundColor(OmiColors.error)
              Text(errorMessage)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.error)
            }
          }

          // Submit button
          Button(action: submitReview) {
            HStack {
              if isSubmitting {
                ProgressView()
                  .scaleEffect(0.8)
                  .tint(OmiColors.textPrimary)
              } else {
                Text(existingReview != nil ? "Update Review" : "Submit Review")
                  .scaledFont(size: OmiType.body, weight: .semibold)
              }
            }
            .foregroundColor(OmiColors.textPrimary)
            .frame(maxWidth: .infinity)
            .frame(height: 44)
            .background(isFormValid ? Color.white : Color.white.opacity(0.5))
            .cornerRadius(OmiChrome.smallControlRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .stroke(OmiColors.border, lineWidth: 1)
            )
          }
          .buttonStyle(.plain)
          .disabled(!isFormValid || isSubmitting)
        }
        .padding()
      }
    }
    .frame(width: 400, height: 480)
    .background(OmiColors.backgroundPrimary)
  }

  private func submitReview() {
    guard isFormValid else { return }

    isSubmitting = true
    errorMessage = nil

    Task {
      do {
        let review = try await APIClient.shared.submitAppReview(
          appId: app.id,
          score: selectedRating,
          review: reviewText.trimmingCharacters(in: .whitespacesAndNewlines)
        )
        await MainActor.run {
          onReviewSubmitted(review)
          dismissSheet()
        }
      } catch {
        await MainActor.run {
          errorMessage = "Failed to submit review. Please try again."
          isSubmitting = false
        }
      }
    }
  }
}

// MARK: - Star Rating Picker

struct StarRatingPicker: View {
  @Binding var rating: Int
  var maxRating: Int = 5
  var starSize: CGFloat = 32

  @State private var hoverRating: Int = 0

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      ForEach(1...maxRating, id: \.self) { star in
        Image(systemName: starImage(for: star))
          .scaledFont(size: starSize)
          .foregroundColor(starColor(for: star))
          .onTapGesture {
            OmiMotion.withGated(.easeInOut(duration: 0.15)) {
              rating = star
            }
          }
          .onHover { hovering in
            hoverRating = hovering ? star : 0
          }
          .scaleEffect(scaleEffect(for: star))
          .omiAnimation(.easeInOut(duration: 0.1), value: hoverRating)
      }

      if rating > 0 {
        Text(ratingLabel)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          .padding(.leading, OmiSpacing.sm)
      }
    }
  }

  private func starImage(for star: Int) -> String {
    let effectiveRating = hoverRating > 0 ? hoverRating : rating
    return star <= effectiveRating ? "star.fill" : "star"
  }

  private func starColor(for star: Int) -> Color {
    let effectiveRating = hoverRating > 0 ? hoverRating : rating
    return star <= effectiveRating ? .yellow : OmiColors.textTertiary.opacity(0.5)
  }

  private func scaleEffect(for star: Int) -> CGFloat {
    if hoverRating == star {
      return 1.15
    }
    return 1.0
  }

  private var ratingLabel: String {
    switch rating {
    case 1: return "Poor"
    case 2: return "Fair"
    case 3: return "Good"
    case 4: return "Very Good"
    case 5: return "Excellent"
    default: return ""
    }
  }
}

// MARK: - Capability Badge

struct CapabilityBadge: View {
  let capability: String

  var icon: String {
    switch capability {
    case "chat": return "bubble.left.and.bubble.right"
    case "memories": return "brain"
    case "persona": return "person.crop.circle"
    case "external_integration": return "link"
    case "proactive_notification": return "bell"
    default: return "app"
    }
  }

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.micro)
      Text(capability.replacingOccurrences(of: "_", with: " ").capitalized)
        .scaledFont(size: OmiType.caption)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.xs)
    .background(OmiColors.backgroundSecondary)
    .foregroundColor(OmiColors.textSecondary)
    .cornerRadius(OmiChrome.controlRadius)
  }
}

// MARK: - Review Card

struct ReviewCard: View {
  let review: OmiAppReview

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack {
        // Rating stars
        HStack(spacing: OmiSpacing.hairline) {
          ForEach(1...5, id: \.self) { star in
            Image(systemName: star <= review.score ? "star.fill" : "star")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(star <= review.score ? .yellow : OmiColors.textTertiary)
          }
        }

        Spacer()

        Text(review.ratedAt, style: .date)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }

      Text(review.review)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)
        .lineLimit(3)

      if let response = review.response {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Developer Response")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)

          Text(response)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textSecondary)
            .lineLimit(2)
        }
        .padding(OmiSpacing.sm)
        .background(OmiColors.backgroundSecondary)
        .cornerRadius(OmiChrome.elementRadius)
      }
    }
    .padding(OmiSpacing.md)
    .background(OmiColors.backgroundSecondary.opacity(0.5))
    .cornerRadius(OmiChrome.smallControlRadius)
  }
}

// MARK: - Flow Layout Helper

struct FlowLayout: Layout {
  var spacing: CGFloat = 8

  struct CacheData {
    var result: FlowResult?
    var width: CGFloat = 0
  }

  func makeCache(subviews: Subviews) -> CacheData {
    CacheData()
  }

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout CacheData) -> CGSize {
    let width = proposal.width ?? 0
    let result = FlowResult(in: width, subviews: subviews, spacing: spacing)
    cache.result = result
    cache.width = width
    return result.size
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout CacheData) {
    let result: FlowResult
    if let cached = cache.result, cache.width == bounds.width {
      result = cached
    } else {
      result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
    }
    for (index, subview) in subviews.enumerated() {
      let idealSize = subview.sizeThatFits(.unspecified)
      let subProposal: ProposedViewSize =
        idealSize.width > bounds.width
        ? ProposedViewSize(width: bounds.width, height: nil)
        : .unspecified
      subview.place(
        at: CGPoint(
          x: bounds.minX + result.positions[index].x,
          y: bounds.minY + result.positions[index].y),
        proposal: subProposal)
    }
  }

  struct FlowResult {
    var size: CGSize = .zero
    var positions: [CGPoint] = []

    init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
      var x: CGFloat = 0
      var y: CGFloat = 0
      var rowHeight: CGFloat = 0

      for subview in subviews {
        var size = subview.sizeThatFits(.unspecified)

        // Constrain oversized items to available width
        if size.width > maxWidth {
          size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
        }

        if x + size.width > maxWidth && x > 0 {
          x = 0
          y += rowHeight + spacing
          rowHeight = 0
        }

        positions.append(CGPoint(x: x, y: y))
        rowHeight = max(rowHeight, size.height)
        x += size.width + spacing
        self.size.width = max(self.size.width, min(x, maxWidth))
      }

      self.size.height = y + rowHeight
    }
  }
}

// MARK: - Dismissable Sheet
/// A sheet that can be dismissed by clicking outside the content area.
/// This provides macOS-friendly modal behavior where clicking the dimmed background dismisses the sheet.

/// Maps Esc to a dismiss closure for custom overlay modals. These overlays are
/// ZStack layers, not NSWindow sheets, so AppKit gives them no cancel handling,
/// `onExitCommand` needs focus they never receive, and hidden SwiftUI buttons
/// with a cancel key equivalent get culled from key-equivalent dispatch. A
/// local key-down monitor scoped to the hosting window delivers Esc
/// deterministically. Render it only while its overlay is the topmost modal.
struct OverlayModalEscapeCatcher: NSViewRepresentable {
  let action: () -> Void

  func makeNSView(context: Context) -> EscapeCatcherView {
    let view = EscapeCatcherView()
    view.onEscape = action
    return view
  }

  func updateNSView(_ nsView: EscapeCatcherView, context: Context) {
    nsView.onEscape = action
  }

  final class EscapeCatcherView: NSView {
    var onEscape: (() -> Void)?
    private nonisolated(unsafe) var monitor: Any?

    override func viewDidMoveToWindow() {
      super.viewDidMoveToWindow()
      if window != nil {
        installMonitor()
      } else {
        removeMonitor()
      }
    }

    // Never intercept mouse events — this view exists only for the monitor.
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    private func installMonitor() {
      guard monitor == nil else { return }
      monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
        guard
          let self,
          event.keyCode == 53,  // Esc
          let window = self.window,
          event.window === window
        else { return event }
        self.onEscape?()
        // Consume the event — while the overlay is up it owns Esc.
        return nil
      }
    }

    private func removeMonitor() {
      if let monitor {
        NSEvent.removeMonitor(monitor)
        self.monitor = nil
      }
    }

    deinit {
      // Deinitialization is nonisolated. The monitor is main-thread-only,
      // while NSEvent.removeMonitor is safe to invoke from this boundary.
      if let monitor {
        NSEvent.removeMonitor(monitor)
      }
    }
  }
}

struct DismissableSheetModifier<SheetContent: View>: ViewModifier {
  @Binding var isPresented: Bool
  let sheetContent: () -> SheetContent

  func body(content: Content) -> some View {
    content
      // The overlay is modal: while it is up, the content underneath must
      // not be reachable by VoiceOver / Full Keyboard Access.
      .accessibilityHidden(isPresented)
      .overlay {
        ZStack {
          if isPresented {
            // Dimmed background that dismisses on tap.
            Color.black.opacity(0.3)
              .ignoresSafeArea()
              .contentShape(Rectangle())
              .onTapGesture {
                log("DISMISSABLE_SHEET: Background tapped, dismissing")
                OmiMotion.withGated(.easeOut(duration: 0.2)) {
                  isPresented = false
                }
              }
              .transition(.opacity)
              .zIndex(0)

            // Force the sheet into a centered full-size overlay so it
            // does not end up clipped or visually hidden behind the scrim.
            sheetContent()
              .background(OmiColors.backgroundPrimary)
              .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
              .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
              .transition(.scale(scale: 0.95).combined(with: .opacity))
              .accessibilityAddTraits(.isModal)
              .zIndex(1)

            OverlayModalEscapeCatcher {
              log("DISMISSABLE_SHEET: Escape pressed, dismissing")
              OmiMotion.withGated(.easeOut(duration: 0.2)) {
                isPresented = false
              }
            }
            .zIndex(2)
          }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .omiAnimation(.easeOut(duration: 0.2), value: isPresented)
  }
}

extension View {
  /// Presents a sheet that can be dismissed by clicking outside the content area.
  func dismissableSheet<Content: View>(
    isPresented: Binding<Bool>,
    @ViewBuilder content: @escaping () -> Content
  ) -> some View {
    self.modifier(DismissableSheetModifier(isPresented: isPresented, sheetContent: content))
  }

  /// Presents an item-based sheet that can be dismissed by clicking outside the content area.
  func dismissableSheet<Item: Identifiable, Content: View>(
    item: Binding<Item?>,
    @ViewBuilder content: @escaping (Item) -> Content
  ) -> some View {
    self.modifier(DismissableSheetItemModifier(item: item, sheetContent: content))
  }
}

/// Item-based version of DismissableSheetModifier for optional item bindings.
struct DismissableSheetItemModifier<Item: Identifiable, SheetContent: View>: ViewModifier {
  @Binding var item: Item?
  let sheetContent: (Item) -> SheetContent

  func body(content: Content) -> some View {
    content
      // The overlay is modal: while it is up, the content underneath must
      // not be reachable by VoiceOver / Full Keyboard Access.
      .accessibilityHidden(item != nil)
      .overlay {
        ZStack {
          if let presentedItem = item {
            // Dimmed background that dismisses on tap.
            Color.black.opacity(0.3)
              .ignoresSafeArea()
              .contentShape(Rectangle())
              .onTapGesture {
                log("DISMISSABLE_SHEET: Background tapped, dismissing item")
                OmiMotion.withGated(.easeOut(duration: 0.2)) {
                  item = nil
                }
              }
              .transition(.opacity)
              .zIndex(0)

            // Force the sheet into a centered full-size overlay so it
            // does not end up clipped or visually hidden behind the scrim.
            sheetContent(presentedItem)
              .background(OmiColors.backgroundPrimary)
              .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
              .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
              .transition(.scale(scale: 0.95).combined(with: .opacity))
              .accessibilityAddTraits(.isModal)
              .zIndex(1)

            OverlayModalEscapeCatcher {
              log("DISMISSABLE_SHEET: Escape pressed, dismissing item")
              OmiMotion.withGated(.easeOut(duration: 0.2)) {
                item = nil
              }
            }
            .zIndex(2)
          }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .omiAnimation(.easeOut(duration: 0.2), value: item?.id != nil)
  }
}

// MARK: - Create App Card
/// Simple card button for creating apps or persona

struct CreateAppCard: View {
  let icon: String
  let iconColor: Color
  let title: String
  let onTap: () -> Void

  @State private var isHovering = false

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      // Icon
      ZStack {
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(iconColor.opacity(0.15))
          .frame(width: 44, height: 44)

        Image(systemName: icon)
          .scaledFont(size: OmiType.heading)
          .foregroundColor(iconColor)
      }

      Text(title)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      Spacer()

      Image(systemName: "chevron.right")
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
    }
    .padding(OmiSpacing.md)
    .frame(maxWidth: .infinity)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
            .stroke(iconColor.opacity(0.3), lineWidth: 1)
        )
    )
    .contentShape(Rectangle())
    .onTapGesture {
      onTap()
    }
    .onHover { isHovering = $0 }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    AppsPage(appProvider: AppProvider())
      .frame(width: 900, height: 700)
  }
#endif
