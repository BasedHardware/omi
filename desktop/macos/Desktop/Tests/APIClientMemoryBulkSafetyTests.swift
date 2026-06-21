import XCTest
@testable import Omi_Computer

private struct BulkCapturedRequest {
    let url: URL
    let method: String
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
            BulkURLCapture.record(BulkCapturedRequest(url: url, method: request.httpMethod ?? "GET"))
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 500, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
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
