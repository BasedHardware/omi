import Foundation
import Network

enum LocalAgentMCPSettings {
  static let defaultPort: UInt16 = 47778

  private static let enabledKey = "localAgentMCPEnabled"
  private static let tokenKey = "localAgentMCPToken"
  private static let portKey = "localAgentMCPPort"

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
    "http://127.0.0.1:\(port)/mcp"
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

  static func enable() -> String {
    let token = ensureToken()
    isEnabled = true
    LocalAgentMCPServer.shared.startIfNeeded()
    return token
  }
}

private struct LocalMCPTool {
  let name: String
  let description: String
  let properties: [String: Any]
  let required: [String]
}

final class LocalAgentMCPServer {
  static let shared = LocalAgentMCPServer()

  private let queue = DispatchQueue(label: "com.omi.desktop.local-agent-mcp")
  private var listener: NWListener?

  private init() {}

  func startIfNeeded() {
    guard LocalAgentMCPSettings.isEnabled else { return }
    guard listener == nil else { return }

    do {
      let parameters = NWParameters.tcp
      parameters.allowLocalEndpointReuse = true
      guard let port = NWEndpoint.Port(rawValue: LocalAgentMCPSettings.port) else {
        log("LocalAgentMCPServer: invalid port \(LocalAgentMCPSettings.port)")
        return
      }

      let listener = try NWListener(using: parameters, on: port)
      listener.newConnectionHandler = { [weak self] connection in
        self?.handleConnection(connection)
      }
      listener.stateUpdateHandler = { state in
        log("LocalAgentMCPServer: listener state changed to \(String(describing: state))")
      }
      listener.start(queue: queue)
      self.listener = listener
      log("LocalAgentMCPServer: listening on \(LocalAgentMCPSettings.serverURL)")
    } catch {
      logError("LocalAgentMCPServer: failed to start listener", error: error)
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
        "mcp": LocalAgentMCPSettings.serverURL,
      ])
    }

    guard request.method == "POST", request.path == "/mcp" || request.path == "/" else {
      return errorResponse("unsupported_route", statusCode: 404)
    }

    guard authenticate(request.headers["authorization"]) else {
      return errorResponse("invalid_or_missing_local_token", statusCode: 401)
    }

    guard
      let json = try? JSONSerialization.jsonObject(with: request.body) as? [String: Any],
      let method = json["method"] as? String
    else {
      return rpcError(id: nil, code: -32700, message: "Parse error")
    }

    let id = json["id"]
    let params = json["params"] as? [String: Any] ?? [:]

    switch method {
    case "initialize":
      return rpcResult(id: id, result: [
        "protocolVersion": "2025-03-26",
        "capabilities": ["tools": [:]],
        "serverInfo": ["name": "omi-desktop-local", "version": "1.0.0"],
      ])

    case "notifications/initialized":
      return emptyResponse()

    case "tools/list":
      return rpcResult(id: id, result: ["tools": Self.tools.map(toolJSON)])

    case "tools/call":
      guard let toolName = params["name"] as? String else {
        return rpcError(id: id, code: -32602, message: "Missing tool name")
      }
      let arguments = params["arguments"] as? [String: Any] ?? [:]
      guard Self.tools.contains(where: { $0.name == toolName }) else {
        return rpcError(id: id, code: -32601, message: "Unknown tool: \(toolName)")
      }
      let result = await ChatToolExecutor.execute(
        ToolCall(name: toolName, arguments: arguments, thoughtSignature: nil))
      return rpcResult(id: id, result: ["content": [["type": "text", "text": result]]])

    default:
      return rpcError(id: id, code: -32601, message: "Method not found: \(method)")
    }
  }

  private func authenticate(_ authorization: String?) -> Bool {
    guard let token = LocalAgentMCPSettings.storedToken(), let authorization else {
      return false
    }
    if authorization == token {
      return true
    }
    if authorization == "Bearer \(token)" {
      return true
    }
    return false
  }

  private static let tools: [LocalMCPTool] = [
    LocalMCPTool(
      name: "execute_sql",
      description:
        "Run SQL on the local Omi Desktop SQLite database. Use for structured questions about screenshots, transcriptions, tasks, memories, indexed files, goals, and activity. SELECT is safest; destructive schema statements are blocked.",
      properties: ["query": ["type": "string", "description": "SQL query to execute against the local Omi database"]],
      required: ["query"]
    ),
    LocalMCPTool(
      name: "semantic_search",
      description:
        "Vector similarity search over local Rewind screen history. Use for fuzzy questions about what the user saw or worked on.",
      properties: [
        "query": ["type": "string", "description": "Natural language query"],
        "days": ["type": "number", "description": "Days to search back; default 7"],
        "app_filter": ["type": "string", "description": "Optional app name filter"],
      ],
      required: ["query"]
    ),
    LocalMCPTool(
      name: "get_daily_recap",
      description: "Get a formatted local activity recap for today, yesterday, or a recent range.",
      properties: ["days_ago": ["type": "number", "description": "0=today, 1=yesterday, 7=past week"]],
      required: []
    ),
    LocalMCPTool(
      name: "search_tasks",
      description: "Semantic search over local Omi tasks and staged tasks.",
      properties: [
        "query": ["type": "string", "description": "Task search query"],
        "include_completed": ["type": "boolean", "description": "Include completed tasks"],
      ],
      required: ["query"]
    ),
    LocalMCPTool(
      name: "complete_task",
      description: "Toggle a task completion state. Find the task id first with execute_sql or search_tasks.",
      properties: ["task_id": ["type": "string", "description": "Task backendId"]],
      required: ["task_id"]
    ),
    LocalMCPTool(
      name: "delete_task",
      description: "Delete a task. Find the task id first with execute_sql or search_tasks.",
      properties: ["task_id": ["type": "string", "description": "Task backendId"]],
      required: ["task_id"]
    ),
  ]

  private func toolJSON(_ tool: LocalMCPTool) -> [String: Any] {
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

  private func rpcResult(id: Any?, result: Any) -> LocalHTTPResponse {
    jsonResponse(["jsonrpc": "2.0", "id": id ?? NSNull(), "result": result])
  }

  private func rpcError(id: Any?, code: Int, message: String) -> LocalHTTPResponse {
    jsonResponse([
      "jsonrpc": "2.0",
      "id": id ?? NSNull(),
      "error": ["code": code, "message": message],
    ])
  }

  private func emptyResponse() -> LocalHTTPResponse {
    LocalHTTPResponse(statusCode: 202, headers: ["Content-Type": "application/json"], body: Data())
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
