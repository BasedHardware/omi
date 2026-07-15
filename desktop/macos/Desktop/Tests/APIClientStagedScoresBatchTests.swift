import XCTest
@testable import Omi_Computer

private struct StagedScoresCapturedRequest {
    let url: URL
    let method: String
    let body: Data?
}

private final class StagedScoresURLCapture: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var _requests: [StagedScoresCapturedRequest] = []

    /// Request ordinal (0-based) -> HTTP status to return. Missing = 200.
    static var failStatusForRequestIndex: [Int: Int] = [:]

    static var capturedRequests: [StagedScoresCapturedRequest] {
        lock.lock()
        defer { lock.unlock() }
        return _requests
    }

    static func reset() {
        lock.lock()
        _requests.removeAll()
        failStatusForRequestIndex.removeAll()
        lock.unlock()
    }

    private static func record(_ request: StagedScoresCapturedRequest) -> Int {
        lock.lock()
        defer { lock.unlock() }
        _requests.append(request)
        return _requests.count - 1
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        var index = 0
        if request.url != nil {
            index = StagedScoresURLCapture.record(
                StagedScoresCapturedRequest(
                    url: request.url!,
                    method: request.httpMethod ?? "GET",
                    body: Self.bodyData(from: request)))
        }
        let status = StagedScoresURLCapture.failStatusForRequestIndex[index] ?? 200
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data((status == 200 ? "{\"status\":\"ok\"}" : "{}").utf8))
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
        let bufferSize = 65536
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

/// Regression coverage for #9814: desktop scored up to 10,000 staged tasks but
/// sent every score in one request, exceeding the backend `scores` cap of 500
/// (HTTP 422). Scores must now split into ordered requests of at most 500.
final class APIClientStagedScoresBatchTests: XCTestCase {
    override func setUp() {
        super.setUp()
        StagedScoresURLCapture.reset()
        setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    }

    override func tearDown() {
        unsetenv("OMI_PYTHON_API_URL")
        StagedScoresURLCapture.reset()
        super.tearDown()
    }

    private func makeClient() async -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StagedScoresURLCapture.self]
        let session = URLSession(configuration: config)
        let client = APIClient(session: session)
        await client.setTestAuthHeader("Bearer test-token")
        return client
    }

    private func scoreEntryCount(_ request: StagedScoresCapturedRequest) throws -> Int {
        let body = try XCTUnwrap(request.body)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        let entries = try XCTUnwrap(json["scores"] as? [[String: Any]])
        return entries.count
    }

    func testBatchUpdateStagedScoresSplitsAtBackendCap() async throws {
        let client = await makeClient()
        let scores = (0..<(APIClient.stagedScoresBatchMaxSize + 1)).map { (id: "task-\($0)", score: $0) }

        try await client.batchUpdateStagedScores(scores)

        let requests = StagedScoresURLCapture.capturedRequests
        XCTAssertEqual(requests.count, 2, "501 scores should produce 500 + 1 requests")
        XCTAssertTrue(requests.allSatisfy { $0.method == "PATCH" })
        XCTAssertTrue(requests.allSatisfy { $0.url.path == "/v1/staged-tasks/batch-scores" })

        let counts = try requests.map { try scoreEntryCount($0) }
        XCTAssertEqual(counts, [APIClient.stagedScoresBatchMaxSize, 1])
    }

    func testBatchUpdateStagedScoresSendsNoRequestForEmptyInput() async throws {
        let client = await makeClient()

        try await client.batchUpdateStagedScores([])

        XCTAssertEqual(StagedScoresURLCapture.capturedRequests.count, 0)
    }

    func testBatchUpdateStagedScoresFailsFastWhenABatchIsRejected() async throws {
        let client = await makeClient()
        // Reject the second batch; the third must never be sent.
        StagedScoresURLCapture.failStatusForRequestIndex = [1: 422]
        let scores = (0..<(APIClient.stagedScoresBatchMaxSize * 2 + 1)).map { (id: "task-\($0)", score: $0) }

        await XCTAssertThrowsErrorAsync({ try await client.batchUpdateStagedScores(scores) }) { error in
            guard case let APIError.httpError(statusCode, _) = error, statusCode == 422 else {
                XCTFail("Expected httpError 422, got \(error)")
                return
            }
        }

        XCTAssertEqual(
            StagedScoresURLCapture.capturedRequests.count, 2,
            "Fail-fast: the third batch must not be sent after the second is rejected")
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
