import AppKit
import Foundation
import Network

enum DesktopAutomationLaunchOptions {
  static let enableFlag = "--automation-bridge"
  static let portPrefix = "--automation-port="
  static let defaultPort: UInt16 = 47777

  static var isEnabled: Bool {
    // Explicit opt-out always wins, so a dev build can be run "clean" if needed.
    if ProcessInfo.processInfo.environment["OMI_DISABLE_LOCAL_AUTOMATION"] == "1" {
      return false
    }
    // Auto-enable on any non-production bundle (Omi Dev + every `omi-*` named test
    // bundle) so agents can drive the app without remembering a launch flag. The
    // listener only binds to 127.0.0.1 and is never enabled on the production bundle.
    return CommandLine.arguments.contains(enableFlag)
      || ProcessInfo.processInfo.environment["OMI_ENABLE_LOCAL_AUTOMATION"] == "1"
      || AppBuild.isNonProduction
  }

  static var port: UInt16 {
    for argument in CommandLine.arguments {
      guard argument.hasPrefix(portPrefix) else { continue }
      let rawValue = String(argument.dropFirst(portPrefix.count))
      if let parsed = UInt16(rawValue) {
        return parsed
      }
    }

    if let rawValue = ProcessInfo.processInfo.environment["OMI_AUTOMATION_PORT"],
      let parsed = UInt16(rawValue)
    {
      return parsed
    }

    return defaultPort
  }
}

struct DesktopAutomationSnapshot: Codable {
  var bridgeEnabled: Bool
  var bridgePort: UInt16
  var bundleIdentifier: String
  var appState: String
  var selectedTab: String?
  var selectedTabIndex: Int?
  var selectedSettingsSection: String?
  var highlightedSettingId: String?
  var hasCompletedOnboarding: Bool
  var isSignedIn: Bool
  var isRestoringAuth: Bool
  var isAppActive: Bool
  var mainWindowTitle: String?
  var updatedAt: String
}

struct DesktopAutomationNavigationRequest: Codable {
  let target: String
  let settingsSection: String?
  let highlightedSettingId: String?
  let activateApp: Bool?
}

struct DesktopAutomationOpenConversationRequest: Codable {
  let conversationId: String
  let showTranscript: Bool?
  let activateApp: Bool?
}

struct DesktopAutomationExecuteExportRequest: Codable {
  let destination: String
}

/// Describes a semantic action exposed over `GET /actions` so an agent can discover
/// what it can drive without inspecting the UI tree.
struct DesktopAutomationActionDescriptor: Codable {
  let name: String
  let summary: String
  /// Names of params the handler reads (hints for the caller; not enforced).
  let params: [String]
}

/// Returned by `POST /action`: what ran, any handler detail, and the resulting state.
struct DesktopAutomationActionResult: Codable {
  let action: String
  let detail: [String: String]?
  let state: DesktopAutomationSnapshot
}

enum DesktopAutomationActionError: LocalizedError {
  case unknownAction(String)
  case invalidParams(String)

  var errorDescription: String? {
    switch self {
    case .unknownAction(let name): return "unknown_action: \(name)"
    case .invalidParams(let detail): return "invalid_params: \(detail)"
    }
  }
}

private struct DesktopAutomationResponse<T: Codable>: Codable {
  let ok: Bool
  let result: T?
  let error: String?
}

actor DesktopAutomationStateStore {
  static let shared = DesktopAutomationStateStore()

  private var snapshot = DesktopAutomationSnapshot(
    bridgeEnabled: DesktopAutomationLaunchOptions.isEnabled,
    bridgePort: DesktopAutomationLaunchOptions.port,
    bundleIdentifier: Bundle.main.bundleIdentifier ?? "unknown",
    appState: "launching",
    selectedTab: nil,
    selectedTabIndex: nil,
    selectedSettingsSection: nil,
    highlightedSettingId: nil,
    hasCompletedOnboarding: false,
    isSignedIn: false,
    isRestoringAuth: true,
    isAppActive: false,
    mainWindowTitle: nil,
    updatedAt: ISO8601DateFormatter().string(from: Date())
  )

  func update(_ snapshot: DesktopAutomationSnapshot) {
    self.snapshot = snapshot
  }

  func current() -> DesktopAutomationSnapshot {
    snapshot
  }
}

