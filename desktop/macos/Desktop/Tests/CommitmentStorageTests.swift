import XCTest
@testable import Omi_Computer

final class CommitmentStorageTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "commitment-storage-test-\(UUID().uuidString)"
    try await RewindDatabase.shared.switchUser(to: testUserId)
    await CommitmentStorage.shared.invalidateCache()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir = appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await CommitmentStorage.shared.invalidateCache()
    await RewindDatabase.shared.close()
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    RewindDatabase.currentUserId = nil
    try await super.tearDown()
  }

  // MARK: - hasProcessedSession

  func testHasProcessedSessionFalseWhenNeverProcessed() async {
    let result = await CommitmentStorage.shared.hasProcessedSession(999_999)
    XCTAssertFalse(result, "A session that was never processed must return false")
  }

  func testHasProcessedSessionTrueWhenCommitmentsExist() async {
    let sessionId = try! await insertMinimalCompletedSession()
    let record = CommitmentRecord(
      text: "I'll send the report",
      sourceSessionId: sessionId
    )
    try! await CommitmentStorage.shared.insertCommitment(record)

    let result = await CommitmentStorage.shared.hasProcessedSession(sessionId)
    XCTAssertTrue(result, "Session with extracted commitments must be recognized as processed")
  }

  func testHasProcessedSessionTrueWhenMarkedNoCommitments() async {
    let sessionId = try! await insertMinimalCompletedSession()
    try! await CommitmentStorage.shared.markSessionProcessed(sessionId)

    let result = await CommitmentStorage.shared.hasProcessedSession(sessionId)
    XCTAssertTrue(result, "Session marked as processed (no commitments) must return true")
  }

  // MARK: - markSessionProcessed

  func testMarkSessionProcessedCreatesMarker() async {
    let sessionId = try! await insertMinimalCompletedSession()
    try! await CommitmentStorage.shared.markSessionProcessed(sessionId)

    let result = await CommitmentStorage.shared.hasProcessedSession(sessionId)
    XCTAssertTrue(result, "markSessionProcessed must register the session as processed")
  }

  func testMarkSessionProcessedIdempotent() async {
    let sessionId = try! await insertMinimalCompletedSession()
    try! await CommitmentStorage.shared.markSessionProcessed(sessionId)
    try! await CommitmentStorage.shared.markSessionProcessed(sessionId)

    let result = await CommitmentStorage.shared.hasProcessedSession(sessionId)
    XCTAssertTrue(result, "Marking the same session twice must not throw")
  }

  // MARK: - getUnprocessedCompletedSessionIds

  func testGetUnprocessedExcludesSessionsWithCommitments() async {
    let processedSessionId = try! await insertMinimalCompletedSession()
    let unprocessedSessionId = try! await insertMinimalCompletedSession()

    let record = CommitmentRecord(
      text: "I'll call you",
      sourceSessionId: processedSessionId
    )
    try! await CommitmentStorage.shared.insertCommitment(record)

    let ids = try! await CommitmentStorage.shared.getUnprocessedCompletedSessionIds(limit: 100)
    XCTAssertFalse(ids.contains(processedSessionId), "Session with commitments must be excluded")
    XCTAssertTrue(ids.contains(unprocessedSessionId), "Unprocessed session must be included")
  }

  func testGetUnprocessedExcludesMarkedSessions() async {
    let markedSessionId = try! await insertMinimalCompletedSession()
    let unmarkedSessionId = try! await insertMinimalCompletedSession()

    try! await CommitmentStorage.shared.markSessionProcessed(markedSessionId)

    let ids = try! await CommitmentStorage.shared.getUnprocessedCompletedSessionIds(limit: 100)
    XCTAssertFalse(ids.contains(markedSessionId), "Session marked as processed must be excluded")
    XCTAssertTrue(ids.contains(unmarkedSessionId), "Unmarked session must be included")
  }

  func testGetUnprocessedRespectsLimit() async {
    for _ in 0..<10 {
      try! await insertMinimalCompletedSession()
    }

    let ids = try! await CommitmentStorage.shared.getUnprocessedCompletedSessionIds(limit: 3)
    XCTAssertEqual(ids.count, 3, "Limit of 3 must return exactly 3 sessions")
  }

  func testGetUnprocessedReturnsEmptyWhenAllProcessed() async {
    for _ in 0..<3 {
      let sid = try! await insertMinimalCompletedSession()
      try! await CommitmentStorage.shared.markSessionProcessed(sid)
    }

    let ids = try! await CommitmentStorage.shared.getUnprocessedCompletedSessionIds(limit: 100)
    XCTAssertTrue(ids.isEmpty, "All sessions processed must return empty")
  }

  // MARK: - CRUD

  func testInsertAndQueryCommitmentsByStatus() async {
    let sessionId = try! await insertMinimalCompletedSession()

    let pending = CommitmentRecord(
      text: "Pending task",
      status: .pending,
      sourceSessionId: sessionId
    )
    let fulfilled = CommitmentRecord(
      text: "Fulfilled task",
      status: .fulfilled,
      sourceSessionId: sessionId
    )
    try! await CommitmentStorage.shared.insertCommitment(pending)
    try! await CommitmentStorage.shared.insertCommitment(fulfilled)

    let allPending = try! await CommitmentStorage.shared.getCommitments(status: .pending)
    let allFulfilled = try! await CommitmentStorage.shared.getCommitments(status: .fulfilled)

    XCTAssertEqual(allPending.count, 1, "Must find 1 pending commitment")
    XCTAssertEqual(allPending.first?.text, "Pending task")
    XCTAssertEqual(allFulfilled.count, 1, "Must find 1 fulfilled commitment")
  }

  func testMarkFulfilled() async {
    let sessionId = try! await insertMinimalCompletedSession()
    let record = CommitmentRecord(
      text: "Will do",
      status: .pending,
      sourceSessionId: sessionId
    )
    let id = try! await CommitmentStorage.shared.insertCommitment(record)

    try! await CommitmentStorage.shared.markFulfilled(
      id: id, evidence: "Done it", bySessionId: nil
    )

    let updated = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertNotNil(updated)
    XCTAssertEqual(updated?.commitmentStatus, .fulfilled)
    XCTAssertEqual(updated?.fulfilledByEvidence, "Done it")
  }

  func testMarkMissed() async {
    let sessionId = try! await insertMinimalCompletedSession()
    let record = CommitmentRecord(
      text: "Missed it",
      status: .pending,
      sourceSessionId: sessionId
    )
    let id = try! await CommitmentStorage.shared.insertCommitment(record)

    try! await CommitmentStorage.shared.markMissed(id: id)

    let updated = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertNotNil(updated)
    XCTAssertEqual(updated?.commitmentStatus, .missed)
  }

  func testUpdateDeadline() async {
    let sessionId = try! await insertMinimalCompletedSession()
    let record = CommitmentRecord(
      text: "Deadline test",
      status: .pending,
      sourceSessionId: sessionId
    )
    let id = try! await CommitmentStorage.shared.insertCommitment(record)
    let newDeadline = Date(timeIntervalSinceNow: 86400)

    try! await CommitmentStorage.shared.updateDeadline(id: id, deadline: newDeadline)

    let updated = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertNotNil(updated)
    let deadline = updated?.deadline
    XCTAssertNotNil(deadline)
    XCTAssertEqual(deadline!.timeIntervalSinceReferenceDate,
                   newDeadline.timeIntervalSinceReferenceDate, accuracy: 1.0)
  }

  func testUpdateStatus() async {
    let sessionId = try! await insertMinimalCompletedSession()
    let record = CommitmentRecord(
      text: "Status cycle",
      status: .pending,
      sourceSessionId: sessionId
    )
    let id = try! await CommitmentStorage.shared.insertCommitment(record)

    try! await CommitmentStorage.shared.updateStatus(id: id, status: .fulfilled)
    var updated = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertEqual(updated?.commitmentStatus, .fulfilled)

    try! await CommitmentStorage.shared.updateStatus(id: id, status: .missed)
    updated = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertEqual(updated?.commitmentStatus, .missed)

    try! await CommitmentStorage.shared.updateStatus(id: id, status: .pending)
    updated = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertEqual(updated?.commitmentStatus, .pending)
  }

  func testDeleteCommitment() async {
    let sessionId = try! await insertMinimalCompletedSession()
    let record = CommitmentRecord(
      text: "Delete me",
      status: .pending,
      sourceSessionId: sessionId
    )
    let id = try! await CommitmentStorage.shared.insertCommitment(record)

    try! await CommitmentStorage.shared.deleteCommitment(id: id)

    let deleted = try! await CommitmentStorage.shared.getCommitment(byId: id)
    XCTAssertNil(deleted)
  }

  // MARK: - Helpers

  /// Creates a minimal completed transcription session and returns its ID.
  @discardableResult
  private func insertMinimalCompletedSession() async throws -> Int64 {
    guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
      throw CommitmentStorageError.databaseNotInitialized
    }
    let session = TranscriptionSessionRecord(
      source: "desktop",
      status: .completed,
      backendSynced: true
    )
    let inserted = try await db.write { database in
      try session.inserted(database)
    }
    return inserted.id!
  }
}
