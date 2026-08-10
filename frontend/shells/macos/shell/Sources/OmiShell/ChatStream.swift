import CoreFoundation
import Foundation
import WebKit

struct ChatStreamPreparedRequest {
  let id: String
  let request: URLRequest
}

enum ChatStreamPolicyDecision {
  case dispatch(ChatStreamPreparedRequest)
  case failure(String)
}

enum ChatStreamPolicy {
  private static let generationIdLimit = 256
  private static let eventIdLimit = 1_024
  private static let pathSegmentAllowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

  static func isSafeOpaque(_ value: String, limit: Int) -> Bool {
    guard !value.isEmpty, value.utf8.count <= limit else { return false }
    return value.unicodeScalars.allSatisfy { scalar in
      scalar.value >= 0x20 && scalar.value != 0x7f && scalar.value != 0x2028 && scalar.value != 0x2029
    }
  }

  static func prepare(
    id: String,
    generationId: String,
    lastEventId: String?,
    baseURL: URL,
    token: String?,
    runId: String?
  ) -> ChatStreamPolicyDecision {
    guard isSafeOpaque(generationId, limit: generationIdLimit),
      let encodedGenerationId = generationId.addingPercentEncoding(withAllowedCharacters: pathSegmentAllowed)
    else { return .failure("unsafe-generation-id") }
    if let lastEventId, !isSafeOpaque(lastEventId, limit: eventIdLimit) {
      return .failure("unsafe-event-id")
    }
    guard let token, !token.isEmpty else { return .failure("not-authenticated") }
    guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false),
      components.scheme == "http" || components.scheme == "https",
      components.host != nil
    else { return .failure("invalid-origin") }
    components.percentEncodedPath = "/v1/chat-generations/\(encodedGenerationId)/events"
    components.query = nil
    components.fragment = nil
    guard let url = components.url else { return .failure("invalid-origin") }

    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
    request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
    request.setValue(
      NativeChatRequestContract.contractVersion,
      forHTTPHeaderField: NativeChatRequestContract.contractVersionHeader)
    if let clientId = BridgeHttpPolicy.shellClientId(runId: runId) {
      request.setValue(clientId, forHTTPHeaderField: NativeChatRequestContract.clientIdHeader)
    }
    if let lastEventId {
      request.setValue(lastEventId, forHTTPHeaderField: "Last-Event-ID")
    }
    return .dispatch(ChatStreamPreparedRequest(id: id, request: request))
  }

  static func sessionConfiguration() -> URLSessionConfiguration {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.timeoutIntervalForRequest = 30
    configuration.timeoutIntervalForResource = 60 * 60
    configuration.httpCookieStorage = nil
    configuration.httpShouldSetCookies = false
    configuration.httpCookieAcceptPolicy = .never
    return configuration
  }
}

enum IncrementalUTF8Error: Error {
  case invalid
  case truncated
}

/// Strict streaming UTF-8 decoder. At most three incomplete bytes are retained;
/// complete prefixes are never repaired with replacement characters.
struct IncrementalUTF8Decoder {
  private var pending = Data()

  mutating func push(_ data: Data) throws -> String? {
    pending.append(data)
    let prefixLength = try completePrefixLength(pending)
    guard prefixLength > 0 else { return nil }
    let prefix = pending.prefix(prefixLength)
    pending.removeFirst(prefixLength)
    guard let text = String(data: prefix, encoding: .utf8) else { throw IncrementalUTF8Error.invalid }
    return text.isEmpty ? nil : text
  }

  mutating func finish() throws -> String? {
    guard pending.isEmpty else { throw IncrementalUTF8Error.truncated }
    return nil
  }

  private func completePrefixLength(_ data: Data) throws -> Int {
    let bytes = [UInt8](data)
    var index = 0
    while index < bytes.count {
      let first = bytes[index]
      if first <= 0x7f {
        index += 1
        continue
      }
      let length: Int
      if first >= 0xc2 && first <= 0xdf { length = 2 }
      else if first >= 0xe0 && first <= 0xef { length = 3 }
      else if first >= 0xf0 && first <= 0xf4 { length = 4 }
      else { throw IncrementalUTF8Error.invalid }
      if bytes.count - index < length { return index }
      let second = bytes[index + 1]
      guard second >= 0x80 && second <= 0xbf else { throw IncrementalUTF8Error.invalid }
      if first == 0xe0 && second < 0xa0 { throw IncrementalUTF8Error.invalid }
      if first == 0xed && second > 0x9f { throw IncrementalUTF8Error.invalid }
      if first == 0xf0 && second < 0x90 { throw IncrementalUTF8Error.invalid }
      if first == 0xf4 && second > 0x8f { throw IncrementalUTF8Error.invalid }
      if length >= 3 {
        let third = bytes[index + 2]
        guard third >= 0x80 && third <= 0xbf else { throw IncrementalUTF8Error.invalid }
      }
      if length == 4 {
        let fourth = bytes[index + 3]
        guard fourth >= 0x80 && fourth <= 0xbf else { throw IncrementalUTF8Error.invalid }
      }
      index += length
    }
    return index
  }
}

