import Foundation
import XCTest

@testable import Omi_Computer

private struct LocalProjectionRequest {
  let url: URL
  let method: String
  let body: Data?
}

private final class LocalProjectionURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _requests: [LocalProjectionRequest] = []
  private nonisolated(unsafe) static var _fromSegmentsFailuresRemaining = 0

  static var requests: [LocalProjectionRequest] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset() {
    lock.lock()
    _requests.removeAll()
    _fromSegmentsFailuresRemaining = 0
    lock.unlock()
  }

  static func failNextFromSegments(_ count: Int) {
    lock.lock()
    _fromSegmentsFailuresRemaining = count
    lock.unlock()
  }

  private static func consumeFromSegmentsFailure() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    guard _fromSegmentsFailuresRemaining > 0 else { return false }
    _fromSegmentsFailuresRemaining -= 1
    return true
  }

  private static func record(_ request: LocalProjectionRequest) {
    lock.lock()
    _requests.append(request)
    lock.unlock()
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
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let readCount = stream.read(buffer, maxLength: 4096)
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
    Self.record(
      LocalProjectionRequest(
        url: url,
        method: request.httpMethod ?? "GET",
        body: Self.bodyData(from: request)
      ))

    let path = url.path
    if path == "/v1/conversations/from-segments" {
      if Self.consumeFromSegmentsFailure() {
        guard let response = HTTPURLResponse(url: url, statusCode: 500, httpVersion: nil, headerFields: nil) else {
          return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(#"{"detail":"transient"}"#.utf8))
        client?.urlProtocolDidFinishLoading(self)
        return
      }
      guard let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil) else {
        return
      }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(
        self,
        didLoad: Data(#"{"id":"s11-conversation","status":"processing","discarded":false}"#.utf8)
      )
    } else if path == "/v1/conversations/s11-conversation" {
      guard let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil) else {
        return
      }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(
        self,
        didLoad: Data(
          """
          {
            "id": "s11-conversation",
            "created_at": "2026-09-06T10:00:00Z",
            "started_at": "2026-09-06T10:00:00Z",
            "finished_at": "2026-09-06T10:01:00Z",
            "structured": {
              "title": "S11 hydrated",
              "overview": "Hydrated overview",
              "emoji": "",
              "category": "other",
              "action_items": [],
              "events": []
            },
            "status": "completed",
            "source": "desktop",
            "discarded": false,
            "deleted": false,
            "starred": false,
            "deferred": false
          }
          """.utf8
        )
      )
    } else {
      guard let response = HTTPURLResponse(url: url, statusCode: 404, httpVersion: nil, headerFields: nil) else {
        return
      }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: Data(#"{"detail":"not found"}"#.utf8))
    }
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

#if DEBUG
  final class ConversationFinalizationLocalProjectionTests: XCTestCase {
    private var testUserId = ""
    private var userDir: URL?

    override func setUp() async throws {
      try await super.setUp()
      testUserId = "s11-finalization-\(UUID().uuidString)"
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      RewindDatabase.currentUserId = testUserId
      await RewindDatabase.shared.configure(userId: testUserId)
      try await RewindDatabase.shared.initialize()

      let appSupport = try XCTUnwrap(
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      )
      userDir =
        appSupport
        .appendingPathComponent("Omi", isDirectory: true)
        .appendingPathComponent(testUserId, isDirectory: true)
    }

    override func tearDown() async throws {
      await ConversationFinalizationService.shared.setLocalProjectionHooksForTesting(nil)
      await ConversationFinalizationService.shared.setAPIClientForTesting(nil)
      LocalProjectionURLStub.reset()
      unsetenv("OMI_PYTHON_API_URL")
      unsetenv(LocalInferenceKillSwitches.disableEnvironmentKey)
      await RewindDatabase.shared.close()
      await TranscriptionStorage.shared.invalidateCache()
      RewindDatabase.currentUserId = nil
      if let userDir {
        try? FileManager.default.removeItem(at: userDir)
      }
      try await super.tearDown()
    }

    func testPaidPlanDoesNotAttachOrCallSummarizer() async throws {
      let engine = DraftProjectionEngine(
        generateResults: [.success(LocalSummaryDraft(title: "must not run"))]
      )
      let summarizer = CountingSummarizer(makeSummarizer(engine: engine))
      try await finalizeLocalSession(
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .allowManagedProactivity,
          thermalState: .nominal,
          summarizer: summarizer
        )
      )

      let json = try firstFromSegmentsJSON()
      let summarizeCalls = summarizer.summarizeCalls
      XCTAssertNil(json["client_processing"])
      XCTAssertEqual(summarizeCalls, 0)
      XCTAssertEqual(engine.generateCallCount, 0)
    }

    func testIdentifiedBasicAttachesLocalProjection() async throws {
      let engine = DraftProjectionEngine(
        generateResults: [.success(LocalSummaryDraft(title: "On-device title", overview: "Local overview."))]
      )
      try await finalizeLocalSession(
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .planGated,
          thermalState: .nominal,
          summarizer: makeSummarizer(engine: engine)
        )
      )

      let projection = try firstClientProcessing()
      XCTAssertEqual(projection.structure.title, "On-device title")
      XCTAssertEqual(projection.provenance.runtime, "local")
      XCTAssertEqual(engine.generateCallCount, 1)
    }

    func testRetrySendsStoredProjectionWithoutRegenerating() async throws {
      let engine = DraftProjectionEngine(
        generateResults: [
          .success(LocalSummaryDraft(title: "First pass", overview: "Keep this.")),
          .success(LocalSummaryDraft(title: "Must not run")),
        ]
      )
      let summarizer = CountingSummarizer(makeSummarizer(engine: engine))
      let sessionId = try await startLocalSession(text: "We decided to ship S11 today.")
      await installClient(
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .planGated,
          thermalState: .nominal,
          summarizer: summarizer
        ))
      LocalProjectionURLStub.failNextFromSegments(1)

      await ConversationFinalizationService.shared.finalizeSession(id: sessionId, reason: .userStop)
      await ConversationFinalizationService.shared.finalizeSession(id: sessionId, reason: .retry)

      let posts = LocalProjectionURLStub.requests.filter {
        $0.method == "POST" && $0.url.path == "/v1/conversations/from-segments"
      }
      XCTAssertEqual(posts.count, 2)
      let first = try clientProcessing(from: try XCTUnwrap(posts[0].body))
      let second = try clientProcessing(from: try XCTUnwrap(posts[1].body))
      XCTAssertEqual(first.provenance.generatedAt, second.provenance.generatedAt)
      XCTAssertEqual(first.structure.title, "First pass")
      XCTAssertEqual(second.structure.title, "First pass")
      XCTAssertEqual(summarizer.summarizeCalls, 2)
      XCTAssertEqual(engine.generateCallCount, 1, "retry must send the stored blob, never regenerate")

      let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
      let session = try XCTUnwrap(storedSession)
      XCTAssertEqual(session.status, .completed)
    }

    func testForcedEngineFailureStillUploadsDeterministicProjection() async throws {
      let local = DraftProjectionEngine(
        generateResults: [
          .failure(LocalInferenceError.engineFailed("forced failure")),
          .failure(LocalInferenceError.engineFailed("forced failure")),
        ]
      )
      let cloud = DraftProjectionEngine(
        engineID: .afm,
        generateResults: [.success(LocalSummaryDraft(title: "cloud should never run"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local, cloud],
        killSwitches: .enabled,
        fallback: DesktopLocalInferenceFallbackRecorder(),
        defaultEngineID: .localServer
      )
      let summarizer = ConversationChunkSummarizer(
        runtime: runtime,
        store: MemoryLocalProjectionStore(),
        now: { Date(timeIntervalSince1970: 1_704_140_040) },
        deviceClass: "macos",
        sourceLabel: "Recording",
        timeZone: TimeZone.gmt
      )
      let sessionId = try await finalizeLocalSession(
        text: "We decided to ship the local runtime today. Extra sentence.",
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .planGated,
          thermalState: .nominal,
          summarizer: summarizer
        )
      )

      let projection = try firstClientProcessing()
      XCTAssertEqual(projection.provenance.runtime, "deterministic")
      XCTAssertEqual(local.generateCallCount, 2)
      XCTAssertEqual(cloud.generateCallCount, 0)
      let storedSession = try await TranscriptionStorage.shared.getSession(id: sessionId)
      let session = try XCTUnwrap(storedSession)
      XCTAssertEqual(session.status, .completed)
      let posts = LocalProjectionURLStub.requests.filter {
        $0.method == "POST" && $0.url.path == "/v1/conversations/from-segments"
      }
      XCTAssertEqual(posts.count, 1)
    }

    func testThermalSeriousWithoutStoredProjectionUploadsSegmentsOnly() async throws {
      let engine = DraftProjectionEngine(
        generateResults: [.success(LocalSummaryDraft(title: "must not run"))]
      )
      let summarizer = CountingSummarizer(makeSummarizer(engine: engine))
      try await finalizeLocalSession(
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .planGated,
          thermalState: .serious,
          summarizer: summarizer
        )
      )

      let json = try firstFromSegmentsJSON()
      XCTAssertNil(json["client_processing"])
      XCTAssertEqual(summarizer.summarizeCalls, 0)
      XCTAssertEqual(summarizer.peekCalls, 1)
      XCTAssertEqual(engine.generateCallCount, 0)
    }

    func testEmptySessionStillDeletedWhenFlagOn() async throws {
      let engine = DraftProjectionEngine(
        generateResults: [.success(LocalSummaryDraft(title: "must not run"))]
      )
      let summarizer = CountingSummarizer(makeSummarizer(engine: engine))
      await installClient(
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .planGated,
          thermalState: .nominal,
          summarizer: summarizer
        ))
      let sessionId = try await TranscriptionStorage.shared.startSession(
        source: "desktop",
        finalizationStrategy: .localSegments
      )
      try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)

      await ConversationFinalizationService.shared.finalizeSession(id: sessionId, reason: .userStop)

      let session = try await TranscriptionStorage.shared.getSession(id: sessionId)
      XCTAssertNil(session)
      XCTAssertEqual(summarizer.summarizeCalls, 0)
      XCTAssertTrue(
        LocalProjectionURLStub.requests.filter { $0.url.path == "/v1/conversations/from-segments" }.isEmpty
      )
    }

    func testProductionPathAttachesDeterministicMinimumWhenLocalInferenceDisabled() async throws {
      setenv(LocalInferenceKillSwitches.disableEnvironmentKey, "1", 1)
      try await finalizeLocalSession(
        hooks: LocalProjectionTestHooks(
          flagEnabled: true,
          entitlement: .planGated,
          thermalState: .nominal,
          summarizer: nil
        )
      )

      let projection = try firstClientProcessing()
      XCTAssertEqual(projection.provenance.runtime, "deterministic")
      XCTAssertEqual(projection.provenance.modelId, ClientProcessingContract.deterministicModelID)
    }

    @discardableResult
    private func finalizeLocalSession(
      text: String = "S11 finalization fixture",
      hooks: LocalProjectionTestHooks
    ) async throws -> Int64 {
      let sessionId = try await startLocalSession(text: text)
      await installClient(hooks: hooks)
      await ConversationFinalizationService.shared.finalizeSession(id: sessionId, reason: .userStop)
      return sessionId
    }

    private func startLocalSession(text: String) async throws -> Int64 {
      let sessionId = try await TranscriptionStorage.shared.startSession(
        source: "desktop",
        clientConversationId: "s11-\(UUID().uuidString)",
        finalizationStrategy: .localSegments
      )
      try await TranscriptionStorage.shared.appendSegment(
        sessionId: sessionId,
        speaker: 0,
        text: text,
        startTime: 0,
        endTime: 1
      )
      try await TranscriptionStorage.shared.finishSession(id: sessionId, reason: .userStop)
      return sessionId
    }

    private func installClient(hooks: LocalProjectionTestHooks) async {
      LocalProjectionURLStub.reset()
      setenv("OMI_PYTHON_API_URL", "https://s11-finalization.test/", 1)
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [LocalProjectionURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.setTestAuthHeader("Bearer test-token")
      await ConversationFinalizationService.shared.setAPIClientForTesting(client)
      await ConversationFinalizationService.shared.setLocalProjectionHooksForTesting(hooks)
    }

    private func firstFromSegmentsJSON() throws -> [String: Any] {
      let body = try XCTUnwrap(
        LocalProjectionURLStub.requests.first(where: {
          $0.method == "POST" && $0.url.path == "/v1/conversations/from-segments"
        })?.body
      )
      return try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    }

    private func firstClientProcessing() throws -> OmiAPI.ClientProcessing {
      try clientProcessing(
        from: try XCTUnwrap(
          LocalProjectionURLStub.requests.first(where: {
            $0.method == "POST" && $0.url.path == "/v1/conversations/from-segments"
          })?.body
        ))
    }

    private func clientProcessing(from body: Data) throws -> OmiAPI.ClientProcessing {
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      let raw = try XCTUnwrap(json["client_processing"])
      let data = try JSONSerialization.data(withJSONObject: raw)
      return try ClientProcessingContract.decode(data)
    }

    private func makeSummarizer(engine: DraftProjectionEngine) -> ConversationChunkSummarizer {
      ConversationChunkSummarizer(
        runtime: LocalInferenceRuntime(
          engines: [engine],
          killSwitches: .enabled,
          fallback: DesktopLocalInferenceFallbackRecorder(),
          defaultEngineID: .localServer
        ),
        store: MemoryLocalProjectionStore(),
        now: { Date(timeIntervalSince1970: 1_704_140_040) },
        deviceClass: "macos",
        sourceLabel: "Recording",
        timeZone: TimeZone.gmt
      )
    }
  }

  private final class DraftProjectionEngine: LocalInferenceService, @unchecked Sendable {
    let engineID: LocalInferenceEngineID
    let capabilities: LocalInferenceCapabilities
    private let lock = NSLock()
    private var generateResults: [Result<LocalSummaryDraft, Error>]
    private(set) var generateCallCount = 0

    init(
      engineID: LocalInferenceEngineID = .localServer,
      generateResults: [Result<LocalSummaryDraft, Error>]
    ) {
      self.engineID = engineID
      self.capabilities = LocalInferenceCapabilities(
        structuredOutput: true,
        toolLoop: false,
        contextWindowTokens: 8192
      )
      self.generateResults = generateResults
    }

    func generateStructured<T: Decodable>(prompt _: String, schema _: LocalInferenceJSONSchema) async throws -> T {
      let result: Result<LocalSummaryDraft, Error> = lock.withLock {
        generateCallCount += 1
        if generateResults.isEmpty {
          return .success(LocalSummaryDraft(title: "chunk-\(generateCallCount)", overview: "ok"))
        }
        return generateResults.removeFirst()
      }
      let draft = try result.get()
      return try JSONDecoder().decode(T.self, from: JSONEncoder().encode(draft))
    }

    func runToolLoop(prompt _: String, tools _: [LocalInferenceToolSpec], budget _: ToolLoopBudget) async throws
      -> ToolLoopResult
    {
      throw LocalInferenceError.capabilityUnavailable("tool_loop")
    }
  }

  private final class CountingSummarizer: ConversationSummarizing, @unchecked Sendable {
    private let lock = NSLock()
    private let inner: ConversationChunkSummarizer
    private var _summarizeCalls = 0
    private var _peekCalls = 0

    var summarizeCalls: Int {
      lock.lock()
      defer { lock.unlock() }
      return _summarizeCalls
    }

    var peekCalls: Int {
      lock.lock()
      defer { lock.unlock() }
      return _peekCalls
    }

    init(_ inner: ConversationChunkSummarizer) {
      self.inner = inner
    }

    func summarize(
      sessionId: Int64,
      segments: [TranscriptHash.Segment],
      startedAt: Date
    ) async throws -> StoredClientProjection {
      lock.withLock { _summarizeCalls += 1 }
      return try await inner.summarize(sessionId: sessionId, segments: segments, startedAt: startedAt)
    }

    func peekStored(sessionId: Int64) async throws -> StoredClientProjection? {
      lock.withLock { _peekCalls += 1 }
      return try await inner.peekStored(sessionId: sessionId)
    }
  }
#endif
