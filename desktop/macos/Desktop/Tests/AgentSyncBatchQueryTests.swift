import XCTest

@testable import Omi_Computer

private actor AgentSyncDelayedTokenGate {
  private var fetchCount = 0
  private var firstFetchStarted = false
  private var firstFetchWaiters: [CheckedContinuation<Void, Never>] = []
  private var firstFetchContinuation: CheckedContinuation<Void, Never>?
  private var requests: [URLRequest] = []
  private var requestWaiters: [CheckedContinuation<Void, Never>] = []

  func fetchToken() async -> String {
    fetchCount += 1
    if fetchCount == 1 {
      firstFetchStarted = true
      let waiters = firstFetchWaiters
      firstFetchWaiters.removeAll()
      waiters.forEach { $0.resume() }
      await withCheckedContinuation { continuation in
        firstFetchContinuation = continuation
      }
      return "owner-a-token"
    }
    return "owner-b-token"
  }

  func waitUntilFirstFetchStarts() async {
    guard !firstFetchStarted else { return }
    await withCheckedContinuation { continuation in
      firstFetchWaiters.append(continuation)
    }
  }

  func releaseFirstFetch() {
    firstFetchContinuation?.resume()
    firstFetchContinuation = nil
  }

  func respond(to request: URLRequest) -> (Data, URLResponse) {
    requests.append(request)
    let waiters = requestWaiters
    requestWaiters.removeAll()
    waiters.forEach { $0.resume() }
    let response = HTTPURLResponse(
      url: request.url!,
      statusCode: 200,
      httpVersion: nil,
      headerFields: nil)!
    return (Data(), response)
  }

  func waitForRequest() async {
    guard requests.isEmpty else { return }
    await withCheckedContinuation { continuation in
      requestWaiters.append(continuation)
    }
  }

  func requestURLs() -> [URL] {
    requests.compactMap(\.url)
  }
}

/// Regression test for the AgentSync mutable-table pagination skip: paging with a
/// strict `updatedAt > ?` cursor drops every row past the first batch when more
/// than `batchSize` rows share the same `updatedAt` (a bulk update touching >100
/// rows in one second), silently diverging the VM's copy. Mutable tables must page
/// on a compound `(updatedAt, id)` cursor.
final class AgentSyncBatchQueryTests: XCTestCase {

  func testPartialSchemaIsNotReadyEvenWhenDatabaseReadyIsTrue() {
    let readiness = AgentSyncService.databaseReadiness(
      healthPayload: ["databaseReady": true],
      syncFailureBody: "SQLite error: no such table: transcription_sessions"
    )

    XCTAssertEqual(
      readiness,
      .missingRequiredSchema,
      "A VM that reports databaseReady while rejecting a required sync table must be re-provisioned by the existing upload owner"
    )
  }

  func testUnrelatedSQLiteTableFailureDoesNotTriggerDatabaseReupload() {
    let readiness = AgentSyncService.databaseReadiness(
      healthPayload: ["databaseReady": true],
      syncFailureBody: "SQLite error: no such table: scratch_cache"
    )

    XCTAssertEqual(
      readiness,
      .ready,
      "Only tables owned by AgentSync prove its uploaded schema is partial; unrelated server faults must keep bounded retry behavior"
    )
  }

  func testMutableTableUsesCompoundCursor() {
    let (sql, args) = AgentSyncService.buildBatchQuery(
      tableName: "action_items",
      selectCols: "\"id\", \"updatedAt\"",
      appendOnly: false,
      lastId: 42,
      lastUpdatedAt: "2026-04-09T12:00:00",
      batchSize: 100
    )

    // Must include the compound clause and id-tiebreaker ordering — not a bare
    // strict `updatedAt > ?` that would skip same-timestamp rows.
    XCTAssertTrue(sql.contains("updatedAt > ? OR (updatedAt = ? AND id > ?)"), sql)
    XCTAssertTrue(sql.contains("ORDER BY updatedAt ASC, id ASC"), sql)
    XCTAssertEqual(
      args,
      [.text("2026-04-09T12:00:00"), .text("2026-04-09T12:00:00"), .int(42), .int(100)])
  }

  func testAppendOnlyTablePagesById() {
    let (sql, args) = AgentSyncService.buildBatchQuery(
      tableName: "screenshots",
      selectCols: "\"id\"",
      appendOnly: true,
      lastId: 7,
      lastUpdatedAt: "1970-01-01T00:00:00",
      batchSize: 100
    )

    XCTAssertTrue(sql.contains("WHERE id > ? ORDER BY id ASC"), sql)
    XCTAssertFalse(sql.contains("updatedAt"), sql)
    XCTAssertEqual(args, [.int(7), .int(100)])
  }

  @MainActor
  func testDelayedOwnerATokenCannotResumeIntoOwnerBVM() async {
    let originalPhase = AuthState.shared.sessionPhase
    AuthState.shared.transition(to: .authenticated)
    defer { AuthState.shared.transition(to: originalPhase) }

    let gate = AgentSyncDelayedTokenGate()
    let service = AgentSyncService(
      networkHooks: AgentSyncService.NetworkHooks(
        fetchIDToken: { await gate.fetchToken() },
        dataForRequest: { request in await gate.respond(to: request) },
        tableSyncEnabled: false))

    await service.start(vmIP: "owner-a-vm", authToken: "owner-a-auth")
    await gate.waitUntilFirstFetchStarts()
    await service.stop(flushPendingChanges: false)
    await service.start(vmIP: "owner-b-vm", authToken: "owner-b-auth")

    await gate.waitForRequest()
    await gate.releaseFirstFetch()
    await Task.yield()
    await service.stop(flushPendingChanges: false)

    let requestURLs = await gate.requestURLs()
    XCTAssertEqual(requestURLs.count, 1)
    XCTAssertEqual(requestURLs.first?.host, "owner-b-vm")
    XCTAssertEqual(requestURLs.first?.path, "/auth")
  }
}
