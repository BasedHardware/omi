import Foundation

/// Lightweight client handle for the shared Node.js agent runtime.
actor AgentBridge {

  struct QueryResult {
    let text: String
    let costUsd: Double
    let omiSessionId: String
    let runId: String
    let attemptId: String
    let adapterSessionId: String?
    let terminalStatus: String
    let inputTokens: Int
    let outputTokens: Int
    let cacheReadTokens: Int
    let cacheWriteTokens: Int

    @available(*, deprecated, message: "Use omiSessionId or adapterSessionId explicitly")
    var sessionId: String { adapterSessionId ?? omiSessionId }
  }

  typealias TextDeltaHandler = @Sendable (String) -> Void
  typealias ToolCallHandler = @Sendable (String, String, [String: Any]) async -> String
  typealias ToolActivityHandler = @Sendable (String, String, String?, [String: Any]?) -> Void
  typealias ThinkingDeltaHandler = @Sendable (String) -> Void
  typealias ToolResultDisplayHandler = @Sendable (String, String, String) -> Void
  typealias AuthRequiredHandler = @Sendable ([[String: Any]], String?) -> Void
  typealias AuthSuccessHandler = @Sendable () -> Void

  struct WarmupSessionConfig {
    let key: String
    let model: String?
    let systemPrompt: String?
  }

  let harnessMode: String

  private let clientId = UUID().uuidString
  private let runtime: AgentRuntimeProcess
  private var registered = false
  private var activeRequestId: String?
  private var lastKnownQuota: APIClient.ChatUsageQuota?
  private var tokenRefreshTask: Task<Void, Never>?

  var isAlive: Bool {
    get async {
      await runtime.isAlive
    }
  }

  init(harnessMode: String = "piMono", runtime: AgentRuntimeProcess = .shared) {
    self.harnessMode = harnessMode
    self.runtime = runtime
  }

  private var isPiMonoHarness: Bool {
    AgentRuntimeProcess.adapterId(forHarnessMode: harnessMode) == AgentAdapterId.piMono.rawValue
  }

  func setGlobalAuthHandlers(
    onAuthRequired: AuthRequiredHandler?,
    onAuthSuccess: AuthSuccessHandler?
  ) async {
    await runtime.setGlobalAuthHandlers(
      clientId: clientId,
      onAuthRequired: onAuthRequired,
      onAuthSuccess: onAuthSuccess
    )
  }

  func start() async throws {
    guard !registered else { return }
    try await runtime.registerClient(clientId: clientId, harnessMode: harnessMode)
    registered = true

    if isPiMonoHarness, tokenRefreshTask == nil {
      tokenRefreshTask = Task { [weak self] in
        while !Task.isCancelled {
          try? await Task.sleep(nanoseconds: 45 * 60 * 1_000_000_000)
          guard !Task.isCancelled else { break }
          await self?.refreshAuthToken()
        }
      }
      await refreshAuthToken()
    }
  }

  func restart() async throws {
    try await runtime.restart(harnessMode: harnessMode)
    registered = true
  }

  func stopAndWaitForExit() async {
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    let wasRegistered = registered
    registered = false
    activeRequestId = nil
    lastKnownQuota = nil
    guard wasRegistered else { return }
    await runtime.unregisterClient(clientId: clientId)
  }

  func stop() {
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    let wasRegistered = registered
    registered = false
    activeRequestId = nil
    lastKnownQuota = nil
    guard wasRegistered else { return }
    Task {
      await runtime.unregisterClient(clientId: clientId)
    }
  }

  func authenticate(methodId: String) {
    Task {
      await runtime.authenticate(methodId: methodId)
    }
  }

  func warmupSession(cwd: String? = nil, sessions: [WarmupSessionConfig]) {
    Task {
      await runtime.warmupSession(
        clientId: clientId,
        cwd: cwd,
        sessions: sessions.map {
          AgentRuntimeProcess.WarmupSessionConfig(
            key: $0.key,
            model: $0.model,
            systemPrompt: $0.systemPrompt
          )
        }
      )
    }
  }

  func invalidateSession(sessionKey: String) {
    Task {
      await runtime.invalidateSession(clientId: clientId, sessionKey: sessionKey)
    }
  }

  func controlTool(name: String, input: [String: Any]) async throws -> String {
    try await start()
    return try await runtime.directControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: input
    )
  }

  func query(
    prompt: String,
    systemPrompt: String,
    sessionKey: String? = nil,
    omiSessionId: String? = nil,
    surfaceKind: String? = nil,
    externalRefKind: String? = nil,
    externalRefId: String? = nil,
    legacyClientScope: String? = nil,
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
    await setGlobalAuthHandlers(onAuthRequired: onAuthRequired, onAuthSuccess: onAuthSuccess)
    try await start()

    guard activeRequestId == nil else {
      throw BridgeError.requestAlreadyActive
    }

    if isPiMonoHarness {
      if let cached = lastKnownQuota, !cached.allowed {
        QueryTracerContext.current?.mark("quota_check", metadata: ["result": "exceeded_cached"])
        throw BridgeError.quotaExceeded(
          plan: cached.plan,
          unit: cached.unit,
          used: cached.used,
          limit: cached.limit,
          resetAtUnix: cached.resetAt
        )
      }
      QueryTracerContext.current?.mark("quota_check", metadata: ["mode": "optimistic"])
      Task { [weak self] in
        if let quota = await APIClient.shared.fetchChatUsageQuota() {
          await self?.cacheQuota(quota)
        }
      }
    }

    let requestId = UUID().uuidString
    activeRequestId = requestId
    defer { activeRequestId = nil }

    return try await runtime.query(
      clientId: clientId,
      requestId: requestId,
      harnessMode: harnessMode,
      prompt: prompt,
      systemPrompt: systemPrompt,
      sessionKey: sessionKey,
      omiSessionId: omiSessionId,
      surfaceKind: surfaceKind,
      externalRefKind: externalRefKind,
      externalRefId: externalRefId,
      legacyClientScope: legacyClientScope,
      cwd: cwd,
      mode: mode,
      model: model,
      resume: resume,
      imageData: imageData,
      onTextDelta: onTextDelta,
      onToolCall: onToolCall,
      onToolActivity: onToolActivity,
      onThinkingDelta: onThinkingDelta,
      onToolResultDisplay: onToolResultDisplay,
      onAuthRequired: onAuthRequired,
      onAuthSuccess: onAuthSuccess
    )
  }

  func interrupt() {
    guard let requestId = activeRequestId else { return }
    Task {
      await runtime.interrupt(clientId: clientId, requestId: requestId)
    }
  }

  func refreshAuthToken() async {
    guard isPiMonoHarness else { return }
    let authService = await MainActor.run { AuthService.shared }
    let token: String
    do {
      token = try await authService.getIdToken(forceRefresh: true)
    } catch {
      log("AgentBridge: refreshAuthToken failed: \(error.localizedDescription)")
      return
    }
    guard !token.isEmpty else {
      log("AgentBridge: refreshAuthToken got empty token; skipping push")
      return
    }
    await runtime.refreshAuthToken(token)
  }

  func testPlaywrightConnection() async throws -> Bool {
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

  private func cacheQuota(_ quota: APIClient.ChatUsageQuota) {
    lastKnownQuota = quota
  }
}

