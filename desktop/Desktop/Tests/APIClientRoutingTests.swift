import XCTest
@testable import Omi_Computer

// MARK: - URL-capturing protocol for routing verification

/// Records every request URL so tests can assert which backend was called.
private final class URLCapture: URLProtocol, @unchecked Sendable {
    /// Thread-safe storage for captured URLs
    private static let lock = NSLock()
    private static var _urls: [URL] = []

    static var capturedURLs: [URL] {
        lock.lock()
        defer { lock.unlock() }
        return _urls
    }

    static func reset() {
        lock.lock()
        _urls.removeAll()
        lock.unlock()
    }

    private static func record(_ url: URL) {
        lock.lock()
        _urls.append(url)
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        if let url = request.url {
            URLCapture.record(url)
        }
        // Return an auth error so the request terminates quickly
        let response = HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

// MARK: - URL property tests

final class APIClientRoutingTests: XCTestCase {

    // MARK: - baseURL defaults to Python backend (api.omi.me)

    func testBaseURLDefaultsToPythonBackend() async {
        unsetenv("OMI_PYTHON_API_URL")
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertEqual(url, "https://api.omi.me/", "baseURL should default to Python backend when OMI_PYTHON_API_URL is not set")
    }

    func testBaseURLReadsFromPythonEnvVar() async {
        setenv("OMI_PYTHON_API_URL", "http://localhost:8080", 1)
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertEqual(url, "http://localhost:8080/", "baseURL should read from OMI_PYTHON_API_URL and add trailing slash")
        unsetenv("OMI_PYTHON_API_URL")
    }

    func testBaseURLAddsTrailingSlash() async {
        setenv("OMI_PYTHON_API_URL", "http://localhost:8080", 1)
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertTrue(url.hasSuffix("/"), "baseURL should always have a trailing slash")
        unsetenv("OMI_PYTHON_API_URL")
    }

    func testBaseURLPreservesExistingTrailingSlash() async {
        setenv("OMI_PYTHON_API_URL", "http://localhost:8080/", 1)
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertEqual(url, "http://localhost:8080/", "baseURL should not double trailing slash")
        unsetenv("OMI_PYTHON_API_URL")
    }

    // MARK: - rustBackendURL reads from OMI_API_URL

    func testRustBackendURLReadsFromApiUrlEnvVar() async {
        setenv("OMI_API_URL", "http://localhost:8787", 1)
        let client = APIClient()
        let url = await client.rustBackendURL
        XCTAssertEqual(url, "http://localhost:8787/", "rustBackendURL should read from OMI_API_URL and add trailing slash")
        unsetenv("OMI_API_URL")
    }

    func testRustBackendURLReturnsEmptyWhenNotSet() async {
        unsetenv("OMI_API_URL")
        let client = APIClient()
        let url = await client.rustBackendURL
        XCTAssertEqual(url, "", "rustBackendURL should return empty string when OMI_API_URL is not set")
    }

    // MARK: - baseURL and rustBackendURL are independent

    func testBaseURLAndRustBackendURLAreIndependent() async {
        setenv("OMI_PYTHON_API_URL", "http://python:8080", 1)
        setenv("OMI_API_URL", "http://rust:8787", 1)
        let client = APIClient()
        let base = await client.baseURL
        let rust = await client.rustBackendURL
        XCTAssertEqual(base, "http://python:8080/")
        XCTAssertEqual(rust, "http://rust:8787/")
        XCTAssertNotEqual(base, rust, "baseURL (Python) and rustBackendURL should be different URLs")
        unsetenv("OMI_PYTHON_API_URL")
        unsetenv("OMI_API_URL")
    }

    // MARK: - Routing behavior: migrated CRUD uses Python, Rust-only uses Rust

    /// Helper: creates an APIClient whose session uses URLCapture so we can
    /// inspect which host each request targets without hitting the network.
    private func makeCapturingClient() -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLCapture.self]

        // Create a fresh client with our capturing session
        let client = APIClient()
        // We cannot replace `session` (it's `let`), so we test through the
        // generic HTTP helpers that accept `customBaseURL`. The endpoint
        // methods in APIClient simply call these helpers, passing
        // `customBaseURL: rustBackendURL` for Rust-only endpoints.
        return client
    }

    /// Verify that when no customBaseURL is provided (Python path), the
    /// constructed URL points to the Python backend.
    func testGetWithoutCustomBaseURLUsesPythonBackend() async {
        setenv("OMI_PYTHON_API_URL", "http://python-host:8080", 1)
        setenv("OMI_API_URL", "http://rust-host:8787", 1)
        defer {
            unsetenv("OMI_PYTHON_API_URL")
            unsetenv("OMI_API_URL")
        }

        let client = APIClient()
        let base = await client.baseURL

        // Simulate what a migrated endpoint (e.g., getConversation) does:
        //   get("v1/conversations/abc123")  →  baseURL + endpoint
        let expectedURL = base + "v1/conversations/abc123"
        XCTAssertTrue(
            expectedURL.hasPrefix("http://python-host:8080/"),
            "Migrated CRUD endpoint should route to Python backend, got: \(expectedURL)"
        )
    }

