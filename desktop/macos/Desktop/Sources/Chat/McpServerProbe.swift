import Foundation

/// Whether a configured MCP server actually answers, and with what.
///
/// Without this every server read "Active in chat" — including one whose command is not installed,
/// whose token expired, or whose URL moved. The user found out in a conversation, where the only
/// symptom is the assistant quietly not having the tools it should.
///
/// The probe speaks the same three messages the runtime does (`initialize`, `notifications/
/// initialized`, `tools/list`) so a server that passes here is one the runtime can use.
enum McpServerProbe {
  enum Status: Equatable {
    case checking
    case running(toolCount: Int)
    /// A local command that resolves. Whether it *works* is only knowable by running it, which a
    /// status badge must not do.
    case configured
    /// Reachable, but refusing us — an expired token or a server that wants OAuth.
    case needsAuth
    case unreachable(String)

    var isHealthy: Bool {
      switch self {
      case .running, .configured: return true
      case .checking, .needsAuth, .unreachable: return false
      }
    }

    /// What the card shows in place of the old unconditional "Active in chat".
    var label: String {
      switch self {
      case .checking: return "Checking…"
      case .configured: return "Ready"
      case .running(let count):
        if count < 0 { return "Responding" }
        return count == 1 ? "1 tool" : "\(count) tools"
      case .needsAuth: return "Needs sign-in"
      case .unreachable: return "Not responding"
      }
    }

    var detail: String? {
      if case .unreachable(let reason) = self { return reason }
      return nil
    }
  }

  /// Long enough for `npx` to resolve a package on a cold cache, short enough that a wedged server
  /// does not hold the section.
  static let timeout: TimeInterval = 20

  /// How many event-stream lines to read before giving up on an SSE server naming its endpoint.
  /// A conforming server names it first; anything past this is keepalives or another protocol.
  static let maxSseProbeLines = 200

  /// A server's config reduced to what a probe needs, and to values that can cross an actor
  /// boundary — the raw `[String: Any]` entry cannot.
  enum Target: Sendable, Equatable {
    case stdio(command: String, args: [String], env: [String: String])
    case http(url: URL, headers: [String: String])
    /// The older HTTP+SSE transport: the URL is an event stream, not a POST target.
    case sse(url: URL, headers: [String: String])
    case unconfigured

    init(entry: [String: Any]) {
      if let command = (entry["command"] as? String)?.trimmingCharacters(in: .whitespaces),
        !command.isEmpty
      {
        self = .stdio(
          command: command,
          args: (entry["args"] as? [Any])?.compactMap { $0 as? String } ?? [],
          env: (entry["env"] as? [String: Any])?.compactMapValues { $0 as? String } ?? [:])
      } else if let raw = entry["url"] as? String, let url = URL(string: raw) {
        let headers = McpServerProbe.headers(from: entry)
        self =
          (entry["transport"] as? String) == "sse"
          ? .sse(url: url, headers: headers) : .http(url: url, headers: headers)
      } else {
        self = .unconfigured
      }
    }
  }

  static func probe(_ target: Target) async -> Status {
    switch target {
    case .stdio(let command, let args, let env):
      return await probeStdio(command: command, args: args, env: env)
    case .http(let url, let headers):
      return await probeHTTP(url: url, headers: headers)
    case .sse(let url, let headers):
      return await probeSSE(url: url, headers: headers)
    case .unconfigured:
      return .unreachable("No command or URL configured")
    }
  }

  static func headers(from entry: [String: Any]) -> [String: String] {
    var headers = (entry["headers"] as? [String: Any])?.compactMapValues { $0 as? String } ?? [:]
    let bearer =
      (entry["token"] as? String)
      ?? ((entry["auth"] as? [String: Any])?["access_token"] as? String)
    if let bearer, !bearer.isEmpty, headers["Authorization"] == nil {
      headers["Authorization"] = "Bearer \(bearer)"
    }
    return headers
  }

  // MARK: - Remote

  static func probeHTTP(url: URL, headers: [String: String]) async -> Status {
    var request = URLRequest(url: url, timeoutInterval: timeout)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    // Streamable HTTP servers answer either as JSON or as an SSE stream; accept both.
    request.setValue("application/json, text/event-stream", forHTTPHeaderField: "Accept")
    for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
    request.httpBody = try? JSONSerialization.data(withJSONObject: initializeRequest)

    do {
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse else { return .unreachable("No response") }
      if http.statusCode == 401 || http.statusCode == 403 { return .needsAuth }
      guard (200..<300).contains(http.statusCode) else {
        return .unreachable("Server returned HTTP \(http.statusCode)")
      }
      guard payload(from: data) != nil else { return .unreachable("Unexpected response") }

      // Streamable HTTP binds the rest of the exchange to the session it just issued.
      var session = headers
      if let id = http.value(forHTTPHeaderField: "mcp-session-id") { session["mcp-session-id"] = id }
      _ = try? await post(url: url, headers: session, body: initializedNotification)
      guard let listed = try? await post(url: url, headers: session, body: toolsListRequest),
        let tools = payload(from: listed)?["tools"] as? [Any]
      else {
        // Initialize succeeded, so the server is up; only the count is unknown.
        return .running(toolCount: -1)
      }
      return .running(toolCount: tools.count)
    } catch {
      return .unreachable("Could not reach the server")
    }
  }

