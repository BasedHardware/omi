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

  func testStoredMCPKeyDoesNotMarkAgentDestinationsConnected() async {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")

    let codexStatus = await MemoryExportService.shared.status(for: .codex)
    let claudeCodeStatus = await MemoryExportService.shared.status(for: .claudeCode)

    XCTAssertTrue(codexStatus.isConfigured)
    XCTAssertTrue(claudeCodeStatus.isConfigured)
    XCTAssertFalse(codexStatus.hasConnection)
    XCTAssertFalse(claudeCodeStatus.hasConnection)
  }

  func testMarkConnectedIsPerDestination() async {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")

    await MemoryExportService.shared.markConnected(.openclaw)

    let openClawStatus = await MemoryExportService.shared.status(for: .openclaw)
    let hermesStatus = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertTrue(openClawStatus.hasConnection)
    XCTAssertFalse(hermesStatus.hasConnection)
  }

  func testMemoryPackExportStillCountsAsConnectionHistory() async {
    UserDefaults.standard.set(7, forKey: "memoryExportExportedCount.claude")

    let status = await MemoryExportService.shared.status(for: .claude)

    XCTAssertTrue(status.isConfigured)
    XCTAssertTrue(status.hasConnection)
  }

  func testExistingCodexMCPConfigMarksCodexConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
      [mcp_servers.omi-memory]
      command = "npx"
      args = ["-y", "mcp-remote", "https://api.omi.me/v1/mcp/sse", "--header", "Authorization: Bearer test-key"]
      """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    let codexStatus = await MemoryExportService.shared.status(for: .codex)
    let chatGPTStatus = await MemoryExportService.shared.status(for: .chatgpt)

    XCTAssertTrue(codexStatus.isConfigured)
    XCTAssertTrue(codexStatus.hasConnection)
    XCTAssertFalse(chatGPTStatus.hasConnection)
  }

  func testCommentedCodexMCPConfigDoesNotMarkCodexConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    let codex = tempHome.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codex, withIntermediateDirectories: true)
    try """
      # [mcp_servers.omi-memory]
      # command = "npx"
      # args = ["-y", "mcp-remote", "https://api.omi.me/v1/mcp/sse", "--header", "Authorization: Bearer test-key"]
      """.write(to: codex.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .codex)

    XCTAssertFalse(status.hasConnection)
  }

  func testExistingClaudeMCPConfigMarksClaudeCodeConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    try """
      {
        "mcpServers": {
          "omi-memory": {
            "type": "http",
            "url": "https://api.omiapi.com/v1/mcp/sse"
          }
        }
      }
      """.write(to: tempHome.appendingPathComponent(".claude.json"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .claudeCode)

    XCTAssertTrue(status.isConfigured)
    XCTAssertTrue(status.hasConnection)
  }

  func testClaudeDesktopConfigMarksClaudeNotClaudeCodeConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    let claudeDesktop = tempHome.appendingPathComponent(
      "Library/Application Support/Claude", isDirectory: true)
    try FileManager.default.createDirectory(at: claudeDesktop, withIntermediateDirectories: true)
    try """
      {
        "mcpServers": {
          "omi-memory": {
            "type": "http",
            "url": "https://api.omi.me/v1/mcp/sse"
          }
        }
      }
      """.write(to: claudeDesktop.appendingPathComponent("claude_desktop_config.json"), atomically: true, encoding: .utf8)

    let claudeStatus = await MemoryExportService.shared.status(for: .claude)
    let claudeCodeStatus = await MemoryExportService.shared.status(for: .claudeCode)

    XCTAssertTrue(claudeStatus.isConfigured)
    XCTAssertTrue(claudeStatus.hasConnection)
    XCTAssertTrue(claudeCodeStatus.isConfigured)
    XCTAssertFalse(claudeCodeStatus.hasConnection)
  }

  func testDisabledOpenClawMCPConfigDoesNotMarkOpenClawConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    let openClaw = tempHome.appendingPathComponent(".openclaw", isDirectory: true)
    try FileManager.default.createDirectory(at: openClaw, withIntermediateDirectories: true)
    try """
      {
        "mcp": {
          "servers": {
            "omi-memory": {
              "enabled": false,
              "url": "https://api.omi.me/v1/mcp/sse"
            }
          }
        }
      }
      """.write(to: openClaw.appendingPathComponent("openclaw.json"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .openclaw)

    XCTAssertFalse(status.hasConnection)
  }

  func testCommentedHermesMCPConfigDoesNotMarkHermesConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    let hermes = tempHome.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: hermes, withIntermediateDirectories: true)
    try """
      mcp_servers:
      #  omi-memory:
      #    command: npx
      #    args: ["-y", "mcp-remote", "https://api.omi.me/v1/mcp/sse", "--header", "Authorization: Bearer test-key"]
      """.write(to: hermes.appendingPathComponent("config.yaml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertFalse(status.hasConnection)
  }

  func testExistingHermesMCPConfigMarksHermesConnected() async throws {
    UserDefaults.standard.set("test-key", forKey: "memoryExportMCPApiKey")
    let hermes = tempHome.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: hermes, withIntermediateDirectories: true)
    try """
      mcp_servers:
        omi-memory:
          command: npx
          args: ["-y", "mcp-remote", "https://api.omi.me/v1/mcp/sse", "--header", "Authorization: Bearer test-key"]
      """.write(to: hermes.appendingPathComponent("config.yaml"), atomically: true, encoding: .utf8)

    let status = await MemoryExportService.shared.status(for: .hermes)

    XCTAssertTrue(status.hasConnection)
  }

  private func resetMemoryExportDefaults() {
    let defaults = UserDefaults.standard
    defaults.removeObject(forKey: "memoryExportMCPApiKey")
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
}