enum BridgeError: LocalizedError {
  case nodeNotFound
  case bridgeScriptNotFound
  case notRunning
  case encodingError
  case timeout
  case processExited
  case outOfMemory
  case stopped
  case restarting
  case requestAlreadyActive
  case agentError(String)
  case agentRuntimeFailure(AgentRuntimeFailure)
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
    case .restarting:
      return "AI is restarting. Try sending your message again."
    case .requestAlreadyActive:
      return "A response is already running for this chat."
    case .authMissing:
      return "Please sign in to use AI chat."
    case .agentRuntimeFailure(let failure):
      return failure.displayMessage
    case .agentError(let msg):
      let lower = msg.lowercased()
      // Codex auth errors mention codex/OPENAI_API_KEY; without this carve-out
      // they'd hit the generic "update the app" branch below, which is wrong
      // guidance (the fix is signing in, not updating).
      if lower.contains("codex") {
        return "Codex isn't signed in. Run `codex login` in Terminal, or add an OpenAI API key in Omi Settings, then try again."
      }
      // OpenClaw's `acp` mode bridges to the local gateway daemon; when it
      // isn't running the raw error is "ACP bridge failed: connect
      // ECONNREFUSED 127.0.0.1:18789" — surface what to actually do instead.
      if lower.contains("openclaw"), lower.contains("econnrefused") || lower.contains("bridge failed") {
        return "OpenClaw is installed but not running. Start OpenClaw (run `openclaw gateway` or open the OpenClaw app), then try again."
      }
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
