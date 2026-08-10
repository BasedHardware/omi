import Foundation
import WebKit

struct ListenSocketPreparedRequest {
  let id: String
  let request: URLRequest
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

  func makeListenHandler() -> ListenSocketHandler {
    ListenSocketHandler(baseURL: baseURL, custody: custody)
  }

  func prepareListen(id: String, path: String) -> ListenSocketPolicyDecision {
    ListenSocketPolicy.prepare(
      id: id, path: path, baseURL: baseURL, token: custody.currentToken())
  }
}

/// Pure authority/auth policy shared by the live handler and composition test.
enum ListenSocketPolicy {
  static func prepare(id: String, path: String, baseURL: URL, token: String?)
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
    return .dispatch(ListenSocketPreparedRequest(id: id, request: request))
  }
}

private struct ListenSocketCommand: Decodable {
  let id: String
  let action: String
  let path: String?
  let code: Int?
  let reason: String?
}

/// Native WebSocket owner. Base authority and bearer credential never cross to JS.
final class ListenSocketHandler: NSObject, WKScriptMessageHandler, URLSessionWebSocketDelegate,
  @unchecked Sendable
{
  static let channel = "omiListenSocket"

  private let baseURL: URL
  private let custody: ShellCredentialCustody
  private var tasksById: [String: URLSessionWebSocketTask] = [:]
  private var idsByTask: [Int: String] = [:]
  private var webViewsById: [String: WKWebView] = [:]
  private lazy var session: URLSession = {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.httpCookieStorage = nil
    configuration.httpShouldSetCookies = false
    return URLSession(configuration: configuration, delegate: self, delegateQueue: .main)
  }()

  init(baseURL: URL, custody: ShellCredentialCustody) {
    self.baseURL = baseURL
    self.custody = custody
    super.init()
  }

  func prepareUsingCurrentCustodyForConformance(
    id: String, path: String
  ) -> ListenSocketPolicyDecision {
    ListenSocketPolicy.prepare(
      id: id, path: path, baseURL: baseURL, token: custody.currentToken())
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

    if command.action == "close" {
      let closeCode = URLSessionWebSocketTask.CloseCode(rawValue: command.code ?? 1000)
        ?? .normalClosure
      let reason = command.reason?.data(using: .utf8)
      tasksById[command.id]?.cancel(with: closeCode, reason: reason)
      return
    }
    guard command.action == "open", let path = command.path else { return }
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
  }

  private func emit(id: String, payload: [String: Any], webView: WKWebView) {
    guard
      let idData = try? JSONSerialization.data(withJSONObject: id, options: .fragmentsAllowed),
      let payloadData = try? JSONSerialization.data(withJSONObject: payload),
      let idJSON = String(data: idData, encoding: .utf8),
      let payloadJSON = String(data: payloadData, encoding: .utf8)
    else { return }
    webView.evaluateJavaScript(
      "window.__omiListenSocketEvent?.(\(idJSON), \(payloadJSON))",
      completionHandler: nil)
  }
}
