import Foundation

enum MemoryExportConnectionDetector {
  static var homeOverrideForTesting: URL?

  private static var home: URL {
    homeOverrideForTesting ?? FileManager.default.homeDirectoryForCurrentUser
  }

  private enum ConfigFile: CaseIterable, Hashable {
    case codex
    case claudeDesktop
    case claudeCodeGlobal
    case claudeCodeSettings
    case openclaw
    case hermes

    var url: URL {
      let home = MemoryExportConnectionDetector.home
      switch self {
      case .codex:
        return home.appendingPathComponent(".codex/config.toml")
      case .claudeDesktop:
        return home.appendingPathComponent("Library/Application Support/Claude/claude_desktop_config.json")
      case .claudeCodeGlobal:
        return home.appendingPathComponent(".claude.json")
      case .claudeCodeSettings:
        return home.appendingPathComponent(".claude/settings.json")
      case .openclaw:
        return home.appendingPathComponent(".openclaw/openclaw.json")
      case .hermes:
        return home.appendingPathComponent(".hermes/config.yaml")
      }
    }

    var destinations: Set<MemoryExportDestination> {
      switch self {
      case .codex: return [.codex]
      case .claudeDesktop: return [.claude]
      case .claudeCodeGlobal, .claudeCodeSettings: return [.claudeCode]
      case .openclaw: return [.openclaw]
      case .hermes: return [.hermes]
      }
    }
  }

  static func hasExistingConnection(
    for destination: MemoryExportDestination,
    matchingKey key: String?
  ) -> Bool {
    scanLocalMCPConnections(for: destination, matchingKey: key).contains(destination)
  }

  static func scanLocalMCPConnections(matchingKey key: String?) -> Set<MemoryExportDestination> {
    guard let key = normalizedKey(key) else { return [] }
    return scan(ConfigFile.allCases, matchingKey: key)
  }

  static func scanLocalMCPConnections(
    for destination: MemoryExportDestination,
    matchingKey key: String?
  ) -> Set<MemoryExportDestination> {
    guard let key = normalizedKey(key) else { return [] }
    let files = ConfigFile.allCases.filter { $0.destinations.contains(destination) }
    return scan(files, matchingKey: key)
  }

  private static func scan(
    _ files: [ConfigFile],
    matchingKey key: String
  ) -> Set<MemoryExportDestination> {
    files.reduce(into: Set<MemoryExportDestination>()) { result, file in
      result.formUnion(parse(file, matchingKey: key))
    }
  }

  private static func parse(
    _ file: ConfigFile,
    matchingKey key: String
  ) -> Set<MemoryExportDestination> {
    switch file {
    case .codex:
      return codexConfigHasOmiMCP(file.url, matchingKey: key) ? [.codex] : []
    case .claudeDesktop:
      return jsonConfigHasOmiMCP(
        file.url,
        serverPath: ["mcpServers", "omi-memory"],
        matchingKey: key
      ) ? [.claude] : []
    case .claudeCodeGlobal, .claudeCodeSettings:
      return jsonConfigHasOmiMCP(
        file.url,
        serverPath: ["mcpServers", "omi-memory"],
        matchingKey: key
      ) ? [.claudeCode] : []
    case .openclaw:
      return jsonConfigHasOmiMCP(
        file.url,
        serverPath: ["mcp", "servers", "omi-memory"],
        matchingKey: key
      ) ? [.openclaw] : []
    case .hermes:
      return hermesConfigHasOmiMCP(file.url, matchingKey: key) ? [.hermes] : []
    }
  }

  private static func codexConfigHasOmiMCP(_ url: URL, matchingKey key: String) -> Bool {
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
    return bodyContainsCurrentOmiMCP(body, matchingKey: key)
  }

  private static func hermesConfigHasOmiMCP(_ url: URL, matchingKey key: String) -> Bool {
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
    return bodyContainsCurrentOmiMCP(body, matchingKey: key)
  }

  private static func jsonConfigHasOmiMCP(
    _ url: URL,
    serverPath: [String],
    matchingKey key: String
  ) -> Bool {
    guard
      let data = try? Data(contentsOf: url),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let server = value(in: json, at: serverPath) as? [String: Any],
      server["disabled"] as? Bool != true,
      server["enabled"] as? Bool != false
    else {
      return false
    }
    return bodyContainsCurrentOmiMCP(stringValues(in: server).joined(separator: "\n"), matchingKey: key)
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

  private static func bodyContainsCurrentOmiMCP(_ body: String, matchingKey key: String) -> Bool {
    body.range(of: MemoryExportDestination.mcpServerURL, options: [.caseInsensitive]) != nil
      && bearerTokens(in: body).contains(key)
  }

  private static func bearerTokens(in body: String) -> Set<String> {
    guard
      let regex = try? NSRegularExpression(
        pattern: #"(?i)\bBearer\s+([^\s"',}\]]+)"#,
        options: []
      )
    else {
      return []
    }

    let nsRange = NSRange(body.startIndex..<body.endIndex, in: body)
    return Set(regex.matches(in: body, options: [], range: nsRange).compactMap { match in
      guard
        match.numberOfRanges > 1,
        let range = Range(match.range(at: 1), in: body)
      else {
        return nil
      }
      return String(body[range])
    })
  }

  private static func normalizedKey(_ key: String?) -> String? {
    let trimmed = (key ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
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
