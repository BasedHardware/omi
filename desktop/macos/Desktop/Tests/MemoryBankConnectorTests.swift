import XCTest

@testable import Omi_Computer

final class MemoryBankConnectorTests: XCTestCase {
  private var tempHome: URL!

  override func setUpWithError() throws {
    try super.setUpWithError()
    tempHome = FileManager.default.temporaryDirectory
      .appendingPathComponent("memory-bank-connector-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)
    MemoryBankConnector.homeOverrideForTesting = tempHome
  }

  override func tearDownWithError() throws {
    MemoryBankConnector.homeOverrideForTesting = nil
    if let tempHome {
      try? FileManager.default.removeItem(at: tempHome)
    }
    try super.tearDownWithError()
  }

  func testOpenClawConnectWritesMCPConfigAndSoulNote() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace)

    let message = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let soul = workspace.appendingPathComponent("SOUL.md")
    let soulContent = try String(contentsOf: soul, encoding: .utf8)
    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertEqual(
      message,
      "Connected OpenClaw — added the Omi MCP to openclaw.json and a 'search Omi first' note to SOUL.md.")
    XCTAssertTrue(soulContent.contains(MemoryBankConnector.marker))
    XCTAssertTrue(soulContent.contains("The `omi-memory` MCP server is configured for you"))
    XCTAssertFalse(soulContent.contains("test-key"))
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
    XCTAssertTrue(configContent.contains(#""transport" : "sse""#))
    XCTAssertTrue(configContent.contains(#""Authorization" : "Bearer test-key""#))
  }

  func testOpenClawConnectUsesConfiguredWorkspaceForSoulNote() throws {
    let workspace = tempHome.appendingPathComponent("custom-openclaw-workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    _ = try writeOpenClawConfig(workspace: workspace)

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    XCTAssertTrue(FileManager.default.fileExists(atPath: workspace.appendingPathComponent("SOUL.md").path))
    XCTAssertFalse(
      FileManager.default.fileExists(
        atPath: tempHome.appendingPathComponent(".openclaw/workspace/SOUL.md").path))
  }

  func testOpenClawConnectRejectsMalformedMCPConfig() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace, extra: #","mcp":[]"#)

    XCTAssertThrowsError(try MemoryBankConnector.connect(.openclaw, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("non-object mcp value"))
    }
    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""mcp":[]"#))
    XCTAssertFalse(configContent.contains("omi-memory"))
  }

  func testHermesConnectRequiresRealInstallEvidence() throws {
    let hermes = tempHome.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(at: hermes, withIntermediateDirectories: true)

    XCTAssertThrowsError(try MemoryBankConnector.connect(.hermes, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("Hermes not found locally"))
    }
    XCTAssertFalse(FileManager.default.fileExists(atPath: hermes.appendingPathComponent("config.yaml").path))
    XCTAssertFalse(FileManager.default.fileExists(atPath: hermes.appendingPathComponent("SOUL.md").path))
  }

  func testHermesConnectWritesConfigAndSoulForInstalledHermes() throws {
    let hermes = try writeHermesInstall()

    let message = try MemoryBankConnector.connect(.hermes, key: "test-key")

    let config = try String(contentsOf: hermes.appendingPathComponent("config.yaml"), encoding: .utf8)
    let soul = try String(contentsOf: hermes.appendingPathComponent("SOUL.md"), encoding: .utf8)
    XCTAssertEqual(message, "Connected Hermes — added the Omi MCP to config.yaml and a 'search Omi first' note to SOUL.md.")
    XCTAssertTrue(config.contains("omi-memory:"))
    XCTAssertTrue(config.contains("Authorization: Bearer test-key"))
    XCTAssertTrue(soul.contains(MemoryBankConnector.marker))
    XCTAssertTrue(soul.contains("The `omi-memory` MCP server is configured for you"))
    XCTAssertFalse(soul.contains("test-key"))
  }

  func testHermesConnectReplacesStaleOmiMemoryEntry() throws {
    let hermes = try writeHermesInstall(
      config: """
        model:
          default: test
        mcp_servers:
          omi-memory:
            command: npx
            args: ["-y", "mcp-remote", "https://old.example/v1/mcp/sse", "--header", "Authorization: Bearer old-key"]
        """
    )

    _ = try MemoryBankConnector.connect(.hermes, key: "new-key")

    let config = try String(contentsOf: hermes.appendingPathComponent("config.yaml"), encoding: .utf8)
    XCTAssertTrue(config.contains("Authorization: Bearer new-key"))
    XCTAssertFalse(config.contains("old-key"))
    XCTAssertFalse(config.contains("https://old.example"))
  }

  func testHermesConnectAlwaysWritesSoulNotAgentsFallback() throws {
    let hermes = try writeHermesInstall()
    try "legacy agents prompt".write(
      to: hermes.appendingPathComponent("AGENTS.md"),
      atomically: true,
      encoding: .utf8)

    _ = try MemoryBankConnector.connect(.hermes, key: "test-key")

    let uppercaseSoul = try String(contentsOf: hermes.appendingPathComponent("SOUL.md"), encoding: .utf8)
    let agents = try String(contentsOf: hermes.appendingPathComponent("AGENTS.md"), encoding: .utf8)
    XCTAssertTrue(uppercaseSoul.contains(MemoryBankConnector.marker))
    XCTAssertEqual(agents, "legacy agents prompt")
  }

  private func writeOpenClawConfig(workspace: URL, extra: String = "") throws -> URL {
    let configDir = tempHome.appendingPathComponent(".openclaw", isDirectory: true)
    try FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
    let config = """
      {
        "agents": {
          "defaults": {
            "workspace": "\(workspace.path)"
          }
        }\(extra)
      }
      """
    let url = configDir.appendingPathComponent("openclaw.json")
    try config.write(to: url, atomically: true, encoding: .utf8)
    return url
  }

  private func writeHermesInstall(config: String = "model:\n  default: test\n") throws -> URL {
    let hermes = tempHome.appendingPathComponent(".hermes", isDirectory: true)
    try FileManager.default.createDirectory(
      at: hermes.appendingPathComponent("hermes-agent", isDirectory: true),
      withIntermediateDirectories: true)
    try config.write(
      to: hermes.appendingPathComponent("config.yaml"),
      atomically: true,
      encoding: .utf8)
    try #"{"name":"hermes-agent"}"#.write(
      to: hermes.appendingPathComponent("hermes-agent/package.json"),
      atomically: true,
      encoding: .utf8)
    return hermes
  }
}
