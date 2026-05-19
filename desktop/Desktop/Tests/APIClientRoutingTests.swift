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
  private static var _statusCode = 403

  static var capturedRequests: [CapturedRequest] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static var statusCode: Int {
    lock.lock()
    defer { lock.unlock() }
    return _statusCode
  }

  static func reset() {
    lock.lock()
    _requests.removeAll()
    _statusCode = 403
    lock.unlock()
  }

  static func setStatusCode(_ statusCode: Int) {
    lock.lock()
    _statusCode = statusCode
    lock.unlock()
  }

  private static func record(_ req: CapturedRequest) {
    lock.lock()
    _requests.append(req)
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
    let bufferSize = 4096
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
    defer { buffer.deallocate() }

    while stream.hasBytesAvailable {
      let readCount = stream.read(buffer, maxLength: bufferSize)
      if readCount > 0 {
        data.append(buffer, count: readCount)
      } else if readCount < 0 {
        return nil
      } else {
        break
      }
    }

    return data.isEmpty ? nil : data
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    if let url = request.url {
      URLCapture.record(
        CapturedRequest(
          url: url,
          method: request.httpMethod ?? "GET",
          headers: request.allHTTPHeaderFields ?? [:],
          body: Self.bodyData(from: request)
        ))
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: Self.statusCode, httpVersion: nil, headerFields: nil)!
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
  XCTAssertEqual(
    reqs.count, 1, "\(label): expected 1 request, got \(reqs.count)", file: file, line: line)
  guard let req = reqs.first else { return }
  XCTAssertEqual(req.url.host, host, "\(label): wrong host", file: file, line: line)
  XCTAssertEqual(req.url.port, port, "\(label): wrong port", file: file, line: line)
  XCTAssertTrue(
    req.url.absoluteString.contains(pathContains),
    "\(label): path should contain '\(pathContains)', got \(req.url.absoluteString)", file: file,
    line: line)
  XCTAssertEqual(req.method, method, "\(label): wrong HTTP method", file: file, line: line)
}

private func assertNoOmiHostedBackendRequests(
  _ reqs: [CapturedRequest],
  file: StaticString = #filePath,
  line: UInt = #line
) {
  let forbiddenHosts: Set<String> = [
    "api.omi.me",
    "api.omiapi.com",
    "desktop-backend-hhibjajaja-uc.a.run.app",
    "desktop-backend-dt5lrfkkoa-uc.a.run.app",
    "omi-cloud-invalid",
    "omi-rust-invalid",
  ]

  XCTAssertFalse(
    reqs.contains { request in
      guard let host = request.url.host else { return false }
      return forbiddenHosts.contains(host) || host.contains("firebase")
        || host.hasSuffix(".firebaseio.com") || host.hasSuffix(".googleapis.com")
    },
    "local-mode routing should not call Omi-hosted backend or Firebase endpoints",
    file: file,
    line: line
  )
}