/// In-process registry of semantic, cursor-free actions the automation bridge can
/// run. Handlers invoke the app's real code (notifications, services) directly, so
/// no synthetic mouse events are ever generated — this is the deterministic
/// "command channel" equivalent of the Flutter app's Marionette driver.
///
/// Built-ins are registered at bridge startup. Feature code can register more via
/// `register(name:summary:params:handler:)` (e.g. from a view model's lifecycle) and
/// remove them with `unregister(_:)`.
@MainActor
final class DesktopAutomationActionRegistry {
  static let shared = DesktopAutomationActionRegistry()

  /// Handler runs on the main actor and returns optional string detail for the caller.
  typealias Handler = (_ params: [String: String]) async throws -> [String: String]?

  private struct Entry {
    let descriptor: DesktopAutomationActionDescriptor
    let run: Handler
  }

  private var entries: [String: Entry] = [:]
  private var didRegisterBuiltins = false

  func register(
    name: String, summary: String, params: [String] = [], handler: @escaping Handler
  ) {
    entries[name] = Entry(
      descriptor: DesktopAutomationActionDescriptor(name: name, summary: summary, params: params),
      run: handler)
  }

  func unregister(_ name: String) {
    entries[name] = nil
  }

  func descriptors() -> [DesktopAutomationActionDescriptor] {
    entries.values.map(\.descriptor).sorted { $0.name < $1.name }
  }

  func perform(_ name: String, params: [String: String]) async throws -> [String: String]? {
    guard let entry = entries[name] else {
      throw DesktopAutomationActionError.unknownAction(name)
    }
    return try await entry.run(params)
  }

  /// Register the always-available actions that don't need any view's `@State` —
  /// they post the same notifications / hit the same services as the real controls,
  /// so they exercise the genuine code paths. Idempotent.
  func registerBuiltins() {
    guard !didRegisterBuiltins else { return }
    didRegisterBuiltins = true

    register(
      name: "refresh_all_data",
      summary: "Refresh conversations, chat, tasks, and memories (same as Cmd+R)"
    ) { _ in
      NotificationCenter.default.post(name: .refreshAllData, object: nil)
      return nil
    }

    register(
      name: "toggle_transcription",
      summary: "Enable or disable live transcription (mirrors the menu-bar toggle)",
      params: ["enabled"]
    ) { params in
      let enabled = boolParam(params["enabled"], default: true)
      AssistantSettings.shared.transcriptionEnabled = enabled
      NotificationCenter.default.post(
        name: .toggleTranscriptionRequested, object: nil, userInfo: ["enabled": enabled])
      return ["enabled": enabled ? "true" : "false"]
    }
  }
}

/// Coerce a string param ("true"/"1"/"yes") into a Bool, falling back when absent.
private func boolParam(_ raw: String?, default fallback: Bool) -> Bool {
  guard let raw = raw?.trimmingCharacters(in: .whitespaces).lowercased(), !raw.isEmpty else {
    return fallback
  }
  return ["1", "true", "yes", "on"].contains(raw)
}

final class DesktopAutomationBridge {
  static let shared = DesktopAutomationBridge()

  private let queue = DispatchQueue(label: "com.omi.desktop.automation-bridge")
  private var listener: NWListener?

  private init() {}

  func startIfNeeded() {
    guard DesktopAutomationLaunchOptions.isEnabled else { return }
    guard listener == nil else { return }

    do {
      let parameters = NWParameters.tcp
      parameters.allowLocalEndpointReuse = true
      guard let port = NWEndpoint.Port(rawValue: DesktopAutomationLaunchOptions.port) else {
        log("DesktopAutomationBridge: invalid port \(DesktopAutomationLaunchOptions.port)")
        return
      }
      let listener = try NWListener(using: parameters, on: port)
      listener.newConnectionHandler = { [weak self] connection in
        self?.handleConnection(connection)
      }
      listener.stateUpdateHandler = { (state: NWListener.State) in
        log("DesktopAutomationBridge: listener state changed to \(String(describing: state))")
      }
      listener.start(queue: queue)
      self.listener = listener
      Task { @MainActor in DesktopAutomationActionRegistry.shared.registerBuiltins() }
      log(
        "DesktopAutomationBridge: listening on http://127.0.0.1:\(DesktopAutomationLaunchOptions.port)"
      )
    } catch {
      logError("DesktopAutomationBridge: failed to start listener", error: error)
    }
  }

