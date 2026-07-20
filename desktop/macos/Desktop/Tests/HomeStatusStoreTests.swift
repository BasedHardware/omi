import XCTest

@testable import Omi_Computer

@MainActor
final class HomeStatusStoreTests: XCTestCase {
  func testRefreshUsesCachedValuesUntilCooldownExpires() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    var connectorLoads = 0
    var screenshotLoads = 0
    var knowledgeLoads = 0
    var exportLoads = 0
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: { connectorLoads += 1 },
        loadScreenshotCount: {
          screenshotLoads += 1
          return screenshotLoads
        },
        loadKnowledgeCounts: { _ in
          knowledgeLoads += 1
          return HomeKnowledgeCounts(
            conversations: knowledgeLoads,
            memories: knowledgeLoads,
            tasks: knowledgeLoads,
            hasOmiDeviceConversations: false
          )
        },
        loadMemoryExportStatuses: {
          exportLoads += 1
          return [:]
        }
      ),
      localDatabaseReady: true
    )
    let start = Date(timeIntervalSince1970: 10_000)

    await store.refreshIfNeeded(now: start)
    await store.refreshIfNeeded(now: start.addingTimeInterval(1))

    XCTAssertEqual(connectorLoads, 1)
    XCTAssertEqual(screenshotLoads, 1)
    XCTAssertEqual(knowledgeLoads, 1)
    XCTAssertEqual(exportLoads, 1)
    XCTAssertEqual(store.screenshotCount, 1)
    XCTAssertEqual(store.conversationCount, 1)

    await store.refreshIfNeeded(now: start.addingTimeInterval(PollingConfig.activationCooldown))

    XCTAssertEqual(connectorLoads, 2)
    XCTAssertEqual(screenshotLoads, 2)
    XCTAssertEqual(knowledgeLoads, 2)
    XCTAssertEqual(exportLoads, 2)
    XCTAssertEqual(store.screenshotCount, 2)
    XCTAssertEqual(store.conversationCount, 2)
  }

  func testConcurrentRefreshesShareOneLoad() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    let gate = RefreshGate()
    var connectorLoads = 0
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: {
          connectorLoads += 1
          await gate.wait()
        },
        loadScreenshotCount: { nil },
        loadKnowledgeCounts: { _ in
          HomeKnowledgeCounts(
            conversations: nil,
            memories: nil,
            tasks: nil,
            hasOmiDeviceConversations: nil
          )
        },
        loadMemoryExportStatuses: { [:] }
      )
    )
    let now = Date(timeIntervalSince1970: 20_000)

    let first = Task { await store.refreshIfNeeded(now: now) }
    for _ in 0..<100 where connectorLoads == 0 {
      await Task.yield()
    }
    XCTAssertEqual(connectorLoads, 1)
    let second = Task { await store.refreshIfNeeded(now: now) }
    await Task.yield()

    XCTAssertEqual(connectorLoads, 1)

    gate.open()
    await first.value
    await second.value
    XCTAssertEqual(connectorLoads, 1)
  }

  func testDatabaseReadinessLoadsSkippedScreenshotCountWithoutWaitingForCooldown() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    var connectorLoads = 0
    var screenshotLoads = 0
    var knowledgeLoads = 0
    var exportLoads = 0
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: { connectorLoads += 1 },
        loadScreenshotCount: {
          screenshotLoads += 1
          return 73
        },
        loadKnowledgeCounts: { _ in
          knowledgeLoads += 1
          return HomeKnowledgeCounts(
            conversations: nil,
            memories: nil,
            tasks: nil,
            hasOmiDeviceConversations: nil
          )
        },
        loadMemoryExportStatuses: {
          exportLoads += 1
          return [:]
        }
      )
    )
    let start = Date(timeIntervalSince1970: 25_000)

    await store.refreshIfNeeded(now: start)

    XCTAssertEqual(screenshotLoads, 0)
    XCTAssertNil(store.screenshotCount)
    XCTAssertEqual(connectorLoads, 1)
    XCTAssertEqual(knowledgeLoads, 1)
    XCTAssertEqual(exportLoads, 1)

    await store.databaseDidBecomeReady()

    XCTAssertEqual(screenshotLoads, 1)
    XCTAssertEqual(store.screenshotCount, 73)

    await store.refreshIfNeeded(now: start.addingTimeInterval(1))

    XCTAssertEqual(
      screenshotLoads,
      1,
      "The readiness-triggered screenshot load must not wait for or bypass the normal Home refresh cooldown"
    )
    XCTAssertEqual(connectorLoads, 1)
    XCTAssertEqual(knowledgeLoads, 1)
    XCTAssertEqual(exportLoads, 1)
  }

  func testFailedScreenshotRefreshKeepsLastKnownCount() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    var results: [Int?] = [9, nil]
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: {},
        loadScreenshotCount: { results.removeFirst() },
        loadKnowledgeCounts: { _ in
          HomeKnowledgeCounts(
            conversations: nil,
            memories: nil,
            tasks: nil,
            hasOmiDeviceConversations: nil
          )
        },
        loadMemoryExportStatuses: { [:] }
      ),
      localDatabaseReady: true
    )

    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 27_000))
    XCTAssertEqual(store.screenshotCount, 9)

    await store.refreshIfNeeded(force: true, now: Date(timeIntervalSince1970: 27_001))

    XCTAssertEqual(store.screenshotCount, 9)
  }

  func testCompletedImportRefreshesOnlyKnowledgeCounts() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    var connectorLoads = 0
    var screenshotLoads = 0
    var knowledgeLoads = 0
    var exportLoads = 0
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: { connectorLoads += 1 },
        loadScreenshotCount: {
          screenshotLoads += 1
          return 4
        },
        loadKnowledgeCounts: { _ in
          knowledgeLoads += 1
          return HomeKnowledgeCounts(
            conversations: 10 + knowledgeLoads,
            memories: 20 + knowledgeLoads,
            tasks: 30 + knowledgeLoads,
            hasOmiDeviceConversations: false
          )
        },
        loadMemoryExportStatuses: {
          exportLoads += 1
          return [:]
        }
      ),
      localDatabaseReady: true
    )

    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 30_000))
    connectorStore.markSynced(connectorID: "email", sourceCount: 12)
    for _ in 0..<100 where knowledgeLoads < 2 {
      await Task.yield()
    }

    XCTAssertEqual(knowledgeLoads, 2)
    XCTAssertEqual(store.conversationCount, 12)
    XCTAssertEqual(store.memoryCount, 22)
    XCTAssertEqual(store.taskCount, 32)
    XCTAssertEqual(connectorLoads, 1)
    XCTAssertEqual(screenshotLoads, 1)
    XCTAssertEqual(exportLoads, 1)
  }

  func testCompletedImportCountsAreNotOverwrittenByOlderHomeRefresh() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    let connectorGate = RefreshGate()
    var knowledgeLoads = 0
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: { await connectorGate.wait() },
        loadScreenshotCount: { nil },
        loadKnowledgeCounts: { _ in
          knowledgeLoads += 1
          let count = knowledgeLoads == 1 ? 10 : 20
          return HomeKnowledgeCounts(
            conversations: count,
            memories: count,
            tasks: count,
            hasOmiDeviceConversations: false
          )
        },
        loadMemoryExportStatuses: { [:] }
      )
    )

    let homeRefresh = Task {
      await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 35_000))
    }
    for _ in 0..<100 where knowledgeLoads < 1 {
      await Task.yield()
    }
    XCTAssertEqual(knowledgeLoads, 1)

    connectorStore.markSynced(connectorID: "email", sourceCount: 12)
    for _ in 0..<100 where store.conversationCount != 20 {
      await Task.yield()
    }
    XCTAssertEqual(store.conversationCount, 20)

    connectorGate.open()
    await homeRefresh.value

    XCTAssertEqual(store.conversationCount, 20)
    XCTAssertEqual(store.memoryCount, 20)
    XCTAssertEqual(store.taskCount, 20)
  }

  func testRefreshFindsManualImportCompletedAfterStoreInitialization() async throws {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    defaults.set("user-a", forKey: "auth_userId")

    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: { connectorStore.refreshPersistedManualImportMetrics() },
        loadScreenshotCount: { nil },
        loadKnowledgeCounts: { _ in
          HomeKnowledgeCounts(
            conversations: nil,
            memories: nil,
            tasks: nil,
            hasOmiDeviceConversations: nil
          )
        },
        loadMemoryExportStatuses: { [:] }
      )
    )
    defaults.set(4, forKey: "onboardingChatGPTImportedMemoriesCount")

    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 37_500))

    let connector = try XCTUnwrap(ImportConnector.all.first { $0.id == "chatgpt" })
    let snapshot = connectorStore.snapshot(for: connector)
    XCTAssertTrue(snapshot.isConnected)
    XCTAssertEqual(snapshot.primaryText, "4 memories imported")
  }

  func testPersistedDeviceHistorySkipsDeviceLookup() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    defaults.set("user-a", forKey: "auth_userId")
    defaults.set(true, forKey: HomeStatusStore.omiDeviceHistoryDefaultsKey)

    var deviceLookupRequests: [Bool] = []
    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: {},
        loadScreenshotCount: { nil },
        loadKnowledgeCounts: { includeOmiDeviceHistory in
          deviceLookupRequests.append(includeOmiDeviceHistory)
          return HomeKnowledgeCounts(
            conversations: nil,
            memories: nil,
            tasks: nil,
            hasOmiDeviceConversations: nil
          )
        },
        loadMemoryExportStatuses: { [:] }
      )
    )

    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 40_000))

    XCTAssertTrue(store.accountHasOmiDeviceConversations)
    XCTAssertEqual(deviceLookupRequests, [false])
    XCTAssertNil(defaults.object(forKey: HomeStatusStore.omiDeviceHistoryDefaultsKey))
  }

  func testAccountSwitchDoesNotExposePreviousAccountStatus() async throws {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }
    defaults.set("user-a", forKey: "auth_userId")

    let connectorStore = ImportConnectorStatusStore(defaults: defaults)
    let store = HomeStatusStore(
      connectorStatusStore: connectorStore,
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: {},
        loadScreenshotCount: { nil },
        loadKnowledgeCounts: { _ in
          HomeKnowledgeCounts(
            conversations: nil,
            memories: nil,
            tasks: nil,
            hasOmiDeviceConversations: defaults.string(forKey: "auth_userId") == "user-a"
          )
        },
        loadMemoryExportStatuses: { [:] }
      )
    )
    let email = try XCTUnwrap(ImportConnector.all.first { $0.id == "email" })

    connectorStore.markSynced(connectorID: "email", sourceCount: 12)
    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 50_000))
    XCTAssertTrue(store.accountHasOmiDeviceConversations)
    XCTAssertTrue(connectorStore.snapshot(for: email).isConnected)

    defaults.set("user-b", forKey: "auth_userId")
    store.resetSessionState()
    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 50_100))

    XCTAssertFalse(store.accountHasOmiDeviceConversations)
    XCTAssertFalse(connectorStore.snapshot(for: email).isConnected)

    defaults.set("user-a", forKey: "auth_userId")
    await store.refreshIfNeeded(force: true, now: Date(timeIntervalSince1970: 50_200))

    XCTAssertTrue(store.accountHasOmiDeviceConversations)
    XCTAssertTrue(connectorStore.snapshot(for: email).isConnected)
    XCTAssertEqual(connectorStore.snapshot(for: email).primaryText, "12 emails")
  }

  func testKnowledgeCountChangeRefreshesCountsDuringActivationCooldown() async {
    let testDefaults = makeDefaults()
    let defaults = testDefaults.defaults
    defer { defaults.removePersistentDomain(forName: testDefaults.suiteName) }

    var knowledgeLoads = 0
    let store = HomeStatusStore(
      connectorStatusStore: ImportConnectorStatusStore(defaults: defaults),
      defaults: defaults,
      loader: HomeStatusLoader(
        refreshConnectorStatuses: {},
        loadScreenshotCount: { nil },
        loadKnowledgeCounts: { _ in
          knowledgeLoads += 1
          return HomeKnowledgeCounts(
            conversations: nil,
            memories: knowledgeLoads,
            tasks: knowledgeLoads,
            hasOmiDeviceConversations: nil
          )
        },
        loadMemoryExportStatuses: { [:] }
      )
    )

    await store.refreshIfNeeded(now: Date(timeIntervalSince1970: 40_000))
    NotificationCenter.default.post(name: .homeKnowledgeCountsDidChange, object: nil)
    for _ in 0..<100 where knowledgeLoads < 2 {
      await Task.yield()
    }

    XCTAssertEqual(knowledgeLoads, 2)
    XCTAssertEqual(store.memoryCount, 2)
    XCTAssertEqual(store.taskCount, 2)
  }

  private func makeDefaults() -> (defaults: UserDefaults, suiteName: String) {
    let suiteName = "HomeStatusStoreTests.\(UUID().uuidString)"
    return (UserDefaults(suiteName: suiteName)!, suiteName)
  }
}

@MainActor
private final class RefreshGate {
  private var isOpen = false
  private var continuations: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    guard !isOpen else { return }
    await withCheckedContinuation { continuation in
      continuations.append(continuation)
    }
  }

  func open() {
    isOpen = true
    let pending = continuations
    continuations.removeAll()
    pending.forEach { $0.resume() }
  }
}
