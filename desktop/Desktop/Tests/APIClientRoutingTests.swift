import XCTest
@testable import Omi_Computer

// MARK: - Request-capturing protocol for routing verification

/// Captured request info: URL + HTTP method.
private struct CapturedRequest {
    let url: URL
    let method: String
    let headers: [String: String]
    let body: Data?
}

/// Intercepts HTTP requests, records their URL and method, then returns 403
/// so APIClient throws .httpError (not 401, which triggers AuthService refresh).
private final class URLCapture: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var _requests: [CapturedRequest] = []

    static var capturedRequests: [CapturedRequest] {
        lock.lock()
        defer { lock.unlock() }
        return _requests
    }

    static func reset() {
        lock.lock()
        _requests.removeAll()
        lock.unlock()
    }

    private static func record(_ req: CapturedRequest) {
        lock.lock()
        _requests.append(req)
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        if let url = request.url {
            URLCapture.record(CapturedRequest(
                url: url,
                method: request.httpMethod ?? "GET",
                headers: request.allHTTPHeaderFields ?? [:],
                body: request.httpBody
            ))
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 403, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{\"detail\":\"test\"}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

// MARK: - Assertion helpers

private func assertRoutes(
    _ reqs: [CapturedRequest],
    host: String,
    port: Int,
    pathContains: String,
    method: String,
    label: String,
    file: StaticString = #filePath,
    line: UInt = #line
) {
    XCTAssertEqual(reqs.count, 1, "\(label): expected 1 request, got \(reqs.count)", file: file, line: line)
    guard let req = reqs.first else { return }
    XCTAssertEqual(req.url.host, host, "\(label): wrong host", file: file, line: line)
    XCTAssertEqual(req.url.port, port, "\(label): wrong port", file: file, line: line)
    XCTAssertTrue(req.url.absoluteString.contains(pathContains), "\(label): path should contain '\(pathContains)', got \(req.url.absoluteString)", file: file, line: line)
    XCTAssertEqual(req.method, method, "\(label): wrong HTTP method", file: file, line: line)
}

// MARK: - Tests

final class APIClientRoutingTests: XCTestCase {

    // MARK: - URL property tests

    func testBaseURLDefaultsToPythonBackend() async {
        unsetenv("OMI_PYTHON_API_URL")
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertEqual(url, "https://api.omi.me/")
    }

    func testBaseURLReadsFromPythonEnvVar() async {
        setenv("OMI_PYTHON_API_URL", "http://localhost:8080", 1)
        defer { unsetenv("OMI_PYTHON_API_URL") }
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertEqual(url, "http://localhost:8080/")
    }

    func testBaseURLAddsTrailingSlash() async {
        setenv("OMI_PYTHON_API_URL", "http://localhost:8080", 1)
        defer { unsetenv("OMI_PYTHON_API_URL") }
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertTrue(url.hasSuffix("/"))
    }

    func testBaseURLPreservesExistingTrailingSlash() async {
        setenv("OMI_PYTHON_API_URL", "http://localhost:8080/", 1)
        defer { unsetenv("OMI_PYTHON_API_URL") }
        let client = APIClient()
        let url = await client.baseURL
        XCTAssertEqual(url, "http://localhost:8080/")
    }

    func testRustBackendURLReadsFromApiUrlEnvVar() async {
        setenv("OMI_API_URL", "http://localhost:8787", 1)
        defer { unsetenv("OMI_API_URL") }
        let client = APIClient()
        let url = await client.rustBackendURL
        XCTAssertEqual(url, "http://localhost:8787/")
    }

    func testRustBackendURLReturnsEmptyWhenNotSet() async {
        unsetenv("OMI_API_URL")
        let client = APIClient()
        let url = await client.rustBackendURL
        XCTAssertEqual(url, "")
    }

    func testBaseURLAndRustBackendURLAreIndependent() async {
        setenv("OMI_PYTHON_API_URL", "http://python:8080", 1)
        setenv("OMI_API_URL", "http://rust:8787", 1)
        defer { unsetenv("OMI_PYTHON_API_URL"); unsetenv("OMI_API_URL") }

        let client = APIClient()
        let base = await client.baseURL
        let rust = await client.rustBackendURL
        XCTAssertEqual(base, "http://python:8080/")
        XCTAssertEqual(rust, "http://rust:8787/")
        XCTAssertNotEqual(base, rust)
    }

    // MARK: - Routing behavior: Python-routed endpoints (default baseURL)

    private func makeTestClient() async -> APIClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [URLCapture.self]
        let session = URLSession(configuration: config)
        let client = APIClient(session: session)
        await client.setTestAuthHeader("Bearer test-token")
        return client
    }

    override func setUp() {
        super.setUp()
        URLCapture.reset()
        setenv("OMI_PYTHON_API_URL", "http://python-test:9001", 1)
        setenv("OMI_API_URL", "http://rust-test:9002", 1)
    }

    override func tearDown() {
        unsetenv("OMI_PYTHON_API_URL")
        unsetenv("OMI_API_URL")
        URLCapture.reset()
        super.tearDown()
    }

    // -- Conversations (GET, DELETE → Python) --

    func testGetConversationRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getConversation(id: "test-123") as ServerConversation
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/test-123", method: "GET",
                     label: "getConversation")
    }

    func testDeleteConversationRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.deleteConversation(id: "conv-456")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/conv-456", method: "DELETE",
                     label: "deleteConversation")
    }

    // -- Conversations: manual URL(string: baseURL + ...) paths (PATCH → Python) --

    func testSetConversationStarredRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.setConversationStarred(id: "c1", starred: true)
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/c1/starred", method: "PATCH",
                     label: "setConversationStarred")
    }

    func testUpdateConversationTitleRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.updateConversationTitle(id: "c2", title: "New")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/c2", method: "PATCH",
                     label: "updateConversationTitle")
    }

    // -- Folders (GET → Python) --

    func testGetFoldersRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getFolders() as [Folder]
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/folders", method: "GET",
                     label: "getFolders")
    }

    // -- Memories (POST → Python) --

    func testCreateMemoryRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.createMemory(content: "test memory") as CreateMemoryResponse
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v3/memories", method: "POST",
                     label: "createMemory")
    }

    // -- Goals: manual URL path (PATCH → Python) --

    func testUpdateGoalProgressRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.updateGoalProgress(goalId: "g1", currentValue: 42.0) as Goal
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/goals/g1/progress", method: "PATCH",
                     label: "updateGoalProgress")
    }

    // -- Apps (GET → Python) --

    func testGetAppsRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getApps() as [OmiApp]
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/apps", method: "GET",
                     label: "getApps")
    }

    // -- Personas (GET → Python) --

    func testGetPersonaRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getPersona() as Persona?
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/personas", method: "GET",
                     label: "getPersona")
    }

    // -- User settings (GET → Python) --

    func testGetDailySummarySettingsRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getDailySummarySettings() as DailySummarySettings
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/daily-summary-settings", method: "GET",
                     label: "getDailySummarySettings")
    }

    // -- Subscription/payments (GET → Python, was explicit pythonBackendURL, now default) --

    func testGetUserSubscriptionRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getUserSubscription() as UserSubscriptionResponse
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/me/subscription", method: "GET",
                     label: "getUserSubscription")
    }

    // MARK: - Routing behavior: Rust-routed endpoints (customBaseURL: rustBackendURL)

    // -- Config/API keys (GET → Rust) --

    func testFetchApiKeysRoutesToRust() async {
        let client = await makeTestClient()
        _ = try? await client.fetchApiKeys() as APIClient.ApiKeysResponse
        assertRoutes(URLCapture.capturedRequests, host: "rust-test", port: 9002,
                     pathContains: "v1/config/api-keys", method: "GET",
                     label: "fetchApiKeys")
    }

    func testSynthesizeSpeechRoutesToRustWithExpectedPayload() async throws {
        let client = await makeTestClient()
        let request = APIClient.TtsSynthesizeRequest(
            text: "hello from test",
            voiceId: "BAMYoBHLZM7lJgJAmFz0",
            modelId: "eleven_turbo_v2_5",
            outputFormat: "mp3_44100_128",
            voiceSettings: .init(
                stability: 0.34,
                similarityBoost: 0.88,
                style: 0.12,
                useSpeakerBoost: true
            )
        )

        _ = try? await client.synthesizeSpeech(request: request)

        assertRoutes(URLCapture.capturedRequests, host: "rust-test", port: 9002,
                     pathContains: "v1/tts/synthesize", method: "POST",
                     label: "synthesizeSpeech")

        let captured = try XCTUnwrap(URLCapture.capturedRequests.first)
        XCTAssertEqual(captured.headers["Authorization"], "Bearer test-token")
        XCTAssertEqual(captured.headers["Content-Type"], "application/json")

        let body = try XCTUnwrap(captured.body)
        let json = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: body) as? [String: Any]
        )

        XCTAssertEqual(json["text"] as? String, "hello from test")
        XCTAssertEqual(json["voice_id"] as? String, "BAMYoBHLZM7lJgJAmFz0")
        XCTAssertEqual(json["model_id"] as? String, "eleven_turbo_v2_5")
        XCTAssertEqual(json["output_format"] as? String, "mp3_44100_128")
        XCTAssertNil(json["voiceId"])
        XCTAssertNil(json["modelId"])
        XCTAssertNil(json["outputFormat"])

        let voiceSettings = try XCTUnwrap(json["voice_settings"] as? [String: Any])
        XCTAssertEqual(voiceSettings["stability"] as? Double, 0.34)
        XCTAssertEqual(voiceSettings["similarity_boost"] as? Double, 0.88)
        XCTAssertEqual(voiceSettings["style"] as? Double, 0.12)
        XCTAssertEqual(voiceSettings["use_speaker_boost"] as? Bool, true)
        XCTAssertNil(voiceSettings["similarityBoost"])
        XCTAssertNil(voiceSettings["useSpeakerBoost"])
    }

    // -- Assistant settings (GET → Python, migrated from Rust) --

    func testGetAssistantSettingsRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getAssistantSettings() as AssistantSettingsResponse
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/assistant-settings", method: "GET",
                     label: "getAssistantSettings")
    }

    // -- Notification settings (GET → Python, migrated from Rust) --

    func testGetNotificationSettingsRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getNotificationSettings() as NotificationSettingsResponse
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/notification-settings", method: "GET",
                     label: "getNotificationSettings")
    }

    // -- Staged tasks (GET, DELETE → Python, migrated from Rust) --

    func testGetStagedTasksRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getStagedTasks() as ActionItemsListResponse
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/staged-tasks", method: "GET",
                     label: "getStagedTasks")
    }

    func testDeleteStagedTaskRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.deleteStagedTask(id: "st-1")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/staged-tasks/st-1", method: "DELETE",
                     label: "deleteStagedTask")
    }

    // -- Chat sessions (GET, POST, DELETE → Python, migrated from Rust) --

    func testGetChatSessionsRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getChatSessions() as [ChatSession]
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v2/chat-sessions", method: "GET",
                     label: "getChatSessions")
    }

    func testCreateChatSessionRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.createChatSession(title: "test") as ChatSession
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v2/chat-sessions", method: "POST",
                     label: "createChatSession")
    }

    func testDeleteChatSessionRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.deleteChatSession(sessionId: "sess-1")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v2/chat-sessions/sess-1", method: "DELETE",
                     label: "deleteChatSession")
    }

    // -- Desktop messages (DELETE → Python, path changed to v2/desktop/messages) --

    func testDeleteMessagesRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.deleteMessages() as MessageDeleteResponse
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v2/desktop/messages", method: "DELETE",
                     label: "deleteMessages")
    }

    // -- LLM usage (GET → Python, migrated from Rust) --

    func testFetchTotalOmiAICostRoutesToPython() async {
        let client = await makeTestClient()
        _ = await client.fetchTotalOmiAICost()
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/me/llm-usage/total", method: "GET",
                     label: "fetchTotalOmiAICost")
    }

    // MARK: - Python-routed: remaining manual URL builders

    // -- setConversationVisibility: manual URL(string: baseURL + ...) PATCH → Python --

    func testSetConversationVisibilityRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.setConversationVisibility(id: "c3")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/c3/visibility", method: "PATCH",
                     label: "setConversationVisibility")
    }

    // -- moveConversationToFolder: manual URL PATCH → Python --

    func testMoveConversationToFolderRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.moveConversationToFolder(conversationId: "c4", folderId: "f1")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/c4/folder", method: "PATCH",
                     label: "moveConversationToFolder")
    }

    // -- setRecordingPermission: manual URL POST → Python --

    func testSetRecordingPermissionRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.setRecordingPermission(enabled: true)
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/store-recording-permission", method: "POST",
                     label: "setRecordingPermission")
    }

    // -- setPrivateCloudSync: manual URL POST → Python --

    func testSetPrivateCloudSyncRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.setPrivateCloudSync(enabled: false)
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/private-cloud-sync", method: "POST",
                     label: "setPrivateCloudSync")
    }

    // -- completeGoal: manual URL PATCH → Python --

    func testCompleteGoalRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.completeGoal(id: "g2") as Goal
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/goals/g2", method: "PATCH",
                     label: "completeGoal")
    }

    // -- assignSegmentsBulk: manual URL PATCH → Python --

    func testAssignSegmentsBulkRoutesToPython() async {
        let client = await makeTestClient()
        try? await client.assignSegmentsBulk(conversationId: "c5", segmentIds: ["s1"], isUser: true, personId: nil)
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/conversations/c5/segments/assign-bulk", method: "PATCH",
                     label: "assignSegmentsBulk")
    }

    // -- Chat AI endpoints (migrated from Rust to Python) --

    func testGetInitialMessageRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getInitialMessage(sessionId: "s1")
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v2/chat/initial-message", method: "POST",
                     label: "getInitialMessage")
    }

    func testGenerateSessionTitleRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.generateSessionTitle(sessionId: "s1", messages: [("hi", "human")])
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v2/chat/generate-title", method: "POST",
                     label: "generateSessionTitle")
    }

    func testGetChatMessageCountRoutesToPython() async {
        let client = await makeTestClient()
        _ = try? await client.getChatMessageCount()
        assertRoutes(URLCapture.capturedRequests, host: "python-test", port: 9001,
                     pathContains: "v1/users/stats/chat-messages", method: "GET",
                     label: "getChatMessageCount")
    }
}

// MARK: - Helper extension to set testAuthHeader from async context

extension APIClient {
    func setTestAuthHeader(_ header: String) async {
        self.testAuthHeader = header
    }
}
