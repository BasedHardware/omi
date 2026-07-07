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
    static let omiDeviceHistoryDefaultsKey = "home-omi-device-account-history"

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
    @Published var accountHasOmiDeviceConversations = UserDefaults.standard.bool(
        forKey: HomeStatusStore.omiDeviceHistoryDefaultsKey)

    private var lastRefreshAt = Date.distantPast
    private var isRefreshing = false
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
        defer { isRefreshing = false }

        async let importConnectorStatuses: Void = importConnectorStatusStore.refresh()
        async let screenshots: Void = loadScreenshotCount()
        async let knowledgeCounts: Void = loadKnowledgeCounts()
        async let exportStatuses: Void = loadMemoryExportStatuses()
        _ = await (importConnectorStatuses, screenshots, knowledgeCounts, exportStatuses)
    }

    /// Clear per-account data on sign-out/account switch.
    func resetSessionState() {
        screenshotCount = nil
        conversationCount = nil
        memoryCount = nil
        taskCount = nil
        memoryExportStatuses = [:]
        accountHasOmiDeviceConversations = UserDefaults.standard.bool(
            forKey: HomeStatusStore.omiDeviceHistoryDefaultsKey)
        lastRefreshAt = .distantPast
    }

    // MARK: - Loaders

    private func loadScreenshotCount() async {
        let stats = await RewindIndexer.shared.getStats()
        screenshotCount = stats?.total
    }

    private func loadMemoryExportStatuses() async {
        let statuses = await MemoryExportService.shared.allStatuses()
        memoryExportStatuses = statuses
    }

    /// Load the true totals behind the "What omi knows" tiles. Conversations come
    /// from the server count endpoint (not stored locally); memories and tasks are
    /// counted from the synced local DB — the same totals the detail pages show.
    private func loadKnowledgeCounts() async {
        async let convos = try? APIClient.shared.getConversationsCount(includeDiscarded: false)
        async let mems = try? MemoryStorage.shared.getLocalMemoriesCount()
        // Open tasks only (matches the "Tasks" label and the old tile's intent —
        // the old value just under-counted, capping each bucket at a 7-day window).
        async let tasks = try? ActionItemStorage.shared.getLocalActionItemsCount(completed: false)
        let shouldLoadDeviceHistory = !accountHasOmiDeviceConversations
        async let deviceHistory = shouldLoadDeviceHistory ? loadOmiDeviceHistory() : nil
        let (c, m, t, d) = await (convos, mems, tasks, deviceHistory)
        if let c { conversationCount = c }
        if let m { memoryCount = m }
        if let t { taskCount = t }
        // Sticky: device history never un-happens; keep the badge across
        // launches and network failures once observed.
        if d == true {
            accountHasOmiDeviceConversations = true
            UserDefaults.standard.set(true, forKey: Self.omiDeviceHistoryDefaultsKey)
        }
    }

    private func loadOmiDeviceHistory() async -> Bool? {
        try? await APIClient.shared.hasOmiDeviceConversations()
    }
}
