import Foundation

/// Deterministic, local "Do it for me" for agent frameworks that store their
/// memory/config as plain files (OpenClaw, Hermes). Unlike the cloud
/// connectors, these don't have a CLI like `claude mcp add`, and delegating to
/// the in-app agent proved unreliable (it doesn't reliably fire a file-write
/// tool). So we write the Omi memory bank ourselves — idempotently — exactly
/// the way Codex's config.toml block is written.
enum MemoryBankConnector {
  static let marker = "omi-memory-bank"
  private static let mcpURL = "https://api.omi.me/v1/mcp/sse"

  enum ConnectError: LocalizedError {
    case notInstalled(String)
    var errorDescription: String? {
      switch self {
      case .notInstalled(let msg): return msg
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

  private static var home: URL { FileManager.default.homeDirectoryForCurrentUser }

  // MARK: - OpenClaw (markdown memory bank)

  private static func connectOpenClaw(key: String) throws -> String {
    let fm = FileManager.default
    // OpenClaw keeps its core memory as markdown in its workspace; ~/clawd is
    // the documented default, MEMORY.md the core file.
    let candidates = ["clawd/MEMORY.md", ".openclaw/MEMORY.md", "clawd/AGENTS.md"]
    guard
      let rel = candidates.first(where: {
        fm.fileExists(atPath: home.appendingPathComponent($0).path)
      })
    else {
      throw ConnectError.notInstalled(
        "OpenClaw not found locally (looked for ~/clawd/MEMORY.md). Install OpenClaw, then try again.")
    }
    let url = home.appendingPathComponent(rel)
    var content = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    if content.contains(marker) {
      return "OpenClaw already connected — Omi memory bank is in ~/\(rel)."
    }
    if !content.isEmpty && !content.hasSuffix("\n") { content += "\n" }
    content += "\n" + openClawBlock(key: key) + "\n"
    try content.write(to: url, atomically: true, encoding: .utf8)
    return "Connected OpenClaw — added the Omi memory bank to ~/\(rel)."
  }

  private static func openClawBlock(key: String) -> String {
    """
    <!-- \(marker) -->
    ## OMI memory (search FIRST)
    Omi is your memory bank. Before any task, **search Omi memory first** for context, then save durable new facts back to it.
    - MCP: \(mcpURL)  (Authorization: Bearer \(key))
    - HTTP search: GET https://api.omi.me/v1/mcp/memories/search?query=<q>  (Bearer \(key))
    - HTTP save:   POST https://api.omi.me/v1/mcp/memories  {"content":"…"}  (Bearer \(key))
    <!-- /\(marker) -->
    """
  }

  // MARK: - Hermes (config.yaml mcp_servers)

  private static func connectHermes(key: String) throws -> String {
    let fm = FileManager.default
    let hermesDir = home.appendingPathComponent(".hermes")
    guard fm.fileExists(atPath: hermesDir.path) else {
      throw ConnectError.notInstalled(
        "Hermes not found locally (~/.hermes). Install Hermes, then try again.")
    }
    let cfg = hermesDir.appendingPathComponent("config.yaml")
    var content = (try? String(contentsOf: cfg, encoding: .utf8)) ?? ""
    if content.contains("omi-memory") {
      return "Hermes already has the Omi memory MCP in ~/.hermes/config.yaml."
    }
    let entry = hermesEntry(key: key)
    if let range = content.range(of: "mcp_servers:") {
      // Insert as the first child under the existing mcp_servers: key.
      content.replaceSubrange(range, with: "mcp_servers:\n" + entry)
    } else {
      if !content.isEmpty && !content.hasSuffix("\n") { content += "\n" }
      content += "\nmcp_servers:\n" + entry
    }
    try content.write(to: cfg, atomically: true, encoding: .utf8)
    // Also drop a one-line "search Omi first" note next to the core prompt if present.
    return "Connected Hermes — added the Omi memory MCP to ~/.hermes/config.yaml."
  }

  private static func hermesEntry(key: String) -> String {
    """
      omi-memory:
        command: npx
        args: ["-y", "mcp-remote", "\(mcpURL)", "--header", "Authorization: Bearer \(key)"]
    """
  }
}
