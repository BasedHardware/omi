import Foundation

/// Manages the long-lived on-device Telegram MTProto helper subprocess and
/// translates its stdio JSON protocol into typed events.
///
/// Unlike iMessage (local chat.db + AppleScript), Telegram has no local message
/// store or send API, so all reads/sends go through this helper over MTProto. The
/// helper bootstraps its session from the already logged-in Telegram Desktop
/// `tdata` (via OpenTele) so there's no phone-code login, and the session never
/// leaves the Mac.
///
/// Events are delivered on the main actor via `onEvent` so the inbox store can
/// consume them directly.
final class TelegramClientService: @unchecked Sendable {
  static let shared = TelegramClientService()

  /// Set by the store before starting; receives every decoded helper event on the
  /// main actor.
  var onEvent: (@MainActor (TelegramHelperEvent) -> Void)?

  private let queue = DispatchQueue(label: "com.omi.telegram.client")
  private var process: Process?
  private var stdinHandle: FileHandle?
  private var stdoutBuffer = Data()

  private var isRunning: Bool { process?.isRunning ?? false }

  // MARK: - Config

  /// Where the Telegram Desktop session lives on this Mac.
  static var defaultTdataPath: String {
    NSString(string: "~/Library/Application Support/Telegram Desktop/tdata").expandingTildeInPath
  }

  /// True when driving the fake `--selftest` helper (integration testing without
  /// Telegram/network).
  static var isSelftest: Bool { ProcessInfo.processInfo.environment["OMI_TELEGRAM_SELFTEST"] == "1" }

  /// True when a local Telegram Desktop install with tdata is present to bootstrap
  /// from (always true under selftest so the connect flow is reachable).
  static func telegramDesktopPresent() -> Bool {
    isSelftest || FileManager.default.fileExists(atPath: defaultTdataPath)
  }

  /// Persisted Telethon session string (stays on-device, never uploaded).
  private static var sessionFilePath: String {
    let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
      .appendingPathComponent("Omi", isDirectory: true)
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    return dir.appendingPathComponent("telegram.session").path
  }

  static var hasSession: Bool {
    let p = sessionFilePath
    guard let data = try? Data(contentsOf: URL(fileURLWithPath: p)) else { return false }
    return !data.isEmpty
  }

  private struct HelperLaunch {
    let executable: URL
    let leadingArgs: [String]  // e.g. the .py path when running via python3 in dev
  }

  /// Resolve how to launch the helper: bundled frozen binary in production, or a
  /// dev override (env vars) pointing at the .py so it can be exercised without a
  /// notarized build.
  private func resolveLaunch() -> HelperLaunch? {
    let env = ProcessInfo.processInfo.environment
    if let bin = env["OMI_TELEGRAM_HELPER"], FileManager.default.isExecutableFile(atPath: bin) {
      return HelperLaunch(executable: URL(fileURLWithPath: bin), leadingArgs: [])
    }
    if let py = env["OMI_TELEGRAM_HELPER_PY"] {
      let python = env["OMI_TELEGRAM_PYTHON"] ?? "/usr/bin/env"
      let lead = python == "/usr/bin/env" ? ["python3", py] : [py]
      return HelperLaunch(executable: URL(fileURLWithPath: python), leadingArgs: lead)
    }
    if let bundled = Bundle.main.url(forResource: "omi-telegram-helper", withExtension: nil) {
      return HelperLaunch(executable: bundled, leadingArgs: [])
    }
    return nil
  }

  // ⚠️ PRE-PRODUCTION REQUIREMENT — Telegram MTProto app credentials.
  //
  // The shipped app MUST provide Omi's OWN api_id/api_hash, registered once at
  // https://my.telegram.org as "Omi" and injected via the Info.plist keys
  // `OMITelegramAPIID` / `OMITelegramAPIHash` (these identify the *app*, shared by
  // all users' sessions — they are not per-user or OAuth-style secrets).
  //
  // Until then, dev/live testing passes a pair via OMI_TELEGRAM_API_ID/HASH env
  // (currently Telegram Desktop's PUBLIC 2040 pair). The public pair is a stopgap:
  // shared public creds are the most likely to trip Telegram's anti-abuse
  // heuristics, so this MUST be switched to an Omi-registered pair before release.
  // See desktop/macos/telegram-helper/README.md and the feature plan.
  private func apiCredentials() -> (id: String, hash: String) {
    let env = ProcessInfo.processInfo.environment
    let id =
      env["OMI_TELEGRAM_API_ID"]
      ?? (Bundle.main.object(forInfoDictionaryKey: "OMITelegramAPIID") as? String) ?? "0"
    let hash =
      env["OMI_TELEGRAM_API_HASH"]
      ?? (Bundle.main.object(forInfoDictionaryKey: "OMITelegramAPIHash") as? String) ?? ""
    return (id, hash)
  }

  // MARK: - Lifecycle

