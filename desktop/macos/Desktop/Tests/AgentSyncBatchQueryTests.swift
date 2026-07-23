import Foundation
import GRDB
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

private final class AgentSyncManualClock: @unchecked Sendable {
  private let lock = NSLock()
  private var value: Date

  init(_ value: Date = Date(timeIntervalSince1970: 1_700_000_000)) {
    self.value = value
  }

  func now() -> Date {
    lock.withLock { value }
  }

  func advance(_ interval: TimeInterval) {
    lock.withLock { value.addTimeInterval(interval) }
  }
}

private actor AgentSyncReplacementCallbackGate {
  enum Endpoint: Hashable {
    case sync
    case health
    case upload
  }

  private let suspended: Set<Endpoint>
  private var started: Set<Endpoint> = []
  private var startWaiters: [Endpoint: [CheckedContinuation<Void, Never>]] = [:]
  private var releaseContinuations: [Endpoint: CheckedContinuation<Void, Never>] = [:]
  private var reuploadVMs: [String] = []

  init(suspending endpoint: Endpoint) {
    suspended = [endpoint]
  }

  func respond(to request: URLRequest) async throws -> (Data, URLResponse) {
    let url = try XCTUnwrap(request.url)
    let endpoint: Endpoint? =
      switch url.path {
      case "/sync": .sync
      case "/health": .health
      default: nil
      }
    if url.host == "old-vm", let endpoint, suspended.contains(endpoint) {
      await suspend(endpoint)
    }

    switch url.path {
    case "/auth":
      return (Data(), response(url, status: 200))
    case "/sync":
      let payload = try XCTUnwrap(request.httpBody)
      let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: payload) as? [String: Any])
      let table = try XCTUnwrap(json["table"] as? String)
      if table == "transcription_sessions" {
        return (Data("SQLite error: no such table: \(table)".utf8), response(url, status: 500))
      }
      return (Data(), response(url, status: 200))
    case "/health":
      return (try JSONSerialization.data(withJSONObject: ["databaseReady": true]), response(url, status: 200))
    default:
      return (Data(), response(url, status: 404))
    }
  }

  func reupload(vmIP: String) async -> Bool {
    reuploadVMs.append(vmIP)
    if vmIP == "old-vm", suspended.contains(.upload) {
      await suspend(.upload)
    }
    return true
  }

  func waitUntilStarted(_ endpoint: Endpoint) async {
    guard !started.contains(endpoint) else { return }
    await withCheckedContinuation { continuation in
      startWaiters[endpoint, default: []].append(continuation)
    }
  }

  func release(_ endpoint: Endpoint) {
    releaseContinuations.removeValue(forKey: endpoint)?.resume()
  }

  func uploadVMs() -> [String] {
    reuploadVMs
  }

  private func suspend(_ endpoint: Endpoint) async {
    started.insert(endpoint)
    let waiters = startWaiters.removeValue(forKey: endpoint) ?? []
    waiters.forEach { $0.resume() }
    await withCheckedContinuation { continuation in
      releaseContinuations[endpoint] = continuation
    }
  }

  private func response(_ url: URL, status: Int) -> URLResponse {
    HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)
      ?? URLResponse(url: url, mimeType: nil, expectedContentLength: 0, textEncodingName: nil)
  }
}

