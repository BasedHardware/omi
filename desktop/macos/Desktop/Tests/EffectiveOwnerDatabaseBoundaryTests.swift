import GRDB
import OmiSupport
import XCTest

@testable import Omi_Computer

private final class OwnerDatabaseCommitObserver: TransactionObserver, @unchecked Sendable {
  private let releaseCommit = DispatchSemaphore(value: 0)
  private let lock = NSLock()
  private var reachedWillCommit = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func observes(eventsOfKind eventKind: DatabaseEventKind) -> Bool { true }
  func databaseDidChange(with event: DatabaseEvent) {}

  func databaseWillCommit() throws {
    let pending = lock.withLock { () -> [CheckedContinuation<Void, Never>] in
      reachedWillCommit = true
      let pending = waiters
      waiters.removeAll()
      return pending
    }
    pending.forEach { $0.resume() }
    releaseCommit.wait()
  }

  func databaseDidCommit(_ db: Database) {}
  func databaseDidRollback(_ db: Database) {}

  func waitUntilWillCommit() async {
    if lock.withLock({ reachedWillCommit }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = lock.withLock { () -> Bool in
        guard !reachedWillCommit else { return true }
        waiters.append(continuation)
        return false
      }
      if shouldResume { continuation.resume() }
    }
  }

  func allowCommit() {
    releaseCommit.signal()
  }
}

@MainActor
final class EffectiveOwnerDatabaseBoundaryTests: XCTestCase {
  private var originalAuthOwner: String?
  private var originalOverride: String?
  private var originalBackup: String?
  private var createdOwnerIDs: [String] = []

