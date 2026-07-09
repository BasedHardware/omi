import Combine
import Foundation

struct HomeKnowledgeCounts: Equatable, Sendable {
    let conversations: Int?
    let memories: Int?
    let tasks: Int?
    let hasOmiDeviceConversations: Bool?
}

@MainActor
struct HomeStatusLoader {
    let refreshConnectorStatuses: () async -> Void
    let loadScreenshotCount: () async -> Int?
    let loadKnowledgeCounts: (_ includeOmiDeviceHistory: Bool) async -> HomeKnowledgeCounts
    let loadMemoryExportStatuses: () async -> [MemoryExportDestination: MemoryExportStatus]

    static func live(connectorStatusStore: ImportConnectorStatusStore) -> HomeStatusLoader {
        HomeStatusLoader(
            refreshConnectorStatuses: {
                await connectorStatusStore.refresh()
            },
            loadScreenshotCount: {
                let stats = await RewindIndexer.shared.getStats()
                return stats?.total
            },
            loadKnowledgeCounts: { includeOmiDeviceHistory in
                async let conversations = try? APIClient.shared.getConversationsCount(includeDiscarded: false)
                async let memories = try? MemoryStorage.shared.getLocalMemoriesCount()
                async let tasks = try? ActionItemStorage.shared.getLocalActionItemsCount(completed: false)
                async let deviceHistory = includeOmiDeviceHistory
                    ? (try? APIClient.shared.hasOmiDeviceConversations())
                    : nil

                return await HomeKnowledgeCounts(
                    conversations: conversations,
                    memories: memories,
                    tasks: tasks,
                    hasOmiDeviceConversations: deviceHistory
                )
            },
            loadMemoryExportStatuses: {
                await MemoryExportService.shared.allStatuses()
            }
        )
    }
}

/// Long-lived cache for status data shown on Home. The view is intentionally
/// recreated during navigation; this store is owned by ViewModelContainer so
/// returning to Home can render cached values without repeating provider scans.
@MainActor
final class HomeStatusStore: ObservableObject {
    static let omiDeviceHistoryDefaultsKey = "home-omi-device-account-history"

    let connectorStatusStore: ImportConnectorStatusStore

    @Published private(set) var screenshotCount: Int?
    @Published private(set) var conversationCount: Int?
    @Published private(set) var memoryCount: Int?
    @Published private(set) var taskCount: Int?
    @Published private(set) var accountHasOmiDeviceConversations: Bool
    @Published var memoryExportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]

    private let defaults: UserDefaults
    private let loader: HomeStatusLoader
    private var lastRefreshAt = Date.distantPast
    private var refreshTask: Task<Void, Never>?
    private var refreshID: UUID?
    private var latestKnowledgeRefreshID: UUID?
    private var refreshGeneration = 0
    private var cancellables = Set<AnyCancellable>()

    init(
        connectorStatusStore: ImportConnectorStatusStore? = nil,
        defaults: UserDefaults = .standard,
        loader: HomeStatusLoader? = nil
    ) {
        let connectorStatusStore = connectorStatusStore ?? ImportConnectorStatusStore(defaults: defaults)
        self.connectorStatusStore = connectorStatusStore
        self.defaults = defaults
        self.loader = loader ?? .live(connectorStatusStore: connectorStatusStore)
        accountHasOmiDeviceConversations = defaults.bool(forKey: Self.omiDeviceHistoryDefaultsKey)

        connectorStatusStore.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        connectorStatusStore.connectorDidSync
            .sink { [weak self] _ in
                self?.refreshKnowledgeCountsAfterImport()
            }
            .store(in: &cancellables)
    }

    func refreshIfNeeded(force: Bool = false, now: Date = Date()) async {
        if let refreshTask {
            await refreshTask.value
            return
        }

        guard force || PollingConfig.shouldAllowActivationRefresh(now: now, lastRefresh: lastRefreshAt) else {
            return
        }

        lastRefreshAt = now
        let generation = refreshGeneration
        let refreshID = UUID()
        let task = Task { [weak self] in
            guard let self else { return }
            await self.performRefresh(generation: generation)
        }
        self.refreshID = refreshID
        refreshTask = task
        await task.value
        if self.refreshID == refreshID {
            self.refreshID = nil
            refreshTask = nil
        }
    }

    func resetSessionState() {
        refreshGeneration += 1
        refreshTask?.cancel()
        refreshTask = nil
        refreshID = nil
        latestKnowledgeRefreshID = nil
        lastRefreshAt = .distantPast
        screenshotCount = nil
        conversationCount = nil
        memoryCount = nil
        taskCount = nil
        memoryExportStatuses = [:]
        accountHasOmiDeviceConversations = defaults.bool(forKey: Self.omiDeviceHistoryDefaultsKey)
    }

    private func performRefresh(generation: Int) async {
        let includeDeviceHistory = !accountHasOmiDeviceConversations
        let knowledgeRefreshID = beginKnowledgeRefresh()
        async let connectorStatuses: Void = loader.refreshConnectorStatuses()
        async let screenshots = loader.loadScreenshotCount()
        async let knowledgeCounts = loader.loadKnowledgeCounts(includeDeviceHistory)
        async let exportStatuses = loader.loadMemoryExportStatuses()
        let (_, loadedScreenshots, loadedKnowledgeCounts, loadedExportStatuses) = await (
            connectorStatuses,
            screenshots,
            knowledgeCounts,
            exportStatuses
        )

        guard !Task.isCancelled, generation == refreshGeneration else { return }
        apply(screenshotCount: loadedScreenshots)
        if knowledgeRefreshID == latestKnowledgeRefreshID {
            apply(knowledgeCounts: loadedKnowledgeCounts)
        }
        memoryExportStatuses = loadedExportStatuses
    }

    private func refreshKnowledgeCountsAfterImport() {
        let generation = refreshGeneration
        let knowledgeRefreshID = beginKnowledgeRefresh()
        Task { [weak self] in
            guard let self else { return }
            let counts = await self.loader.loadKnowledgeCounts(!self.accountHasOmiDeviceConversations)
            guard !Task.isCancelled,
                  generation == self.refreshGeneration,
                  knowledgeRefreshID == self.latestKnowledgeRefreshID
            else { return }
            self.apply(knowledgeCounts: counts)
        }
    }

    private func beginKnowledgeRefresh() -> UUID {
        let refreshID = UUID()
        latestKnowledgeRefreshID = refreshID
        return refreshID
    }

    private func apply(screenshotCount: Int?) {
        if let screenshotCount {
            self.screenshotCount = screenshotCount
        }
    }

    private func apply(knowledgeCounts: HomeKnowledgeCounts) {
        if let conversations = knowledgeCounts.conversations {
            conversationCount = conversations
        }
        if let memories = knowledgeCounts.memories {
            memoryCount = memories
        }
        if let tasks = knowledgeCounts.tasks {
            taskCount = tasks
        }
        if knowledgeCounts.hasOmiDeviceConversations == true {
            accountHasOmiDeviceConversations = true
            defaults.set(true, forKey: Self.omiDeviceHistoryDefaultsKey)
        }
    }
}
