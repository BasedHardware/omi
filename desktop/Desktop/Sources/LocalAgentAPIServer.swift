import Foundation
import Network

enum LocalAgentAPISettings {
  static let defaultPort: UInt16 = 47778

  private static let enabledKey = "localAgentAPIEnabled"
  // Local-agent tokens currently live in app preferences so setup prompts can
  // be generated without a Keychain prompt. The API is loopback-only, but the
  // token is still readable by same-user processes; use Keychain if this scope
  // expands beyond local desktop automation.
  private static let tokenKey = "localAgentAPIToken"
  private static let portKey = "localAgentAPIPort"

  static var isEnabled: Bool {
    get { UserDefaults.standard.bool(forKey: enabledKey) }
    set { UserDefaults.standard.set(newValue, forKey: enabledKey) }
  }

  static var port: UInt16 {
    let stored = UserDefaults.standard.integer(forKey: portKey)
    guard stored > 0, let port = UInt16(exactly: stored) else {
      return defaultPort
    }
    return port
  }

  static var serverURL: String {
    "http://127.0.0.1:\(port)"
  }

  static var toolURL: String {
    "\(serverURL)/v1/local/tool"
  }

  static func storedToken() -> String? {
    let token = UserDefaults.standard.string(forKey: tokenKey) ?? ""
    return token.isEmpty ? nil : token
  }

  static func ensureToken() -> String {
    if let token = storedToken() {
      return token
    }
    let token = "omi_local_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    UserDefaults.standard.set(token, forKey: tokenKey)
    return token
  }

  static func createNewToken() -> String {
    let token = "omi_local_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    UserDefaults.standard.set(token, forKey: tokenKey)
    isEnabled = true
    LocalAgentAPIServer.shared.startIfNeeded()
    return token
  }

  static func enable() -> String {
    let token = ensureToken()
    isEnabled = true
    LocalAgentAPIServer.shared.startIfNeeded()
    return token
  }
}

private struct LocalAgentTool {
  let name: String
  let description: String
  let properties: [String: Any]
  let required: [String]
}

final class LocalAgentAPIServer {
  static let shared = LocalAgentAPIServer()
  private static let maxRequestBytes = 1024 * 1024

  private let queue = DispatchQueue(label: "com.omi.desktop.local-agent-api")
  private var listener: NWListener?

  private init() {}

