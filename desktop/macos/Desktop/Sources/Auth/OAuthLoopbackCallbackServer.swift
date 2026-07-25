import Darwin
import Foundation

final class OAuthLoopbackCallbackServer: @unchecked Sendable {
  enum ServerError: Error {
    case socketCreationFailed
    case bindFailed
    case listenFailed
    case portLookupFailed
    case invalidRequest
  }

  private var socketFD: Int32?
  private var activeClientFD: Int32?
  private let queue = DispatchQueue(label: "com.omi.desktop.oauth-loopback-callback")
  private let lock = NSLock()
  private var continuation: CheckedContinuation<(code: String, state: String), Error>?
  private var pendingResult: Result<(code: String, state: String), Error>?
  private var completed = false
  private let expectedState: String
  private let appOpenURL: String

  let port: UInt16
  let redirectURI: String

  private init(socketFD: Int32, port: UInt16, expectedState: String, appOpenURL: String) {
    self.socketFD = socketFD
    self.port = port
    self.expectedState = expectedState
    self.appOpenURL = appOpenURL
    self.redirectURI = "http://127.0.0.1:\(port)/callback"
  }

  static func start(expectedState: String, appOpenURL: String) throws -> OAuthLoopbackCallbackServer {
    let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
    guard fd >= 0 else { throw ServerError.socketCreationFailed }

    var addr = sockaddr_in()
    addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = 0
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr)