  /// An HTTP+SSE server is checked by opening its stream, not by POSTing to it: the stream URL
  /// rejects a POST, so the Streamable HTTP probe reports every such server as not responding.
  ///
  /// Reaching the stream and being named a message endpoint is where the check stops. Completing a
  /// handshake would mean holding the stream open for the reply, and a status badge must not keep
  /// a connection per server on every refresh.
  static func probeSSE(url: URL, headers: [String: String]) async -> Status {
    var request = URLRequest(url: url, timeoutInterval: timeout)
    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
    for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }

    do {
      let (bytes, response) = try await URLSession.shared.bytes(for: request)
      guard let http = response as? HTTPURLResponse else { return .unreachable("No response") }
      if http.statusCode == 401 || http.statusCode == 403 { return .needsAuth }
      guard (200..<300).contains(http.statusCode) else {
        return .unreachable("Server returned HTTP \(http.statusCode)")
      }
      // Bounded by lines read, not only by the request timeout: that timeout measures
      // the gap between packets, and a server sending `: ping` keepalives before it
      // names an endpoint resets it forever, leaving the badge on "Checking…" and the
      // connection open for as long as the app runs.
      var linesRead = 0
      for try await line in bytes.lines {
        linesRead += 1
        if line.hasPrefix("event:"),
          line.dropFirst("event:".count).trimmingCharacters(in: .whitespaces) == "endpoint"
        {
          return .running(toolCount: -1)
        }
        if linesRead >= maxSseProbeLines { break }
      }
      return .unreachable("Server never named a message endpoint")
    } catch {
      return .unreachable("Could not reach the server")
    }
  }

  private static func post(url: URL, headers: [String: String], body: [String: Any]) async throws
    -> Data
  {
    var request = URLRequest(url: url, timeoutInterval: timeout)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("application/json, text/event-stream", forHTTPHeaderField: "Accept")
    for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    return try await URLSession.shared.data(for: request).0
  }

  /// The JSON-RPC body of a response, whether it came back as JSON or wrapped in SSE `data:` lines.
  static func payload(from data: Data) -> [String: Any]? {
    if let json = decode(data) { return json["result"] as? [String: Any] ?? json }
    guard let text = String(data: data, encoding: .utf8) else { return nil }
    for line in text.split(separator: "\n") where line.hasPrefix("data:") {
      let body = line.dropFirst("data:".count).trimmingCharacters(in: .whitespaces)
      if let json = decode(Data(body.utf8)) { return json["result"] as? [String: Any] ?? json }
    }
    return nil
  }

  /// Decode and cast in two steps: `try? JSONSerialization…() as? [String: Any]` is a double
  /// optional, and code that unwraps one level ends up subscripting through an optional.
  private static func decode(_ data: Data) -> [String: Any]? {
    guard let object = try? JSONSerialization.jsonObject(with: data) else { return nil }
    return object as? [String: Any]
  }

  // MARK: - Local command

  /// A local server is checked by resolving its command, not by running it.
  ///
  /// Launching one to shake hands would be a better signal, but it is also a side effect: `npx`
  /// installs a package on first run, and a server's own startup may touch the user's files. Doing
  /// that every time the tab is opened is not something a status badge should cost. Resolution
  /// still catches the failure that actually happens — a command that is not installed, or was
  /// removed since it was configured — and it is the same lookup the runtime will do.
  static func probeStdio(command: String, args: [String], env: [String: String]) async -> Status {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .utility).async {
        continuation.resume(returning: resolveCommand(command))
      }
    }
  }

  static func resolveCommand(_ command: String) -> Status {
    if command.contains("/") {
      return FileManager.default.isExecutableFile(atPath: command)
        ? .configured : .unreachable("\(command) is not an executable file")
    }
    let manager = FileManager.default
    for directory in searchPath(from: ProcessInfo.processInfo.environment).split(separator: ":") {
      let candidate = "\(directory)/\(command)"
      if manager.isExecutableFile(atPath: candidate) { return .configured }
    }
    return .unreachable("\(command) is not installed")
  }

  /// Homebrew and Node version managers are where `npx` and `uvx` actually live, and a bundled app
  /// inherits none of them from a login shell.
  static func searchPath(from environment: [String: String]) -> String {
    let existing = environment["PATH"]?.split(separator: ":").map(String.init) ?? []
    let extras = [
      "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
      "\(NSHomeDirectory())/.local/bin",
    ]
    var seen = Set<String>()
    return (existing + extras).filter { seen.insert($0).inserted }.joined(separator: ":")
  }

  private static var initializedNotification: [String: Any] {
    ["jsonrpc": "2.0", "method": "notifications/initialized", "params": [String: Any]()]
  }

  private static var toolsListRequest: [String: Any] {
    ["jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": [String: Any]()]
  }

  private static var initializeRequest: [String: Any] {
    [
      "jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": [
        "protocolVersion": "2025-06-18",
        "capabilities": [String: Any](),
        "clientInfo": ["name": "omi-desktop-probe", "version": "1.0.0"],
      ],
    ]
  }
}