  func startIfNeeded() {
    guard LocalAgentAPISettings.isEnabled else { return }
    guard listener == nil else { return }

    do {
      let parameters = NWParameters.tcp
      parameters.allowLocalEndpointReuse = true
      guard let port = NWEndpoint.Port(rawValue: LocalAgentAPISettings.port) else {
        log("LocalAgentAPIServer: invalid port \(LocalAgentAPISettings.port)")
        return
      }
      guard let loopback = IPv4Address("127.0.0.1") else {
        log("LocalAgentAPIServer: failed to resolve loopback address")
        return
      }
      parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(loopback), port: port)

      let listener = try NWListener(using: parameters)
      listener.newConnectionHandler = { [weak self] connection in
        self?.handleConnection(connection)
      }
      listener.stateUpdateHandler = { state in
        log("LocalAgentAPIServer: listener state changed to \(String(describing: state))")
      }
      listener.start(queue: queue)
      self.listener = listener
      log("LocalAgentAPIServer: listening on \(LocalAgentAPISettings.serverURL)")
    } catch {
      logError("LocalAgentAPIServer: failed to start listener", error: error)
    }
  }

  private func handleConnection(_ connection: NWConnection) {
    connection.start(queue: queue)
    receiveRequest(on: connection, buffer: Data())
  }

  private func receiveRequest(on connection: NWConnection, buffer: Data) {
    connection.receive(minimumIncompleteLength: 1, maximumLength: 128 * 1024) {
      [weak self] data, _, isComplete, error in
      guard let self else { return }

      if let error {
        self.send(self.errorResponse("receive_failed: \(error.localizedDescription)", statusCode: 500), on: connection)
        return
      }

      var accumulated = buffer
      if let data {
        accumulated.append(data)
      }

      if accumulated.count > Self.maxRequestBytes {
        self.send(self.errorResponse("request_too_large", statusCode: 413), on: connection)
        return
      }

      if let request = self.parseRequest(from: accumulated) {
        Task {
          let response = await self.route(request)
          self.send(response, on: connection)
        }
        return
      }

      if isComplete {
        self.send(self.errorResponse("incomplete_request", statusCode: 400), on: connection)
        return
      }

      self.receiveRequest(on: connection, buffer: accumulated)
    }
  }

  private func parseRequest(from data: Data) -> LocalHTTPRequest? {
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

    var headers: [String: String] = [:]
    var contentLength = 0
    for line in lines.dropFirst() {
      let pieces = line.split(separator: ":", maxSplits: 1)
      guard pieces.count == 2 else { continue }
      let key = pieces[0].trimmingCharacters(in: .whitespaces).lowercased()
      let value = pieces[1].trimmingCharacters(in: .whitespaces)
      headers[key] = value
      if key == "content-length" {
        contentLength = Int(value) ?? 0
        if contentLength > Self.maxRequestBytes {
          return nil
        }
      }
    }

    let bodyStart = headerRange.upperBound
    let expectedLength = data.distance(from: data.startIndex, to: bodyStart) + contentLength
    guard data.count >= expectedLength else {
      return nil
    }

    let body = Data(data[bodyStart..<data.index(bodyStart, offsetBy: contentLength)])
    return LocalHTTPRequest(
      method: String(requestParts[0]),
      path: String(requestParts[1]),
      headers: headers,
      body: body
    )
  }

  private func route(_ request: LocalHTTPRequest) async -> LocalHTTPResponse {
    if request.method == "GET", request.path == "/health" || request.path == "/" {
      return jsonResponse([
        "ok": true,
        "name": "omi-desktop-local",
        "api_version": 1,
        "min_cli_version": "0.3.0",
        "bundle_id": Bundle.main.bundleIdentifier ?? "unknown",
        "local_api": LocalAgentAPISettings.serverURL,
        "tool_endpoint": LocalAgentAPISettings.toolURL,
      ])
    }

    if request.method == "GET", request.path == "/v1/local/tools" {
      guard authenticate(request.headers["authorization"]) else {
        return errorResponse("invalid_or_missing_local_token", statusCode: 401)
      }
      return jsonResponse([
        "ok": true,
        "tools": Self.tools.map(toolJSON),
      ])
    }

    guard request.method == "POST", request.path == "/v1/local/tool" else {
      return errorResponse("unsupported_route", statusCode: 404)
    }

    guard authenticate(request.headers["authorization"]) else {
      return errorResponse("invalid_or_missing_local_token", statusCode: 401)
    }

    guard
      let json = try? JSONSerialization.jsonObject(with: request.body) as? [String: Any],
      let toolName = json["name"] as? String
    else {
      return errorResponse("invalid_json_body", statusCode: 400)
    }

    var arguments = json["arguments"] as? [String: Any] ?? [:]
    guard Self.tools.contains(where: { $0.name == toolName }) else {
      return errorResponse("unknown_tool: \(toolName)", statusCode: 404)
    }
    if toolName == "get_screenshot" {
      return await screenshotToolResponse(toolName: toolName, arguments: arguments)
    }
    if toolName == "execute_sql" {
      arguments["read_only"] = true
    }
    let executorToolName = toolName == "search_screen_history" ? "semantic_search" : toolName
    let result = await ChatToolExecutor.execute(
      ToolCall(name: executorToolName, arguments: arguments, thoughtSignature: nil))
    return toolResponse(name: toolName, result: result)
  }

  private func authenticate(_ authorization: String?) -> Bool {
    guard let token = LocalAgentAPISettings.storedToken(), let authorization else {
      return false
    }
    let supplied = authorization.hasPrefix("Bearer ") ? String(authorization.dropFirst(7)) : authorization
    return constantTimeEquals(supplied, token)
  }

  private func constantTimeEquals(_ lhs: String, _ rhs: String) -> Bool {
    let left = Array(lhs.utf8)
    let right = Array(rhs.utf8)
    var diff = left.count ^ right.count
    for index in 0..<max(left.count, right.count) {
      let a = index < left.count ? left[index] : 0
      let b = index < right.count ? right[index] : 0
      diff |= Int(a ^ b)
    }
    return diff == 0
  }

  private func screenshotToolResponse(toolName: String, arguments: [String: Any]) async -> LocalHTTPResponse {
    guard let screenshotID = parseInt64(arguments["screenshot_id"] ?? arguments["id"]) else {
      return errorResponse("screenshot_id is required", statusCode: 400)
    }

    do {
      guard let screenshot = try await RewindDatabase.shared.getScreenshot(id: screenshotID) else {
        return errorResponse("screenshot_not_found: \(screenshotID)", statusCode: 404)
      }

      let imageData = try await loadScreenshotDataEnsuringStorage(for: screenshot)
      let metadata = screenshotMetadata(screenshot, imageByteCount: imageData.count)
      return jsonResponse([
        "ok": true,
        "name": toolName,
        "content_type": "image/jpeg",
        "metadata": metadata,
        "image_base64": imageData.base64EncodedString(),
      ])
    } catch {
      logError("LocalAgentAPIServer: get_screenshot failed", error: error)
      return errorResponse("failed_to_load_screenshot: \(error.localizedDescription)", statusCode: 500)
    }
  }

  private func loadScreenshotDataEnsuringStorage(for screenshot: Screenshot) async throws -> Data {
    do {
      return try await RewindStorage.shared.loadScreenshotData(for: screenshot)
    } catch {
      try await RewindStorage.shared.initialize()
      return try await RewindStorage.shared.loadScreenshotData(for: screenshot)
    }
  }

  private func parseInt64(_ value: Any?) -> Int64? {
    if let value = value as? Int64 { return value }
    if let value = value as? Int { return Int64(value) }
    if let value = value as? Double { return Int64(value) }
    if let value = value as? String { return Int64(value.trimmingCharacters(in: .whitespacesAndNewlines)) }
    return nil
  }

  private func screenshotMetadata(_ screenshot: Screenshot, imageByteCount: Int) -> [String: Any] {
    let formatter = ISO8601DateFormatter()
    return [
      "screenshot_id": screenshot.id ?? NSNull(),
      "timestamp": formatter.string(from: screenshot.timestamp),
      "app_name": screenshot.appName,
      "window_title": screenshot.windowTitle ?? NSNull(),
      "has_ocr": !(screenshot.ocrText ?? "").isEmpty,
      "is_indexed": screenshot.isIndexed,
      "image_mime_type": "image/jpeg",
      "image_bytes": imageByteCount,
      "ocr_preview": String((screenshot.ocrText ?? "").prefix(600)),
    ]
  }

  private static let tools: [LocalAgentTool] = [
    LocalAgentTool(
      name: "get_local_status",
      description:
        "Report whether local Omi Desktop context is available, including screen-history counts, indexed screenshot counts, and latest capture time. Call this before local screen-history or SQL work.",
      properties: [:],
      required: []
    ),
    LocalAgentTool(
      name: "execute_sql",
      description:
        "Run read-only SQL on the local Omi Desktop SQLite database. Use SELECT or WITH queries for structured questions about screenshots, transcriptions, tasks, memories, indexed files, goals, and activity.",
      properties: ["query": ["type": "string", "description": "SQL query to execute against the local Omi database"]],
      required: ["query"]
    ),
    LocalAgentTool(
      name: "search_screen_history",
      description:
        "Search local Rewind screen history using OCR and semantic similarity. Use for fuzzy questions about what the user saw or worked on. Results include screenshot IDs that can be opened with get_screenshot.",
      properties: [
        "query": ["type": "string", "description": "Natural language query"],
        "days": ["type": "number", "description": "Days to search back; default 7"],
        "app_filter": ["type": "string", "description": "Optional app name filter"],
      ],
      required: ["query"]
    ),
    LocalAgentTool(
      name: "semantic_search",
      description:
        "Compatibility alias for search_screen_history.",
      properties: [
        "query": ["type": "string", "description": "Natural language query"],
        "days": ["type": "number", "description": "Days to search back; default 7"],
        "app_filter": ["type": "string", "description": "Optional app name filter"],
      ],
      required: ["query"]
    ),
    LocalAgentTool(
      name: "get_screenshot",
      description:
        "Fetch a local Rewind screenshot image by screenshot_id. Use screenshot IDs returned by search_screen_history or execute_sql.",
      properties: [
        "screenshot_id": ["type": "number", "description": "Screenshot ID from search_screen_history or the screenshots table"]
      ],
      required: ["screenshot_id"]
    ),
    LocalAgentTool(
      name: "get_daily_recap",
      description: "Get a formatted local activity recap for today, yesterday, or a recent range.",
      properties: ["days_ago": ["type": "number", "description": "0=today, 1=yesterday, 7=past week"]],
      required: []
    ),
    LocalAgentTool(
      name: "search_tasks",
      description: "Semantic search over local Omi tasks and staged tasks.",
      properties: [
        "query": ["type": "string", "description": "Task search query"],
        "include_completed": ["type": "boolean", "description": "Include completed tasks"],
      ],
      required: ["query"]
    ),
    LocalAgentTool(
      name: "complete_task",
      description: "Mark a task complete. This is idempotent; already-completed tasks stay completed. Find the task id first with execute_sql or search_tasks.",
      properties: ["task_id": ["type": "string", "description": "Task backendId"]],
      required: ["task_id"]
    ),
    LocalAgentTool(
      name: "delete_task",
      description: "Delete a task. Find the task id first with execute_sql or search_tasks.",
      properties: ["task_id": ["type": "string", "description": "Task backendId"]],
      required: ["task_id"]
    ),
  ]

  private func toolJSON(_ tool: LocalAgentTool) -> [String: Any] {
    [
      "name": tool.name,
      "description": tool.description,
      "annotations": [
        "readOnlyHint": !["complete_task", "delete_task"].contains(tool.name),
        "destructiveHint": tool.name == "delete_task",
        "openWorldHint": false,
      ],
      "inputSchema": [
        "type": "object",
        "properties": tool.properties,
        "required": tool.required,
      ],
    ]
  }

  private func toolResponse(name: String, result: String) -> LocalHTTPResponse {
    if result.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("Error:") {
      return errorResponse(result, statusCode: 400)
    }
    return jsonResponse([
      "ok": true,
      "name": name,
      "content_type": "text/plain",
      "result": result,
    ])
  }

  private func jsonResponse(_ payload: Any, statusCode: Int = 200) -> LocalHTTPResponse {
    let body: Data
    do {
      body = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    } catch {
      body = Data("{\"error\":\"encode_failed\"}".utf8)
    }
    return LocalHTTPResponse(
      statusCode: statusCode,
      headers: ["Content-Type": "application/json"],
      body: body
    )
  }

  private func errorResponse(_ message: String, statusCode: Int) -> LocalHTTPResponse {
    jsonResponse(["ok": false, "error": message], statusCode: statusCode)
  }

  private func send(_ response: LocalHTTPResponse, on connection: NWConnection) {
    let statusText: String
    switch response.statusCode {
    case 200: statusText = "OK"
    case 202: statusText = "Accepted"
    case 400: statusText = "Bad Request"
    case 401: statusText = "Unauthorized"
    case 404: statusText = "Not Found"
    case 413: statusText = "Payload Too Large"
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
    connection.send(content: data, completion: .contentProcessed { _ in connection.cancel() })
  }
}

private struct LocalHTTPRequest {
  let method: String
  let path: String
  let headers: [String: String]
  let body: Data
}

private struct LocalHTTPResponse {
  let statusCode: Int
  let headers: [String: String]
  let body: Data
}