  /// Start the helper process (idempotent). Returns false if the helper can't be located.
  @discardableResult
  func start() -> Bool {
    guard !isRunning else { return true }
    guard let launch = resolveLaunch() else {
      NSLog("Telegram: helper binary not found (set OMI_TELEGRAM_HELPER or bundle it)")
      return false
    }
    let creds = apiCredentials()
    let selftest = ProcessInfo.processInfo.environment["OMI_TELEGRAM_SELFTEST"] == "1"

    let process = Process()
    process.executableURL = launch.executable
    if selftest {
      process.arguments = launch.leadingArgs + ["--selftest"]
    } else {
      process.arguments =
        launch.leadingArgs + [
          "--api-id", creds.id, "--api-hash", creds.hash,
          "--session-file", Self.sessionFilePath,
        ]
    }

    let stdinPipe = Pipe()
    let stdoutPipe = Pipe()
    let stderrPipe = Pipe()
    process.standardInput = stdinPipe
    process.standardOutput = stdoutPipe
    process.standardError = stderrPipe

    stdoutPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
      let data = handle.availableData
      guard !data.isEmpty else { return }
      self?.queue.async { self?.ingest(data) }
    }
    stderrPipe.fileHandleForReading.readabilityHandler = { handle in
      let data = handle.availableData
      if let s = String(data: data, encoding: .utf8), !s.isEmpty {
        NSLog("Telegram helper: %@", s.trimmingCharacters(in: .whitespacesAndNewlines))
      }
    }
    process.terminationHandler = { [weak self] _ in
      self?.queue.async {
        self?.stdinHandle = nil
        self?.process = nil
      }
    }

    do {
      try process.run()
    } catch {
      NSLog("Telegram: failed to launch helper: %@", error.localizedDescription)
      return false
    }
    self.process = process
    self.stdinHandle = stdinPipe.fileHandleForWriting
    return true
  }

  func shutdown() {
    send(command: ["cmd": "shutdown"])
    queue.asyncAfter(deadline: .now() + 1.0) { [weak self] in
      if self?.process?.isRunning == true { self?.process?.terminate() }
    }
  }

  // MARK: - Commands

  func bootstrap(passcode: String?) {
    var cmd: [String: Any] = ["cmd": "bootstrap", "tdata_path": Self.defaultTdataPath]
    if let passcode, !passcode.isEmpty { cmd["passcode"] = passcode }
    send(command: cmd)
  }

  func connect() { send(command: ["cmd": "connect"]) }
  func startListening(backfillDays: Int = 90) {
    send(command: ["cmd": "start_listening", "backfill_days": backfillDays])
  }
  func send(chatID: String, text: String) {
    send(command: ["cmd": "send", "chat_id": chatID, "text": text])
  }

  private func send(command: [String: Any]) {
    queue.async { [weak self] in
      guard let self, let handle = self.stdinHandle else { return }
      guard
        let data = try? JSONSerialization.data(withJSONObject: command),
        var line = String(data: data, encoding: .utf8)
      else { return }
      line += "\n"
      if let out = line.data(using: .utf8) {
        do { try handle.write(contentsOf: out) } catch {
          NSLog("Telegram: stdin write failed: %@", error.localizedDescription)
        }
      }
    }
  }

  // MARK: - stdout decoding (runs on `queue`)

  private func ingest(_ data: Data) {
    stdoutBuffer.append(data)
    let newline = UInt8(ascii: "\n")
    while let idx = stdoutBuffer.firstIndex(of: newline) {
      let lineData = stdoutBuffer.subdata(in: stdoutBuffer.startIndex..<idx)
      stdoutBuffer.removeSubrange(stdoutBuffer.startIndex...idx)
      guard !lineData.isEmpty else { continue }
      decodeAndDispatch(lineData)
    }
  }

  private func decodeAndDispatch(_ lineData: Data) {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601WithFractional
    guard let event = try? decoder.decode(TelegramHelperEvent.self, from: lineData) else {
      if let s = String(data: lineData, encoding: .utf8) {
        NSLog("Telegram: undecodable helper line: %@", s)
      }
      return
    }
    if let handler = onEvent {
      Task { @MainActor in handler(event) }
    }
  }
}

extension JSONDecoder.DateDecodingStrategy {
  /// ISO8601 with optional fractional seconds, tolerant of both forms the helper emits.
  static var iso8601WithFractional: JSONDecoder.DateDecodingStrategy {
    .custom { decoder in
      let container = try decoder.singleValueContainer()
      let s = try container.decode(String.self)
      let withFrac = ISO8601DateFormatter()
      withFrac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      if let d = withFrac.date(from: s) { return d }
      let plain = ISO8601DateFormatter()
      plain.formatOptions = [.withInternetDateTime]
      if let d = plain.date(from: s) { return d }
      throw DecodingError.dataCorruptedError(
        in: container, debugDescription: "Bad ISO8601 date: \(s)")
    }
  }
}
