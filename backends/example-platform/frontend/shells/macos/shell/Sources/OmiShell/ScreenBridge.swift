import Foundation
import WebKit

struct ScreenBridgeCommand: Decodable {
  var id: String
  var action: String
  var params: ScreenBridgeParams?
}

struct ScreenBridgeParams: Decodable {
  var frameRef: String?
  var maxLongEdge: Int?
  var bundleIds: [String]?
  var days: Int?

  enum CodingKeys: String, CodingKey {
    case frameRef, maxLongEdge, bundleIds, days
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    if let direct = try container.decodeIfPresent(String.self, forKey: .frameRef) {
      frameRef = direct
    } else if let object = try container.decodeIfPresent(ScreenBridgeFrameRef.self, forKey: .frameRef)
    {
      frameRef = object.ref ?? object.path
    } else {
      frameRef = nil
    }
    maxLongEdge = try container.decodeIfPresent(Int.self, forKey: .maxLongEdge)
    bundleIds = try container.decodeIfPresent([String].self, forKey: .bundleIds)
    days = try container.decodeIfPresent(Int.self, forKey: .days)
  }
}

private struct ScreenBridgeFrameRef: Decodable {
  var ref: String?
  var path: String?
}

/// Dedicated page-side transport for Rewind capture. The production surface posts
/// `{id, action, params}` strings to `omiScreenBridge` and listens on
/// `__omiScreenBridgeEvent` / `__omiScreenStatusEvent`. The generic
/// `OmiShellBridge` dispatcher keeps the same verbs for the generated macos
/// surface; this handler is the channel that production actually looks up.
final class ScreenBridgeHandler: NSObject, WKScriptMessageHandler, @unchecked Sendable {
  static let channel = "omiScreenBridge"
  static let resultCallback = "__omiScreenBridgeEvent"
  static let statusCallback = "__omiScreenStatusEvent"

  private let handler: BridgeHandling
  private let promptForPermissionOnStart: Bool

  init(handler: BridgeHandling, promptForPermissionOnStart: Bool = true) {
    self.handler = handler
    self.promptForPermissionOnStart = promptForPermissionOnStart
    super.init()
  }

  static func emitStatus(_ event: ScreenStatusEvent) -> String {
    guard let body = encodeJSON(event) else { return "" }
    return "window.\(statusCallback)?.(\(body));"
  }

  func userContentController(
    _ userContentController: WKUserContentController,
    didReceive message: WKScriptMessage
  ) {
    guard let webView = message.webView else {
      logScreen("screen-bridge: dropped (no webView)")
      return
    }
    guard let data = jsonData(from: message.body) else {
      logScreen("screen-bridge: dropped bodyType=\(type(of: message.body))")
      return
    }
    guard let command = try? JSONDecoder().decode(ScreenBridgeCommand.self, from: data) else {
      let preview = String(data: data, encoding: .utf8).map { String($0.prefix(180)) } ?? "<binary>"
      logScreen("screen-bridge: dropped (unreadable envelope) body=\(preview)")
      return
    }
    logScreen("screen-bridge: action=\(command.action) id=\(command.id)")
    Task { @MainActor in
      let json = await self.dispatch(command)
      self.emit(id: command.id, json: json, webView: webView)
    }
  }

  private func dispatch(_ command: ScreenBridgeCommand) async -> String {
    let params = command.params
    do {
      switch command.action {
      case "screen.status":
        return try encodeJSON(await handler.screenStatus(ScreenEmptyParams())) ?? errorJSON("encode")
      case "screen.start":
        if promptForPermissionOnStart {
          let status = try await handler.screenStatus(ScreenEmptyParams())
          if status.permission != .granted {
            _ = try await handler.screenRequestPermission(ScreenEmptyParams())
          }
        }
        return try encodeJSON(await handler.screenStart(ScreenEmptyParams())) ?? errorJSON("encode")
      case "screen.stop":
        return try encodeJSON(await handler.screenStop(ScreenEmptyParams())) ?? errorJSON("encode")
      case "screen.frameImage":
        guard let frameRef = params?.frameRef else { return errorJSON("missing frameRef") }
        return try encodeJSON(
          await handler.screenFrameImage(
            ScreenFrameImageParams(frameRef: frameRef, maxLongEdge: params?.maxLongEdge))
        ) ?? errorJSON("encode")
      case "screen.exclusionsList":
        return try encodeJSON(await handler.screenExclusionsList(ScreenEmptyParams()))
          ?? errorJSON("encode")
      case "screen.exclusionsSet":
        return try encodeJSON(
          await handler.screenExclusionsSet(
            ScreenExclusionsSetParams(bundleIds: params?.bundleIds ?? []))
        ) ?? errorJSON("encode")
      case "screen.retentionSet":
        return try encodeJSON(
          await handler.screenRetentionSet(ScreenRetentionSetParams(days: params?.days ?? 0))
        ) ?? errorJSON("encode")
      case "screen.rebuildIndex":
        return try encodeJSON(await handler.screenRebuildIndex(ScreenEmptyParams()))
          ?? errorJSON("encode")
      case "screen.requestPermission":
        let result = try await handler.screenRequestPermission(ScreenEmptyParams())
        logScreen("screen-tcc: requestPermission permission=\(result.permission.rawValue)")
        return encodeJSON(result) ?? errorJSON("encode")
      case "screen.openSettings":
        return try encodeJSON(await handler.screenOpenSettings(ScreenEmptyParams()))
          ?? errorJSON("encode")
      default:
        logScreen("screen-bridge: unknown action=\(command.action)")
        return errorJSON("unknown action")
      }
    } catch {
      logScreen("screen-bridge: action=\(command.action) error=\(error)")
      return errorJSON(String(describing: error))
    }
  }

  private func emit(id: String, json: String, webView: WKWebView) {
    guard let idJSON = Self.encodeJSON(id) else { return }
    webView.evaluateJavaScript(
      "window.\(Self.resultCallback)?.(\(idJSON), \(json))",
      completionHandler: nil)
  }

  private func jsonData(from body: Any) -> Data? {
    if let raw = body as? String { return raw.data(using: .utf8) }
    if let data = body as? Data { return data }
    if JSONSerialization.isValidJSONObject(body) {
      return try? JSONSerialization.data(withJSONObject: body)
    }
    return nil
  }

  private func errorJSON(_ message: String) -> String {
    guard
      let data = try? JSONSerialization.data(withJSONObject: ["error": message]),
      let text = String(data: data, encoding: .utf8)
    else { return "{\"error\":\"unreadable\"}" }
    return text
  }

  private func encodeJSON<T: Encodable>(_ value: T) -> String? {
    Self.encodeJSON(value)
  }

  fileprivate static func encodeJSON<T: Encodable>(_ value: T) -> String? {
    let encoder = JSONEncoder()
    guard let data = try? encoder.encode(value) else { return nil }
    return String(data: data, encoding: .utf8)
  }

  private func logScreen(_ line: String) {
    FileHandle.standardError.write(Data("\(line)\n".utf8))
  }
}