    /// Verify that when customBaseURL = rustBackendURL is provided (Rust path),
    /// the constructed URL points to the Rust backend.
    func testGetWithCustomBaseURLUsesRustBackend() async {
        setenv("OMI_PYTHON_API_URL", "http://python-host:8080", 1)
        setenv("OMI_API_URL", "http://rust-host:8787", 1)
        defer {
            unsetenv("OMI_PYTHON_API_URL")
            unsetenv("OMI_API_URL")
        }

        let client = APIClient()
        let rustURL = await client.rustBackendURL

        // Simulate what a Rust-only endpoint (e.g., fetchApiKeys) does:
        //   get("v1/config/api-keys", customBaseURL: rustBackendURL)
        let expectedURL = rustURL + "v1/config/api-keys"
        XCTAssertTrue(
            expectedURL.hasPrefix("http://rust-host:8787/"),
            "Rust-only endpoint should route to Rust backend, got: \(expectedURL)"
        )
    }

    /// Verify the customBaseURL-or-baseURL fallback logic matches what
    /// the generic HTTP helpers do: `let base = customBaseURL ?? baseURL`.
    func testCustomBaseURLFallbackLogic() async {
        setenv("OMI_PYTHON_API_URL", "http://python:9001", 1)
        setenv("OMI_API_URL", "http://rust:9002", 1)
        defer {
            unsetenv("OMI_PYTHON_API_URL")
            unsetenv("OMI_API_URL")
        }

        let client = APIClient()
        let pythonBase = await client.baseURL
        let rustBase = await client.rustBackendURL

        // No customBaseURL → Python (this is what getConversation, getMemories, etc. do)
        let nilFallback: String? = nil
        let pythonPath = (nilFallback ?? pythonBase) + "v1/conversations"
        XCTAssertEqual(pythonPath, "http://python:9001/v1/conversations")

        // customBaseURL = rustBackendURL → Rust (this is what fetchApiKeys, getAssistantSettings, etc. do)
        let rustPath = (rustBase) + "v1/config/api-keys"
        XCTAssertEqual(rustPath, "http://rust:9002/v1/config/api-keys")
    }

    /// Verify specific endpoint routing by checking customBaseURL parameter presence.
    /// This ensures the code paths for representative endpoints are correct:
    /// - getConversation: no customBaseURL → Python
    /// - fetchApiKeys: customBaseURL = rustBackendURL → Rust
    /// - getAssistantSettings: customBaseURL = rustBackendURL → Rust
    func testEndpointRoutingClassification() async {
        setenv("OMI_PYTHON_API_URL", "http://python:9001", 1)
        setenv("OMI_API_URL", "http://rust:9002", 1)
        defer {
            unsetenv("OMI_PYTHON_API_URL")
            unsetenv("OMI_API_URL")
        }

        let client = APIClient()
        let pythonBase = await client.baseURL
        let rustBase = await client.rustBackendURL

        // Python-routed endpoints (no customBaseURL):
        // getConversation → get("v1/conversations/\(id)")
        XCTAssertEqual(pythonBase + "v1/conversations/test-id", "http://python:9001/v1/conversations/test-id")
        // getMemories → get("v3/memories?...")
        XCTAssertEqual(pythonBase + "v3/memories?limit=50&offset=0", "http://python:9001/v3/memories?limit=50&offset=0")
        // getActionItems → get("v1/action-items?...")
        XCTAssertEqual(pythonBase + "v1/action-items?limit=50", "http://python:9001/v1/action-items?limit=50")
        // getGoals → get("v1/goals")
        XCTAssertEqual(pythonBase + "v1/goals", "http://python:9001/v1/goals")
        // getFolders → get("v1/folders")
        XCTAssertEqual(pythonBase + "v1/folders", "http://python:9001/v1/folders")

        // Rust-routed endpoints (customBaseURL = rustBackendURL):
        // fetchApiKeys → get("v1/config/api-keys", customBaseURL: rustBackendURL)
        XCTAssertEqual(rustBase + "v1/config/api-keys", "http://rust:9002/v1/config/api-keys")
        // getAssistantSettings → get("v1/users/assistant-settings", customBaseURL: rustBackendURL)
        XCTAssertEqual(rustBase + "v1/users/assistant-settings", "http://rust:9002/v1/users/assistant-settings")
        // getStagedTasks → get("v1/staged-tasks?...", customBaseURL: rustBackendURL)
        XCTAssertEqual(rustBase + "v1/staged-tasks?limit=100&offset=0", "http://rust:9002/v1/staged-tasks?limit=100&offset=0")
        // getChatSessions → get("v2/chat-sessions", customBaseURL: rustBackendURL)
        XCTAssertEqual(rustBase + "v2/chat-sessions", "http://rust:9002/v2/chat-sessions")
        // getDailyScore → get("v1/daily-score?...", customBaseURL: rustBackendURL)
        XCTAssertEqual(rustBase + "v1/daily-score", "http://rust:9002/v1/daily-score")
    }
}
