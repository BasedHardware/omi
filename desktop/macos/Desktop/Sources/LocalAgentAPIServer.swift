import CoreGraphics
import Foundation
import Network

enum LocalAgentAPIError: LocalizedError {
  case tokenStorageUnavailable

  var errorDescription: String? {
    switch self {
    case .tokenStorageUnavailable:
      return "Couldn't save the local agent token securely."
    }
  }
}

enum LocalAgentAPISettings {
  static let defaultPort: UInt16 = 47778

  private static let enabledKey = "localAgentAPIEnabled"
  private static let tokenKey = "localAgentAPIToken"
  private static let tokenKeychainAccount = "local-agent-api-token"
  private static let portKey = "localAgentAPIPort"
  /// Team+bundle scoped so local Apple Development / named bundles cannot poison
  /// each other or the notarized item. Never query the unscoped legacy service.
  private static var tokenKeychainService: String {
    DesktopKeychainStore.scopedService(DesktopKeychainStore.legacyLocalAgentTokenService)
  }

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
    if let token = DesktopKeychainStore.string(
      service: tokenKeychainService,
      account: tokenKeychainAccount
    ) {
      return token
    }
    let token = UserDefaults.standard.string(forKey: tokenKey) ?? ""
    guard !token.isEmpty else { return nil }
    if DesktopKeychainStore.setString(token, service: tokenKeychainService, account: tokenKeychainAccount) {
      UserDefaults.standard.removeObject(forKey: tokenKey)
      log("LocalAgentAPISettings: migrated token from UserDefaults to Keychain")
      return token
    }
    UserDefaults.standard.removeObject(forKey: tokenKey)
    log("LocalAgentAPISettings: failed to migrate token to Keychain")
    return nil
  }

  static func ensureToken() throws -> String {
    if let token = storedToken() {
      return token
    }
    // No readable scoped/UserDefaults token. Mint a fresh one into the scoped
    // service. We deliberately do NOT read the unscoped legacy Keychain item
    // (that query can show the login-keychain password dialog). Callers that
    // still hold the pre-scoping token must re-copy the new token from Settings.
    let token = "omi_local_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    guard DesktopKeychainStore.setString(token, service: tokenKeychainService, account: tokenKeychainAccount) else {
      log("LocalAgentAPISettings: failed to save token to Keychain")
      throw LocalAgentAPIError.tokenStorageUnavailable
    }
    UserDefaults.standard.removeObject(forKey: tokenKey)
    log("LocalAgentAPISettings: minted replacement local-agent token into scoped Keychain (re-copy token for clients)")
    return token
  }

  static func createNewToken() throws -> String {
    let token = "omi_local_\(UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased())"
    guard DesktopKeychainStore.setString(token, service: tokenKeychainService, account: tokenKeychainAccount) else {
      isEnabled = false
      log("LocalAgentAPISettings: failed to save replacement token to Keychain")
      throw LocalAgentAPIError.tokenStorageUnavailable
    }
    UserDefaults.standard.removeObject(forKey: tokenKey)
    isEnabled = true
    LocalAgentAPIServer.shared.startIfNeeded()
    return token
  }

  static func enable() throws -> String {
    let token = try ensureToken()
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

/// Shared parsing for the `Content-Length` header of the loopback HTTP servers
/// (LocalAgentAPIServer + DesktopAutomationBridge). Both slice the body with
/// `data.index(bodyStart, offsetBy: contentLength)`, which traps on a negative
/// length, and add `contentLength` to a distance, which overflows on a huge one.
/// Since both servers parse before authenticating, a malformed length from any
/// local process would otherwise crash the whole app. Fail closed instead.
enum LoopbackHTTPParsing {
  /// Returns the validated body length, or `nil` if the header value is malformed,
  /// negative, or exceeds `maxBytes` (caller should reject the request).
  static func parseContentLength(_ value: String, maxBytes: Int) -> Int? {
    guard let parsed = Int(value), parsed >= 0, parsed <= maxBytes else {
      return nil
    }
    return parsed
  }
}

final class LocalAgentAPIServer {
  static let shared = LocalAgentAPIServer()
  private static let maxRequestBytes = 1024 * 1024

  private let queue = DispatchQueue(label: "com.omi.desktop.local-agent-api")
  private var listener: NWListener?

  private init() {}

  func startIfNeeded() {
    guard LocalAgentAPISettings.isEnabled else { return }
    // If the feature was enabled before team+bundle scoping, the old Keychain
    // token is intentionally unread (to avoid password prompts). Mint a fresh
    // scoped token so the server can authenticate again; clients must re-copy it.
    do {
      _ = try LocalAgentAPISettings.ensureToken()
    } catch {
      log("LocalAgentAPIServer: cannot start — token storage unavailable (\(error.localizedDescription))")
      LocalAgentAPISettings.isEnabled = false
      return
    }
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
        // Reject a negative/over-large length before it reaches the body-slice
        // range below (which would trap on an unauthenticated request).
        guard let parsed = LoopbackHTTPParsing.parseContentLength(value, maxBytes: Self.maxRequestBytes)
        else {
          return nil
        }
        contentLength = parsed
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
      guard url.scheme == "http" || url.scheme == "https", port == Int(LocalAgentAPISettings.port) else {
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
    let payload = await ScreenContextWorkContextBuilder.payload(arguments: arguments)
    let telemetry = ScreenContextWorkContextBuilder.telemetryValues(from: payload)
    ScreenContextToolTelemetry.trackToolResult(
      toolName: "get_work_context",
      context: ScreenContextTelemetryContext(surface: "local_api"),
      ok: telemetry.ok && telemetry.screenNowAvailable == true,
      failureCode: telemetry.failureCode,
      screenNowAvailable: telemetry.screenNowAvailable,
      timelineCount: telemetry.timelineCount,
      latestCaptureAgeSeconds: telemetry.latestCaptureAgeSeconds,
      hasOCRPreview: telemetry.hasOCRPreview,
      imageBytes: telemetry.imageBytes,
      permissionTCCGranted: CGPreflightScreenCaptureAccess()
    )
    return jsonResponse(payload)
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
      ScreenContextToolTelemetry.trackToolResult(
        toolName: "get_screenshot",
        context: ScreenContextTelemetryContext(surface: "local_api"),
        ok: false,
        failureCode: .databaseUnavailable,
        permissionTCCGranted: CGPreflightScreenCaptureAccess()
      )
      return errorResponse("failed_to_load_screenshot: \(error.localizedDescription)", statusCode: 500)
    }
    guard let screenshot else {
      ScreenContextToolTelemetry.trackToolResult(
        toolName: "get_screenshot",
        context: ScreenContextTelemetryContext(surface: "local_api"),
        ok: false,
        failureCode: .imageUnavailable,
        permissionTCCGranted: CGPreflightScreenCaptureAccess()
      )
      return errorResponse("screenshot_not_found: \(screenshotID)", statusCode: 404)
    }

    do {
      let imageData = try await loadScreenshotDataEnsuringStorage(for: screenshot)
      let metadata = screenshotMetadata(screenshot, imageByteCount: imageData.count)
      ScreenContextToolTelemetry.trackToolResult(
        toolName: "get_screenshot",
        context: ScreenContextTelemetryContext(surface: "local_api"),
        ok: true,
        imageBytes: imageData.count,
        permissionTCCGranted: CGPreflightScreenCaptureAccess()
      )
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

    if let classification = ScreenContextToolTelemetry.classifyScreenshotUnavailable(
      screenshot: screenshot,
      activeChunk: activeChunk,
      error: error
    ) {
      code = classification.code.rawValue
      reason = classification.reason
      hint = classification.hint
    } else {
      logError("LocalAgentAPIServer: get_screenshot failed", error: error)
      ScreenContextToolTelemetry.trackToolResult(
        toolName: "get_screenshot",
        context: ScreenContextTelemetryContext(surface: "local_api"),
        ok: false,
        failureCode: .unknown,
        permissionTCCGranted: CGPreflightScreenCaptureAccess()
      )
      return errorResponse("failed_to_load_screenshot: \(error.localizedDescription)", statusCode: 500)
    }

    ScreenContextToolTelemetry.trackToolResult(
      toolName: "get_screenshot",
      context: ScreenContextTelemetryContext(surface: "local_api"),
      ok: false,
      failureCode: ScreenContextFailureCode(rawValue: code) ?? .unknown,
      permissionTCCGranted: CGPreflightScreenCaptureAccess()
    )
    return jsonResponse(
      [
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
