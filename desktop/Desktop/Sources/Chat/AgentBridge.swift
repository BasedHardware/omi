import Foundation

/// Manages a long-lived Node.js subprocess running the agent runtime.
/// Supports multiple harness modes: pi-mono (default, routed through api.omi.me)
/// and Claude Account (user's own OAuth credentials via ACP).
/// Communication uses JSON lines over stdin/stdout pipes.
actor AgentBridge {

  // MARK: - Types

  /// Result from a query
  struct QueryResult {
    let text: String
    let costUsd: Double
    let sessionId: String
    let inputTokens: Int
    let outputTokens: Int
    let cacheReadTokens: Int
    let cacheWriteTokens: Int
  }

  /// Callback for streaming text deltas
  typealias TextDeltaHandler = @Sendable (String) -> Void

  /// Callback for OMI tool calls that need Swift execution
  typealias ToolCallHandler = @Sendable (String, String, [String: Any]) async -> String

  /// Callback for tool activity events (name, status, toolUseId?, input?)
  typealias ToolActivityHandler = @Sendable (String, String, String?, [String: Any]?) -> Void

  /// Callback for thinking text deltas
  typealias ThinkingDeltaHandler = @Sendable (String) -> Void

  /// Callback for tool result display (toolUseId, name, output)
  typealias ToolResultDisplayHandler = @Sendable (String, String, String) -> Void

  /// Callback for auth required events (methods array, optional auth URL)
  typealias AuthRequiredHandler = @Sendable ([[String: Any]], String?) -> Void

  /// Callback for auth success
  typealias AuthSuccessHandler = @Sendable () -> Void

  /// Inbound message types (Bridge → Swift, read from stdout)
  private enum InboundMessage {
    case `init`(sessionId: String)
    case textDelta(text: String)
    case thinkingDelta(text: String)
    case toolUse(callId: String, name: String, input: [String: Any])
    case toolActivity(name: String, status: String, toolUseId: String?, input: [String: Any]?)
    case toolResultDisplay(toolUseId: String, name: String, output: String)
    case result(
      text: String, sessionId: String, costUsd: Double?, inputTokens: Int, outputTokens: Int,
      cacheReadTokens: Int, cacheWriteTokens: Int)
    case error(message: String)
    case authRequired(methods: [[String: Any]], authUrl: String?)
    case authSuccess
  }

  // MARK: - Configuration

  /// Which harness to use: "acp" (Claude OAuth) or "piMono" (Omi AI via Firebase token)
  let harnessMode: String

  /// Persistent auth handler called whenever auth_required arrives (even outside query)
  var onAuthRequiredGlobal: AuthRequiredHandler?
  /// Persistent auth success handler called whenever auth_success arrives (even outside query)
  var onAuthSuccessGlobal: AuthSuccessHandler?

  func setGlobalAuthHandlers(
    onAuthRequired: AuthRequiredHandler?,
    onAuthSuccess: AuthSuccessHandler?
  ) {
    self.onAuthRequiredGlobal = onAuthRequired
    self.onAuthSuccessGlobal = onAuthSuccess
  }

  init(harnessMode: String = "piMono") {
    self.harnessMode = harnessMode
  }

  // MARK: - State

  private var process: Process?
  private var stdinPipe: Pipe?
  private var stdoutPipe: Pipe?
  private var stderrPipe: Pipe?
  private var isRunning = false
  private var readTask: Task<Void, Never>?
  /// Incremented each time start() is called; stale termination handlers check this
  private var processGeneration: UInt64 = 0

  /// Pending messages from the bridge
  private var pendingMessages: [InboundMessage] = []
  private var messageContinuation: CheckedContinuation<InboundMessage, Error>?
  private var messageGeneration: UInt64 = 0
  /// Set when stderr indicates OOM so handleTermination can throw the right error
  private var lastExitWasOOM = false
  /// Set when interrupt() is called so query() can skip remaining tool calls
  private var isInterrupted = false
  /// Timer for periodic Firebase token refresh (piMono mode)
  private var tokenRefreshTask: Task<Void, Never>?

  /// Whether the bridge subprocess is alive and ready
  var isAlive: Bool { isRunning }

  // MARK: - Lifecycle

  /// Start the Node.js agent bridge process
  func start() async throws {
    guard !isRunning else { return }

    // Clean up any leftover state from a previous crashed process
    readTask?.cancel()
    readTask = nil
    process = nil
    closePipes()
    pendingMessages.removeAll()
    messageContinuation = nil
    lastExitWasOOM = false

    let nodePath = findNodeBinary()
    guard let nodePath else {
      throw BridgeError.nodeNotFound
    }

    let bridgePath = findBridgeScript()
    guard let bridgePath else {
      throw BridgeError.bridgeScriptNotFound
    }

    let nodeExists = FileManager.default.isExecutableFile(atPath: nodePath)
    let bridgeExists = FileManager.default.fileExists(atPath: bridgePath)
    let bridgeDir = (bridgePath as NSString).deletingLastPathComponent
    let pkgJsonPath = ((bridgeDir as NSString).deletingLastPathComponent as NSString)
      .appendingPathComponent("package.json")
    let pkgJsonExists = FileManager.default.fileExists(atPath: pkgJsonPath)
    log(
      "AgentBridge: starting with node=\(nodePath) (exists=\(nodeExists)), bridge=\(bridgePath) (exists=\(bridgeExists)), package.json=\(pkgJsonExists)"
    )

    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: nodePath)
    proc.arguments = ["--max-old-space-size=256", "--max-semi-space-size=16", bridgePath]

    // Build environment — ANTHROPIC_API_KEY is never passed to subprocesses (issue #6594).
    // ACP mode uses user's own Claude OAuth; piMono mode uses Firebase token.
    var env = ProcessInfo.processInfo.environment
    env["NODE_NO_WARNINGS"] = "1"
    env.removeValue(forKey: "ANTHROPIC_API_KEY")
    env.removeValue(forKey: "CLAUDE_CODE_USE_VERTEX")

    // Pass harness mode to bridge (acp or piMono)
    env["HARNESS_MODE"] = harnessMode

    // For piMono mode, inject the Firebase ID token so the bridge can
    // authenticate against POST /v2/chat/completions (which expects
    // Authorization: Bearer <firebase-id-token>).
    //
    // SECURITY: if we can't get a Firebase token, refuse to start. The bridge
    // must NEVER fall back to ANTHROPIC_API_KEY as the Omi backend credential.
    if harnessMode == "piMono" {
      let authService = await MainActor.run { AuthService.shared }
      let token: String
      do {
        token = try await authService.getIdToken()
      } catch {
        log("AgentBridge: pi-mono start refused — auth error: \(error.localizedDescription)")
        throw BridgeError.authMissing
      }
      guard !token.isEmpty else {
        log("AgentBridge: pi-mono start refused — Firebase ID token is empty")
        throw BridgeError.authMissing
      }
      env["OMI_AUTH_TOKEN"] = token
      // Point pi-mono at the Rust desktop-backend's /v2/chat/completions proxy.
      // Without this, pi-mono-extension falls back to https://api.omi.me/v2 which
      // does NOT serve chat/completions — the shipped app would get 404 on every
      // prompt. rustBackendURL is baked at build time from OMI_DESKTOP_API_URL in .env.
      let rustBase = await APIClient.shared.rustBackendURL
      if !rustBase.isEmpty {
        env["OMI_API_BASE_URL"] = rustBase.hasSuffix("/") ? "\(rustBase)v2" : "\(rustBase)/v2"
      } else {
        log("AgentBridge: pi-mono start refused — OMI_DESKTOP_API_URL (Rust backend) not configured")
        throw BridgeError.bridgeScriptNotFound
      }
    }

    // Ensure the directory containing node is in PATH
    let nodeDir = (nodePath as NSString).deletingLastPathComponent
    let existingPath = env["PATH"] ?? "/usr/bin:/bin"
    if !existingPath.contains(nodeDir) {
      env["PATH"] = "\(nodeDir):\(existingPath)"
    }

    // Playwright MCP extension mode
    let defaults = UserDefaults.standard
    let useExtension =
      defaults.object(forKey: "playwrightUseExtension") == nil
      || defaults.bool(forKey: "playwrightUseExtension")
    if useExtension {
      env["PLAYWRIGHT_USE_EXTENSION"] = "true"
      if let token = defaults.string(forKey: "playwrightExtensionToken"), !token.isEmpty {
        env["PLAYWRIGHT_MCP_EXTENSION_TOKEN"] = token
      }
    }

    proc.environment = env

    let stdin = Pipe()
    let stdout = Pipe()
    let stderr = Pipe()

    proc.standardInput = stdin
    proc.standardOutput = stdout
    proc.standardError = stderr

    self.stdinPipe = stdin
    self.stdoutPipe = stdout
    self.stderrPipe = stderr
    self.process = proc

    // Read stderr for logging and OOM detection
    stderr.fileHandleForReading.readabilityHandler = { [weak self] handle in
      let data = handle.availableData
      if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
        log("AgentBridge stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
        if text.contains("FatalProcessOutOfMemory")
          || text.contains("JavaScript heap out of memory")
          || text.contains("Failed to reserve virtual memory")
          || text.contains("out of memory")
        {
          Task { await self?.markOOM() }
        }
      }
    }

    // Bump generation so stale termination handlers from previous processes are ignored
    processGeneration &+= 1
    let expectedGeneration = processGeneration

    proc.terminationHandler = { [weak self] terminatedProc in
      let code = terminatedProc.terminationStatus
      let reason = terminatedProc.terminationReason
      Task { [weak self] in
        await self?.handleTermination(
          exitCode: code, reason: reason, generation: expectedGeneration)
      }
    }

    try proc.run()
    isRunning = true

    // Start reading stdout
    startReadingStdout()

    // Start periodic token refresh for piMono mode (every 45 min)
    if harnessMode == "piMono" {
      tokenRefreshTask = Task { [weak self] in
        while !Task.isCancelled {
          try? await Task.sleep(nanoseconds: 45 * 60 * 1_000_000_000)
          guard !Task.isCancelled else { break }
          await self?.refreshAuthToken()
        }
      }
    }

    // Wait for the initial "init" message indicating bridge is ready
    let initMsg = try await waitForMessage(timeout: 30.0)
    if case .`init`(let sessionId) = initMsg {
      log("AgentBridge: bridge ready (sessionId=\(sessionId))")
    }
  }

  /// Restart the bridge process (stop then start)
  func restart() async throws {
    await stopAndWaitForExit()
    try await start()
  }

  /// Stop the bridge process and wait for the subprocess to fully terminate.
  /// This prevents race conditions where the old process is still alive when
  /// a new bridge is started (e.g. during provider switching).
  func stopAndWaitForExit() async {
    let proc = process
    let pid = proc?.processIdentifier ?? 0
    stop()
    // Wait for the subprocess to fully exit (up to 3s).
    // This is important during provider switches: the old Node.js process must
    // be dead before the new one starts to avoid log confusion and resource overlap.
    if let proc = proc {
      let start = Date()
      while proc.isRunning && Date().timeIntervalSince(start) < 3.0 {
        try? await Task.sleep(nanoseconds: 50_000_000)  // 50ms
      }
      if proc.isRunning && pid > 0 {
        log("AgentBridge: process \(pid) still alive after 3s, sending SIGKILL")
        kill(pid, SIGKILL)
        // Brief wait for SIGKILL to take effect
        try? await Task.sleep(nanoseconds: 200_000_000)  // 200ms
      }
    }
  }

  /// Stop the bridge process
  func stop() {
    log("AgentBridge: stopping (harness=\(harnessMode))")
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    readTask?.cancel()
    readTask = nil

    sendLine(
      """
      {"type":"stop"}
      """)
    try? stdinPipe?.fileHandleForWriting.close()

    process?.terminate()
    process = nil
    closePipes()
    isRunning = false

    messageContinuation?.resume(throwing: BridgeError.stopped)
    messageContinuation = nil
  }

  // MARK: - Authentication

  /// Tell the bridge which auth method the user chose
  func authenticate(methodId: String) {
    guard isRunning else { return }
    let msg: [String: Any] = [
      "type": "authenticate",
      "methodId": methodId,
    ]
    if let data = try? JSONSerialization.data(withJSONObject: msg),
      let jsonString = String(data: data, encoding: .utf8)
    {
      sendLine(jsonString)
    }
  }

  // MARK: - Session Pre-warming

  /// Tell the bridge to pre-create ACP sessions in the background.
  /// This saves ~4s on the first query by doing session/new ahead of time.
  /// Pass multiple models to pre-warm sessions for both Opus and Sonnet in parallel.
  struct WarmupSessionConfig {
    let key: String
    let model: String
    let systemPrompt: String?
  }

  func warmupSession(cwd: String? = nil, sessions: [WarmupSessionConfig]) {
    guard isRunning else { return }
    var dict: [String: Any] = ["type": "warmup"]
    if let cwd = cwd { dict["cwd"] = cwd }
    dict["sessions"] = sessions.map { s -> [String: Any] in
      var entry: [String: Any] = ["key": s.key, "model": s.model]
      if let sp = s.systemPrompt { entry["systemPrompt"] = sp }
      return entry
    }
    if let data = try? JSONSerialization.data(withJSONObject: dict),
      let str = String(data: data, encoding: .utf8)
    {
      sendLine(str)
    }
  }

  /// Invalidate a cached session key so the next query creates a fresh ACP session.
  func invalidateSession(sessionKey: String) {
    guard isRunning else { return }
    let msg: [String: Any] = [
      "type": "invalidate_session",
      "sessionKey": sessionKey,
    ]
    if let data = try? JSONSerialization.data(withJSONObject: msg),
      let str = String(data: data, encoding: .utf8)
    {
      sendLine(str)
    }
  }

  // MARK: - Query

  /// Send a query to the ACP agent and stream results back.
  ///
  /// SESSION LIFECYCLE (Desktop app — not the VM/agent-cloud flow):
  /// Sessions are pre-warmed at startup via warmupSession(). The bridge reuses
  /// the same session for every subsequent query, so `systemPrompt` is ignored
  /// for the normal path. It is only applied if the session was invalidated
  /// (e.g. cwd change) and the bridge creates a new session/new internally.
  /// Pass cachedMainSystemPrompt here — never rebuild the full system prompt
  /// per-query, and never inject conversation history into it (the ACP SDK
  /// maintains conversation history natively within the session).
  ///
  /// TOKEN COUNTS: The cacheReadTokens/cacheWriteTokens returned by the bridge
  /// reflect the TOTAL across all internal tool-use rounds within this single
  /// session/prompt call. The ACP SDK handles tool use internally — there is no
  /// separate "sub-agent" spawning visible at this level.
  func query(
    prompt: String,
    systemPrompt: String,
    sessionKey: String? = nil,
    cwd: String? = nil,
    mode: String? = nil,
    model: String? = nil,
    resume: String? = nil,
    imageData: Data? = nil,
    onTextDelta: @escaping TextDeltaHandler,
    onToolCall: @escaping ToolCallHandler,
    onToolActivity: @escaping ToolActivityHandler,
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    guard isRunning else {
      throw BridgeError.notRunning
    }

    // Hard cap: check monthly chat quota before spending any Anthropic tokens.
    // Free / Operator / Unlimited cap by question count; Architect (pro) caps by
    // cost_usd. Raises BridgeError.quotaExceeded if over — caller shows upgrade UI.
    if let quota = await APIClient.shared.fetchChatUsageQuota(), !quota.allowed {
      throw BridgeError.quotaExceeded(
        plan: quota.plan,
        unit: quota.unit,
        used: quota.used,
        limit: quota.limit,
        resetAtUnix: quota.resetAt
      )
    }

    var queryDict: [String: Any] = [
      "type": "query",
      "id": UUID().uuidString,
      "prompt": prompt,
      "systemPrompt": systemPrompt,
    ]
    if let sessionKey = sessionKey {
      queryDict["sessionKey"] = sessionKey
    }
    if let cwd = cwd {
      queryDict["cwd"] = cwd
    }
    if let mode = mode {
      queryDict["mode"] = mode
    }
    if let model = model {
      queryDict["model"] = model
    }
    if let resume = resume {
      queryDict["resume"] = resume
    }
    if let imageData = imageData {
      queryDict["imageBase64"] = imageData.base64EncodedString()
    }

    let jsonData = try JSONSerialization.data(withJSONObject: queryDict)
    guard let jsonString = String(data: jsonData, encoding: .utf8) else {
      throw BridgeError.encodingError
    }

    isInterrupted = false
    // Discard any stale messages from a previous interrupted/timed-out query
    // to avoid desynchronizing the request-response protocol.
    if !pendingMessages.isEmpty {
      log("AgentBridge: clearing \(pendingMessages.count) stale pending messages before new query")
      pendingMessages.removeAll()
    }
    sendLine(jsonString)

    // Read messages until we get a result or error.
    // No per-message timeout — rely on process termination (handleTermination) to
    // detect a dead bridge. A per-message timeout (like Zed's old low_speed_timeout)
    // fires prematurely during long-running tools (sentry-logs, slow API calls, etc.).
    while true {
      let message = try await waitForMessage()

      switch message {
      case .`init`:
        log("AgentBridge: new session started")

      case .textDelta(let text):
        onTextDelta(text)

      case .toolUse(let callId, let name, let input):
        // If already interrupted, skip this tool call entirely
        if isInterrupted {
          log("AgentBridge: skipping tool call \(name) (interrupted)")
          continue
        }
        let result = await onToolCall(callId, name, input)
        let resultDict: [String: Any] = [
          "type": "tool_result",
          "callId": callId,
          "result": result,
        ]
        let resultData = try JSONSerialization.data(withJSONObject: resultDict)
        if let resultString = String(data: resultData, encoding: .utf8) {
          sendLine(resultString)
        }

        // If interrupted during tool execution, skip remaining tool calls
        // and drain messages to find the result (already sent by the bridge).
        if isInterrupted {
          log("AgentBridge: interrupted during tool call, draining for result")
          while !pendingMessages.isEmpty {
            let pending = pendingMessages.removeFirst()
            switch pending {
            case .result(
              let text, let sessionId, let costUsd, let inputTokens, let outputTokens,
              let cacheReadTokens, let cacheWriteTokens):
              return QueryResult(
                text: text, costUsd: costUsd ?? 0, sessionId: sessionId, inputTokens: inputTokens,
                outputTokens: outputTokens, cacheReadTokens: cacheReadTokens,
                cacheWriteTokens: cacheWriteTokens)
            case .error(let message):
              log("AgentBridge: agent error (raw): \(message)")
              throw BridgeError.agentError(message)
            default:
              continue
            }
          }
          while true {
            let msg = try await waitForMessage()
            switch msg {
            case .result(
              let text, let sessionId, let costUsd, let inputTokens, let outputTokens,
              let cacheReadTokens, let cacheWriteTokens):
              return QueryResult(
                text: text, costUsd: costUsd ?? 0, sessionId: sessionId, inputTokens: inputTokens,
                outputTokens: outputTokens, cacheReadTokens: cacheReadTokens,
                cacheWriteTokens: cacheWriteTokens)
            case .error(let message):
              log("AgentBridge: agent error (raw): \(message)")
              throw BridgeError.agentError(message)
            default:
              continue
            }
          }
        }

      case .thinkingDelta(let text):
        onThinkingDelta(text)

      case .toolActivity(let name, let status, let toolUseId, let input):
        onToolActivity(name, status, toolUseId, input)

      case .toolResultDisplay(let toolUseId, let name, let output):
        onToolResultDisplay(toolUseId, name, output)

      case .result(
        let text, let sessionId, let costUsd, let inputTokens, let outputTokens,
        let cacheReadTokens, let cacheWriteTokens):
        return QueryResult(
          text: text, costUsd: costUsd ?? 0, sessionId: sessionId, inputTokens: inputTokens,
          outputTokens: outputTokens, cacheReadTokens: cacheReadTokens,
          cacheWriteTokens: cacheWriteTokens)

      case .error(let message):
        log("AgentBridge: agent error (raw): \(message)")
        throw BridgeError.agentError(message)

      case .authRequired(let methods, let authUrl):
        onAuthRequired(methods, authUrl)

      case .authSuccess:
        onAuthSuccess()
      }
    }
  }

  // MARK: - Streaming Input Controls

  /// Interrupt the running agent, keeping partial response.
  func interrupt() {
    guard isRunning else { return }
    isInterrupted = true
    sendLine("{\"type\":\"interrupt\"}")
  }

  /// Push a refreshed Firebase ID token to the bridge (piMono mode only).
  /// Called periodically so long-running sessions don't expire.
  func refreshAuthToken() async {
    guard isRunning, harnessMode == "piMono" else { return }
    let authService = await MainActor.run { AuthService.shared }
    let token: String
    do {
      token = try await authService.getIdToken(forceRefresh: true)
    } catch {
      log("AgentBridge: refreshAuthToken failed — \(error.localizedDescription)")
      return
    }
    guard !token.isEmpty else {
      log("AgentBridge: refreshAuthToken got empty token; skipping push")
      return
    }
    let msg: [String: Any] = ["type": "refresh_token", "token": token]
    if let data = try? JSONSerialization.data(withJSONObject: msg),
       let str = String(data: data, encoding: .utf8) {
      sendLine(str)
    }
  }

  // MARK: - Private

  private func sendLine(_ line: String) {
    guard let pipe = stdinPipe else { return }
    let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if let data = (trimmed + "\n").data(using: .utf8) {
      do {
        try pipe.fileHandleForWriting.write(contentsOf: data)
      } catch {
        log("AgentBridge: Failed to write to stdin pipe: \(error.localizedDescription)")
      }
    }
  }

  private func startReadingStdout() {
    guard let stdout = stdoutPipe else { return }

    readTask = Task.detached { [weak self] in
      let handle = stdout.fileHandleForReading
      var buffer = Data()

      while !Task.isCancelled {
        let chunk = handle.availableData
        if chunk.isEmpty {
          break
        }
        buffer.append(chunk)

        while let newlineIndex = buffer.firstIndex(of: UInt8(ascii: "\n")) {
          let lineData = buffer[buffer.startIndex..<newlineIndex]
          buffer = Data(buffer[buffer.index(after: newlineIndex)...])

          guard let lineStr = String(data: lineData, encoding: .utf8),
            !lineStr.trimmingCharacters(in: .whitespaces).isEmpty
          else {
            continue
          }

          if let message = Self.parseMessage(lineStr) {
            await self?.deliverMessage(message)
          }
        }
      }
    }
  }

  private static func parseMessage(_ json: String) -> InboundMessage? {
    guard let data = json.data(using: .utf8),
      let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let type = dict["type"] as? String
    else {
      log("AgentBridge: failed to parse message: \(json.prefix(200))")
      return nil
    }

    switch type {
    case "init":
      let sessionId = dict["sessionId"] as? String ?? ""
      return .`init`(sessionId: sessionId)

    case "text_delta":
      let text = dict["text"] as? String ?? ""
      return .textDelta(text: text)

    case "tool_use":
      let callId = dict["callId"] as? String ?? ""
      let name = dict["name"] as? String ?? ""
      let input = dict["input"] as? [String: Any] ?? [:]
      return .toolUse(callId: callId, name: name, input: input)

    case "thinking_delta":
      let text = dict["text"] as? String ?? ""
      return .thinkingDelta(text: text)

    case "tool_activity":
      let name = dict["name"] as? String ?? ""
      let status = dict["status"] as? String ?? "started"
      let toolUseId = dict["toolUseId"] as? String
      let input = dict["input"] as? [String: Any]
      return .toolActivity(name: name, status: status, toolUseId: toolUseId, input: input)

    case "tool_result_display":
      let toolUseId = dict["toolUseId"] as? String ?? ""
      let name = dict["name"] as? String ?? ""
      let output = dict["output"] as? String ?? ""
      return .toolResultDisplay(toolUseId: toolUseId, name: name, output: output)

    case "result":
      let text = dict["text"] as? String ?? ""
      let sessionId = dict["sessionId"] as? String ?? ""
      let costUsd = dict["costUsd"] as? Double
      let inputTokens = dict["inputTokens"] as? Int ?? 0
      let outputTokens = dict["outputTokens"] as? Int ?? 0
      let cacheReadTokens = dict["cacheReadTokens"] as? Int ?? 0
      let cacheWriteTokens = dict["cacheWriteTokens"] as? Int ?? 0
      return .result(
        text: text, sessionId: sessionId, costUsd: costUsd,
        inputTokens: inputTokens, outputTokens: outputTokens,
        cacheReadTokens: cacheReadTokens, cacheWriteTokens: cacheWriteTokens)

    case "error":
      let message = dict["message"] as? String ?? "Unknown error"
      return .error(message: message)

    case "auth_required":
      let methods = dict["methods"] as? [[String: Any]] ?? []
      let authUrl = dict["authUrl"] as? String
      return .authRequired(methods: methods, authUrl: authUrl)

    case "auth_success":
      return .authSuccess

    default:
      log("AgentBridge: unknown message type: \(type)")
      return nil
    }
  }

  private func deliverMessage(_ message: InboundMessage) {
    // Handle auth messages immediately via global handlers (even outside query)
    switch message {
    case .authRequired(let methods, let authUrl):
      if messageContinuation == nil, let handler = onAuthRequiredGlobal {
        // No active query waiting — fire the global handler immediately
        handler(methods, authUrl)
        return
      }
    case .authSuccess:
      if messageContinuation == nil, let handler = onAuthSuccessGlobal {
        handler()
        return
      }
    default:
      break
    }

    if let continuation = messageContinuation {
      messageContinuation = nil
      continuation.resume(returning: message)
    } else {
      pendingMessages.append(message)
    }
  }

  private func waitForMessage(timeout: TimeInterval? = nil) async throws -> InboundMessage {
    if !pendingMessages.isEmpty {
      return pendingMessages.removeFirst()
    }

    messageGeneration &+= 1
    let expectedGeneration = messageGeneration

    return try await withCheckedThrowingContinuation { continuation in
      self.messageContinuation = continuation

      if let timeout = timeout {
        Task {
          try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
          if self.messageGeneration == expectedGeneration, self.messageContinuation != nil {
            self.messageContinuation = nil
            continuation.resume(throwing: BridgeError.timeout)
          }
        }
      }
    }
  }

  private func markOOM() {
    lastExitWasOOM = true
  }

  private func handleTermination(
    exitCode: Int32 = -1, reason: Process.TerminationReason = .exit, generation: UInt64? = nil
  ) {
    // Ignore stale termination from a previous process (fixes race where old handler closes new pipes)
    if let gen = generation, gen != processGeneration {
      log("AgentBridge: ignoring stale termination (gen=\(gen), current=\(processGeneration))")
      return
    }

    let reasonStr = reason == .uncaughtSignal ? "signal" : "exit"

    // Capture any remaining stderr before closing pipes (may reveal OOM)
    if let stderrHandle = stderrPipe?.fileHandleForReading {
      stderrHandle.readabilityHandler = nil  // Stop async handler
      let remaining = stderrHandle.availableData
      if !remaining.isEmpty, let text = String(data: remaining, encoding: .utf8) {
        log("AgentBridge stderr (final): \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
        if text.contains("out of memory") || text.contains("Failed to reserve virtual memory") {
          lastExitWasOOM = true
        }
      }
    }

    // SIGABRT (134) and SIGTRAP (133/5) with uncaughtSignal are typical V8 OOM crashes
    let likelyOOM =
      lastExitWasOOM
      || (reason == .uncaughtSignal
        && (exitCode == 134 || exitCode == 133 || exitCode == 5 || exitCode == 6))
    let error: BridgeError = likelyOOM ? .outOfMemory : .processExited
    lastExitWasOOM = false

    log("AgentBridge: process terminated (code=\(exitCode), reason=\(reasonStr), error=\(error))")
    isRunning = false
    closePipes()
    messageContinuation?.resume(throwing: error)
    messageContinuation = nil
  }

  private func closePipes() {
    if let stdin = stdinPipe {
      try? stdin.fileHandleForWriting.close()
      try? stdin.fileHandleForReading.close()
    }
    if let stdout = stdoutPipe {
      stdout.fileHandleForReading.readabilityHandler = nil
      try? stdout.fileHandleForReading.close()
      try? stdout.fileHandleForWriting.close()
    }
    if let stderr = stderrPipe {
      stderr.fileHandleForReading.readabilityHandler = nil
      try? stderr.fileHandleForReading.close()
      try? stderr.fileHandleForWriting.close()
    }
    stdinPipe = nil
    stdoutPipe = nil
    stderrPipe = nil
  }

  // MARK: - Node.js Discovery

  private func findNodeBinary() -> String? {
    // 1. Check bundled node binary in app resources
    let bundledNode = Bundle.resourceBundle.path(forResource: "node", ofType: nil)
    if let bundledNode, FileManager.default.isExecutableFile(atPath: bundledNode) {
      return bundledNode
    }

    // 2. Fall back to system-installed node
    let candidates = [
      "/opt/homebrew/bin/node",
      "/usr/local/bin/node",
      "/usr/bin/node",
    ]
    for path in candidates {
      if FileManager.default.isExecutableFile(atPath: path) {
        return path
      }
    }

    // 3. Check NVM installations
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let nvmDir = (home as NSString).appendingPathComponent(".nvm/versions/node")
    if let versions = try? FileManager.default.contentsOfDirectory(atPath: nvmDir) {
      let sorted = versions.sorted { v1, v2 in
        v1.compare(v2, options: .numeric) == .orderedDescending
      }
      for version in sorted {
        let nodePath = (nvmDir as NSString).appendingPathComponent("\(version)/bin/node")
        if FileManager.default.isExecutableFile(atPath: nodePath) {
          return nodePath
        }
      }
    }

    // 4. Try `which node`
    let whichProcess = Process()
    whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
    whichProcess.arguments = ["node"]
    let pipe = Pipe()
    whichProcess.standardOutput = pipe
    try? whichProcess.run()
    whichProcess.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(
      in: .whitespacesAndNewlines),
      !path.isEmpty,
      FileManager.default.isExecutableFile(atPath: path)
    {
      return path
    }

    return nil
  }

  // MARK: - Playwright Connection Test

  /// Test that the Playwright Chrome extension is connected and working.
  /// Sends a minimal query that triggers a browser_snapshot tool call.
  /// Returns true if the extension responds successfully.
  func testPlaywrightConnection() async throws -> Bool {
    guard isRunning else {
      throw BridgeError.notRunning
    }

    log("AgentBridge: Testing Playwright connection...")
    let result = try await query(
      prompt:
        "Call browser_snapshot to verify the extension is connected. Only call that one tool, then report success or failure.",
      systemPrompt:
        "You are a connection test agent. Call the browser_snapshot tool exactly once. If it succeeds, respond with exactly 'CONNECTED'. If it fails, respond with 'FAILED' followed by the error.",
      mode: "ask",
      onTextDelta: { _ in },
      onToolCall: { _, _, _ in "" },
      onToolActivity: { name, status, _, _ in
        log("AgentBridge: test tool activity: \(name) \(status)")
      },
      onThinkingDelta: { _ in },
      onToolResultDisplay: { _, name, output in
        log("AgentBridge: test tool result: \(name) -> \(output.prefix(200))")
      }
    )
    let connected = result.text.contains("CONNECTED")
    log("AgentBridge: Playwright test response: \(result.text.prefix(300)), connected=\(connected)")
    return connected
  }

  private func findBridgeScript() -> String? {
    // 1. Check in app bundle Resources
    if let bundlePath = Bundle.main.resourcePath {
      let bundledScript = (bundlePath as NSString).appendingPathComponent(
        "agent/dist/index.js")
      if FileManager.default.fileExists(atPath: bundledScript) {
        return bundledScript
      }
    }

    // 2. Check relative to executable (development mode)
    let executableURL = Bundle.main.executableURL
    if let execDir = executableURL?.deletingLastPathComponent() {
      let devPaths = [
        execDir.appendingPathComponent("../../../agent/dist/index.js").path,
        execDir.appendingPathComponent("../../../../agent/dist/index.js").path,
      ]
      for path in devPaths {
        let resolved = (path as NSString).standardizingPath
        if FileManager.default.fileExists(atPath: resolved) {
          return resolved
        }
      }
    }

    // 3. Check relative to current working directory
    let cwdPath = FileManager.default.currentDirectoryPath
    let cwdCandidates = [
      "agent/dist/index.js",
      "desktop/agent/dist/index.js",
      "../desktop/agent/dist/index.js",
    ]
    for relativePath in cwdCandidates {
      let candidate = (cwdPath as NSString).appendingPathComponent(relativePath)
      let resolved = (candidate as NSString).standardizingPath
      if FileManager.default.fileExists(atPath: resolved) {
        return resolved
      }
    }

    return nil
  }
}

