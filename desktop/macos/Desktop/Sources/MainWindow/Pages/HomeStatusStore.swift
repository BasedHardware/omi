import Combine
import Foundation

extension Notification.Name {
  /// Posted after local memory/task visibility changes so Home never waits for
  /// the activation cooldown before showing the new totals.
  static let homeKnowledgeCountsDidChange = Notification.Name("com.omi.desktop.homeKnowledgeCountsDidChange")
}

enum HomeKnowledgeCountInvalidation {
  static func post() {
    NotificationCenter.default.post(name: .homeKnowledgeCountsDidChange, object: nil)
  }

  static func post(logMessage: @autoclosure () -> String) {
    log(logMessage())
    post()
  }
}

struct HomeKnowledgeCounts: Equatable, Sendable {
  let conversations: Int?
  let memories: Int?
  let tasks: Int?
  let hasOmiDeviceConversations: Bool?
}

@MainActor
struct HomeStatusLoader {
  let refreshConnectorStatuses: @MainActor @Sendable () async -> Void
  let loadScreenshotCount: @MainActor @Sendable () async -> Int?
  let loadKnowledgeCounts: @MainActor @Sendable (_ includeOmiDeviceHistory: Bool) async -> HomeKnowledgeCounts
  let loadMemoryExportStatuses: @MainActor @Sendable () async -> [MemoryExportDestination: MemoryExportStatus]

