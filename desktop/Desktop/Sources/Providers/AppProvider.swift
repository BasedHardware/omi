import SwiftUI

/// State management for apps/plugins functionality
@MainActor
class AppProvider: ObservableObject {
    @Published var apps: [OmiApp] = []
    @Published var popularApps: [OmiApp] = []  // Featured apps (is_popular=true)
    @Published var integrationApps: [OmiApp] = []  // Apps with external_integration capability
    @Published var chatApps: [OmiApp] = []  // Apps with chat capability
    @Published var summaryApps: [OmiApp] = []  // Apps with memories capability
    @Published var notificationApps: [OmiApp] = []  // Apps with proactive_notification capability
    @Published var enabledApps: [OmiApp] = []
    @Published var categories: [OmiAppCategory] = []
    @Published var capabilities: [OmiAppCapability] = []

    @Published var isLoading = false
    @Published var isSearching = false
    @Published var appLoadingStates: [String: Bool] = [:]

    @Published var searchQuery = ""
    @Published var selectedCategory: String?
    @Published var selectedCapability: String?
    @Published var showInstalledOnly = false

    @Published var errorMessage: String?
    @Published var categoryFilteredApps: [OmiApp]?
    @Published var hasMoreCategoryApps = false
    @Published var isLoadingMore = false

    private var categoryFilterOffset = 0
    private let categoryPageSize = 50

    private let apiClient = APIClient.shared

    // MARK: - Fetch Methods

    /// Fetch all apps data using v2/apps endpoint (grouped by capability, matching Flutter)
    func fetchApps() async {
        isLoading = true
        errorMessage = nil
        defer {
            isLoading = false
            NotificationCenter.default.post(name: .appsPageDidLoad, object: nil)
        }

        do {
            // Fetch grouped apps and metadata in parallel
            async let v2AppsTask = apiClient.getAppsV2()
            async let categoriesTask = apiClient.getAppCategories()
            async let capabilitiesTask = apiClient.getAppCapabilities()

            let (v2Response, fetchedCategories, fetchedCapabilities) = try await (
                v2AppsTask,
                categoriesTask,
                capabilitiesTask
            )

            // Process groups off main thread
            let processed = await Task.detached(priority: .utility) {
                var dedupedApps: [OmiApp] = []
                var popular: [OmiApp] = []
                var integration: [OmiApp] = []
                var chat: [OmiApp] = []
                var summary: [OmiApp] = []
                var notification: [OmiApp] = []
                var allApps: [OmiApp] = []

                for group in v2Response.groups {
                    allApps.append(contentsOf: group.data)
                    switch group.capability.id {
                    case "popular":
                        popular = group.data
                    case "external_integration":
                        integration = group.data
                    case "chat":
                        chat = group.data
                    case "memories":
                        summary = group.data
                    case "proactive_notification":
                        notification = group.data
                    default:
                        break
                    }
                }

                // Remove duplicates
                var seenIds = Set<String>()
                dedupedApps = allApps.filter { app in
                    if seenIds.contains(app.id) { return false }
                    seenIds.insert(app.id)
                    return true
                }

                return (dedupedApps, popular, integration, chat, summary, notification)
            }.value

            // Batch-assign all @Published properties on main actor
            apps = processed.0
            popularApps = processed.1
            integrationApps = processed.2
            chatApps = processed.3
            summaryApps = processed.4
            notificationApps = processed.5
            categories = fetchedCategories
            capabilities = fetchedCapabilities

            updateDerivedLists()

            log("Fetched \(apps.count) apps via v2: \(popularApps.count) featured, \(integrationApps.count) integrations, \(chatApps.count) chat, \(summaryApps.count) summary, \(notificationApps.count) notifications")
        } catch {
            logError("Failed to fetch apps", error: error)
            errorMessage = "Failed to load apps: \(error.localizedDescription)"
        }
    }

    /// Search apps with current filters
    func searchApps() async {
        guard !searchQuery.isEmpty || selectedCategory != nil || selectedCapability != nil || showInstalledOnly else {
            // Reset to default view
            await fetchApps()
            return
        }

        isSearching = true
        errorMessage = nil
        defer { isSearching = false }

        do {
            apps = try await apiClient.searchApps(
                query: searchQuery.isEmpty ? nil : searchQuery,
                category: selectedCategory,
                capability: selectedCapability,
                installedOnly: showInstalledOnly
            )
            updateDerivedLists()
        } catch {
            logError("Failed to search apps", error: error)
            errorMessage = "Search failed: \(error.localizedDescription)"
        }
    }

    /// Fetch apps for a specific category from the API
    func fetchAppsForCategory(_ categoryId: String) async {
        isSearching = true
        categoryFilterOffset = 0
        defer { isSearching = false }

        do {
            let results = try await apiClient.getApps(category: categoryId, limit: categoryPageSize, offset: 0)
            categoryFilteredApps = results
            hasMoreCategoryApps = results.count >= categoryPageSize
            log("Fetched \(results.count) apps for category \(categoryId)")
        } catch {
            logError("Failed to fetch apps for category \(categoryId)", error: error)
            // Fallback to client-side filtering
            categoryFilteredApps = apps.filter { $0.category == categoryId }
            hasMoreCategoryApps = false
        }
    }

