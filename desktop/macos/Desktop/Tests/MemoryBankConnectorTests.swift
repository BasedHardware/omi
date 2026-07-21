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
    MemoryExportConnectionDetector.homeOverrideForTesting = tempHome
    MemoryBankConnector.claudeCLIPathOverrideForTesting = ""
    MemoryBankConnector.codexCLIPathOverrideForTesting = ""
    MemoryBankConnector.openClawCLIPathOverrideForTesting = try writeFakeOpenClawCLI().path
    MemoryBankConnector.processTimeoutSecondsForTesting = 5
  }

  override func tearDownWithError() throws {
    MemoryBankConnector.homeOverrideForTesting = nil
    MemoryExportConnectionDetector.homeOverrideForTesting = nil
    MemoryBankConnector.claudeCLIPathOverrideForTesting = nil
    MemoryBankConnector.codexCLIPathOverrideForTesting = nil
    MemoryBankConnector.openClawCLIPathOverrideForTesting = nil
    MemoryBankConnector.processTimeoutSecondsForTesting = nil
    if let tempHome {
      try? FileManager.default.removeItem(at: tempHome)
    }
    try super.tearDownWithError()
  }

  func testClaudeCodeConnectWritesUserScopedMCPServer() throws {
    let config = tempHome.appendingPathComponent(".claude.json")
    try """
    {
      "theme": "dark",
      "mcpServers": {
        "other": {
          "type": "http",
          "url": "https://example.com/mcp"
        }
      }
    }
    """.write(to: config, atomically: true, encoding: .utf8)

    let message = try MemoryBankConnector.connect(.claudeCode, key: "test-key")

    let data = try Data(contentsOf: config)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let servers = try XCTUnwrap(json["mcpServers"] as? [String: Any])
    let omi = try XCTUnwrap(servers["omi-memory"] as? [String: Any])
    let headers = try XCTUnwrap(omi["headers"] as? [String: Any])
    XCTAssertEqual(message, "Claude Code is now connected.")
    XCTAssertEqual(json["theme"] as? String, "dark")
    XCTAssertEqual(omi["type"] as? String, "http")
    XCTAssertEqual(omi["url"] as? String, MemoryExportDestination.mcpServerURL)
    XCTAssertEqual(headers["Authorization"] as? String, "Bearer test-key")
    XCTAssertNotNil(servers["other"])
    XCTAssertTrue(MemoryExportConnectionDetector.hasExistingConnection(for: .claudeCode, matchingKey: "test-key"))

    let backups = try FileManager.default.contentsOfDirectory(
      at: tempHome.appendingPathComponent(".claude/backups", isDirectory: true),
      includingPropertiesForKeys: nil)
    XCTAssertEqual(backups.count, 1)
  }

  func testClaudeCodeConnectUpdatesExistingOmiServerKey() throws {
    let config = tempHome.appendingPathComponent(".claude.json")
    try """
    {
      "mcpServers": {
        "omi-memory": {
          "type": "http",
          "url": "\(MemoryExportDestination.mcpServerURL)",
          "headers": {
            "Authorization": "Bearer old-key"
          }
        }
      }
    }
    """.write(to: config, atomically: true, encoding: .utf8)

    let message = try MemoryBankConnector.connect(.claudeCode, key: "new-key")

    let data = try Data(contentsOf: config)
    let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let servers = try XCTUnwrap(json["mcpServers"] as? [String: Any])
    let omi = try XCTUnwrap(servers["omi-memory"] as? [String: Any])
    let headers = try XCTUnwrap(omi["headers"] as? [String: Any])
    XCTAssertEqual(message, "Claude Code is now connected.")
    XCTAssertEqual(headers["Authorization"] as? String, "Bearer new-key")
    XCTAssertTrue(MemoryExportConnectionDetector.hasExistingConnection(for: .claudeCode, matchingKey: "new-key"))
    XCTAssertFalse(MemoryExportConnectionDetector.hasExistingConnection(for: .claudeCode, matchingKey: "old-key"))
  }

  func testClaudeCodeConfigBackupsAreBounded() throws {
    let config = tempHome.appendingPathComponent(".claude.json")
    try """
    {
      "theme": "dark"
    }
    """.write(to: config, atomically: true, encoding: .utf8)

    for index in 0..<7 {
      _ = try MemoryBankConnector.connect(.claudeCode, key: "key-\(index)")
    }

    let backups = try FileManager.default.contentsOfDirectory(
      at: tempHome.appendingPathComponent(".claude/backups", isDirectory: true),
      includingPropertiesForKeys: nil)
    XCTAssertEqual(backups.count, 5)
  }

  func testClaudeCodeConnectRequiresInstallEvidence() throws {
    XCTAssertThrowsError(try MemoryBankConnector.connect(.claudeCode, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("Claude Code is not installed"))
    }
  }

  func testCodexConnectRunsNativeMCPAdd() throws {
    MemoryBankConnector.codexCLIPathOverrideForTesting = try writeFakeCodexCLI().path

    let message = try MemoryBankConnector.connect(.codex, key: "test-key")

    let config = tempHome.appendingPathComponent(".codex/config.toml")
    let content = try String(contentsOf: config, encoding: .utf8)
    XCTAssertEqual(message, "Codex is now connected.")
    XCTAssertTrue(content.contains("[mcp_servers.omi-memory]"))
    XCTAssertTrue(content.contains(#"command = "npx""#))
    XCTAssertTrue(content.contains(MemoryExportDestination.mcpServerURL))
    XCTAssertTrue(content.contains("Authorization: Bearer test-key"))
    XCTAssertTrue(MemoryExportConnectionDetector.hasExistingConnection(for: .codex, matchingKey: "test-key"))
  }

  func testCodexConnectRequiresCLI() throws {
    XCTAssertThrowsError(try MemoryBankConnector.connect(.codex, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("Codex is not available"))
    }
  }

  func testCodexConnectRedactsTokenFromCLIError() throws {
    let cli = tempHome.appendingPathComponent("echoing-codex")
    try """
    #!/bin/sh
    echo "bad args: $*" >&2
    exit 1
    """.write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    MemoryBankConnector.codexCLIPathOverrideForTesting = cli.path

    XCTAssertThrowsError(try MemoryBankConnector.connect(.codex, key: "secret-token")) { error in
      XCTAssertFalse(error.localizedDescription.contains("secret-token"), error.localizedDescription)
      XCTAssertTrue(error.localizedDescription.contains("Bearer [redacted]"), error.localizedDescription)
    }
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
      "OpenClaw is now connected.")
    XCTAssertTrue(soulContent.contains(MemoryBankConnector.marker))
    XCTAssertTrue(soulContent.contains("omi-memory__search_memories"))
    XCTAssertTrue(soulContent.contains("Do not substitute OpenClaw's local `memory_search`"))
    XCTAssertFalse(soulContent.contains("test-key"))
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
    XCTAssertTrue(configContent.contains(#""transport":"streamable-http""#))
    XCTAssertTrue(configContent.contains(#""Authorization":"Bearer test-key""#))
  }

  func testOpenClawConnectUsesCLIForJSON5Config() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let configDir = tempHome.appendingPathComponent(".openclaw", isDirectory: true)
    try FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
    let config = configDir.appendingPathComponent("openclaw.json")
    try """
    {
      agents: { defaults: { workspace: "\(workspace.path)" } },
    }
    """.write(to: config, atomically: true, encoding: .utf8)
    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
    XCTAssertTrue(configContent.contains(#""transport":"streamable-http""#))
    XCTAssertTrue(configContent.contains(#""Authorization":"Bearer test-key""#))
    XCTAssertTrue(FileManager.default.fileExists(atPath: workspace.appendingPathComponent("SOUL.md").path))
  }

  func testOpenClawConnectUsesSiblingNodeForEnvLauncher() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace)
    let install = tempHome.appendingPathComponent(".hermes/node/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: install, withIntermediateDirectories: true)
    let cli = install.appendingPathComponent("openclaw")
    let node = install.appendingPathComponent("node")
    try "#!/usr/bin/env definitely-missing-node\n".write(to: cli, atomically: true, encoding: .utf8)
    try """
    #!/bin/sh
    shift
    if [ "$1" = "mcp" ] && [ "$2" = "show" ]; then
      exit 1
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "set" ] && [ "$3" = "omi-memory" ]; then
      printf '{"mcp":{"servers":{"omi-memory":%s}}}\\n' "$4" > "$OPENCLAW_CONFIG_PATH"
      exit 0
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "reload" ]; then
      exit 0
    fi
    echo "unexpected arguments: $*" >&2
    exit 2
    """.write(to: node, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: node.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
    XCTAssertTrue(configContent.contains(#""Authorization":"Bearer test-key""#))
  }

  func testOpenClawConnectDiscoversCommonUserBinInstall() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace)
    let bin = tempHome.appendingPathComponent(".local/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    let cli = bin.appendingPathComponent("openclaw")
    try fakeOpenClawScript().write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = nil

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
  }

  func testOpenClawConnectFindsNodeFromVersionManagerPath() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace)
    let cliBin = tempHome.appendingPathComponent(".local/bin", isDirectory: true)
    let nodeBin = tempHome.appendingPathComponent(".nvm/versions/node/v22.0.0/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: cliBin, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: nodeBin, withIntermediateDirectories: true)
    let cli = cliBin.appendingPathComponent("openclaw")
    let node = nodeBin.appendingPathComponent("node")
    try "#!/usr/bin/env node\n".write(to: cli, atomically: true, encoding: .utf8)
    try nodeBackedFakeOpenClawScript().write(to: node, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: node.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
  }

  func testOpenClawConnectFindsNodeFromXDGFnmPath() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace)
    let cliBin = tempHome.appendingPathComponent(".local/bin", isDirectory: true)
    let nodeBin = tempHome.appendingPathComponent(
      ".local/share/fnm/node-versions/v22.0.0/installation/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: cliBin, withIntermediateDirectories: true)
    try FileManager.default.createDirectory(at: nodeBin, withIntermediateDirectories: true)
    let cli = cliBin.appendingPathComponent("openclaw")
    let node = nodeBin.appendingPathComponent("node")
    try "#!/usr/bin/env node\n".write(to: cli, atomically: true, encoding: .utf8)
    try nodeBackedFakeOpenClawScript().write(to: node, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: node.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
  }

  func testOpenClawConnectDoesNotRunShellShimThroughSiblingNode() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace)
    let bin = tempHome.appendingPathComponent(".volta/bin", isDirectory: true)
    try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
    let cli = bin.appendingPathComponent("openclaw")
    let node = bin.appendingPathComponent("node")
    try fakeOpenClawScript().write(to: cli, atomically: true, encoding: .utf8)
    try "#!/bin/sh\necho should-not-wrap-openclaw-shim >&2\nexit 9\n".write(to: node, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: node.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = nil

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""omi-memory""#))
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

  func testOpenClawConnectExpandsHomeInConfiguredWorkspace() throws {
    let workspace = tempHome.appendingPathComponent("custom-openclaw-workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let configDir = tempHome.appendingPathComponent(".openclaw", isDirectory: true)
    try FileManager.default.createDirectory(at: configDir, withIntermediateDirectories: true)
    let config = configDir.appendingPathComponent("openclaw.json")
    try """
    {
      "agents": {
        "defaults": {
          "workspace": "${HOME}/custom-openclaw-workspace"
        }
      }
    }
    """.write(to: config, atomically: true, encoding: .utf8)

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    XCTAssertTrue(FileManager.default.fileExists(atPath: workspace.appendingPathComponent("SOUL.md").path))
  }

  func testOpenClawConnectRejectsMalformedMCPConfig() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    let config = try writeOpenClawConfig(workspace: workspace, extra: #","mcp":[]"#)

    XCTAssertThrowsError(try MemoryBankConnector.connect(.openclaw, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("OpenClaw rejected the connection update"))
      XCTAssertTrue(error.localizedDescription.contains("expected object"))
    }
    let configContent = try String(contentsOf: config, encoding: .utf8)
    XCTAssertTrue(configContent.contains(#""mcp":[]"#))
    XCTAssertFalse(configContent.contains("omi-memory"))
  }

  func testOpenClawConnectRedactsTokenFromCLIError() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    _ = try writeOpenClawConfig(workspace: workspace)
    let cli = tempHome.appendingPathComponent("echoing-openclaw")
    try """
    #!/bin/sh
    if [ "$1" = "mcp" ] && [ "$2" = "show" ]; then
      exit 1
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "set" ]; then
      echo "rejected payload $4" >&2
      exit 1
    fi
    exit 0
    """.write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path

    XCTAssertThrowsError(try MemoryBankConnector.connect(.openclaw, key: "secret-token")) { error in
      XCTAssertFalse(error.localizedDescription.contains("secret-token"), error.localizedDescription)
      XCTAssertTrue(error.localizedDescription.contains("Bearer [redacted]"), error.localizedDescription)
    }
  }

  func testOpenClawConnectTimesOutHungCLI() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    _ = try writeOpenClawConfig(workspace: workspace)
    let cli = tempHome.appendingPathComponent("hung-openclaw")
    try "#!/bin/sh\nsleep 5\n".write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path
    MemoryBankConnector.processTimeoutSecondsForTesting = 0.2

    XCTAssertThrowsError(try MemoryBankConnector.connect(.openclaw, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("timed out"), error.localizedDescription)
    }
  }

  func testOpenClawConnectReloadsMCPRuntimeAfterConfigUpdate() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    _ = try writeOpenClawConfig(workspace: workspace)
    let reloadMarker = tempHome.appendingPathComponent("openclaw-reloaded")
    let cli = tempHome.appendingPathComponent("reload-openclaw")
    try """
    #!/bin/sh
    if [ "$1" = "mcp" ] && [ "$2" = "show" ]; then
      exit 1
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "set" ] && [ "$3" = "omi-memory" ]; then
      printf '{"mcp":{"servers":{"omi-memory":%s}}}\\n' "$4" > "$OPENCLAW_CONFIG_PATH"
      exit 0
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "reload" ]; then
      touch "\(reloadMarker.path)"
      exit 0
    fi
    echo "unexpected arguments: $*" >&2
    exit 2
    """.write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path

    _ = try MemoryBankConnector.connect(.openclaw, key: "test-key")

    XCTAssertTrue(FileManager.default.fileExists(atPath: reloadMarker.path))
  }

  func testOpenClawConnectSurfacesReloadFailure() throws {
    let workspace = tempHome.appendingPathComponent(".openclaw/workspace", isDirectory: true)
    try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
    _ = try writeOpenClawConfig(workspace: workspace)
    let cli = tempHome.appendingPathComponent("reload-failing-openclaw")
    try """
    #!/bin/sh
    if [ "$1" = "mcp" ] && [ "$2" = "show" ]; then
      exit 1
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "set" ] && [ "$3" = "omi-memory" ]; then
      printf '{"mcp":{"servers":{"omi-memory":%s}}}\\n' "$4" > "$OPENCLAW_CONFIG_PATH"
      exit 0
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "reload" ]; then
      echo "reload unavailable" >&2
      exit 7
    fi
    echo "unexpected arguments: $*" >&2
    exit 2
    """.write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    MemoryBankConnector.openClawCLIPathOverrideForTesting = cli.path

    XCTAssertThrowsError(try MemoryBankConnector.connect(.openclaw, key: "test-key")) { error in
      XCTAssertTrue(error.localizedDescription.contains("OpenClaw MCP config was updated"))
      XCTAssertTrue(error.localizedDescription.contains("reload unavailable"))
    }
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
    XCTAssertEqual(message, "Hermes is now connected.")
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

  func testHermesConnectRecognizesFormattedMCPServersKey() throws {
    let hermes = try writeHermesInstall(
      config: """
        model:
          default: test
        mcp_servers:  # local tools
          other-tool:
            command: other
        """
    )

    _ = try MemoryBankConnector.connect(.hermes, key: "test-key")

    let config = try String(contentsOf: hermes.appendingPathComponent("config.yaml"), encoding: .utf8)
    XCTAssertEqual(config.components(separatedBy: "mcp_servers:").count - 1, 1)
    XCTAssertTrue(config.contains("Authorization: Bearer test-key"))
    XCTAssertTrue(config.contains("other-tool:"))
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

  private func writeFakeOpenClawCLI() throws -> URL {
    let cli = tempHome.appendingPathComponent("openclaw")
    try fakeOpenClawScript().write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    return cli
  }

  private func writeFakeCodexCLI() throws -> URL {
    let cli = tempHome.appendingPathComponent("codex")
    try """
    #!/bin/sh
    if [ "$1" = "mcp" ] && [ "$2" = "add" ] && [ "$3" = "omi-memory" ]; then
      mkdir -p "$CODEX_HOME"
      cat > "$CODEX_HOME/config.toml" <<EOF
    [mcp_servers.omi-memory]
    command = "npx"
    args = ["-y", "mcp-remote", "$8", "--header", "${10}"]
    EOF
      exit 0
    fi
    echo "unexpected arguments: $*" >&2
    exit 2
    """.write(to: cli, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
    return cli
  }

  private func fakeOpenClawScript() -> String {
    """
    #!/bin/sh
    if [ "$1" = "mcp" ] && [ "$2" = "show" ]; then
      exit 1
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "set" ] && [ "$3" = "omi-memory" ]; then
      if grep -Fq '"mcp":[]' "$OPENCLAW_CONFIG_PATH"; then
        echo "mcp: Invalid input: expected object, received array" >&2
        exit 1
      fi
      printf '{"mcp":{"servers":{"omi-memory":%s}}}\\n' "$4" > "$OPENCLAW_CONFIG_PATH"
      exit 0
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "reload" ]; then
      exit 0
    fi
    echo "unexpected arguments: $*" >&2
    exit 2
    """
  }

  private func nodeBackedFakeOpenClawScript() -> String {
    """
    #!/bin/sh
    shift
    if [ "$1" = "mcp" ] && [ "$2" = "show" ]; then
      exit 1
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "set" ] && [ "$3" = "omi-memory" ]; then
      printf '{"mcp":{"servers":{"omi-memory":%s}}}\\n' "$4" > "$OPENCLAW_CONFIG_PATH"
      exit 0
    fi
    if [ "$1" = "mcp" ] && [ "$2" = "reload" ]; then
      exit 0
    fi
    echo "unexpected arguments: $*" >&2
    exit 2
    """
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
