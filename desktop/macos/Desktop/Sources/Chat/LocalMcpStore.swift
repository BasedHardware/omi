import Foundation

/// Local MCP servers at `~/.omi/mcp.json`, in the standard client format:
/// `{"mcpServers": {"<name>": {"command", "args", "env"} | {"url", ...}}}`.
/// Hand-edits are respected: reads and writes go through read-modify-write on
/// the raw JSON so entries this UI does not understand survive untouched.
enum LocalMcpStore {
  struct Entry: Identifiable, Equatable {
    let name: String
    /// "command …args" for stdio entries, the URL for remote ones.
    let summary: String
    let isCommand: Bool
    var id: String { name }

    /// Omi itself serves this entry rather than a third party. It is written and
    /// removed by its own feature's gate (`CuaMcpRegistration`), not added by
    /// the user, so the UI shows it as built-in and offers no Remove.
    var isBuiltIn: Bool { LocalMcpStore.builtInServerNames.contains(name) }
  }

  /// Entries this app writes for its own features. They live in the same file
  /// and the same list as user-added servers, but their presence follows the
  /// feature's settings rather than the user's add/remove, so the generic
  /// removal path refuses them: the registrar that wrote each entry is the one
  /// that removes it, through `removeBuiltInServer`.
  static var builtInServerNames: Set<String> { [CuaMcpRegistration.serverName] }

  static var fileURL: URL { LocalSkillsStore.rootURL.appendingPathComponent("mcp.json") }

  static func listServers() -> [Entry] {
    let servers = readServers()
    return servers.keys.sorted().compactMap { name in
      guard let raw = servers[name] as? [String: Any] else { return nil }
      if let command = raw["command"] as? String {
        let args = (raw["args"] as? [Any])?.compactMap { $0 as? String } ?? []
        return Entry(name: name, summary: ([command] + args).joined(separator: " "), isCommand: true)
      }
      if let url = raw["url"] as? String {
        return Entry(name: name, summary: url, isCommand: false)
      }
      return nil
    }
  }

  /// Add a stdio server from a single command line ("npx @playwright/mcp@latest").
  static func addCommandServer(name: String, commandLine: String) throws {
    let slug = LocalSkillsStore.slugify(name)
    let parts = commandLine.split(separator: " ").map(String.init)
    guard !slug.isEmpty else {
      throw storeError("Server name must contain letters or numbers")
    }
    guard let command = parts.first, !command.isEmpty else {
      throw storeError("Enter the command to run, e.g. npx @playwright/mcp@latest")
    }
    var servers = readServers()
    var entry: [String: Any] = ["command": command]
    if parts.count > 1 { entry["args"] = Array(parts.dropFirst()) }
    servers[slug] = entry
    try writeServers(servers)
  }

  static func removeServer(name: String) {
    // Built-in entries follow their feature's gate, not this store's user-facing
    // remove. A user's Remove — or any code treating mcp.json as purely user
    // data — silently deleting Omi's own server is the failure this guards.
    guard !builtInServerNames.contains(name) else {
      log("LocalMcpStore: refusing to remove built-in server '\(name)'")
      return
    }
    dropEntry(named: name)
  }

  /// The one way a built-in entry leaves the file: the registrar that wrote it
  /// removing it as its feature turns off.
  static func removeBuiltInServer(name: String) {
    dropEntry(named: name)
  }

  private static func dropEntry(named name: String) {
    var servers = readServers()
    servers.removeValue(forKey: name)
    try? writeServers(servers)
  }

  static func upsertServer(_ name: String, entry: [String: Any]) throws {
    var servers = readServers()
    servers[name] = entry
    try writeServers(servers)
  }

  static func readAllServers() -> [String: Any] {
    readServers()
  }

  // MARK: - Raw file access

  private static func readServers() -> [String: Any] {
    guard let data = try? Data(contentsOf: fileURL),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return [:] }
    return json["mcpServers"] as? [String: Any] ?? [:]
  }

  private static func writeServers(_ servers: [String: Any]) throws {
    var root: [String: Any] = [:]
    if let data = try? Data(contentsOf: fileURL),
      let existing = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    {
      root = existing
    }
    root["mcpServers"] = servers
    let fm = FileManager.default
    try fm.createDirectory(at: LocalSkillsStore.rootURL, withIntermediateDirectories: true)
    let data = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: fileURL, options: .atomic)
  }

  static func storeError(_ message: String) -> Error {
    NSError(domain: "LocalMcpStore", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
  }
}
