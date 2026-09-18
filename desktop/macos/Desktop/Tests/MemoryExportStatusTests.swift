import XCTest

@testable import Omi_Computer

private final class CloudOAuthDisconnectURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var requests: [(method: String, path: String)] = []

  static func reset() {
    lock.lock()
    requests.removeAll()
    lock.unlock()
  }

  static var capturedRequests: [(method: String, path: String)] {
    lock.lock()
    defer { lock.unlock() }
    return requests
  }

  override class func canInit(with request: URLRequest) -> Bool { true }

  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let method = request.httpMethod ?? "GET"
    let path = request.url?.path ?? ""
    Self.lock.lock()
    Self.requests.append((method: method, path: path))
    Self.lock.unlock()

    let body =
      method == "GET"
      ? Data("{\"grants\":[{\"id\":\"grant-123\",\"client_id\":\"omi-chatgpt-prod\",\"status\":\"active\"}]}".utf8)
      : Data()
    let statusCode = method == "DELETE" ? 204 : 200
    guard let requestURL = request.url,
      let response = HTTPURLResponse(
        url: requestURL, statusCode: statusCode, httpVersion: nil, headerFields: nil)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    if !body.isEmpty {
      client?.urlProtocol(self, didLoad: body)
    }
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

extension APIClient {
  fileprivate func setTestAuthHeaderForMemoryExportTests(_ value: String) {
    testAuthHeader = value
  }
}

final class MemoryExportStatusTests: XCTestCase {
  private var tempHome: URL!

