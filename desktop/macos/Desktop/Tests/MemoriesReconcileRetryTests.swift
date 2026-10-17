import XCTest

@testable import Omi_Computer

/// A truncated reconcile pull must not park the orphan prune until the next
/// launch: search reads the local SQLite cache, so a synced row deleted on
/// another device stays findable all session when the reconcile gives up.
/// These tests pin the bounded in-launch retry — re-entering the same guarded
/// path, fencing on owner switches, latching only on a complete pull — and the
/// `Memories Cache Reconcile` outcome telemetry that makes the failure class
/// visible. The sleeper is injected, so the 30s/60s/120s backoff is
/// deterministic here.
@MainActor
final class MemoriesReconcileRetryTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?
  private var testUserId: String?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-reconcile-retry")
    userDir = fixture.userDir
    testUserId = fixture.testUserId
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
    // Align the process-global owner authority with this throwaway user, the
    // way a real signed-in session does, so the reconcile's owner fence
    // (capture → isAuthorizationCurrent) observes a stable owner.
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: fixture.testUserId)
  }

  override func tearDown() async throws {
    MemoryCacheReconcileTelemetry.captureForTests = nil
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: authSnapshot.userId)
    }
    if let userDir {
      await RewindStorageTestIsolation.tearDown(userDir: userDir)
    }
  }

  private func page(
    _ memories: [ServerMemory],
    nextCursor: String? = nil,
    truncated: Bool = false
  ) -> APIClient.MemoryListPage {
    APIClient.MemoryListPage(
      memories: memories,
      nextCursor: nextCursor,
      canonicalLifecycleExposed: false,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: truncated
    )
  }

  private func makeMemory(id: String, tier: MemoryLayer) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: tier,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
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

  /// Truncated first page, complete retry page: the retry must re-run the
  /// reconcile from a fresh cursor, prune the orphan, latch the launch guard,
  /// and report the terminal outcome with the attempt number.
  func testTruncatedThenCompleteRetryPrunesOrphanAndLatches() async throws {
    let kept = makeMemory(id: "retry-kept", tier: .longTerm)
    let deletedElsewhere = makeMemory(id: "retry-orphan", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([kept, deletedElsewhere])

    let viewModel = MemoriesViewModel(reconcileRetrySleeper: { _ in })
    var fetches = 0
    viewModel.reconcilePageFetch = { [self] _, cursor, _ in
      fetches += 1
      if cursor == nil, fetches == 1 {
        return page([kept], truncated: true)
      }
      return page([kept])
    }
    var events: [[String: Any]] = []
    let finished = expectation(description: "reconcile run reached a terminal outcome")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      finished.fulfill()
    }

    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [finished], timeout: 5)

    let gone = try await MemoryStorage.shared.getMemoryByBackendId("retry-orphan")
    XCTAssertEqual(gone?.deleted, true, "the retried reconcile must prune the orphan")
    let keptRecord = try await MemoryStorage.shared.getMemoryByBackendId("retry-kept")
    XCTAssertEqual(keptRecord?.deleted, false)
    XCTAssertEqual(fetches, 2, "one truncated pull plus one complete retry pull")
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0]["outcome"] as? String, "complete")
    XCTAssertEqual(events[0]["attempts"] as? Int, 2)
    XCTAssertEqual(events[0]["truncated"] as? Bool, false)
    XCTAssertEqual(events[0]["pruned"] as? Int, 1)

    // Latched: a third reconcile must not pull again.
    await viewModel.reconcileCacheIfNeeded()
    XCTAssertEqual(fetches, 2, "a successful reconcile latches for the rest of the launch")
  }

  /// Truncated on every attempt (initial pull + 3 retries at 30/60/120s): no
  /// prune, no latch — the next launch retries — and the terminal telemetry
  /// reports truncated_exhausted with the full attempt count.
  func testTruncatedOnEveryAttemptExhaustsUnlatchedWithoutPruning() async throws {
    let present = makeMemory(id: "exhausted-present", tier: .longTerm)
    let unseen = makeMemory(id: "exhausted-unseen", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([present, unseen])

    let viewModel = MemoriesViewModel(reconcileRetrySleeper: { _ in })
    var fetches = 0
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      fetches += 1
      return page([present], truncated: true)
    }
    var events: [[String: Any]] = []
    let exhausted = expectation(description: "reconcile run exhausted its retries")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      exhausted.fulfill()
    }

    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [exhausted], timeout: 5)

    XCTAssertEqual(fetches, 4, "the initial pull plus three bounded retries")
    let record = try await MemoryStorage.shared.getMemoryByBackendId("exhausted-unseen")
    XCTAssertEqual(
      record?.deleted, false,
      "a truncated pull saw only part of the backend, so absence proves nothing")
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0]["outcome"] as? String, "truncated_exhausted")
    XCTAssertEqual(events[0]["attempts"] as? Int, 4)
    XCTAssertEqual(events[0]["truncated"] as? Bool, true)
    XCTAssertEqual(events[0]["pruned"] as? Int, 0)

    // Unlatched: the next reconcile runs again instead of returning early.
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      fetches += 1
      return page([])
    }
    let completed = expectation(description: "follow-up reconcile run completed")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      if events.count == 2 { completed.fulfill() }
    }
    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [completed], timeout: 5)
    XCTAssertEqual(fetches, 5, "an exhausted run must not latch its user")
  }

  /// A complete pull that returned nothing is an authoritative empty account
  /// and must keep pruning every synced orphan — the retry plumbing must not
  /// weaken the existing empty-pull semantics.
  func testCompleteEmptyPullStillPrunesAllSyncedOrphans() async throws {
    let first = makeMemory(id: "empty-pull-1", tier: .longTerm)
    let second = makeMemory(id: "empty-pull-2", tier: .archive)
    try await MemoryStorage.shared.syncServerMemories([first, second])

    let viewModel = MemoriesViewModel(reconcileRetrySleeper: { _ in })
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      page([])
    }
    var events: [[String: Any]] = []
    let finished = expectation(description: "reconcile run reached a terminal outcome")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      finished.fulfill()
    }

    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [finished], timeout: 5)

    let goneFirst = try await MemoryStorage.shared.getMemoryByBackendId("empty-pull-1")
    XCTAssertEqual(goneFirst?.deleted, true)
    let goneSecond = try await MemoryStorage.shared.getMemoryByBackendId("empty-pull-2")
    XCTAssertEqual(goneSecond?.deleted, true)
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0]["outcome"] as? String, "complete")
    XCTAssertEqual(events[0]["pruned"] as? Int, 2)
    XCTAssertEqual(events[0]["attempts"] as? Int, 1)
    XCTAssertEqual(events[0]["truncated"] as? Bool, false)
  }

  /// An owner switch between attempts must abort the run without pruning: the
  /// keep-set belongs to the owner that started the run, and a retry firing
  /// after the switch must not pull or prune for the new owner.
  func testOwnerSwitchBetweenAttemptsAbortsRetryWithoutPruning() async throws {
    let synced = makeMemory(id: "owner-switch-row", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([synced])

    // Flip the owner while the first retry is backing off.
    let viewModel = MemoriesViewModel(reconcileRetrySleeper: { _ in
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: "reconcile-retry-other-owner")
    })
    var fetches = 0
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      fetches += 1
      return page([synced], truncated: true)
    }
    var events: [[String: Any]] = []
    let aborted = expectation(description: "reconcile run aborted after the owner switch")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      aborted.fulfill()
    }

    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [aborted], timeout: 5)

    XCTAssertEqual(fetches, 1, "the retry must not re-pull under a different owner")
    let stillThere = try await MemoryStorage.shared.getMemoryByBackendId("owner-switch-row")
    XCTAssertEqual(
      stillThere?.deleted, false,
      "an owner switch must fence the run's prune, not re-target it")
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0]["outcome"] as? String, "aborted_owner_changed")

    // No latch either: with this user's authority restored, the reconcile must
    // run again from the top instead of returning before its first fetch.
    guard let testUserId else { return }
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: testUserId)
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      fetches += 1
      return page([synced])
    }
    let completed = expectation(description: "clean reconcile run completed")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      if events.count == 2 { completed.fulfill() }
    }
    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [completed], timeout: 5)
    XCTAssertEqual(fetches, 2, "the aborted run must not latch its user")
  }
}
