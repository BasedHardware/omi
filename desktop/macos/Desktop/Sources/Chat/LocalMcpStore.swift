import Foundation

extension Notification.Name {
  /// Posted after ~/.omi/mcp.json changes on disk — a server added, removed,
  /// retargeted, or re-authed from the UI, and a hand-edit noticed by
  /// `checkForExternalChanges()`. The agent runtime reads the file once per
  /// process spawn, so ChatProvider respawns it in response.
  static let omiUserMcpDidChange = Notification.Name("omiUserMcpDidChange")
}

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
  }

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
    guard !slug.isEmpty else {
      throw storeError("Server name must contain letters or numbers")
    }
    let parts = try splitCommandLine(commandLine)
    guard let command = parts.first, !command.isEmpty else {
      throw storeError("Enter the command to run, e.g. npx @playwright/mcp@latest")
    }
    var servers = readServers()
    var entry: [String: Any] = ["command": command]
    if parts.count > 1 { entry["args"] = Array(parts.dropFirst()) }
    servers[slug] = entry
    try writeServers(servers)
  }

  /// Split a command line into argv the way a shell would for the cases users
  /// hit: bare words, and runs quoted with `"` or `'` kept whole — a quoted
  /// path with spaces stays one argument, and a quote toggles quoting from
  /// anywhere in a word, so `--filter="App Store"` survives as one argument
  /// too. Backslash escapes are not interpreted; quote a path instead of
  /// escaping it. Runs of spaces or tabs separate words outside quotes. An
  /// unterminated quote is a typo that would mangle the command at spawn, so
  /// it throws rather than guessing.
  static func splitCommandLine(_ line: String) throws -> [String] {
    var parts: [String] = []
    var current = ""
    var inWord = false
    var quote: Character?
    for character in line {
      switch character {
      case "\"", "'":
        if let open = quote {
          if open == character { quote = nil } else { current.append(character) }
        } else {
          quote = character
          inWord = true
        }
      case " ", "\t":
        guard quote == nil else {
          current.append(character)
          continue
        }
        if inWord {
          parts.append(current)
          current = ""
          inWord = false
        }
      default:
        current.append(character)
        inWord = true
      }
    }
    guard quote == nil else {
      throw storeError("The command has an unmatched quote")
    }
    if inWord { parts.append(current) }
    return parts
  }

  static func removeServer(name: String) {
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
    try fm.createDirectory(
      at: LocalSkillsStore.rootURL, withIntermediateDirectories: true,
      attributes: [.posixPermissions: 0o700])
    // The directory also holds auth material (token-bearing mcp.json, skills),
    // so it must not be world-listable — a directory that predates this
    // hardening keeps its looser mode, so re-assert on every write.
    try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: LocalSkillsStore.rootURL.path)
    let data = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    // The file carries OAuth access/refresh tokens and client secrets, so it
    // is user-only. The atomic rename replaces the file wholesale, so the
    // chmod must run on every write — it both sets the new file's mode and
    // tightens a file written by an older build.
    try data.write(to: fileURL, options: .atomic)
    try? fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
    recordWriteFingerprint()
    notifyChanged()
  }

  // MARK: - Change notification

  private static let fingerprintLock = NSLock()
  // Guarded by `fingerprintLock`.
  private nonisolated(unsafe) static var lastWriteFingerprint: (modified: Date, size: Int)?

  /// Records the just-written file state so `checkForExternalChanges()` does
  /// not read our own write back as a hand-edit.
  private static func recordWriteFingerprint() {
    fingerprintLock.lock()
    defer { fingerprintLock.unlock() }
    lastWriteFingerprint = fileFingerprint()
  }

  private static func fileFingerprint() -> (modified: Date, size: Int)? {
    guard let attributes = try? FileManager.default.attributesOfItem(atPath: fileURL.path),
      let modified = attributes[.modificationDate] as? Date
    else { return nil }
    return (modified, attributes[.size] as? Int ?? 0)
  }

  /// Cheap source-of-truth check for edits made outside this process (the file
  /// is hand-editable by design, and nothing watches it). Call when the Apps
  /// page shows the server section: a stat, and a notification only when the
  /// file actually moved under us. The first observation in a process adopts
  /// the file silently — there is no earlier baseline to diff against.
  /// Returns whether an external change was detected.
  @discardableResult
  static func checkForExternalChanges() -> Bool {
    fingerprintLock.lock()
    defer { fingerprintLock.unlock() }
    let current = fileFingerprint()
    if current?.modified == lastWriteFingerprint?.modified, current?.size == lastWriteFingerprint?.size {
      return false
    }
    let hadBaseline = lastWriteFingerprint != nil
    lastWriteFingerprint = current
    guard hadBaseline else { return false }
    notifyChanged()
    return true
  }

  /// Test seam: clears the recorded fingerprint so a test process does not
  /// inherit another test's baseline.
  static func resetChangeDetectionForTesting() {
    fingerprintLock.lock()
    defer { fingerprintLock.unlock() }
    lastWriteFingerprint = nil
  }

  private static func notifyChanged() {
    if Thread.isMainThread {
      NotificationCenter.default.post(name: .omiUserMcpDidChange, object: nil)
    } else {
      DispatchQueue.main.async {
        NotificationCenter.default.post(name: .omiUserMcpDidChange, object: nil)
      }
    }
  }

  static func storeError(_ message: String) -> Error {
    NSError(domain: "LocalMcpStore", code: 1, userInfo: [NSLocalizedDescriptionKey: message])
  }
}