private func assertUnavailable(
  _ error: Error?,
  capability: DesktopBackendEnvironment.Capability,
  file: StaticString = #filePath,
  line: UInt = #line
) {
  guard let error, case APIError.featureUnavailable(let feature, _) = error else {
    XCTFail(
      "expected featureUnavailable for \(capability.rawValue), got \(String(describing: error))",
      file: file, line: line)
    return
  }
  XCTAssertEqual(feature, capability.rawValue, file: file, line: line)
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

  func testBetaProductionBundleUsesDevelopmentPythonBackend() {
    let url = DesktopBackendEnvironment.pythonBaseURL(
      useDevelopmentBackends: true,
      environmentValue: "https://api.omi.me"
    )
    XCTAssertEqual(url, "https://api.omiapi.com/")
  }

  func testStableProductionBundleKeepsProductionPythonBackend() {
    let url = DesktopBackendEnvironment.pythonBaseURL(
      useDevelopmentBackends: false,
      environmentValue: "https://api.omi.me"
    )
    XCTAssertEqual(url, "https://api.omi.me/")
  }

  func testBetaProductionBundleUsesDevelopmentRustBackend() {
    let url = DesktopBackendEnvironment.rustBackendURL(
      useDevelopmentBackends: true,
      environmentValue: "https://desktop-backend-hhibjajaja-uc.a.run.app",
      launchEnvironmentValue: nil
    )
    XCTAssertEqual(url, "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/")
  }

  func testStableProductionBundleKeepsConfiguredRustBackend() {
    let url = DesktopBackendEnvironment.rustBackendURL(
      useDevelopmentBackends: false,
      environmentValue: "https://desktop-backend-hhibjajaja-uc.a.run.app",
      launchEnvironmentValue: nil
    )
    XCTAssertEqual(url, "https://desktop-backend-hhibjajaja-uc.a.run.app/")
  }

  func testBetaProductionBundleRoutesToDevelopmentBackends() {
    XCTAssertTrue(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.computer-macos",
        updateChannel: "beta"
      ))
    // "staging" is normalized to "beta" — same routing.
    XCTAssertTrue(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.computer-macos",
        updateChannel: "staging"
      ))
  }

  func testStableProductionBundleKeepsProductionBackends() {
    XCTAssertFalse(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.computer-macos",
        updateChannel: "stable"
      ))
  }

  func testNonProductionBundleSkipsAutomaticBetaRouting() {
    // Dev bundle and named test bundles never trigger beta-to-dev routing
    // automatically. They must opt in via OMI_FORCE_DEV_BACKENDS or env URLs.
    XCTAssertFalse(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.desktop-dev",
        updateChannel: "beta"
      ))
    XCTAssertFalse(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.omi-beta-dev-test",
        updateChannel: "beta"
      ))
  }

  func testForceOverrideEnablesDevelopmentBackendsForAnyBundle() {
    XCTAssertTrue(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.desktop-dev",
        updateChannel: "stable",
        forceOverride: "1"
      ))
    XCTAssertTrue(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.omi-beta-dev-test",
        updateChannel: "stable",
        forceOverride: "true"
      ))
    XCTAssertFalse(
      DesktopBackendEnvironment.shouldUseDevelopmentBackends(
        bundleIdentifier: "com.omi.computer-macos",
        updateChannel: "stable",
        forceOverride: "0"
      ))
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
    setenv("OMI_DESKTOP_API_URL", "http://localhost:8787", 1)
    defer { unsetenv("OMI_DESKTOP_API_URL") }
    let client = APIClient()
    let url = await client.rustBackendURL
    XCTAssertEqual(url, "http://localhost:8787/")
  }

  func testRustBackendURLReturnsEmptyWhenNotSet() async {
    unsetenv("OMI_DESKTOP_API_URL")
    let client = APIClient()
    let url = await client.rustBackendURL
    XCTAssertEqual(url, "")
  }

  func testSelectedBackendTargetDefaultsToCloudPython() {
    let target = DesktopBackendEnvironment.selectedBackendTarget(
      modeValue: nil,
      pythonEnvironmentValue: "https://api.example.test",
      localDaemonEnvironmentValue: nil
    )
    XCTAssertEqual(target.mode, .cloud)
    XCTAssertEqual(target.baseURL, "https://api.example.test/")
    XCTAssertTrue(target.requiresAuth)
  }

  func testSelectedBackendTargetSupportsLocalDaemonDefault() {
    let target = DesktopBackendEnvironment.selectedBackendTarget(
      modeValue: "local",
      pythonEnvironmentValue: "https://api.example.test",
      localDaemonEnvironmentValue: nil
    )
    XCTAssertEqual(target.mode, .localDaemon)
    XCTAssertEqual(target.baseURL, "http://127.0.0.1:8765/")
    XCTAssertFalse(target.requiresAuth)
  }

  func testSelectedBackendTargetSupportsCustomRemote() {
    let target = DesktopBackendEnvironment.selectedBackendTarget(
      modeValue: "custom",
      pythonEnvironmentValue: "http://custom-backend:7777",
      localDaemonEnvironmentValue: "http://127.0.0.1:8765"
    )
    XCTAssertEqual(target.mode, .customRemote)
    XCTAssertEqual(target.baseURL, "http://custom-backend:7777/")
    XCTAssertTrue(target.requiresAuth)
  }

  func testLocalDaemonCapabilityMatrixDisablesCloudBoundFeatures() {
    let capabilities = Dictionary(
      uniqueKeysWithValues: DesktopBackendEnvironment.capabilities(for: .localDaemon)
        .map { ($0.capability, $0) }
    )

    XCTAssertEqual(capabilities[.localConversationData]?.available, true)
    XCTAssertEqual(capabilities[.firebaseSignIn]?.available, true)
    XCTAssertEqual(capabilities[.managedAgentVM]?.available, false)
    XCTAssertEqual(capabilities[.omiBackendProviderProxy]?.available, false)
    XCTAssertEqual(capabilities[.publicSharing]?.available, false)
    XCTAssertEqual(capabilities[.cloudSync]?.available, false)
    XCTAssertEqual(capabilities[.payments]?.available, false)
    XCTAssertEqual(capabilities[.crispSupport]?.available, false)
    XCTAssertEqual(capabilities[.hostedTranscription]?.available, false)
    XCTAssertNotNil(capabilities[.managedAgentVM]?.reason)
  }

  func testCloudCapabilityMatrixAllowsCloudBoundFeatures() {
    for state in DesktopBackendEnvironment.capabilities(for: .cloud) {
      XCTAssertTrue(
        state.available, "\(state.capability.rawValue) should be available in cloud mode")
      XCTAssertNil(state.reason)
    }
  }

  func testBaseURLAndRustBackendURLAreIndependent() async {
    setenv("OMI_PYTHON_API_URL", "http://python:8080", 1)
    setenv("OMI_DESKTOP_API_URL", "http://rust:8787", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      unsetenv("OMI_DESKTOP_API_URL")
    }

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
    setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
    unsetenv("OMI_DESKTOP_BACKEND_MODE")
    unsetenv("OMI_LOCAL_DAEMON_URL")
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    unsetenv("OMI_DESKTOP_API_URL")
    unsetenv("OMI_DESKTOP_BACKEND_MODE")
    unsetenv("OMI_LOCAL_DAEMON_URL")
    URLCapture.reset()
    super.tearDown()
  }

  // -- Conversations (GET, DELETE → Python) --

  func testGetConversationRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getConversation(id: "test-123") as ServerConversation
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/test-123", method: "GET",
      label: "getConversation")
  }

  func testLocalModeGetConversationRoutesToLocalDaemonWithoutAuth() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()
    _ = try? await client.getConversation(id: "local-123") as ServerConversation

    assertRoutes(
      URLCapture.capturedRequests, host: "127.0.0.1", port: 8765,
      pathContains: "v1/conversations/local-123", method: "GET",
      label: "local getConversation")
    XCTAssertNil(URLCapture.capturedRequests.first?.headers["Authorization"])
  }

  func testDeleteConversationRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.deleteConversation(id: "conv-456")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/conv-456", method: "DELETE",
      label: "deleteConversation")
  }

  func testLocalModeCreateConversationRoutesToLocalDaemonWithoutAuth() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()
    _ = try? await client.createLocalDaemonConversation(
      sessionId: "desktop-1",
      title: "Local",
      overview: "Local daemon",
      startedAt: Date(timeIntervalSince1970: 0)
    )

    let requests = URLCapture.capturedRequests
    assertRoutes(
      requests, host: "127.0.0.1", port: 8765,
      pathContains: "v1/conversations", method: "POST",
      label: "local createConversation")
    XCTAssertNil(requests.first?.headers["Authorization"])
  }

  func testLocalModeHealthCheckRoutesToLocalDaemonWithoutAuth() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()
    _ = try? await client.checkSelectedBackendHealth()

    assertRoutes(
      URLCapture.capturedRequests, host: "127.0.0.1", port: 8765,
      pathContains: "health", method: "GET",
      label: "local health")
    XCTAssertNil(URLCapture.capturedRequests.first?.headers["Authorization"])
  }

  func testLocalModeSettingsRoutesToLocalDaemonWithoutAuth() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()
    _ = try? await client.updateSelectedBackendSettings(["profile_name": "Local"])

    assertRoutes(
      URLCapture.capturedRequests, host: "127.0.0.1", port: 8765,
      pathContains: "v1/settings", method: "PUT",
      label: "local settings")
    XCTAssertNil(URLCapture.capturedRequests.first?.headers["Authorization"])
  }

  func testLocalModeMVPConversationFlowsIgnoreInvalidCloudURLs() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_PYTHON_API_URL", "http://omi-cloud-invalid:9001", 1)
    setenv("OMI_DESKTOP_API_URL", "http://omi-rust-invalid:9002", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:9876", 1)
    let client = await makeTestClient()

    _ = try? await client.getConversations()
    _ = try? await client.getConversation(id: "local-123") as ServerConversation
    _ = try? await client.searchConversations(query: "offline")
    try? await client.updateConversationTitle(id: "local-123", title: "Offline")
    try? await client.setConversationStarred(id: "local-123", starred: true)
    _ = try? await client.updateSelectedBackendSettings(["profile_name": "Offline"])
    try? await client.deleteConversation(id: "local-123")

    let requests = URLCapture.capturedRequests
    XCTAssertEqual(requests.count, 7)
    XCTAssertTrue(requests.allSatisfy { $0.url.host == "127.0.0.1" && $0.url.port == 9876 })
    XCTAssertTrue(requests.allSatisfy { $0.headers["Authorization"] == nil })
    assertNoOmiHostedBackendRequests(requests)
  }

  func testLocalModeTranscriptImportRoutesToLocalDaemonWithoutAuth() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_PYTHON_API_URL", "https://api.omi.me", 1)
    setenv("OMI_DESKTOP_API_URL", "https://desktop-backend-hhibjajaja-uc.a.run.app", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:9876", 1)
    let client = await makeTestClient()
    let segment = TranscriptionSegmentRecord(
      sessionId: 42,
      speaker: 0,
      text: "Local transcript import should stay on loopback.",
      startTime: 0,
      endTime: 2.5,
      segmentOrder: 0,
      segmentId: "seg-local-0",
      speakerLabel: "Speaker 1"
    )

    try? await client.appendLocalDaemonTranscriptSegment(
      conversationId: "local-123",
      segment: segment
    )
    try? await client.finalizeLocalDaemonTranscript(conversationId: "local-123")

    let requests = URLCapture.capturedRequests
    XCTAssertEqual(requests.count, 2)
    XCTAssertTrue(requests.allSatisfy { $0.url.host == "127.0.0.1" && $0.url.port == 9876 })
    XCTAssertTrue(requests.allSatisfy { $0.headers["Authorization"] == nil })
    XCTAssertEqual(requests.map(\.method), ["POST", "POST"])
    XCTAssertTrue(
      requests[0].url.path.contains("/v1/conversations/local-123/transcript-segments"))
    XCTAssertTrue(
      requests[1].url.path.contains("/v1/conversations/local-123/finalize-transcript"))
    assertNoOmiHostedBackendRequests(requests)
  }

  func testLocalModeSetConversationStarredRoutesToLocalDaemonWithoutAuth() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()
    try? await client.setConversationStarred(id: "local-star", starred: true)

    let requests = URLCapture.capturedRequests
    assertRoutes(
      requests, host: "127.0.0.1", port: 8765,
      pathContains: "v1/conversations/local-star", method: "PATCH",
      label: "local setConversationStarred")
    XCTAssertNil(requests.first?.headers["Authorization"])

    let body = requests.first?.body.flatMap {
      try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
    }
    XCTAssertEqual(body?["starred"] as? Bool, true)
  }

  func testLocalModeMergeAndFolderActionsFailBeforeNetworkRequests() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()

    do {
      _ = try await client.mergeConversations(ids: ["c1", "c2"])
      XCTFail("expected merge to be unavailable")
    } catch {
      guard case APIError.featureUnavailable(let feature, _) = error else {
        XCTFail("expected featureUnavailable for merge, got \(error)")
        return
      }
      XCTAssertEqual(feature, "conversation_merge")
    }

    do {
      _ = try await client.getFolders()
      XCTFail("expected folders to be unavailable")
    } catch {
      guard case APIError.featureUnavailable(let feature, _) = error else {
        XCTFail("expected featureUnavailable for folders, got \(error)")
        return
      }
      XCTAssertEqual(feature, "conversation_folders")
    }

    do {
      _ = try await client.createFolder(name: "Work")
      XCTFail("expected folder creation to be unavailable")
    } catch {
      guard case APIError.featureUnavailable = error else {
        XCTFail("expected featureUnavailable for folder creation, got \(error)")
        return
      }
    }

    do {
      _ = try await client.updateFolder(id: "f1", name: "Renamed")
      XCTFail("expected folder update to be unavailable")
    } catch {
      guard case APIError.featureUnavailable = error else {
        XCTFail("expected featureUnavailable for folder update, got \(error)")
        return
      }
    }

    do {
      try await client.deleteFolder(id: "f1")
      XCTFail("expected folder deletion to be unavailable")
    } catch {
      guard case APIError.featureUnavailable = error else {
        XCTFail("expected featureUnavailable for folder deletion, got \(error)")
        return
      }
    }

    do {
      try await client.moveConversationToFolder(conversationId: "c1", folderId: "f1")
      XCTFail("expected move-to-folder to be unavailable")
    } catch {
      guard case APIError.featureUnavailable = error else {
        XCTFail("expected featureUnavailable for move-to-folder, got \(error)")
        return
      }
    }

    XCTAssertTrue(URLCapture.capturedRequests.isEmpty)
  }

  func testLocalUnauthenticatedRequestDoesNotRefreshAuthOn401() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    URLCapture.setStatusCode(401)
    let client = await makeTestClient()

    do {
      _ = try await client.getSelectedBackendSettings()
      XCTFail("expected unauthorized")
    } catch {
      guard case APIError.unauthorized = error else {
        XCTFail("expected unauthorized, got \(error)")
        return
      }
    }

    let requests = URLCapture.capturedRequests
    XCTAssertEqual(requests.count, 1)
    XCTAssertNil(requests.first?.headers["Authorization"])
  }

  func testLocalModeCloudOnlyFeaturesFailBeforeNetworkRequests() async {
    setenv("OMI_DESKTOP_BACKEND_MODE", "local", 1)
    setenv("OMI_LOCAL_DAEMON_URL", "http://127.0.0.1:8765", 1)
    let client = await makeTestClient()

    do {
      _ = try await client.provisionAgentVM()
      XCTFail("expected managed agent VM to be unavailable")
    } catch {
      assertUnavailable(error, capability: .managedAgentVM)
    }

    do {
      _ = try await client.fetchApiKeys()
      XCTFail("expected backend provider proxy to be unavailable")
    } catch {
      assertUnavailable(error, capability: .omiBackendProviderProxy)
    }

    do {
      _ = try await client.getUserSubscription()
      XCTFail("expected payments to be unavailable")
    } catch {
      assertUnavailable(error, capability: .payments)
    }

    do {
      _ = try await client.shareChatMessages(messageIds: ["m1"])
      XCTFail("expected public sharing to be unavailable")
    } catch {
      assertUnavailable(error, capability: .publicSharing)
    }

    do {
      try await client.setPrivateCloudSync(enabled: true)
      XCTFail("expected cloud sync to be unavailable")
    } catch {
      assertUnavailable(error, capability: .cloudSync)
    }

    XCTAssertTrue(URLCapture.capturedRequests.isEmpty)
  }

  // -- Conversations: manual URL(string: baseURL + ...) paths (PATCH → Python) --

  func testSetConversationStarredRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.setConversationStarred(id: "c1", starred: true)
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/c1/starred", method: "PATCH",
      label: "setConversationStarred")
  }

  func testUpdateConversationTitleRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.updateConversationTitle(id: "c2", title: "New")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/c2", method: "PATCH",
      label: "updateConversationTitle")
  }

  // -- Folders (GET → Python) --

  func testGetFoldersRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getFolders() as [Folder]
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/folders", method: "GET",
      label: "getFolders")
  }

  // -- Memories (POST → Python) --

  func testCreateMemoryRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.createMemory(content: "test memory") as CreateMemoryResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v3/memories", method: "POST",
      label: "createMemory")
  }

  // -- Goals: manual URL path (PATCH → Python) --

  func testUpdateGoalProgressRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.updateGoalProgress(goalId: "g1", currentValue: 42.0) as Goal
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/goals/g1/progress", method: "PATCH",
      label: "updateGoalProgress")
  }

  // -- Apps (GET → Python) --

  func testGetAppsRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getApps() as [OmiApp]
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/apps", method: "GET",
      label: "getApps")
  }

  // -- Personas (GET → Python) --

  func testGetPersonaRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getPersona() as Persona?
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/personas", method: "GET",
      label: "getPersona")
  }

  // -- User settings (GET → Python) --

  func testGetDailySummarySettingsRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getDailySummarySettings() as DailySummarySettings
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/daily-summary-settings", method: "GET",
      label: "getDailySummarySettings")
  }

  // -- Subscription/payments (GET → Python, was explicit pythonBackendURL, now default) --

  func testGetUserSubscriptionRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getUserSubscription() as UserSubscriptionResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/me/subscription", method: "GET",
      label: "getUserSubscription")
  }

  // MARK: - Routing behavior: Rust-routed endpoints (customBaseURL: rustBackendURL)

  // -- Config/API keys (GET → Rust) --

  func testFetchApiKeysRoutesToRust() async {
    let client = await makeTestClient()
    _ = try? await client.fetchApiKeys() as APIClient.ApiKeysResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "rust-test", port: 9002,
      pathContains: "v1/config/api-keys", method: "GET",
      label: "fetchApiKeys")
  }

  func testSynthesizeSpeechRoutesToRust() async {
    let client = await makeTestClient()
    _ = try? await client.synthesizeSpeech(
      request: APIClient.TtsSynthesizeRequest(
        text: "Hello",
        voiceId: "onyx",
        instructions: "Speak naturally"
      )
    )

    let requests = URLCapture.capturedRequests
    assertRoutes(
      requests, host: "rust-test", port: 9002,
      pathContains: "v1/tts/synthesize", method: "POST",
      label: "synthesizeSpeech")

    let body = requests.first?.body.flatMap {
      try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
    }
    XCTAssertEqual(body?["text"] as? String, "Hello")
    XCTAssertEqual(body?["voice_id"] as? String, "onyx")
    XCTAssertEqual(body?["instructions"] as? String, "Speak naturally")
  }

  // -- Assistant settings (GET → Python, migrated from Rust) --

  func testGetAssistantSettingsRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getAssistantSettings() as AssistantSettingsResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/assistant-settings", method: "GET",
      label: "getAssistantSettings")
  }

  // -- Notification settings (GET → Python, migrated from Rust) --

  func testGetNotificationSettingsRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getNotificationSettings() as NotificationSettingsResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/notification-settings", method: "GET",
      label: "getNotificationSettings")
  }

  // -- Staged tasks (GET, DELETE → Python, migrated from Rust) --

  func testGetStagedTasksRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getStagedTasks() as ActionItemsListResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/staged-tasks", method: "GET",
      label: "getStagedTasks")
  }

  func testDeleteStagedTaskRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.deleteStagedTask(id: "st-1")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/staged-tasks/st-1", method: "DELETE",
      label: "deleteStagedTask")
  }

  // -- Chat sessions (GET, POST, DELETE → Python, migrated from Rust) --

  func testGetChatSessionsRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getChatSessions() as [ChatSession]
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v2/chat-sessions", method: "GET",
      label: "getChatSessions")
  }

  func testCreateChatSessionRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.createChatSession(title: "test") as ChatSession
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v2/chat-sessions", method: "POST",
      label: "createChatSession")
  }

  func testDeleteChatSessionRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.deleteChatSession(sessionId: "sess-1")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v2/chat-sessions/sess-1", method: "DELETE",
      label: "deleteChatSession")
  }

  // -- Desktop messages (DELETE → Python, path changed to v2/desktop/messages) --

  func testDeleteMessagesRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.deleteMessages() as MessageDeleteResponse
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v2/desktop/messages", method: "DELETE",
      label: "deleteMessages")
  }

  // -- LLM usage (GET → Python, migrated from Rust) --

  func testFetchTotalOmiAICostRoutesToPython() async {
    let client = await makeTestClient()
    _ = await client.fetchTotalOmiAICost()
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/me/llm-usage/total", method: "GET",
      label: "fetchTotalOmiAICost")
  }

  // MARK: - Python-routed: remaining manual URL builders

  // -- setConversationVisibility: manual URL(string: baseURL + ...) PATCH → Python --

  func testSetConversationVisibilityRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.setConversationVisibility(id: "c3")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/c3/visibility", method: "PATCH",
      label: "setConversationVisibility")
  }

  // -- moveConversationToFolder: manual URL PATCH → Python --

  func testMoveConversationToFolderRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.moveConversationToFolder(conversationId: "c4", folderId: "f1")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/c4/folder", method: "PATCH",
      label: "moveConversationToFolder")
  }

  // -- setRecordingPermission: manual URL POST → Python --

  func testSetRecordingPermissionRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.setRecordingPermission(enabled: true)
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/store-recording-permission", method: "POST",
      label: "setRecordingPermission")
  }

  // -- setPrivateCloudSync: manual URL POST → Python --

  func testSetPrivateCloudSyncRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.setPrivateCloudSync(enabled: false)
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/users/private-cloud-sync", method: "POST",
      label: "setPrivateCloudSync")
  }

  // -- completeGoal: manual URL PATCH → Python --

  func testCompleteGoalRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.completeGoal(id: "g2") as Goal
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/goals/g2", method: "PATCH",
      label: "completeGoal")
  }

  // -- assignSegmentsBulk: manual URL PATCH → Python --

  func testAssignSegmentsBulkRoutesToPython() async {
    let client = await makeTestClient()
    try? await client.assignSegmentsBulk(
      conversationId: "c5", segmentIds: ["s1"], isUser: true, personId: nil)
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v1/conversations/c5/segments/assign-bulk", method: "PATCH",
      label: "assignSegmentsBulk")
  }

  // -- Chat AI endpoints (migrated from Rust to Python) --

  func testGetInitialMessageRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getInitialMessage(sessionId: "s1")
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v2/chat/initial-message", method: "POST",
      label: "getInitialMessage")
  }

  func testGenerateSessionTitleRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.generateSessionTitle(sessionId: "s1", messages: [("hi", "human")])
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
      pathContains: "v2/chat/generate-title", method: "POST",
      label: "generateSessionTitle")
  }

  func testGetChatMessageCountRoutesToPython() async {
    let client = await makeTestClient()
    _ = try? await client.getChatMessageCount()
    assertRoutes(
      URLCapture.capturedRequests, host: "python-test", port: 9001,
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
