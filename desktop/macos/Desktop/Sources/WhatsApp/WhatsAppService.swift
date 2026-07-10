import Combine
import Foundation

enum WAConnectionState: Equatable, Sendable {
  case disconnected
  case downloading
  case pairing(qr: String)
  case pairingTerminal(qrText: String)
  case connecting
  case connected
  case degraded(reason: String)
  case needsReauth

  var isConnected: Bool {
    if case .connected = self { return true }
    return false
  }

  var isDegraded: Bool {
    if case .degraded = self { return true }
    return false
  }

  var statusText: String {
    switch self {
    case .disconnected:
      return "Not connected"
    case .downloading:
      return "Downloading WhatsApp helper..."
    case .pairing, .pairingTerminal:
      return "Waiting for scan..."
    case .connecting:
      return "Linking..."
    case .connected:
      return "Connected"
    case .degraded(let reason):
      return reason.isEmpty ? "Connection degraded" : reason
    case .needsReauth:
      return "Reconnect required"
    }
  }
}

struct WAHealth: Equatable, Sendable {
  let isAvailable: Bool
  let isAuthenticated: Bool
  let isConnected: Bool
  let summary: String
  let rawJSON: String?
}

@MainActor
final class WhatsAppState: ObservableObject {
  static let shared = WhatsAppState()

  @Published private(set) var connectionState: WAConnectionState = .disconnected
  @Published private(set) var lastEventSummary: String?
  @Published private(set) var storePath: String = WhatsAppService.defaultStoreDirectory()

  private init() {}

  func update(connectionState: WAConnectionState) {
    self.connectionState = connectionState
  }

  func update(lastEventSummary: String?) {
    self.lastEventSummary = lastEventSummary
  }

  func update(storePath: String) {
    self.storePath = storePath
  }
}

