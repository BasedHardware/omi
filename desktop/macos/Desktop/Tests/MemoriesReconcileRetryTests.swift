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

  /// One-shot latch a test opens from the main actor while an injected
  /// `@Sendable` sleeper parks on it — the sleeper cannot touch main-actor
  /// test state, so the gate guards its waiters with a lock.
  private final class AsyncGate: @unchecked Sendable {
    private let lock = NSLock()
    private var opened = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
      _ = await withCheckedContinuation { continuation in
        lock.lock()
        if opened {
          lock.unlock()
          continuation.resume()
          return
        }
        waiters.append(continuation)
        lock.unlock()
      }
    }

    func open() {
      lock.lock()
      opened = true
      let toResume = waiters
      waiters = []
      lock.unlock()
      toResume.forEach { $0.resume() }
    }
  }

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

  /// The truncated-reconcile path is a fail-open path, so beside the
  /// structured PostHog event it must leave the standard resilience signal:
  /// `recordFallback`'s `fallback_triggered` snapshots in the diagnostics ring
  /// buffer. Filtered by area so only this feature's events are seen; the
  /// buffer is process-global, so tests compare against a baseline captured
  /// before their first reconcile.
  private func memoriesCacheFallbackSnapshots() throws -> [[String: Any]] {
    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    return snapshots.filter {
      ($0["event"] as? String) == "fallback_triggered" && ($0["area"] as? String) == "memories-cache"
    }
  }

  private func assertMemoriesCacheFallback(
    _ snapshot: [String: Any],
    to: String,
    outcome: String,
    attempt: Int,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered", file: file, line: line)
    XCTAssertEqual(snapshot["area"] as? String, "memories-cache", file: file, line: line)
    XCTAssertEqual(snapshot["from"] as? String, "server-page", file: file, line: line)
    XCTAssertEqual(snapshot["to"] as? String, to, file: file, line: line)
    XCTAssertEqual(snapshot["reason"] as? String, "list_truncated", file: file, line: line)
    XCTAssertEqual(snapshot["outcome"] as? String, outcome, file: file, line: line)
    XCTAssertEqual(snapshot["attempt"] as? Int, attempt, file: file, line: line)
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
    let fallbackBaseline = try memoriesCacheFallbackSnapshots().count

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

    // The truncated first pull degraded the reconcile onto its in-launch
    // retry, and the standard resilience telemetry must show that fail-open
    // step beside the structured event.
    let fallbacks = Array(try memoriesCacheFallbackSnapshots().dropFirst(fallbackBaseline))
    XCTAssertEqual(fallbacks.count, 1)
    assertMemoriesCacheFallback(
      fallbacks[0], to: "in-launch-retry", outcome: "degraded", attempt: 2)
  }

  /// Truncated on every attempt (initial pull + 3 retries at 30/60/120s): no
  /// prune, and the user is latched as attempted so only the next launch
  /// retries — and the terminal telemetry
  /// reports truncated_exhausted with the full attempt count.
  func testTruncatedOnEveryAttemptExhaustsWithoutPruningAndHoldsUntilNextLaunch() async throws {
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
    let fallbackBaseline = try memoriesCacheFallbackSnapshots().count

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

    // Exhausted means "next launch": a later reload in this process (filter
    // change, tag edit) must not start another full retry budget.
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      fetches += 1
      return page([])
    }
    await viewModel.reconcileCacheIfNeeded()
    let reloaded = MemoriesViewModel(reconcileRetrySleeper: { _ in })
    reloaded.reconcilePageFetch = viewModel.reconcilePageFetch
    await reloaded.reconcileCacheIfNeeded()
    XCTAssertEqual(fetches, 4, "an exhausted run latches its user for the rest of the launch")
    XCTAssertEqual(events.count, 1, "no second run starts, so no second terminal event")
    XCTAssertFalse(viewModel.reconcileRetry.hasPendingRetry)
    let stillPresent = try await MemoryStorage.shared.getMemoryByBackendId("exhausted-unseen")
    XCTAssertEqual(stillPresent?.deleted, false, "the exhausted latch never prunes")

    // Each truncated attempt that scheduled a retry degraded the reconcile
    // (attempts 1–3); the fourth exhausted it to next launch.
    let fallbacks = Array(try memoriesCacheFallbackSnapshots().dropFirst(fallbackBaseline))
    XCTAssertEqual(fallbacks.count, 4)
    assertMemoriesCacheFallback(
      fallbacks[0], to: "in-launch-retry", outcome: "degraded", attempt: 2)
    assertMemoriesCacheFallback(
      fallbacks[1], to: "in-launch-retry", outcome: "degraded", attempt: 3)
    assertMemoriesCacheFallback(
      fallbacks[2], to: "in-launch-retry", outcome: "degraded", attempt: 4)
    assertMemoriesCacheFallback(
      fallbacks[3], to: "next-launch", outcome: "exhausted", attempt: 4)
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
    let fallbackBaseline = try memoriesCacheFallbackSnapshots().count

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

    // A complete pull never degraded anything: no fallback telemetry.
    let fallbacksAfterComplete = try memoriesCacheFallbackSnapshots()
    XCTAssertEqual(
      fallbacksAfterComplete.count - fallbackBaseline, 0,
      "fallback telemetry belongs to the truncated path only")
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
    let fallbackBaseline = try memoriesCacheFallbackSnapshots().count

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

    // The aborted run scheduled one retry before the switch (degraded), and
    // the owner abort itself is not a further fallback step.
    let fallbacks = Array(try memoriesCacheFallbackSnapshots().dropFirst(fallbackBaseline))
    XCTAssertEqual(fallbacks.count, 1)
    assertMemoriesCacheFallback(
      fallbacks[0], to: "in-launch-retry", outcome: "degraded", attempt: 2)
  }

  /// The owner-switch reset (`resetSessionState` → `endRunReportingOwnerChange`)
  /// must carry the dying run's `aborted_owner_changed` terminal signal — with
  /// its pre-reset attempt count — before the reset invalidates the token: the
  /// reset used to drop an active run silently, so a real account switch never
  /// showed up on the reconcile telemetry this run outcome was created to
  /// surface. A reset with no active run reports nothing.
  func testOwnerSwitchResetReportsAbortedOwnerChangedForTheDyingRun() async throws {
    let present = makeMemory(id: "reset-report-row", tier: .longTerm)
    try await MemoryStorage.shared.syncServerMemories([present])

    // Park one run mid-backoff: the first pull truncates and schedules a
    // retry whose sleeper holds the run in the pending-retry state.
    let sleepGate = AsyncGate()
    let enteredBackoff = expectation(description: "retry backoff entered")
    let viewModel = MemoriesViewModel(reconcileRetrySleeper: { _ in
      enteredBackoff.fulfill()
      await sleepGate.wait()
    })
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      page([present], truncated: true)
    }
    var events: [[String: Any]] = []
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
    }

    await viewModel.reconcileCacheIfNeeded()
    await fulfillment(of: [enteredBackoff], timeout: 5)
    XCTAssertTrue(viewModel.reconcileRetry.hasPendingRetry)
    XCTAssertEqual(viewModel.reconcileRetry.attempt, 1)
    XCTAssertEqual(events.count, 0, "a pending backoff has not reached a terminal outcome")

    // The owner switch: the dying run reports before the reset drops it.
    let reported = expectation(description: "dying run reported aborted_owner_changed")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      reported.fulfill()
    }
    viewModel.endRunReportingOwnerChange()
    await fulfillment(of: [reported], timeout: 5)

    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0]["outcome"] as? String, "aborted_owner_changed")
    XCTAssertEqual(events[0]["attempts"] as? Int, 1)

    // The reset completed: the new owner's run starts clean.
    XCTAssertNil(viewModel.reconcileRetry.runKey)
    XCTAssertEqual(viewModel.reconcileRetry.attempt, 0)
    XCTAssertFalse(viewModel.reconcileRetry.hasPendingRetry)

    // A reset with no active run reports nothing.
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
    }
    viewModel.endRunReportingOwnerChange()
    XCTAssertEqual(events.count, 1, "no active run — no report")

    sleepGate.open()
  }

  /// The race the run token fences: owner A's retry pull is still awaiting
  /// when an account switch resets the scheduler (the owner-change path's
  /// `end()`) and owner B is admitted. B's run truncates and schedules its own
  /// pending retry; A's pull then resumes and reports the owner-fence abort
  /// for its superseded run. A's run is reported `aborted_owner_changed` at
  /// the reset itself (the owner-switch reset carries the dying run's terminal
  /// signal); the late owner-fence report from A's suspended pull is then
  /// dropped by the token fence. B's pending retry is not cancelled, B's
  /// attempt counter is not reset, and B's run still exercises its full retry
  /// budget instead of being treated as exhausted.
  func testSupersededRunLateAbortDoesNotCancelLiveRunRetryOrCounter() async throws {
    guard let ownerA = testUserId else {
      XCTFail("setUp did not produce a signed-in user")
      return
    }
    let ownerB = "memories-reconcile-race-owner-b-\(UUID().uuidString)"

    // Holds A's retry pull mid-fetch until the test resumes it, reproducing
    // "owner A's page fetch is still awaiting" across the switch.
    var aFetchGate: CheckedContinuation<APIClient.MemoryListPage, Never>?
    // Holds B's first backoff open until the mid-race assertions are done, so
    // B's pending retry is still pending when A's late abort lands.
    let bSleepGate = AsyncGate()
    let aMemory = makeMemory(id: "race-a-row", tier: .longTerm)
    let bMemory = makeMemory(id: "race-b-row", tier: .longTerm)

    let viewModel = MemoriesViewModel(reconcileRetrySleeper: { _ in
      // A's backoff passes — A's retry must fire to reach the suspended pull —
      // while B's backoff parks on the gate.
      let user = UserDefaults.standard.string(forKey: .authUserId)
      if user == ownerB { await bSleepGate.wait() }
    })
    var aFetches = 0
    var bFetches = 0
    let aRetryPullEntered = expectation(description: "owner A's retry pull is mid-fetch")
    viewModel.reconcilePageFetch = { [self] _, _, _ in
      let user = UserDefaults.standard.string(forKey: .authUserId) ?? "unknown"
      if user == ownerB {
        bFetches += 1
        return page([bMemory], truncated: true)
      }
      aFetches += 1
      if aFetches == 1 { return page([aMemory], truncated: true) }
      aRetryPullEntered.fulfill()
      _ = await withCheckedContinuation { continuation in aFetchGate = continuation }
      return page([aMemory])
    }
    var events: [[String: Any]] = []
    let aAborted = expectation(description: "A's dying run reported aborted_owner_changed")
    let bExhausted = expectation(description: "B's run exhausted its retries")
    MemoryCacheReconcileTelemetry.captureForTests = { _, properties in
      events.append(properties)
      if properties["outcome"] as? String == "aborted_owner_changed" {
        aAborted.fulfill()
      } else if properties["outcome"] as? String == "truncated_exhausted" {
        bExhausted.fulfill()
      }
    }
    let fallbackBaseline = try memoriesCacheFallbackSnapshots().count

    // A's first pull truncates and schedules its 30s retry.
    await viewModel.reconcileCacheIfNeeded()
    XCTAssertEqual(viewModel.reconcileRetry.runKey, ownerA)
    XCTAssertEqual(viewModel.reconcileRetry.attempt, 1)
    XCTAssertTrue(viewModel.reconcileRetry.hasPendingRetry)

    // A's retry fires and suspends mid-pull — the fetch that will still be
    // awaiting when the account switches.
    await fulfillment(of: [aRetryPullEntered], timeout: 5)
    XCTAssertEqual(viewModel.reconcileRetry.attempt, 2)
    XCTAssertFalse(viewModel.reconcileRetry.hasPendingRetry)

    // The account switch: the owner-change path reports A's dying run
    // (attempt 2, mid-pull) as aborted_owner_changed, then resets the
    // scheduler; B signs in, and B's own reconcile is admitted, truncates,
    // and schedules its pending retry (parked on the gate above).
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: ownerB)
    RewindStorageTestIsolation.signInForTests(userId: ownerB)
    viewModel.resetSessionState()
    await fulfillment(of: [aAborted], timeout: 5)
    XCTAssertEqual(events.count, 1)
    XCTAssertEqual(events[0]["outcome"] as? String, "aborted_owner_changed")
    XCTAssertEqual(events[0]["attempts"] as? Int, 2)

    await viewModel.reconcileCacheIfNeeded()
    XCTAssertEqual(viewModel.reconcileRetry.runKey, ownerB)
    XCTAssertEqual(viewModel.reconcileRetry.attempt, 1)
    XCTAssertTrue(viewModel.reconcileRetry.hasPendingRetry, "B's run owns the next retry slot")

    // A's suspended pull resumes under owner B: its mid-pull owner fence trips
    // and reports the abort for A's superseded run. Let the late report land.
    aFetchGate?.resume(returning: page([aMemory]))
    for _ in 0..<20 { await Task.yield() }

    XCTAssertTrue(
      viewModel.reconcileRetry.hasPendingRetry,
      "a superseded run's late abort must not cancel the live run's pending retry")
    XCTAssertEqual(
      viewModel.reconcileRetry.attempt, 1,
      "a superseded run's late abort must not reset the live run's attempt counter")
    XCTAssertEqual(viewModel.reconcileRetry.runKey, ownerB)
    XCTAssertEqual(
      events.count, 1,
      "A's abort was already reported at the reset; the superseded run's late report must be dropped")

    // Released, B's run spends its full retry budget and exhausts unlatched.
    bSleepGate.open()
    await fulfillment(of: [bExhausted], timeout: 5)

    XCTAssertEqual(aFetches, 2, "A's truncated pull plus its suspended retry pull")
    XCTAssertEqual(bFetches, 4, "B's initial pull plus three bounded retries")
    XCTAssertEqual(events.count, 2)
    XCTAssertEqual(events[1]["outcome"] as? String, "truncated_exhausted")
    XCTAssertEqual(events[1]["attempts"] as? Int, 4)

    let fallbacks = Array(try memoriesCacheFallbackSnapshots().dropFirst(fallbackBaseline))
    XCTAssertEqual(fallbacks.count, 5, "A degraded once; B degraded three times then exhausted")
    assertMemoriesCacheFallback(
      fallbacks[0], to: "in-launch-retry", outcome: "degraded", attempt: 2)
    assertMemoriesCacheFallback(
      fallbacks[1], to: "in-launch-retry", outcome: "degraded", attempt: 2)
    assertMemoriesCacheFallback(
      fallbacks[2], to: "in-launch-retry", outcome: "degraded", attempt: 3)
    assertMemoriesCacheFallback(
      fallbacks[3], to: "in-launch-retry", outcome: "degraded", attempt: 4)
    assertMemoriesCacheFallback(
      fallbacks[4], to: "next-launch", outcome: "exhausted", attempt: 4)
  }
}
