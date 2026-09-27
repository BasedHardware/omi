import Foundation

enum MemoryExportConnectionDetector {
  nonisolated(unsafe) static var homeOverrideForTesting: URL?

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

  /// How a destination's owned config block relates to the current endpoint:
  /// the canonical `/v1/mcp` URL is `connected`; the legacy `/v1/mcp/sse` alias
  /// with the same key is `needsUpdate` (a migration target, not connected).
  enum ConnectionState: Sendable, Equatable {
    case connected
    case needsUpdate
  }

  static func hasExistingConnection(
    for destination: MemoryExportDestination,
    matchingKey key: String?
  ) -> Bool {
    localMCPConnectionState(for: destination, matchingKey: key) == .connected
  }

  static func localMCPConnectionState(
    for destination: MemoryExportDestination,
    matchingKey key: String?
  ) -> ConnectionState? {
    guard let key = normalizedKey(key) else { return nil }
    let files = ConfigFile.allCases.filter { $0.destinations.contains(destination) }
    return scan(files, matchingKey: key)[destination]
  }

  static func scanLocalMCPConnections(matchingKey key: String?) -> Set<MemoryExportDestination> {
    Set(
      scanLocalMCPConnectionStates(matchingKey: key).compactMap { destination, state in
        state == .connected ? destination : nil
      })
  }

  static func scanLocalMCPConnectionStates(
    matchingKey key: String?
  ) -> [MemoryExportDestination: ConnectionState] {
    guard let key = normalizedKey(key) else { return [:] }
    return scan(ConfigFile.allCases, matchingKey: key)
  }

  static func scanLocalMCPConnections(
    for destination: MemoryExportDestination,
    matchingKey key: String?
  ) -> Set<MemoryExportDestination> {
    localMCPConnectionState(for: destination, matchingKey: key) == .connected ? [destination] : []
  }

  private static func scan(
    _ files: [ConfigFile],
    matchingKey key: String
  ) -> [MemoryExportDestination: ConnectionState] {
    files.reduce(into: [MemoryExportDestination: ConnectionState]()) { result, file in
      guard let state = parse(file, matchingKey: key) else { return }
      for destination in file.destinations {
        // A destination backed by several config files (claudeCode) counts as
        // connected when ANY file is canonical — connected wins over legacy.
        if result[destination] != .connected {
          result[destination] = state
        }
      }
    }
  }

  private static func parse(
    _ file: ConfigFile,
    matchingKey key: String
  ) -> ConnectionState? {
    switch file {
    case .codex:
      return codexConfigOmiMCPState(file.url, matchingKey: key)
    case .claudeDesktop:
      return jsonConfigOmiMCPState(
        file.url,
        serverPath: ["mcpServers", "omi-memory"],
        matchingKey: key,
        requiresLocalCommand: true
      )
    case .claudeCodeGlobal, .claudeCodeSettings:
      return jsonConfigOmiMCPState(
        file.url,
        serverPath: ["mcpServers", "omi-memory"],
        matchingKey: key
      )
    case .openclaw:
      return jsonConfigOmiMCPState(
        file.url,
        serverPath: ["mcp", "servers", "omi-memory"],
        matchingKey: key
      )
    case .hermes:
      return hermesConfigOmiMCPState(file.url, matchingKey: key)
    }
  }

  /// Declared endpoint + Bearer parsed from an owned entry's OWN fields — the
  /// `url` scalar or the element right after `mcp-remote` in `args`, and the
  /// Authorization header value or `--header` arg. A nil element marks a field
  /// that is present but unparseable: ambiguity, never absence.
  private struct OwnedEntryScan {
    var endpoints: [String?] = []
    var bearers: [String?] = []
  }

  private static func codexConfigOmiMCPState(_ url: URL, matchingKey key: String) -> ConnectionState? {
    guard let content = try? String(contentsOf: url, encoding: .utf8) else { return nil }

    var inOmiServer = false
    var lines: [String] = []
    for rawLine in content.components(separatedBy: .newlines) {
      let line = stripInlineComment(rawLine, comment: "#").trimmingCharacters(in: .whitespaces)
      guard !line.isEmpty else { continue }
      if line.hasPrefix("[") && line.hasSuffix("]") {
        inOmiServer = line == "[mcp_servers.omi-memory]"
        continue
      }
      if inOmiServer {
        lines.append(line)
      }
    }
    return entryState(codexEntryScan(lines), matchingKey: key)
  }