private actor AgentSyncRecoveryProbe {
  enum HealthResponse {
    case ready
    case malformed
    case status(Int)
  }

  private var missingTables: Set<String>
  private var healthResponse: HealthResponse = .ready
  private var uploadResults: [Bool] = [true]
  private var healthChecks = 0
  private var uploads = 0
  private var syncedTables: [String] = []
  private var lastHealthAuthorization: String?
  private var lastHealthTokenQuery: String?

  init(missingTable: String? = "transcription_sessions") {
    missingTables = missingTable.map { [$0] } ?? []
  }

  func respond(to request: URLRequest) throws -> (Data, URLResponse) {
    let url = try XCTUnwrap(request.url)
    switch url.path {
    case "/auth":
      return (Data(), response(url, status: 200))
    case "/sync":
      let payload = try XCTUnwrap(request.httpBody)
      let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: payload) as? [String: Any])
      let table = try XCTUnwrap(json["table"] as? String)
      syncedTables.append(table)
      if missingTables.contains(table) {
        return (Data("SQLite error: no such table: \(table)".utf8), response(url, status: 500))
      }
      return (Data(), response(url, status: 200))
    case "/health":
      healthChecks += 1
      lastHealthAuthorization = request.value(forHTTPHeaderField: "Authorization")
      lastHealthTokenQuery =
        URLComponents(url: url, resolvingAgainstBaseURL: false)?
        .queryItems?
        .first(where: { $0.name == "token" })?
        .value
      switch healthResponse {
      case .ready:
        return (try JSONSerialization.data(withJSONObject: ["databaseReady": true]), response(url, status: 200))
      case .malformed:
        return (Data("not-json".utf8), response(url, status: 200))
      case .status(let status):
        return (Data(), response(url, status: status))
      }
    default:
      return (Data(), response(url, status: 404))
    }
  }

  func reupload() -> Bool {
    uploads += 1
    return uploadResults.isEmpty ? false : uploadResults.removeFirst()
  }

  func setMissingTable(_ table: String?) {
    missingTables = table.map { [$0] } ?? []
  }

  func setMissingTables(_ tables: Set<String>) {
    missingTables = tables
  }

  func setHealthResponse(_ response: HealthResponse) {
    healthResponse = response
  }

  func setUploadResults(_ results: [Bool]) {
    uploadResults = results
  }

  func counts() -> (healthChecks: Int, uploads: Int, syncedTables: [String]) {
    (healthChecks, uploads, syncedTables)
  }

  func lastHealthAuth() -> (authorization: String?, tokenQuery: String?) {
    (lastHealthAuthorization, lastHealthTokenQuery)
  }

  private func response(_ url: URL, status: Int) -> URLResponse {
    HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)
      ?? URLResponse(url: url, mimeType: nil, expectedContentLength: 0, textEncodingName: nil)
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

  func testMalformedOrMissingHealthReadinessIsNotMissingDatabase() {
    XCTAssertEqual(AgentSyncService.databaseReadiness(healthPayload: [:]), .unknown)
    XCTAssertEqual(AgentSyncService.databaseReadiness(healthPayload: ["databaseReady": "false"]), .unknown)
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
        reuploadDatabase: { _, _ in true },
        now: Date.init,
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

/// These tests drive `syncTick` through the same table reads and HTTP paths as
/// the loop. The DEBUG-only clock/hook seam avoids a scheduler or bridge fault
/// protocol while preserving production ownership and recovery behavior.
final class AgentSyncRecoveryTests: XCTestCase {
  private var storageFixture: RewindStorageTestIsolation.Fixture?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    try await super.setUp()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "agent-sync-recovery")
    storageFixture = fixture
    authSnapshot = await MainActor.run { RewindStorageTestIsolation.captureAuthSnapshot() }
    await MainActor.run { RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId) }
    try await insertSyncRows()
  }

  override func tearDown() async throws {
    if let authSnapshot {
      await MainActor.run { RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot) }
    }
    await RewindStorageTestIsolation.tearDown(userDir: storageFixture?.userDir)
    try await super.tearDown()
  }

  func testMixedSuccessStillRecoversTheRepeatedRequiredTableFailure() async {
    let probe = AgentSyncRecoveryProbe()
    let service = makeService(probe: probe)
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")

    await service.syncOnceForTesting()
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()

    let counts = await probe.counts()
    XCTAssertTrue(
      counts.syncedTables.contains("action_items"), "The control table must take the real /sync success path")
    XCTAssertEqual(counts.syncedTables.filter { $0 == "transcription_sessions" }.count, 3)
    XCTAssertEqual(counts.healthChecks, 1, "Three causal failures trigger one fail-closed /health check")
    XCTAssertEqual(counts.uploads, 1, "The existing database-upload owner repairs the missing table exactly once")
    let healthAuth = await probe.lastHealthAuth()
    XCTAssertEqual(healthAuth.authorization, "Bearer test-token")
    XCTAssertEqual(healthAuth.tokenQuery, "test-token")
  }

  func testTwoMissingRequiredTablesDoNotAlternateAwayTheSelectedRecovery() async {
    let probe = AgentSyncRecoveryProbe()
    await probe.setMissingTables(["transcription_sessions", "action_items"])
    let service = makeService(probe: probe)
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")

    for _ in 0..<3 { await service.syncOnceForTesting() }

    let counts = await probe.counts()
    XCTAssertEqual(counts.syncedTables.filter { $0 == "transcription_sessions" }.count, 3)
    XCTAssertEqual(counts.syncedTables.filter { $0 == "action_items" }.count, 3)
    XCTAssertTrue(
      counts.syncedTables.contains("memories"),
      "A successful required table must not suppress recovery for the selected missing table"
    )
    XCTAssertEqual(counts.healthChecks, 1, "Alternating missing tables must still reach the causal recovery threshold")
    XCTAssertEqual(counts.uploads, 1, "One selected causal table produces one bounded repair")
  }

  func testMatchingTableSuccessClearsRecoveryButUnrelatedSuccessDoesNot() async throws {
    let probe = AgentSyncRecoveryProbe()
    let service = makeService(probe: probe)
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")

    await service.syncOnceForTesting()
    await service.syncOnceForTesting()
    await probe.setMissingTable(nil)  // The previously failing table now succeeds.
    await service.syncOnceForTesting()
    await probe.setMissingTable("transcription_sessions")
    try await touchTranscriptionSession()
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()

    var counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 0, "A matching success clears the earlier table's causal evidence")
    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 1, "Only three new failures of the same required table recover it")
  }

  func testMalformedAndNonSuccessHealthNeverUpload() async {
    let probe = AgentSyncRecoveryProbe()
    await probe.setHealthResponse(.malformed)
    let service = makeService(probe: probe)
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")

    for _ in 0..<3 { await service.syncOnceForTesting() }
    var counts = await probe.counts()
    XCTAssertEqual(counts.healthChecks, 1)
    XCTAssertEqual(counts.uploads, 0)

    await probe.setHealthResponse(.status(503))
    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 0, "Non-2xx health responses fail closed before upload")
  }

  func testSameOwnerRestartPreservesCooldownAndFailedUploadsStayBounded() async {
    let probe = AgentSyncRecoveryProbe()
    await probe.setUploadResults([false, false, false])
    let clock = AgentSyncManualClock()
    let service = makeService(probe: probe, clock: clock)
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")

    for _ in 0..<3 { await service.syncOnceForTesting() }
    var counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 1)

    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")
    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 1, "Same-owner restart cannot mint a new cooldown allowance")

    clock.advance(30 * 60 + 1)
    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 2)

    clock.advance(30 * 60 + 1)
    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 2, "Failed recovery uploads stop at the existing bounded policy")
  }

  func testSameOwnerReplacementVMResetsOldRecoveryEvidenceCooldownAndBudget() async {
    let probe = AgentSyncRecoveryProbe()
    await probe.setUploadResults([false, false, false])
    let clock = AgentSyncManualClock()
    let service = makeService(probe: probe, clock: clock)
    await service.startForTesting(vmIP: "old-vm", authToken: "test-token")

    for _ in 0..<3 { await service.syncOnceForTesting() }
    clock.advance(30 * 60 + 1)
    await service.syncOnceForTesting()
    var counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 2, "The old VM exhausts its bounded retry budget")

    await service.startForTesting(vmIP: "replacement-vm", authToken: "test-token")
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 2, "Replacement must not upload from stale old-VM evidence")

    await service.syncOnceForTesting()
    counts = await probe.counts()
    XCTAssertEqual(counts.uploads, 3, "Replacement gets a fresh causal threshold and bounded retry budget")
  }

  func testDelayedOldVMSyncResponseCannotCreateReplacementRecoveryEvidence() async {
    let gate = AgentSyncReplacementCallbackGate(suspending: .sync)
    let service = makeService(gate: gate)
    await service.startForTesting(vmIP: "old-vm", authToken: "test-token")
    let oldTick = Task { await service.syncOnceForTesting() }
    await gate.waitUntilStarted(.sync)

    await service.startForTesting(vmIP: "replacement-vm", authToken: "test-token")
    await gate.release(.sync)
    await oldTick.value
    for _ in 0..<3 { await service.syncOnceForTesting() }

    let uploadVMs = await gate.uploadVMs()
    XCTAssertEqual(uploadVMs, ["replacement-vm"])
  }

  func testDelayedOldVMHealthResponseCannotSpendReplacementRecoveryBudget() async {
    let gate = AgentSyncReplacementCallbackGate(suspending: .health)
    let service = makeService(gate: gate)
    await service.startForTesting(vmIP: "old-vm", authToken: "test-token")
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()
    let oldTick = Task { await service.syncOnceForTesting() }
    await gate.waitUntilStarted(.health)

    await service.startForTesting(vmIP: "replacement-vm", authToken: "test-token")
    await gate.release(.health)
    await oldTick.value
    for _ in 0..<3 { await service.syncOnceForTesting() }

    let uploadVMs = await gate.uploadVMs()
    XCTAssertEqual(uploadVMs, ["replacement-vm"])
  }

  func testDelayedOldVMUploadResponseCannotClearReplacementRecoveryEvidence() async {
    let gate = AgentSyncReplacementCallbackGate(suspending: .upload)
    let service = makeService(gate: gate)
    await service.startForTesting(vmIP: "old-vm", authToken: "test-token")
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()
    let oldTick = Task { await service.syncOnceForTesting() }
    await gate.waitUntilStarted(.upload)

    await service.startForTesting(vmIP: "replacement-vm", authToken: "test-token")
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()
    await gate.release(.upload)
    await oldTick.value
    await service.syncOnceForTesting()

    let uploadVMs = await gate.uploadVMs()
    XCTAssertEqual(uploadVMs, ["old-vm", "replacement-vm"])
  }

  private func makeService(
    probe: AgentSyncRecoveryProbe,
    clock: AgentSyncManualClock = AgentSyncManualClock()
  ) -> AgentSyncService {
    AgentSyncService(
      networkHooks: AgentSyncService.NetworkHooks(
        fetchIDToken: { "test-firebase-token" },
        dataForRequest: { request in try await probe.respond(to: request) },
        reuploadDatabase: { _, _ in await probe.reupload() },
        now: { clock.now() },
        tableSyncEnabled: true))
  }

  private func makeService(gate: AgentSyncReplacementCallbackGate) -> AgentSyncService {
    AgentSyncService(
      networkHooks: AgentSyncService.NetworkHooks(
        fetchIDToken: { "test-firebase-token" },
        dataForRequest: { request in try await gate.respond(to: request) },
        reuploadDatabase: { vmIP, _ in await gate.reupload(vmIP: vmIP) },
        now: Date.init,
        tableSyncEnabled: true))
  }

  private func insertSyncRows() async throws {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("Rewind database should be initialized")
    }
    let now = Date(timeIntervalSince1970: 1_700_000_000)
    try await dbQueue.write { db in
      try db.execute(
        sql: """
          INSERT INTO transcription_sessions (startedAt, source, createdAt, updatedAt)
          VALUES (?, ?, ?, ?)
          """,
        arguments: [now, "desktop", now, now])
      try db.execute(
        sql: """
            INSERT INTO action_items (description, createdAt, updatedAt)
            VALUES (?, ?, ?)
          """,
        arguments: ["mixed-success control", now, now])
      try db.execute(
        sql: """
          INSERT INTO memories (content, category, createdAt, updatedAt)
          VALUES (?, ?, ?, ?)
          """,
        arguments: ["mixed-success recovery control", "system", now, now])
    }
  }

  private func touchTranscriptionSession() async throws {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("Rewind database should be initialized")
    }
    try await dbQueue.write { db in
      try db.execute(
        sql: "UPDATE transcription_sessions SET updatedAt = ? WHERE id = 1",
        arguments: [Date(timeIntervalSince1970: 1_700_000_001)])
    }
  }
}
