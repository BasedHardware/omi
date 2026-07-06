import Foundation
import Network

enum LocalAgentAPISettings {
  static let defaultPort: UInt16 = 47778

  private static let enabledKey = "localAgentAPIEnabled"
  private static let tokenKey = "localAgentAPIToken"
  private static let tokenKeychainService = "com.omi.desktop.local-agent-api"
  private static let tokenKeychainAccount = "local-agent-api-token"
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
    if let token = DesktopKeychainStore.string(service: tokenKeychainService, account: tokenKeychainAccount) {
      return token
    }
    let token = UserDefaults.standard.string(forKey: tokenKey) ?? ""
    guard !token.isEmpty else { return nil }
    if DesktopKeychainStore.setString(token, service: tokenKeychainService, account: tokenKeychainAccount) {
      UserDefaults.standard.removeObject(forKey: tokenKey)
      log("LocalAgentAPISettings: migrated token from UserDefaults to Keychain")
      return token
    }
    log("LocalAgentAPISettings: failed to migrate token to Keychain")
    return nil
  }

  static func ensureToken() -> String {
    if let token = storedToken() {
      return token
    }
    let token = "omi_local_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    guard DesktopKeychainStore.setString(token, service: tokenKeychainService, account: tokenKeychainAccount) else {
      log("LocalAgentAPISettings: failed to save token to Keychain")
      return ""
    }
    UserDefaults.standard.removeObject(forKey: tokenKey)
    return token
  }

  static func createNewToken() -> String {
    let token = "omi_local_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    guard DesktopKeychainStore.setString(token, service: tokenKeychainService, account: tokenKeychainAccount) else {
      isEnabled = false
      log("LocalAgentAPISettings: failed to save replacement token to Keychain")
      return ""
    }
    UserDefaults.standard.removeObject(forKey: tokenKey)
    isEnabled = true
    LocalAgentAPIServer.shared.startIfNeeded()
    return token
  }

  static func enable() -> String {
    let token = ensureToken()
    guard !token.isEmpty else {
      isEnabled = false
      return ""
    }
    isEnabled = true
    LocalAgentAPIServer.shared.startIfNeeded()
    return token
  }
}

