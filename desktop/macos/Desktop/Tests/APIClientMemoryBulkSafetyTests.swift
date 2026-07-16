import XCTest

@testable import Omi_Computer

private struct BulkCapturedRequest {
  let url: URL
  let method: String
  let headers: [String: String]
  let body: Data?
}

private final class BulkURLCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var _requests: [BulkCapturedRequest] = []

  static var capturedRequests: [BulkCapturedRequest] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset() {
    lock.lock()
    _requests.removeAll()
    lock.unlock()
  }

  private static func record(_ request: BulkCapturedRequest) {
    lock.lock()
    _requests.append(request)
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    if let url = request.url {
      BulkURLCapture.record(
        BulkCapturedRequest(
          url: url,
          method: request.httpMethod ?? "GET",
          headers: request.allHTTPHeaderFields ?? [:],
          body: Self.bodyData(from: request)))
    }
    let response = HTTPURLResponse(url: request.url!, statusCode: 500, httpVersion: nil, headerFields: nil)!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Data("{}".utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let httpBody = request.httpBody {
      return httpBody
    }
    guard let stream = request.httpBodyStream else { return nil }

    stream.open()
    defer { stream.close() }

    var data = Data()
    let bufferSize = 4096
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
    defer { buffer.deallocate() }

    while stream.hasBytesAvailable {
      let read = stream.read(buffer, maxLength: bufferSize)
      if read <= 0 { break }
      data.append(buffer, count: read)
    }
    return data
  }
}

private actor FakeImportEvidenceAPI: ImportEvidenceBatchCreating {
  private let outcomes: [Result<ImportEvidenceBatchResponse, Error>]
  private var index = 0
  private var calls = 0
  private var batches: [ImportEvidenceBatch] = []

  init(outcomes: [Result<ImportEvidenceBatchResponse, Error>]) {
    self.outcomes = outcomes
  }

  func createMemoryImportBatch(_ batch: ImportEvidenceBatch) async throws -> ImportEvidenceBatchResponse {
    calls += 1
    batches.append(batch)
    let outcome = outcomes[min(index, outcomes.count - 1)]
    index += 1
    switch outcome {
    case .success(let response):
      return response
    case .failure(let error):
      throw error
    }
  }

  func callCount() -> Int {
    calls
  }

  func capturedBatches() -> [ImportEvidenceBatch] {
    batches
  }
}

private actor FakeMemoryBatchAPI: MemoryBatchCreating {
  private var calls = 0
  private var memories: [MemoryBatchItem] = []

  func createMemoriesBatch(_ memories: [MemoryBatchItem]) async throws -> BatchMemoriesResponse {
    calls += 1
    self.memories.append(contentsOf: memories)
    return BatchMemoriesResponse(
      memories: memories.enumerated().map { index, item in
        BatchMemoriesResponse.BatchMemory(id: "legacy-\(index)", content: item.content)
      },
      createdCount: memories.count
    )
  }

  func callCount() -> Int {
    calls
  }

  func capturedMemories() -> [MemoryBatchItem] {
    memories
  }
}

private actor SleepRecorder {
  private var delays: [UInt64] = []

  func sleep(_ delay: UInt64) async {
    delays.append(delay)
  }

  func recordedDelays() -> [UInt64] {
    delays
  }
}

