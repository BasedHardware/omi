import Foundation

enum MemoryExportConnectionDetector {
  static var homeOverrideForTesting: URL?

  private static var home: URL {
    homeOverrideForTesting ?? FileManager.default.homeDirectoryForCurrentUser
  }

  static func hasExistingConnection(for destination: MemoryExportDestination) -> Bool {
    switch destination {
    case .codex:
      return codexConfigHasOmiMCP(home.appendingPathComponent(".codex/config.toml"))
    case .claude:
      return jsonConfigHasOmiMCP(
        home.appendingPathComponent("Library/Application Support/Claude/claude_desktop_config.json"),
        serverPath: ["mcpServers", "omi-memory"])
    case .claudeCode:
      return [
        home.appendingPathComponent(".claude.json"),
        home.appendingPathComponent(".claude/settings.json"),
      ].contains { jsonConfigHasOmiMCP($0, serverPath: ["mcpServers", "omi-memory"]) }
    case .hermes:
      return hermesConfigHasOmiMCP(home.appendingPathComponent(".hermes/config.yaml"))
    case .openclaw:
      return jsonConfigHasOmiMCP(
        home.appendingPathComponent(".openclaw/openclaw.json"),
        serverPath: ["mcp", "servers", "omi-memory"])
    case .notion, .obsidian, .chatgpt, .gemini, .agents:
      return false
    }
  }

  private static func codexConfigHasOmiMCP(_ url: URL) -> Bool {
    guard let content = try? String(contentsOf: url, encoding: .utf8) else { return false }

    var inOmiServer = false
    var body = ""
    for rawLine in content.components(separatedBy: .newlines) {
      let line = stripInlineComment(rawLine, comment: "#").trimmingCharacters(in: .whitespaces)
      guard !line.isEmpty else { continue }
      if line.hasPrefix("[") && line.hasSuffix("]") {
        inOmiServer = line == "[mcp_servers.omi-memory]"
        continue
      }
      if inOmiServer {
        body += "\n" + line
      }
    }
    return bodyContainsOmiEndpoint(body)
  }

  private static func hermesConfigHasOmiMCP(_ url: URL) -> Bool {
    guard let content = try? String(contentsOf: url, encoding: .utf8) else { return false }

    var inMCPServers = false
    var inOmiServer = false
    var body = ""
    for rawLine in content.components(separatedBy: .newlines) {
      let line = stripInlineComment(rawLine, comment: "#")
      let trimmed = line.trimmingCharacters(in: .whitespaces)
      guard !trimmed.isEmpty else { continue }

      if !line.hasPrefix(" "), !line.hasPrefix("\t") {
        inMCPServers = trimmed == "mcp_servers:"
        inOmiServer = false
        continue
      }
      guard inMCPServers else { continue }

      if line.hasPrefix("  "), !line.hasPrefix("    "), trimmed.hasSuffix(":") {
        inOmiServer = trimmed == "omi-memory:"
        continue
      }
      if inOmiServer {
        body += "\n" + trimmed
      }
    }
    return bodyContainsOmiEndpoint(body)
  }

  private static func jsonConfigHasOmiMCP(_ url: URL, serverPath: [String]) -> Bool {
    guard
      let data = try? Data(contentsOf: url),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let server = value(in: json, at: serverPath) as? [String: Any],
      server["disabled"] as? Bool != true,
      server["enabled"] as? Bool != false
    else {
      return false
    }
    return bodyContainsOmiEndpoint(stringValues(in: server).joined(separator: "\n"))
  }

  private static func value(in dictionary: [String: Any], at path: [String]) -> Any? {
    var current: Any? = dictionary
    for key in path {
      current = (current as? [String: Any])?[key]
    }
    return current
  }

  private static func stringValues(in value: Any) -> [String] {
    if let string = value as? String {
      return [string]
    }
    if let array = value as? [Any] {
      return array.flatMap(stringValues)
    }
    if let dictionary = value as? [String: Any] {
      return dictionary.values.flatMap(stringValues)
    }
    return []
  }

  private static func bodyContainsOmiEndpoint(_ body: String) -> Bool {
    let lower = body.lowercased()
    return lower.contains("api.omi") && lower.contains("/v1/mcp/sse")
  }

  private static func stripInlineComment(_ line: String, comment: Character) -> String {
    var result = ""
    var isInSingleQuote = false
    var isInDoubleQuote = false
    var previous: Character?
    for character in line {
      if character == "'", !isInDoubleQuote {
        isInSingleQuote.toggle()
      } else if character == "\"", !isInSingleQuote, previous != "\\" {
        isInDoubleQuote.toggle()
      } else if character == comment, !isInSingleQuote, !isInDoubleQuote {
        break
      }
      result.append(character)
      previous = character
    }
    return result
  }
}
