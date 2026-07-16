import XCTest

@testable import Omi_Computer

final class MemoryExportStatusTests: XCTestCase {
  private var tempHome: URL!

  override func setUp() {
    super.setUp()
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

  private func storeOwnedMCPKey(userId: String = "test-user", key: String = "test-key") {
    UserDefaults.standard.set(userId, forKey: "auth_userId")
    UserDefaults.standard.set(key, forKey: "memoryExportMCPApiKey")
    UserDefaults.standard.set(userId, forKey: "memoryExportMCPApiKeyOwnerUserId")
  }
}
