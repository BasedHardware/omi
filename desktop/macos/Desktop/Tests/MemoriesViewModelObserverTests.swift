import AppKit
import XCTest

@testable import Omi_Computer

/// Tests for `MemoriesViewModel` auto-refresh observer wiring (#6500).
///
/// After replacing the 30-second `Timer.publish` with `didBecomeActive` +
/// `.refreshAllData` subscribers, the view model must still refresh when
/// those notifications fire. Because `MemoriesViewModel` is not a singleton,
/// each test constructs a fresh instance (triggering `init()` which registers
/// the two subscribers into its private `cancellables`) and asserts that
/// posting each notification advances `refreshInvocations` by one.
@MainActor
final class MemoriesViewModelObserverTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot!

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-vm-observer")
    testUserId = fixture.testUserId
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: testUserId)
  }

  override func tearDown() async throws {
    RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  func testDidBecomeActiveNotificationTriggersRefresh() async {
    let viewModel = MemoriesViewModel()
    XCTAssertEqual(viewModel.refreshInvocations, 0, "Fresh instance must start at zero")

    NotificationCenter.default.post(
      name: NSApplication.didBecomeActiveNotification, object: nil
    )
    await Task.yield()
    try? await Task.sleep(nanoseconds: 50_000_000)

    XCTAssertEqual(
      viewModel.refreshInvocations, 1,
      "didBecomeActive must route to refreshMemoriesIfNeeded() via the activation subscriber"
    )
  }

  func testRefreshAllDataNotificationTriggersRefresh() async {
    let viewModel = MemoriesViewModel()

    NotificationCenter.default.post(name: .refreshAllData, object: nil)
    await Task.yield()
    try? await Task.sleep(nanoseconds: 50_000_000)

    XCTAssertEqual(
      viewModel.refreshInvocations, 1,
      ".refreshAllData (Cmd+R) must route to refreshMemoriesIfNeeded() via the refresh subscriber"
    )
  }

  func testRefreshWaitsForActiveInitialLoadBeforeReturning() async {
    let viewModel = MemoriesViewModel()
    viewModel.isActive = true
    viewModel.isLoading = true

    // Force the bridge-search interleave: its refresh reaches the view model
    // while navigation's initial load still owns the projection. This must
    // suspend at the lifecycle barrier rather than silently no-op.
    let refresh = Task { await viewModel.refreshMemoriesIfNeeded() }
    await Task.yield()
    XCTAssertEqual(viewModel.memoryLoadLifecycleWaiterCount, 1)

    viewModel.isLoading = false
    await refresh.value

    XCTAssertEqual(viewModel.memoryLoadLifecycleWaiterCount, 0)
    XCTAssertEqual(viewModel.refreshInvocations, 1)
  }

  /// Auto-refresh must fetch the selected temporal view, not the legacy
  /// released view. The pre-fix refresh called `getMemoriesPage` without a
  /// view, then committed that released-view cursor — so with History
  /// selected, `loadMore()` resumed a released-issued cursor as the history
  /// view and pages skipped/mixed projections. Refresh must also commit the
  /// cursor from its own response.
  func testAutoRefreshFetchesTheSelectedTemporalViewAndCommitsItsCursor() async throws {
    let viewModel = MemoriesViewModel()
    viewModel.isActive = true
    // Keep loadMemories' one-time background tails off the network: latch the
    // default-scope full sync for this throwaway user (key mirrors
    // performFullSyncIfNeeded) and serve the cache reconcile an empty
    // terminal page through its own seam.
    let userId = try XCTUnwrap(testUserId)
    let defaultScopeSyncKey = "memoriesDefaultScopeSyncCompleted_v3_\(userId)"
    UserDefaults.standard.set(true, forKey: defaultScopeSyncKey)
    viewModel.reconcilePageFetch = { _, _, _ in
      APIClient.MemoryListPage(
        memories: [],
        nextCursor: nil,
        canonicalLifecycleExposed: false,
        deviceScopeSupported: nil,
        defaultMemoryDeleteSupported: false,
        truncated: false,
        beliefEnabled: nil)
    }

    var requestedViews: [APIClient.MemoryTemporalView?] = []
    viewModel.memoriesPageFetch = { _, _, _, _, _, view, _ in
      requestedViews.append(view)
      // Distinct cursor per request proves which response the refresh
      // committed. Every page advertises the belief capability so the
      // History selection stays mounted.
      return APIClient.MemoryListPage(
        memories: [],
        nextCursor: "history-stage-\(requestedViews.count)",
        canonicalLifecycleExposed: true,
        deviceScopeSupported: nil,
        defaultMemoryDeleteSupported: false,
        truncated: false,
        beliefEnabled: true)
    }

    viewModel.selectedTemporalFilter = .history
    // Let the didSet-spawned initial load reach the fetch seam, so the
    // refresh below suspends at the lifecycle barrier until it settles.
    for _ in 0..<200 where requestedViews.isEmpty {
      await Task.yield()
    }
    XCTAssertFalse(requestedViews.isEmpty, "Initial load must reach the fetch seam")

    await viewModel.refreshMemoriesIfNeeded()

    // Handshake: page one discovers the capability without a view, then the
    // explicit-view restart fetches history before retaining its cursor.
    XCTAssertEqual(requestedViews.count, 3)
    XCTAssertNil(requestedViews[0])
    XCTAssertEqual(requestedViews[1], .history)
    // Auto-refresh must fetch the selected temporal view too — a released-view
    // response would donate a cursor that loadMore() pages as the history
    // view — and the committed cursor must come from that same response.
    XCTAssertEqual(requestedViews[2], .history)
    XCTAssertEqual(viewModel.backendCursorForTesting, "history-stage-3")
  }

  func testConversationDeletedNotificationTriggersCascadeHandler() async throws {
    let conversationId = "conv-cascade-test"
    let linkedMemory = makeMemory(id: "mem-linked", conversationId: conversationId)
    let otherMemory = makeMemory(id: "mem-other", conversationId: "conv-keep")

    try await MemoryStorage.shared.syncServerMemories([linkedMemory, otherMemory])

    let viewModel = MemoriesViewModel()
    let cached = try await MemoryStorage.shared.getLocalMemories(limit: 50, offset: 0)
    viewModel.memories = cached
    XCTAssertTrue(viewModel.memories.contains { $0.conversationId == conversationId })

    NotificationCenter.default.post(
      name: .conversationDeleted,
      object: nil,
      userInfo: ["conversationId": conversationId]
    )
    await Task.yield()
    try? await Task.sleep(nanoseconds: 200_000_000)

    XCTAssertEqual(
      viewModel.conversationDeleteInvocations, 1,
      ".conversationDeleted must route to handleConversationDeleted() via the cascade subscriber"
    )
    XCTAssertFalse(
      viewModel.memories.contains { $0.conversationId == conversationId },
      "In-memory cache must drop memories for the deleted conversation"
    )
    XCTAssertTrue(
      viewModel.memories.contains { $0.id == otherMemory.id },
      "Unrelated memories must remain after cascade"
    )

    let linkedRecord = try await MemoryStorage.shared.getMemoryByBackendId(linkedMemory.id)
    XCTAssertEqual(linkedRecord?.deleted, true, "SQLite must soft-delete conversation-linked rows")
    let otherRecord = try await MemoryStorage.shared.getMemoryByBackendId(otherMemory.id)
    XCTAssertEqual(otherRecord?.deleted, false, "Unrelated SQLite rows must stay active")
  }

  func testDeallocatedViewModelDoesNotLeakObservers() async {
    // Ensures the `[weak self]` capture in the Combine sinks lets the
    // view model deallocate cleanly — no crash when the notifications
    // fire after the instance is gone.
    do {
      let viewModel = MemoriesViewModel()
      XCTAssertEqual(viewModel.refreshInvocations, 0)
    }
    // viewModel is out of scope and should be deallocated.
    NotificationCenter.default.post(
      name: NSApplication.didBecomeActiveNotification, object: nil
    )
    NotificationCenter.default.post(name: .refreshAllData, object: nil)
    await Task.yield()
    try? await Task.sleep(nanoseconds: 50_000_000)
    // If the weak capture misbehaved we'd crash above; reaching here is the assertion.
  }

  private func makeMemory(id: String, conversationId: String?) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: .shortTerm,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: conversationId,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil
    )
  }
}