final class APIClientMemoryBulkSafetyTests: XCTestCase {
  override func setUp() {
    super.setUp()
    BulkURLCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    BulkURLCapture.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [BulkURLCapture.self]
    let session = URLSession(configuration: config)
    let client = APIClient(session: session)
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testDeleteAllMemoriesDefaultScopeUsesUnscopedEndpoint() async {
    let client = await makeClient()

    await XCTAssertThrowsErrorAsync({ try await client.deleteAllMemories(scope: .defaultAccess) }) { error in
      guard case APIError.httpError(let statusCode, _) = error, statusCode == 500 else {
        XCTFail("Expected httpError 500 from captured request, got \(error)")
        return
      }
    }
    XCTAssertEqual(BulkURLCapture.capturedRequests.count, 1)
    XCTAssertEqual(BulkURLCapture.capturedRequests.first?.method, "DELETE")
    XCTAssertEqual(BulkURLCapture.capturedRequests.first?.url.path, "/v3/memories")
  }

  func testUpdateAllMemoriesVisibilityDefaultScopeUsesUnscopedEndpoint() async {
    let client = await makeClient()

    await XCTAssertThrowsErrorAsync({
      try await client.updateAllMemoriesVisibility(scope: .defaultAccess, visibility: "private")
    }) { error in
      guard case APIError.httpError(let statusCode, _) = error, statusCode == 500 else {
        XCTFail("Expected httpError 500 from captured request, got \(error)")
        return
      }
    }
    XCTAssertEqual(BulkURLCapture.capturedRequests.count, 1)
    XCTAssertEqual(BulkURLCapture.capturedRequests.first?.method, "PATCH")
    XCTAssertEqual(BulkURLCapture.capturedRequests.first?.url.path, "/v3/memories/visibility")
  }

  func testMarkAllMemoriesReadScopeThrowsBeforeNetworkRequest() async {
    let client = await makeClient()

    await XCTAssertThrowsErrorAsync({ try await client.markAllMemoriesRead(scope: .defaultAccess) }) { error in
      guard case APIError.unsupportedTierScopedBulkMutation(_) = error else {
        XCTFail("Expected unsupportedTierScopedBulkMutation, got \(error)")
        return
      }
    }
    XCTAssertEqual(BulkURLCapture.capturedRequests.count, 0)
  }

  func testImportEvidenceBatchItemEncodesSourceArtifactMetadata() throws {
    let item = ImportEvidenceBatchItem(
      externalId: "chatgpt:memory:1",
      occurredAt: Date(timeIntervalSince1970: 1_782_950_400.123),
      title: "ChatGPT Memory Import",
      snippet: "The user prefers concise updates.",
      content: "The user prefers concise updates.",
      metadata: ["window_title": "ChatGPT export"]
    )

    let data = try JSONEncoder().encode(item)
    let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

    XCTAssertEqual(object["external_id"] as? String, "chatgpt:memory:1")
    XCTAssertEqual(object["occurred_at"] as? String, "2026-07-02T00:00:00.123Z")
    XCTAssertEqual(object["title"] as? String, "ChatGPT Memory Import")
    XCTAssertEqual(object["snippet"] as? String, "The user prefers concise updates.")
    XCTAssertEqual(object["content"] as? String, "The user prefers concise updates.")
    let metadata = try XCTUnwrap(object["metadata"] as? [String: String])
    XCTAssertEqual(metadata["window_title"], "ChatGPT export")
  }

  func testCreateMemoryImportBatchRoutesOneRequestWithArtifactPayload() async throws {
    let client = await makeClient()
    let item = ImportEvidenceBatchItem(
      externalId: "gmail:m1",
      title: "Omi",
      snippet: "The user works on Omi.",
      content: "The user works on Omi.",
      metadata: ["import_kind": "email"]
    )
    let batch = ImportEvidenceBatch(sourceType: "gmail", items: [item])

    await XCTAssertThrowsErrorAsync({ try await client.createMemoryImportBatch(batch) }) { error in
      guard case APIError.httpError(let statusCode, _) = error, statusCode == 500 else {
        XCTFail("Expected httpError 500, got \(error)")
        return
      }
    }

    let request = try XCTUnwrap(BulkURLCapture.capturedRequests.first)
    XCTAssertEqual(request.method, "POST")
    XCTAssertEqual(request.url.path, "/v3/memory-imports/batch")
    XCTAssertNil(request.headers["X-BYOK-OpenAI"])
    XCTAssertNil(request.headers["X-BYOK-Anthropic"])
    XCTAssertNil(request.headers["X-BYOK-Gemini"])
    XCTAssertNil(request.headers["X-BYOK-Deepgram"])

    let body = try XCTUnwrap(request.body)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(json["source_type"] as? String, "gmail")
    let items = try XCTUnwrap(json["items"] as? [[String: Any]])
    XCTAssertEqual(items.count, 1)
    XCTAssertEqual(items.first?["external_id"] as? String, "gmail:m1")
  }

  func testChunkedUsesMemoryBatchMaxSizeBoundaries() {
    let values = Array(0..<(APIClient.memoriesBatchMaxSize + 2))

    let chunks = values.chunked(maxSize: APIClient.memoriesBatchMaxSize)

    XCTAssertEqual(chunks.count, 2)
    XCTAssertEqual(chunks[0].count, APIClient.memoriesBatchMaxSize)
    XCTAssertEqual(chunks[1], [APIClient.memoriesBatchMaxSize, APIClient.memoriesBatchMaxSize + 1])
  }

  func testOnboardingImportEvidenceRetriesRateLimitedChunk() async {
    let item = ImportEvidenceBatchItem(
      title: "Verification",
      snippet: "The user likes local verification.",
      content: "The user likes local verification.",
      metadata: ["import_kind": "profile"]
    )
    let api = FakeImportEvidenceAPI(
      outcomes: [
        .failure(APIError.httpError(statusCode: 429)),
        .success(
          ImportEvidenceBatchResponse(
            runId: "run1",
            artifactsReceived: 1,
            artifactsCreated: 1,
            artifactsDeduped: 0,
            candidatesCreated: 0,
            status: "received")),
      ])
    let recorder = SleepRecorder()

    let result = await OnboardingImportEvidenceService.save(
      [item],
      sourceType: "test",
      logPrefix: "test",
      importRunId: "test-run-1",
      sourceAccountHash: "source-hash-1",
      apiClient: api,
      sleep: { delay in await recorder.sleep(delay) }
    )

    XCTAssertEqual(result.saved, 1)
    XCTAssertEqual(result.failed, 0)
    let callCount = await api.callCount()
    let delays = await recorder.recordedDelays()
    XCTAssertEqual(callCount, 2)
    XCTAssertEqual(delays, [2])
    let batches = await api.capturedBatches()
    XCTAssertEqual(batches.map(\.importRunId), ["test-run-1", "test-run-1"])
    XCTAssertEqual(batches.map(\.sourceAccountHash), ["source-hash-1", "source-hash-1"])
  }

  func testOnboardingImportEvidenceStampsClientDeviceIdWithoutDefaultSourceAccountHash() async {
    let item = ImportEvidenceBatchItem(
      title: "Device Provenance",
      snippet: "Imports should stamp client_device_id, not source_account_hash.",
      content: "Imports should stamp client_device_id, not source_account_hash.",
      metadata: ["import_kind": "profile"]
    )
    let api = FakeImportEvidenceAPI(
      outcomes: [
        .success(
          ImportEvidenceBatchResponse(
            runId: "run1",
            artifactsReceived: 1,
            artifactsCreated: 1,
            artifactsDeduped: 0,
            candidatesCreated: 0,
            status: "received"))
      ])

    let result = await OnboardingImportEvidenceService.save(
      [item],
      sourceType: "test",
      logPrefix: "test",
      importRunId: "test-run-device",
      apiClient: api,
      sleep: { _ in }
    )

    XCTAssertEqual(result.saved, 1)
    XCTAssertEqual(result.failed, 0)
    let batches = await api.capturedBatches()
    XCTAssertEqual(batches.map(\.sourceAccountHash), [nil])
    XCTAssertEqual(
      batches.flatMap(\.items).map(\.clientDeviceId),
      [ClientDeviceService.shared.clientDeviceId]
    )
  }

  func testOnboardingImportEvidenceRetriesTransientNetworkError() async {
    let item = ImportEvidenceBatchItem(
      title: "Resilient Import",
      snippet: "The user wants resilient onboarding imports.",
      content: "The user wants resilient onboarding imports.",
      metadata: ["import_kind": "profile"]
    )
    let api = FakeImportEvidenceAPI(
      outcomes: [
        .failure(URLError(.timedOut)),
        .success(
          ImportEvidenceBatchResponse(
            runId: "run1",
            artifactsReceived: 1,
            artifactsCreated: 1,
            artifactsDeduped: 0,
            candidatesCreated: 0,
            status: "received")),
      ])
    let recorder = SleepRecorder()

    let result = await OnboardingImportEvidenceService.save(
      [item],
      sourceType: "test",
      logPrefix: "test",
      importRunId: "test-run-2",
      sourceAccountHash: "source-hash-2",
      apiClient: api,
      sleep: { delay in await recorder.sleep(delay) }
    )

    XCTAssertEqual(result.saved, 1)
    XCTAssertEqual(result.failed, 0)
    let callCount = await api.callCount()
    let delays = await recorder.recordedDelays()
    XCTAssertEqual(callCount, 2)
    XCTAssertEqual(delays, [2])
    let batches = await api.capturedBatches()
    XCTAssertEqual(batches.map(\.importRunId), ["test-run-2", "test-run-2"])
    XCTAssertEqual(batches.map(\.sourceAccountHash), ["source-hash-2", "source-hash-2"])
  }

  func testOnboardingImportEvidenceFallsBackToLegacyBatchOnlyForLegacyUsers() async {
    let item = ImportEvidenceBatchItem(
      title: "Legacy Import",
      snippet: "The legacy user keeps legacy memory behavior.",
      content: "The legacy user keeps legacy memory behavior.",
      metadata: ["import_kind": "profile"]
    )
    let legacyMemory = MemoryBatchItem(
      content: "The legacy user keeps legacy memory behavior.",
      tags: ["gmail", "onboarding"],
      headline: "Legacy Import",
      source: "gmail"
    )
    let api = FakeImportEvidenceAPI(
      outcomes: [
        .failure(APIError.httpError(statusCode: 403, detail: "memory_import_requires_canonical"))
      ])
    let legacyApi = FakeMemoryBatchAPI()

    let result = await OnboardingImportEvidenceService.save(
      [item],
      sourceType: "gmail",
      logPrefix: "test",
      importRunId: "test-run-legacy",
      sourceAccountHash: "source-hash-legacy",
      legacyMemories: [legacyMemory],
      apiClient: api,
      legacyApiClient: legacyApi,
      sleep: { _ in }
    )

    XCTAssertEqual(result.saved, 1)
    XCTAssertEqual(result.failed, 0)
    let importCallCount = await api.callCount()
    let legacyCallCount = await legacyApi.callCount()
    let legacyContents = await legacyApi.capturedMemories().map(\.content)
    XCTAssertEqual(importCallCount, 1)
    XCTAssertEqual(legacyCallCount, 1)
    XCTAssertEqual(legacyContents, [legacyMemory.content])
  }

  func testOnboardingImportEvidenceFallsBackToLegacyBatchWhenEndpointMissing() async {
    // Deployments without the canonical import router (prod today) 404
    // /v3/memory-imports/batch; the scan context must still reach the
    // legacy batch path instead of being silently dropped.
    let item = ImportEvidenceBatchItem(
      title: "Missing Endpoint",
      snippet: "The user works on a local project named foo.",
      content: "The user works on a local project named foo.",
      metadata: ["import_kind": "local_file_profile"]
    )
    let legacyMemory = MemoryBatchItem(
      content: "The user works on a local project named foo.",
      tags: ["local_files", "onboarding", "project"],
      headline: "foo",
      source: "local_files"
    )
    let api = FakeImportEvidenceAPI(
      outcomes: [
        .failure(APIError.httpError(statusCode: 404, detail: "Not Found"))
      ])
    let legacyApi = FakeMemoryBatchAPI()

    let result = await OnboardingImportEvidenceService.save(
      [item],
      sourceType: "local_files",
      logPrefix: "test",
      importRunId: "test-run-missing-endpoint",
      sourceAccountHash: nil,
      legacyMemories: [legacyMemory],
      apiClient: api,
      legacyApiClient: legacyApi,
      sleep: { _ in }
    )

    XCTAssertEqual(result.saved, 1)
    XCTAssertEqual(result.failed, 0)
    let legacyCallCount = await legacyApi.callCount()
    XCTAssertEqual(legacyCallCount, 1)
  }

  func testOnboardingImportEvidenceDoesNotFallbackWhenCanonicalNotReady() async {
    let item = ImportEvidenceBatchItem(
      title: "Canonical Not Ready",
      snippet: "Canonical failures should fail closed.",
      content: "Canonical failures should fail closed.",
      metadata: ["import_kind": "profile"]
    )
    let legacyMemory = MemoryBatchItem(content: "Should not write legacy")
    let api = FakeImportEvidenceAPI(
      outcomes: [
        .failure(APIError.httpError(statusCode: 503, detail: "memory_import_canonical_not_ready"))
      ])
    let legacyApi = FakeMemoryBatchAPI()

    let result = await OnboardingImportEvidenceService.save(
      [item],
      sourceType: "gmail",
      logPrefix: "test",
      importRunId: "test-run-not-ready",
      sourceAccountHash: "source-hash-not-ready",
      legacyMemories: [legacyMemory],
      apiClient: api,
      legacyApiClient: legacyApi,
      sleep: { _ in }
    )

    XCTAssertEqual(result.saved, 0)
    XCTAssertEqual(result.failed, 1)
    let legacyCallCount = await legacyApi.callCount()
    XCTAssertEqual(legacyCallCount, 0)
  }
}

private func XCTAssertThrowsErrorAsync<T>(
  _ expression: () async throws -> T,
  _ errorHandler: (Error) -> Void,
  file: StaticString = #filePath,
  line: UInt = #line
) async {
  do {
    _ = try await expression()
    XCTFail("Expected async expression to throw", file: file, line: line)
  } catch {
    errorHandler(error)
  }
}
