import Darwin
import Foundation

/// A one-shot HTTP listener on `127.0.0.1:<ephemeral port>` that catches the OAuth redirect.
///
/// A loopback redirect is the only browser-based flow a non-sandboxed Mac app can complete without
/// registering a custom URL scheme, and it is what the Omi backend already expects. The socket is
/// raw BSD on purpose: this needs to serve exactly one GET and one HTML page, and `NWListener` would
/// bring an event-loop and a framer for that.
///
/// Lifetime rules the caller can rely on:
/// - The listening socket is closed the moment a result is known, on timeout, on `stop()`, and in
///   `deinit`. There is no path that leaves a port bound.
/// - `waitForCode` resumes exactly once. A result that arrives before anyone waits is held.
final class LoopbackCallbackServer: @unchecked Sendable {
    enum ServerError: Error {
        case socketCreationFailed
        case bindFailed
        case listenFailed
        case portLookupFailed
        /// The redirect carried a `state` that is not the one we sent — a replayed or forged callback.
        case stateMismatch
        /// The identity provider redirected with `error=...` instead of a code.
        case provider(String)
        case timedOut
        case stopped
    }

    let port: UInt16
    let redirectURI: String

    private let expectedState: String
    private let queue = DispatchQueue(label: "com.omi.context-for-claude.auth.loopback")
    private let lock = NSLock()

    private var socketFD: Int32?
    private var clientFD: Int32?
    private var continuation: CheckedContinuation<String, Error>?
    private var pendingResult: Result<String, Error>?
    private var isFinished = false

    private init(socketFD: Int32, port: UInt16, expectedState: String) {
        self.socketFD = socketFD
        self.port = port
        self.expectedState = expectedState
        self.redirectURI = "http://127.0.0.1:\(port)/callback"
    }

    // MARK: - Lifecycle