  private static func hermesConfigOmiMCPState(_ url: URL, matchingKey key: String) -> ConnectionState? {
    guard let content = try? String(contentsOf: url, encoding: .utf8) else { return nil }

    var inMCPServers = false
    var inOmiServer = false
    var scan = OwnedEntryScan()
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
      guard inOmiServer else { continue }
      hermesFieldScan(line, into: &scan)
    }
    return entryState(scan, matchingKey: key)
  }

  private static func jsonConfigOmiMCPState(
    _ url: URL,
    serverPath: [String],
    matchingKey key: String,
    requiresLocalCommand: Bool = false
  ) -> ConnectionState? {
    guard
      let data = try? Data(contentsOf: url),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let server = value(in: json, at: serverPath) as? [String: Any],
      server["disabled"] as? Bool != true,
      server["enabled"] as? Bool != false
    else {
      return nil
    }
    if requiresLocalCommand {
      // Claude Desktop runs only local stdio servers from this file: a remote
      // `url` entry is dead config, and a missing `command` runs nothing.
      guard let command = server["command"] as? String, !command.isEmpty else { return nil }
    }
    return entryState(
      jsonEntryScan(server, endpointsFromURL: !requiresLocalCommand), matchingKey: key)
  }

  private static func value(in dictionary: [String: Any], at path: [String]) -> Any? {
    var current: Any? = dictionary
    for key in path {
      current = (current as? [String: Any])?[key]
    }
    return current
  }

  /// Exact canonical URL + the current Bearer is `connected`; the /sse alias
  /// with the same key is `needsUpdate`. Conflicting declared endpoints or
  /// bearer values are ambiguous → nil, never a guess.
  private static func entryState(_ scan: OwnedEntryScan, matchingKey key: String) -> ConnectionState? {
    guard
      Set(scan.endpoints).count == 1,
      let endpoint = scan.endpoints.first ?? nil,
      Set(scan.bearers).count == 1,
      let bearer = scan.bearers.first ?? nil,
      bearer == key
    else { return nil }
    if endpoint == MemoryExportDestination.mcpServerURL { return .connected }
    if endpoint == MemoryExportDestination.mcpLegacyServerURL { return .needsUpdate }
    return nil
  }

  /// The endpoints a bridge args array declares: every element right after an
  /// `mcp-remote` token. A trailing `mcp-remote` with no URL is ambiguous
  /// (nil); multiple occurrences each contribute (conflicts refuse).
  private static func argsEndpoint(_ args: [String]) -> [String?] {
    var endpoints: [String?] = []
    for (index, arg) in args.enumerated() where arg == "mcp-remote" {
      endpoints.append(index + 1 < args.count ? args[index + 1] : nil)
    }
    return endpoints
  }

  /// Bearer tokens from `Authorization: Bearer x` arg elements (`--header` args).
  private static func argsBearerScans(_ args: [String]) -> [String?] {
    args.compactMap { arg -> String?? in
      guard let auth = firstCapture(#"(?i)^\s*Authorization\s*:\s*(.+?)\s*$"#, in: arg)
      else { return nil }
      return bearerToken(auth)
    }
  }

  /// `Bearer <token>` from an Authorization header value; anything else is a
  /// present-but-unusable credential → nil marker.
  private static func bearerToken(_ value: String) -> String? {
    firstCapture(#"(?i)^\s*Bearer\s+(\S+)\s*$"#, in: value)
  }

  /// A TOML double-quoted basic string decodes as JSON; a single-quoted literal
  /// is verbatim. Anything else is not a scalar we can trust.
  private static func tomlScalar(_ raw: String) -> String? {
    let value = raw.trimmingCharacters(in: .whitespaces)
    guard let quote = value.first, quote == "\"" || quote == "'" else { return nil }
    guard let end = quotedScalarEnd(value, quote: quote) else { return nil }
    let literal = String(value[value.startIndex..<end])
    guard value[end...].trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
    if quote == "'" { return String(literal.dropFirst().dropLast()) }
    guard
      let data = literal.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed])
        as? String
    else { return nil }
    return parsed
  }

  /// Index just past the closing `quote` (honoring `\` escapes in double-quoted
  /// strings), or nil when unterminated.
  private static func quotedScalarEnd(_ text: String, quote: Character) -> String.Index? {
    var index = text.index(after: text.startIndex)
    while index < text.endIndex {
      let char = text[index]
      if char == "\\", quote == "\"" {
        index = text.index(index, offsetBy: 2, limitedBy: text.endIndex) ?? text.endIndex
        continue
      }
      if char == quote { return text.index(after: index) }
      index = text.index(after: index)
    }
    return nil
  }

  /// A YAML scalar after `key:` — quoted like a TOML scalar, or the bare rest
  /// of the line (comments are already stripped). An empty value is a mapping
  /// opener, not a URL.
  private static func yamlScalar(_ raw: String) -> String? {
    let value = raw.trimmingCharacters(in: .whitespaces)
    if value.first == "\"" || value.first == "'" { return tomlScalar(value) }
    return value.isEmpty ? nil : value
  }

  /// A JSON-compatible inline string array (what the `args` fields emit).
  private static func stringArray(_ raw: String) -> [String]? {
    let value = raw.trimmingCharacters(in: .whitespaces)
    guard value.hasPrefix("["),
      let data = value.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [Any]
    else { return nil }
    var strings: [String] = []
    for element in parsed {
      guard let string = element as? String else { return nil }
      strings.append(string)
    }
    return strings
  }

  /// Parse `url`, `args`, and `http_headers`/`headers` out of the owned Codex
  /// section's `key = value` lines.
  private static func codexEntryScan(_ lines: [String]) -> OwnedEntryScan {
    var scan = OwnedEntryScan()
    for line in lines {
      guard let eq = line.firstIndex(of: "=") else { continue }
      let field = line[..<eq].trimmingCharacters(in: .whitespaces)
      guard field.range(of: #"^[A-Za-z0-9_-]+$"#, options: .regularExpression) != nil else {
        continue
      }
      let value = String(line[line.index(after: eq)...])
      switch field {
      case "url":
        scan.endpoints.append(tomlScalar(value))
      case "args":
        if let args = stringArray(value) {
          scan.endpoints.append(contentsOf: argsEndpoint(args))
          scan.bearers.append(contentsOf: argsBearerScans(args))
        } else {
          scan.endpoints.append(nil)
        }
      case "http_headers", "headers":
        if let auth = firstCapture(#"Authorization\s*=\s*("(?:[^"\\]|\\.)*"|'[^']*')"#, in: value) {
          scan.bearers.append(tomlScalar(auth).flatMap(bearerToken))
        }
      default:
        continue
      }
    }
    return scan
  }

  /// Parse the owned Hermes sub-block: direct-child `url:`/`args:` fields plus
  /// the `Authorization:` header line (which sits one level deeper).
  private static func hermesFieldScan(_ line: String, into scan: inout OwnedEntryScan) {
    if let kv = captures(#"^ {4}([A-Za-z0-9_-]+)\s*:\s*(.*)$"#, in: line) {
      if kv[0] == "url" {
        scan.endpoints.append(yamlScalar(kv[1]))
      } else if kv[0] == "args" {
        if let args = stringArray(kv[1]) {
          scan.endpoints.append(contentsOf: argsEndpoint(args))
          scan.bearers.append(contentsOf: argsBearerScans(args))
        } else {
          scan.endpoints.append(nil)
        }
      }
    }
    if let auth = firstCapture(#"^\s+Authorization\s*:\s*(.*)$"#, in: line) {
      scan.bearers.append(yamlScalar(auth).flatMap(bearerToken))
    }
  }

  /// Parse a JSON server entry: `url` (only for remote-capable files), `args`
  /// (mcp-remote bridge), and `headers.Authorization`. An `args` key that is
  /// present but not a string array marks ambiguity, never absence.
  private static func jsonEntryScan(_ server: [String: Any], endpointsFromURL: Bool) -> OwnedEntryScan {
    var scan = OwnedEntryScan()
    if endpointsFromURL, server.keys.contains("url") {
      scan.endpoints.append(server["url"] as? String)
    }
    if let rawArgs = server["args"] as? [Any] {
      var args: [String] = []
      var allStrings = true
      for element in rawArgs {
        guard let string = element as? String else {
          allStrings = false
          break
        }
        args.append(string)
      }
      if allStrings {
        scan.endpoints.append(contentsOf: argsEndpoint(args))
        scan.bearers.append(contentsOf: argsBearerScans(args))
      } else {
        scan.endpoints.append(nil)
      }
    } else if server.keys.contains("args") {
      scan.endpoints.append(nil)
    }
    if let headers = server["headers"] as? [String: Any], headers.keys.contains("Authorization") {
      scan.bearers.append((headers["Authorization"] as? String).flatMap(bearerToken))
    }
    return scan
  }

  private static func firstCapture(_ pattern: String, in text: String) -> String? {
    captures(pattern, in: text)?.first
  }

  private static func captures(_ pattern: String, in text: String) -> [String]? {
    guard
      let regex = try? NSRegularExpression(pattern: pattern),
      let match = regex.firstMatch(
        in: text, range: NSRange(text.startIndex..<text.endIndex, in: text)),
      match.numberOfRanges > 1
    else { return nil }
    let groups = (1..<match.numberOfRanges).compactMap {
      Range(match.range(at: $0), in: text).map { String(text[$0]) }
    }
    return groups.count == match.numberOfRanges - 1 ? groups : nil
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
