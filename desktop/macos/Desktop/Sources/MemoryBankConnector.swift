import Foundation

/// Deterministic, local "Do it for me" for agent frameworks that store their
/// memory/config locally. Delegating setup to the in-app agent is slower and
/// less reliable than using each tool's native durable surface directly.
enum MemoryBankConnector {
  static let marker = "omi-memory-bank"
  private static let claudeCodeBackupRetentionLimit = 5
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
    switch destination {
    case .claudeCode, .codex, .openclaw, .hermes:
      return true
    case .notion, .obsidian, .chatgpt, .claude, .gemini, .agents:
      return false
    }
  }

  /// Whether the local tool for `destination` is actually installed on this Mac,
  /// using the SAME evidence the matching `connect…` path requires. Onboarding's
  /// upfront probe must agree with the connect outcome, otherwise a row offers
  /// "Connect" and then fails to "not installed" only after the click (e.g. a
  /// stray `~/.codex` dir with no `codex` on PATH). May shell out (`command -v`),
  /// so call it off the main thread.
  static func isInstalled(_ destination: MemoryExportDestination) -> Bool {
    let fm = FileManager.default
    switch destination {
    case .claudeCode:
      return fm.fileExists(atPath: home.appendingPathComponent(".claude.json").path)
        || fm.fileExists(atPath: home.appendingPathComponent(".claude/settings.json").path)
        || executablePath(named: "claude", override: claudeCLIPathOverrideForTesting) != nil
    case .codex:
      return executablePath(named: "codex", override: codexCLIPathOverrideForTesting) != nil
    case .openclaw:
      let config = home.appendingPathComponent(".openclaw/openclaw.json")
      guard fm.fileExists(atPath: config.path), let cliPath = openClawCLIPath() else { return false }
      let workspace =
        openClawConfiguredWorkspace(configURL: config, cliPath: cliPath)
        ?? home.appendingPathComponent(".openclaw/workspace")
      return fm.fileExists(atPath: workspace.path)
    case .hermes:
      return hermesInstallIsPresent(hermesDir: home.appendingPathComponent(".hermes"), fileManager: fm)
    default:
      return false
    }
  }

  /// Performs the write. Returns a short user-facing success line. Throws
  /// `ConnectError.notInstalled` when the framework isn't found locally.
  @discardableResult
  static func connect(_ destination: MemoryExportDestination, key: String) throws -> String {
    switch destination {
    case .claudeCode: return try connectClaudeCode(key: key)
    case .codex: return try connectCodex(key: key)
    case .openclaw: return try connectOpenClaw(key: key)
    case .hermes: return try connectHermes(key: key)
    default: throw ConnectError.notInstalled("\(destination.title) is not a local memory-bank target.")
    }
  }

  nonisolated(unsafe) static var homeOverrideForTesting: URL?
  nonisolated(unsafe) static var claudeCLIPathOverrideForTesting: String?
  nonisolated(unsafe) static var codexCLIPathOverrideForTesting: String?
  nonisolated(unsafe) static var openClawCLIPathOverrideForTesting: String?
  nonisolated(unsafe) static var processTimeoutSecondsForTesting: TimeInterval?
  private static var home: URL { homeOverrideForTesting ?? FileManager.default.homeDirectoryForCurrentUser }
  private static var processTimeoutSeconds: TimeInterval { processTimeoutSecondsForTesting ?? 20 }

  // MARK: - Claude Code (~/.claude.json mcpServers)

  private static func connectClaudeCode(key: String) throws -> String {
    let fm = FileManager.default
    let config = home.appendingPathComponent(".claude.json")
    let settings = home.appendingPathComponent(".claude/settings.json")
    let hasInstallEvidence =
      fm.fileExists(atPath: config.path)
      || fm.fileExists(atPath: settings.path)
      || executablePath(named: "claude", override: claudeCLIPathOverrideForTesting) != nil
    guard hasInstallEvidence else {
      throw ConnectError.notInstalled(
        "Claude Code is not installed. Install it, then try again.")
    }

    var root: [String: Any] = [:]
    if fm.fileExists(atPath: config.path) {
      guard
        let data = try? Data(contentsOf: config),
        let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
      else {
        throw ConnectError.invalidConfig(
          "Claude Code settings are invalid. Fix \(displayPath(for: config)), then try again.")
      }
      root = json
    }

    let server = claudeCodeMCPServer(key: key)
    var servers = root["mcpServers"] as? [String: Any] ?? [:]
    if let existing = servers["omi-memory"] as? [String: Any],
      NSDictionary(dictionary: existing).isEqual(to: server)
    {
      return "Claude Code is already connected."
    }

    try backupClaudeCodeConfigIfNeeded(config)
    servers["omi-memory"] = server
    root["mcpServers"] = servers
    let data = try JSONSerialization.data(
      withJSONObject: root,
      options: [.prettyPrinted, .withoutEscapingSlashes])
    try data.write(to: config, options: [.atomic])

    guard MemoryExportConnectionDetector.hasExistingConnection(for: .claudeCode, matchingKey: key) else {
      throw ConnectError.invalidConfig(
        "Claude Code settings were updated, but Omi could not verify the connection.")
    }
    return "Claude Code is now connected."
  }

  private static func claudeCodeMCPServer(key: String) -> [String: Any] {
    [
      "type": "http",
      "url": mcpURL,
      "headers": [
        "Authorization": "Bearer \(key)"
      ],
    ]
  }

  private static func backupClaudeCodeConfigIfNeeded(_ config: URL) throws {
    let fm = FileManager.default
    guard fm.fileExists(atPath: config.path) else { return }
    let backupDir = home.appendingPathComponent(".claude/backups", isDirectory: true)
    try fm.createDirectory(at: backupDir, withIntermediateDirectories: true, attributes: nil)
    let backup = backupDir.appendingPathComponent(
      ".claude.json.backup.\(Int(Date().timeIntervalSince1970 * 1000))-\(UUID().uuidString)")
    try fm.copyItem(at: config, to: backup)
    try pruneClaudeCodeBackups(
      in: backupDir,
      keepingMostRecent: Self.claudeCodeBackupRetentionLimit)
  }

  private static func pruneClaudeCodeBackups(
    in backupDir: URL,
    keepingMostRecent limit: Int
  ) throws {
    guard limit >= 0 else { return }
    let backups = try FileManager.default
      .contentsOfDirectory(
        at: backupDir,
        includingPropertiesForKeys: nil
      )
      .filter { $0.lastPathComponent.hasPrefix(".claude.json.backup.") }
      .sorted { lhs, rhs in
        backupTimestamp(lhs) > backupTimestamp(rhs)
      }
    for backup in backups.dropFirst(limit) {
      try FileManager.default.removeItem(at: backup)
    }
  }

  private static func backupTimestamp(_ url: URL) -> Int64 {
    let prefix = ".claude.json.backup."
    let suffix = url.lastPathComponent.dropFirst(prefix.count)
    let timestamp = suffix.split(separator: "-", maxSplits: 1).first ?? ""
    return Int64(timestamp) ?? 0
  }

  // MARK: - Codex (~/.codex/config.toml)

  private static func connectCodex(key: String) throws -> String {
    guard let cliPath = executablePath(named: "codex", override: codexCLIPathOverrideForTesting) else {
      throw ConnectError.notInstalled(
        "Codex is not available. Install Codex or add the codex command to PATH, then try again.")
    }

    let codexHome = home.appendingPathComponent(".codex", isDirectory: true)
    try FileManager.default.createDirectory(at: codexHome, withIntermediateDirectories: true, attributes: nil)
    do {
      _ = try runProcess(
        executable: cliPath,
        arguments: [
          "mcp", "add", "omi-memory", "--",
          "npx", "-y", "mcp-remote", mcpURL,
          "--header", "Authorization: Bearer \(key)",
        ],
        environment: processEnvironment(extra: ["CODEX_HOME": codexHome.path]))
    } catch {
      throw ConnectError.invalidConfig(
        "Codex rejected the connection update: \(sanitizeCommandError(error.localizedDescription))")
    }

    guard MemoryExportConnectionDetector.hasExistingConnection(for: .codex, matchingKey: key) else {
      throw ConnectError.invalidConfig(
        "Codex was updated, but Omi could not verify the connection.")
    }
    return "Codex is now connected."
  }

  // MARK: - OpenClaw (mcp.servers + workspace SOUL.md)

  private static func connectOpenClaw(key: String) throws -> String {
    let fm = FileManager.default
    let config = home.appendingPathComponent(".openclaw/openclaw.json")
    guard fm.fileExists(atPath: config.path) else {
      throw ConnectError.notInstalled(
        "OpenClaw not found locally (looked for ~/.openclaw/openclaw.json). Install OpenClaw, then try again.")
    }
    guard let cliPath = openClawCLIPath() else {
      throw ConnectError.notInstalled(
        "OpenClaw CLI not found locally. Install OpenClaw or add the openclaw command to PATH, then try again.")
    }
    let workspace =
      openClawConfiguredWorkspace(configURL: config, cliPath: cliPath)
      ?? home.appendingPathComponent(".openclaw/workspace")
    guard fm.fileExists(atPath: workspace.path) else {
      throw ConnectError.notInstalled(
        "OpenClaw workspace not found (looked for \(displayPath(for: workspace))). Run OpenClaw setup, then try again.")
    }

    let alreadyWired = try ensureOpenClawMCPConfig(configURL: config, key: key, cliPath: cliPath)
    try reloadOpenClawMCP(cliPath: cliPath, configURL: config)
    let noteAdded = try ensureOpenClawSoulNote(workspace: workspace)

    if alreadyWired {
      return noteAdded
        ? "OpenClaw is now connected."
        : "OpenClaw is already connected."
    }
    return "OpenClaw is now connected."
  }

  private static func reloadOpenClawMCP(cliPath: String, configURL: URL) throws {
    do {
      _ = try runOpenClawCLI(
        cliPath: cliPath,
        configURL: configURL,
        arguments: ["mcp", "reload"]
      )
    } catch {
      let message = sanitizeCommandError(error.localizedDescription)
      throw ConnectError.invalidConfig(
        "OpenClaw MCP config was updated, but OpenClaw rejected MCP reload for \(displayPath(for: configURL)): \(message)"
      )
    }
  }

  private static func openClawConfiguredWorkspace(configURL: URL, cliPath: String) -> URL? {
    if let output = try? runOpenClawCLI(
      cliPath: cliPath,
      configURL: configURL,
      arguments: ["config", "get", "agents.defaults.workspace"]
    ),
      let workspace = normalizedPath(output.stdout)
    {
      return workspace
    }

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
    return normalizedPath(workspace)
  }

  @discardableResult
  private static func ensureOpenClawMCPConfig(configURL: URL, key: String, cliPath: String) throws -> Bool {
    let server = openClawMCPServer(key: key)
    let existing = try? runOpenClawCLI(
      cliPath: cliPath,
      configURL: configURL,
      arguments: ["mcp", "show", "omi-memory", "--json"]
    )
    if let existing,
      let data = existing.stdout.data(using: .utf8),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      NSDictionary(dictionary: json).isEqual(to: server)
    {
      return true
    }

    let serverData = try JSONSerialization.data(withJSONObject: server, options: [.withoutEscapingSlashes])
    guard let serverJSON = String(data: serverData, encoding: .utf8) else {
      throw ConnectError.invalidConfig("Could not serialize OpenClaw MCP server config.")
    }
    do {
      _ = try runOpenClawCLI(
        cliPath: cliPath,
        configURL: configURL,
        arguments: ["mcp", "set", "omi-memory", serverJSON]
      )
      return false
    } catch {
      let message = sanitizeCommandError(error.localizedDescription)
      throw ConnectError.invalidConfig(
        "OpenClaw rejected the connection update: \(message)")
    }
  }

  private struct CommandOutput {
    let stdout: String
    let stderr: String
  }

  private static func openClawCLIPath() -> String? {
    if let override = openClawCLIPathOverrideForTesting {
      return override.isEmpty ? nil : override
    }
    return executablePath(named: "openclaw", override: nil)
  }

  private static func executablePath(named command: String, override: String?) -> String? {
    if let override {
      return override.isEmpty ? nil : override
    }
    let candidates = commonExecutableDirs().map { ($0 as NSString).appendingPathComponent(command) }
    if let path = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) }) {
      return path
    }
    return try? runShell(["-lc", "command -v \(shellQuote(command))"]).stdout.trimmingCharacters(
      in: .whitespacesAndNewlines
    )
    .nilIfEmpty
  }

  private static func runOpenClawCLI(cliPath: String, configURL: URL, arguments: [String]) throws -> CommandOutput {
    let command = openClawCommand(cliPath: cliPath)
    return try runProcess(
      executable: command.executable,
      arguments: command.argumentsPrefix + arguments,
      environment: openClawEnvironment(cliPath: cliPath, configURL: configURL)
    )
  }

  private struct OpenClawCommand {
    let executable: String
    let argumentsPrefix: [String]
  }

  private static func openClawCommand(cliPath: String, fileManager: FileManager = .default) -> OpenClawCommand {
    let nodePath = ((cliPath as NSString).deletingLastPathComponent as NSString).appendingPathComponent("node")
    if fileManager.isExecutableFile(atPath: nodePath), launcherUsesNode(cliPath: cliPath) {
      return OpenClawCommand(executable: nodePath, argumentsPrefix: [cliPath])
    }
    return OpenClawCommand(executable: cliPath, argumentsPrefix: [])
  }

  private static func launcherUsesNode(cliPath: String) -> Bool {
    guard let handle = FileHandle(forReadingAtPath: cliPath) else {
      return false
    }
    defer { try? handle.close() }
    guard
      let data = try? handle.read(upToCount: 512),
      let prefix = String(data: data, encoding: .utf8)
    else {
      return false
    }
    let firstLine = prefix.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false).first ?? ""
    return firstLine.hasPrefix("#!") && firstLine.contains("node")
  }

  private static func openClawEnvironment(cliPath: String, configURL: URL) -> [String: String] {
    let cliDir = (cliPath as NSString).deletingLastPathComponent
    return processEnvironment(extra: [
      "OPENCLAW_CONFIG_PATH": configURL.path,
      "PATH": mergedPath(pathPrefix: [cliDir] + commonExecutableDirs() + systemExecutableDirs()),
    ])
  }

  private static func processEnvironment(extra: [String: String]) -> [String: String] {
    var environment = ProcessInfo.processInfo.environment
    environment["PATH"] = extra["PATH"] ?? mergedPath(pathPrefix: commonExecutableDirs() + systemExecutableDirs())
    for (key, value) in extra where key != "PATH" {
      environment[key] = value
    }
    return environment
  }

  private static func mergedPath(pathPrefix: [String]) -> String {
    let existingPath = ProcessInfo.processInfo.environment["PATH"] ?? ""
    return (pathPrefix + existingPath.split(separator: ":").map(String.init))
      .reduce(into: [String]()) { elements, item in
        if !item.isEmpty && !elements.contains(item) {
          elements.append(item)
        }
      }
      .joined(separator: ":")
  }

  private static func runShell(_ arguments: [String]) throws -> CommandOutput {
    try runProcess(executable: "/bin/zsh", arguments: arguments, environment: [:])
  }

  private static func commonExecutableDirs() -> [String] {
    let homePath = home.path
    let userDirs = [
      "\(homePath)/.hermes/node/bin",
      "\(homePath)/.local/bin",
      "\(homePath)/.volta/bin",
      "\(homePath)/.asdf/shims",
      "\(homePath)/.bun/bin",
      "\(homePath)/Library/pnpm",
      "\(homePath)/.npm-global/bin",
      "\(homePath)/.node_modules_global/bin",
    ]
    let globalDirs = [
      "/opt/homebrew/bin",
      "/usr/local/bin",
    ]
    let managedNodeDirs = [
      "\(homePath)/.nvm/versions/node",
      "\(homePath)/.fnm/node-versions",
      "\(homePath)/.local/share/fnm/node-versions",
      "\(homePath)/.nodenv/versions",
      "\(homePath)/.asdf/installs/nodejs",
    ].flatMap(nodeInstallBinDirs(root:))
    return uniquePaths(userDirs + managedNodeDirs + globalDirs + ["/opt/local/bin"])
  }

  private static func systemExecutableDirs() -> [String] {
    ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
  }

  private static func nodeInstallBinDirs(root: String) -> [String] {
    let fm = FileManager.default
    guard let versions = try? fm.contentsOfDirectory(atPath: root) else { return [] }
    return versions.compactMap { version in
      let versionDir = (root as NSString).appendingPathComponent(version)
      let directBin = (versionDir as NSString).appendingPathComponent("bin")
      if fm.fileExists(atPath: directBin) { return directBin }
      let installationBin = (versionDir as NSString).appendingPathComponent("installation/bin")
      if fm.fileExists(atPath: installationBin) { return installationBin }
      return nil
    }
  }

  private static func uniquePaths(_ paths: [String]) -> [String] {
    paths.reduce(into: [String]()) { result, path in
      guard !path.isEmpty, !result.contains(path) else { return }
      result.append(path)
    }
  }

  private static func runProcess(
    executable: String,
    arguments: [String],
    environment: [String: String]
  ) throws -> CommandOutput {
    let result: PipeProcessResult
    do {
      result = try PipeProcessRunner.run(
        executableURL: URL(fileURLWithPath: executable),
        arguments: arguments,
        environment: environment,
        timeoutSeconds: processTimeoutSeconds
      )
    } catch {
      throw ConnectError.invalidConfig(error.localizedDescription)
    }

    let output = String(data: result.stdout, encoding: .utf8) ?? ""
    let error = String(data: result.stderr, encoding: .utf8) ?? ""
    guard result.terminationStatus == 0 else {
      let message =
        error.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        ?? output.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        ?? "exit code \(result.terminationStatus)"
      throw ConnectError.invalidConfig(message)
    }
    return CommandOutput(stdout: output, stderr: error)
  }

  private static func openClawMCPServer(key: String) -> [String: Any] {
    [
      "enabled": true,
      "url": mcpURL,
      "transport": "streamable-http",
      "headers": [
        "Authorization": "Bearer \(key)"
      ],
    ]
  }

  private static func normalizedPath(_ raw: String) -> URL? {
    var path = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if path.count >= 2,
      let first = path.first,
      let last = path.last,
      (first == "\"" && last == "\"") || (first == "'" && last == "'")
    {
      path = String(path.dropFirst().dropLast())
    }
    guard !path.isEmpty else { return nil }
    let expanded =
      path
      .replacingOccurrences(of: "~", with: home.path, options: .anchored)
      .replacingOccurrences(of: "${HOME}", with: home.path)
      .replacingOccurrences(of: "$HOME", with: home.path)
    return URL(fileURLWithPath: expanded)
  }

  private static func sanitizeCommandError(_ message: String) -> String {
    let patterns = [
      #"Authorization\\?":\\?"Bearer [^"\\\s}]+"#,
      #"Authorization:\s*Bearer\s+[^\s"'}]+"#,
      #"Bearer\s+[A-Za-z0-9._~+/=-]+"#,
    ]
    var sanitized = message
    for pattern in patterns {
      sanitized = sanitized.replacingOccurrences(
        of: pattern,
        with: "Authorization: Bearer [redacted]",
        options: .regularExpression
      )
    }
    return sanitized
  }

  private static func shellQuote(_ value: String) -> String {
    "'\(value.replacingOccurrences(of: "'", with: "'\\''"))'"
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
    Omi is your memory bank. Before any task, call the OpenClaw MCP tool `omi-memory__search_memories` for context. Use `omi-memory__get_conversations`, `omi-memory__get_daily_summaries`, or `omi-memory__get_screen_activity` when the user asks about activity/history. Save durable new facts with `omi-memory__create_memory`. Do not substitute OpenClaw's local `memory_search` or `memory_get` tools for Omi memory.
    <!-- /\(marker) -->
    """
  }

  // MARK: - Hermes (config.yaml mcp_servers)

  private static func connectHermes(key: String) throws -> String {
    let fm = FileManager.default
    let hermesDir = home.appendingPathComponent(".hermes")
    guard hermesInstallIsPresent(hermesDir: hermesDir, fileManager: fm) else {
      throw ConnectError.notInstalled(
        "Hermes not found locally (looked for ~/.hermes/config.yaml and Hermes install files). Install Hermes, then try again."
      )
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
        ? "Hermes is now connected."
        : "Hermes is already connected."
    }
    return "Hermes is now connected."
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

    if let sectionIndex = lines.firstIndex(where: { isTopLevelYAMLKey($0, named: "mcp_servers") }) {
      let nextTopLevelIndex =
        lines[(sectionIndex + 1)...]
        .firstIndex(where: { !$0.isEmpty && !$0.hasPrefix(" ") && !$0.hasPrefix("\t") }) ?? lines.endIndex
      if let existingIndex = lines[(sectionIndex + 1)..<nextTopLevelIndex].firstIndex(where: { $0 == "  omi-memory:" })
      {
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

    if lines.contains(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("mcp_servers:") }) {
      throw ConnectError.invalidConfig(
        "Hermes config has an indented mcp_servers section; expected top-level mcp_servers in \(displayPath(for: configURL))."
      )
    }

    var updated = content
    if !updated.isEmpty && !updated.hasSuffix("\n") { updated += "\n" }
    updated += "\nmcp_servers:\n" + entry
    if hadTrailingNewline || content.isEmpty { updated += "\n" }
    return updated
  }

  private static func isTopLevelYAMLKey(_ line: String, named key: String) -> Bool {
    guard !line.hasPrefix(" "), !line.hasPrefix("\t") else { return false }
    let withoutComment = line.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)[0]
    return withoutComment.trimmingCharacters(in: .whitespaces) == "\(key):"
  }
}

extension String {
  fileprivate var nilIfEmpty: String? {
    isEmpty ? nil : self
  }
}