/// Applies changes to ~/.omi/mcp.json to the running agent runtime.
///
/// Unlike the skills catalog — which the runtime re-reads per turn to build the
/// prompt — the pi-mono extension registers its `mcp_tools_info` / `mcp_call`
/// proxy tools once at process spawn, so a saved, removed, or re-authed server
/// reaches chat only after the shared bridge respawns. Respawns are debounced
/// (a marketplace install burst, or one OAuth refresh sweeping several tokens,
/// costs one respawn) and never land mid-turn: a change noticed while a query
/// is streaming stays pending until the next turn's bridge-readiness check,
/// which is the safe point between turns. A change that lands while nothing is
/// warm — the real instance is the runtime's own token refresh, which fires
/// unawaited during a spawn — survives the whole stop → spawn → warmup window
/// and applies at the next boundary instead of being dropped. After a
/// successful respawn the coordinator re-stats the file through the store's
/// external-change semantics, so a hand-edit that landed mid-respawn (after
/// the new process may have read the file) applies again, while the runtime's
/// own writes stay excluded and cannot chase it into a respawn loop. The
/// runtime's own restart refuses while requests are active (a background agent
/// mid-run, for example), which defers the respawn the same way.
///
/// The closures exist so the decision logic is testable without a runtime.
@MainActor
final class UserMcpRuntimeRefresh {
  static let debounceNanoseconds: UInt64 = 500_000_000

  /// The process-wide coordinator. ChatProvider binds it to the main
  /// provider's bridge state at init; its notification observer feeds it and
  /// its bridge-readiness check consumes it. Task chat consumes the same
  /// pending state at its own boundary (TaskChatRuntime.sharedBridge) because
  /// a task-chat-only session never calls ensureBridgeStarted — and both
  /// surfaces drive the one shared runtime process. Before a provider exists
  /// nothing has observed a change, so there is no deferred state to apply
  /// and the neutral bindings below simply refuse to respawn.
  static let shared = UserMcpRuntimeRefresh(
    isTurnActive: { false },
    isRuntimeStarted: { false },
    respawn: { throw BridgeError.stopped })

  private let debounce: (UInt64) async -> Void
  private var isTurnActive: () -> Bool
  private var isRuntimeStarted: () -> Bool
  private var respawn: () async throws -> Void
  private var pendingChange = false
  private var debounceInFlight = false
  private var cycleTask: Task<Void, Never>?

  init(
    debounce: @escaping (UInt64) async -> Void = { try? await Task.sleep(nanoseconds: $0) },
    isTurnActive: @escaping () -> Bool,
    isRuntimeStarted: @escaping () -> Bool,
    respawn: @escaping () async throws -> Void
  ) {
    self.debounce = debounce
    self.isTurnActive = isTurnActive
    self.isRuntimeStarted = isRuntimeStarted
    self.respawn = respawn
  }

  /// Rebinds the questions the coordinator asks. Production: ChatProvider's
  /// init installs closures over its own bridge state, so the shared
  /// coordinator has exactly one view of the runtime. Tests install doubles.
  func bindRuntime(
    isTurnActive: @escaping () -> Bool,
    isRuntimeStarted: @escaping () -> Bool,
    respawn: @escaping () async throws -> Void
  ) {
    self.isTurnActive = isTurnActive
    self.isRuntimeStarted = isRuntimeStarted
    self.respawn = respawn
  }

  /// A `.omiUserMcpDidChange` notification arrived. Coalesces while a debounced
  /// cycle is already in flight; the in-flight cycle picks the change up.
  func changeDetected() {
    pendingChange = true
    guard !debounceInFlight else { return }
    debounceInFlight = true
    cycleTask = Task { [weak self] in
      await self?.runDebounceCycle()
    }
  }

  private func runDebounceCycle() async {
    await debounce(Self.debounceNanoseconds)
    debounceInFlight = false
    await applyPendingChange(onlyWhenIdle: true)
  }

  /// Test seam: awaits the debounced cycle so tests observe its outcome
  /// deterministically instead of sleeping on the wall clock.
  func awaitDebouncedCycleForTesting() async {
    await cycleTask?.value
  }

  /// Turn-boundary retry, called from the bridge-readiness check before a turn
  /// issues any runtime work. Not gated on the send lock the way the idle path
  /// is: at this point the caller's turn has produced no requests, and the
  /// runtime's restart still refuses if some other surface's requests are
  /// active.
  func applyAtTurnBoundary() async {
    await applyPendingChange(onlyWhenIdle: false)
  }

  private func applyPendingChange(onlyWhenIdle: Bool) async {
    guard pendingChange else { return }
    if onlyWhenIdle, isTurnActive() { return }  // stays pending; retried at the next boundary
    // Nothing warm to respawn — but the change must not vanish: the stop →
    // spawn → warmup window is exactly when the runtime's own writes (the
    // unawaited OAuth token refresh at spawn) notify, and a spawn already in
    // flight may have read the file before the change landed. It stays
    // pending for the next boundary instead of being dropped.
    guard isRuntimeStarted() else { return }
    pendingChange = false
    do {
      try await respawn()
    } catch {
      // The respawn did not happen. Keep the change pending so the next turn
      // boundary retries once the refusal clears.
      pendingChange = true
      return
    }
    // The runtime reads mcp.json at some point during its startup, so a
    // change that landed mid-respawn may postdate the spawn's read. Re-stat
    // through the store's external-change semantics: writes made by this
    // process (the token refresh writes through the same store) are recorded
    // by the write path and stay excluded, so the runtime's own refresh
    // during a spawn cannot chase this into a respawn loop.
    if LocalMcpStore.checkForExternalChanges() {
      pendingChange = true
    }
  }
}
