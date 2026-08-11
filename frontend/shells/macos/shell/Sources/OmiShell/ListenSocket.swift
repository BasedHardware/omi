import Foundation
import AppKit
import AVFoundation
import WebKit

func deterministicListenEvidenceAudio() -> Data {
  var bytes = Data(count: 3_200)
  bytes.withUnsafeMutableBytes { raw in
    guard let output = raw.bindMemory(to: UInt8.self).baseAddress else { return }
    for sample in 0..<1_600 {
      let value = Int16(((sample * 257) % 24_001) - 12_000)
      let bits = UInt16(bitPattern: value)
      output[sample * 2] = UInt8(bits & 0xff)
      output[sample * 2 + 1] = UInt8((bits >> 8) & 0xff)
    }
  }
  return bytes
}

func isListenProtocolReady(_ text: String) -> Bool {
  guard let data = text.data(using: .utf8),
    let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
  else { return false }
  return value["type"] as? String == "service_status"
    && value["status"] as? String == "ready"
}

struct ListenSocketPreparedRequest {
  let id: String
  let request: URLRequest
}

enum ListenPreflightPolicy {
  static func canOpen(permission: AVAuthorizationStatus, inputAvailable: Bool) -> Bool {
    permission == .authorized && inputAvailable
  }

  static func payload(
    permission: AVAuthorizationStatus, inputAvailable: Bool
  ) -> [String: Any] {
    let permissionState: String
    let recovery: String?
    switch permission {
    case .notDetermined:
      permissionState = "unknown"
      recovery = "request-permission"
    case .authorized:
      permissionState = "granted"
      recovery = nil
    case .denied:
      permissionState = "denied"
      recovery = "open-settings"
    case .restricted:
      permissionState = "restricted"
      recovery = nil
    @unknown default:
      permissionState = "unavailable"
      recovery = nil
    }
    let deviceState: String
    if permissionState == "granted" {
      deviceState = inputAvailable ? "available" : "unavailable"
    } else if permissionState == "unknown" {
      deviceState = "unknown"
    } else {
      deviceState = "unavailable"
    }
    return [
      "permission": permissionState,
      "deviceState": deviceState,
      "deviceLabel": permissionState == "granted" && inputAvailable ? "Default microphone" : NSNull(),
      "recovery": recovery ?? NSNull(),
    ]
  }
}

enum ListenSocketPolicyDecision {
  case dispatch(ListenSocketPreparedRequest)
  case failure(String)
}

/// One shell-owned authority composes both privileged transports.
struct ShellTransportAuthority {
  let baseURL: URL
  let custody: ShellCredentialCustody

  init(
    baseURL: URL,
    token: String?,
    onSuccessfulSignOut: @escaping () -> Void = {}
  ) {
    self.baseURL = baseURL
    self.custody = ShellCredentialCustody(
      token: token, onSuccessfulSignOut: onSuccessfulSignOut)
  }

  @MainActor
  func makeHTTPHandler(clientId: String?) -> BridgeHttpHandler {
    BridgeHttpHandler(baseURL: baseURL, custody: custody, clientId: clientId)
  }

  func makeListenHandler(
    clientId: String? = nil, evidenceAudioEnabled: Bool = false
  ) -> ListenSocketHandler {
    ListenSocketHandler(
      baseURL: baseURL, custody: custody, clientId: clientId,
      evidenceAudioEnabled: evidenceAudioEnabled)
  }

  func prepareListen(id: String, path: String, clientId: String? = nil) -> ListenSocketPolicyDecision {
    ListenSocketPolicy.prepare(
      id: id, path: path, baseURL: baseURL, token: custody.currentToken(), clientId: clientId)
  }
}