    /// Load more apps for the current category (pagination)
    func loadMoreCategoryApps() async {
        guard let categoryId = selectedCategory,
              hasMoreCategoryApps,
              !isLoadingMore else { return }

        isLoadingMore = true
        let newOffset = categoryFilterOffset + categoryPageSize
        defer { isLoadingMore = false }

        do {
            let results = try await apiClient.getApps(category: categoryId, limit: categoryPageSize, offset: newOffset)
            if !results.isEmpty {
                categoryFilteredApps?.append(contentsOf: results)
                categoryFilterOffset = newOffset
                hasMoreCategoryApps = results.count >= categoryPageSize
                log("Loaded \(results.count) more apps for category \(categoryId)")
            } else {
                hasMoreCategoryApps = false
            }
        } catch {
            logError("Failed to load more apps for category \(categoryId)", error: error)
        }
    }

    /// Clear category filter results
    func clearCategoryFilter() {
        selectedCategory = nil
        categoryFilteredApps = nil
        categoryFilterOffset = 0
        hasMoreCategoryApps = false
    }

    /// Fetch user's enabled apps
    func fetchEnabledApps() async {
        do {
            enabledApps = try await apiClient.getEnabledApps()
            chatApps = enabledApps.filter { $0.worksWithChat }
        } catch {
            logError("Failed to fetch enabled apps", error: error)
        }
    }

    // MARK: - App Management

    /// Toggle app enabled state
    func toggleApp(_ app: OmiApp) async {
        appLoadingStates[app.id] = true
        defer { appLoadingStates[app.id] = false }

        do {
            if app.enabled {
                try await apiClient.disableApp(appId: app.id)
                // Track app disabled
                AnalyticsManager.shared.appDisabled(appId: app.id, appName: app.name)
            } else {
                try await apiClient.enableApp(appId: app.id)
                // Track app enabled
                AnalyticsManager.shared.appEnabled(appId: app.id, appName: app.name)
            }

            // Update local state across all lists
            if let index = apps.firstIndex(where: { $0.id == app.id }) {
                apps[index].enabled.toggle()
            }
            if let index = popularApps.firstIndex(where: { $0.id == app.id }) {
                popularApps[index].enabled.toggle()
            }
            if let index = integrationApps.firstIndex(where: { $0.id == app.id }) {
                integrationApps[index].enabled.toggle()
            }
            if let index = chatApps.firstIndex(where: { $0.id == app.id }) {
                chatApps[index].enabled.toggle()
            }
            if let index = summaryApps.firstIndex(where: { $0.id == app.id }) {
                summaryApps[index].enabled.toggle()
            }
            if let index = notificationApps.firstIndex(where: { $0.id == app.id }) {
                notificationApps[index].enabled.toggle()
            }

            updateDerivedLists()

            log("Toggled app \(app.id) to enabled=\(!app.enabled)")
        } catch {
            logError("Failed to toggle app", error: error)
            errorMessage = "Failed to \(app.enabled ? "disable" : "enable") app"
        }
    }

    /// Enable an app
    func enableApp(_ app: OmiApp) async {
        guard !app.enabled else { return }
        await toggleApp(app)
    }

    /// Disable an app
    func disableApp(_ app: OmiApp) async {
        guard app.enabled else { return }
        await toggleApp(app)
    }

    // MARK: - Helpers

    /// Check if an app is currently loading
    func isAppLoading(_ appId: String) -> Bool {
        appLoadingStates[appId] ?? false
    }

    /// Update derived lists from main apps list
    private func updateDerivedLists() {
        enabledApps = apps.filter { $0.enabled }
        // Note: chatApps is populated from v2 response, but we also include enabled chat apps
        // that might not be in the original chatApps list
        let enabledChatApps = enabledApps.filter { $0.worksWithChat }
        let existingChatIds = Set(chatApps.map { $0.id })
        for app in enabledChatApps {
            if !existingChatIds.contains(app.id) {
                chatApps.append(app)
            }
        }
    }

    /// Get apps filtered by category (supports special section IDs)
    func apps(forCategory category: String) -> [OmiApp] {
        switch category {
        case "featured":
            return popularApps
        case "integrations":
            return integrationApps
        case "notifications":
            return notificationApps
        default:
            return apps.filter { $0.category == category }
        }
    }

    /// Get apps filtered by capability
    func apps(forCapability capability: String) -> [OmiApp] {
        apps.filter { $0.capabilities.contains(capability) }
    }

    /// Clear search and filters
    func clearFilters() {
        searchQuery = ""
        selectedCategory = nil
        selectedCapability = nil
        showInstalledOnly = false
    }
}
