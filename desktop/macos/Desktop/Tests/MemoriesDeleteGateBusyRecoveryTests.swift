import XCTest

@testable import Omi_Computer

/// Thread-safe mutable cell for closures that XCTest injects across actor
/// boundaries (same lock pattern as the URLProtocol stubs in these suites).
private final class Locked<Value>: @unchecked Sendable {
  private let lock = NSLock()
  private var _value: Value

  init(_ value: Value) { self._value = value }

  var value: Value {
    get {
      lock.lock()
      defer { lock.unlock() }
      return _value
    }
    set {
      lock.lock()
      _value = newValue
      lock.unlock()
    }
  }
}

/// A gate-busy delete must stop resurrecting the row.
///
/// The backend's account-wide destructive-operation gate answers a concurrent
/// delete with 409 `account_gate_busy` plus `Retry-After`. The old failure
/// path restored the row on any error, so every delete during a
/// retention-cleanup window visibly resurrected seconds after confirmation.
/// The row must stay soft-deleted, the user must be told the deletion is
/// delayed, exactly one deferred retry may be scheduled, and only
/// non-retryable failures keep restoring.
@MainActor
final class MemoriesDeleteGateBusyRecoveryTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-delete-gate-busy")
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    }
    if let userDir {
      await RewindStorageTestIsolation.tearDown(userDir: userDir)
    }
  }

  private func makeServerMemory(id: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: .longTerm,
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

  /// Delete-then-confirm without waiting out the undo countdown.
  private func deleteImmediately(_ memory: ServerMemory, on viewModel: MemoriesViewModel) async {
    await viewModel.deleteMemory(memory)
    let finalize = viewModel.confirmDelete()
    await finalize.value
  }

  func testClampBoundedRetryDelays() {
    XCTAssertEqual(MemoryDeleteRecovery.clamp(nil), MemoryDeleteRecovery.defaultRetryDelay)
    XCTAssertEqual(MemoryDeleteRecovery.clamp(0), MemoryDeleteRecovery.defaultRetryDelay)
    XCTAssertEqual(MemoryDeleteRecovery.clamp(-3), MemoryDeleteRecovery.defaultRetryDelay)
    XCTAssertEqual(MemoryDeleteRecovery.clamp(1), MemoryDeleteRecovery.minRetryDelay)
    XCTAssertEqual(MemoryDeleteRecovery.clamp(60), 60)
    XCTAssertEqual(MemoryDeleteRecovery.clamp(60_000), MemoryDeleteRecovery.maxRetryDelay)
  }

  func testOnlyGateBusyFailuresAreRetryable() {
    XCTAssertNotNil(MemoryDeleteRecovery.retryDelay(for: APIError.memoryDeleteGateBusy(retryAfterSeconds: 2)))
    XCTAssertNotNil(
      MemoryDeleteRecovery.retryDelay(
        for: APIError.httpError(statusCode: 409, detail: MemoryDeleteRecovery.gateBusyDetail)))
    XCTAssertNil(
      MemoryDeleteRecovery.retryDelay(for: APIError.httpError(statusCode: 409, detail: "other conflict")),
      "a non-gate 409 keeps the restore behavior")
    XCTAssertNil(MemoryDeleteRecovery.retryDelay(for: APIError.httpError(statusCode: 500)))
    XCTAssertNil(MemoryDeleteRecovery.retryDelay(for: APIError.unauthorized))
  }

  /// First delete hits the busy gate: the row stays deleted, the message says
  /// the deletion is delayed, one retry is scheduled after the clamped delay,
  /// and the retry that succeeds completes the delete.
  func testGateBusyKeepsRowDeletedAndRetriesOnceUntilSuccess() async throws {
    let memory = makeServerMemory(id: "gate-busy-then-success")
    try await MemoryStorage.shared.syncServerMemories([memory])

    let gateBusy = expectation(description: "initial delete answered gate-busy")
    let retrySucceeded = expectation(description: "deferred retry completed the delete")
    let serverCalls = Locked(0)
    let delays = Locked<[TimeInterval]>([])
    // The sleeper parks the retry on a continuation the test releases, so the
    // pre-retry assertions observe the scheduled state deterministically.
    let retryGate = Locked<CheckedContinuation<Void, Never>?>(nil)
    let viewModel = MemoriesViewModel(
      deleteMemoryRequest: { _ in
        let call = serverCalls.value + 1
        serverCalls.value = call
        if call == 1 {
          gateBusy.fulfill()
          throw APIError.memoryDeleteGateBusy(retryAfterSeconds: 1)
        }
        retrySucceeded.fulfill()
      },
      deferredRetrySleeper: { delay in
        delays.value.append(delay)
        await withCheckedContinuation { continuation in
          retryGate.value = continuation
        }
      }
    )

    await deleteImmediately(memory, on: viewModel)

    let afterFailure = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    XCTAssertEqual(afterFailure?.deleted, true, "a gate-busy delete must not resurrect the row")
    XCTAssertEqual(
      viewModel.errorMessage,
      "Deletion is delayed while Omi finishes another account task. It will retry automatically.")
    while delays.value.isEmpty { await Task.yield() }
    XCTAssertEqual(delays.value, [MemoryDeleteRecovery.minRetryDelay], "Retry-After 1s clamps up to 5s")
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingDelay, MemoryDeleteRecovery.minRetryDelay)

    retryGate.value?.resume()
    retryGate.value = nil
    await fulfillment(of: [gateBusy, retrySucceeded], timeout: 5)

    XCTAssertEqual(serverCalls.value, 2, "one attempt plus one deferred retry")
    XCTAssertEqual(viewModel.deferredDeleteRetry.retryCount, 1, "exactly one deferred retry ran")
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingDelay, nil, "no further retry is armed")
    let afterRetry = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    XCTAssertEqual(afterRetry?.deleted, true, "the successful retry leaves the row deleted")
  }

  /// A gate that stays busy: exactly one retry runs, and it does not arm
  /// another — but the row still stays deleted instead of resurrecting.
  func testPersistentGateBusyRetriesOnlyOnceAndKeepsRowDeleted() async throws {
    let memory = makeServerMemory(id: "gate-stays-busy")
    try await MemoryStorage.shared.syncServerMemories([memory])

    let firstGateBusy = expectation(description: "initial delete answered gate-busy")
    let retryGateBusy = expectation(description: "deferred retry answered gate-busy again")
    let serverCalls = Locked(0)
    let viewModel = MemoriesViewModel(
      deleteMemoryRequest: { _ in
        let call = serverCalls.value + 1
        serverCalls.value = call
        if call == 1 { firstGateBusy.fulfill() } else { retryGateBusy.fulfill() }
        throw APIError.memoryDeleteGateBusy(retryAfterSeconds: nil)
      },
      deferredRetrySleeper: { _ in }
    )

    await deleteImmediately(memory, on: viewModel)

    await fulfillment(of: [firstGateBusy, retryGateBusy], timeout: 5)
    await settleAsyncWork()

    XCTAssertEqual(serverCalls.value, 2, "one attempt plus one deferred retry, never a loop")
    XCTAssertEqual(viewModel.deferredDeleteRetry.retryCount, 1)
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingDelay, nil)
    let record = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    XCTAssertEqual(record?.deleted, true, "a still-busy gate keeps the row soft-deleted")
  }

  /// Non-retryable failures keep the existing behavior: the row is restored.
  func testNonRetryableFailureStillRestoresTheRow() async throws {
    let memory = makeServerMemory(id: "server-error")
    try await MemoryStorage.shared.syncServerMemories([memory])

    let failed = expectation(description: "delete failed with 500")
    let viewModel = MemoriesViewModel(
      deleteMemoryRequest: { _ in
        failed.fulfill()
        throw APIError.httpError(statusCode: 500)
      },
      deferredRetrySleeper: { _ in XCTFail("a 500 must not schedule a deferred retry") }
    )

    await deleteImmediately(memory, on: viewModel)

    await fulfillment(of: [failed], timeout: 5)
    await settleAsyncWork()

    let record = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    XCTAssertEqual(record?.deleted, false, "a non-retryable failure restores the row as before")
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingDelay, nil)
    XCTAssertEqual(viewModel.deferredDeleteRetry.retryCount, 0)
  }

  /// Deleting a second memory during a first memory's retry window must not
  /// cancel the first memory's retry: the scheduler held a single slot, so the
  /// second schedule silently dropped the first row's only server delete and
  /// the next refresh resurrected the row the user had confirmed.
  func testOverlappingGateBusyDeletesKeepBothRetries() async throws {
    let first = makeServerMemory(id: "gate-busy-first")
    let second = makeServerMemory(id: "gate-busy-second")
    try await MemoryStorage.shared.syncServerMemories([first, second])

    let attemptsPerID = Locked<[String: Int]>([:])
    let parked = Locked<[CheckedContinuation<Void, Never>]>([])
    let viewModel = MemoriesViewModel(
      deleteMemoryRequest: { id in
        // First attempt per id is gate-busy; the deferred retry succeeds.
        let count = (attemptsPerID.value[id] ?? 0) + 1
        attemptsPerID.value[id] = count
        if count == 1 {
          throw APIError.memoryDeleteGateBusy(retryAfterSeconds: nil)
        }
      },
      deferredRetrySleeper: { _ in
        await withCheckedContinuation { continuation in
          parked.value.append(continuation)
        }
      }
    )

    await deleteImmediately(first, on: viewModel)
    await deleteImmediately(second, on: viewModel)
    for _ in 0..<1_000 where parked.value.count < 2 { await Task.yield() }
    XCTAssertEqual(parked.value.count, 2, "both deletes must arm their own retry")
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingCount, 2)
    XCTAssertTrue(viewModel.deferredDeleteRetry.hasPendingRetry(for: first.id))
    XCTAssertTrue(viewModel.deferredDeleteRetry.hasPendingRetry(for: second.id))

    for continuation in parked.value { continuation.resume() }
    parked.value = []
    let bothRetried = { attemptsPerID.value[first.id] == 2 && attemptsPerID.value[second.id] == 2 }
    for _ in 0..<1_000 where !bothRetried() { await Task.yield() }
    await settleAsyncWork()

    XCTAssertEqual(
      [attemptsPerID.value[first.id], attemptsPerID.value[second.id]], [2, 2],
      "each row got its initial attempt plus its own deferred retry")
    XCTAssertEqual(viewModel.deferredDeleteRetry.retryCount, 2)
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingCount, 0)
    let firstRecord = try await MemoryStorage.shared.getMemoryByBackendId(first.id)
    XCTAssertEqual(firstRecord?.deleted, true, "the first row's retry still completed")
    let secondRecord = try await MemoryStorage.shared.getMemoryByBackendId(second.id)
    XCTAssertEqual(secondRecord?.deleted, true)
  }

  /// Undo during a pending retry: the retry is cancelled before the row is
  /// restored, so the armed 409 retry can no longer delete the server row the
  /// user just put back.
  func testUndoDuringPendingRetryCancelsItAndKeepsTheRow() async throws {
    let memory = makeServerMemory(id: "undo-with-pending-retry")
    try await MemoryStorage.shared.syncServerMemories([memory])

    let attempts = Locked(0)
    let parked = Locked<CheckedContinuation<Void, Never>?>(nil)
    let viewModel = MemoriesViewModel(
      deleteMemoryRequest: { _ in
        attempts.value += 1
        throw APIError.memoryDeleteGateBusy(retryAfterSeconds: nil)
      },
      deferredRetrySleeper: { _ in
        await withCheckedContinuation { continuation in
          parked.value = continuation
        }
      }
    )

    await deleteImmediately(memory, on: viewModel)
    for _ in 0..<1_000 where parked.value == nil { await Task.yield() }
    XCTAssertNotNil(parked.value, "the gate-busy delete armed its deferred retry")
    XCTAssertTrue(viewModel.deferredDeleteRetry.hasPendingRetry(for: memory.id))

    // Re-open the undo window the way `deleteMemory(_:)` holds it between
    // finalizing a previous pending delete (which arms the retry) and
    // installing the new pending row: there, `pendingDeleteMemory` still
    // names the row whose retry was just armed.
    viewModel.pendingDeleteMemory = memory
    viewModel.undoDelete()

    XCTAssertFalse(
      viewModel.deferredDeleteRetry.hasPendingRetry(for: memory.id),
      "undo must clear the row's pending retry from the map")
    parked.value?.resume()
    parked.value = nil
    await settleAsyncWork()

    XCTAssertEqual(attempts.value, 1, "no server delete after the undo")
    XCTAssertEqual(viewModel.deferredDeleteRetry.retryCount, 0)
    let record = try await MemoryStorage.shared.getMemoryByBackendId(memory.id)
    XCTAssertEqual(record?.deleted, false, "the row stays restored after undo")
  }

  /// Session reset (sign-out / owner switch) cancels every pending retry, not
  /// just the most recent one.
  func testResetSessionStateCancelsAllPendingRetries() async throws {
    let first = makeServerMemory(id: "reset-cancels-first")
    let second = makeServerMemory(id: "reset-cancels-second")
    try await MemoryStorage.shared.syncServerMemories([first, second])

    let attempts = Locked(0)
    let parked = Locked<[CheckedContinuation<Void, Never>]>([])
    let viewModel = MemoriesViewModel(
      deleteMemoryRequest: { _ in
        attempts.value += 1
        throw APIError.memoryDeleteGateBusy(retryAfterSeconds: nil)
      },
      deferredRetrySleeper: { _ in
        await withCheckedContinuation { continuation in
          parked.value.append(continuation)
        }
      }
    )

    await deleteImmediately(first, on: viewModel)
    await deleteImmediately(second, on: viewModel)
    for _ in 0..<1_000 where parked.value.count < 2 { await Task.yield() }
    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingCount, 2)

    viewModel.resetSessionState()

    XCTAssertEqual(viewModel.deferredDeleteRetry.pendingCount, 0)
    XCTAssertFalse(viewModel.deferredDeleteRetry.hasPendingRetry(for: first.id))
    XCTAssertFalse(viewModel.deferredDeleteRetry.hasPendingRetry(for: second.id))
    for continuation in parked.value { continuation.resume() }
    parked.value = []
    await settleAsyncWork()
    XCTAssertEqual(attempts.value, 2, "no deferred retry fired after the reset")
    XCTAssertEqual(viewModel.deferredDeleteRetry.retryCount, 0)
  }

  /// Pending retries are bounded: beyond the cap the oldest pending retry is
  /// evicted (FIFO), and re-arming an already-pending id replaces its own slot
  /// instead of evicting another row's.
  func testPendingRetriesAreCappedByEvictingTheOldest() async {
    let parked = Locked<[CheckedContinuation<Void, Never>]>([])
    let scheduler = MemoryDeleteRetryScheduler(
      sleeper: { _ in
        await withCheckedContinuation { continuation in
          parked.value.append(continuation)
        }
      }
    )

    for index in 0..<MemoryDeleteRetryScheduler.maxPendingRetries {
      scheduler.schedule(after: 1, memoryID: "memory-\(index)") {}
    }
    scheduler.schedule(after: 1, memoryID: "memory-new") {}

    XCTAssertEqual(scheduler.pendingCount, MemoryDeleteRetryScheduler.maxPendingRetries)
    XCTAssertFalse(
      scheduler.hasPendingRetry(for: "memory-0"), "the oldest pending retry is evicted first")
    XCTAssertTrue(scheduler.hasPendingRetry(for: "memory-1"))
    XCTAssertTrue(scheduler.hasPendingRetry(for: "memory-new"))

    // Re-scheduling a pending id replaces its own slot, not another row's.
    scheduler.schedule(after: 2, memoryID: "memory-1") {}
    XCTAssertTrue(scheduler.hasPendingRetry(for: "memory-2"))
    XCTAssertEqual(scheduler.pendingCount, MemoryDeleteRetryScheduler.maxPendingRetries)
    XCTAssertEqual(
      scheduler.pendingDelay, 2, "the most recently armed retry reports its delay")

    for continuation in parked.value { continuation.resume() }
    parked.value = []
    scheduler.cancelAll()
  }

  /// Lets already-started tasks (the retry scheduler hop) drain without a
  /// wall-clock wait before asserting no further work appeared.
  private func settleAsyncWork() async {
    for _ in 0..<20 { await Task.yield() }
  }
}