/// Pure authority/auth policy shared by the live handler and composition test.
enum ListenSocketPolicy {
  static func prepare(
    id: String, path: String, baseURL: URL, token: String?, clientId: String? = nil
  )
    -> ListenSocketPolicyDecision
  {
    guard path.hasPrefix("/"), !path.hasPrefix("//"), !path.contains("://") else {
      return .failure("path is not origin-relative")
    }
    guard let token, !token.isEmpty else {
      return .failure("shell holds no credential")
    }
    guard
      var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false),
      components.scheme == "http" || components.scheme == "https"
    else {
      return .failure("API base must use http(s)")
    }
    components.scheme = components.scheme == "https" ? "wss" : "ws"
    components.path = ""
    components.query = nil
    components.fragment = nil
    guard let socketBase = components.url,
      let socketURL = URL(string: path, relativeTo: socketBase)?.absoluteURL,
      socketURL.host == socketBase.host,
      socketURL.port == socketBase.port
    else {
      return .failure("could not resolve Listen socket URL")
    }
    var request = URLRequest(url: socketURL)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    if let identity = BridgeHttpPolicy.shellClientId(runId: clientId) {
      request.setValue(identity, forHTTPHeaderField: "x-omi-client-id")
    }
    return .dispatch(ListenSocketPreparedRequest(id: id, request: request))
  }
}

private struct ListenSocketCommand: Decodable {
  let id: String
  let action: String
  let path: String?
  let code: Int?
  let reason: String?
  let operation: String?
}

