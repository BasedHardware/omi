import AppKit
import GRDB
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
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(isPressed ? OmiColors.textTertiary : OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(showBackground ? OmiColors.backgroundSecondary : Color.clear)
            .clipShape(Circle())
            .contentShape(Circle())
            .opacity(isPressed ? 0.7 : 1.0)
            .onTapGesture {
                guard !isPressed else { return } // Prevent double-tap
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
                    try? await Task.sleep(nanoseconds: 250_000_000) // 250ms
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
struct DismissButton: View {
    let action: () -> Void
    var icon: String = "xmark"
    var showBackground: Bool = true

    @State private var isPressed = false

    var body: some View {
        Image(systemName: icon)
            .scaledFont(size: 14, weight: .medium)
            .foregroundColor(isPressed ? OmiColors.textTertiary : OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(showBackground ? OmiColors.backgroundSecondary : Color.clear)
            .clipShape(Circle())
            .contentShape(Circle())
            .opacity(isPressed ? 0.7 : 1.0)
            .onTapGesture {
                guard !isPressed else { return }
                isPressed = true

                log("DISMISS_BUTTON: Tap gesture fired")

                // Consume the click by resigning first responder
                NSApp.keyWindow?.makeFirstResponder(nil)

                // Small delay then dismiss
                Task { @MainActor in
                    try? await Task.sleep(nanoseconds: 50_000_000) // 50ms
                    log("DISMISS_BUTTON: Calling action")
                    withAnimation(.easeOut(duration: 0.2)) {
                        action()
                    }
                }
            }
    }
}

struct AppsPage: View {
    @ObservedObject var appProvider: AppProvider
    var appState: AppState? = nil
    @StateObject private var connectorStatusStore = ImportConnectorStatusStore()
    @State private var searchText = ""
    @State private var selectedApp: OmiApp?
    @State private var selectedConnector: ImportConnector?
    @State private var selectedExportDestination: MemoryExportDestination?
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
            } else if appProvider.apps.isEmpty && appProvider.popularApps.isEmpty {
                emptyView
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 24) {
                        if !searchText.isEmpty || hasActiveFilters {
                            // Show filtered/search results in a flat grid
                            if appProvider.isSearching {
                                // Loading state for category filter
                                VStack(spacing: 16) {
                                    ProgressView()
                                        .scaleEffect(1.2)
                                    Text("Loading...")
                                        .scaledFont(size: 14)
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 200)
                            } else if filteredApps.isEmpty {
                                VStack(spacing: 12) {
                                    Image(systemName: "magnifyingglass")
                                        .scaledFont(size: 32)
                                        .foregroundColor(OmiColors.textTertiary)
                                    Text("No apps found")
                                        .scaledFont(size: 16, weight: .medium)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                                .frame(maxWidth: .infinity, minHeight: 200)
                            } else {
                                // Back button for "See more" view
                                if viewAllSection != nil {
                                    Button(action: { viewAllSection = nil }) {
                                        HStack(spacing: 6) {
                                            Image(systemName: "chevron.left")
                                                .scaledFont(size: 12, weight: .medium)
                                            Text("Back")
                                                .scaledFont(size: 13, weight: .medium)
                                        }
                                        .foregroundColor(OmiColors.textSecondary)
                                    }
                                    .buttonStyle(.plain)
                                }

                                AppGridSection(
                                    title: filterResultsTitle,
                                    apps: filteredApps,
                                    appProvider: appProvider,
                                    onSelectApp: { selectedApp = $0 }
                                )

                                // Infinite scroll: load more when reaching bottom
                                if appProvider.hasMoreCategoryApps {
                                    HStack {
                                        Spacer()
                                        if appProvider.isLoadingMore {
                                            ProgressView()
                                                .scaleEffect(0.8)
                                            Text("Loading more...")
                                                .scaledFont(size: 13)
                                                .foregroundColor(OmiColors.textTertiary)
                                        } else {
                                            Color.clear
                                                .frame(height: 1)
                                                .onAppear {
                                                    Task {
                                                        await appProvider.loadMoreCategoryApps()
                                                    }
                                                }
                                        }
                                        Spacer()
                                    }
                                    .padding(.vertical, 16)
                                }
                            }
                        } else {
                            ImportsSection(statusStore: connectorStatusStore) { connector in
                                selectedConnector = connector
                            }

                            ExportsSection(statuses: exportStatuses) { destination in
                                selectedExportDestination = destination
                            }

                            // Featured section (apps marked as is_popular in backend)
                            if !appProvider.popularApps.isEmpty {
                                AppGridSection(
                                    title: "Featured",
                                    apps: Array(appProvider.popularApps.prefix(6)),
                                    appProvider: appProvider,
                                    onSelectApp: { selectedApp = $0 },
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
                                    onSelectApp: { selectedApp = $0 },
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
                                    onSelectApp: { selectedApp = $0 },
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
                if appProvider.selectedCategory != nil {
                    appProvider.clearCategoryFilter()
                }
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
            })
            .frame(width: 520, height: 620)
        }
        .dismissableSheet(item: $selectedExportDestination) { destination in
            MemoryExportDestinationSheet(
                destination: destination,
                statuses: $exportStatuses,
                onDismiss: {
                    selectedExportDestination = nil
                }
            )
            .frame(width: 520, height: 620)
        }
        .onAppear {
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
        .task {
            await connectorStatusStore.refresh()
            exportStatuses = await MemoryExportService.shared.allStatuses()
        }
    }

    private var searchBar: some View {
        HStack(spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(OmiColors.textTertiary)

                TextField("Search apps...", text: $searchText)
                    .textFieldStyle(.plain)
                    .foregroundColor(OmiColors.textPrimary)

                if !searchText.isEmpty {
                    Button(action: { searchText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(10)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(10)

            // Filter toggles
            FilterToggle(
                icon: "arrow.down.circle",
                label: "Installed",
                isActive: appProvider.showInstalledOnly
            ) {
                viewAllSection = nil
                appProvider.showInstalledOnly.toggle()
                Task { await appProvider.searchApps() }
            }

            // Category dropdown
            Menu {
                Button(action: {
                    viewAllSection = nil
                    appProvider.clearCategoryFilter()
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
                        Task { await appProvider.fetchAppsForCategory(category.id) }
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
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease.circle")
                        .scaledFont(size: 12)
                    Text(selectedCategoryLabel)
                        .scaledFont(size: 13)
                    Image(systemName: "chevron.down")
                        .scaledFont(size: 9, weight: .medium)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(OmiColors.backgroundSecondary)
                .foregroundColor(OmiColors.textPrimary)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(appProvider.selectedCategory != nil ? OmiColors.border : Color.clear, lineWidth: 1)
                )
            }
            .menuStyle(.borderlessButton)
            .fixedSize()

            Spacer()

            // Create buttons (compact)
            HStack(spacing: 8) {
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
        }
    }

    private var hasActiveFilters: Bool {
        appProvider.selectedCategory != nil || viewAllSection != nil
    }

    private var selectedCategoryLabel: String {
        if let categoryId = appProvider.selectedCategory,
           let category = appProvider.categories.first(where: { $0.id == categoryId }) {
            return category.title
        }
        return "Category"
    }

    /// Apps for the selected category (from API) or search results or "See more" section
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
        if appProvider.selectedCategory != nil {
            return appProvider.categoryFilteredApps ?? []
        }
        return appProvider.apps
    }

    private var filterResultsTitle: String {
        let apps = filteredApps
        // "See more" section title
        if let section = viewAllSection {
            let title = switch section {
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
           let category = appProvider.categories.first(where: { $0.id == categoryId }) {
            return "\(category.title) (\(apps.count))"
        }
        return "Results (\(apps.count))"
    }


    private var loadingShimmerView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                // Shimmer sections
                ForEach(0..<3, id: \.self) { _ in
                    VStack(alignment: .leading, spacing: 12) {
                        ShimmerView()
                            .frame(width: 120, height: 24)
                            .cornerRadius(6)

                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 16) {
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
        VStack(spacing: 16) {
            Image(systemName: "square.grid.2x2")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text("No apps found")
                .scaledFont(size: 20, weight: .semibold)
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
            statusText: "Connected",
            metricText: "Available on this device",
            actionTitle: "Connected",
            isConnected: true
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

    private let defaults: UserDefaults
    private let sourceCountKeyPrefix = "appsImportConnectorSourceCount."
    private let memoryCountKeyPrefix = "appsImportConnectorMemoryCount."
    private let lastSyncedAtKeyPrefix = "appsImportConnectorLastSyncedAt."
    private let lastDeltaCountKeyPrefix = "appsImportConnectorLastDeltaCount."
    private let hasLastDeltaKeyPrefix = "appsImportConnectorHasLastDelta."
    private let manualConnectorIDs: Set<String> = ["chatgpt", "claude"]
    private let appleNotesFolderDefaultsKey = "onboardingAppleNotesFolderPath"
    private let onboardingChatGPTImportedMemoriesKey = "onboardingChatGPTImportedMemoriesCount"
    private let onboardingClaudeImportedMemoriesKey = "onboardingClaudeImportedMemoriesCount"

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        load()
    }

    func snapshot(for connector: ImportConnector) -> Snapshot {
        let metrics = metricsByID[connector.id] ?? ConnectorMetrics()
        let isConnected =
            metrics.memoryCount.map { $0 > 0 } ?? false
            || metrics.sourceCount.map { $0 > 0 } ?? false
            || metrics.availabilityText != nil
            || connector.id == "local-files"
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
            defaults.set(metrics.sourceCount, forKey: sourceCountKeyPrefix + connectorID)
        }
        if let memoryCount {
            metrics.memoryCount = max(memoryCount, 0)
            defaults.set(metrics.memoryCount, forKey: memoryCountKeyPrefix + connectorID)
        }
        metrics.lastSyncedAt = syncedAt
        defaults.set(syncedAt.timeIntervalSince1970, forKey: lastSyncedAtKeyPrefix + connectorID)
        metrics.lastDeltaCount = lastDeltaCount
        defaults.set(lastDeltaCount != nil, forKey: hasLastDeltaKeyPrefix + connectorID)
        if let lastDeltaCount {
            defaults.set(lastDeltaCount, forKey: lastDeltaCountKeyPrefix + connectorID)
        } else {
            defaults.removeObject(forKey: lastDeltaCountKeyPrefix + connectorID)
        }
        if let availabilityText {
            metrics.availabilityText = availabilityText
        }
        metricsByID[connectorID] = metrics
    }

    func refresh() async {
        await refreshLocalFilesMetrics()
        await refreshAppleNotesMetrics()
    }

    private func load() {
        for connector in ImportConnector.all {
            var metrics = ConnectorMetrics()

            if defaults.object(forKey: sourceCountKeyPrefix + connector.id) != nil {
                metrics.sourceCount = defaults.integer(forKey: sourceCountKeyPrefix + connector.id)
            }
            if defaults.object(forKey: memoryCountKeyPrefix + connector.id) != nil {
                metrics.memoryCount = defaults.integer(forKey: memoryCountKeyPrefix + connector.id)
            }
            if defaults.object(forKey: lastSyncedAtKeyPrefix + connector.id) != nil {
                let timestamp = defaults.double(forKey: lastSyncedAtKeyPrefix + connector.id)
                if timestamp > 0 {
                    metrics.lastSyncedAt = Date(timeIntervalSince1970: timestamp)
                }
            }
            if defaults.bool(forKey: hasLastDeltaKeyPrefix + connector.id) {
                metrics.lastDeltaCount = defaults.integer(forKey: lastDeltaCountKeyPrefix + connector.id)
            }

            metricsByID[connector.id] = metrics
        }

        hydrateLegacyManualImports()

        if let folderPath = defaults.string(forKey: appleNotesFolderDefaultsKey), !folderPath.isEmpty {
            var metrics = metricsByID["apple-notes"] ?? ConnectorMetrics()
            metrics.availabilityText = "Folder granted"
            metricsByID["apple-notes"] = metrics
        }
    }

    private func hydrateLegacyManualImports() {
        let legacyChatGPTCount = defaults.integer(forKey: onboardingChatGPTImportedMemoriesKey)
        if legacyChatGPTCount > 0, metricsByID["chatgpt"]?.memoryCount == nil {
            var metrics = metricsByID["chatgpt"] ?? ConnectorMetrics()
            metrics.memoryCount = legacyChatGPTCount
            metrics.availabilityText = "Imported during onboarding"
            metricsByID["chatgpt"] = metrics
        }

        let legacyClaudeCount = defaults.integer(forKey: onboardingClaudeImportedMemoriesKey)
        if legacyClaudeCount > 0, metricsByID["claude"]?.memoryCount == nil {
            var metrics = metricsByID["claude"] ?? ConnectorMetrics()
            metrics.memoryCount = legacyClaudeCount
            metrics.availabilityText = "Imported during onboarding"
            metricsByID["claude"] = metrics
        }
    }

    private func refreshLocalFilesMetrics() async {
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else { return }

        do {
            let result: (count: Int, lastIndexedAt: Date?) = try await dbQueue.read { db in
                guard let row = try Row.fetchOne(
                    db,
                    sql: """
                        SELECT COUNT(*) AS count, MAX(indexedAt) AS lastIndexedAt
                        FROM indexed_files
                    """
                ) else {
                    return (0, nil)
                }
                let count: Int = row["count"] ?? 0
                let lastIndexedAt: Date? = row["lastIndexedAt"]
                return (count, lastIndexedAt)
            }

            var metrics = metricsByID["local-files"] ?? ConnectorMetrics()
            metrics.sourceCount = result.count
            metrics.lastSyncedAt = result.lastIndexedAt
            metrics.availabilityText = "On-device index"
            metricsByID["local-files"] = metrics
        } catch {
            log("ImportConnectorStatusStore: Failed to refresh local files metrics: \(error)")
        }
    }

    private func refreshAppleNotesMetrics() async {
        do {
            let notes = try await AppleNotesReaderService.shared.readRecentNotes(maxResults: 250)
            guard !notes.isEmpty else { return }

            var metrics = metricsByID["apple-notes"] ?? ConnectorMetrics()
            metrics.sourceCount = notes.count
            metrics.availabilityText = "Private notes accessible"
            metricsByID["apple-notes"] = metrics
        } catch {
            let folderPath = defaults.string(forKey: appleNotesFolderDefaultsKey) ?? ""
            guard !folderPath.isEmpty else { return }
            var metrics = metricsByID["apple-notes"] ?? ConnectorMetrics()
            metrics.availabilityText = "Folder granted"
            metricsByID["apple-notes"] = metrics
        }
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
            if connector.id == "local-files" || sourceCount > 0 {
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

        if let availabilityText = metrics.availabilityText, availabilityText != primaryText(for: connector, metrics: metrics, isConnected: isConnected) {
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
        VStack(alignment: .leading, spacing: 12) {
            Text("Imports")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            LazyVGrid(columns: [
                GridItem(.adaptive(minimum: 220), spacing: 16)
            ], spacing: 16) {
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

struct ImportConnectorCard: View {
    let connector: ImportConnector
    let snapshot: ImportConnectorStatusStore.Snapshot
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    ConnectorBrandIcon(brand: connector.brand, size: 50, cornerRadius: 12)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(connector.title)
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .lineLimit(1)

                        Text(connector.subtitle)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }

                    Spacer()
                }

                Text(connector.description)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(snapshot.primaryText)
                            .scaledFont(size: 11, weight: .medium)
                            .foregroundColor(snapshot.isConnected ? OmiColors.textSecondary : OmiColors.textTertiary)

                        if let secondaryText = snapshot.secondaryText {
                            Text(secondaryText)
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                                .lineLimit(1)
                        }
                    }

                    Spacer()

                    ImportConnectorActionButton(title: snapshot.actionTitle, isConnected: snapshot.isConnected)
                }
            }
            .padding(14)
            .background(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
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
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(isConnected ? OmiColors.textPrimary : .black)
            .frame(width: isConnected ? 84 : 72, height: 28)
            .background(isConnected ? OmiColors.backgroundSecondary : Color.white)
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(OmiColors.border, lineWidth: 1)
            )
    }
}

@MainActor
private final class ImportConnectorSheetModel: ObservableObject {
    struct SyncResult {
        let sourceCount: Int?
        let memoryCount: Int?
        let newItems: Int?
    }

    @Published var isRunning = false
    @Published var progressTitle: String?
    @Published var progressDetail: String?
    @Published var statusMessage: String?
    @Published var errorMessage: String?
    @Published var draftText = ""

    private func beginRun(title: String, detail: String) {
        errorMessage = nil
        statusMessage = nil
        progressTitle = title
        progressDetail = detail
        isRunning = true
    }

    private func updateProgress(title: String, detail: String) {
        progressTitle = title
        progressDetail = detail
    }

    private func finishRun() {
        isRunning = false
        progressTitle = nil
        progressDetail = nil
    }

    func openAndCopyPrompt(for source: OnboardingMemoryLogSource) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(source.prompt, forType: .string)
        NSWorkspace.shared.open(source.prefilledBrowserURL)
    }

    func importMemoryLog(source: OnboardingMemoryLogSource) async -> SyncResult? {
        let trimmed = draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "Paste the full response first."
            return nil
        }

        beginRun(
            title: "Importing \(source.displayName)",
            detail: "Extracting durable memories from the pasted conversation."
        )
        defer { finishRun() }

        let result = await OnboardingMemoryLogImportService.shared.importMemoryLog(trimmed, source: source)
        guard result.memories > 0 else {
            errorMessage = "No durable memories could be extracted from that import."
            return nil
        }

        draftText = ""
        statusMessage = "Imported \(result.memories.formatted()) memories from \(source.displayName)."
        return SyncResult(sourceCount: nil, memoryCount: result.memories, newItems: result.memories)
    }

    func importGmail() async -> SyncResult? {
        beginRun(
            title: "Connecting to Gmail",
            detail: "Reading recent email history and follow-ups from the last year."
        )
        defer { finishRun() }

        do {
            let emails = try await GmailReaderService.shared.readRecentEmails(
                maxResults: 300,
                query: "newer_than:365d"
            )
            updateProgress(
                title: "Importing Gmail history",
                detail: "Saving raw emails as memories and generating follow-up insights."
            )
            let rawImport = await GmailReaderService.shared.saveAsMemories(emails: emails)
            let synthesis = await GmailReaderService.shared.synthesizeFromEmails(emails: emails)
            let memoryCount = rawImport.saved + synthesis.memories
            statusMessage =
                "Imported \(emails.count.formatted()) emails and saved \(memoryCount.formatted()) memories."
            return SyncResult(sourceCount: emails.count, memoryCount: memoryCount, newItems: emails.count)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func importCalendar() async -> SyncResult? {
        beginRun(
            title: "Connecting to Calendar",
            detail: "Reading past events and upcoming commitments for memory extraction."
        )
        defer { finishRun() }

        do {
            let events = try await CalendarReaderService.shared.readEvents(
                daysBack: 365,
                daysForward: 30,
                maxResults: 500
            )
            updateProgress(
                title: "Importing calendar events",
                detail: "Saving events as memories and generating action-oriented summaries."
            )
            let rawImport = await CalendarReaderService.shared.saveAsMemories(events: events, limit: 200)
            let synthesis = await CalendarReaderService.shared.synthesizeFromEvents(events: events)
            let memoryCount = rawImport.saved + synthesis.memories
            statusMessage =
                "Read \(events.count.formatted()) calendar events and saved \(memoryCount.formatted()) memories."
            return SyncResult(sourceCount: events.count, memoryCount: memoryCount, newItems: events.count)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func importAppleNotes() async -> SyncResult? {
        beginRun(
            title: "Connecting to Apple Notes",
            detail: "Checking access and preparing to import recent notes."
        )
        defer { finishRun() }

        do {
            return try await runAppleNotesImport()
        } catch let error as AppleNotesReaderError {
            switch error {
            case .storeNotFound, .storeUnavailable:
                break
            }
            let granted = await selectAppleNotesFolder()
            guard granted else {
                if errorMessage == nil {
                    errorMessage = error.localizedDescription
                }
                return nil
            }

            do {
                return try await runAppleNotesImport()
            } catch {
                errorMessage = error.localizedDescription
                return nil
            }
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    private func runAppleNotesImport() async throws -> SyncResult {
        updateProgress(
            title: "Importing Apple Notes",
            detail: "Reading recent notes and turning useful content into memories."
        )
        let notes = try await AppleNotesReaderService.shared.readRecentNotes(maxResults: 250)
        let rawImport = await AppleNotesReaderService.shared.saveAsMemories(notes: notes, limit: 200)
        let synthesis = await AppleNotesReaderService.shared.synthesizeFromNotes(notes: notes)
        let memoryCount = rawImport.saved + synthesis.memories
        statusMessage =
            "Imported \(notes.count.formatted()) notes and saved \(memoryCount.formatted()) memories."
        return SyncResult(sourceCount: notes.count, memoryCount: memoryCount, newItems: notes.count)
    }

    func rescanLocalFiles(appState: AppState?) async -> SyncResult? {
        guard let appState else {
            errorMessage = "App state is unavailable right now."
            return nil
        }

        beginRun(
            title: "Indexing local files",
            detail: "Scanning your on-device files so Omi can use them in memory search."
        )
        defer { finishRun() }

        let previousCount = await currentIndexedFileCount()
        ChatToolExecutor.onboardingAppState = appState
        let result = await ChatToolExecutor.execute(
            ToolCall(name: "scan_files", arguments: [:], thoughtSignature: nil)
        )

        if result.lowercased().hasPrefix("error") {
            errorMessage = result
            return nil
        } else {
            statusMessage = result
            let updatedCount = await currentIndexedFileCount()
            let newItems = max(updatedCount - previousCount, 0)
            return SyncResult(sourceCount: updatedCount, memoryCount: nil, newItems: newItems)
        }
    }

    func selectAppleNotesFolder() async -> Bool {
        let fileManager = FileManager.default
        let home = fileManager.homeDirectoryForCurrentUser
        let notesContainerURL = home
            .appendingPathComponent("Library/Group Containers/group.com.apple.notes", isDirectory: true)
        let groupContainersURL = home
            .appendingPathComponent("Library/Group Containers", isDirectory: true)

        let panel = NSOpenPanel()
        panel.message = "Select your Apple Notes data folder to grant access."
        panel.prompt = "Open"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = fileManager.fileExists(atPath: notesContainerURL.path)
            ? notesContainerURL
            : groupContainersURL

        guard panel.runModal() == .OK, let selectedURL = panel.url else {
            return false
        }

        let resolvedURL: URL
        if selectedURL.path == groupContainersURL.path {
            let inferredURL = groupContainersURL.appendingPathComponent("group.com.apple.notes", isDirectory: true)
            guard fileManager.fileExists(atPath: inferredURL.path) else {
                errorMessage = "Choose the Apple Notes folder inside Group Containers."
                return false
            }
            resolvedURL = inferredURL
        } else if selectedURL.lastPathComponent == "group.com.apple.notes" {
            resolvedURL = selectedURL
        } else {
            let nestedURL = selectedURL.appendingPathComponent("group.com.apple.notes", isDirectory: true)
            if fileManager.fileExists(atPath: nestedURL.path) {
                resolvedURL = nestedURL
            } else {
                errorMessage = "Choose the Apple Notes folder named group.com.apple.notes."
                return false
            }
        }

        errorMessage = nil
        await AppleNotesReaderService.shared.rememberSelectedFolder(path: resolvedURL.path)
        return true
    }

    private func currentIndexedFileCount() async -> Int {
        guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else { return 0 }
        do {
            return try await dbQueue.read { db in
                try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files") ?? 0
            }
        } catch {
            log("ImportConnectorSheetModel: Failed to read indexed file count: \(error)")
            return 0
        }
    }
}

struct ImportConnectorSheet: View {
    let connector: ImportConnector
    let appState: AppState?
    @ObservedObject var statusStore: ImportConnectorStatusStore
    let onDismiss: () -> Void

    @StateObject private var model = ImportConnectorSheetModel()

    private var snapshot: ImportConnectorStatusStore.Snapshot {
        statusStore.snapshot(for: connector)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 14) {
                ConnectorBrandIcon(brand: connector.brand, size: 56, cornerRadius: 16)

                VStack(alignment: .leading, spacing: 4) {
                    Text(connector.title)
                        .scaledFont(size: 20, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)

                    Text(connector.subtitle)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    Text(connector.description)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.top, 4)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 8) {
                    DismissButton(action: onDismiss)

                    Text("Press Esc or click × to close. Imports keep running in the background.")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: 180, alignment: .trailing)
                }
            }

            if connector.id == "chatgpt" || connector.id == "claude" {
                memoryImportContent
            } else {
                connectorActionContent
            }

            statusSection

            Spacer(minLength: 0)
        }
        .padding(24)
        .background(OmiColors.backgroundPrimary)
    }

    private var connectorActionContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let metricText = connector.metricText {
                Text(metricText)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Button(primaryActionTitle) {
                Task {
                    switch connector.id {
                    case "calendar":
                        if let result = await model.importCalendar() {
                            statusStore.markSynced(
                                connectorID: connector.id,
                                sourceCount: result.sourceCount,
                                memoryCount: result.memoryCount,
                                lastDeltaCount: result.newItems
                            )
                        }
                    case "email":
                        if let result = await model.importGmail() {
                            statusStore.markSynced(
                                connectorID: connector.id,
                                sourceCount: result.sourceCount,
                                memoryCount: result.memoryCount,
                                lastDeltaCount: result.newItems
                            )
                        }
                    case "apple-notes":
                        if let result = await model.importAppleNotes() {
                            statusStore.markSynced(
                                connectorID: connector.id,
                                sourceCount: result.sourceCount,
                                memoryCount: result.memoryCount,
                                lastDeltaCount: result.newItems,
                                availabilityText: "Private notes accessible"
                            )
                        }
                    case "local-files":
                        if let result = await model.rescanLocalFiles(appState: appState) {
                            statusStore.markSynced(
                                connectorID: connector.id,
                                sourceCount: result.sourceCount,
                                memoryCount: result.memoryCount,
                                lastDeltaCount: result.newItems,
                                availabilityText: "On-device index"
                            )
                        }
                    default:
                        break
                    }
                }
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
            .disabled(model.isRunning)

            if connector.id == "local-files" {
                Text("Local files are indexed on-device and used to build your memory graph.")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
    }

    private var memoryImportContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Open \(connector.title), paste the copied prompt, then drop the full response here.")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)

            Button("Open \(connector.title) and Copy Prompt") {
                model.openAndCopyPrompt(for: memorySource)
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))

            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .fill(OmiColors.backgroundSecondary)
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .stroke(Color.white.opacity(0.08), lineWidth: 1)
                    )

                if model.draftText.isEmpty {
                    Text("Paste the full \(connector.title) response here…")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 14)
                }

                TextEditor(text: $model.draftText)
                    .scrollContentBackground(.hidden)
                    .font(.system(size: 13))
                    .foregroundColor(OmiColors.textPrimary)
                    .frame(minHeight: 220)
                    .padding(8)
            }

            Button(model.isRunning ? "Importing…" : "Import \(connector.title)") {
                Task {
                    if let result = await model.importMemoryLog(source: memorySource) {
                        statusStore.markSynced(
                            connectorID: connector.id,
                            sourceCount: result.sourceCount,
                            memoryCount: result.memoryCount,
                            lastDeltaCount: result.newItems,
                            availabilityText: "Imported manually"
                        )
                    }
                }
            }
            .buttonStyle(OnboardingCardButtonStyle(isPrimary: true))
            .disabled(model.isRunning)
        }
    }

    private var memorySource: OnboardingMemoryLogSource {
        connector.id == "chatgpt" ? .chatgpt : .claude
    }

    private var primaryActionTitle: String {
        switch connector.id {
        case "calendar":
            return model.isRunning ? "Importing…" : "Connect Calendar"
        case "email":
            return model.isRunning ? "Importing…" : "Connect Gmail"
        case "apple-notes":
            return model.isRunning ? "Importing…" : "Connect Apple Notes"
        case "local-files":
            return model.isRunning ? "Reindexing…" : "Reindex Local Files"
        default:
            return model.isRunning ? "Working…" : connector.actionTitle
        }
    }

    @ViewBuilder
    private var statusSection: some View {
        if model.isRunning, let title = model.progressTitle {
            statusCard {
                HStack(alignment: .top, spacing: 12) {
                    ProgressView()
                        .controlSize(.small)
                        .padding(.top, 2)

                    VStack(alignment: .leading, spacing: 4) {
                        Text(title)
                            .scaledFont(size: 12, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        if let detail = model.progressDetail {
                            Text(detail)
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        Text("You can close this popup now. The import will keep running in the background.")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        } else if let statusMessage = model.statusMessage {
            Text(statusMessage)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.success)
        } else if let errorMessage = model.errorMessage {
            Text(errorMessage)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.warning)
        } else if snapshot.isConnected || snapshot.secondaryText != nil {
            statusCard {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Current import status")
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)

                    Text(snapshot.primaryText)
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)

                    if let secondaryText = snapshot.secondaryText {
                        Text(secondaryText)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        } else {
            Text("Start the import here. You can close this popup any time with Esc or ×, and once started the import will keep running in the background.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    private func statusCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(16)
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
                        OmiColors.backgroundSecondary
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
            )
            .mask(Rectangle())
            .offset(x: isAnimating ? 200 : -200)
            .animation(.linear(duration: 1.5).repeatForever(autoreverses: false), value: isAnimating)
            .onAppear { isAnimating = true }
    }
}

struct ShimmerAppCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ShimmerView()
                .frame(width: 60, height: 60)
                .cornerRadius(12)

            ShimmerView()
                .frame(width: 80, height: 14)
                .cornerRadius(4)

            ShimmerView()
                .frame(width: 60, height: 12)
                .cornerRadius(4)
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
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .scaledFont(size: 12)
                Text(label)
                    .scaledFont(size: 13)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isActive ? Color.white : OmiColors.backgroundSecondary)
            .foregroundColor(isActive ? Color.black : OmiColors.textSecondary)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isActive ? OmiColors.border : Color.clear, lineWidth: 1)
            )
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
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .scaledFont(size: 12)
                    .foregroundColor(color)
                Text(label)
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
            .cornerRadius(6)
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
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) {
                    ForEach(apps) { app in
                        CompactAppCard(app: app, appProvider: appProvider, onSelect: { onSelectApp(app) })
                    }

                    // "See more" button inline with cards
                    if showSeeMore, let onSeeMore = onSeeMore {
                        Button(action: onSeeMore) {
                            VStack(spacing: 6) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(OmiColors.backgroundSecondary)
                                        .frame(width: 56, height: 56)
                                    Image(systemName: "chevron.right")
                                        .scaledFont(size: 18, weight: .medium)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                                Text("See more")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            .frame(width: 70)
                        }
                        .buttonStyle(.plain)
                    } else if let onViewAll = onViewAll {
                        Button(action: onViewAll) {
                            VStack(spacing: 6) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 14)
                                        .fill(OmiColors.backgroundSecondary)
                                        .frame(width: 56, height: 56)
                                    Image(systemName: "chevron.right")
                                        .scaledFont(size: 18, weight: .medium)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                                Text("View all")
                                    .scaledFont(size: 11)
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
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(title)
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                if showSeeMore, let onSeeMore = onSeeMore {
                    Button(action: onSeeMore) {
                        HStack(spacing: 4) {
                            Text("See all")
                                .scaledFont(size: 13, weight: .medium)
                            Image(systemName: "chevron.right")
                                .scaledFont(size: 10, weight: .medium)
                        }
                        .foregroundColor(OmiColors.textSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }

            LazyVGrid(columns: [
                GridItem(.adaptive(minimum: 220), spacing: 16)
            ], spacing: 16) {
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
            VStack(alignment: .center, spacing: 8) {
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
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: .black.opacity(0.1), radius: 4, y: 2)

                VStack(spacing: 2) {
                    Text(app.name)
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    // Rating and installs
                    HStack(spacing: 3) {
                        if let rating = app.formattedRating {
                            Image(systemName: "star.fill")
                                .scaledFont(size: 8)
                                .foregroundColor(.yellow)
                            Text(rating)
                                .scaledFont(size: 10)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        if let installs = app.formattedInstalls {
                            if app.formattedRating != nil {
                                Text("·")
                                    .scaledFont(size: 10)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                            Text(installs)
                                .scaledFont(size: 10)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    }
                }

                // Get/Open button
                SmallAppButton(app: app, appProvider: appProvider, onOpen: onSelect)
            }
            .frame(width: 90)
            .padding(.vertical, 8)
            .background(isHovering ? OmiColors.backgroundSecondary.opacity(0.5) : Color.clear)
            .cornerRadius(12)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }

    private var appIconPlaceholder: some View {
        RoundedRectangle(cornerRadius: 14)
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
                    .scaledFont(size: 11, weight: .medium)
                    .foregroundColor(.black)
                    .frame(width: 50, height: 22)
                    .background(Color.white)
                    .cornerRadius(11)
                    .overlay(
                        RoundedRectangle(cornerRadius: 11)
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
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
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
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                    VStack(alignment: .leading, spacing: 4) {
                        Text(app.name)
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .lineLimit(1)

                        Text(app.author)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }

                    Spacer()
                }

                Text(app.description)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)

                HStack {
                    // Rating and installs
                    HStack(spacing: 6) {
                        if let rating = app.formattedRating {
                            HStack(spacing: 3) {
                                Image(systemName: "star.fill")
                                    .scaledFont(size: 10)
                                    .foregroundColor(.yellow)
                                Text(rating)
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }
                        if let installs = app.formattedInstalls {
                            HStack(spacing: 3) {
                                Image(systemName: "arrow.down.circle")
                                    .scaledFont(size: 10)
                                    .foregroundColor(OmiColors.textTertiary)
                                Text(installs)
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                            }
                        }
                    }

                    Spacer()

                    // Get/Open button
                    AppActionButton(app: app, appProvider: appProvider, onOpen: onSelect)
                }
            }
            .padding(14)
            .background(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
        }
    }

    private var appIconPlaceholder: some View {
        RoundedRectangle(cornerRadius: 12)
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
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.black)
                    .frame(width: 60, height: 28)
                    .background(Color.white)
                    .cornerRadius(14)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
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
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                if hasActiveFilters {
                    Button("Clear All") {
                        appProvider.clearFilters()
                        Task { await appProvider.searchApps() }
                    }
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                }

                DismissButton(action: dismissSheet)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // Categories
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Category")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        FlowLayout(spacing: 8) {
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
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Capability")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        FlowLayout(spacing: 8) {
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
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Other")
                            .scaledFont(size: 14, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Toggle("Show installed only", isOn: $appProvider.showInstalledOnly)
                            .toggleStyle(SwitchToggleStyle(tint: OmiColors.purplePrimary))
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
        appProvider.selectedCategory != nil ||
        appProvider.selectedCapability != nil ||
        appProvider.showInstalledOnly
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
                .scaledFont(size: 13)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(isSelected ? Color.white : OmiColors.backgroundSecondary)
                .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)
                .cornerRadius(20)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
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
                DismissButton(action: dismissSheet, icon: "chevron.left", showBackground: false)

                Text(category.title)
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Text("\(categoryApps.count) apps")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                LazyVGrid(columns: [
                    GridItem(.flexible(), spacing: 16),
                    GridItem(.flexible(), spacing: 16)
                ], spacing: 16) {
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
                VStack(alignment: .leading, spacing: 20) {
                    // App header
                    HStack(spacing: 16) {
                        AsyncImage(url: URL(string: app.image)) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            default:
                                RoundedRectangle(cornerRadius: 16)
                                    .fill(OmiColors.backgroundTertiary)
                            }
                        }
                        .frame(width: 80, height: 80)
                        .clipShape(RoundedRectangle(cornerRadius: 16))

                        VStack(alignment: .leading, spacing: 6) {
                            Text(app.name)
                                .scaledFont(size: 24, weight: .bold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text(app.author)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textTertiary)

                            HStack(spacing: 12) {
                                let ratingAvg = appDetails?.ratingAvg ?? app.ratingAvg
                                let ratingCount = appDetails?.ratingCount ?? app.ratingCount
                                let installs = appDetails?.installs ?? app.installs
                                if let ratingAvg, ratingCount > 0 {
                                    HStack(spacing: 4) {
                                        Image(systemName: "star.fill")
                                            .foregroundColor(.yellow)
                                        Text(String(format: "%.1f", ratingAvg))
                                        Text("(\(ratingCount))")
                                    }
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textSecondary)
                                }
                                if installs > 0 {
                                    Text("\(installs) installs")
                                        .scaledFont(size: 13)
                                        .foregroundColor(OmiColors.textSecondary)
                                }
                            }
                        }

                        Spacer()

                        // Action button
                        HStack(spacing: 8) {
                            Button(action: {
                                Task {
                                    if isEnabled && app.worksExternally {
                                        // Open the external integration in browser
                                        openExternalApp()
                                    } else if !isEnabled && app.worksExternally {
                                        await handleInstall()
                                    } else {
                                        await appProvider.toggleApp(app)
                                    }
                                }
                            }) {
                                if appProvider.isAppLoading(app.id) {
                                    ProgressView()
                                        .frame(width: 100, height: 36)
                                } else if isSettingUp {
                                    HStack(spacing: 6) {
                                        ProgressView()
                                            .scaleEffect(0.7)
                                        Text("Setting up...")
                                            .scaledFont(size: 12, weight: .semibold)
                                    }
                                    .foregroundColor(OmiColors.textSecondary)
                                    .frame(width: 120, height: 36)
                                } else {
                                    Text(isEnabled ? "Open" : "Install")
                                        .scaledFont(size: 14, weight: .semibold)
                                        .foregroundColor(.black)
                                        .frame(width: 100, height: 36)
                                        .background(Color.white)
                                        .cornerRadius(18)
                                        .overlay(
                                            RoundedRectangle(cornerRadius: 18)
                                                .stroke(OmiColors.border, lineWidth: 1)
                                        )
                                }
                            }
                            .buttonStyle(.plain)

                            // Disable button shown only when app is enabled
                            if isEnabled && !appProvider.isAppLoading(app.id) && !isSettingUp {
                                Button(action: {
                                    Task { await appProvider.toggleApp(app) }
                                }) {
                                    Image(systemName: "trash")
                                        .scaledFont(size: 14)
                                        .foregroundColor(OmiColors.error)
                                        .frame(width: 36, height: 36)
                                        .background(OmiColors.error.opacity(0.1))
                                        .cornerRadius(18)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    Divider()
                        .background(OmiColors.backgroundTertiary)

                    // Description
                    VStack(alignment: .leading, spacing: 8) {
                        Text("About")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(app.description)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    // Setup steps (external integration)
                    if let integration = appDetails?.externalIntegration, !integration.authSteps.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(Array(integration.authSteps.enumerated()), id: \.offset) { index, step in
                                Button(action: {
                                    if let uid = AuthState.shared.userId,
                                       let url = URL(string: "\(step.url)?uid=\(uid)") {
                                        NSWorkspace.shared.open(url)
                                    }
                                }) {
                                    HStack(spacing: 12) {
                                        // Step number / checkmark
                                        ZStack {
                                            RoundedRectangle(cornerRadius: 10)
                                                .fill(isSetupCompleted ? Color.green.opacity(0.15) : OmiColors.backgroundTertiary)
                                                .frame(width: 40, height: 40)
                                            if isSetupCompleted {
                                                Image(systemName: "checkmark")
                                                    .scaledFont(size: 14, weight: .semibold)
                                                    .foregroundColor(.green)
                                            } else {
                                                Text("\(index + 1)")
                                                    .scaledFont(size: 14, weight: .semibold)
                                                    .foregroundColor(OmiColors.textSecondary)
                                            }
                                        }

                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(step.name)
                                                .scaledFont(size: 14, weight: .medium)
                                                .foregroundColor(OmiColors.textPrimary)
                                            Text(isSetupCompleted ? "Completed" : "Click to complete")
                                                .scaledFont(size: 12)
                                                .foregroundColor(isSetupCompleted ? .green : OmiColors.textTertiary)
                                        }

                                        Spacer()

                                        Image(systemName: "arrow.up.right.square")
                                            .scaledFont(size: 14)
                                            .foregroundColor(OmiColors.textTertiary)
                                    }
                                    .padding(12)
                                    .background(OmiColors.backgroundSecondary)
                                    .cornerRadius(12)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    // Capabilities
                    if !app.capabilities.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Capabilities")
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            FlowLayout(spacing: 8) {
                                ForEach(app.capabilities, id: \.self) { capability in
                                    CapabilityBadge(capability: capability)
                                }
                            }
                        }
                    }

                    // Category
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Category")
                            .scaledFont(size: 16, weight: .semibold)
                            .foregroundColor(OmiColors.textPrimary)

                        Text(app.category.replacingOccurrences(of: "-", with: " ").capitalized)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textSecondary)
                    }

                    Divider()
                        .background(OmiColors.backgroundTertiary)

                    // Add Review Section
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Reviews")
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            Spacer()

                            if userReview == nil {
                                Button(action: { showAddReview = true }) {
                                    HStack(spacing: 4) {
                                        Image(systemName: "plus")
                                            .scaledFont(size: 12, weight: .medium)
                                        Text("Add Review")
                                            .scaledFont(size: 13, weight: .medium)
                                    }
                                    .foregroundColor(OmiColors.textSecondary)
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        // User's own review (if exists)
                        if let userReview = userReview {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text("Your Review")
                                        .scaledFont(size: 13, weight: .medium)
                                        .foregroundColor(OmiColors.textPrimary)

                                    Spacer()

                                    Button(action: { showAddReview = true }) {
                                        Text("Edit")
                                            .scaledFont(size: 12, weight: .medium)
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
                            Text("No reviews yet. Be the first to review this app!")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.vertical, 8)
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
              !completionUrl.isEmpty else {
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
                  let url = URL(string: "\(authSteps[0].url)?uid=\(uid)") {
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

    init(app: OmiApp, existingReview: OmiAppReview?, onReviewSubmitted: @escaping (OmiAppReview) -> Void, onDismiss: (() -> Void)? = nil) {
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
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                DismissButton(action: dismissSheet)
            }
            .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    // App info
                    HStack(spacing: 12) {
                        AsyncImage(url: URL(string: app.image)) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            default:
                                RoundedRectangle(cornerRadius: 12)
                                    .fill(OmiColors.backgroundTertiary)
                            }
                        }
                        .frame(width: 50, height: 50)
                        .clipShape(RoundedRectangle(cornerRadius: 12))

                        VStack(alignment: .leading, spacing: 4) {
                            Text(app.name)
                                .scaledFont(size: 16, weight: .semibold)
                                .foregroundColor(OmiColors.textPrimary)

                            Text(app.author)
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Spacer()
                    }

                    // Star Rating Picker
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Your Rating")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)

                        StarRatingPicker(rating: $selectedRating)
                    }

                    // Review Text
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Your Review")
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Spacer()

                            Text("\(reviewText.count)/\(maxReviewLength)")
                                .scaledFont(size: 12)
                                .foregroundColor(reviewText.count > maxReviewLength ? OmiColors.error : OmiColors.textTertiary)
                        }

                        ZStack(alignment: .topLeading) {
                            TextEditor(text: $reviewText)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textPrimary)
                                .scrollContentBackground(.hidden)
                                .frame(minHeight: 120, maxHeight: 200)
                                .padding(12)
                                .background(OmiColors.backgroundSecondary)
                                .cornerRadius(10)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(OmiColors.backgroundTertiary, lineWidth: 1)
                                )
                                .onChange(of: reviewText) { _, newValue in
                                    if newValue.count > maxReviewLength {
                                        reviewText = String(newValue.prefix(maxReviewLength))
                                    }
                                }

                            if reviewText.isEmpty {
                                Text("Share your experience with this app...")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .padding(.leading, 17)
                                    .padding(.top, 20)
                                    .allowsHitTesting(false)
                            }
                        }
                    }

                    // Error message
                    if let errorMessage = errorMessage {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundColor(OmiColors.error)
                            Text(errorMessage)
                                .scaledFont(size: 13)
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
                                    .scaledFont(size: 14, weight: .semibold)
                            }
                        }
                        .foregroundColor(OmiColors.textPrimary)
                        .frame(maxWidth: .infinity)
                        .frame(height: 44)
                        .background(isFormValid ? Color.white : Color.white.opacity(0.5))
                        .cornerRadius(10)
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
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
        HStack(spacing: 8) {
            ForEach(1...maxRating, id: \.self) { star in
                Image(systemName: starImage(for: star))
                    .scaledFont(size: starSize)
                    .foregroundColor(starColor(for: star))
                    .onTapGesture {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            rating = star
                        }
                    }
                    .onHover { hovering in
                        hoverRating = hovering ? star : 0
                    }
                    .scaleEffect(scaleEffect(for: star))
                    .animation(.easeInOut(duration: 0.1), value: hoverRating)
            }

            if rating > 0 {
                Text(ratingLabel)
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(.leading, 8)
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
        HStack(spacing: 6) {
            Image(systemName: icon)
                .scaledFont(size: 10)
            Text(capability.replacingOccurrences(of: "_", with: " ").capitalized)
                .scaledFont(size: 12)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(OmiColors.backgroundSecondary)
        .foregroundColor(OmiColors.textSecondary)
        .cornerRadius(16)
    }
}

// MARK: - Review Card

struct ReviewCard: View {
    let review: OmiAppReview

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                // Rating stars
                HStack(spacing: 2) {
                    ForEach(1...5, id: \.self) { star in
                        Image(systemName: star <= review.score ? "star.fill" : "star")
                            .scaledFont(size: 10)
                            .foregroundColor(star <= review.score ? .yellow : OmiColors.textTertiary)
                    }
                }

                Spacer()

                Text(review.ratedAt, style: .date)
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
            }

            Text(review.review)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(3)

            if let response = review.response {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Developer Response")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)

                    Text(response)
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textSecondary)
                        .lineLimit(2)
                }
                .padding(10)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(8)
            }
        }
        .padding(12)
        .background(OmiColors.backgroundSecondary.opacity(0.5))
        .cornerRadius(10)
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
            let subProposal: ProposedViewSize = idealSize.width > bounds.width
                ? ProposedViewSize(width: bounds.width, height: nil)
                : .unspecified
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
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

struct DismissableSheetModifier<SheetContent: View>: ViewModifier {
    @Binding var isPresented: Bool
    let sheetContent: () -> SheetContent

    func body(content: Content) -> some View {
        content
            .overlay {
                ZStack {
                    if isPresented {
                        // Dimmed background that dismisses on tap.
                        Color.black.opacity(0.3)
                            .ignoresSafeArea()
                            .contentShape(Rectangle())
                            .onTapGesture {
                                log("DISMISSABLE_SHEET: Background tapped, dismissing")
                                withAnimation(.easeOut(duration: 0.2)) {
                                    isPresented = false
                                }
                            }
                            .transition(.opacity)
                            .zIndex(0)

                        // Force the sheet into a centered full-size overlay so it
                        // does not end up clipped or visually hidden behind the scrim.
                        sheetContent()
                            .background(OmiColors.backgroundPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                            .transition(.scale(scale: 0.95).combined(with: .opacity))
                            .zIndex(1)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .animation(.easeOut(duration: 0.2), value: isPresented)
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
            .overlay {
                ZStack {
                    if let presentedItem = item {
                        // Dimmed background that dismisses on tap.
                        Color.black.opacity(0.3)
                            .ignoresSafeArea()
                            .contentShape(Rectangle())
                            .onTapGesture {
                                log("DISMISSABLE_SHEET: Background tapped, dismissing item")
                                withAnimation(.easeOut(duration: 0.2)) {
                                    item = nil
                                }
                            }
                            .transition(.opacity)
                            .zIndex(0)

                        // Force the sheet into a centered full-size overlay so it
                        // does not end up clipped or visually hidden behind the scrim.
                        sheetContent(presentedItem)
                            .background(OmiColors.backgroundPrimary)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
                            .transition(.scale(scale: 0.95).combined(with: .opacity))
                            .zIndex(1)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .animation(.easeOut(duration: 0.2), value: item?.id != nil)
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
        HStack(spacing: 12) {
            // Icon
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(iconColor.opacity(0.15))
                    .frame(width: 44, height: 44)

                Image(systemName: icon)
                    .scaledFont(size: 20)
                    .foregroundColor(iconColor)
            }

            Text(title)
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Spacer()

            Image(systemName: "chevron.right")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
        }
        .padding(12)
        .frame(maxWidth: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(isHovering ? OmiColors.backgroundSecondary : OmiColors.backgroundPrimary)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
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

#Preview {
    AppsPage(appProvider: AppProvider())
        .frame(width: 900, height: 700)
}
