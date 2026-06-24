import Foundation

actor AgentRuntimeProcess {
  static let shared = AgentRuntimeProcess()

  struct WarmupSessionConfig {
    let key: String
    let model: String
    let systemPrompt: String?
  }

  struct RuntimeMessage {
    enum Kind: Equatable {
      case initMessage
      case textDelta
      case thinkingDelta
      case toolUse
      case toolActivity
      case toolResultDisplay
      case result
      case error
      case authRequired
      case authSuccess
      case cancelAck
      case unknown(String)
    }

    let kind: Kind
    let requestId: String?
    let clientId: String?
    let protocolVersion: Int?
    let payload: [String: Any]

    var routingKey: String? { requestId }

    static func parse(_ json: String) -> RuntimeMessage? {
      guard let data = json.data(using: .utf8),
        let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let type = dict["type"] as? String
      else {
        return nil
      }
      return RuntimeMessage(
        kind: kind(for: type),
        requestId: dict["requestId"] as? String,
        clientId: dict["clientId"] as? String,
        protocolVersion: dict["protocolVersion"] as? Int,
        payload: dict
      )
    }

    private static func kind(for type: String) -> Kind {
      switch type {
      case "init": return .initMessage
      case "text_delta": return .textDelta
      case "thinking_delta": return .thinkingDelta
      case "tool_use": return .toolUse
      case "tool_activity": return .toolActivity
      case "tool_result_display": return .toolResultDisplay
      case "result": return .result
      case "error": return .error
      case "auth_required": return .authRequired
      case "auth_success": return .authSuccess
      case "cancel_ack": return .cancelAck
      default: return .unknown(type)
      }
    }
  }

  private struct ClientRegistration {
    var harnessMode: String
    var onAuthRequired: AgentBridge.AuthRequiredHandler?
    var onAuthSuccess: AgentBridge.AuthSuccessHandler?
  }

  private struct ActiveRequest {
    let clientId: String
    let requestId: String
    let surfaceRef: AgentSurfaceReference?
    let onTextDelta: AgentBridge.TextDeltaHandler
    let onToolCall: AgentBridge.ToolCallHandler
    let onToolActivity: AgentBridge.ToolActivityHandler
    let onThinkingDelta: AgentBridge.ThinkingDeltaHandler
    let onToolResultDisplay: AgentBridge.ToolResultDisplayHandler
    let onAuthRequired: AgentBridge.AuthRequiredHandler
    let onAuthSuccess: AgentBridge.AuthSuccessHandler
    let continuation: CheckedContinuation<AgentBridge.QueryResult, Error>
    var isInterrupted = false
    var cancelAck: RuntimeMessage?
  }

  private var process: Process?
  private var stdinPipe: Pipe?
  private var stdoutPipe: Pipe?
  private var stderrPipe: Pipe?
  private var readTask: Task<Void, Never>?
  private var isRunning = false
  private var processGeneration: UInt64 = 0
  private var lastExitWasOOM = false
  private var clients: [String: ClientRegistration] = [:]
  private var activeRequests: [String: ActiveRequest] = [:]
  private var initContinuations: [CheckedContinuation<Void, Error>] = []
  private var receivedInit = false
  private var isRestarting = false

  var isAlive: Bool { isRunning }

  func registerClient(clientId: String, harnessMode: String) async throws {
    guard !isRestarting else {
      throw BridgeError.restarting
    }
    var registration = clients[clientId] ?? ClientRegistration(harnessMode: harnessMode)
    registration.harnessMode = harnessMode
    clients[clientId] = registration

    if isRunning {
      return
    }

    try await startProcess(preferredHarnessMode: harnessMode)
  }

  func unregisterClient(clientId: String) async {
    clients.removeValue(forKey: clientId)

    for (requestId, request) in activeRequests where request.clientId == clientId {
      activeRequests.removeValue(forKey: requestId)
      request.continuation.resume(throwing: BridgeError.stopped)
    }

    if clients.isEmpty {
      await stopProcess(resumeRequestsWith: BridgeError.stopped)
    }
  }

  func setGlobalAuthHandlers(
    clientId: String,
    onAuthRequired: AgentBridge.AuthRequiredHandler?,
    onAuthSuccess: AgentBridge.AuthSuccessHandler?
  ) {
    var registration = clients[clientId] ?? ClientRegistration(harnessMode: "piMono")
    registration.onAuthRequired = onAuthRequired
    registration.onAuthSuccess = onAuthSuccess
    clients[clientId] = registration
  }

  func restart(harnessMode: String) async throws {
    guard activeRequests.isEmpty else {
      log("AgentRuntimeProcess: shared restart blocked while \(activeRequests.count) request(s) are active")
      throw BridgeError.requestAlreadyActive
    }
    isRestarting = true
    defer { isRestarting = false }
    await stopProcess(resumeRequestsWith: BridgeError.stopped)
    try await startProcess(preferredHarnessMode: harnessMode)
  }

  func authenticate(methodId: String) {
    sendJson([
      "type": "authenticate",
      "methodId": methodId,
    ])
  }

  func warmupSession(clientId: String, cwd: String? = nil, sessions: [WarmupSessionConfig]) {
    var dict: [String: Any] = [
      "type": "warmup",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    if let cwd { dict["cwd"] = cwd }
    dict["sessions"] = sessions.map { session -> [String: Any] in
      var entry: [String: Any] = [
        "key": session.key,
        "model": session.model,
      ]
      if let systemPrompt = session.systemPrompt {
        entry["systemPrompt"] = systemPrompt
      }
      return entry
    }
    sendJson(dict)
  }

  func invalidateSession(clientId: String, sessionKey: String) {
    var dict: [String: Any] = [
      "type": "invalidate_session",
      "protocolVersion": 2,
      "requestId": UUID().uuidString,
      "clientId": clientId,
      "sessionKey": sessionKey,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func refreshAuthToken(_ token: String) {
    var dict: [String: Any] = [
      "type": "refresh_token",
      "token": token,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func interrupt(clientId: String, requestId: String) {
    guard var request = activeRequests[requestId], request.clientId == clientId else { return }
    request.isInterrupted = true
    activeRequests[requestId] = request
    var dict: [String: Any] = [
      "type": "interrupt",
      "protocolVersion": 2,
      "requestId": requestId,
      "clientId": clientId,
    ]
    if let ownerId = currentOwnerId() {
      dict["ownerId"] = ownerId
    }
    sendJson(dict)
  }

  func query(
    clientId: String,
    requestId: String,
    harnessMode: String,
    prompt: String,
    systemPrompt: String,
    sessionKey: String?,
    omiSessionId: String?,
    surfaceKind: String?,
    externalRefKind: String?,
    externalRefId: String?,
    legacyClientScope: String?,
    cwd: String?,
    mode: String?,
    model: String?,
    resume: String?,
    imageData: Data?,
    onTextDelta: @escaping AgentBridge.TextDeltaHandler,
    onToolCall: @escaping AgentBridge.ToolCallHandler,
    onToolActivity: @escaping AgentBridge.ToolActivityHandler,
    onThinkingDelta: @escaping AgentBridge.ThinkingDeltaHandler,
    onToolResultDisplay: @escaping AgentBridge.ToolResultDisplayHandler,
    onAuthRequired: @escaping AgentBridge.AuthRequiredHandler,
    onAuthSuccess: @escaping AgentBridge.AuthSuccessHandler
  ) async throws -> AgentBridge.QueryResult {
    try await registerClient(clientId: clientId, harnessMode: harnessMode)

    return try await withCheckedThrowingContinuation { continuation in
      let surfaceRef: AgentSurfaceReference?
      if let surfaceKind, let externalRefKind, let externalRefId {
        surfaceRef = AgentSurfaceReference(
          surfaceKind: surfaceKind,
          externalRefKind: externalRefKind,
          externalRefId: externalRefId
        )
      } else {
        surfaceRef = nil
      }
      let request = ActiveRequest(
        clientId: clientId,
        requestId: requestId,
        surfaceRef: surfaceRef,
        onTextDelta: onTextDelta,
        onToolCall: onToolCall,
        onToolActivity: onToolActivity,
        onThinkingDelta: onThinkingDelta,
        onToolResultDisplay: onToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess,
        continuation: continuation
      )
      activeRequests[requestId] = request
      if let surfaceRef {
        Task { @MainActor in
          AgentRuntimeStatusStore.shared.beginRequest(surface: surfaceRef)
        }
      }

      var queryDict: [String: Any] = [
        "type": "query",
        "protocolVersion": 2,
        "id": requestId,
        "requestId": requestId,
        "clientId": clientId,
        "prompt": prompt,
        "systemPrompt": systemPrompt,
        "adapterId": harnessMode == "piMono" ? "pi-mono" : "acp",
      ]
      if let sessionKey {
        queryDict["sessionKey"] = sessionKey
        queryDict["legacySessionKey"] = sessionKey
      }
      if let omiSessionId {
        queryDict["sessionId"] = omiSessionId
      }
      if let surfaceKind {
        queryDict["surfaceKind"] = surfaceKind
      }
      if let externalRefKind {
        queryDict["externalRefKind"] = externalRefKind
      }
      if let externalRefId {
        queryDict["externalRefId"] = externalRefId
      }
      if let legacyClientScope {
        queryDict["legacyClientScope"] = legacyClientScope
      }
      if let cwd { queryDict["cwd"] = cwd }
      if let mode { queryDict["mode"] = mode }
      if let model { queryDict["model"] = model }
      if let resume {
        queryDict["legacyAdapterSessionId"] = resume
        queryDict["resume"] = resume
      }
      if let imageData {
        queryDict["imageBase64"] = imageData.base64EncodedString()
      }
      if let ownerId = currentOwnerId() {
        queryDict["ownerId"] = ownerId
      }
      sendJson(queryDict)
    }
  }

  private func startProcess(preferredHarnessMode: String) async throws {
    guard !isRunning else { return }

    readTask?.cancel()
    readTask = nil
    process = nil
    closePipes()
    lastExitWasOOM = false
    receivedInit = false

    guard let nodePath = findNodeBinary() else {
      throw BridgeError.nodeNotFound
    }
    guard let bridgePath = findBridgeScript() else {
      throw BridgeError.bridgeScriptNotFound
    }

    let nodeExists = FileManager.default.isExecutableFile(atPath: nodePath)
    let bridgeExists = FileManager.default.fileExists(atPath: bridgePath)
    let bridgeDir = (bridgePath as NSString).deletingLastPathComponent
    let pkgJsonPath = ((bridgeDir as NSString).deletingLastPathComponent as NSString)
      .appendingPathComponent("package.json")
    let pkgJsonExists = FileManager.default.fileExists(atPath: pkgJsonPath)
    log(
      "AgentRuntimeProcess: starting node=\(nodePath) (exists=\(nodeExists)), bridge=\(bridgePath) (exists=\(bridgeExists)), package.json=\(pkgJsonExists)"
    )

    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: nodePath)
    proc.arguments = ["--max-old-space-size=256", "--max-semi-space-size=16", bridgePath]

    var env = ProcessInfo.processInfo.environment
    env["NODE_NO_WARNINGS"] = "1"
    env["HARNESS_MODE"] = preferredHarnessMode
    env["OMI_AGENT_STATE_DIR"] = Self.defaultStateDirectory()
    env.removeValue(forKey: "ANTHROPIC_API_KEY")
    env.removeValue(forKey: "CLAUDE_CODE_USE_VERTEX")

    let rustBase = await APIClient.shared.rustBackendURL
    if !rustBase.isEmpty {
      env["OMI_API_BASE_URL"] = rustBase.hasSuffix("/") ? "\(rustBase)v2" : "\(rustBase)/v2"
    } else if preferredHarnessMode == "piMono" {
      log("AgentRuntimeProcess: pi-mono start refused, OMI_DESKTOP_API_URL is not configured")
      throw BridgeError.bridgeScriptNotFound
    }

    if APIKeyService.isByokActive {
      for provider in BYOKProvider.allCases {
        if let key = APIKeyService.byokKey(provider) {
          env["OMI_BYOK_\(provider.rawValue.uppercased())"] = key
        }
      }
      log("AgentRuntimeProcess: pi-mono BYOK active, forwarding \(BYOKProvider.allCases.count) user keys")
    }

    let authService = await MainActor.run { AuthService.shared }
    if let token = try? await authService.getIdToken(), !token.isEmpty {
      env["OMI_AUTH_TOKEN"] = token
    } else if preferredHarnessMode == "piMono" {
      log("AgentRuntimeProcess: pi-mono start refused, Firebase ID token is missing")
      throw BridgeError.authMissing
    }

    let nodeDir = (nodePath as NSString).deletingLastPathComponent
    let existingPath = env["PATH"] ?? "/usr/bin:/bin"
    if !existingPath.contains(nodeDir) {
      env["PATH"] = "\(nodeDir):\(existingPath)"
    }

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
    stdinPipe = stdin
    stdoutPipe = stdout
    stderrPipe = stderr
    process = proc

    stderr.fileHandleForReading.readabilityHandler = { [weak self] handle in
      let data = handle.availableData
      if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
        log("AgentRuntimeProcess stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
        if text.contains("FatalProcessOutOfMemory")
          || text.contains("JavaScript heap out of memory")
          || text.contains("Failed to reserve virtual memory")
          || text.contains("out of memory")
        {
          Task { await self?.markOOM() }
        }
      }
    }

    processGeneration &+= 1
    let expectedGeneration = processGeneration
    proc.terminationHandler = { [weak self] terminatedProc in
      let code = terminatedProc.terminationStatus
      let reason = terminatedProc.terminationReason
      Task { [weak self] in
        await self?.handleTermination(
          exitCode: code,
          reason: reason,
          generation: expectedGeneration
        )
      }
    }

    try proc.run()
    isRunning = true
    startReadingStdout()

    do {
      try await waitForInit(timeout: 30.0)
    } catch {
      await cleanupFailedStart(process: proc, error: error)
      throw error
    }
  }

  private func cleanupFailedStart(process failedProcess: Process, error: Error) async {
    log("AgentRuntimeProcess: startup failed after launch: \(error)")
    if failedProcess.isRunning {
      failedProcess.terminate()
      let start = Date()
      while failedProcess.isRunning && Date().timeIntervalSince(start) < 1.0 {
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      if failedProcess.isRunning {
        kill(failedProcess.processIdentifier, SIGKILL)
      }
    }
    if let currentProcess = process, currentProcess === failedProcess {
      process = nil
    }
    readTask?.cancel()
    readTask = nil
    closePipes()
    isRunning = false
    receivedInit = false
    resumeAllRequests(throwing: BridgeError.stopped)
    resumeInitContinuations(throwing: BridgeError.stopped)
  }

  private func waitForInit(timeout: TimeInterval) async throws {
    if receivedInit { return }

    let timeoutTask = Task {
      do {
        try await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
        self.resumeInitContinuations(throwing: BridgeError.timeout)
      } catch {
        // Cancelled because init completed first.
      }
    }
    defer { timeoutTask.cancel() }

    try await withCheckedThrowingContinuation { continuation in
      storeInitContinuation(continuation)
    }
  }

  private func storeInitContinuation(_ continuation: CheckedContinuation<Void, Error>) {
    if receivedInit {
      continuation.resume()
      return
    }
    initContinuations.append(continuation)
  }

  private func resolveInitContinuations() {
    let continuations = initContinuations
    initContinuations.removeAll()
    for continuation in continuations {
      continuation.resume()
    }
  }

  private func stopProcess(resumeRequestsWith error: BridgeError) async {
    let proc = process
    sendJson(["type": "stop"])
    try? stdinPipe?.fileHandleForWriting.close()
    proc?.terminate()

    if let proc {
      let pid = proc.processIdentifier
      let start = Date()
      while proc.isRunning && Date().timeIntervalSince(start) < 3.0 {
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      if proc.isRunning && pid > 0 {
        log("AgentRuntimeProcess: process \(pid) still alive after 3s, sending SIGKILL")
        kill(pid, SIGKILL)
        try? await Task.sleep(nanoseconds: 200_000_000)
      }
    }

    readTask?.cancel()
    readTask = nil
    process = nil
    closePipes()
    isRunning = false
    receivedInit = false
    resumeAllRequests(throwing: error)
    resumeInitContinuations(throwing: error)
  }

  private func startReadingStdout() {
    guard let stdoutPipe else { return }

    readTask = Task.detached { [weak self] in
      let handle = stdoutPipe.fileHandleForReading
      var buffer = Data()

      while !Task.isCancelled {
        let chunk = handle.availableData
        if chunk.isEmpty { break }
        buffer.append(chunk)

        while let newlineIndex = buffer.firstIndex(of: UInt8(ascii: "\n")) {
          let lineData = buffer[buffer.startIndex..<newlineIndex]
          buffer = Data(buffer[buffer.index(after: newlineIndex)...])

          guard let line = String(data: lineData, encoding: .utf8),
            !line.trimmingCharacters(in: .whitespaces).isEmpty
          else {
            continue
          }

          if let message = RuntimeMessage.parse(line) {
            await self?.handleMessage(message)
          } else {
            log("AgentRuntimeProcess: failed to parse message: \(line.prefix(200))")
          }
        }
      }
    }
  }

  private func handleMessage(_ message: RuntimeMessage) {
    if let request = routedRequest(for: message), let surfaceRef = request.surfaceRef {
      Task { @MainActor in
        AgentRuntimeStatusStore.shared.ingest(message: message, surface: surfaceRef)
      }
    }

    switch message.kind {
    case .initMessage:
      log("AgentRuntimeProcess: bridge ready (sessionId=\(message.payload["sessionId"] as? String ?? ""))")
      receivedInit = true
      resolveInitContinuations()

    case .authRequired:
      let methods = message.payload["methods"] as? [[String: Any]] ?? []
      let authUrl = message.payload["authUrl"] as? String
      if let request = routedRequest(for: message) {
        request.onAuthRequired(methods, authUrl)
      } else {
        for client in clients.values {
          client.onAuthRequired?(methods, authUrl)
        }
      }

    case .authSuccess:
      if let request = routedRequest(for: message) {
        request.onAuthSuccess()
      } else {
        for client in clients.values {
          client.onAuthSuccess?()
        }
      }

    case .textDelta:
      routedRequest(for: message)?.onTextDelta(message.payload["text"] as? String ?? "")

    case .thinkingDelta:
      routedRequest(for: message)?.onThinkingDelta(message.payload["text"] as? String ?? "")

    case .toolActivity:
      routedRequest(for: message)?.onToolActivity(
        message.payload["name"] as? String ?? "",
        message.payload["status"] as? String ?? "started",
        message.payload["toolUseId"] as? String,
        message.payload["input"] as? [String: Any]
      )

    case .toolResultDisplay:
      routedRequest(for: message)?.onToolResultDisplay(
        message.payload["toolUseId"] as? String ?? "",
        message.payload["name"] as? String ?? "",
        message.payload["output"] as? String ?? ""
      )

    case .toolUse:
      handleToolUse(message)

    case .cancelAck:
      if let requestId = message.routingKey, var request = activeRequests[requestId] {
        request.cancelAck = message
        activeRequests[requestId] = request
      }

    case .result:
      completeRequest(message)

    case .error:
      failRequest(message)

    case .unknown(let type):
      log("AgentRuntimeProcess: unknown message type: \(type)")
    }
  }

  private func routedRequest(for message: RuntimeMessage) -> ActiveRequest? {
    if let requestId = message.routingKey {
      return activeRequests[requestId]
    }
    if activeRequests.count == 1 {
      return activeRequests.values.first
    }
    return nil
  }

  private func handleToolUse(_ message: RuntimeMessage) {
    guard let request = routedRequest(for: message) else {
      log("AgentRuntimeProcess: dropping unroutable tool call")
      return
    }
    if request.isInterrupted {
      log("AgentRuntimeProcess: skipping tool call after interrupt")
      return
    }
    let callId = message.payload["callId"] as? String ?? ""
    let name = message.payload["name"] as? String ?? ""
    let input = message.payload["input"] as? [String: Any] ?? [:]
    Task {
      let result = await request.onToolCall(callId, name, input)
      completeToolCall(callId: callId, result: result)
    }
  }

  private func completeToolCall(callId: String, result: String) {
    sendJson([
      "type": "tool_result",
      "callId": callId,
      "result": result,
    ])
  }

  private func completeRequest(_ message: RuntimeMessage) {
    guard let requestId = message.routingKey, let request = activeRequests.removeValue(forKey: requestId) else {
      log("AgentRuntimeProcess: dropping unroutable result")
      return
    }
    if (message.payload["terminalStatus"] as? String) == "cancelled" {
      request.continuation.resume(throwing: BridgeError.stopped)
      return
    }
    request.continuation.resume(returning: queryResult(from: message))
  }

  private func failRequest(_ message: RuntimeMessage) {
    guard let requestId = message.routingKey, let request = activeRequests.removeValue(forKey: requestId) else {
      log("AgentRuntimeProcess: dropping unroutable error")
      return
    }
    let raw = message.payload["message"] as? String ?? "Unknown error"
    log("AgentRuntimeProcess: agent error (raw): \(raw)")
    request.continuation.resume(throwing: BridgeError.agentError(raw))
  }

  private func queryResult(from message: RuntimeMessage) -> AgentBridge.QueryResult {
    let payload = message.payload
    let omiSessionId = payload["sessionId"] as? String ?? message.payload["omiSessionId"] as? String ?? ""
    let adapterSessionId =
      payload["adapterSessionId"] as? String
      ?? payload["legacyAdapterSessionId"] as? String
    return AgentBridge.QueryResult(
      text: payload["text"] as? String ?? "",
      costUsd: payload["costUsd"] as? Double ?? 0,
      omiSessionId: omiSessionId,
      runId: payload["runId"] as? String ?? "",
      attemptId: payload["attemptId"] as? String ?? "",
      adapterSessionId: adapterSessionId,
      terminalStatus: payload["terminalStatus"] as? String ?? "succeeded",
      inputTokens: payload["inputTokens"] as? Int ?? 0,
      outputTokens: payload["outputTokens"] as? Int ?? 0,
      cacheReadTokens: payload["cacheReadTokens"] as? Int ?? 0,
      cacheWriteTokens: payload["cacheWriteTokens"] as? Int ?? 0
    )
  }

  private func sendJson(_ dict: [String: Any]) {
    guard let stdinPipe else { return }
    do {
      let data = try JSONSerialization.data(withJSONObject: dict)
      guard let line = String(data: data, encoding: .utf8) else { return }
      try stdinPipe.fileHandleForWriting.write(contentsOf: Data((line + "\n").utf8))
    } catch {
      log("AgentRuntimeProcess: failed to write stdin: \(error.localizedDescription)")
    }
  }

  private func currentOwnerId() -> String? {
    guard let value = UserDefaults.standard.string(forKey: "auth_userId"), !value.isEmpty else {
      return nil
    }
    return value
  }

  private func markOOM() {
    lastExitWasOOM = true
  }

  private func handleTermination(
    exitCode: Int32 = -1,
    reason: Process.TerminationReason = .exit,
    generation: UInt64? = nil
  ) {
    if let generation, generation != processGeneration {
      log("AgentRuntimeProcess: ignoring stale termination (gen=\(generation), current=\(processGeneration))")
      return
    }

    if let stderrHandle = stderrPipe?.fileHandleForReading {
      stderrHandle.readabilityHandler = nil
      let remaining = stderrHandle.availableData
      if !remaining.isEmpty, let text = String(data: remaining, encoding: .utf8) {
        log("AgentRuntimeProcess stderr (final): \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
        if text.contains("out of memory") || text.contains("Failed to reserve virtual memory") {
          lastExitWasOOM = true
        }
      }
    }

    let likelyOOM =
      lastExitWasOOM
      || (reason == .uncaughtSignal
        && (exitCode == 134 || exitCode == 133 || exitCode == 5 || exitCode == 6))
    let error: BridgeError = likelyOOM ? .outOfMemory : .processExited
    lastExitWasOOM = false

    log("AgentRuntimeProcess: process terminated (code=\(exitCode), error=\(error))")
    isRunning = false
    receivedInit = false
    closePipes()
    resumeAllRequests(throwing: error)
    resumeInitContinuations(throwing: error)
  }

  private func resumeAllRequests(throwing error: Error) {
    let requests = activeRequests.values
    activeRequests.removeAll()
    for request in requests {
      request.continuation.resume(throwing: error)
    }
  }

  private func resumeInitContinuations(throwing error: Error) {
    let continuations = initContinuations
    initContinuations.removeAll()
    for continuation in continuations {
      continuation.resume(throwing: error)
    }
  }

  private func closePipes() {
    if let stdinPipe {
      try? stdinPipe.fileHandleForWriting.close()
      try? stdinPipe.fileHandleForReading.close()
    }
    if let stdoutPipe {
      stdoutPipe.fileHandleForReading.readabilityHandler = nil
      try? stdoutPipe.fileHandleForReading.close()
      try? stdoutPipe.fileHandleForWriting.close()
    }
    if let stderrPipe {
      stderrPipe.fileHandleForReading.readabilityHandler = nil
      try? stderrPipe.fileHandleForReading.close()
      try? stderrPipe.fileHandleForWriting.close()
    }
    stdinPipe = nil
    stdoutPipe = nil
    stderrPipe = nil
  }

  static func defaultStateDirectory(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) -> String {
    let bundleComponent = (bundleIdentifier?.isEmpty == false ? bundleIdentifier : "com.omi.desktop-dev")
      ?? "com.omi.desktop-dev"
    return homeDirectory
      .appendingPathComponent("Library")
      .appendingPathComponent("Application Support")
      .appendingPathComponent("Omi")
      .appendingPathComponent("AgentRuntime")
      .appendingPathComponent(bundleComponent)
      .path
  }

  private func findNodeBinary() -> String? {
    let bundledNode = Bundle.resourceBundle.path(forResource: "node", ofType: nil)
    if let bundledNode, FileManager.default.isExecutableFile(atPath: bundledNode) {
      return bundledNode
    }

    let candidates = [
      "/opt/homebrew/bin/node",
      "/usr/local/bin/node",
      "/usr/bin/node",
    ]
    for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
      return path
    }

    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let nvmDir = (home as NSString).appendingPathComponent(".nvm/versions/node")
    if let versions = try? FileManager.default.contentsOfDirectory(atPath: nvmDir) {
      let sorted = versions.sorted { lhs, rhs in
        lhs.compare(rhs, options: .numeric) == .orderedDescending
      }
      for version in sorted {
        let nodePath = (nvmDir as NSString).appendingPathComponent("\(version)/bin/node")
        if FileManager.default.isExecutableFile(atPath: nodePath) {
          return nodePath
        }
      }
    }

    let whichProcess = Process()
    whichProcess.executableURL = URL(fileURLWithPath: "/usr/bin/which")
    whichProcess.arguments = ["node"]
    let pipe = Pipe()
    whichProcess.standardOutput = pipe
    try? whichProcess.run()
    whichProcess.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
      !path.isEmpty,
      FileManager.default.isExecutableFile(atPath: path)
    {
      return path
    }

    return nil
  }

  private func findBridgeScript() -> String? {
    if let bundlePath = Bundle.main.resourcePath {
      let bundledScript = (bundlePath as NSString).appendingPathComponent("agent/dist/index.js")
      if FileManager.default.fileExists(atPath: bundledScript) {
        return bundledScript
      }
    }

    if let execDir = Bundle.main.executableURL?.deletingLastPathComponent() {
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