/// Native WebSocket owner. Base authority and bearer credential never cross to JS.
final class ListenSocketHandler: NSObject, WKScriptMessageHandler, URLSessionWebSocketDelegate,
  @unchecked Sendable
{
  static let channel = "omiListenSocket"

  private let baseURL: URL
  private let custody: ShellCredentialCustody
  private let clientId: String?
  private let evidenceAudioEnabled: Bool
  private var tasksById: [String: URLSessionWebSocketTask] = [:]
  private var idsByTask: [Int: String] = [:]
  private var webViewsById: [String: WKWebView] = [:]
  private var evidenceAudioSent = Set<String>()

  private func listenPreflightPayload() -> [String: Any] {
    let hasInput = AVCaptureDevice.default(for: .audio) != nil
    return ListenPreflightPolicy.payload(
      permission: AVCaptureDevice.authorizationStatus(for: .audio), inputAvailable: hasInput)
  }

  private func listenPreflightCanOpen() -> Bool {
    ListenPreflightPolicy.canOpen(
      permission: AVCaptureDevice.authorizationStatus(for: .audio),
      inputAvailable: AVCaptureDevice.default(for: .audio) != nil)
  }
  private lazy var session: URLSession = {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.httpCookieStorage = nil
    configuration.httpShouldSetCookies = false
    return URLSession(configuration: configuration, delegate: self, delegateQueue: .main)
  }()

  init(
    baseURL: URL, custody: ShellCredentialCustody, clientId: String? = nil,
    evidenceAudioEnabled: Bool = false
  ) {
    self.baseURL = baseURL
    self.custody = custody
    self.clientId = clientId
    self.evidenceAudioEnabled = evidenceAudioEnabled
    super.init()
  }

  func prepareUsingCurrentCustodyForConformance(
    id: String, path: String
  ) -> ListenSocketPolicyDecision {
    ListenSocketPolicy.prepare(
      id: id, path: path, baseURL: baseURL, token: custody.currentToken(), clientId: clientId)
  }

  func cancelAll() {
    let tasks = Array(tasksById.values)
    tasksById.removeAll()
    idsByTask.removeAll()
    webViewsById.removeAll()
    evidenceAudioSent.removeAll()
    for task in tasks {
      task.cancel(with: .goingAway, reason: nil)
    }
  }

  func userContentController(
    _ userContentController: WKUserContentController,
    didReceive message: WKScriptMessage
  ) {
    guard let webView = message.webView,
      let raw = message.body as? String,
      let data = raw.data(using: .utf8),
      let command = try? JSONDecoder().decode(ListenSocketCommand.self, from: data)
    else { return }

    if command.action == "preflight" {
      let operation = command.operation ?? "check"
      switch operation {
      case "request-permission":
        AVCaptureDevice.requestAccess(for: .audio) { [weak self, weak webView] _ in
          DispatchQueue.main.async {
            guard let self, let webView else { return }
            self.emitPreflight(id: command.id, webView: webView)
          }
        }
      case "open-settings":
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!
        _ = NSWorkspace.shared.open(url)
        emitPreflight(id: command.id, webView: webView)
      case "check":
        emitPreflight(id: command.id, webView: webView)
      default:
        return
      }
      return
    }

    if command.action == "close" {
      let closeCode = URLSessionWebSocketTask.CloseCode(rawValue: command.code ?? 1000)
        ?? .normalClosure
      let reason = command.reason?.data(using: .utf8)
      tasksById[command.id]?.cancel(with: closeCode, reason: reason)
      return
    }
    guard command.action == "open", let path = command.path else { return }
    guard listenPreflightCanOpen() else {
      emit(id: command.id, payload: ["type": "error"], webView: webView)
      emit(id: command.id, payload: ["type": "close", "code": 1008], webView: webView)
      return
    }
    switch prepareUsingCurrentCustodyForConformance(id: command.id, path: path) {
    case .failure:
      emit(id: command.id, payload: ["type": "error"], webView: webView)
      emit(id: command.id, payload: ["type": "close", "code": 1008], webView: webView)
    case .dispatch(let prepared):
      let task = session.webSocketTask(with: prepared.request)
      tasksById[command.id] = task
      idsByTask[task.taskIdentifier] = command.id
      webViewsById[command.id] = webView
      task.resume()
    }
  }

  private func emitPreflight(id: String, webView: WKWebView) {
    var payload = listenPreflightPayload()
    payload["type"] = "preflight"
    payload["requestId"] = id
    emit(id: id, payload: payload, webView: webView, callback: "__omiListenPreflightEvent")
  }

  func urlSession(
    _ session: URLSession,
    webSocketTask: URLSessionWebSocketTask,
    didOpenWithProtocol protocol: String?
  ) {
    guard let id = idsByTask[webSocketTask.taskIdentifier], let webView = webViewsById[id]
    else { return }
    emit(id: id, payload: ["type": "open"], webView: webView)
    receive(webSocketTask, id: id)
  }

  func urlSession(
    _ session: URLSession,
    webSocketTask: URLSessionWebSocketTask,
    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
    reason: Data?
  ) {
    guard let id = idsByTask[webSocketTask.taskIdentifier], let webView = webViewsById[id]
    else { return }
    emit(id: id, payload: ["type": "close", "code": closeCode.rawValue], webView: webView)
    forget(id: id, task: webSocketTask)
  }

  private func receive(_ task: URLSessionWebSocketTask, id: String) {
    task.receive { [weak self, weak task] result in
      guard let self, let task, let webView = self.webViewsById[id] else { return }
      switch result {
      case .success(.string(let text)):
        if self.evidenceAudioEnabled && !self.evidenceAudioSent.contains(id)
          && isListenProtocolReady(text)
        {
          self.evidenceAudioSent.insert(id)
          task.send(.data(deterministicListenEvidenceAudio())) { [weak self, weak task] error in
            guard error != nil, let self, let task,
              let webView = self.webViewsById[id]
            else { return }
            self.emit(id: id, payload: ["type": "error"], webView: webView)
            task.cancel(with: .internalServerError, reason: nil)
          }
        }
        self.emit(id: id, payload: ["type": "message", "data": text], webView: webView)
        self.receive(task, id: id)
      case .success(.data):
        self.emit(id: id, payload: ["type": "error"], webView: webView)
        task.cancel(with: .unsupportedData, reason: nil)
      case .failure:
        self.emit(id: id, payload: ["type": "error"], webView: webView)
        self.emit(id: id, payload: ["type": "close", "code": 1006], webView: webView)
        self.forget(id: id, task: task)
      @unknown default:
        self.emit(id: id, payload: ["type": "error"], webView: webView)
      }
    }
  }

  private func forget(id: String, task: URLSessionWebSocketTask) {
    tasksById.removeValue(forKey: id)
    idsByTask.removeValue(forKey: task.taskIdentifier)
    webViewsById.removeValue(forKey: id)
    evidenceAudioSent.remove(id)
  }

  private func emit(id: String, payload: [String: Any], webView: WKWebView, callback: String = "__omiListenSocketEvent") {
    guard
      let idData = try? JSONSerialization.data(withJSONObject: id, options: .fragmentsAllowed),
      let payloadData = try? JSONSerialization.data(withJSONObject: payload),
      let idJSON = String(data: idData, encoding: .utf8),
      let payloadJSON = String(data: payloadData, encoding: .utf8)
    else { return }
    webView.evaluateJavaScript(
      "window.\(callback)?.(\(idJSON), \(payloadJSON))",
      completionHandler: nil)
  }
}
