import Combine
import Foundation
import SwiftUI

/// Persistent owner of the Home page's status data: knowledge counts,
/// import-connector and MCP-export statuses, and the refresh cooldown.
///
/// Lives in `ViewModelContainer` so navigating away and back to Home renders
/// instantly from cached values instead of refetching — the page view itself
/// is recreated on every tab switch, so any state kept on the page (including
/// its refresh cooldown) dies with it and turns each visit into a refetch
/// storm (2 network calls + Rewind DB stats + local counts + connector and
/// MCP status scans).
@MainActor
final class HomeStatusStore: ObservableObject {
    static let legacyOmiDeviceHistoryDefaultsKey = "home-omi-device-account-history"
    static let omiDeviceHistoryDefaultsKeyPrefix = "home-omi-device-account-history."

    /// Import-connector (Gmail, Notes, …) status cache. Owned here so the
    /// connected badges don't reset to unknown on every Home visit.
    let importConnectorStatusStore = ImportConnectorStatusStore()

    // True totals for the "What omi knows" tiles. Without these the tiles
    // showed only the loaded page (~50 conversations, ~100 memories), badly
    // undercounting.
    @Published var screenshotCount: Int?
    @Published var conversationCount: Int?
    @Published var memoryCount: Int?
    @Published var taskCount: Int?
    @Published var memoryExportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]
    /// Wearable used on this account (any friend/omi-sourced conversation).
    /// Seeded from UserDefaults so the badge is instant on later launches.
    @Published var accountHasOmiDeviceConversations = HomeStatusStore.cachedOmiDeviceHistory()

    private var lastRefreshAt = Date.distantPast
    private var isRefreshing = false
    private var refreshGeneration = 0
    private var cancellables: Set<AnyCancellable> = []

    init() {
        // The nested connector store publishes its own changes; forward them
        // so views observing this store re-render connected badges.
        importConnectorStatusStore.objectWillChange
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    /// Refresh all Home status data. Non-forced calls share the app-wide
    /// activation cooldown (so tab switches and Cmd-Tab bursts render from
    /// cache), and calls are coalesced while a refresh is in flight.
    func refresh(force: Bool) async {
        let now = Date()
        if !force,
            !PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastRefreshAt)
        {
            return
        }
        guard !isRefreshing else { return }
        isRefreshing = true
        lastRefreshAt = now
        let generation = refreshGeneration
        defer {
            if generation == refreshGeneration {
                isRefreshing = false
            }
        }

        async let importConnectorStatuses: Void = importConnectorStatusStore.refresh()
        async let screenshots = loadScreenshotCount()
        async let knowledgeCounts = loadKnowledgeCounts()
        async let exportStatuses = loadMemoryExportStatuses()
        let (_, screenshotCount, counts, statuses) = await (
            importConnectorStatuses, screenshots, knowledgeCounts, exportStatuses)

        guard generation == refreshGeneration else { return }
        self.screenshotCount = screenshotCount
        if let conversationCount = counts.conversationCount {
            self.conversationCount = conversationCount
        }
        if let memoryCount = counts.memoryCount {
            self.memoryCount = memoryCount
        }
        if let taskCount = counts.taskCount {
            self.taskCount = taskCount
        }
        if counts.hasOmiDeviceHistory == true {
            accountHasOmiDeviceConversations = true
            Self.setCachedOmiDeviceHistory()
        }
        memoryExportStatuses = statuses
    }

    /// Clear per-account data on sign-out/account switch.
    func resetSessionState() {
        refreshGeneration += 1
        isRefreshing = false
        screenshotCount = nil
        conversationCount = nil
        memoryCount = nil
        taskCount = nil
        memoryExportStatuses = [:]
        accountHasOmiDeviceConversations = Self.cachedOmiDeviceHistory()
        importConnectorStatusStore.resetSessionState()
        lastRefreshAt = .distantPast
    }

    // MARK: - Loaders

    private struct KnowledgeCounts {
        var conversationCount: Int?
        var memoryCount: Int?
        var taskCount: Int?
        var hasOmiDeviceHistory: Bool?
    }

    private func loadScreenshotCount() async -> Int? {
        let stats = await RewindIndexer.shared.getStats()
        return stats?.total
    }

    private func loadMemoryExportStatuses() async -> [MemoryExportDestination: MemoryExportStatus] {
        await MemoryExportService.shared.allStatuses()
    }

    /// Load the true totals behind the "What omi knows" tiles. Conversations come
    /// from the server count endpoint (not stored locally); memories and tasks are
    /// counted from the synced local DB — the same totals the detail pages show.
    private func loadKnowledgeCounts() async -> KnowledgeCounts {
        async let convos = try? APIClient.shared.getConversationsCount(includeDiscarded: false)
        async let mems = try? MemoryStorage.shared.getLocalMemoriesCount()
        // Open tasks only (matches the "Tasks" label and the old tile's intent —
        // the old value just under-counted, capping each bucket at a 7-day window).
        async let tasks = try? ActionItemStorage.shared.getLocalActionItemsCount(completed: false)
        let shouldLoadDeviceHistory = !accountHasOmiDeviceConversations
        async let deviceHistory = shouldLoadDeviceHistory ? loadOmiDeviceHistory() : nil
        let (c, m, t, d) = await (convos, mems, tasks, deviceHistory)
        return KnowledgeCounts(
            conversationCount: c,
            memoryCount: m,
            taskCount: t,
            hasOmiDeviceHistory: d
        )
    }

    private func loadOmiDeviceHistory() async -> Bool? {
        try? await APIClient.shared.hasOmiDeviceConversations()
    }

    private static func cachedOmiDeviceHistory(defaults: UserDefaults = .standard) -> Bool {
        guard let key = omiDeviceHistoryDefaultsKey(defaults: defaults) else { return false }
        if defaults.object(forKey: key) == nil,
            defaults.bool(forKey: legacyOmiDeviceHistoryDefaultsKey)
        {
            defaults.set(true, forKey: key)
            defaults.removeObject(forKey: legacyOmiDeviceHistoryDefaultsKey)
        }
        return defaults.bool(forKey: key)
    }

    private static func setCachedOmiDeviceHistory(defaults: UserDefaults = .standard) {
        guard let key = omiDeviceHistoryDefaultsKey(defaults: defaults) else { return }
        defaults.set(true, forKey: key)
    }

    private static func omiDeviceHistoryDefaultsKey(defaults: UserDefaults = .standard) -> String? {
        guard let userId = defaults.string(forKey: .authUserId), !userId.isEmpty else { return nil }
        return omiDeviceHistoryDefaultsKeyPrefix + userId
    }
}
