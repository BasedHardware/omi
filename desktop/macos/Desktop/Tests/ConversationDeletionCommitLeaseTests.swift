@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

private final class ConversationDeletionCommitObserver: TransactionObserver, @unchecked Sendable {
  private let release = DispatchSemaphore(value: 0)
  private let lock = NSLock()
  private var entered = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func observes(eventsOfKind eventKind: DatabaseEventKind) -> Bool { true }
  func databaseDidChange(with event: DatabaseEvent) {}
  func databaseDidCommit(_ db: Database) {}
  func databaseDidRollback(_ db: Database) {}

  func databaseWillCommit() throws {
    let pending = lock.withLock {
      entered = true
      let pending = waiters
      waiters = []
      return pending
    }
    for continuation in pending { continuation.resume() }
    release.wait()
  }

  func waitUntilWillCommit() async {
    await withCheckedContinuation { continuation in
      let ready = lock.withLock {
        if entered { return true }
        waiters.append(continuation)
        return false
      }
      if ready { continuation.resume() }
    }
  }

  func allowCommit() { release.signal() }
}

private final class ConversationDeletionOwnerProbe: @unchecked Sendable {
  private let lock = NSLock()
  private var value = "owner-a"
  func owner() -> String { lock.withLock { value } }
  func replace() { lock.withLock { value = "owner-b" } }
}

private actor ConversationDeletionCommitSignal {
  enum Event: Equatable, Sendable { case transitionPending, transitionBegan }
  private var first: Event?
  private var waiter: CheckedContinuation<Event, Never>?

  func record(_ event: Event) {
    guard first == nil else { return }
    first = event
    waiter?.resume(returning: event)
    waiter = nil
  }

  func wait() async -> Event {
    if let first { return first }
    return await withCheckedContinuation { waiter = $0 }
  }
}

private func replaceDeletionTestOwner(
  probe: ConversationDeletionOwnerProbe, scope: ConversationCacheWriteScope?, signal: ConversationDeletionCommitSignal
) async throws {
  try await EffectiveOwnerTransitionFence.shared.performEffectiveOwnerTransition(
    currentOwner: { probe.owner() },
    plannedNextOwner: { _ in "owner-b" },
    quiescePreviousOwner: { _, _ in },
    transition: {
      probe.replace()
      scope?.advance()
      await signal.record(.transitionBegan)
    },
    retargetLocalStorage: { _, _ in },
    ownerDidChange: {})
}

final class ConversationDeletionCommitLeaseTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "conversation-deletion-commit")
    self.fixture = fixture
    let ownerFixture = await MainActor.run { RuntimeOwnerAuthorityTestFixture() }
    await ownerFixture.establish(authOwnerID: fixture.testUserId)
    self.ownerFixture = ownerFixture
  }

  override func tearDown() async throws {
    await ownerFixture?.restore()
    ownerFixture = nil
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testDeletionLeaseCoversPhysicalCommitAndSuppressesSupersededResult() async throws {
    let scope = ConversationCacheWriteScope()
    let generation = scope.capture()
    let pool = await RewindDatabase.shared.getDatabaseQueue()
    let db = try XCTUnwrap(pool)
    let observer = ConversationDeletionCommitObserver()
    db.add(transactionObserver: observer, extent: .nextTransaction)
    defer { observer.allowCommit() }
    let write = Task { () -> Result<Void, Error> in
      do {
        try await TranscriptionStorage.shared.prepareConversationDeletion(
          backendId: "commit-deletion", cacheScope: scope, cacheGeneration: generation)
        return .success(())
      } catch { return .failure(error) }
    }
    await observer.waitUntilWillCommit()

    let probe = ConversationDeletionOwnerProbe()
    let signal = ConversationDeletionCommitSignal()
    let pending = Task {
      await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()
      await signal.record(.transitionPending)
    }
    let transition = Task { try await replaceDeletionTestOwner(probe: probe, scope: scope, signal: signal) }
    let first = await signal.wait()
    XCTAssertEqual(first, .transitionPending, "The owner transition must wait until SQLite physically commits")
    XCTAssertEqual(probe.owner(), "owner-a")
    observer.allowCommit()
    let result = await write.value
    try await transition.value

    // A missing lease lets the transition run immediately. Drain its pending-observer
    // task deterministically in that failure case instead of leaving a hung test.
    if first == .transitionBegan {
      let control = try await EffectiveOwnerTransitionFence.shared.acquireMutationLease(validating: { true })
      let cleanup = Task { try await replaceDeletionTestOwner(probe: probe, scope: nil, signal: signal) }
      await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()
      await EffectiveOwnerTransitionFence.shared.releaseMutationLease(control)
      try await cleanup.value
    }
    await pending.value
    switch result {
    case .failure(let error) where error is CancellationError:
      break
    case .failure(let error):
      XCTFail("Expected cancellation of the superseded result, got \(error)")
    case .success:
      XCTFail("An owner-A commit superseded by an owner transition cannot publish success")
    }
    XCTAssertEqual(probe.owner(), "owner-b")
    let deletions = try await TranscriptionStorage.shared.getPendingConversationDeletionIDs()
    XCTAssertEqual(deletions, ["commit-deletion"], "The already admitted commit remains durable for owner A")
  }

  func testSameOwnerReplacementRevokesEveryDelayedFinalizationWrite() async throws {
    let fixture = try XCTUnwrap(fixture)
    let ownerFixture = try XCTUnwrap(ownerFixture)
    for operation in 0..<5 {
      let identity = "original-session-\(operation)"
      let id = try await TranscriptionStorage.shared.startSession(source: "desktop", clientConversationId: identity)
      try await TranscriptionStorage.shared.finishSession(id: id)
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: fixture.testUserId))
      await ownerFixture.establish(authOwnerID: nil)
      await ownerFixture.establish(authOwnerID: fixture.testUserId)
      do {
        switch operation {
        case 0:
          try await TranscriptionStorage.shared.confirmSessionDeletion(
            id: id, expectedOwner: fixture.testUserId, expectedSessionId: identity, authorizationSnapshot: snapshot)
        case 1:
          _ = try await TranscriptionStorage.shared.markSessionUploading(
            id: id, expectedOwner: fixture.testUserId, expectedSessionId: identity, authorizationSnapshot: snapshot)
        case 2:
          _ = try await TranscriptionStorage.shared.markSessionCompleted(
            id: id, backendId: "late-backend", expectedOwner: fixture.testUserId, expectedSessionId: identity,
            authorizationSnapshot: snapshot)
        case 3:
          try await TranscriptionStorage.shared.markSessionFailed(
            id: id, error: "late failure", expectedOwner: fixture.testUserId, expectedSessionId: identity,
            authorizationSnapshot: snapshot)
        default:
          try await TranscriptionStorage.shared.incrementRetryCount(
            id: id, expectedOwner: fixture.testUserId, expectedSessionId: identity, authorizationSnapshot: snapshot)
        }
        XCTFail("Same-owner session replacement must revoke delayed mutation \(operation)")
      } catch is CancellationError {
        // The UID still matches; the original immutable generation does not.
      }
      let row = try await TranscriptionStorage.shared.getSession(id: id)
      XCTAssertEqual(row?.deleted, false)
      XCTAssertEqual(row?.status, .pendingUpload)
      XCTAssertEqual(row?.retryCount, 0)
      XCTAssertNil(row?.lastError)
      XCTAssertNil(row?.backendId)
    }
  }
}
