import Foundation

/// Manages a long-lived Node.js subprocess running the Claude Agent SDK bridge.
/// Communication uses JSON lines over stdin/stdout pipes.
actor ClaudeAgentBridge {

    // MARK: - Types

    /// Result from a query
    struct QueryResult {
        let text: String
        let costUsd: Double
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

    /// Inbound message types (Bridge → Swift, read from stdout)
    private enum InboundMessage {
        case `init`(sessionId: String)
        case textDelta(text: String)
        case thinkingDelta(text: String)
        case toolUse(callId: String, name: String, input: [String: Any])
        case toolActivity(name: String, status: String, toolUseId: String?, input: [String: Any]?)
        case toolResultDisplay(toolUseId: String, name: String, output: String)
        case result(text: String, sessionId: String, costUsd: Double?)
        case error(message: String)
    }

    // MARK: - State

    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private var isRunning = false
    private var readTask: Task<Void, Never>?

    /// Pending messages from the bridge
    private var pendingMessages: [InboundMessage] = []
    private var messageContinuation: CheckedContinuation<InboundMessage, Error>?
    private var messageGeneration: UInt64 = 0

    /// Whether the bridge subprocess is alive and ready
    var isAlive: Bool { isRunning }

    // MARK: - Lifecycle

    /// Start the Node.js bridge process (safe to call after a crash — cleans up old state)
    func start() async throws {
        guard !isRunning else { return }

        // Clean up any leftover state from a previous crashed process
        readTask?.cancel()
        readTask = nil
        process = nil
        stdinPipe = nil
        stdoutPipe = nil
        stderrPipe = nil
        pendingMessages.removeAll()
        messageContinuation = nil

        let nodePath = findNodeBinary()
        guard let nodePath else {
            throw BridgeError.nodeNotFound
        }

        // Find the bridge script
        let bridgePath = findBridgeScript()
        guard let bridgePath else {
            throw BridgeError.bridgeScriptNotFound
        }

        log("ClaudeAgentBridge: starting with node=\(nodePath), bridge=\(bridgePath)")

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: nodePath)
        proc.arguments = [bridgePath]

        // Inherit environment (includes ANTHROPIC_API_KEY from .env)
        var env = ProcessInfo.processInfo.environment
        env["NODE_NO_WARNINGS"] = "1"
        // Ensure the directory containing node is in PATH so child processes (e.g. claude-agent-sdk) can find it
        let nodeDir = (nodePath as NSString).deletingLastPathComponent
        let existingPath = env["PATH"] ?? "/usr/bin:/bin"
        if !existingPath.contains(nodeDir) {
            env["PATH"] = "\(nodeDir):\(existingPath)"
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

        // Read stderr for logging
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                log("ClaudeAgentBridge stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }

        proc.terminationHandler = { [weak self] _ in
            Task { [weak self] in
                await self?.handleTermination()
            }
        }

        try proc.run()
        isRunning = true

        // Start reading stdout
        startReadingStdout()

        // Wait for the initial "init" message indicating bridge is ready
        let initMsg = try await waitForMessage(timeout: 30.0)
        if case .`init`(let sessionId) = initMsg {
            log("ClaudeAgentBridge: bridge ready (sessionId=\(sessionId))")
        }
    }

    /// Stop the bridge process
    func stop() {
        log("ClaudeAgentBridge: stopping")
        readTask?.cancel()
        readTask = nil

        // Send stop message
        sendLine("""
        {"type":"stop"}
        """)

        process?.terminate()
        process = nil
        stdinPipe = nil
        stdoutPipe = nil
        stderrPipe = nil
        isRunning = false

        // Cancel any pending continuation
        messageContinuation?.resume(throwing: BridgeError.stopped)
        messageContinuation = nil
    }

    // MARK: - Query

    /// Send a query to the Claude agent and stream results back.
    /// Each query is standalone — conversation history is passed via the system prompt.
    /// This ensures cross-platform sync (messages from mobile/other clients are included).
    /// - Parameters:
    ///   - prompt: User's message
    ///   - systemPrompt: System prompt with context and conversation history
    ///   - onTextDelta: Called for each streaming text chunk
    ///   - onToolCall: Called when an OMI tool needs Swift execution
    /// - Returns: Query result with response text and cost
    func query(
        prompt: String,
        systemPrompt: String,
        cwd: String? = nil,
        mode: String? = nil,
        onTextDelta: @escaping TextDeltaHandler,
        onToolCall: @escaping ToolCallHandler,
        onToolActivity: @escaping ToolActivityHandler,
        onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
        onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in }
    ) async throws -> QueryResult {
        guard isRunning else {
            throw BridgeError.notRunning
        }

        // Build query message — no session resume, each query is independent
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

        let jsonData = try JSONSerialization.data(withJSONObject: queryDict)
        guard let jsonString = String(data: jsonData, encoding: .utf8) else {
            throw BridgeError.encodingError
        }

        sendLine(jsonString)

        // Read messages until we get a result or error
        while true {
            let message = try await waitForMessage()

            switch message {
            case .`init`:
                log("ClaudeAgentBridge: new session started")

            case .textDelta(let text):
                onTextDelta(text)

            case .toolUse(let callId, let name, let input):
                // Route OMI tool calls back to Swift for execution
                let result = await onToolCall(callId, name, input)
                // Send result back to bridge
                let resultDict: [String: Any] = [
                    "type": "tool_result",
                    "callId": callId,
                    "result": result
                ]
                let resultData = try JSONSerialization.data(withJSONObject: resultDict)
                if let resultString = String(data: resultData, encoding: .utf8) {
                    sendLine(resultString)
                }

            case .thinkingDelta(let text):
                onThinkingDelta(text)

            case .toolActivity(let name, let status, let toolUseId, let input):
                onToolActivity(name, status, toolUseId, input)

            case .toolResultDisplay(let toolUseId, let name, let output):
                onToolResultDisplay(toolUseId, name, output)

            case .result(let text, _, let costUsd):
                return QueryResult(text: text, costUsd: costUsd ?? 0)

            case .error(let message):
                throw BridgeError.agentError(message)
            }
        }
    }

    // MARK: - Streaming Input Controls

    /// Interrupt the running agent, keeping partial response.
    /// The bridge will abort the current query and send back a partial result.
    func interrupt() {
        guard isRunning else { return }
        sendLine("{\"type\":\"interrupt\"}")
    }

    // MARK: - Private

    private func sendLine(_ line: String) {
        guard let pipe = stdinPipe else { return }
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if let data = (trimmed + "\n").data(using: .utf8) {
            pipe.fileHandleForWriting.write(data)
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
                    // EOF
                    break
                }
                buffer.append(chunk)

                // Process complete lines
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
            log("ClaudeAgentBridge: failed to parse message: \(json.prefix(200))")
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
            return .result(text: text, sessionId: sessionId, costUsd: costUsd)

        case "error":
            let message = dict["message"] as? String ?? "Unknown error"
            return .error(message: message)

        default:
            log("ClaudeAgentBridge: unknown message type: \(type)")
            return nil
        }
    }

    private func deliverMessage(_ message: InboundMessage) {
        if let continuation = messageContinuation {
            messageContinuation = nil
            continuation.resume(returning: message)
        } else {
            pendingMessages.append(message)
        }
    }

    private func waitForMessage(timeout: TimeInterval? = nil) async throws -> InboundMessage {
        // Check pending first
        if !pendingMessages.isEmpty {
            return pendingMessages.removeFirst()
        }

        // Increment generation so stale timeout tasks become no-ops
        messageGeneration &+= 1
        let expectedGeneration = messageGeneration

        // Wait for next message (with optional timeout)
        return try await withCheckedThrowingContinuation { continuation in
            self.messageContinuation = continuation

            // Set up timeout only if specified — process termination handler covers crash cases
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

    private func handleTermination() {
        log("ClaudeAgentBridge: process terminated")
        isRunning = false
        messageContinuation?.resume(throwing: BridgeError.processExited)
        messageContinuation = nil
    }

    // MARK: - Node.js Discovery

    private func findNodeBinary() -> String? {
        // 1. Check bundled node binary in app resources (preferred — no external dependency)
        if let bundledNode = Bundle.resourceBundle.path(forResource: "node", ofType: nil),
           FileManager.default.isExecutableFile(atPath: bundledNode) {
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

        // 3. Try `which node`
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

    private func findBridgeScript() -> String? {
        // 1. Check in app bundle Resources
        if let bundlePath = Bundle.main.resourcePath {
            let bundledScript = (bundlePath as NSString).appendingPathComponent("agent-bridge/dist/index.js")
            if FileManager.default.fileExists(atPath: bundledScript) {
                return bundledScript
            }
        }

        // 2. Check relative to executable (development mode)
        let executableURL = Bundle.main.executableURL
        if let execDir = executableURL?.deletingLastPathComponent() {
            // In dev, binary is at Desktop/.build/debug/Omi Computer
            // agent-bridge is at repo root
            let devPaths = [
                execDir.appendingPathComponent("../../../agent-bridge/dist/index.js").path,
                execDir.appendingPathComponent("../../../../agent-bridge/dist/index.js").path,
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
        let cwdScript = (cwdPath as NSString).appendingPathComponent("agent-bridge/dist/index.js")
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
    case stopped
    case agentError(String)

    var errorDescription: String? {
        switch self {
        case .nodeNotFound:
            return "Node.js not found. Install via: brew install node"
        case .bridgeScriptNotFound:
            return "Agent bridge script not found"
        case .notRunning:
            return "Agent bridge is not running"
        case .encodingError:
            return "Failed to encode message"
        case .timeout:
            return "Agent bridge timed out"
        case .processExited:
            return "Agent bridge process exited unexpectedly"
        case .stopped:
            return "Agent bridge was stopped"
        case .agentError(let msg):
            return "Agent error: \(msg)"
        }
    }
}
