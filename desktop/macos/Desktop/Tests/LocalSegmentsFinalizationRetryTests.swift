import GRDB
import XCTest

@testable import Omi_Computer

private enum LocalUploadStubMode: Sendable {
  case offline
  case httpStatus(Int)
  case success
}

/// Scripted `/v1/conversations/from-segments`: success returns `backend-<client_conversation_id>`, and
/// every other path is a 404 so hydration fails open.
private final class LocalUploadRetryURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _mode: LocalUploadStubMode = .success
  private nonisolated(unsafe) static var _uploadBodies: [Data] = []

  static var uploadBodies: [Data] {
    lock.lock()
    defer { lock.unlock() }
    return _uploadBodies
  }

  static func setMode(_ mode: LocalUploadStubMode) {
    lock.lock()
    _mode = mode
    lock.unlock()
  }

  static func reset() {
    lock.lock()
    _mode = .success
    _uploadBodies.removeAll()
    lock.unlock()
  }

  private static func recordUpload(_ body: Data?) -> LocalUploadStubMode {
    lock.lock()
    defer { lock.unlock() }
    _uploadBodies.append(body ?? Data())
    return _mode
  }

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody {
      return body
    }
    guard let stream = request.httpBodyStream else {
      return nil
    }

    stream.open()
    defer { stream.close() }

    var data = Data()
    let bufferSize = 4096
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
    defer { buffer.deallocate() }

    while stream.hasBytesAvailable {
      let readCount = stream.read(buffer, maxLength: bufferSize)
      if readCount > 0 {
        data.append(buffer, count: readCount)
      } else {
        break
      }
    }

    return data.isEmpty ? nil : data
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else { return }
    guard url.path == "/v1/conversations/from-segments" else {
      respond(url: url, statusCode: 404, body: Data(#"{"detail":"not found"}"#.utf8))
      return
    }
    let body = Self.bodyData(from: request)
    switch Self.recordUpload(body) {
    case .offline:
      client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
    case .httpStatus(let statusCode):
      respond(url: url, statusCode: statusCode, body: Data(#"{"detail":"stubbed upload failure"}"#.utf8))
    case .success:
      let json = body.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
      let clientConversationId = json?["client_conversation_id"] as? String ?? "unknown"
      let response: [String: Any] = [
        "id": "backend-\(clientConversationId)",
        "status": "processing",
        "discarded": false,
      ]
      let responseBody = (try? JSONSerialization.data(withJSONObject: response)) ?? Data()
      respond(url: url, statusCode: 200, body: responseBody)
    }
  }

  private func respond(url: URL, statusCode: Int, body: Data) {
    guard let response = HTTPURLResponse(url: url, statusCode: statusCode, httpVersion: nil, headerFields: nil)
    else { return }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

/// Storage stamps `updatedAt` with the real time, so the injected clock is "real now + elapsed".
private final class ElapsedTimeClock: @unchecked Sendable {
  private let lock = NSLock()
  private var elapsed: TimeInterval = 0

  var now: Date {
    lock.lock()
    defer { lock.unlock() }
    return Date().addingTimeInterval(elapsed)
  }

  func setElapsed(_ seconds: TimeInterval) {
    lock.lock()
    elapsed = seconds
    lock.unlock()
  }
}

private actor NetworkPathFlag {
  private(set) var isOnline = true

  func set(_ online: Bool) {
    isOnline = online
  }
}

final class LocalSegmentsFinalizationRetryTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL?
  private let clock = ElapsedTimeClock()
  private let network = NetworkPathFlag()

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "local-segments-retry-test-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)

    LocalUploadRetryURLStub.reset()
    setenv("OMI_PYTHON_API_URL", "https://local-segments-retry.test/", 1)
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [LocalUploadRetryURLStub.self]
    let client = APIClient(session: URLSession(configuration: config))
    await client.setTestAuthHeader("Bearer test-token")
    let service = ConversationFinalizationService.shared
    await service.setAPIClientForTesting(client)
    let clock = self.clock
    await service.setClockForTesting { clock.now }
    let network = self.network
    await service.setNetworkReachabilityForTesting { await network.isOnline }
  }

  override func tearDown() async throws {
    let service = ConversationFinalizationService.shared
    await service.setAPIClientForTesting(nil)
    await service.setClockForTesting(nil)
    await service.setNetworkReachabilityForTesting(nil)
    unsetenv("OMI_PYTHON_API_URL")
    LocalUploadRetryURLStub.reset()
    await RewindDatabase.shared.close()
    await TranscriptionStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDir {
      try? FileManager.default.removeItem(at: userDir)
    }
    try await super.tearDown()
  }

  // MARK: - State machine

  func testLocalSegmentsSessionOutlivesFiveFailuresAndOfflineThenUploads() async throws {
    let service = ConversationFinalizationService.shared
    let sessionId = try await makeFinishedLocalSession(clientConversationId: "local-retry-recording")

    // Backend brownout: five counted failures, each after its backoff has elapsed.
    LocalUploadRetryURLStub.setMode(.httpStatus(503))
    for attempt in 1...5 {
      clock.setElapsed(2 * 60 * 60)
      await service.recoverPendingFinalizations()
      let session = try await requireSession(sessionId)
      XCTAssertEqual(session.status, .failed, "attempt \(attempt)")
      XCTAssertEqual(session.retryCount, attempt, "attempt \(attempt)")
      XCTAssertFalse(session.backendSynced, "attempt \(attempt)")
    }
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 5)

    let queued = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
    XCTAssertTrue(
      queued.contains { $0.id == sessionId },
      "exhausting the cloud retry budget must not strand the only copy of a local transcript"
    )

    // Backoff still applies after the old budget: no time has passed since the last failure.
    clock.setElapsed(0)
    await service.recoverPendingFinalizations()
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 5)

    // Offline: the reachability gate prevents the attempt entirely.
    await network.set(false)
    LocalUploadRetryURLStub.setMode(.offline)
    clock.setElapsed(2 * 60 * 60)
    await service.recoverPendingFinalizations()
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 5, "no attempt while the path monitor is offline")
    var session = try await requireSession(sessionId)
    XCTAssertEqual(session.retryCount, 5)

    // The path monitor reports a network but requests still cannot leave the machine.
    await network.set(true)
    await service.recoverPendingFinalizations()
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 6)
    session = try await requireSession(sessionId)
    XCTAssertEqual(session.status, .failed)
    XCTAssertEqual(session.retryCount, 5, "offline failures do not spend retry budget")

    // Network recovery: the next due attempt uploads and completes the session.
    LocalUploadRetryURLStub.setMode(.success)
    clock.setElapsed(2 * 60 * 60)
    await service.recoverPendingFinalizations()

    session = try await requireSession(sessionId)
    XCTAssertEqual(session.status, .completed)
    XCTAssertTrue(session.backendSynced)
    XCTAssertEqual(session.backendId, "backend-local-retry-recording")
    XCTAssertEqual(session.retryCount, 0)
    XCTAssertNil(session.lastError)

    let bodies = LocalUploadRetryURLStub.uploadBodies
    XCTAssertEqual(bodies.count, 7)
    for body in bodies {
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      XCTAssertEqual(
        json["client_conversation_id"] as? String,
        "local-retry-recording",
        "every retry must carry the same idempotency key"
      )
    }
  }

  func testPermanentRejectionStaysQueuedAndRetriesHourly() async throws {
    let service = ConversationFinalizationService.shared
    let sessionId = try await makeFinishedLocalSession(clientConversationId: "local-rejected-recording")

    LocalUploadRetryURLStub.setMode(.httpStatus(422))
    await service.recoverPendingFinalizations()

    var session = try await requireSession(sessionId)
    XCTAssertEqual(session.status, .failed)
    XCTAssertEqual(session.retryCount, 1)
    XCTAssertTrue(session.hasPermanentFinalizationFailure)
    XCTAssertEqual(session.retryBackoffSeconds, FinalizationRetryPolicy.maxBackoffSeconds)
    let queued = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
    XCTAssertTrue(queued.contains { $0.id == sessionId }, "rejected uploads stay visible to recovery")

    // A transient failure at retryCount 1 would be due after two minutes; a rejection waits the hour.
    clock.setElapsed(30 * 60)
    await service.recoverPendingFinalizations()
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 1)

    LocalUploadRetryURLStub.setMode(.success)
    clock.setElapsed(FinalizationRetryPolicy.maxBackoffSeconds + 60)
    await service.recoverPendingFinalizations()

    session = try await requireSession(sessionId)
    XCTAssertEqual(session.status, .completed)
    XCTAssertTrue(session.backendSynced)
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 2)
  }

  func testRecoveryQueryPicksUpLocalSessionsStrandedByTheOldBudget() async throws {
    let strandedLocalId = try await makeFinishedLocalSession(clientConversationId: "stranded-local")
    try await failSession(strandedLocalId, times: 9)

    let legacyNullStrategyId = try await makeFinishedLocalSession(clientConversationId: "stranded-legacy")
    try await failSession(legacyNullStrategyId, times: 5)
    let dbQueue = await RewindDatabase.shared.getDatabaseQueue()
    let db = try XCTUnwrap(dbQueue)
    try await db.write { database in
      try database.execute(
        sql: "UPDATE transcription_sessions SET finalizationStrategy = NULL WHERE id = ?",
        arguments: [legacyNullStrategyId]
      )
    }

    let exhaustedCloudId = try await TranscriptionStorage.shared.startSession(
      source: "desktop",
      finalizationStrategy: .cloudReconcile
    )
    try await TranscriptionStorage.shared.finishSession(id: exhaustedCloudId, reason: .userStop)
    try await failSession(exhaustedCloudId, times: 5)

    let pending = try await TranscriptionStorage.shared.getSessionsNeedingFinalization()
    let ids = Set(pending.compactMap(\.id))
    XCTAssertTrue(ids.contains(strandedLocalId))
    XCTAssertTrue(ids.contains(legacyNullStrategyId))
    XCTAssertFalse(ids.contains(exhaustedCloudId), "cloud sessions keep their bounded budget")

    await ConversationFinalizationService.shared.recoverPendingFinalizations()
    // Nothing has elapsed since the stranding writes, so every stranded row waits out its backoff.
    XCTAssertTrue(LocalUploadRetryURLStub.uploadBodies.isEmpty)

    clock.setElapsed(2 * 60 * 60)
    await ConversationFinalizationService.shared.recoverPendingFinalizations()
    let strandedLocal = try await requireSession(strandedLocalId)
    let legacy = try await requireSession(legacyNullStrategyId)
    XCTAssertEqual(strandedLocal.status, .completed)
    XCTAssertEqual(strandedLocal.backendId, "backend-stranded-local")
    XCTAssertEqual(legacy.status, .completed)
    XCTAssertEqual(legacy.backendId, "backend-stranded-legacy")
    XCTAssertEqual(LocalUploadRetryURLStub.uploadBodies.count, 2)
  }

  // MARK: - Policy

  func testFailureClassification() {
    XCTAssertEqual(FinalizationFailureClass.classify(URLError(.notConnectedToInternet)), .offline)
    XCTAssertEqual(FinalizationFailureClass.classify(URLError(.networkConnectionLost)), .offline)
    XCTAssertEqual(FinalizationFailureClass.classify(URLError(.cannotFindHost)), .offline)
    XCTAssertEqual(FinalizationFailureClass.classify(URLError(.timedOut)), .transient)
    XCTAssertEqual(FinalizationFailureClass.classify(APIError.httpError(statusCode: 503)), .transient)
    XCTAssertEqual(FinalizationFailureClass.classify(APIError.httpError(statusCode: 429)), .transient)
    XCTAssertEqual(FinalizationFailureClass.classify(APIError.httpError(statusCode: 401)), .transient)
    XCTAssertEqual(FinalizationFailureClass.classify(APIError.unauthorized), .transient)
    XCTAssertEqual(FinalizationFailureClass.classify(APIError.httpError(statusCode: 400)), .permanent)
    XCTAssertEqual(FinalizationFailureClass.classify(APIError.httpError(statusCode: 422)), .permanent)
    XCTAssertEqual(
      FinalizationFailureClass.classify(TranscriptionStorageError.invalidState("local write rejected")),
      .transient
    )
  }

  func testBackoffIsCappedAtOneHour() {
    let schedule = [0, 1, 2, 3, 4, 5, 6, 7, 50, Int.max].map {
      FinalizationRetryPolicy.backoffSeconds(retryCount: $0, permanentFailure: false)
    }
    XCTAssertEqual(schedule, [60, 120, 240, 480, 960, 1920, 3600, 3600, 3600, 3600])
    XCTAssertEqual(FinalizationRetryPolicy.backoffSeconds(retryCount: 0, permanentFailure: true), 3600)
  }

  func testExhaustedCloudSessionsSkipBackoffButLocalSessionsDoNot() {
    let now = Date()
    let local = TranscriptionSessionRecord(
      source: "desktop",
      status: .failed,
      retryCount: 7,
      updatedAt: now,
      finalizationStrategy: .localSegments
    )
    XCTAssertTrue(local.canRetry)
    XCTAssertFalse(ConversationFinalizationService.isDueForRecovery(local, now: now, maxRetries: 5))
    XCTAssertTrue(
      ConversationFinalizationService.isDueForRecovery(local, now: now.addingTimeInterval(3600), maxRetries: 5)
    )

    let cloud = TranscriptionSessionRecord(
      source: "desktop",
      status: .failed,
      retryCount: 5,
      updatedAt: now,
      finalizationStrategy: .cloudReconcile
    )
    XCTAssertFalse(cloud.canRetry)
    XCTAssertTrue(ConversationFinalizationService.isDueForRecovery(cloud, now: now, maxRetries: 5))
  }

  // MARK: - Helpers

  private func makeFinishedLocalSession(clientConversationId: String) async throws -> Int64 {
    let sessionId = try await TranscriptionStorage.shared.startSession(
      source: "desktop",
      clientConversationId: clientConversationId,
      finalizationStrategy: .localSegments
    )
    try await TranscriptionStorage.shared.appendSegment(
      sessionId: sessionId,
      speaker: 0,
      text: "on-device transcript for \(clientConversationId)",
      startTime: 0,
      endTime: 1
    )
    try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
    return sessionId
  }

  private func failSession(_ sessionId: Int64, times: Int) async throws {
    try await TranscriptionStorage.shared.markSessionFailed(id: sessionId, error: "from-segments failed")
    for _ in 0..<times {
      try await TranscriptionStorage.shared.incrementRetryCount(id: sessionId)
    }
  }

  private func requireSession(_ sessionId: Int64) async throws -> TranscriptionSessionRecord {
    let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
    return try XCTUnwrap(session)
  }
}