  override func setUp() {
    super.setUp()
    DesktopDiagnosticsManager.shared.resetForTests()
    resetMemoryExportDefaults()
    tempHome = FileManager.default.temporaryDirectory
      .appendingPathComponent("memory-export-status-\(UUID().uuidString)", isDirectory: true)
    try? FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)
    MemoryExportConnectionDetector.homeOverrideForTesting = tempHome
  }

  override func tearDown() {
    resetMemoryExportDefaults()
    MemoryExportConnectionDetector.homeOverrideForTesting = nil
    if let tempHome {
      try? FileManager.default.removeItem(at: tempHome)
    }
    super.tearDown()
  }

  func testStoredMCPKeyDoesNotMarkLocalMCPDestinationsConfiguredOrConnected() async {
    storeOwnedMCPKey()

    let codexStatus = await MemoryExportService.shared.status(for: .codex)
    let claudeCodeStatus = await MemoryExportService.shared.status(for: .claudeCode)
    let openClawStatus = await MemoryExportService.shared.status(for: .openclaw)
    let hermesStatus = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertFalse(codexStatus.isConfigured)
    XCTAssertFalse(claudeCodeStatus.isConfigured)
    XCTAssertFalse(openClawStatus.isConfigured)
    XCTAssertFalse(hermesStatus.isConfigured)
    XCTAssertFalse(codexStatus.hasConnection)
    XCTAssertFalse(claudeCodeStatus.hasConnection)
    XCTAssertFalse(openClawStatus.hasConnection)
    XCTAssertFalse(hermesStatus.hasConnection)
  }

  /// The ChatGPT directory listing is a single global plugin that always
  /// authorizes under `omi-chatgpt-prod`, even on a build pointed at the dev
  /// backend. Grant verification must accept that prod client ID regardless of
  /// `chatgptOAuthClientID`'s env switch, or ChatGPT never flips to connected on
  /// Beta (the shipped symptom: Claude verified, ChatGPT stuck).
  func testChatGPTGrantVerificationAcceptsProdDirectoryClientOnAnyBackend() {
    XCTAssertTrue(MemoryExportDestination.chatgpt.cloudOAuthGrantClientIDs.contains("omi-chatgpt-prod"))
    XCTAssertTrue(MemoryExportDestination.chatgpt.cloudOAuthGrantClientIDs.contains("omi-chatgpt-dev"))
    XCTAssertEqual(MemoryExportDestination.claude.cloudOAuthGrantClientIDs, ["omi-claude-prod"])
    XCTAssertTrue(MemoryExportDestination.notion.cloudOAuthGrantClientIDs.isEmpty)
  }

  func testMarkConnectedDoesNotMaskMissingLocalMCPConfig() async {
    storeOwnedMCPKey()

    await MemoryExportService.shared.markConnected(.openclaw)

    let openClawStatus = await MemoryExportService.shared.status(for: .openclaw)
    let hermesStatus = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertFalse(openClawStatus.hasConnection)
    XCTAssertFalse(hermesStatus.hasConnection)
  }

  func testMemoryPackExportStillCountsAsConnectionHistory() async {
    UserDefaults.standard.set(7, forKey: "memoryExportExportedCount.claude")

    let status = await MemoryExportService.shared.status(for: .claude)

    XCTAssertTrue(status.isConfigured)
    XCTAssertTrue(status.hasConnection)
  }

  func testChatGPTMemoryPackDoesNotClaimDirectoryAuthorization() async {
    UserDefaults.standard.set(7, forKey: "memoryExportExportedCount.chatgpt")

    let status = await MemoryExportService.shared.status(for: .chatgpt)
    let presentation = MemoryExportConnectionPresentation.make(
      destination: .chatgpt,
      status: status,
      isRunning: false)

    XCTAssertFalse(status.isConfigured)
    XCTAssertFalse(status.hasConnection)
    XCTAssertEqual(presentation.primaryActionTitle, "Add Omi to ChatGPT")
  }

  func testDisconnectCloudAuthorizationRevokesGrantAndClearsProjection() async throws {
    CloudOAuthDisconnectURLProtocol.reset()
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CloudOAuthDisconnectURLProtocol.self]
    let apiClient = APIClient(session: URLSession(configuration: configuration))
    await apiClient.setTestAuthHeaderForMemoryExportTests("Bearer test-token")
    let service = MemoryExportService(apiClient: apiClient)
    let connectedAtKey = memoryExportDefaultsKey("memoryExportConnectedAt", destination: .chatgpt)
    let detailKey = memoryExportDefaultsKey("memoryExportDetail", destination: .chatgpt)

    UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: connectedAtKey)
    UserDefaults.standard.set("Authorized through ChatGPT (cloud)", forKey: detailKey)

    let status = try await service.disconnectCloudOAuthConnection(for: .chatgpt)

    XCTAssertFalse(status.hasConnection)
    XCTAssertFalse(status.isConfigured)
    XCTAssertNil(UserDefaults.standard.object(forKey: connectedAtKey))
    XCTAssertNil(UserDefaults.standard.object(forKey: detailKey))
    let requests = CloudOAuthDisconnectURLProtocol.capturedRequests
    XCTAssertEqual(requests.count, 2)
    XCTAssertEqual(requests[0].method, "GET")
    XCTAssertEqual(requests[0].path, "/v1/mcp/oauth/grants")
    XCTAssertEqual(requests[1].method, "DELETE")
    XCTAssertEqual(requests[1].path, "/v1/mcp/oauth/grants/grant-123")
  }

  func testCachedCloudGrantStatusReadSignalsInferredConnectorAuthority() async {
    await MemoryExportService.shared.markConnected(.chatgpt)

    let status = await MemoryExportService.shared.status(for: .chatgpt)

    XCTAssertTrue(status.hasConnection)
    let signal = DesktopDiagnosticsManager.shared.currentSnapshotsForSentry().last {
      $0["seam"] as? String == DesktopStateAuthoritySeam.connectorStatus.rawValue
    }
    XCTAssertEqual(signal?["direction"] as? String, "cloud_grant_status_inferred")
    XCTAssertEqual(signal?["from"] as? String, "cached_or_derived")
    XCTAssertEqual(signal?["to"] as? String, "connected")
    XCTAssertEqual(signal?["subject"] as? String, "chatgpt")
  }

  func testOnlyLocalAgentSetupDestinationsHaveLocallyVerifiableLiveSetup() {
    XCTAssertFalse(MemoryExportDestination.chatgpt.hasLocallyVerifiableLiveSetup)
    XCTAssertFalse(MemoryExportDestination.claude.hasLocallyVerifiableLiveSetup)
    XCTAssertTrue(MemoryExportDestination.codex.hasLocallyVerifiableLiveSetup)
    XCTAssertTrue(MemoryExportDestination.claudeCode.hasLocallyVerifiableLiveSetup)
    XCTAssertTrue(MemoryExportDestination.openclaw.hasLocallyVerifiableLiveSetup)
    XCTAssertTrue(MemoryExportDestination.hermes.hasLocallyVerifiableLiveSetup)
    XCTAssertTrue(MemoryExportDestination.agents.hasLocallyVerifiableLiveSetup)
  }

  func testExistingCodexMCPConfigMarksCodexConnected() async throws {
    storeOwnedMCPKey()
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
    [mcp_servers.omi-memory]
    command = "npx"
    args = ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    let codexStatus = await MemoryExportService.shared.status(for: .codex)
    let chatGPTStatus = await MemoryExportService.shared.status(for: .chatgpt)

    XCTAssertTrue(codexStatus.isConfigured)
    XCTAssertTrue(codexStatus.hasConnection)
    XCTAssertFalse(chatGPTStatus.hasConnection)
  }

  func testCodexSetupCompletionRefreshHidesPrimarySetupCTA() async throws {
    storeOwnedMCPKey()

    var statuses = await MemoryExportService.shared.allStatuses()
    XCTAssertFalse(statuses[.codex]?.hasConnection == true)
    XCTAssertEqual(
      MemoryExportConnectionPresentation.make(
        destination: .codex,
        status: statuses[.codex],
        isRunning: false
      ).primaryActionTitle,
      "Do it for me"
    )

    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
    [mcp_servers.omi-memory]
    command = "npx"
    args = ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    statuses = await MemoryExportService.shared.allStatuses()
    let presentation = MemoryExportConnectionPresentation.make(
      destination: .codex,
      status: statuses[.codex],
      isRunning: false
    )

    XCTAssertTrue(statuses[.codex]?.hasConnection == true)
    XCTAssertNil(presentation.primaryActionTitle)
    XCTAssertEqual(
      presentation.completion,
      MCPSetupCompletionSummary(
        title: "Setup complete",
        subtitle: "Restart Codex to load Omi Memory."
      )
    )
  }

  func testExistingCodexMCPConfigWithDifferentKeyDoesNotMarkCodexConnected() async throws {
    storeOwnedMCPKey(key: "current-key")
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
    [mcp_servers.omi-memory]
    command = "npx"
    args = ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer old-key"]
    """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .codex)

    XCTAssertFalse(status.isConfigured)
    XCTAssertFalse(status.hasConnection)
  }

  func testExistingCodexMCPConfigWithoutCurrentUserKeyDoesNotMarkCodexConnected() async throws {
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
    [mcp_servers.omi-memory]
    command = "npx"
    args = ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .codex)

    XCTAssertFalse(status.isConfigured)
    XCTAssertFalse(status.hasConnection)
  }

  func testCommentedCodexMCPConfigDoesNotMarkCodexConnected() async throws {
    storeOwnedMCPKey()
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
    # [mcp_servers.omi-memory]
    # command = "npx"
    # args = ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .codex)

    XCTAssertFalse(status.hasConnection)
  }

  func testExistingClaudeMCPConfigMarksClaudeCodeConnected() async throws {
    storeOwnedMCPKey()
    try """
    {
      "mcpServers": {
        "omi-memory": {
          "type": "http",
          "url": "\(MemoryExportDestination.mcpServerURL)",
          "headers": {
            "Authorization": "Bearer test-key"
          }
        }
      }
    }
    """.write(to: tempHome.appendingPathComponent(".claude.json"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .claudeCode)

    XCTAssertTrue(status.isConfigured)
    XCTAssertTrue(status.hasConnection)
  }

  func testClaudeDesktopConfigMarksClaudeNotClaudeCodeConnected() async throws {
    storeOwnedMCPKey()
    let claudeDesktop = tempHome.appendingPathComponent(
      "Library/Application Support/Claude", isDirectory: true)
    try FileManager.default.createDirectory(at: claudeDesktop, withIntermediateDirectories: true)
    try """
    {
      "mcpServers": {
        "omi-memory": {
          "type": "http",
          "url": "\(MemoryExportDestination.mcpServerURL)",
          "headers": {
            "Authorization": "Bearer test-key"
          }
        }
      }
    }
    """.write(to: claudeDesktop.appendingPathComponent("claude_desktop_config.json"), atomically: true, encoding: .utf8)

    let claudeStatus = await MemoryExportService.shared.status(for: .claude)
    let claudeCodeStatus = await MemoryExportService.shared.status(for: .claudeCode)

    XCTAssertTrue(claudeStatus.isConfigured)
    XCTAssertTrue(claudeStatus.hasConnection)
    XCTAssertFalse(claudeCodeStatus.isConfigured)
    XCTAssertFalse(claudeCodeStatus.hasConnection)
  }

  func testDisabledOpenClawMCPConfigDoesNotMarkOpenClawConnected() async throws {
    storeOwnedMCPKey()
    let openClaw = tempHome.appendingPathComponent(".openclaw", isDirectory: true)
    try FileManager.default.createDirectory(at: openClaw, withIntermediateDirectories: true)
    try """
    {
      "mcp": {
        "servers": {
          "omi-memory": {
            "enabled": false,
            "url": "\(MemoryExportDestination.mcpServerURL)",
            "headers": {
              "Authorization": "Bearer test-key"
            }
          }
        }
      }
    }
    """.write(to: openClaw.appendingPathComponent("openclaw.json"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .openclaw)

    XCTAssertFalse(status.hasConnection)
  }

  func testCommentedHermesMCPConfigDoesNotMarkHermesConnected() async throws {
    storeOwnedMCPKey()
    let hermes = tempHome.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: hermes, withIntermediateDirectories: true)
    try """
    mcp_servers:
    #  omi-memory:
    #    command: npx
    #    args: ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: hermes.appendingPathComponent("config.yaml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertFalse(status.hasConnection)
  }

  func testExistingHermesMCPConfigMarksHermesConnected() async throws {
    storeOwnedMCPKey()
    let hermes = tempHome.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: hermes, withIntermediateDirectories: true)
    try """
    mcp_servers:
      omi-memory:
        command: npx
        args: ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: hermes.appendingPathComponent("config.yaml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertTrue(status.isConfigured)
    XCTAssertTrue(status.hasConnection)
  }

  func testMCPKeyOwnedByDifferentUserDoesNotConfigureAgentPrompt() async {
    UserDefaults.standard.set("user-a", forKey: "auth_userId")
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    UserDefaults.standard.set("user-b", forKey: "memoryExportMCPApiKeyOwnerUserId")
    UserDefaults.standard.set(true, forKey: "localAgentAPIEnabled")
    UserDefaults.standard.set("local-token", forKey: "localAgentAPIToken")

    let status = await MemoryExportService.shared.status(for: .agents)

    XCTAssertFalse(status.isConfigured)
  }

  func testConfigDetectorReflectsFileChanges() async throws {
    storeOwnedMCPKey()
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    let config = codex.appendingPathComponent("config.toml")
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
    [mcp_servers.omi-memory]
    command = "npx"
    args = ["-y", "mcp-remote", "\(MemoryExportDestination.mcpServerURL)", "--header", "Authorization: Bearer test-key"]
    """.write(to: config, atomically: true, encoding: .utf8)

    XCTAssertTrue(MemoryExportConnectionDetector.hasExistingConnection(for: .codex, matchingKey: "test-key"))

    try """
    [mcp_servers.other]
    command = "npx"
    args = ["different-size"]
    """.write(to: config, atomically: true, encoding: .utf8)

    XCTAssertFalse(MemoryExportConnectionDetector.hasExistingConnection(for: .codex, matchingKey: "test-key"))
  }

  func testExportPaginationContinuesUntilShortPageWithoutSkipping() async throws {
    var requestedOffsets: [Int] = []
    let values: [Int] = try await MemoryExportService.fetchAllPages(pageSize: 2) { limit, offset in
      requestedOffsets.append(offset)
      let all = [1, 2, 3, 4, 5]
      return Array(all.dropFirst(offset).prefix(limit))
    }

    XCTAssertEqual(values, [1, 2, 3, 4, 5])
    XCTAssertEqual(requestedOffsets, [0, 2, 4])
  }

  func testExportCursorPaginationContinuesUntilNextCursorAbsent() async throws {
    var requestedCursors: [String?] = []
    let pages: [APIClient.MemoryListPage] = [
      APIClient.MemoryListPage(
        memories: [Self.sampleMemory(id: "m1"), Self.sampleMemory(id: "m2")],
        nextCursor: "cursor-a",
        canonicalLifecycleExposed: true,
        deviceScopeSupported: true,
        defaultMemoryDeleteSupported: true,
        truncated: false),
      APIClient.MemoryListPage(
        memories: [Self.sampleMemory(id: "m3")],
        nextCursor: nil,
        canonicalLifecycleExposed: true,
        deviceScopeSupported: true,
        defaultMemoryDeleteSupported: true,
        truncated: false),
    ]
    var pageIndex = 0
    let values = try await MemoryExportService.fetchAllCursorPages(pageSize: 2) { _, cursor in
      requestedCursors.append(cursor)
      defer { pageIndex += 1 }
      return pages[pageIndex]
    }

    XCTAssertEqual(values.map(\.id), ["m1", "m2", "m3"])
    XCTAssertEqual(requestedCursors.map { $0 ?? "<nil>" }, ["<nil>", "cursor-a"])
  }

  func testExportCursorPaginationRejectsRepeatedContinuationToken() async throws {
    let page = APIClient.MemoryListPage(
      memories: [Self.sampleMemory(id: "m1")],
      nextCursor: "cursor-a",
      canonicalLifecycleExposed: true,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: false)

    do {
      _ = try await MemoryExportService.fetchAllCursorPages(pageSize: 2) { _, _ in page }
      XCTFail("A repeated continuation token must not produce a partial successful export")
    } catch let error as MemoryExportError {
      guard case .requestFailed(let message) = error else {
        return XCTFail("Unexpected export error: \(error)")
      }
      XCTAssertTrue(message.contains("repeated a continuation token"))
    }
  }

  func testExportCursorPaginationRejectsTruncatedPage() async throws {
    let page = APIClient.MemoryListPage(
      memories: [Self.sampleMemory(id: "m1")],
      nextCursor: nil,
      canonicalLifecycleExposed: true,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: true)

    do {
      _ = try await MemoryExportService.fetchAllCursorPages(pageSize: 2) { _, _ in page }
      XCTFail("A truncated page must not produce a successful complete export")
    } catch let error as MemoryExportError {
      guard case .requestFailed(let message) = error else {
        return XCTFail("Unexpected export error: \(error)")
      }
      XCTAssertTrue(message.contains("truncated"))
    }
  }

  private static func sampleMemory(id: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "content-\(id)",
      category: .interesting,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 0),
      updatedAt: Date(timeIntervalSince1970: 0),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
      scoring: nil,
      source: "desktop",
      confidence: nil,
      sourceApp: nil,
      contextSummary: nil,
      isRead: false,
      isDismissed: false,
      tags: [],
      reasoning: nil,
      currentActivity: nil,
      inputDeviceName: nil,
      windowTitle: nil,
      headline: nil
    )
  }

  private func resetMemoryExportDefaults() {
    let defaults = UserDefaults.standard
    defaults.removeObject(forKey: "auth_userId")
    defaults.removeObject(forKey: "memoryExportMCPApiKey")
    defaults.removeObject(forKey: "memoryExportMCPApiKeyOwnerUserId")
    defaults.removeObject(forKey: "memoryExportMCPApiKeyCreatedAt")
    defaults.removeObject(forKey: "localAgentAPIEnabled")
    defaults.removeObject(forKey: "localAgentAPIToken")

    for destination in MemoryExportDestination.allCases {
      defaults.removeObject(forKey: "memoryExportExportedCount.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportLastExportedAt.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportDetail.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportLastExportPath.\(destination.rawValue)")
      defaults.removeObject(forKey: "memoryExportConnectedAt.\(destination.rawValue)")
    }
  }

  private func memoryExportDefaultsKey(_ prefix: String, destination: MemoryExportDestination) -> String {
    "\(prefix).\(destination.rawValue)"
  }

  private func storeOwnedMCPKey(userId: String = "test-user", key: String = "test-key") {
    UserDefaults.standard.set(userId, forKey: "auth_userId")
    UserDefaults.standard.set(key, forKey: "memoryExportMCPApiKey")
    UserDefaults.standard.set(userId, forKey: "memoryExportMCPApiKeyOwnerUserId")
  }
}
