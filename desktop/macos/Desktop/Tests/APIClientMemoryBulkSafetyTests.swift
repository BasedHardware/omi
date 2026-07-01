import XCTest
@testable import Omi_Computer

private struct BulkCapturedRequest {
    let url: URL
    let method: String
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
                BulkCapturedRequest(url: url, method: request.httpMethod ?? "GET", body: Self.bodyData(from: request)))
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

private actor FakeMemoryBatchAPI: MemoryBatchCreating {
    private let outcomes: [Result<BatchMemoriesResponse, Error>]
    private var index = 0
    private var calls = 0

    init(outcomes: [Result<BatchMemoriesResponse, Error>]) {
        self.outcomes = outcomes
    }

    func createMemoriesBatch(_ memories: [MemoryBatchItem]) async throws -> BatchMemoriesResponse {
        calls += 1
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

    func testDeleteAllMemoriesScopeThrowsBeforeNetworkRequest() async {
        let client = await makeClient()

        await XCTAssertThrowsErrorAsync({ try await client.deleteAllMemories(scope: .defaultAccess) }) { error in
            guard case APIError.unsupportedTierScopedBulkMutation(_) = error else {
                XCTFail("Expected unsupportedTierScopedBulkMutation, got \(error)")
                return
            }
        }
        XCTAssertEqual(BulkURLCapture.capturedRequests.count, 0)
    }

    func testUpdateAllMemoriesVisibilityScopeThrowsBeforeNetworkRequest() async {
        let client = await makeClient()

        await XCTAssertThrowsErrorAsync({
            try await client.updateAllMemoriesVisibility(scope: .defaultAccess, visibility: "private")
        }) { error in
            guard case APIError.unsupportedTierScopedBulkMutation(_) = error else {
                XCTFail("Expected unsupportedTierScopedBulkMutation, got \(error)")
                return
            }
        }
        XCTAssertEqual(BulkURLCapture.capturedRequests.count, 0)
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

    func testMemoryBatchItemEncodesImportMetadata() throws {
        let item = MemoryBatchItem(
            content: "The user prefers concise updates.",
            visibility: "private",
            category: .system,
            tags: ["chatgpt", "import"],
            headline: "ChatGPT Memory Import",
            source: "chatgpt_memory_log",
            windowTitle: "ChatGPT export"
        )

        let data = try JSONEncoder().encode(item)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertEqual(object["content"] as? String, "The user prefers concise updates.")
        XCTAssertEqual(object["category"] as? String, "system")
        XCTAssertEqual(object["source"] as? String, "chatgpt_memory_log")
        XCTAssertEqual(object["window_title"] as? String, "ChatGPT export")
        XCTAssertNil(object["windowTitle"])
    }

    func testCreateMemoriesBatchRoutesOneRequestWithChunkPayload() async throws {
        let client = await makeClient()
        let item = MemoryBatchItem(
            content: "The user works on Omi.",
            visibility: "private",
            category: .system,
            tags: ["import"],
            headline: "Omi",
            source: "test"
        )

        await XCTAssertThrowsErrorAsync({ try await client.createMemoriesBatch([item]) }) { error in
            guard case let APIError.httpError(statusCode, _) = error, statusCode == 500 else {
                XCTFail("Expected httpError 500, got \(error)")
                return
            }
        }

        let request = try XCTUnwrap(BulkURLCapture.capturedRequests.first)
        XCTAssertEqual(request.method, "POST")
        XCTAssertEqual(request.url.path, "/v3/memories/batch")

        let body = try XCTUnwrap(request.body)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        let memories = try XCTUnwrap(json["memories"] as? [[String: Any]])
        XCTAssertEqual(memories.count, 1)
        XCTAssertEqual(memories.first?["source"] as? String, "test")
    }

    func testChunkedUsesMemoryBatchMaxSizeBoundaries() {
        let values = Array(0..<(APIClient.memoriesBatchMaxSize + 2))

        let chunks = values.chunked(maxSize: APIClient.memoriesBatchMaxSize)

        XCTAssertEqual(chunks.count, 2)
        XCTAssertEqual(chunks[0].count, APIClient.memoriesBatchMaxSize)
        XCTAssertEqual(chunks[1], [APIClient.memoriesBatchMaxSize, APIClient.memoriesBatchMaxSize + 1])
    }

    func testOnboardingMemoryBatchImportRetriesRateLimitedChunk() async {
        let item = MemoryBatchItem(
            content: "The user likes local verification.",
            visibility: "private",
            category: .system,
            tags: ["import"],
            headline: "Verification",
            source: "test"
        )
        let api = FakeMemoryBatchAPI(
            outcomes: [
                .failure(APIError.httpError(statusCode: 429)),
                .success(BatchMemoriesResponse(memories: [], createdCount: 1)),
            ])
        let recorder = SleepRecorder()

        let result = await OnboardingMemoryBatchImportService.save(
            [item],
            logPrefix: "test",
            apiClient: api,
            sleep: { delay in await recorder.sleep(delay) }
        )

        XCTAssertEqual(result.saved, 1)
        XCTAssertEqual(result.failed, 0)
        let callCount = await api.callCount()
        let delays = await recorder.recordedDelays()
        XCTAssertEqual(callCount, 2)
        XCTAssertEqual(delays, [2])
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