actor WhatsAppService {
  static let shared = WhatsAppService()

  private var authProcess: Process?
  private var followProcess: Process?
  private var authReadTask: Task<Void, Never>?
  private var followReadTask: Task<Void, Never>?
  private var authGeneration = 0
  private var followGeneration = 0
  private var followRestartAttempts = 0
  private var isStartingFollow = false
  private var followLastExitWasStoreLocked = false
  private var expectedAuthStopGenerations: Set<Int> = []
  private var disconnectRequested = false
  private var isCapturingTerminalQR = false
  private var terminalQRLines: [String] = []

  private init() {}

  static func defaultStoreDirectory(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String {
    let bundleComponent = (bundleIdentifier?.isEmpty == false ? bundleIdentifier : "com.omi.desktop-dev")
      ?? "com.omi.desktop-dev"
    return homeDirectory
      .appendingPathComponent("Library")
      .appendingPathComponent("Application Support")
      .appendingPathComponent("Omi")
      .appendingPathComponent("whatsapp")
      .appendingPathComponent(bundleComponent)
      .path
  }

  static func findWacliBinary() -> String? {
    if let installed = WacliInstaller.findInstalledBinary() {
      return installed
    }

    // Dev overrides / local installs — never require a binary shipped in the app bundle.
    let candidates = [
      ProcessInfo.processInfo.environment["OMI_WACLI_BIN"],
      "/opt/homebrew/bin/wacli",
      "/usr/local/bin/wacli",
    ].compactMap { $0 }

    for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
      return path
    }

    let whichProcess = Process()
    whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
    whichProcess.arguments = ["wacli"]
    let pipe = Pipe()
    whichProcess.standardOutput = pipe
    try? whichProcess.run()
    whichProcess.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
      !path.isEmpty,
      FileManager.default.isExecutableFile(atPath: path)
    {
      return path
    }

    return nil
  }

  /// Resolves wacli, downloading into Application Support on first connect when needed.
  static func ensureWacliBinary() async throws -> String {
    if let existing = findWacliBinary(),
      WacliInstaller.supportsRequiredAuthFlags(binaryPath: existing)
    {
      return existing
    }
    return try await WacliInstaller.ensureInstalled()
  }

  func pair() async {
    disconnectRequested = false
    await updateStorePath()

    let state = await currentState()
    if followProcess?.isRunning == true || state.isConnected {
      await setState(.connected)
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Connected") }
      log("WhatsAppService: pair skipped because WhatsApp is already connected")
      return
    }

    await stopAuthProcess()

    let binary: String
    do {
      if Self.findWacliBinary() == nil {
        await setState(.downloading)
        await MainActor.run {
          WhatsAppState.shared.update(lastEventSummary: "Downloading WhatsApp helper")
        }
      }
      binary = try await Self.ensureWacliBinary()
    } catch {
      let message = (error as? LocalizedError)?.errorDescription ?? "Failed to download WhatsApp helper"
      await setState(.degraded(reason: message))
      log("WhatsAppService: wacli install failed: \(error)")
      return
    }

    // If this store is already authenticated, resume sync instead of showing a new QR.
    let doctor = await runOneShot(binary: binary, arguments: ["doctor"])
    if doctor.exitCode == 0, parseDoctorAuthenticated(doctor.output) {
      log("WhatsAppService: pair found existing authenticated store; resuming sync")
      await startFollow()
      return
    }

    do {
      isCapturingTerminalQR = false
      terminalQRLines = []
      let process = try makeProcess(
        binary: binary,
        arguments: ["--events", "auth", "--qr-format", "text", "--idle-exit", "5m"],
        json: false
      )
      authGeneration &+= 1
      let generation = authGeneration
      authProcess = process
      await setState(.connecting)

      process.terminationHandler = { [weak self] terminatedProcess in
        let exitCode = terminatedProcess.terminationStatus
        Task { await self?.handleAuthTermination(exitCode: exitCode, generation: generation) }
      }

      try process.run()
      authReadTask = readLines(from: process, label: "auth") { [weak self] line in
        await self?.handleAuthLine(line)
      }
      log("WhatsAppService: started wacli --store <store> --events auth --qr-format text")
    } catch {
      await setState(.degraded(reason: "Failed to start wacli auth"))
      log("WhatsAppService: failed to start auth: \(error)")
    }
  }

  func startFollow() async {
    disconnectRequested = false
    await updateStorePath()

    if isStartingFollow {
      log("WhatsAppService: sync start skipped because another start is in progress")
      return
    }
    if followProcess?.isRunning == true {
      await setState(.connected)
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Connected") }
      log("WhatsAppService: sync start skipped because sync is already running")
      return
    }

    isStartingFollow = true
    defer { isStartingFollow = false }
    await stopFollowProcess()

    let binary: String
    do {
      binary = try await Self.ensureWacliBinary()
    } catch {
      let message = (error as? LocalizedError)?.errorDescription ?? "Failed to download WhatsApp helper"
      await setState(.degraded(reason: message))
      log("WhatsAppService: wacli install failed for sync: \(error)")
      return
    }

    do {
      await WhatsAppWebhookServer.shared.startIfNeeded()
      let webhookURL = await WhatsAppWebhookServer.shared.url
      let process = try makeProcess(
        binary: binary,
        arguments: [
          "--events",
          "sync",
          "--follow",
          "--webhook", webhookURL,
          "--webhook-allow-private",
        ]
      )
      followGeneration &+= 1
      let generation = followGeneration
      followProcess = process

      process.terminationHandler = { [weak self] terminatedProcess in
        let exitCode = terminatedProcess.terminationStatus
        Task { await self?.handleFollowTermination(exitCode: exitCode, generation: generation) }
      }

      try process.run()
      followReadTask = readLines(from: process, label: "sync") { [weak self] line in
        await self?.handleFollowLine(line)
      }
      followLastExitWasStoreLocked = false
      await setState(.connected)
      await handleConnectedSyncSideEffects()
      log("WhatsAppService: started wacli --store <store> --json --events sync --follow --webhook <local>")
    } catch {
      await setState(.degraded(reason: "Failed to start WhatsApp sync"))
      log("WhatsAppService: failed to start sync: \(error)")
    }
  }

  func resumeIfAuthenticated() async {
    guard authProcess == nil, followProcess == nil else { return }
    // Only resume when a helper is already present — never auto-download on launch.
    guard let binary = Self.findWacliBinary() else { return }

    let result = await runOneShot(binary: binary, arguments: ["doctor"])
    guard result.exitCode == 0, parseDoctorAuthenticated(result.output) else {
      log("WhatsAppService: resume skipped; doctor did not report authenticated")
      return
    }

    await startFollow()
  }

  func health() async -> WAHealth {
    guard let binary = Self.findWacliBinary() else {
      return WAHealth(
        isAvailable: false,
        isAuthenticated: false,
        isConnected: false,
        summary: "WhatsApp helper not downloaded yet",
        rawJSON: nil
      )
    }

    let result = await runOneShot(binary: binary, arguments: ["doctor"])
    guard result.exitCode == 0 else {
      return WAHealth(
        isAvailable: true,
        isAuthenticated: false,
        isConnected: false,
        summary: result.output.isEmpty ? "doctor failed with exit \(result.exitCode)" : result.output,
        rawJSON: result.output
      )
    }

    let authenticated = parseDoctorAuthenticated(result.output)
    let connected = parseDoctorConnected(result.output)
    return WAHealth(
      isAvailable: true,
      isAuthenticated: authenticated,
      isConnected: connected,
      summary: connected ? "Connected" : (authenticated ? "Authenticated, syncing" : "Not connected"),
      rawJSON: result.output
    )
  }

  func disconnect() async {
    disconnectRequested = true
    await stopAuthProcess()
    await stopFollowProcess()

    if let binary = Self.findWacliBinary() {
      _ = await runOneShot(binary: binary, arguments: ["auth", "logout"])
    }

    let storeDir = Self.defaultStoreDirectory()
    try? FileManager.default.removeItem(atPath: storeDir)
    await setState(.disconnected)
    await MainActor.run {
      WhatsAppState.shared.update(lastEventSummary: nil)
      WhatsAppState.shared.update(storePath: storeDir)
    }
    log("WhatsAppService: disconnected and removed store at \(storeDir)")
  }

  private func makeProcess(binary: String, arguments: [String], json: Bool = true) throws -> Process {
    try FileManager.default.createDirectory(
      atPath: Self.defaultStoreDirectory(),
      withIntermediateDirectories: true
    )

    let process = Process()
    process.executableURL = URL(fileURLWithPath: binary)
    var processArguments = ["--store", Self.defaultStoreDirectory()]
    if json {
      processArguments.append("--json")
    }
    process.arguments = processArguments + arguments

    var env = ProcessInfo.processInfo.environment
    let binaryDir = (binary as NSString).deletingLastPathComponent
    let existingPath = env["PATH"] ?? "/usr/bin:/bin"
    if !existingPath.components(separatedBy: ":").contains(binaryDir) {
      env["PATH"] = "\(binaryDir):\(existingPath)"
    }
    process.environment = env

    let outputPipe = Pipe()
    process.standardOutput = outputPipe
    process.standardError = outputPipe
    return process
  }

  private func readLines(
    from process: Process,
    label: String,
    handler: @escaping @Sendable (String) async -> Void
  ) -> Task<Void, Never> {
    guard let stdout = process.standardOutput as? Pipe else {
      return Task {}
    }

    return Task.detached {
      let handle = stdout.fileHandleForReading
      var buffer = Data()

      while !Task.isCancelled {
        let chunk = handle.availableData
        if chunk.isEmpty { break }
        buffer.append(chunk)

        while let newlineIndex = buffer.firstIndex(of: UInt8(ascii: "\n")) {
          let lineData = buffer[buffer.startIndex..<newlineIndex]
          buffer = Data(buffer[buffer.index(after: newlineIndex)...])

          guard let line = String(data: lineData, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !line.isEmpty
          else {
            continue
          }
          await handler(line)
        }
      }
    }
  }

  private func handleAuthLine(_ line: String) async {
    log("WhatsAppService auth event: \(line.prefix(500))")
    let cleanLine = stripANSI(line)
    if cleanLine.contains("unknown flag: --events") || cleanLine.contains("unknown flag: --qr-format") {
      let message = "WhatsApp helper is too old. Reconnect to download an update."
      await setState(.degraded(reason: message))
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: message) }
      return
    }

    if await handleTerminalQRLine(cleanLine) {
      return
    }

    if looksLikeRawQRPayload(cleanLine) {
      await setState(.pairing(qr: cleanLine))
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Waiting for scan") }
      return
    }

    guard let event = parseEvent(line) else { return }
    let eventName = normalizedEventName(event)

    if isWarningEvent(eventName) {
      log("WhatsAppService: auth warning: \((warningSummary(from: event) ?? line).prefix(300))")
      return
    }

    if let error = extractError(from: event), !error.isEmpty {
      if error.contains("store is locked"), followProcess?.isRunning == true {
        await setState(.connected)
        await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Connected") }
        log("WhatsAppService: ignored auth store lock because sync is already running")
        return
      }
      await setState(.degraded(reason: error))
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: error) }
      return
    }

    if let qr = extractQR(from: event), !qr.isEmpty {
      await setState(.pairing(qr: qr))
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Waiting for scan") }
      return
    }

    if isConnectedEvent(eventName, event: event) || parseAuthenticated(event) {
      await setState(.connected)
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Connected") }
      await stopAuthProcess()
      await startFollow()
    } else if isNeedsReauthEvent(eventName, event: event) {
      await setState(.needsReauth)
    }
  }

  private func handleFollowLine(_ line: String) async {
    log("WhatsAppService sync event: \(line.prefix(500))")
    guard let event = parseEvent(line) else { return }

    let eventName = normalizedEventName(event)
    if isWarningEvent(eventName) {
      log("WhatsAppService: sync warning: \((warningSummary(from: event) ?? line).prefix(300))")
      return
    }

    if let error = extractError(from: event), !error.isEmpty {
      if isStoreLockError(error) {
        followLastExitWasStoreLocked = true
        await setState(.connected)
        await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Connected") }
        log("WhatsAppService: sync store lock is transient; will retry after current wacli exits")
        return
      }
      await setState(.degraded(reason: error))
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: error) }
      return
    }

    if eventName.contains("message.received") || eventName == "message" || eventName.contains("received") {
      followRestartAttempts = 0
      let summary = summarizeMessageEvent(event)
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: summary) }
      if let message = WAIncomingMessage(event: event) {
        await WhatsAppReplyCoordinator.shared.handle(message)
      }
    } else if isTransientSyncEvent(eventName) {
      followRestartAttempts = 0
      await setState(.connected)
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: eventName == "reconnecting" ? "Reconnecting" : "Connected") }
    } else if isNeedsReauthEvent(eventName, event: event) {
      await setState(.needsReauth)
    } else if isConnectedEvent(eventName, event: event) {
      followRestartAttempts = 0
      await setState(.connected)
      await handleConnectedSyncSideEffects()
    }
  }

  private func handleAuthTermination(exitCode: Int32, generation: Int) async {
    if expectedAuthStopGenerations.remove(generation) != nil {
      log("WhatsAppService: auth exited with \(exitCode) after expected stop")
      return
    }
    guard generation == authGeneration else { return }
    authReadTask?.cancel()
    authReadTask = nil
    authProcess = nil
    let state = await currentState()
    if !disconnectRequested, exitCode != 0, !state.isConnected, !state.isDegraded {
      await setState(.degraded(reason: "WhatsApp auth exited with \(exitCode)"))
    }
    log("WhatsAppService: auth exited with \(exitCode)")
  }

  private func handleFollowTermination(exitCode: Int32, generation: Int) async {
    guard generation == followGeneration else { return }
    followReadTask?.cancel()
    followReadTask = nil
    followProcess = nil
    log("WhatsAppService: sync exited with \(exitCode)")

    guard !disconnectRequested else { return }
    if exitCode != 0, (await currentState()) == .needsReauth {
      return
    }

    followRestartAttempts += 1
    let delaySeconds = min(Double(followRestartAttempts * 2), 30)
    if followLastExitWasStoreLocked {
      followLastExitWasStoreLocked = false
      await setState(.connected)
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Connected") }
      log("WhatsAppService: sync store lock retry in \(delaySeconds)s")
    } else {
      await setState(.degraded(reason: "WhatsApp sync stopped"))
    }
    try? await Task.sleep(nanoseconds: UInt64(delaySeconds * 1_000_000_000))
    guard !disconnectRequested else { return }
    await startFollow()
  }

  private func stopAuthProcess() async {
    authReadTask?.cancel()
    authReadTask = nil
    if authProcess?.isRunning == true {
      expectedAuthStopGenerations.insert(authGeneration)
    }
    await terminate(authProcess)
    authProcess = nil
  }

  private func stopFollowProcess() async {
    followReadTask?.cancel()
    followReadTask = nil
    await terminate(followProcess)
    followProcess = nil
  }

  private func terminate(_ process: Process?) async {
    guard let process else { return }
    await Task.detached(priority: .utility) {
      if process.isRunning {
        process.terminate()
        let start = Date()
        while process.isRunning && Date().timeIntervalSince(start) < 2 {
          try? await Task.sleep(nanoseconds: 50_000_000)
        }
        if process.isRunning {
          kill(process.processIdentifier, SIGKILL)
        }
      }
    }.value
  }

  private func runOneShot(binary: String, arguments: [String]) async -> (output: String, exitCode: Int32) {
    do {
      let process = try makeProcess(binary: binary, arguments: arguments)
      let output = process.standardOutput as? Pipe
      try process.run()
      let data = output?.fileHandleForReading.readDataToEndOfFile() ?? Data()
      process.waitUntilExit()
      let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      return (text, process.terminationStatus)
    } catch {
      return ("\(error)", 1)
    }
  }

  private func updateStorePath() async {
    let storeDir = Self.defaultStoreDirectory()
    await MainActor.run { WhatsAppState.shared.update(storePath: storeDir) }
  }

  private func setState(_ state: WAConnectionState) async {
    await MainActor.run { WhatsAppState.shared.update(connectionState: state) }
  }

  private func handleConnectedSyncSideEffects() async {
    await MainActor.run {
      WhatsAppContactResolver.shared.scheduleRefresh()
      WhatsAppToneProfile.shared.scheduleAutomaticRebuild()
      WhatsAppMemoryImportService.shared.scheduleSyncIfEnabled()
    }
  }

  private func currentState() async -> WAConnectionState {
    await MainActor.run { WhatsAppState.shared.connectionState }
  }

  private func parseEvent(_ line: String) -> [String: Any]? {
    guard let data = line.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else {
      return nil
    }
    return object
  }

  private func handleTerminalQRLine(_ line: String) async -> Bool {
    let cleanLine = stripANSI(line)
    if cleanLine.contains("Scan this QR code") {
      isCapturingTerminalQR = true
      terminalQRLines = []
      await MainActor.run { WhatsAppState.shared.update(lastEventSummary: "Waiting for scan") }
      return true
    }

    guard isCapturingTerminalQR else {
      return false
    }

    if isTerminalQRLine(cleanLine) {
      terminalQRLines.append(cleanLine)
      await setState(.pairingTerminal(qrText: terminalQRLines.joined(separator: "\n")))
      return true
    }

    return false
  }

  private func isTerminalQRLine(_ line: String) -> Bool {
    line.contains("█") || line.contains("▀") || line.contains("▄")
  }

  private func stripANSI(_ value: String) -> String {
    value.replacingOccurrences(
      of: #"\u{001B}\[[0-9;]*[A-Za-z]"#,
      with: "",
      options: .regularExpression
    )
  }

  private func extractError(from event: [String: Any]) -> String? {
    if let success = event["success"] as? Bool, success {
      return nil
    }
    if let error = event["error"] as? String, !error.isEmpty {
      return error
    }
    if let data = event["data"] as? [String: Any],
      let error = data["error"] as? String,
      !error.isEmpty
    {
      return error
    }
    if let data = event["data"] as? [String: Any],
      let message = data["message"] as? String,
      !message.isEmpty
    {
      return message
    }
    return nil
  }

  private func isStoreLockError(_ error: String) -> Bool {
    let normalized = error.lowercased()
    return normalized.contains("store is locked") || normalized.contains("store locked")
  }

  private func warningSummary(from event: [String: Any]) -> String? {
    if let data = event["data"] as? [String: Any] {
      return nonEmptyString(data["message"])
        ?? nonEmptyString(data["code"])
    }
    return nonEmptyString(event["message"])
      ?? nonEmptyString(event["code"])
  }

  private func nonEmptyString(_ value: Any?) -> String? {
    guard let string = value as? String else { return nil }
    let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  private func parseAuthenticated(_ event: [String: Any]) -> Bool {
    if let authenticated = boolValue(event["authenticated"]) {
      return authenticated
    }
    if let data = event["data"] as? [String: Any],
      let authenticated = boolValue(data["authenticated"])
    {
      return authenticated
    }
    return false
  }

  private func parseDoctorConnected(_ output: String) -> Bool {
    guard let event = parseEvent(output),
      let data = event["data"] as? [String: Any]
    else {
      return false
    }
    return boolValue(data["connected"]) ?? false
  }

  private func parseDoctorAuthenticated(_ output: String) -> Bool {
    guard let event = parseEvent(output),
      let data = event["data"] as? [String: Any]
    else {
      return false
    }
    return boolValue(data["authenticated"]) ?? boolValue(event["authenticated"]) ?? false
  }

  private func normalizedEventName(_ event: [String: Any]) -> String {
    for key in ["event", "type", "status", "name"] {
      if let value = event[key] as? String, !value.isEmpty {
        return value.lowercased()
      }
    }
    return ""
  }

  private func isWarningEvent(_ eventName: String) -> Bool {
    eventName == "warning" || eventName.contains("warning")
  }

  private func extractQR(from event: [String: Any]) -> String? {
    for key in ["qr", "code", "pairingCode", "pairing_code", "payload"] {
      if let value = event[key] as? String, looksLikeQRCode(value) {
        return value
      }
    }

    if let data = event["data"] as? [String: Any] {
      for key in ["qr", "code", "pairingCode", "pairing_code", "payload"] {
        if let value = data[key] as? String, looksLikeQRCode(value) {
          return value
        }
      }
    }

    return nil
  }

  private func looksLikeQRCode(_ value: String) -> Bool {
    value.count > 20 || value.lowercased().contains("wa")
  }

  private func looksLikeRawQRPayload(_ value: String) -> Bool {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count > 80 else { return false }
    guard !trimmed.hasPrefix("{"), !trimmed.contains(" "), !trimmed.contains("█") else { return false }
    return trimmed.contains(",") || trimmed.contains("@") || trimmed.contains("=")
  }

  private func isConnectedEvent(_ eventName: String, event: [String: Any]) -> Bool {
    if parseAuthenticated(event) {
      return true
    }
    if let data = event["data"] as? [String: Any], boolValue(data["connected"]) == true {
      return true
    }
    let haystack = "\(eventName) \(event)".lowercased()
    return eventName == "connected"
      || haystack.contains("login.success")
      || haystack.contains("logged_in")
  }

  private func isNeedsReauthEvent(_ eventName: String, event: [String: Any]) -> Bool {
    let haystack = "\(eventName) \(event)".lowercased()
    return haystack.contains("needs_reauth")
      || haystack.contains("reauth")
      || haystack.contains("logged_out")
      || haystack.contains("logout")
      || haystack.contains("not authenticated")
  }

  private func isTransientSyncEvent(_ eventName: String) -> Bool {
    eventName == "disconnected" || eventName == "reconnecting"
  }

  private func boolValue(_ value: Any?) -> Bool? {
    if let value = value as? Bool {
      return value
    }
    if let value = value as? NSNumber {
      return value.boolValue
    }
    if let value = value as? String {
      switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
      case "true", "1", "yes", "authenticated", "connected":
        return true
      case "false", "0", "no", "unauthenticated", "not authenticated", "disconnected":
        return false
      default:
        return nil
      }
    }
    return nil
  }

  private func summarizeMessageEvent(_ event: [String: Any]) -> String {
    let message = (event["message"] as? [String: Any]) ?? (event["data"] as? [String: Any]) ?? event
    let chat = (message["chatJid"] ?? message["chat"] ?? message["from"] ?? message["sender"]) as? String
    let text = (message["text"] ?? message["body"] ?? message["message"]) as? String
    if let chat, let text, !text.isEmpty {
      return "New message from \(chat): \(text.prefix(80))"
    }
    if let chat {
      return "New message from \(chat)"
    }
    return "New WhatsApp message received"
  }
}
