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
    @Published var filteredApps: [OmiApp]?
    @Published var hasMoreFilteredApps = false
    @Published var isLoadingMore = false

    private var filteredAppsOffset = 0
    private let filteredAppsPageSize = 50
    private let filteredAppsCacheLimit = 20
    private var marketplaceApps: [OmiApp] = []
    private var filteredAppsCache: [FilterKey: FilterCacheEntry] = [:]
    private var filteredAppsCacheOrder: [FilterKey] = []

    private let apiClient = APIClient.shared

    var hasActiveFilters: Bool {
        normalizedSearchQuery != nil || selectedCategory != nil || selectedCapability != nil || showInstalledOnly
    }

    private var normalizedSearchQuery: String? {
        let normalizedQuery = searchQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        return normalizedQuery.isEmpty ? nil : normalizedQuery
    }

    private var currentFilterKey: FilterKey? {
        guard hasActiveFilters else { return nil }
        return FilterKey(
            query: normalizedSearchQuery,
            category: selectedCategory,
            capability: selectedCapability,
            installedOnly: showInstalledOnly
        )
    }

    private struct FilterKey: Hashable {
        let query: String?
        let category: String?
        let capability: String?
        let installedOnly: Bool
    }

    private struct FilterCacheEntry {
        var apps: [OmiApp]
        var offset: Int
        var hasMore: Bool
    }

    // MARK: - Session Lifecycle

    func resetSessionState() {
        apps = []
        popularApps = []
        integrationApps = []
        chatApps = []
        summaryApps = []
        notificationApps = []
        enabledApps = []
        categories = []
        capabilities = []
        marketplaceApps = []
        filteredAppsCache = [:]
        filteredAppsCacheOrder = []

        isLoading = false
        isSearching = false
        appLoadingStates = [:]

        searchQuery = ""
        selectedCategory = nil
        selectedCapability = nil
        showInstalledOnly = false

        errorMessage = nil
        filteredApps = nil
        hasMoreFilteredApps = false
        isLoadingMore = false
        filteredAppsOffset = 0
    }

    // MARK: - Fetch Methods

    /// Fetch only chat-capable apps for startup chat picker warmup.
    /// The full Apps page still loads categories, capabilities, ratings, and all groups on first use.
    func fetchChatAppsForStartup() async {
        do {
            let v2Response = try await apiClient.getAppsV2()
            let chat = v2Response.groups.first { $0.capability.id == "chat" }?.data ?? []
            chatApps = chat
            log("Fetched \(chatApps.count) chat apps for startup")
        } catch {
            logError("Failed to fetch startup chat apps", error: error)
        }
    }

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
            marketplaceApps = processed.0
            filteredApps = nil
            popularApps = processed.1
            integrationApps = processed.2
            chatApps = processed.3
            summaryApps = processed.4
            notificationApps = processed.5
            categories = fetchedCategories
            capabilities = fetchedCapabilities

            updateDerivedLists()

            log("Fetched \(apps.count) apps via v2: \(popularApps.count) featured, \(integrationApps.count) integrations, \(chatApps.count) chat, \(summaryApps.count) summary, \(notificationApps.count) notifications")

            // Enrich ratings + enabled state in background.
            // v2/apps returns rating_avg=0 and may not include per-user enabled state.
            // v1/apps is user-specific and has real ratings + correct enabled field.
            Task {
                do {
                    let ratedApps = try await self.apiClient.getAppsWithRatings()
                    // Build a map of id → full app (for ratings AND enabled state)
                    let v1Map = Dictionary(uniqueKeysWithValues: ratedApps.map { ($0.id, $0) })
                    func enrich(_ list: inout [OmiApp]) {
                        for index in list.indices {
                            guard let v1App = v1Map[list[index].id] else { continue }
                            if v1App.ratingCount > 0 {
                                list[index].ratingAvg = v1App.ratingAvg
                                list[index].ratingCount = v1App.ratingCount
                            }
                            // Sync enabled state from user-specific v1/apps response
                            list[index].enabled = v1App.enabled
                        }
                    }
                    enrich(&self.apps)
                    enrich(&self.marketplaceApps)
                    enrich(&self.popularApps)
                    enrich(&self.integrationApps)
                    enrich(&self.chatApps)
                    enrich(&self.summaryApps)
                    enrich(&self.notificationApps)
                    self.updateDerivedLists()
                } catch {
                    // silently fail — ratings are supplementary
                }
            }
        } catch {
            logError("Failed to fetch apps", error: error)
            errorMessage = "Failed to load apps: \(error.localizedDescription)"
        }
    }

    /// Search apps with current filters
    func searchApps() async {
        guard hasActiveFilters else {
            // Reset to default view
            filteredAppsOffset = 0
            hasMoreFilteredApps = false
            if !marketplaceApps.isEmpty {
                apps = marketplaceApps
                filteredApps = nil
                updateDerivedLists()
                return
            }
            await fetchApps()
            return
        }

        guard let cacheKey = currentFilterKey else { return }

        if let cached = cachedFilteredApps(for: cacheKey) {
            filteredApps = cached.apps
            filteredAppsOffset = cached.offset
            hasMoreFilteredApps = cached.hasMore
            return
        }

        isSearching = true
        errorMessage = nil
        defer { isSearching = false }

        do {
            filteredAppsOffset = 0
            let results = try await apiClient.searchApps(
                query: normalizedSearchQuery,
                category: selectedCategory,
                capability: selectedCapability,
                installedOnly: showInstalledOnly,
                limit: filteredAppsPageSize,
                offset: 0
            )
            guard currentFilterKey == cacheKey else { return }
            filteredApps = results
            hasMoreFilteredApps = results.count >= filteredAppsPageSize
            cacheFilteredApps(
                FilterCacheEntry(
                    apps: results,
                    offset: filteredAppsOffset,
                    hasMore: hasMoreFilteredApps
                ),
                for: cacheKey
            )
        } catch {
            logError("Failed to search apps", error: error)
            errorMessage = "Search failed: \(error.localizedDescription)"
            hasMoreFilteredApps = false
        }
    }

    /// Load more apps for the current search/filter set.
    func loadMoreFilteredApps() async {
        guard hasActiveFilters,
              hasMoreFilteredApps,
              !isLoadingMore,
              let cacheKey = currentFilterKey else { return }

        isLoadingMore = true
        let newOffset = filteredAppsOffset + filteredAppsPageSize
        defer { isLoadingMore = false }

        do {
            let results = try await apiClient.searchApps(
                query: normalizedSearchQuery,
                category: selectedCategory,
                capability: selectedCapability,
                installedOnly: showInstalledOnly,
                limit: filteredAppsPageSize,
                offset: newOffset
            )
            guard currentFilterKey == cacheKey else { return }
            if !results.isEmpty {
                var updatedResults = filteredApps ?? []
                updatedResults.append(contentsOf: results)
                filteredApps = updatedResults
                filteredAppsOffset = newOffset
                hasMoreFilteredApps = results.count >= filteredAppsPageSize
                cacheFilteredApps(
                    FilterCacheEntry(
                        apps: updatedResults,
                        offset: filteredAppsOffset,
                        hasMore: hasMoreFilteredApps
                    ),
                    for: cacheKey
                )
                log("Loaded \(results.count) more filtered apps")
            } else {
                hasMoreFilteredApps = false
                if var cached = cachedFilteredApps(for: cacheKey) {
                    cached.hasMore = false
                    cacheFilteredApps(cached, for: cacheKey)
                }
            }
        } catch {
            logError("Failed to load more filtered apps", error: error)
        }
    }

    /// Clear category filter results
    func clearCategoryFilter() {
        selectedCategory = nil
        filteredApps = nil
        filteredAppsOffset = 0
        hasMoreFilteredApps = false
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
            let newEnabled = !app.enabled
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
            setEnabled(newEnabled, for: app.id, in: &apps)
            setEnabled(newEnabled, for: app.id, in: &marketplaceApps)
            setEnabled(newEnabled, for: app.id, in: &popularApps)
            setEnabled(newEnabled, for: app.id, in: &integrationApps)
            setEnabled(newEnabled, for: app.id, in: &chatApps)
            setEnabled(newEnabled, for: app.id, in: &summaryApps)
            setEnabled(newEnabled, for: app.id, in: &notificationApps)
            setEnabled(newEnabled, for: app.id, in: &filteredApps)
            updateCachedEnabledState(appId: app.id, enabled: newEnabled)

            updateDerivedLists()
            if showInstalledOnly && !newEnabled {
                await searchApps()
            }

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

    private func setEnabled(_ enabled: Bool, for appId: String, in list: inout [OmiApp]) {
        guard let index = list.firstIndex(where: { $0.id == appId }) else { return }
        list[index].enabled = enabled
    }

    private func setEnabled(_ enabled: Bool, for appId: String, in list: inout [OmiApp]?) {
        guard var updatedList = list else { return }
        setEnabled(enabled, for: appId, in: &updatedList)
        list = updatedList
    }

    private func cachedFilteredApps(for key: FilterKey) -> FilterCacheEntry? {
        guard let cached = filteredAppsCache[key] else { return nil }
        filteredAppsCacheOrder.removeAll { $0 == key }
        filteredAppsCacheOrder.append(key)
        return cached
    }

    private func cacheFilteredApps(_ entry: FilterCacheEntry, for key: FilterKey) {
        filteredAppsCache[key] = entry
        filteredAppsCacheOrder.removeAll { $0 == key }
        filteredAppsCacheOrder.append(key)

        while filteredAppsCacheOrder.count > filteredAppsCacheLimit {
            let staleKey = filteredAppsCacheOrder.removeFirst()
            filteredAppsCache[staleKey] = nil
        }
    }

    private func removeCachedFilteredApps(for key: FilterKey) {
        filteredAppsCache[key] = nil
        filteredAppsCacheOrder.removeAll { $0 == key }
    }

    private func updateCachedEnabledState(appId: String, enabled: Bool) {
        for key in Array(filteredAppsCache.keys) {
            if key.installedOnly {
                removeCachedFilteredApps(for: key)
                continue
            }

            guard var cached = filteredAppsCache[key],
                  let index = cached.apps.firstIndex(where: { $0.id == appId }) else { continue }
            cached.apps[index].enabled = enabled
            cacheFilteredApps(cached, for: key)
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

    /// Clear all marketplace filter/search state. Fresh catalog presentations
    /// (the Home popup) call this so they open on the unfiltered sections
    /// instead of whatever filters an earlier visit left behind. Results from
    /// searches still in flight are discarded by their `currentFilterKey`
    /// guard once this runs.
    func clearFilters() {
        searchQuery = ""
        selectedCategory = nil
        selectedCapability = nil
        showInstalledOnly = false
        filteredApps = nil
        filteredAppsOffset = 0
        hasMoreFilteredApps = false
    }
}