    /// Binds an ephemeral loopback port and starts accepting. Never binds `0.0.0.0`: the redirect is
    /// a bearer credential and must not be reachable from the network.
    static func start(expectedState: String) throws -> LoopbackCallbackServer {
        let fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
        guard fd >= 0 else { throw ServerError.socketCreationFailed }

        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = 0
        inet_pton(AF_INET, "127.0.0.1", &address.sin_addr)

        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0 else {
            close(fd)
            throw ServerError.bindFailed
        }
        guard listen(fd, 10) == 0 else {
            close(fd)
            throw ServerError.listenFailed
        }

        var assigned = sockaddr_in()
        var assignedLength = socklen_t(MemoryLayout<sockaddr_in>.size)
        let named = withUnsafeMutablePointer(to: &assigned) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(fd, $0, &assignedLength)
            }
        }
        guard named == 0 else {
            close(fd)
            throw ServerError.portLookupFailed
        }

        let server = LoopbackCallbackServer(
            socketFD: fd,
            port: UInt16(bigEndian: assigned.sin_port),
            expectedState: expectedState
        )
        server.acceptLoop()
        return server
    }

    /// Waits for the browser to hit `/callback`. The timeout is the backstop for the common real
    /// failure — the user closed the tab, or wandered off mid-consent — so the port and the accept
    /// thread cannot outlive the attempt.
    func waitForCode(timeout: TimeInterval = 180) async throws -> String {
        // Not `queue`: that one is parked inside a blocking `accept()` and would never run this.
        let expiry = DispatchWorkItem { [weak self] in self?.finish(.failure(ServerError.timedOut)) }
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + timeout, execute: expiry)
        defer { expiry.cancel() }

        return try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            if let pendingResult {
                self.pendingResult = nil
                lock.unlock()
                continuation.resume(with: pendingResult)
                return
            }
            self.continuation = continuation
            lock.unlock()
        }
    }

    /// Idempotent. Safe to call from a `defer` and again on the success path.
    func stop() {
        finish(.failure(ServerError.stopped))
    }

    deinit {
        stop()
    }

    // MARK: - Accepting

    private func acceptLoop() {
        queue.async { [weak self] in
            guard let self else { return }

            while !self.isCompleted {
                guard let listenFD = self.listeningSocket() else { return }

                var remote = sockaddr()
                var remoteLength = socklen_t(MemoryLayout<sockaddr>.size)
                let client = accept(listenFD, &remote, &remoteLength)
                // A closed listening socket lands here; the loop condition ends the thread.
                guard client >= 0 else { continue }

                self.setClient(client)
                defer { self.closeClient(client) }

                var on: Int32 = 1
                setsockopt(client, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
                var timeout = timeval(tv_sec: 5, tv_usec: 0)
                setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
                setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))

                var buffer = [UInt8]()
                buffer.reserveCapacity(8192)
                var temp = [UInt8](repeating: 0, count: 1024)
                var foundTerminator = false
                while buffer.count < 8192 {
                    let space = min(temp.count, 8192 - buffer.count)
                    let read = recv(client, &temp, space, 0)
                    guard read > 0 else { break }
                    buffer.append(contentsOf: temp.prefix(read))
                    if buffer.count >= 4 {
                        for i in 0..<(buffer.count - 3) {
                            if buffer[i] == 0x0D && buffer[i+1] == 0x0A &&
                               buffer[i+2] == 0x0D && buffer[i+3] == 0x0A {
                                buffer = Array(buffer[0..<i])
                                foundTerminator = true
                                break
                            }
                        }
                    }
                    if foundTerminator { break }
                }
                guard foundTerminator, let request = String(bytes: buffer, encoding: .utf8) else {
                    self.respond(.invalid, to: client)
                    continue
                }

                switch self.parse(request) {
                case .code(let code):
                    self.respond(.success, to: client)
                    self.finish(.success(code))
                    return
                case .stateMismatch:
                    // Loud, not ignored: something addressed our port with a foreign `state`, and
                    // exchanging that code would be the CSRF this parameter exists to stop.
                    self.respond(.failure, to: client)
                    self.finish(.failure(ServerError.stateMismatch))
                    return
                case .providerError(let reason):
                    self.respond(.failure, to: client)
                    self.finish(.failure(ServerError.provider(reason)))
                    return
                case .ignore:
                    // Favicon fetches and stray local probes must not end the sign-in.
                    self.respond(.invalid, to: client)
                    continue
                }
            }
        }
    }

    // MARK: - Request parsing

    private enum ParsedRequest {
        case code(String)
        case stateMismatch
        case providerError(String)
        case ignore
    }

    private func parse(_ request: String) -> ParsedRequest {
        let lines = request.split(separator: "\r\n", omittingEmptySubsequences: false)
        guard let requestLine = lines.first else { return .ignore }
        let parts = requestLine.split(separator: " ")
        guard parts.count >= 2, parts[0] == "GET" else { return .ignore }

        let headers = Array(lines.dropFirst())
        guard headersComeFromLoopback(headers) else { return .ignore }

        guard let components = URLComponents(string: "http://127.0.0.1\(parts[1])"),
            components.path == "/callback"
        else {
            return .ignore
        }

        let items = components.queryItems ?? []
        guard let state = items.first(where: { $0.name == "state" })?.value else { return .ignore }
        guard state == expectedState else { return .stateMismatch }

        if let error = items.first(where: { $0.name == "error" })?.value {
            return .providerError(error)
        }
        guard let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty else {
            return .ignore
        }
        return .code(code)
    }

    /// The redirect URI is a bearer credential and must only be accepted from the same machine. We
    /// require the HTTP `Host` header to match the bound loopback address, and if the browser sent an
    /// `Origin` or `Referer` it must also be loopback for this app.
    private func headersComeFromLoopback(_ headers: [Substring]) -> Bool {
        let hostHeader = headers.first {
            $0.trimmingCharacters(in: .whitespaces).lowercased().hasPrefix("host:")
        }.map { String($0.dropFirst(5)).trimmingCharacters(in: .whitespaces) }
        let expectedHost = redirectURI.replacingOccurrences(of: "http://", with: "")
            .replacingOccurrences(of: "/callback", with: "")
        let expectedHosts: Set<String> = [
            expectedHost,
            expectedHost.replacingOccurrences(of: "127.0.0.1", with: "localhost")
        ]
        guard let hostHeader, expectedHosts.contains(hostHeader) else { return false }

        let originOrReferer = headers.compactMap { line -> String? in
            let trimmed = line.trimmingCharacters(in: .whitespaces).lowercased()
            if trimmed.hasPrefix("origin:") {
                return String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
            }
            if trimmed.hasPrefix("referer:") {
                return String(line.dropFirst(8)).trimmingCharacters(in: .whitespaces)
            }
            return nil
        }
        for value in originOrReferer where !value.isEmpty {
            let allowed: Set<String> = [
                "http://127.0.0.1:\(port)",
                "http://localhost:\(port)",
            ]
            guard allowed.contains(value) || value.hasPrefix("http://127.0.0.1:\(port)/")
                  || value.hasPrefix("http://localhost:\(port)/")
            else { return false }
        }
        return true
    }

    // MARK: - Response

    enum CallbackPage {
        case success
        case failure
        case invalid

        var status: String {
            switch self {
            case .success: return "200 OK"
            case .failure, .invalid: return "400 Bad Request"
            }
        }

        var title: String {
            switch self {
            case .success: return "Signed in — Context for Claude"
            case .failure, .invalid: return "Sign-in failed — Context for Claude"
            }
        }

        var heading: String {
            switch self {
            case .success: return "You're signed in"
            case .failure: return "Sign-in failed"
            case .invalid: return "That wasn't a sign-in"
            }
        }

        var message: String {
            switch self {
            case .success: return "Head back to Context for Claude — it's in your menu bar. You can close this tab."
            case .failure: return "Something went wrong on the way back. Close this tab and try again from Context for Claude."
            case .invalid: return "This page only handles Context for Claude sign-in. You can close this tab."
            }
        }

        /// Two accents: the ordinary heading colour, and a red when something failed.
        ///
        /// These are plain neutrals and a standard red rather than the warm palette this page used
        /// to carry. The old justification was that the page "opens in the same browser as the
        /// product site, so it is held to the site's palette" — but that palette is the one the app
        /// deliberately moved off, and this page is the only web surface a real user sees, so it was
        /// the last place still showing it. `currentColor` would be neater than repeating the body
        /// colour, except the failure case genuinely needs its own hue.
        var accent: String {
            switch self {
            case .success: return "inherit"
            case .failure, .invalid: return "#C0392B"
            }
        }
    }

    /// Pure and static so the markup can be exercised without opening a socket.
    static func responseHTML(for page: CallbackPage) -> String {
        """
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>\(page.title)</title>
        <style>
          :root { color-scheme: light; }
          body {
            margin: 0; min-height: 100vh;
            display: flex; align-items: center; justify-content: center;
            /* Neutral greys, matching the installer art. This page kept the abandoned warm palette
               long after the app moved off it, and it is the one web surface a real user sees.
               A browser page cannot read NSColor semantics, so the appearance split below is a
               media query rather than a token. */
            background: #FAFAFA; color: #1C1C1C;
            font-family: "Open Runde", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            -webkit-font-smoothing: antialiased;
          }
          .card { max-width: 26rem; padding: 3rem 2rem; text-align: center; }
          svg { display: block; margin: 0 auto 1.75rem; opacity: 0.9; }
          h1 { margin: 0 0 0.6rem; font-size: 1.6rem; font-weight: 600; letter-spacing: -0.03em; color: \(page.accent); }
          p { margin: 0; font-size: 1rem; line-height: 1.55; color: #6E6E6E; }
          @media (prefers-color-scheme: dark) {
            body { background: #1C1C1E; color: #F2F2F2; }
            p { color: #9A9A9E; }
          }
        </style>
        </head>
        <body>
        <div class="card">
          <svg width="34" height="34" viewBox="0 0 32 32" fill="\(page.accent)" aria-hidden="true">
            <circle cx="6" cy="6" r="3"/><circle cx="16" cy="6" r="3"/><circle cx="26" cy="6" r="3"/>
            <circle cx="6" cy="16" r="3"/><circle cx="26" cy="16" r="3"/>
            <circle cx="6" cy="26" r="3"/><circle cx="16" cy="26" r="3"/><circle cx="26" cy="26" r="3"/>
          </svg>
          <h1>\(page.heading)</h1>
          <p>\(page.message)</p>
        </div>
        </body>
        </html>
        """
    }

    private func respond(_ page: CallbackPage, to fd: Int32) {
        let body = Self.responseHTML(for: page)
        let head = "HTTP/1.1 \(page.status)\r\n"
            + "Content-Type: text/html; charset=utf-8\r\n"
            + "Content-Length: \(body.utf8.count)\r\n"
            + "Cache-Control: no-store\r\n"
            + "Connection: close\r\n\r\n"
        sendAll(head + body, to: fd)
    }

    /// `send` can accept fewer bytes than asked for; a short write would truncate the page.
    private func sendAll(_ text: String, to fd: Int32) {
        let bytes = Array(text.utf8)
        var offset = 0
        while offset < bytes.count {
            let written = bytes.withUnsafeBytes { raw -> Int in
                guard let base = raw.baseAddress else { return -1 }
                return Darwin.send(fd, base.advanced(by: offset), bytes.count - offset, 0)
            }
            guard written > 0 else { return }
            offset += written
        }
    }

    // MARK: - Completion

    private func finish(_ result: Result<String, Error>) {
        lock.lock()
        guard !isFinished else {
            lock.unlock()
            return
        }
        isFinished = true
        closeSocketsLocked()
        let waiter = continuation
        continuation = nil
        if waiter == nil { pendingResult = result }
        lock.unlock()
        waiter?.resume(with: result)
    }

    private var isCompleted: Bool {
        lock.lock()
        defer { lock.unlock() }
        return isFinished
    }

    private func listeningSocket() -> Int32? {
        lock.lock()
        defer { lock.unlock() }
        return socketFD
    }

    private func setClient(_ fd: Int32) {
        lock.lock()
        clientFD = fd
        lock.unlock()
    }

    private func closeClient(_ fd: Int32) {
        lock.lock()
        if clientFD == fd {
            clientFD = nil
            close(fd)
        }
        lock.unlock()
    }

    private func closeSocketsLocked() {
        if let clientFD {
            close(clientFD)
            self.clientFD = nil
        }
        if let socketFD {
            close(socketFD)
            self.socketFD = nil
        }
    }
}