struct LocalAgentTool {
  let name: String
  let description: String
  let properties: [String: Any]
  let required: [String]
  let annotations: [String: Any]
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
    guard acceptsLoopbackHostAndOrigin(request.headers) else {
      return errorResponse("invalid_host_or_origin", statusCode: 403)
    }

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
    if toolName == "get_work_context" {
      return await workContextResponse(arguments: arguments)
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

  private func acceptsLoopbackHostAndOrigin(_ headers: [String: String]) -> Bool {
    if let host = headers["host"], !isAllowedLoopbackHost(host) {
      return false
    }
    if let origin = headers["origin"], !origin.isEmpty {
      guard let url = URL(string: origin), let host = url.host, let port = url.port else {
        return false
      }
      guard (url.scheme == "http" || url.scheme == "https"), port == Int(LocalAgentAPISettings.port) else {
        return false
      }
      guard host == "127.0.0.1" || host == "localhost" || host == "[::1]" || host == "::1" else {
        return false
      }
    }
    return true
  }

  private func isAllowedLoopbackHost(_ hostHeader: String) -> Bool {
    let value = hostHeader.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let allowed = [
      "127.0.0.1:\(LocalAgentAPISettings.port)",
      "localhost:\(LocalAgentAPISettings.port)",
      "[::1]:\(LocalAgentAPISettings.port)",
    ]
    return allowed.contains(value)
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

  /// One-call "work context" for agents: the current screen + a compressed
  /// timeline of the last N minutes of on-screen activity. Read-only; composes
  /// existing Rewind data so agents stop asking the user to screenshot/re-explain.
  private func workContextResponse(arguments: [String: Any]) async -> LocalHTTPResponse {
    let minutes = max(1, min(120, Int(parseInt64(arguments["minutes"]) ?? 10)))
    let now = Date()
    let start = now.addingTimeInterval(-Double(minutes) * 60)
    let formatter = ISO8601DateFormatter()

    // 1) Screen now — most recent frame whose pixels are currently loadable.
    //    Frames still buffering in the unflushed active video chunk can't be
    //    decoded yet; skip them up front so we don't repeatedly attempt (and
    //    fail) a load — each failed load re-inits storage, a real latency spike
    //    since the newest frames are commonly in the active chunk.
    var screenNow: [String: Any] = ["available": false]
    let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
    if let recent = try? await RewindDatabase.shared.getRecentScreenshots(limit: 25) {
      for shot in recent {
        guard let sid = shot.id else { continue }
        if shot.usesVideoStorage, let chunk = shot.videoChunkPath, chunk == activeChunk {
          continue  // pending: still in the active, unflushed chunk
        }
        if let data = try? await loadScreenshotDataEnsuringStorage(for: shot) {
          screenNow = [
            "available": true,
            "screenshot_id": sid,
            "timestamp": formatter.string(from: shot.timestamp),
            "app_name": shot.appName,
            "window_title": shot.windowTitle ?? NSNull(),
            "ocr_preview": String((shot.ocrText ?? "").prefix(800)),
            "image_bytes": data.count,
            "note":
              "Latest available finalized frame (may be up to ~1 min old, and can predate window_minutes). Call get_screenshot with this screenshot_id to SEE the full-screen image.",
          ]
          break
        }
      }
    }

    // 2) Recent activity — sampled frames, consecutive (app, window) runs collapsed.
    var timeline: [[String: Any]] = []
    let calendar = Calendar.current
    func clock(_ date: Date) -> String {
      let c = calendar.dateComponents([.hour, .minute], from: date)
      return String(format: "%02d:%02d", c.hour ?? 0, c.minute ?? 0)
    }
    if let shots = try? await RewindDatabase.shared.getScreenshotsSampled(
      from: start, to: now, targetCount: 80)
    {
      var runs: [(app: String, window: String, start: String, end: String, frames: Int)] = []
      for shot in shots {
        let window = Self.normalizeWindow(shot.windowTitle ?? "")
        let cl = clock(shot.timestamp)
        if var last = runs.last, last.app == shot.appName, last.window == window {
          last.end = cl
          last.frames += 1
          runs[runs.count - 1] = last
        } else {
          runs.append((shot.appName, window, cl, cl, 1))
        }
      }
      for run in runs.reversed().prefix(20) {
        timeline.append([
          "start": run.start, "end": run.end, "app": run.app,
          "window": run.window, "frames": run.frames,
        ])
      }
    }

    return jsonResponse([
      "ok": true,
      "name": "get_work_context",
      "window_minutes": minutes,
      "screen_now": screenNow,
      "timeline": timeline,
      "memories_hint":
        "For the user's operating principles/preferences, also call search_memories (omi-memory).",
      "guidance":
        "This is the user's recent on-screen activity. Act on it directly instead of asking them to screenshot or re-explain what they were doing.",
    ])
  }

  /// Strip Unicode format/control marks (bidi isolates apps like Telegram inject),
  /// trailing message counters "(245236)", and leading unread badges "(2) ", so
  /// near-identical consecutive window titles collapse into one timeline run.
  private static func normalizeWindow(_ raw: String) -> String {
    var w = String(
      raw.unicodeScalars.filter { scalar in
        let category = scalar.properties.generalCategory
        return category != .format && category != .control
      })
    if let r = w.range(of: #"\s*\(\d{2,}\)\s*$"#, options: .regularExpression) {
      w.removeSubrange(r)
    }
    if let r = w.range(of: #"^\(\d+\)\s*"#, options: .regularExpression) {
      w.removeSubrange(r)
    }
    return w.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func screenshotToolResponse(toolName: String, arguments: [String: Any]) async -> LocalHTTPResponse {
    guard let screenshotID = parseInt64(arguments["screenshot_id"] ?? arguments["id"]) else {
      return errorResponse("screenshot_id is required", statusCode: 400)
    }

    let screenshot: Screenshot?
    do {
      screenshot = try await RewindDatabase.shared.getScreenshot(id: screenshotID)
    } catch {
      logError("LocalAgentAPIServer: get_screenshot lookup failed", error: error)
      return errorResponse("failed_to_load_screenshot: \(error.localizedDescription)", statusCode: 500)
    }
    guard let screenshot else {
      return errorResponse("screenshot_not_found: \(screenshotID)", statusCode: 404)
    }

    do {
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
      // The image row exists but its pixels could not be loaded. Rather than a
      // generic 500, classify why so agents get an actionable reason + hint.
      return await screenshotUnavailableResponse(screenshot, screenshotID: screenshotID, error: error)
    }
  }

  /// Map a screenshot load failure to a clear, structured response. Recent
  /// screenshots commonly sit in the active (unfinalized) video chunk, which
  /// cannot be decoded yet; other rows may be orphaned or have a file that
  /// retention already removed. All of these previously surfaced as an opaque
  /// `failed_to_load_screenshot: Screenshot not found` 500.
  private func screenshotUnavailableResponse(
    _ screenshot: Screenshot,
    screenshotID: Int64,
    error: Error
  ) async -> LocalHTTPResponse {
    let activeChunk = await VideoChunkEncoder.shared.currentChunkPath

    let code: String
    let reason: String
    let hint: String

    if let rewindError = error as? RewindError, case .corruptedVideoChunk = rewindError {
      code = "screenshot_chunk_corrupted"
      reason = "The video chunk backing this screenshot is corrupted and cannot be decoded."
      hint = "Pick a different screenshot_id; this frame's pixels are unrecoverable."
    } else if screenshot.usesVideoStorage, let chunk = screenshot.videoChunkPath, chunk == activeChunk {
      code = "screenshot_pending"
      reason = "The frame is in the active recording segment that has not been flushed to disk yet."
      hint = "Retry in ~60s, or choose an older screenshot_id whose video chunk is already finalized."
    } else if !screenshot.usesVideoStorage, (screenshot.imagePath ?? "").isEmpty {
      code = "screenshot_image_unavailable"
      reason = "This screenshot row has no stored image (orphaned capture with no video chunk or image file)."
      hint = "Pick a different screenshot_id from a recent search_screen_history result."
    } else if error as? RewindError != nil {
      code = "screenshot_file_missing"
      reason = "The image data for this screenshot is no longer on disk (likely removed by retention/cleanup)."
      hint = "Pick a more recent screenshot_id whose pixels are still retained."
    } else {
      logError("LocalAgentAPIServer: get_screenshot failed", error: error)
      return errorResponse("failed_to_load_screenshot: \(error.localizedDescription)", statusCode: 500)
    }

    return jsonResponse([
      "ok": false,
      "error": code,
      "reason": reason,
      "hint": hint,
      "screenshot_id": screenshotID,
    ], statusCode: 422)
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

  private static let tools: [LocalAgentTool] = OmiToolManifest.localAgentAPITools

  private func toolJSON(_ tool: LocalAgentTool) -> [String: Any] {
    [
      "name": tool.name,
      "description": tool.description,
      "annotations": tool.annotations,
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
    case 422: statusText = "Unprocessable Entity"
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