  override func setUp() async throws {
    originalAuthOwner = UserDefaults.standard.string(forKey: .authUserId)
    originalOverride = UserDefaults.standard.string(forKey: .automationOwnerOverride)
    originalBackup = UserDefaults.standard.string(forKey: .automationOwnerABackup)
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in nil }
    ) { defaults in
      defaults.removeObject(forKey: .authUserId)
      defaults.removeObject(forKey: .automationOwnerOverride)
      defaults.removeObject(forKey: .automationOwnerABackup)
    }
    await RewindDatabase.shared.close()
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    let authOwner = originalAuthOwner
    let override = originalOverride
    let backup = originalBackup
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      allowAutomationOverride: true,
      plannedNextOwner: { _, _ in
        let normalizedOverride = override?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let normalizedOverride, !normalizedOverride.isEmpty { return normalizedOverride }
        return authOwner?.trimmingCharacters(in: .whitespacesAndNewlines)
      }
    ) { defaults in
      Self.restore(authOwner, forKey: .authUserId, in: defaults)
      Self.restore(override, forKey: .automationOwnerOverride, in: defaults)
      Self.restore(backup, forKey: .automationOwnerABackup, in: defaults)
    }
    for ownerID in createdOwnerIDs {
      try? FileManager.default.removeItem(at: userDirectory(ownerID))
    }
    createdOwnerIDs = []
  }

  func testOwnerTransitionWaitsForACommitThenAdmitsBWithBPool() async throws {
    let ownerA = makeOwnerID("pool-owner-a")
    let ownerB = makeOwnerID("pool-owner-b")
    await setOwner(ownerA)
    try await RewindDatabase.shared.initialize()
    let maybeOwnerAPool = await RewindDatabase.shared.getDatabaseQueue()
    let ownerAPool = try XCTUnwrap(maybeOwnerAPool)
    try await ownerAPool.write { db in
      try db.execute(sql: "CREATE TABLE owner_probe (value TEXT NOT NULL)")
      try Self.insertIndexedFile(path: "~/owner-a.txt", in: db)
    }
    let ownerAIndexedFileCount = await FileIndexerService.shared.getIndexedFileCount()
    XCTAssertEqual(ownerAIndexedFileCount, 1)

    let observer = OwnerDatabaseCommitObserver()
    ownerAPool.add(transactionObserver: observer, extent: .nextTransaction)
    let ownerAWrite = Task.detached {
      try await ChatToolExecutor.executeWriteQuery(
        "INSERT INTO owner_probe(value) VALUES ('owner-a')",
        dbQueue: ownerAPool,
        expectedOwnerID: ownerA,
        ownerIsCurrent: { expected in
          RuntimeOwnerIdentity.currentOwnerId(allowAutomationOverride: false) == expected
        })
    }

    await observer.waitUntilWillCommit()
    let transition = Task { @MainActor in
      await self.setOwner(ownerB)
    }
    await EffectiveOwnerTransitionFence.shared.waitUntilTransitionIsPending()
    XCTAssertEqual(
      RuntimeOwnerIdentity.currentOwnerId(allowAutomationOverride: false),
      ownerA,
      "the owner must not change while A still has a physical commit lease")

    observer.allowCommit()
    let ownerAResult = try await ownerAWrite.value
    XCTAssertEqual(
      ownerAResult,
      ChatToolExecutor.authorizedOwnerChangedResult(),
      "A may commit before the queued transition, but its result must not publish into B")
    await transition.value

    let ownerBAuthorization = LocalMutationAuthorization {
      RuntimeOwnerIdentity.currentOwnerId(allowAutomationOverride: false) == ownerB
    }
    try await ownerBAuthorization.withCommitLease {
      try await RewindDatabase.shared.initialize()
      let maybeOwnerBPool = await RewindDatabase.shared.getDatabaseQueue()
      let ownerBPool = try XCTUnwrap(maybeOwnerBPool)
      try await ownerBPool.write { db in
        try db.execute(sql: "CREATE TABLE owner_probe (value TEXT NOT NULL)")
        try db.execute(sql: "INSERT INTO owner_probe(value) VALUES ('owner-b')")
        try Self.insertIndexedFile(path: "~/owner-b-1.txt", in: db)
        try Self.insertIndexedFile(path: "~/owner-b-2.txt", in: db)
      }
    }
    let ownerBIndexedFileCount = await FileIndexerService.shared.getIndexedFileCount()
    XCTAssertEqual(
      ownerBIndexedFileCount,
      2,
      "the shared file indexer must drop its owner-A pool before serving owner B")

    await RewindDatabase.shared.close()
    let ownerAValues = try readProbeValues(ownerID: ownerA)
    let ownerBValues = try readProbeValues(ownerID: ownerB)
    XCTAssertEqual(ownerAValues, ["owner-a"])
    XCTAssertEqual(ownerBValues, ["owner-b"])
  }

  private func setOwner(_ ownerID: String) async {
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      allowAutomationOverride: false,
      plannedNextOwner: { _, _ in ownerID }
    ) { defaults in
      defaults.set(ownerID, forKey: .authUserId)
    }
  }

  private func readProbeValues(ownerID: String) throws -> [String] {
    let pool = try DatabasePool(
      path: userDirectory(ownerID).appendingPathComponent("omi.db").path)
    return try pool.read { db in
      try String.fetchAll(db, sql: "SELECT value FROM owner_probe ORDER BY rowid")
    }
  }

  private func makeOwnerID(_ prefix: String) -> String {
    let ownerID = "\(prefix)-\(UUID().uuidString)"
    createdOwnerIDs.append(ownerID)
    return ownerID
  }

  private func userDirectory(_ ownerID: String) -> URL {
    DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(ownerID, isDirectory: true)
  }

  nonisolated private static func restore(
    _ value: String?,
    forKey key: DefaultsKey,
    in defaults: UserDefaults
  ) {
    if let value {
      defaults.set(value, forKey: key)
    } else {
      defaults.removeObject(forKey: key)
    }
  }

  nonisolated private static func insertIndexedFile(path: String, in db: Database) throws {
    try db.execute(
      sql: """
        INSERT INTO indexed_files
          (path, filename, fileType, sizeBytes, folder, depth, indexedAt)
        VALUES (?, ?, 'document', 1, 'Documents', 0, ?)
        """,
      arguments: [path, URL(fileURLWithPath: path).lastPathComponent, Date()])
  }
}
