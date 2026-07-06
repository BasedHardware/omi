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
    let artifacts: [AgentArtifactProjection]
    let completionDeltaArtifacts: [AgentArtifactProjection]

    init(
      text: String,
      costUsd: Double,
      omiSessionId: String,
      runId: String,
      attemptId: String,
      adapterSessionId: String?,
      terminalStatus: String,
      inputTokens: Int,
      outputTokens: Int,
      cacheReadTokens: Int,
      cacheWriteTokens: Int,
      artifacts: [AgentArtifactProjection] = [],
      completionDeltaArtifacts: [AgentArtifactProjection] = []
    ) {
      self.text = text
      self.costUsd = costUsd
      self.omiSessionId = omiSessionId
      self.runId = runId
      self.attemptId = attemptId
      self.adapterSessionId = adapterSessionId
      self.terminalStatus = terminalStatus
      self.inputTokens = inputTokens
      self.outputTokens = outputTokens
      self.cacheReadTokens = cacheReadTokens
      self.cacheWriteTokens = cacheWriteTokens
      self.artifacts = artifacts
      self.completionDeltaArtifacts = completionDeltaArtifacts
    }
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
    await migrateLegacyMainChatSessionsIfNeeded()
    await migrateFloatingChatIntoMainChatIfNeeded()

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

  func invalidateSurface(_ surface: AgentSurfaceReference) async {
    await runtime.invalidateSurface(clientId: clientId, surface: surface)
  }

  func clearOwnerState() async {
    await runtime.clearOwnerState(clientId: clientId)
  }

  func clearOwnerSurfaceState(chatId: String = "default") async {
    await runtime.clearOwnerSurfaceState(clientId: clientId, chatId: chatId)
  }

  func importLegacyMainChatSessions(_ entries: [(chatId: String, agentSessionId: String)]) async {
    await runtime.importLegacyMainChatSessions(
      clientId: clientId,
      entries: entries.map { ["chatId": $0.chatId, "agentSessionId": $0.agentSessionId] }
    )
  }

  func mergeFloatingChatIntoMainChat(chatId: String = "default") async {
    await runtime.mergeFloatingChatIntoMainChat(clientId: clientId, chatId: chatId)
  }

  func importConversationTurns(
    surface: AgentSurfaceReference,
    turns: [(role: String, content: String, createdAtMs: Int?)]
  ) async {
    await runtime.importConversationTurns(
      clientId: clientId,
      surface: surface,
      turns: turns.map {
        var entry: [String: Any] = ["role": $0.role, "content": $0.content]
        if let createdAtMs = $0.createdAtMs {
          entry["createdAtMs"] = createdAtMs
        }
        return entry
      }
    )
  }

  func recordSurfaceTurn(
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String,
    interrupted: Bool = false,
    idempotencyKey: String? = nil
  ) async {
    await runtime.recordSurfaceTurn(
      clientId: clientId,
      surface: surface,
      userText: userText,
      assistantText: assistantText,
      origin: origin,
      interrupted: interrupted,
      idempotencyKey: idempotencyKey
    )
  }

  func getVoiceSeedContext(surface: AgentSurfaceReference) async throws -> (conversationId: String, context: String) {
    try await start()
    return try await runtime.getVoiceSeedContext(
      clientId: clientId,
      harnessMode: harnessMode,
      surface: surface
    )
  }

  func getKernelTurnTail(limit: Int = 8, chatId: String = "default") async throws -> AgentRuntimeProcess.KernelTurnTailResult {
    try await start()
    return try await runtime.getKernelTurnTail(
      clientId: clientId,
      harnessMode: harnessMode,
      limit: limit,
      chatId: chatId
    )
  }

  func projectCrossSurfaceTurn(
    surface: AgentSurfaceReference,
    userText: String,
    assistantText: String,
    origin: String,
    idempotencyKey: String? = nil
  ) async {
    await runtime.projectCrossSurfaceTurn(
      clientId: clientId,
      surface: surface,
      userText: userText,
      assistantText: assistantText,
      origin: origin,
      idempotencyKey: idempotencyKey
    )
  }

  func setTurnRecordedHandler(_ handler: @escaping AgentRuntimeProcess.TurnRecordedHandler) async {
    await runtime.addTurnRecordedHandler(handler)
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
    surface: AgentSurfaceReference,
    cwd: String? = nil,
    mode: String? = nil,
    model: String? = nil,
    imageData: Data? = nil,
    attachmentMetadataJson: String? = nil,
    surfaceContextJson: String? = nil,
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
      surface: surface,
      cwd: cwd,
      mode: mode,
      model: model,
      imageData: imageData,
      attachmentMetadataJson: attachmentMetadataJson,
      surfaceContextJson: surfaceContextJson,
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
      surface: .service("playwright_connection_test"),
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

  private static let legacyMainChatDefaultsKey = "mainChatRuntimeSessionIdsByOwnerAndChat"
  private static let floatingChatMigrationDefaultsKey = "floatingChatToMainChatMigration_v1"

  private func migrateFloatingChatIntoMainChatIfNeeded() async {
    guard !UserDefaults.standard.bool(forKey: Self.floatingChatMigrationDefaultsKey) else { return }
    await mergeFloatingChatIntoMainChat(chatId: "default")
    UserDefaults.standard.set(true, forKey: Self.floatingChatMigrationDefaultsKey)
  }

  private func migrateLegacyMainChatSessionsIfNeeded() async {
    let ownerId = await MainActor.run {
      AuthState.shared.userId ?? UserDefaults.standard.string(forKey: "auth_userId")
    }
    guard let ownerId, !ownerId.isEmpty else { return }
    guard let map = UserDefaults.standard.dictionary(forKey: Self.legacyMainChatDefaultsKey) as? [String: String],
          !map.isEmpty
    else { return }

    let prefix = "\(ownerId)|"
    let entries = map.compactMap { key, sessionId -> (chatId: String, agentSessionId: String)? in
      guard key.hasPrefix(prefix), !sessionId.isEmpty else { return nil }
      let chatId = String(key.dropFirst(prefix.count))
      return (chatId: chatId.isEmpty ? "default" : chatId, agentSessionId: sessionId)
    }
    if !entries.isEmpty {
      await importLegacyMainChatSessions(entries)
    }
    UserDefaults.standard.removeObject(forKey: Self.legacyMainChatDefaultsKey)
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
      return Self.userFacingAgentErrorMessage(msg)
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

  private static func userFacingAgentErrorMessage(_ msg: String) -> String {
    guard !msg.isEmpty else { return "Something went wrong. Please try again." }
    let lower = msg.lowercased()
    if lower.contains("leaked") || lower.contains("api key") || lower.contains("api_key")
      || lower.contains("unauthorized") || lower.contains("permission denied")
      || lower.contains("invalid key") || lower.contains("forbidden")
    {
      return "AI service authentication error. Please update the app to the latest version."
    }
    if lower.contains("quota") || lower.contains("rate limit") || lower.contains("resource exhausted") {
      return "AI service is busy. Please try again in a moment."
    }
    if lower.contains("overloaded") || lower.contains("service unavailable") || lower.contains("internal error") {
      return "AI service is temporarily unavailable. Please try again later."
    }
    return "Something went wrong. Please try again."
  }
}
