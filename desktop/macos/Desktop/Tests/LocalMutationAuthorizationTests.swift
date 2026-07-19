import GRDB
import XCTest

@testable import Omi_Computer

private final class MutationAuthorizationGate: @unchecked Sendable {
  private let lock = NSLock()
  private var remainingAllowedChecks: Int

  init(allowedChecks: Int = 3) {
    remainingAllowedChecks = allowedChecks
  }

  func authorization() -> LocalMutationAuthorization {
    LocalMutationAuthorization { [self] in
      lock.lock()
      defer { lock.unlock() }
      guard remainingAllowedChecks > 0 else { return false }
      remainingAllowedChecks -= 1
      return true
    }
  }
}

private final class LocalMutationTransactionObserver: TransactionObserver, @unchecked Sendable {
  private let lock = NSLock()
  private var observedDML = false
  private var rolledBack = false

  func observes(eventsOfKind eventKind: DatabaseEventKind) -> Bool { true }
  func databaseDidChange(with event: DatabaseEvent) {
    lock.withLock { observedDML = true }
  }
  func databaseWillCommit() throws {}
  func databaseDidCommit(_ db: Database) {}
  func databaseDidRollback(_ db: Database) {
    lock.withLock { rolledBack = true }
  }

  func snapshot() -> (observedDML: Bool, rolledBack: Bool) {
    lock.withLock { (observedDML, rolledBack) }
  }
}

private actor OwnerTransitionTestGate {
  private var isOpen = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    guard !isOpen else { return }
    await withCheckedContinuation { continuation in
      waiters.append(continuation)
    }
  }

  func open() {
    guard !isOpen else { return }
    isOpen = true
    let pending = waiters
    waiters.removeAll()
    pending.forEach { $0.resume() }
  }
}

private final class EffectiveOwnerTransitionProbe: @unchecked Sendable {
  private let lock = NSLock()
  private var ownerID: String? = "owner-a"
  private var events: [String] = []
  private var mutationValidatorCalls = 0

  func owner() -> String? { lock.withLock { ownerID } }
  func setOwner(_ ownerID: String?) { lock.withLock { self.ownerID = ownerID } }
  func record(_ event: String) { lock.withLock { events.append(event) } }
  func validateOwnerB() -> Bool {
    lock.withLock {
      mutationValidatorCalls += 1
      events.append("mutation_validator")
      return ownerID == "owner-b"
    }
  }
  func snapshot() -> (ownerID: String?, events: [String], validatorCalls: Int) {
    lock.withLock { (ownerID, events, mutationValidatorCalls) }
  }
}

final class LocalMutationAuthorizationTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?

  override func setUp() async throws {
    try await super.setUp()
    fixture = try await RewindStorageTestIsolation.setUp(
      userIdPrefix: "owner-bound-local-mutation")
    await KnowledgeGraphStorage.shared.invalidateCache()
  }

  override func tearDown() async throws {
    await KnowledgeGraphStorage.shared.invalidateCache()
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
    try await super.tearDown()
  }

  func testPostDMLRevocationRollsBackEveryTaskMutationBoundary() async throws {
    let original = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(
        backendId: "task-owner-a",
        description: "must remain unchanged",
        relevanceScore: 2),
      // Fixture setup precedes the revocation gates exercised below.
      authorization: .unrestricted)
    let localID = try XCTUnwrap(original.id)

    let markSyncedObserver = LocalMutationTransactionObserver()
    let maybePool = await RewindDatabase.shared.getDatabaseQueue()
    let pool = try XCTUnwrap(maybePool)
    pool.add(transactionObserver: markSyncedObserver, extent: .nextTransaction)

    await assertRevoked {
      try await ActionItemStorage.shared.markSynced(
        id: localID,
        backendId: "replacement-id",
        authorization: MutationAuthorizationGate().authorization())
    }
    var storedValue = try await ActionItemStorage.shared.getActionItem(id: localID)
    var stored = try XCTUnwrap(storedValue)
    XCTAssertEqual(stored.backendId, "task-owner-a")
    XCTAssertFalse(stored.backendSynced)
    let markSyncedTransaction = markSyncedObserver.snapshot()
    XCTAssertTrue(markSyncedTransaction.observedDML)
    XCTAssertTrue(markSyncedTransaction.rolledBack)

    await assertRevoked {
      try await ActionItemStorage.shared.updateCompletionStatus(
        backendId: "task-owner-a",
        completed: true,
        authorization: MutationAuthorizationGate().authorization())
    }
    storedValue = try await ActionItemStorage.shared.getActionItem(id: localID)
    stored = try XCTUnwrap(storedValue)
    XCTAssertFalse(stored.completed)

    await assertRevoked {
      try await ActionItemStorage.shared.compactScoresAfterRemoval(
        removedScore: 1,
        authorization: MutationAuthorizationGate().authorization())
    }
    storedValue = try await ActionItemStorage.shared.getActionItem(id: localID)
    stored = try XCTUnwrap(storedValue)
    XCTAssertEqual(stored.relevanceScore, 2)

    await assertRevoked {
      try await ActionItemStorage.shared.syncTaskActionItems(
        [
          TaskActionItem(
            id: "incoming-owner-a",
            description: "must not insert",
            completed: false,
            createdAt: Date())
        ],
        authorization: MutationAuthorizationGate().authorization())
    }
    let incoming = try await ActionItemStorage.shared.getLocalActionItem(
      byBackendId: "incoming-owner-a")
    XCTAssertNil(incoming)

    await assertRevoked {
      try await ActionItemStorage.shared.deleteActionItemByBackendId(
        "task-owner-a",
        authorization: MutationAuthorizationGate().authorization())
    }
    let afterRejectedDelete = try await ActionItemStorage.shared.getActionItem(id: localID)
    XCTAssertNotNil(afterRejectedDelete)
  }

  func testPostDMLRevocationRollsBackKnowledgeGraphUpsert() async throws {
    let node = LocalKGNodeRecord(
      nodeId: "owner-a-node",
      label: "Owner A private node",
      nodeType: "concept",
      aliasesJson: nil,
      sourceFileIds: nil,
      createdAt: Date(),
      updatedAt: Date())

    let observer = LocalMutationTransactionObserver()
    let maybePool = await RewindDatabase.shared.getDatabaseQueue()
    let pool = try XCTUnwrap(maybePool)
    pool.add(transactionObserver: observer, extent: .nextTransaction)

    await assertRevoked {
      try await KnowledgeGraphStorage.shared.mergeGraph(
        nodes: [node],
        edges: [],
        authorization: MutationAuthorizationGate().authorization())
    }

    let graph = await KnowledgeGraphStorage.shared.loadGraph()
    XCTAssertTrue(graph.nodes.isEmpty)
    XCTAssertTrue(graph.edges.isEmpty)
    let transaction = observer.snapshot()
    XCTAssertTrue(transaction.observedDML)
    XCTAssertTrue(transaction.rolledBack)
  }

  func testPostDMLRevocationRollsBackKnowledgeGraphClear() async throws {
    let node = LocalKGNodeRecord(
      nodeId: "owner-a-node",
      label: "Owner A private node",
      nodeType: "concept",
      aliasesJson: nil,
      sourceFileIds: nil,
      createdAt: Date(),
      updatedAt: Date())
    try await KnowledgeGraphStorage.shared.mergeGraph(
      nodes: [node],
      edges: [],
      authorization: .unrestricted)

    let observer = LocalMutationTransactionObserver()
    let maybePool = await RewindDatabase.shared.getDatabaseQueue()
    let pool = try XCTUnwrap(maybePool)
    pool.add(transactionObserver: observer, extent: .nextTransaction)

    await assertRevoked {
      try await KnowledgeGraphStorage.shared.clearAll(
        authorization: MutationAuthorizationGate().authorization())
    }

    let graph = await KnowledgeGraphStorage.shared.loadGraph()
    XCTAssertEqual(graph.nodes.map(\.id), ["owner-a-node"])
    let transaction = observer.snapshot()
    XCTAssertTrue(transaction.observedDML)
    XCTAssertTrue(transaction.rolledBack)
  }

  func testOwnerQuiescenceCompletesBeforeOwnerMutationAndOwnerBAdmission() async throws {
    let fence = EffectiveOwnerTransitionFence()
    let probe = EffectiveOwnerTransitionProbe()
    let quiescenceEntered = OwnerTransitionTestGate()
    let allowQuiescenceToFinish = OwnerTransitionTestGate()

    let transition = Task {
      await fence.performEffectiveOwnerTransition(
        currentOwner: { probe.owner() },
        plannedNextOwner: { _ in "owner-b" },
        quiescePreviousOwner: { previousOwner, plannedOwner in
          XCTAssertEqual(previousOwner, "owner-a")
          XCTAssertEqual(plannedOwner, "owner-b")
          probe.record("quiesce_started")
          await quiescenceEntered.open()
          await allowQuiescenceToFinish.wait()
          probe.record("quiesce_finished")
        },
        transition: {
          probe.record("owner_mutation")
          probe.setOwner("owner-b")
        },
        retargetLocalStorage: { _, _ in probe.record("retarget") },
        ownerDidChange: { probe.record("owner_changed") })
    }

    await quiescenceEntered.wait()
    let ownerBMutation = Task {
      let lease = try await fence.acquireMutationLease(validating: {
        probe.validateOwnerB()
      })
      await fence.releaseMutationLease(lease)
    }
    await fence.waitUntilMutationIsPending()

    var snapshot = probe.snapshot()
    XCTAssertEqual(snapshot.ownerID, "owner-a")
    XCTAssertEqual(snapshot.validatorCalls, 0)
    XCTAssertEqual(snapshot.events, ["quiesce_started"])

    await allowQuiescenceToFinish.open()
    await transition.value
    try await ownerBMutation.value

    snapshot = probe.snapshot()
    XCTAssertEqual(snapshot.ownerID, "owner-b")
    XCTAssertEqual(snapshot.validatorCalls, 1)
    XCTAssertEqual(
      snapshot.events,
      [
        "quiesce_started", "quiesce_finished", "owner_mutation", "retarget",
        "owner_changed", "mutation_validator",
      ])
  }

  private func assertRevoked(
    _ operation: () async throws -> Void,
    file: StaticString = #filePath,
    line: UInt = #line
  ) async {
    do {
      try await operation()
      XCTFail("owner-revoked mutation unexpectedly committed", file: file, line: line)
    } catch {
      XCTAssertEqual(
        error as? LocalMutationAuthorizationError,
        .revoked,
        file: file,
        line: line)
    }
  }
}