  private func handleConnection(_ connection: NWConnection) {
    connection.start(queue: queue)
    receiveRequest(on: connection, buffer: Data())
  }

  private func receiveRequest(on connection: NWConnection, buffer: Data) {
    connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) {
      [weak self] data, _, isComplete, error in
      guard let self else { return }

      if let error {
        self.sendError(
          "receive_failed: \(error.localizedDescription)", statusCode: 500, on: connection)
        return
      }

      var accumulated = buffer
      if let data {
        accumulated.append(data)
      }

      if let request = self.parseRequest(from: accumulated) {
        Task {
          let response = await self.route(request: request)
          self.send(response, on: connection)
        }
        return
      }

      if isComplete {
        self.sendError("incomplete_request", statusCode: 400, on: connection)
        return
      }

      self.receiveRequest(on: connection, buffer: accumulated)
    }
  }

  private func parseRequest(from data: Data) -> HTTPRequest? {
    guard let headerRange = data.range(of: Data("\r\n\r\n".utf8)) else {
      return nil
    }

    let headerData = data[..<headerRange.lowerBound]
    guard let headerString = String(data: headerData, encoding: .utf8) else {
      return nil
    }

    let lines = headerString.components(separatedBy: "\r\n")
    guard let requestLine = lines.first else { return nil }
    let requestParts = requestLine.split(separator: " ")
    guard requestParts.count >= 2 else { return nil }

    let method = String(requestParts[0])
    let path = String(requestParts[1])

    var contentLength = 0
    for line in lines.dropFirst() {
      let pieces = line.split(separator: ":", maxSplits: 1)
      guard pieces.count == 2 else { continue }
      if pieces[0].lowercased() == "content-length" {
        contentLength = Int(pieces[1].trimmingCharacters(in: .whitespaces)) ?? 0
      }
    }

    let bodyStart = headerRange.upperBound
    let expectedLength = data.distance(from: data.startIndex, to: bodyStart) + contentLength
    guard data.count >= expectedLength else {
      return nil
    }

    let body = Data(data[bodyStart..<data.index(bodyStart, offsetBy: contentLength)])
    return HTTPRequest(method: method, path: path, body: body)
  }

  /// Parse a `POST /action` body: `{ "name": "...", "params": { "k": "v", ... } }`.
  /// Param values are coerced to strings (bools → "true"/"false", numbers → digits)
  /// so callers can send natural JSON types.
  private func parseActionRequest(from body: Data) -> (name: String, params: [String: String])? {
    guard let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
      let name = object["name"] as? String, !name.isEmpty
    else {
      return nil
    }

    var params: [String: String] = [:]
    if let raw = object["params"] as? [String: Any] {
      for (key, value) in raw {
        if let string = value as? String {
          params[key] = string
        } else if let number = value as? NSNumber {
          if CFGetTypeID(number) == CFBooleanGetTypeID() {
            params[key] = number.boolValue ? "true" : "false"
          } else {
            params[key] = number.stringValue
          }
        } else {
          params[key] = String(describing: value)
        }
      }
    }
    return (name, params)
  }

  private func route(request: HTTPRequest) async -> HTTPResponse {
    switch (request.method, request.path) {
    case ("GET", "/health"):
      let snapshot = await DesktopAutomationStateStore.shared.current()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
    case ("GET", "/state"):
      let snapshot = await DesktopAutomationStateStore.shared.current()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
    case ("POST", "/navigate"):
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationNavigationRequest.self, from: request.body)
        try await dispatchNavigation(payload)
        try await Task.sleep(for: .milliseconds(150))
        let snapshot = await DesktopAutomationStateStore.shared.current()
        return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationSnapshot>(
            ok: false,
            result: nil,
            error: error.localizedDescription
          ),
          statusCode: 400
        )
      }
    case ("POST", "/conversation/open"):
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationOpenConversationRequest.self, from: request.body)
        try await dispatchOpenConversation(payload)
        try await Task.sleep(for: .milliseconds(350))
        let snapshot = await DesktopAutomationStateStore.shared.current()
        return jsonResponse(DesktopAutomationResponse(ok: true, result: snapshot, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationSnapshot>(
            ok: false,
            result: nil,
            error: error.localizedDescription
          ),
          statusCode: 400
        )
      }
    case ("POST", "/execute-export"):
      struct ExecResult: Codable { let taskTitle: String }
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationExecuteExportRequest.self, from: request.body)
        guard let destination = MemoryExportDestination(rawValue: payload.destination) else {
          return jsonResponse(
            DesktopAutomationResponse<ExecResult>(
              ok: false, result: nil, error: "unknown destination: \(payload.destination)"),
            statusCode: 400)
        }
        let outcome = try await MemoryExportExecutor.run(destination)
        return jsonResponse(
          DesktopAutomationResponse(
            ok: true, result: ExecResult(taskTitle: outcome.taskTitle), error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<ExecResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 500)
      }
    case ("GET", "/actions"):
      let descriptors = await DesktopAutomationActionRegistry.shared.descriptors()
      return jsonResponse(DesktopAutomationResponse(ok: true, result: descriptors, error: nil))
    case ("POST", "/action"):
      guard let parsed = parseActionRequest(from: request.body) else {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationActionResult>(
            ok: false, result: nil, error: "invalid_action_request"),
          statusCode: 400
        )
      }
      do {
        let detail = try await DesktopAutomationActionRegistry.shared.perform(
          parsed.name, params: parsed.params)
        try await Task.sleep(for: .milliseconds(150))
        let snapshot = await DesktopAutomationStateStore.shared.current()
        let result = DesktopAutomationActionResult(
          action: parsed.name, detail: detail, state: snapshot)
        return jsonResponse(DesktopAutomationResponse(ok: true, result: result, error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<DesktopAutomationActionResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 400
        )
      }
    case ("POST", "/open-export"):
      struct OpenResult: Codable { let destination: String }
      do {
        let payload = try JSONDecoder().decode(
          DesktopAutomationExecuteExportRequest.self, from: request.body)
        guard MemoryExportDestination(rawValue: payload.destination) != nil else {
          return jsonResponse(
            DesktopAutomationResponse<OpenResult>(
              ok: false, result: nil, error: "unknown destination: \(payload.destination)"),
            statusCode: 400)
        }
        await MainActor.run {
          NSApp.activate()
          if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
            window.makeKeyAndOrderFront(nil)
          }
          NotificationCenter.default.post(
            name: .desktopAutomationOpenExportRequested, object: nil,
            userInfo: ["destination": payload.destination])
        }
        try await Task.sleep(for: .milliseconds(300))
        return jsonResponse(
          DesktopAutomationResponse(
            ok: true, result: OpenResult(destination: payload.destination), error: nil))
      } catch {
        return jsonResponse(
          DesktopAutomationResponse<OpenResult>(
            ok: false, result: nil, error: error.localizedDescription),
          statusCode: 500)
      }
    case ("POST", "/gmail-read"):
      do {
        let emails = try await GmailReaderService.shared.readRecentEmails(maxResults: 50)
        let result = await GmailReaderService.shared.saveAsMemories(emails: emails)
        struct GmailReadResult: Codable {
          let emailCount: Int
          let memoriesSaved: Int
          let memoriesFailed: Int
          let emails: [GmailEmailSummary]
        }
        struct GmailEmailSummary: Codable {
          let from: String
          let subject: String
          let snippet: String
          let date: String
          let isUnread: Bool
        }
        let formatter = ISO8601DateFormatter()
        let summaries = emails.prefix(50).map { e in
          GmailEmailSummary(
            from: e.from, subject: e.subject, snippet: e.snippet,
            date: formatter.string(from: e.date), isUnread: e.isUnread)
        }
        let gmailResult = GmailReadResult(
          emailCount: emails.count,
          memoriesSaved: result.saved,
          memoriesFailed: result.failed,
          emails: summaries
        )
        return jsonResponse(DesktopAutomationResponse(ok: true, result: gmailResult, error: nil))
      } catch {
        struct ErrorResult: Codable { let message: String }
        return jsonResponse(
          DesktopAutomationResponse(ok: false, result: ErrorResult(message: error.localizedDescription), error: error.localizedDescription),
          statusCode: 500
        )
      }
    default:
      return jsonResponse(
        DesktopAutomationResponse<DesktopAutomationSnapshot>(
          ok: false,
          result: nil,
          error: "unsupported_route"
        ),
        statusCode: 404
      )
    }
  }

  private func dispatchNavigation(_ payload: DesktopAutomationNavigationRequest) async throws {
    await activateMainWindowIfNeeded(payload.activateApp ?? true)
    await MainActor.run {
      NotificationCenter.default.post(
        name: .desktopAutomationNavigateRequested,
        object: nil,
        userInfo: [
          "target": payload.target,
          "settingsSection": payload.settingsSection as Any,
          "highlightedSettingId": payload.highlightedSettingId as Any,
        ]
      )
    }
  }

  private func dispatchOpenConversation(_ payload: DesktopAutomationOpenConversationRequest) async throws {
    await activateMainWindowIfNeeded(payload.activateApp ?? true)
    await MainActor.run {
      NotificationCenter.default.post(
        name: .desktopAutomationOpenConversationRequested,
        object: nil,
        userInfo: [
          "conversationId": payload.conversationId,
          "showTranscript": payload.showTranscript ?? false,
        ]
      )
    }
  }

  private func activateMainWindowIfNeeded(_ activateApp: Bool) async {
    guard activateApp else { return }
    await MainActor.run {
      NSApp.activate()
      if let window = NSApp.windows.first(where: { $0.title.lowercased().hasPrefix("omi") }) {
        window.makeKeyAndOrderFront(nil)
      }
    }
  }

  private func jsonResponse<T: Codable>(_ payload: T, statusCode: Int = 200) -> HTTPResponse {
    do {
      let body = try JSONEncoder.pretty.encode(payload)
      return HTTPResponse(
        statusCode: statusCode,
        headers: ["Content-Type": "application/json"],
        body: body
      )
    } catch {
      let fallback = Data("{\"ok\":false,\"error\":\"encode_failed\"}".utf8)
      return HTTPResponse(
        statusCode: 500,
        headers: ["Content-Type": "application/json"],
        body: fallback
      )
    }
  }

  private func sendError(_ message: String, statusCode: Int, on connection: NWConnection) {
    let response = jsonResponse(
      DesktopAutomationResponse<DesktopAutomationSnapshot>(ok: false, result: nil, error: message),
      statusCode: statusCode
    )
    send(response, on: connection)
  }

  private func send(_ response: HTTPResponse, on connection: NWConnection) {
    let statusText: String
    switch response.statusCode {
    case 200: statusText = "OK"
    case 400: statusText = "Bad Request"
    case 404: statusText = "Not Found"
    default: statusText = "Internal Server Error"
    }

    var headerLines = [
      "HTTP/1.1 \(response.statusCode) \(statusText)",
      "Content-Length: \(response.body.count)",
      "Connection: close",
    ]
    for (key, value) in response.headers {
      headerLines.append("\(key): \(value)")
    }
    headerLines.append("")
    headerLines.append("")

    var data = Data(headerLines.joined(separator: "\r\n").utf8)
    data.append(response.body)

    connection.send(
      content: data,
      completion: .contentProcessed { _ in
        connection.cancel()
      })
  }
}

private struct HTTPRequest {
  let method: String
  let path: String
  let body: Data
}

private struct HTTPResponse {
  let statusCode: Int
  let headers: [String: String]
  let body: Data
}

extension JSONEncoder {
  fileprivate static var pretty: JSONEncoder {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    return encoder
  }
}