private final class ChatStreamSession {
  let id: String
  let channel: String
  weak var webView: WKWebView?
  var credit: Int
  var decoder = IncrementalUTF8Decoder()
  var queuedPayloads: [String] = []
  var task: URLSessionDataTask?
  var isSuspended = false
  var responseAccepted = false
  var networkFinished = false

  init(id: String, channel: String, credit: Int, webView: WKWebView?) {
    self.id = id
    self.channel = channel
    self.credit = credit
    self.webView = webView
  }
}

/// The sole macOS producer for the generated `omiStream` channel.
final class ChatStreamHandler: NSObject, WKScriptMessageHandler, URLSessionDataDelegate,
  URLSessionTaskDelegate, @unchecked Sendable
{
  static let channel = BridgeStreamContract.channel

  private let baseURL: URL
  private let custody: ShellCredentialCustody
  private let runId: String?
  private let configuration: URLSessionConfiguration
  private let evaluateJavaScript: ((String) -> Void)?
  private var sessions: [String: ChatStreamSession] = [:]
  private var idsByTask: [Int: String] = [:]
  private var tornDown = false
  private lazy var session = URLSession(
    configuration: configuration, delegate: self, delegateQueue: .main)

  init(
    baseURL: URL,
    custody: ShellCredentialCustody,
    runId: String?,
    configuration: URLSessionConfiguration? = nil,
    evaluateJavaScript: ((String) -> Void)? = nil
  ) {
    self.baseURL = baseURL
    self.custody = custody
    self.runId = runId
    self.configuration = configuration ?? ChatStreamPolicy.sessionConfiguration()
    self.evaluateJavaScript = evaluateJavaScript
    super.init()
  }

  func prepareUsingCurrentCustodyForConformance(
    id: String, generationId: String, lastEventId: String?
  ) -> ChatStreamPolicyDecision {
    ChatStreamPolicy.prepare(
      id: id, generationId: generationId, lastEventId: lastEventId,
      baseURL: baseURL, token: custody.currentToken(), runId: runId)
  }

  func enqueuePayloadForConformance(id: String, payload: String) -> Bool {
    guard let item = sessions[id], item.responseAccepted, !item.networkFinished else { return false }
    item.queuedPayloads.append(payload)
    drain(item)
    return true
  }

  func finishForConformance(id: String) -> Bool {
    guard let item = sessions[id], item.responseAccepted else { return false }
    item.networkFinished = true
    drain(item)
    return true
  }

  func userContentController(
    _ userContentController: WKUserContentController,
    didReceive message: WKScriptMessage
  ) {
    receive(raw: message.body, webView: message.webView)
  }

  /// Controllable production seam used by the compiled host proofs.
  func receive(raw: Any, webView: WKWebView? = nil) {
    dispatchPrecondition(condition: .onQueue(.main))
    guard !tornDown, let raw = raw as? String,
      let data = raw.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data),
      let frame = object as? [String: Any]
    else { return }
    guard let id = frame["id"] as? String, safeBridgeId(id) else { return }
    guard let type = frame["t"] as? String,
      let channel = frame["channel"] as? String,
      channel == BridgeStreamContract.chatGenerationChannel
    else {
      rejectRoutable(id: id, webView: webView)
      return
    }

    switch type {
    case BridgeStreamContract.ToShellMessage.open.rawValue:
      open(frame: frame, id: id, channel: channel, webView: webView)
    case BridgeStreamContract.ToShellMessage.grant.rawValue:
      grant(frame: frame, id: id, channel: channel, webView: webView)
    case BridgeStreamContract.ToShellMessage.cancel.rawValue:
      cancel(frame: frame, id: id, channel: channel, webView: webView)
    default:
      rejectRoutable(id: id, webView: webView)
    }
  }

  func cancelAll() {
    dispatchPrecondition(condition: .onQueue(.main))
    let active = Array(sessions.values)
    sessions.removeAll()
    idsByTask.removeAll()
    for item in active { item.task?.cancel() }
  }

  func teardown() {
    dispatchPrecondition(condition: .onQueue(.main))
    guard !tornDown else { return }
    tornDown = true
    cancelAll()
    session.invalidateAndCancel()
  }

  private func open(frame: [String: Any], id: String, channel: String, webView: WKWebView?) {
    guard Set(frame.keys) == ["t", "id", "channel", "params", "credit"],
      sessions[id] == nil,
      let params = frame["params"] as? String,
      let credit = exactPositiveInteger(frame["credit"]), credit <= 1_000_000,
      let paramsData = params.data(using: .utf8),
      let paramsObject = try? JSONSerialization.jsonObject(with: paramsData),
      let values = paramsObject as? [String: Any],
      exactGenerationParameterKeys(Set(values.keys)),
      let generationId = values["generationId"] as? String,
      values["lastEventId"] == nil || values["lastEventId"] is String
    else {
      rejectRoutable(id: id, webView: webView)
      return
    }
    let lastEventId = values["lastEventId"] as? String
    switch prepareUsingCurrentCustodyForConformance(
      id: id, generationId: generationId, lastEventId: lastEventId)
    {
    case .failure(let failure):
      emit(type: .error, id: id, channel: channel, valueName: "failure", value: failure, webView: webView)
    case .dispatch(let prepared):
      let item = ChatStreamSession(id: id, channel: channel, credit: credit, webView: webView)
      let task = session.dataTask(with: prepared.request)
      item.task = task
      sessions[id] = item
      idsByTask[task.taskIdentifier] = id
      task.resume()
    }
  }

  private func grant(
    frame: [String: Any], id: String, channel: String, webView: WKWebView?
  ) {
    guard Set(frame.keys) == ["t", "id", "channel", "credit"],
      let item = sessions[id], item.channel == channel,
      let grant = exactPositiveInteger(frame["credit"]),
      grant <= 1_000_000, item.credit <= 1_000_000 - grant
    else {
      rejectRoutable(id: id, webView: webView)
      return
    }
    item.credit += grant
    drain(item)
    if item.isSuspended && !item.networkFinished && item.credit > 0 {
      item.isSuspended = false
      item.task?.resume()
    }
  }

  private func cancel(
    frame: [String: Any], id: String, channel: String, webView: WKWebView?
  ) {
    let keys = Set(frame.keys)
    guard keys == ["t", "id", "channel"] || keys == ["t", "id", "channel", "reason"],
      frame["reason"] == nil || safeReason(frame["reason"]),
      let item = sessions[id], item.channel == channel
    else {
      rejectRoutable(id: id, webView: webView)
      return
    }
    forget(item, cancelTask: true)
  }

  private func rejectRoutable(id: String, webView: WKWebView?) {
    if let item = sessions[id] {
      fail(item, failure: "invalid-frame")
      return
    }
    emit(
      type: .error, id: id, channel: BridgeStreamContract.chatGenerationChannel,
      valueName: "failure", value: "invalid-frame", webView: webView)
  }

  private func exactGenerationParameterKeys(_ keys: Set<String>) -> Bool {
    let required = BridgeStreamContract.chatGenerationRequiredParameterFields
    let allowed = required.union(BridgeStreamContract.chatGenerationOptionalParameterFields)
    return required.isSubset(of: keys) && keys.isSubset(of: allowed)
  }

  private func safeBridgeId(_ id: String) -> Bool {
    id.count <= 128
      && id.range(of: #"^[A-Za-z0-9][A-Za-z0-9._-]*$"#, options: .regularExpression) != nil
  }

  private func safeReason(_ value: Any?) -> Bool {
    guard let value = value as? String, value.utf8.count <= 256 else { return false }
    return ChatStreamPolicy.isSafeOpaque(value, limit: 256)
  }

  private func exactPositiveInteger(_ value: Any?) -> Int? {
    guard let number = value as? NSNumber,
      CFGetTypeID(number) != CFBooleanGetTypeID()
    else { return nil }
    let double = number.doubleValue
    guard double.isFinite, double.rounded() == double, double > 0, double <= Double(Int.max) else {
      return nil
    }
    return Int(double)
  }

  private func drain(_ item: ChatStreamSession) {
    guard sessions[item.id] === item else { return }
    while item.credit > 0 && !item.queuedPayloads.isEmpty {
      let payload = item.queuedPayloads.removeFirst()
      item.credit -= 1
      emit(
        type: .data, id: item.id, channel: item.channel,
        valueName: "payload", value: payload, webView: item.webView)
    }
    if item.credit == 0 && !item.networkFinished && !item.isSuspended {
      item.isSuspended = true
      item.task?.suspend()
    }
    if item.networkFinished && item.queuedPayloads.isEmpty {
      finish(item)
    }
  }

  private func finish(_ item: ChatStreamSession) {
    guard sessions[item.id] === item else { return }
    emit(type: .end, id: item.id, channel: item.channel, webView: item.webView)
    forget(item, cancelTask: true)
  }

  private func fail(_ item: ChatStreamSession, failure: String) {
    guard sessions[item.id] === item else { return }
    item.queuedPayloads.removeAll()
    emit(
      type: .error, id: item.id, channel: item.channel,
      valueName: "failure", value: failure, webView: item.webView)
    forget(item, cancelTask: true)
  }

  private func forget(_ item: ChatStreamSession, cancelTask: Bool) {
    sessions.removeValue(forKey: item.id)
    if let task = item.task { idsByTask.removeValue(forKey: task.taskIdentifier) }
    if cancelTask { item.task?.cancel() }
    item.task = nil
    item.queuedPayloads.removeAll()
  }

  private func emit(
    type: BridgeStreamContract.FromShellMessage,
    id: String,
    channel: String,
    valueName: String? = nil,
    value: String? = nil,
    webView: WKWebView?
  ) {
    guard !tornDown else { return }
    var frame: [String: Any] = ["t": type.rawValue, "id": id, "channel": channel]
    if let valueName, let value { frame[valueName] = value }
    guard let frameData = try? JSONSerialization.data(withJSONObject: frame),
      let frameJSON = String(data: frameData, encoding: .utf8),
      let argumentData = try? JSONSerialization.data(
        withJSONObject: frameJSON, options: .fragmentsAllowed),
      let argumentJSON = String(data: argumentData, encoding: .utf8),
      let sinkData = try? JSONSerialization.data(
        withJSONObject: BridgeStreamContract.sinkFunction, options: .fragmentsAllowed),
      let sinkJSON = String(data: sinkData, encoding: .utf8)
    else { return }
    let script = "globalThis[\(sinkJSON)]?.(\(argumentJSON))"
    if let evaluateJavaScript { evaluateJavaScript(script) }
    else { webView?.evaluateJavaScript(script, completionHandler: nil) }
  }

  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse,
    newRequest request: URLRequest,
    completionHandler: @escaping (URLRequest?) -> Void
  ) {
    if let id = idsByTask[task.taskIdentifier], let item = sessions[id] {
      fail(item, failure: "redirect-refused")
    }
    completionHandler(nil)
  }

  func urlSession(
    _ session: URLSession,
    dataTask: URLSessionDataTask,
    didReceive response: URLResponse,
    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
  ) {
    guard let id = idsByTask[dataTask.taskIdentifier], let item = sessions[id],
      let http = response as? HTTPURLResponse,
      http.statusCode == 200,
      http.mimeType?.lowercased() == "text/event-stream"
    else {
      if let id = idsByTask[dataTask.taskIdentifier], let item = sessions[id] {
        fail(item, failure: "request-refused")
      }
      completionHandler(.cancel)
      return
    }
    item.responseAccepted = true
    completionHandler(.allow)
  }

  func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
    guard let id = idsByTask[dataTask.taskIdentifier], let item = sessions[id],
      item.responseAccepted
    else { return }
    do {
      if let text = try item.decoder.push(data) { item.queuedPayloads.append(text) }
      drain(item)
    } catch {
      fail(item, failure: "invalid-utf8")
    }
  }

  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    didCompleteWithError error: Error?
  ) {
    guard let id = idsByTask[task.taskIdentifier], let item = sessions[id] else { return }
    if error != nil {
      fail(item, failure: "transport-error")
      return
    }
    do {
      if let text = try item.decoder.finish() { item.queuedPayloads.append(text) }
      item.networkFinished = true
      drain(item)
    } catch {
      fail(item, failure: "invalid-utf8")
    }
  }
}