// MARK: - Errors

enum BridgeError: LocalizedError {
  case nodeNotFound
  case bridgeScriptNotFound
  case notRunning
  case encodingError
  case timeout
  case processExited
  case outOfMemory
  case stopped
  case agentError(String)
  /// User is past their monthly chat cap; the client should render an
  /// upgrade modal instead of a generic error. `plan` is the user-facing
  /// plan label (e.g. "Free" / "Operator" / "Architect") and `resetAtUnix`
  /// is the Unix-seconds timestamp of the cap reset (start of next UTC month).
  case quotaExceeded(plan: String, unit: String, used: Double, limit: Double?, resetAtUnix: Int?)
  case authMissing

  var errorDescription: String? {
    switch self {
    case .nodeNotFound:
      return AnalyticsManager.isDevBuild
        ? "Node.js not found. Run ./run.sh to set up AI components."
        : "Node.js not found. Please reinstall the app."
    case .bridgeScriptNotFound:
      return AnalyticsManager.isDevBuild
        ? "AI components missing. Run ./run.sh to install the agent runtime."
        : "AI components missing. Please reinstall the app."
    case .notRunning:
      return "AI is not running. Try sending your message again."
    case .encodingError:
      return "Failed to encode message"
    case .timeout:
      return "AI took too long to respond. Try again."
    case .processExited:
      return "AI stopped unexpectedly. Try sending your message again."
    case .outOfMemory:
      return "Not enough memory for AI chat. Close some apps and try again."
    case .stopped:
      return "Response stopped."
    case .authMissing:
      return "Please sign in to use AI chat."
    case .agentError(let msg):
      let lower = msg.lowercased()
      if lower.contains("leaked") || lower.contains("api key") || lower.contains("api_key")
        || lower.contains("unauthorized") || lower.contains("permission denied")
        || lower.contains("invalid key") || lower.contains("forbidden")
      {
        return "AI service authentication error. Please update the app to the latest version."
      }
      if lower.contains("quota") || lower.contains("rate limit")
        || lower.contains("resource exhausted")
      {
        return "AI service is busy. Please try again in a moment."
      }
      if lower.contains("overloaded") || lower.contains("service unavailable")
        || lower.contains("internal error")
      {
        return "AI service is temporarily unavailable. Please try again later."
      }
      return "Something went wrong. Please try again."
    case .quotaExceeded(let plan, let unit, let used, let limit, _):
      let limitStr: String = {
        guard let limit = limit else { return "your monthly limit" }
        return unit == "cost_usd"
          ? String(format: "$%.0f of monthly chat usage", limit)
          : "\(Int(limit)) chat questions per month"
      }()
      let usedStr: String = {
        unit == "cost_usd"
          ? String(format: "$%.2f used", used)
          : "\(Int(used)) used"
      }()
      return "You've hit your \(plan) plan limit (\(limitStr); \(usedStr)). Upgrade in Settings → Plan and Usage, or wait until the next reset."
    }
  }
}
