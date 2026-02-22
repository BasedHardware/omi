import Foundation

/// Manages a long-lived Node.js subprocess running the ACP (Agent Client Protocol) bridge.
/// This is the sole bridge for AI chat — supports both OMI's API key (passApiKey=true)
/// and user's own Claude account via OAuth (passApiKey=false).
/// Communication uses JSON lines over stdin/stdout pipes.
actor ACPBridge {

    // MARK: - Types

    /// Result from a query
    struct QueryResult {
        let text: String
        let costUsd: Double
        let sessionId: String
        let inputTokens: Int
        let outputTokens: Int
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
        case result(text: String, sessionId: String, costUsd: Double?, inputTokens: Int, outputTokens: Int)
        case error(message: String)
        case authRequired(methods: [[String: Any]], authUrl: String?)
        case authSuccess
    }

    // MARK: - Configuration

    /// When true, ANTHROPIC_API_KEY is passed through to the ACP subprocess
    /// (Mode A: OMI's key). When false, the key is stripped so ACP uses OAuth.
    let passApiKey: Bool

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

    init(passApiKey: Bool = false) {
        self.passApiKey = passApiKey
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

    /// Whether the bridge subprocess is alive and ready
    var isAlive: Bool { isRunning }

    // MARK: - Lifecycle

    /// Start the Node.js ACP bridge process
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
        let pkgJsonPath = ((bridgeDir as NSString).deletingLastPathComponent as NSString).appendingPathComponent("package.json")
        let pkgJsonExists = FileManager.default.fileExists(atPath: pkgJsonPath)
        log("ACPBridge: starting with node=\(nodePath) (exists=\(nodeExists)), bridge=\(bridgePath) (exists=\(bridgeExists)), package.json=\(pkgJsonExists)")

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: nodePath)
        proc.arguments = ["--max-old-space-size=256", "--max-semi-space-size=16", bridgePath]

        // Build environment
        var env = ProcessInfo.processInfo.environment
        env["NODE_NO_WARNINGS"] = "1"
        if !passApiKey {
            // Mode B: Strip API key so ACP uses user's own OAuth
            env.removeValue(forKey: "ANTHROPIC_API_KEY")
        }
        // else: Mode A: Keep ANTHROPIC_API_KEY for OMI's key
        env.removeValue(forKey: "CLAUDE_CODE_USE_VERTEX")

        // Ensure the directory containing node is in PATH
        let nodeDir = (nodePath as NSString).deletingLastPathComponent
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        if !existingPath.contains(nodeDir) {
            env["PATH"] = "\(nodeDir):\(existingPath)"
        }

        // Playwright MCP extension mode
        let defaults = UserDefaults.standard
        let useExtension = defaults.object(forKey: "playwrightUseExtension") == nil || defaults.bool(forKey: "playwrightUseExtension")
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
                log("ACPBridge stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
                if text.contains("FatalProcessOutOfMemory")
                    || text.contains("JavaScript heap out of memory")
                    || text.contains("Failed to reserve virtual memory")
                    || text.contains("out of memory") {
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
                await self?.handleTermination(exitCode: code, reason: reason, generation: expectedGeneration)
            }
        }

        try proc.run()
        isRunning = true

        // Start reading stdout
        startReadingStdout()

        // Wait for the initial "init" message indicating bridge is ready
        let initMsg = try await waitForMessage(timeout: 30.0)
        if case .`init`(let sessionId) = initMsg {
            log("ACPBridge: bridge ready (sessionId=\(sessionId))")
        }
    }

    /// Restart the bridge process (stop then start)
    func restart() async throws {
        stop()
        try await start()
    }

    /// Stop the bridge process
    func stop() {
        log("ACPBridge: stopping")
        readTask?.cancel()
        readTask = nil

        sendLine("""
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
            "methodId": methodId
        ]
        if let data = try? JSONSerialization.data(withJSONObject: msg),
           let jsonString = String(data: data, encoding: .utf8) {
            sendLine(jsonString)
        }
    }

    // MARK: - Session Pre-warming

    /// Tell the bridge to pre-create ACP sessions in the background.
    /// This saves ~4s on the first query by doing session/new ahead of time.
    /// Pass multiple models to pre-warm sessions for both Opus and Sonnet in parallel.
    func warmupSession(cwd: String? = nil, models: [String]? = nil) {
        guard isRunning else { return }
        var dict: [String: Any] = ["type": "warmup"]
        if let cwd = cwd { dict["cwd"] = cwd }
        if let models = models { dict["models"] = models }
        if let data = try? JSONSerialization.data(withJSONObject: dict),
           let str = String(data: data, encoding: .utf8) {
            sendLine(str)
        }
    }

    // MARK: - Query

    /// Send a query to the ACP agent and stream results back.
    func query(
        prompt: String,
        systemPrompt: String,
        cwd: String? = nil,
        mode: String? = nil,
        model: String? = nil,
        resume: String? = nil,
        onTextDelta: @escaping TextDeltaHandler,
        onToolCall: @escaping ToolCallHandler,
        onToolActivity: @escaping ToolActivityHandler,
        onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
        onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
        onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
        onAuthSuccess: @escaping AuthSuccessHandler = { }
    ) async throws -> QueryResult {
        guard isRunning else {
            throw BridgeError.notRunning
        }

        var queryDict: [String: Any] = [
            "type": "query",
            "id": UUID().uuidString,
            "prompt": prompt,
            "systemPrompt": systemPrompt
        ]
        if let cwd = cwd {
            queryDict["cwd"] = cwd
        }
        if let mode = mode {
            queryDict["mode"] = mode
        }
        if let model = model {
            queryDict["model"] = model
        }

        let jsonData = try JSONSerialization.data(withJSONObject: queryDict)
        guard let jsonString = String(data: jsonData, encoding: .utf8) else {
            throw BridgeError.encodingError
        }

        isInterrupted = false
        // Discard any stale messages from a previous interrupted/timed-out query
        // to avoid desynchronizing the request-response protocol.
        if !pendingMessages.isEmpty {
            log("ACPBridge: clearing \(pendingMessages.count) stale pending messages before new query")
            pendingMessages.removeAll()
        }
        sendLine(jsonString)

        // Read messages until we get a result or error
        while true {
            let message = try await waitForMessage(timeout: 90.0)

            switch message {
            case .`init`:
                log("ACPBridge: new session started")

            case .textDelta(let text):
                onTextDelta(text)

            case .toolUse(let callId, let name, let input):
                // If already interrupted, skip this tool call entirely
                if isInterrupted {
                    log("ACPBridge: skipping tool call \(name) (interrupted)")
                    continue
                }
                let result = await onToolCall(callId, name, input)
                let resultDict: [String: Any] = [
                    "type": "tool_result",
                    "callId": callId,
                    "result": result
                ]
                let resultData = try JSONSerialization.data(withJSONObject: resultDict)
                if let resultString = String(data: resultData, encoding: .utf8) {
                    sendLine(resultString)
                }

                // If interrupted during tool execution, skip remaining tool calls
                // and drain messages to find the result (already sent by the bridge).
                if isInterrupted {
                    log("ACPBridge: interrupted during tool call, draining for result")
                    while !pendingMessages.isEmpty {
                        let pending = pendingMessages.removeFirst()
                        switch pending {
                        case .result(let text, let sessionId, let costUsd, let inputTokens, let outputTokens):
                            return QueryResult(text: text, costUsd: costUsd ?? 0, sessionId: sessionId, inputTokens: inputTokens, outputTokens: outputTokens)
                        case .error(let message):
                            throw BridgeError.agentError(message)
                        default:
                            continue
                        }
                    }
                    while true {
                        let msg = try await waitForMessage(timeout: 10.0)
                        switch msg {
                        case .result(let text, let sessionId, let costUsd, let inputTokens, let outputTokens):
                            return QueryResult(text: text, costUsd: costUsd ?? 0, sessionId: sessionId, inputTokens: inputTokens, outputTokens: outputTokens)
                        case .error(let message):
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

            case .result(let text, let sessionId, let costUsd, let inputTokens, let outputTokens):
                return QueryResult(text: text, costUsd: costUsd ?? 0, sessionId: sessionId, inputTokens: inputTokens, outputTokens: outputTokens)

            case .error(let message):
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

    // MARK: - Private

    private func sendLine(_ line: String) {
        guard let pipe = stdinPipe else { return }
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if let data = (trimmed + "\n").data(using: .utf8) {
            do {
                try pipe.fileHandleForWriting.write(contentsOf: data)
            } catch {
                log("ACPBridge: Failed to write to stdin pipe: \(error.localizedDescription)")
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
                          !lineStr.trimmingCharacters(in: .whitespaces).isEmpty else {
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
              let type = dict["type"] as? String else {
            log("ACPBridge: failed to parse message: \(json.prefix(200))")
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
            return .result(text: text, sessionId: sessionId, costUsd: costUsd,
                           inputTokens: inputTokens, outputTokens: outputTokens)

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
            log("ACPBridge: unknown message type: \(type)")
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

    private func handleTermination(exitCode: Int32 = -1, reason: Process.TerminationReason = .exit, generation: UInt64? = nil) {
        // Ignore stale termination from a previous process (fixes race where old handler closes new pipes)
        if let gen = generation, gen != processGeneration {
            log("ACPBridge: ignoring stale termination (gen=\(gen), current=\(processGeneration))")
            return
        }

        let reasonStr = reason == .uncaughtSignal ? "signal" : "exit"

        // Capture any remaining stderr before closing pipes (may reveal OOM)
        if let stderrHandle = stderrPipe?.fileHandleForReading {
            stderrHandle.readabilityHandler = nil  // Stop async handler
            let remaining = stderrHandle.availableData
            if !remaining.isEmpty, let text = String(data: remaining, encoding: .utf8) {
                log("ACPBridge stderr (final): \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
                if text.contains("out of memory") || text.contains("Failed to reserve virtual memory") {
                    lastExitWasOOM = true
                }
            }
        }

        // SIGABRT (134) and SIGTRAP (133/5) with uncaughtSignal are typical V8 OOM crashes
        let likelyOOM = lastExitWasOOM
            || (reason == .uncaughtSignal && (exitCode == 134 || exitCode == 133 || exitCode == 5 || exitCode == 6))
        let error: BridgeError = likelyOOM ? .outOfMemory : .processExited
        lastExitWasOOM = false

        log("ACPBridge: process terminated (code=\(exitCode), reason=\(reasonStr), error=\(error))")
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
            "/usr/bin/node"
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
        if let path = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
           !path.isEmpty,
           FileManager.default.isExecutableFile(atPath: path) {
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

        log("ACPBridge: Testing Playwright connection...")
        let result = try await query(
            prompt: "Call browser_snapshot to verify the extension is connected. Only call that one tool, then report success or failure.",
            systemPrompt: "You are a connection test agent. Call the browser_snapshot tool exactly once. If it succeeds, respond with exactly 'CONNECTED'. If it fails, respond with 'FAILED' followed by the error.",
            mode: "ask",
            onTextDelta: { _ in },
            onToolCall: { _, _, _ in "" },
            onToolActivity: { name, status, _, _ in
                log("ACPBridge: test tool activity: \(name) \(status)")
            },
            onThinkingDelta: { _ in },
            onToolResultDisplay: { _, name, output in
                log("ACPBridge: test tool result: \(name) -> \(output.prefix(200))")
            }
        )
        let connected = result.text.contains("CONNECTED")
        log("ACPBridge: Playwright test response: \(result.text.prefix(300)), connected=\(connected)")
        return connected
    }

    private func findBridgeScript() -> String? {
        // 1. Check in app bundle Resources
        if let bundlePath = Bundle.main.resourcePath {
            let bundledScript = (bundlePath as NSString).appendingPathComponent("acp-bridge/dist/index.js")
            if FileManager.default.fileExists(atPath: bundledScript) {
                return bundledScript
            }
        }

        // 2. Check relative to executable (development mode)
        let executableURL = Bundle.main.executableURL
        if let execDir = executableURL?.deletingLastPathComponent() {
            let devPaths = [
                execDir.appendingPathComponent("../../../acp-bridge/dist/index.js").path,
                execDir.appendingPathComponent("../../../../acp-bridge/dist/index.js").path,
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
        let cwdScript = (cwdPath as NSString).appendingPathComponent("acp-bridge/dist/index.js")
        if FileManager.default.fileExists(atPath: cwdScript) {
            return cwdScript
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

    var errorDescription: String? {
        switch self {
        case .nodeNotFound:
            return "Node.js not found. Please reinstall the app."
        case .bridgeScriptNotFound:
            return "AI components missing. Please reinstall the app."
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
        case .agentError(let msg):
            return "Agent error: \(msg)"
        }
    }
}
