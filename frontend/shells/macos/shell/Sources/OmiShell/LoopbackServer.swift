// Minimal fixed-port loopback static file server for the shared surface dist/.
// Port must stay constant across launches — IndexedDB/localStorage are origin-keyed
// including the port (ephemeral bind = silent wipe on relaunch).
import Foundation
import Network

final class LoopbackServer: @unchecked Sendable {
  static let defaultPort: UInt16 = 5290

  let port: UInt16
  let root: URL
  private var listener: NWListener?
  private let queue = DispatchQueue(label: "me.omi.shell.loopback")

  init(root: URL, port: UInt16 = LoopbackServer.defaultPort) {
    self.root = root.standardizedFileURL
    self.port = port
  }

  var originURL: URL { URL(string: "http://127.0.0.1:\(port)/")! }

  func start() throws {
    let params = NWParameters.tcp
    params.allowLocalEndpointReuse = true
    // Bind 127.0.0.1 only — plain NWParameters.tcp + on: listens on *:port.
    // requiredLocalEndpoint cannot be combined with NWListener(using:on:); port lives here.
    params.requiredLocalEndpoint = NWEndpoint.hostPort(
      host: .ipv4(.loopback),
      port: NWEndpoint.Port(rawValue: port)!)
    let listener = try NWListener(using: params)
    let ready = DispatchSemaphore(value: 0)
    var bindError: Error?
    listener.stateUpdateHandler = { state in
      switch state {
      case .ready: ready.signal()
      case .failed(let err):
        bindError = err
        FileHandle.standardError.write(Data("loopback failed: \(err)\n".utf8))
        ready.signal()
      default: break
      }
    }
    listener.newConnectionHandler = { [weak self] conn in
      self?.handle(conn)
    }
    listener.start(queue: queue)
    self.listener = listener
    // Wait briefly for ready / failed so bind errors surface before the webview loads.
    if ready.wait(timeout: .now() + 2) == .timedOut {
      throw NSError(
        domain: "LoopbackServer", code: 1,
        userInfo: [NSLocalizedDescriptionKey: "timeout waiting for port \(port)"])
    }
    if let bindError { throw bindError }
    FileHandle.standardError.write(
      Data("loopback: \(originURL.absoluteString) -> \(root.path)\n".utf8))
  }

  func stop() {
    listener?.cancel()
    listener = nil
  }

  private func handle(_ conn: NWConnection) {
    conn.start(queue: queue)
    receive(on: conn, buffer: Data())
  }

  private func receive(on conn: NWConnection, buffer: Data) {
    conn.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [weak self] data, _, isComplete, error in
      guard let self else { return }
      if let error {
        FileHandle.standardError.write(Data("loopback recv: \(error)\n".utf8))
        conn.cancel()
        return
      }
      var buf = buffer
      if let data { buf.append(data) }
      if let range = buf.range(of: Data("\r\n\r\n".utf8)) {
        let head = String(data: buf.subdata(in: buf.startIndex..<range.lowerBound), encoding: .utf8) ?? ""
        self.respond(to: head, on: conn)
        return
      }
      if isComplete {
        conn.cancel()
        return
      }
      if buf.count > 64 * 1024 {
        self.send(status: 400, body: Data("bad request".utf8), contentType: "text/plain", on: conn)
        return
      }
      self.receive(on: conn, buffer: buf)
    }
  }

  private func respond(to requestHead: String, on conn: NWConnection) {
    let lines = requestHead.split(separator: "\r\n", omittingEmptySubsequences: false)
    guard let requestLine = lines.first else {
      send(status: 400, body: Data("bad request".utf8), contentType: "text/plain", on: conn)
      return
    }
    let parts = requestLine.split(separator: " ")
    guard parts.count >= 2, parts[0] == "GET" || parts[0] == "HEAD" else {
      send(status: 405, body: Data("method not allowed".utf8), contentType: "text/plain", on: conn)
      return
    }
    let rawPath = String(parts[1].split(separator: "?", maxSplits: 1)[0])
    let decoded = rawPath.removingPercentEncoding ?? rawPath
    var rel = decoded
    if rel.hasPrefix("/") { rel.removeFirst() }
    if rel.isEmpty { rel = "index.html" }
    // Block path escape.
    if rel.contains("..") {
      send(status: 403, body: Data("forbidden".utf8), contentType: "text/plain", on: conn)
      return
    }
    let fileURL = root.appendingPathComponent(rel)
    guard let data = try? Data(contentsOf: fileURL) else {
      send(status: 404, body: Data("404".utf8), contentType: "text/plain", on: conn)
      return
    }
    let mime = Self.mime(for: fileURL.pathExtension)
    if parts[0] == "HEAD" {
      send(status: 200, body: Data(), contentType: mime, contentLength: data.count, on: conn)
    } else {
      send(status: 200, body: data, contentType: mime, on: conn)
    }
  }

  private func send(
    status: Int, body: Data, contentType: String, contentLength: Int? = nil, on conn: NWConnection
  ) {
    let reason: String
    switch status {
    case 200: reason = "OK"
    case 400: reason = "Bad Request"
    case 403: reason = "Forbidden"
    case 404: reason = "Not Found"
    case 405: reason = "Method Not Allowed"
    default: reason = "Error"
    }
    let len = contentLength ?? body.count
    var head = "HTTP/1.1 \(status) \(reason)\r\n"
    head += "Content-Type: \(contentType)\r\n"
    head += "Content-Length: \(len)\r\n"
    head += "Cache-Control: no-cache\r\n"
    head += "Connection: close\r\n"
    head += "\r\n"
    var payload = Data(head.utf8)
    payload.append(body)
    conn.send(content: payload, completion: .contentProcessed { _ in
      conn.cancel()
    })
  }

  private static func mime(for ext: String) -> String {
    switch ext.lowercased() {
    case "html": return "text/html; charset=utf-8"
    case "js", "mjs": return "text/javascript; charset=utf-8"
    case "css": return "text/css; charset=utf-8"
    case "json": return "application/json; charset=utf-8"
    case "svg": return "image/svg+xml"
    case "png": return "image/png"
    case "jpg", "jpeg": return "image/jpeg"
    case "map": return "application/json"
    case "wasm": return "application/wasm"
    default: return "application/octet-stream"
    }
  }
}
