import Foundation

/// Deterministic, local "Do it for me" for agent frameworks that store their
/// memory/config as plain files (OpenClaw, Hermes). Unlike the cloud
/// connectors, these don't have a CLI like `claude mcp add`, and delegating to
/// the in-app agent proved unreliable (it doesn't reliably fire a file-write
/// tool). So we write the Omi memory bank ourselves — idempotently — exactly
/// the way Codex's config.toml block is written.
enum MemoryBankConnector {
  static let marker = "omi-memory-bank"
  private static var mcpURL: String { MemoryExportDestination.mcpServerURL }

  enum ConnectError: LocalizedError {
    case notInstalled(String)
    case invalidConfig(String)
    var errorDescription: String? {
      switch self {
      case .notInstalled(let msg): return msg
      case .invalidConfig(let msg): return msg
      }
    }
  }

  /// Whether this destination connects via a local file write here.
  static func handles(_ destination: MemoryExportDestination) -> Bool {
    destination == .openclaw || destination == .hermes
  }

  /// Performs the write. Returns a short user-facing success line. Throws
  /// `ConnectError.notInstalled` when the framework isn't found locally.
  @discardableResult
  static func connect(_ destination: MemoryExportDestination, key: String) throws -> String {
    switch destination {
    case .openclaw: return try connectOpenClaw(key: key)
    case .hermes: return try connectHermes(key: key)
    default: throw ConnectError.notInstalled("\(destination.title) is not a local memory-bank target.")
    }
  }

  static var homeOverrideForTesting: URL?
  private static var home: URL { homeOverrideForTesting ?? FileManager.default.homeDirectoryForCurrentUser }

  // MARK: - OpenClaw (mcp.servers + workspace SOUL.md)

  private static func connectOpenClaw(key: String) throws -> String {
    let fm = FileManager.default
    let config = home.appendingPathComponent(".openclaw/openclaw.json")
    guard fm.fileExists(atPath: config.path) else {
      throw ConnectError.notInstalled(
        "OpenClaw not found locally (looked for ~/.openclaw/openclaw.json). Install OpenClaw, then try again.")
    }
    let workspace = openClawConfiguredWorkspace(configURL: config) ?? home.appendingPathComponent(".openclaw/workspace")
    guard fm.fileExists(atPath: workspace.path) else {
      throw ConnectError.notInstalled(
        "OpenClaw workspace not found (looked for \(displayPath(for: workspace))). Run OpenClaw setup, then try again.")
    }

    let alreadyWired = try ensureOpenClawMCPConfig(configURL: config, key: key)
    let noteAdded = try ensureOpenClawSoulNote(workspace: workspace)

    if alreadyWired {
      return noteAdded
        ? "OpenClaw already had the Omi MCP — added the 'search Omi first' note to \(displayPath(for: workspace.appendingPathComponent("SOUL.md")))."
        : "OpenClaw already connected — Omi MCP in openclaw.json, note in SOUL.md."
    }
    return "Connected OpenClaw — added the Omi MCP to openclaw.json and a 'search Omi first' note to SOUL.md."
  }

