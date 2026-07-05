import XCTest
@testable import Omi_Computer

private final class MemoryLifecycleURLStub: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var _headers: [String: String] = [:]

    static var headers: [String: String] {
        get {
            lock.lock()
            defer { lock.unlock() }
            return _headers
        }
        set {
            lock.lock()
            _headers = newValue
            lock.unlock()
        }
    }

    static func reset() {
        headers = [:]
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: Self.headers
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("[]".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

final class APIClientMemoryLifecycleHeaderTests: XCTestCase {
    override func setUp() {
        super.setUp()
        MemoryLifecycleURLStub.reset()
        setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
    }

    override func tearDown() {
        unsetenv("OMI_PYTHON_API_URL")
        MemoryLifecycleURLStub.reset()
        super.tearDown()
    }

    private func makeClient() async -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MemoryLifecycleURLStub.self]
        let session = URLSession(configuration: config)
        let client = APIClient(session: session)
        await client.setTestAuthHeader("Bearer test-token")
        return client
    }

    func testExplicitLifecycleHeaderTrueExposesCanonicalLifecycle() async throws {
        MemoryLifecycleURLStub.headers = [
            "X-Omi-Memory-Canonical-Lifecycle-Exposed": "true",
            "X-Omi-Memory-Device-Scope-Supported": "false",
        ]
        let client = await makeClient()

        let page = try await client.getMemoriesPage()

        XCTAssertTrue(page.canonicalLifecycleExposed)
        XCTAssertEqual(page.deviceScopeSupported, false)
    }

    func testDeviceScopeHeaderAloneDoesNotExposeCanonicalLifecycle() async throws {
        MemoryLifecycleURLStub.headers = [
            "X-Omi-Memory-Device-Scope-Supported": "true"
        ]
        let client = await makeClient()

        let page = try await client.getMemoriesPage()

        XCTAssertFalse(page.canonicalLifecycleExposed)
        XCTAssertEqual(page.deviceScopeSupported, true)
    }

    func testLifecycleHeaderMustBeLiteralLowercaseTrue() async throws {
        MemoryLifecycleURLStub.headers = [
            "X-Omi-Memory-Canonical-Lifecycle-Exposed": "True",
            "X-Omi-Memory-Device-Scope-Supported": "true",
        ]
        let client = await makeClient()

        let page = try await client.getMemoriesPage()

        XCTAssertFalse(page.canonicalLifecycleExposed)
        XCTAssertEqual(page.deviceScopeSupported, true)
    }
}