  static func live(connectorStatusStore: ImportConnectorStatusStore) -> HomeStatusLoader {
    HomeStatusLoader(
      refreshConnectorStatuses: {
        await connectorStatusStore.refresh()
      },
      loadScreenshotCount: {
        do {
          return try await RewindDatabase.shared.getScreenshotCount()
        } catch {
          logError("HomeStatusLoader: Failed to load screenshot count", error: error)
          return nil
        }
      },
      loadKnowledgeCounts: { includeOmiDeviceHistory in
        async let conversations = try? APIClient.shared.getConversationsCount(includeDiscarded: false)
        async let memories = try? MemoryStorage.shared.getLocalMemoriesCount()
        async let tasks = try? ActionItemStorage.shared.getLocalActionItemsCount(completed: false)
        async let deviceHistory =
          includeOmiDeviceHistory
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
  static let omiDeviceHistoryDefaultsKey = DefaultsKey.homeOmiDeviceAccountHistory.rawValue

  let connectorStatusStore: ImportConnectorStatusStore

  @Published private(set) var screenshotCount: Int?
  @Published private(set) var conversationCount: Int?
  @Published private(set) var memoryCount: Int?
  @Published private(set) var taskCount: Int?
  @Published private(set) var accountHasOmiDeviceConversations: Bool
  @Published var memoryExportStatuses: [MemoryExportDestination: MemoryExportStatus] = [:]

  private let defaults: UserDefaults
  private let loader: HomeStatusLoader
  private let currentUserIDProvider: () -> String?
  private var sessionUserID: String?
  private var localDatabaseReady: Bool
  private var lastRefreshAt = Date.distantPast
  private var refreshTask: Task<Void, Never>?
  private var refreshID: UUID?
  private var latestKnowledgeRefreshID: UUID?
  private var knowledgeRefreshTask: Task<Void, Never>?
  private var knowledgeRefreshQueued = false
  private var refreshGeneration = 0
  private var cancellables = Set<AnyCancellable>()

  init(
    connectorStatusStore: ImportConnectorStatusStore? = nil,
    defaults: UserDefaults = .standard,
    loader: HomeStatusLoader? = nil,
    currentUserIDProvider: (() -> String?)? = nil,
    localDatabaseReady: Bool = false
  ) {
    let currentUserIDProvider =
      currentUserIDProvider ?? {
        defaults.string(forKey: .authUserId)
      }
    let sessionUserID = Self.normalizedUserID(currentUserIDProvider())
    let connectorStatusStore =
      connectorStatusStore
      ?? ImportConnectorStatusStore(defaults: defaults, sessionUserID: sessionUserID)
    self.connectorStatusStore = connectorStatusStore
    self.defaults = defaults
    self.loader = loader ?? .live(connectorStatusStore: connectorStatusStore)
    self.currentUserIDProvider = currentUserIDProvider
    self.sessionUserID = sessionUserID
    self.localDatabaseReady = localDatabaseReady
    accountHasOmiDeviceConversations = Self.loadPersistedDeviceHistory(
      defaults: defaults,
      userID: sessionUserID
    )
    connectorStatusStore.setSessionUserID(sessionUserID)

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

    NotificationCenter.default.publisher(for: .homeKnowledgeCountsDidChange)
      .receive(on: DispatchQueue.main)
      .sink { [weak self] _ in
        self?.refreshKnowledgeCountsAfterImport()
      }
      .store(in: &cancellables)
  }

  func refreshIfNeeded(force: Bool = false, now: Date = Date()) async {
    ensureCurrentSessionScope()

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
    resetTransientState()
    sessionUserID = nil
    connectorStatusStore.setSessionUserID(nil)
    accountHasOmiDeviceConversations = false
  }

  /// The Rewind database has opened for the current owner. Load the local
  /// screenshot metric immediately instead of waiting for the Home refresh
  /// cooldown after a pre-startup refresh skipped it.
  func databaseDidBecomeReady() async {
    ensureCurrentSessionScope()
    localDatabaseReady = true

    let generation = refreshGeneration
    let loadedScreenshotCount = await loader.loadScreenshotCount()
    guard !Task.isCancelled,
      generation == refreshGeneration,
      localDatabaseReady
    else { return }
    apply(screenshotCount: loadedScreenshotCount)
  }

  private func resetTransientState() {
    refreshGeneration += 1
    refreshTask?.cancel()
    refreshTask = nil
    refreshID = nil
    latestKnowledgeRefreshID = nil
    knowledgeRefreshTask?.cancel()
    knowledgeRefreshTask = nil
    knowledgeRefreshQueued = false
    lastRefreshAt = .distantPast
    localDatabaseReady = false
    screenshotCount = nil
    conversationCount = nil
    memoryCount = nil
    taskCount = nil
    memoryExportStatuses = [:]
  }

  private func ensureCurrentSessionScope() {
    let currentUserID = Self.normalizedUserID(currentUserIDProvider())
    guard currentUserID != sessionUserID else { return }

    resetTransientState()
    sessionUserID = currentUserID
    connectorStatusStore.setSessionUserID(currentUserID)
    accountHasOmiDeviceConversations = Self.loadPersistedDeviceHistory(
      defaults: defaults,
      userID: currentUserID
    )
  }

  private func performRefresh(generation: Int) async {
    let includeDeviceHistory = !accountHasOmiDeviceConversations
    let shouldLoadScreenshotCount = localDatabaseReady
    let knowledgeRefreshID = beginKnowledgeRefresh()
    async let connectorStatuses: Void = loader.refreshConnectorStatuses()
    async let screenshots: Int? = shouldLoadScreenshotCount ? loader.loadScreenshotCount() : nil
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
    ensureCurrentSessionScope()
    guard knowledgeRefreshTask == nil else {
      knowledgeRefreshQueued = true
      return
    }

    let generation = refreshGeneration
    let knowledgeRefreshID = beginKnowledgeRefresh()
    let task = Task { [weak self] in
      guard let self else { return }
      let counts = await self.loader.loadKnowledgeCounts(!self.accountHasOmiDeviceConversations)
      guard !Task.isCancelled,
        generation == self.refreshGeneration,
        knowledgeRefreshID == self.latestKnowledgeRefreshID
      else {
        self.completeKnowledgeRefresh(id: knowledgeRefreshID)
        return
      }
      self.apply(knowledgeCounts: counts)
      self.completeKnowledgeRefresh(id: knowledgeRefreshID)
    }
    knowledgeRefreshTask = task
  }

  private func completeKnowledgeRefresh(id: UUID) {
    guard id == latestKnowledgeRefreshID else { return }
    knowledgeRefreshTask = nil
    guard knowledgeRefreshQueued else { return }
    knowledgeRefreshQueued = false
    refreshKnowledgeCountsAfterImport()
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
      if let key = Self.deviceHistoryDefaultsKey(userID: sessionUserID) {
        defaults.set(true, forKey: key)
      }
    }
  }

  private static func normalizedUserID(_ userID: String?) -> String? {
    let trimmed = userID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return trimmed.isEmpty ? nil : trimmed
  }

  private static func deviceHistoryDefaultsKey(userID: String?) -> String? {
    guard let userID = normalizedUserID(userID) else { return nil }
    return "\(omiDeviceHistoryDefaultsKey).user.\(userID)"
  }

  private static func loadPersistedDeviceHistory(defaults: UserDefaults, userID: String?) -> Bool {
    guard let scopedKey = deviceHistoryDefaultsKey(userID: userID) else { return false }

    if defaults.object(forKey: scopedKey) == nil,
      defaults.object(forKey: .homeOmiDeviceAccountHistory) != nil
    {
      defaults.set(defaults.bool(forKey: .homeOmiDeviceAccountHistory), forKey: scopedKey)
      defaults.removeObject(forKey: .homeOmiDeviceAccountHistory)
    }
    return defaults.bool(forKey: scopedKey)
  }
}