  private static func openClawConfiguredWorkspace(configURL: URL) -> URL? {
    guard
      let data = try? Data(contentsOf: configURL),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let agents = json["agents"] as? [String: Any],
      let defaults = agents["defaults"] as? [String: Any],
      let workspace = defaults["workspace"] as? String,
      !workspace.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return nil
    }
    let expanded = workspace.replacingOccurrences(of: "~", with: home.path, options: .anchored)
    return URL(fileURLWithPath: expanded)
  }

  @discardableResult
  private static func ensureOpenClawMCPConfig(configURL: URL, key: String) throws -> Bool {
    let data = try Data(contentsOf: configURL)
    guard var json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw ConnectError.notInstalled("OpenClaw config is not a JSON object: \(displayPath(for: configURL)).")
    }

    let server = openClawMCPServer(key: key)
    var mcp: [String: Any]
    if let existingMCP = json["mcp"] {
      guard let existingMCP = existingMCP as? [String: Any] else {
        throw ConnectError.invalidConfig("OpenClaw config has non-object mcp value in \(displayPath(for: configURL)).")
      }
      mcp = existingMCP
    } else {
      mcp = [:]
    }
    var servers: [String: Any]
    if let existingServers = mcp["servers"] {
      guard let existingServers = existingServers as? [String: Any] else {
        throw ConnectError.invalidConfig("OpenClaw config has non-object mcp.servers value in \(displayPath(for: configURL)).")
      }
      servers = existingServers
    } else {
      servers = [:]
    }
    let existing = servers["omi-memory"] as? [String: Any]
    if NSDictionary(dictionary: existing ?? [:]).isEqual(to: server) {
      return true
    }
    servers["omi-memory"] = server
    mcp["servers"] = servers
    json["mcp"] = mcp

    let output = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted, .withoutEscapingSlashes])
    try output.write(to: configURL, options: .atomic)
    return false
  }

  private static func openClawMCPServer(key: String) -> [String: Any] {
    [
      "enabled": true,
      "url": mcpURL,
      "transport": "sse",
      "headers": [
        "Authorization": "Bearer \(key)"
      ],
    ]
  }

  @discardableResult
  private static func ensureOpenClawSoulNote(workspace: URL) throws -> Bool {
    let url = workspace.appendingPathComponent("SOUL.md")
    var soul = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    if soul.contains(marker) { return false }
    if !soul.isEmpty && !soul.hasSuffix("\n") { soul += "\n" }
    soul += "\n" + openClawSoulBlock() + "\n"
    let isSymlink = (try? FileManager.default.destinationOfSymbolicLink(atPath: url.path)) != nil
    try soul.write(to: url, atomically: !isSymlink, encoding: .utf8)
    return true
  }

  private static func displayPath(for url: URL) -> String {
    let homePath = home.standardizedFileURL.path
    let path = url.standardizedFileURL.path
    if path == homePath { return "~" }
    if path.hasPrefix(homePath + "/") {
      return "~/" + String(path.dropFirst(homePath.count + 1))
    }
    return path
  }

  private static func openClawSoulBlock() -> String {
    """
    <!-- \(marker) -->
    ## OMI memory (search FIRST)
    Omi is your memory bank. Before any task, search Omi memory first for context, then save durable new facts back to it. The `omi-memory` MCP server is configured for you — use it.
    <!-- /\(marker) -->
    """
  }

  // MARK: - Hermes (config.yaml mcp_servers)

  private static func connectHermes(key: String) throws -> String {
    let fm = FileManager.default
    let hermesDir = home.appendingPathComponent(".hermes")
    guard hermesInstallIsPresent(hermesDir: hermesDir, fileManager: fm) else {
      throw ConnectError.notInstalled(
        "Hermes not found locally (looked for ~/.hermes/config.yaml and Hermes install files). Install Hermes, then try again.")
    }

    // 1. Wire the Omi memory MCP into config.yaml (idempotent).
    let cfg = hermesDir.appendingPathComponent("config.yaml")
    var content = (try? String(contentsOf: cfg, encoding: .utf8)) ?? ""
    let alreadyWired = hermesEntryIsCurrent(content: content, key: key)
    if !alreadyWired {
      content = try upsertHermesEntry(content: content, key: key, configURL: cfg)
      try content.write(to: cfg, atomically: true, encoding: .utf8)
    }

    // 2. Tell the agent to *use* it — append a "search Omi first" note to the
    //    Hermes system prompt (SOUL.md), matching OpenClaw's memory file. Having
    //    the tool isn't enough; this makes the agent prefer Omi memory.
    let noteAdded = try ensureHermesSoulNote(hermesDir: hermesDir)

    if alreadyWired {
      return noteAdded
        ? "Hermes already had the Omi MCP — added the 'search Omi first' note to SOUL.md."
        : "Hermes already connected — Omi MCP in config.yaml, note in SOUL.md."
    }
    return "Connected Hermes — added the Omi MCP to config.yaml and a 'search Omi first' note to SOUL.md."
  }

  private static func hermesInstallIsPresent(hermesDir: URL, fileManager fm: FileManager) -> Bool {
    var isDirectory: ObjCBool = false
    guard fm.fileExists(atPath: hermesDir.path, isDirectory: &isDirectory), isDirectory.boolValue else {
      return false
    }
    guard fm.fileExists(atPath: hermesDir.appendingPathComponent("config.yaml").path) else {
      return false
    }
    if hermesPackageLooksInstalled(hermesDir: hermesDir) { return true }
    let evidence = [
      ".install_method",
      "hermes-agent/hermes",
    ]
    return evidence.contains { fm.fileExists(atPath: hermesDir.appendingPathComponent($0).path) }
  }

  private static func hermesPackageLooksInstalled(hermesDir: URL) -> Bool {
    let package = hermesDir.appendingPathComponent("hermes-agent/package.json")
    guard
      let data = try? Data(contentsOf: package),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      json["name"] as? String == "hermes-agent"
    else {
      return false
    }
    return true
  }

  /// Appends the marked "search Omi first" block to the Hermes system prompt so
  /// every user's agent is told to prefer Omi memory. Writes SOUL.md, creating
  /// it when needed. Writes *through* a symlinked
  /// prompt instead of replacing it. Idempotent; returns true only when it wrote.
  @discardableResult
  private static func ensureHermesSoulNote(hermesDir: URL) throws -> Bool {
    let fm = FileManager.default
    let url = hermesDir.appendingPathComponent("SOUL.md")
    var soul = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    if soul.contains(marker) { return false }
    if !soul.isEmpty && !soul.hasSuffix("\n") { soul += "\n" }
    soul += "\n" + hermesSoulBlock() + "\n"
    let isSymlink = (try? fm.destinationOfSymbolicLink(atPath: url.path)) != nil
    try soul.write(to: url, atomically: !isSymlink, encoding: .utf8)
    return true
  }

  private static func hermesSoulBlock() -> String {
    """
    <!-- \(marker) -->
    ## OMI memory (search FIRST)
    Omi is your memory bank. Before any task, search Omi memory first for context, then save durable new facts back to it. The `omi-memory` MCP server is configured for you — use it.
    <!-- /\(marker) -->
    """
  }

  private static func hermesEntry(key: String) -> String {
    """
      omi-memory:
        command: npx
        args: ["-y", "mcp-remote", "\(mcpURL)", "--header", "Authorization: Bearer \(key)"]
    """
  }

  private static func hermesEntryIsCurrent(content: String, key: String) -> Bool {
    content.contains(hermesEntry(key: key))
  }

  private static func upsertHermesEntry(content: String, key: String, configURL: URL) throws -> String {
    let entry = hermesEntry(key: key)
    var lines = content.components(separatedBy: "\n")
    let hadTrailingNewline = content.hasSuffix("\n")

    if let sectionIndex = lines.firstIndex(where: { $0 == "mcp_servers:" }) {
      let nextTopLevelIndex =
        lines[(sectionIndex + 1)...]
        .firstIndex(where: { !$0.isEmpty && !$0.hasPrefix(" ") && !$0.hasPrefix("\t") }) ?? lines.endIndex
      if let existingIndex = lines[(sectionIndex + 1)..<nextTopLevelIndex].firstIndex(where: { $0 == "  omi-memory:" }) {
        var endIndex = existingIndex + 1
        while endIndex < nextTopLevelIndex {
          let line = lines[endIndex]
          if line.hasPrefix("    ") || line.isEmpty {
            endIndex += 1
          } else {
            break
          }
        }
        lines.replaceSubrange(existingIndex..<endIndex, with: entry.components(separatedBy: "\n"))
      } else {
        lines.insert(contentsOf: entry.components(separatedBy: "\n"), at: sectionIndex + 1)
      }
      var updated = lines.joined(separator: "\n")
      if hadTrailingNewline && !updated.hasSuffix("\n") { updated += "\n" }
      return updated
    }

    if lines.contains(where: { $0.trimmingCharacters(in: .whitespaces) == "mcp_servers:" }) {
      throw ConnectError.invalidConfig(
        "Hermes config has an indented mcp_servers section; expected top-level mcp_servers in \(displayPath(for: configURL)).")
    }

    var updated = content
    if !updated.isEmpty && !updated.hasSuffix("\n") { updated += "\n" }
    updated += "\nmcp_servers:\n" + entry
    if hadTrailingNewline || content.isEmpty { updated += "\n" }
    return updated
  }
}
