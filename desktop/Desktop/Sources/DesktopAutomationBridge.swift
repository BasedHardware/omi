import AppKit
import Foundation
import Network

enum DesktopAutomationLaunchOptions {
  static let enableFlag = "--automation-bridge"
  static let portPrefix = "--automation-port="
  static let defaultPort: UInt16 = 47777

  static var isEnabled: Bool {
    CommandLine.arguments.contains(enableFlag)
      || ProcessInfo.processInfo.environment["OMI_ENABLE_LOCAL_AUTOMATION"] == "1"
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
    await MainActor.run {
      NotificationCenter.default.post(
        name: .desktopAutomationNavigateRequested,
        object: nil,
        userInfo: [
          "target": payload.target,
          "settingsSection": payload.settingsSection as Any,
          "highlightedSettingId": payload.highlightedSettingId as Any,
          "activateApp": payload.activateApp ?? true,
        ]
      )
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
