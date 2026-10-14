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

  /// Lets already-started tasks (the retry scheduler hop) drain without a
  /// wall-clock wait before asserting no further work appeared.
  private func settleAsyncWork() async {
    for _ in 0..<20 { await Task.yield() }
  }
}