    let bindResult = withUnsafePointer(to: &addr) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
      }
    }
    guard bindResult == 0 else {
      close(fd)
      throw ServerError.bindFailed
    }

    guard listen(fd, 1) == 0 else {
      close(fd)
      throw ServerError.listenFailed
    }

    var boundAddr = sockaddr_in()
    var boundAddrLen = socklen_t(MemoryLayout<sockaddr_in>.size)
    let portResult = withUnsafeMutablePointer(to: &boundAddr) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        getsockname(fd, $0, &boundAddrLen)
      }
    }
    guard portResult == 0 else {
      close(fd)
      throw ServerError.portLookupFailed
    }

    let server = OAuthLoopbackCallbackServer(
      socketFD: fd,
      port: UInt16(bigEndian: boundAddr.sin_port),
      expectedState: expectedState,
      appOpenURL: appOpenURL
    )
    server.acceptRequests()
    return server
  }

  func waitForCallback() async throws -> (code: String, state: String) {
    try await withCheckedThrowingContinuation { continuation in
      lock.lock()
      if let pendingResult {
        lock.unlock()
        continuation.resume(with: pendingResult)
        return
      }
      self.continuation = continuation
      lock.unlock()
    }
  }

  func cancel() {
    finish(.failure(AuthError.cancelled))
  }

  func fail(with error: Error) {
    finish(.failure(error))
  }

  func stop() {
    lock.lock()
    let alreadyCompleted = completed
    completed = true
    closeSocketsLocked()
    lock.unlock()
    if !alreadyCompleted {
      resumeIfNeeded(.failure(AuthError.cancelled))
    }
  }

  deinit {
    stop()
  }

  private func acceptRequests() {
    queue.async { [weak self] in
      guard let self else { return }

      while !self.isCompleted {
        guard let listenFD = self.currentListenSocket() else { return }

        var remoteAddr = sockaddr()
        var remoteLen = socklen_t(MemoryLayout<sockaddr>.size)
        let clientFD = accept(listenFD, &remoteAddr, &remoteLen)
        guard clientFD >= 0 else { continue }

        self.setActiveClient(clientFD)
        defer {
          self.closeActiveClientIfMatching(clientFD)
        }

        var noSigPipe: Int32 = 1
        setsockopt(clientFD, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, socklen_t(MemoryLayout<Int32>.size))

        var timeout = timeval(tv_sec: 5, tv_usec: 0)
        setsockopt(clientFD, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))

        var buffer = [UInt8](repeating: 0, count: 8192)
        let bytesRead = recv(clientFD, &buffer, buffer.count - 1, 0)
        guard bytesRead > 0,
          let request = String(bytes: buffer.prefix(bytesRead), encoding: .utf8)
        else {
          self.sendResponse(clientFD, page: .invalid)
          continue
        }

        switch self.parseCallbackRequest(request) {
        case .success(let code, let state):
          self.sendResponse(clientFD, page: .success, appOpenURL: self.appOpenURL)
          self.finish(.success((code: code, state: state)))
          return
        case .providerError(let error):
          self.sendResponse(clientFD, page: .failure)
          self.finish(.failure(AuthError.oauthError(error)))
          return
        case .ignore:
          self.sendResponse(clientFD, page: .invalid)
          continue
        }
      }
    }
  }

  enum CallbackPage {
    case success
    case failure
    case invalid

    var httpStatus: String {
      switch self {
      case .success: return "200 OK"
      case .failure, .invalid: return "400 Bad Request"
      }
    }

    var documentTitle: String {
      switch self {
      case .success: return "Signed in - Omi"
      case .failure, .invalid: return "Authentication failed - Omi"
      }
    }

    var heading: String {
      switch self {
      case .success: return "You're signed in"
      case .failure: return "Authentication failed"
      case .invalid: return "Invalid callback"
      }
    }

    var message: String {
      switch self {
      case .success: return "You can close this tab and return to Omi."
      case .failure: return "You can close this tab and try again in the app."
      case .invalid: return "This authentication callback was invalid. You can close this tab."
      }
    }

    var icon: String {
      switch self {
      case .success: return "✓"
      case .failure, .invalid: return "!"
      }
    }

    var iconBackground: String {
      switch self {
      case .success: return "#111111"
      case .failure, .invalid: return "#d32f2f"
      }
    }
  }

  /// Branded HTML body served on the local OAuth loopback callback.
  /// Kept pure/static so unit tests can assert markup without opening a socket.
  static func responseHTML(for page: CallbackPage, appOpenURL: String? = nil) -> String {
    let openAppAction: String
    switch (page, appOpenURL) {
    case (.success, let .some(appOpenURL)):
      let escapedURL = htmlAttributeEscaped(appOpenURL)
      openAppAction = """
                <p class="open-app-message">Opening Omi… If it doesn’t come to the front, select Open Omi.</p>
                <a class="open-app-button" id="open-omi" href="\(escapedURL)">Open Omi</a>
        """
    default:
      openAppAction = ""
    }

    let openAppScript: String
    switch (page, appOpenURL) {
    case (.success, .some):
      openAppScript = """
            <script>
                window.setTimeout(function () {
                    var openOmi = document.getElementById("open-omi");
                    if (openOmi) { window.location.assign(openOmi.href); }
                }, 100);
            </script>
        """
    default:
      openAppScript = ""
    }

    return """
      <!DOCTYPE html>
      <html lang="en">
      <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>\(page.documentTitle)</title>
          <style>
              body {
                  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                  display: flex;
                  flex-direction: column;
                  align-items: center;
                  justify-content: center;
                  min-height: 100vh;
                  margin: 0;
                  background-color: #f7f7f7;
                  color: #333;
              }
              .card {
                  background-color: white;
                  border-radius: 8px;
                  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                  padding: 48px 32px;
                  text-align: center;
                  max-width: 400px;
              }
              .icon {
                  width: 56px;
                  height: 56px;
                  margin: 0 auto 16px;
                  border-radius: 50%;
                  background-color: \(page.iconBackground);
                  color: white;
                  font-size: 28px;
                  font-weight: 600;
                  line-height: 56px;
              }
              h1 {
                  font-size: 24px;
                  font-weight: 600;
                  margin: 0 0 12px 0;
              }
              p {
                  font-size: 16px;
                  color: #555;
                  margin: 0;
                  line-height: 1.5;
              }
              .open-app-message {
                  margin-top: 20px;
              }
              .open-app-button {
                  display: inline-block;
                  margin-top: 16px;
                  padding: 12px 20px;
                  border-radius: 8px;
                  background-color: #111111;
                  color: white;
                  font-size: 16px;
                  font-weight: 600;
                  text-decoration: none;
              }
          </style>
      </head>
      <body>
          <div class="card">
              <div class="icon">\(page.icon)</div>
              <h1>\(page.heading)</h1>
              <p>\(page.message)</p>
      \(openAppAction)
          </div>
      \(openAppScript)
      </body>
      </html>
      """
  }

  private static func htmlAttributeEscaped(_ value: String) -> String {
    value
      .replacingOccurrences(of: "&", with: "&amp;")
      .replacingOccurrences(of: "\"", with: "&quot;")
      .replacingOccurrences(of: "<", with: "&lt;")
      .replacingOccurrences(of: ">", with: "&gt;")
  }

  private enum ParsedCallbackRequest {
    case success(code: String, state: String)
    case providerError(String)
    case ignore
  }

  private func parseCallbackRequest(_ request: String) -> ParsedCallbackRequest {
    guard let requestLine = request.split(separator: "\r\n", maxSplits: 1).first else {
      return .ignore
    }
    let parts = requestLine.split(separator: " ")
    guard parts.count >= 2, parts[0] == "GET" else {
      return .ignore
    }

    let target = String(parts[1])
    guard let components = URLComponents(string: "http://127.0.0.1\(target)"),
      components.path == "/callback"
    else {
      return .ignore
    }

    let queryItems = components.queryItems ?? []
    guard let state = queryItems.first(where: { $0.name == "state" })?.value,
      state == expectedState
    else {
      return .ignore
    }

    if let providerError = queryItems.first(where: { $0.name == "error" })?.value {
      return .providerError(providerError)
    }

    guard let code = queryItems.first(where: { $0.name == "code" })?.value else {
      return .ignore
    }
    return .success(code: code, state: state)
  }

  private func sendResponse(_ clientFD: Int32, page: CallbackPage, appOpenURL: String? = nil) {
    let body = Self.responseHTML(for: page, appOpenURL: appOpenURL)
    let response = """
      HTTP/1.1 \(page.httpStatus)\r
      Content-Type: text/html; charset=utf-8\r
      Content-Length: \(body.utf8.count)\r
      Connection: close\r
      \r
      \(body)
      """
    response.withCString { pointer in
      _ = send(clientFD, pointer, strlen(pointer), 0)
    }
  }

  private func finish(_ result: Result<(code: String, state: String), Error>) {
    lock.lock()
    guard !completed else {
      lock.unlock()
      return
    }
    completed = true
    closeSocketsLocked()
    lock.unlock()
    resumeIfNeeded(result)
  }

  private func resumeIfNeeded(_ result: Result<(code: String, state: String), Error>) {
    lock.lock()
    if let continuation {
      self.continuation = nil
      lock.unlock()
      continuation.resume(with: result)
    } else {
      pendingResult = result
      lock.unlock()
    }
  }

  private var isCompleted: Bool {
    lock.lock()
    defer { lock.unlock() }
    return completed
  }

  private func currentListenSocket() -> Int32? {
    lock.lock()
    defer { lock.unlock() }
    return socketFD
  }

  private func setActiveClient(_ fd: Int32) {
    lock.lock()
    activeClientFD = fd
    lock.unlock()
  }

  private func closeActiveClientIfMatching(_ fd: Int32) {
    lock.lock()
    if activeClientFD == fd {
      activeClientFD = nil
      close(fd)
    }
    lock.unlock()
  }

  private func closeSocketsLocked() {
    if let activeClientFD {
      close(activeClientFD)
      self.activeClientFD = nil
    }
    if let socketFD {
      close(socketFD)
      self.socketFD = nil
    }
  }
}
