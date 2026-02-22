import Foundation

/// Manages a long-lived Node.js subprocess running the Claude Agent SDK bridge.
/// Communication uses JSON lines over stdin/stdout pipes.
actor ClaudeAgentBridge {

    // MARK: - Types

    /// Result from a query
    struct QueryResult {
        let text: String
        let costUsd: Double
        let sessionId: String
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
    /// Set when stderr indicates OOM so handleTermination can throw the right error
    private var lastExitWasOOM = false
    /// Set when interrupt() is called so query() can skip remaining tool calls
    private var isInterrupted = false

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
        closePipes()
        pendingMessages.removeAll()
        messageContinuation = nil
        lastExitWasOOM = false

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
        // Use --jitless to avoid V8 CodeRange virtual memory reservation failures
        // on constrained environments (macOS VMs, low-memory machines).
        // The agent-bridge is I/O-bound so JIT makes no noticeable difference.
        proc.arguments = ["--jitless", bridgePath]

        // Inherit environment (includes ANTHROPIC_API_KEY from .env)
        var env = ProcessInfo.processInfo.environment
        env["NODE_NO_WARNINGS"] = "1"
        // Note: do NOT set NODE_OPTIONS=--jitless here. The bridge process gets
        // --jitless via proc.arguments (it only does stdin/stdout, no HTTP).
        // Child processes (Claude Code CLI, MCP servers) need WebAssembly for
        // Node.js fetch (undici/llhttp). Instead, the node binary is signed with
        // JIT entitlements in release.sh to allow V8 JIT under Hardened Runtime.
        // Ensure the directory containing node is in PATH so child processes (e.g. claude-agent-sdk) can find it
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
                log("ClaudeAgentBridge stderr: \(text.trimmingCharacters(in: .whitespacesAndNewlines))")
                if text.contains("FatalProcessOutOfMemory") || text.contains("JavaScript heap out of memory") {
                    Task { await self?.markOOM() }
                }
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

    /// Restart the bridge process (stop then start)
    func restart() async throws {
        stop()
        try await start()
    }

    /// Stop the bridge process
    func stop() {
        log("ClaudeAgentBridge: stopping")
        readTask?.cancel()
        readTask = nil

        // Send stop message, then close stdin so Node sees EOF
        sendLine("""
        {"type":"stop"}
        """)
        try? stdinPipe?.fileHandleForWriting.close()

        process?.terminate()
        process = nil
        // Close remaining pipe handles before releasing
        closePipes()
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
        model: String? = nil,
        resume: String? = nil,
        onTextDelta: @escaping TextDeltaHandler,
        onToolCall: @escaping ToolCallHandler,
        onToolActivity: @escaping ToolActivityHandler,
        onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
        onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in }
    ) async throws -> QueryResult {
        guard isRunning else {
            throw BridgeError.notRunning
        }

        // Build query message
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
        if let resume = resume {
            queryDict["resume"] = resume
        }

        let jsonData = try JSONSerialization.data(withJSONObject: queryDict)
        guard let jsonString = String(data: jsonData, encoding: .utf8) else {
            throw BridgeError.encodingError
        }

        isInterrupted = false
        // Discard any stale messages from a previous interrupted/timed-out query
        // to avoid desynchronizing the request-response protocol.
        if !pendingMessages.isEmpty {
            log("ClaudeAgentBridge: clearing \(pendingMessages.count) stale pending messages before new query")
            pendingMessages.removeAll()
        }
        sendLine(jsonString)

        // Read messages until we get a result or error
        while true {
            let message = try await waitForMessage(timeout: 90.0)

            switch message {
            case .`init`:
                log("ClaudeAgentBridge: new session started")

            case .textDelta(let text):
                onTextDelta(text)

            case .toolUse(let callId, let name, let input):
                // If already interrupted, skip this tool call entirely
                if isInterrupted {
                    log("ClaudeAgentBridge: skipping tool call \(name) (interrupted)")
                    continue
                }
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

                // If interrupted during tool execution, skip remaining tool calls
                // and drain messages to find the result (already sent by the bridge).
                if isInterrupted {
                    log("ClaudeAgentBridge: interrupted during tool call, draining for result")
                    // First check already-buffered messages
                    while !pendingMessages.isEmpty {
                        let pending = pendingMessages.removeFirst()
                        switch pending {
                        case .result(let text, let sessionId, let costUsd):
                            return QueryResult(text: text, costUsd: costUsd ?? 0, sessionId: sessionId)
                        case .error(let message):
                            throw BridgeError.agentError(message)
                        default:
                            continue
                        }
                    }
                    // Result not yet buffered — wait with a short timeout
                    while true {
                        let msg = try await waitForMessage(timeout: 10.0)
                        switch msg {
                        case .result(let text, let sessionId, let costUsd):
                            return QueryResult(text: text, costUsd: costUsd ?? 0, sessionId: sessionId)
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

            case .result(let text, let sessionId, let costUsd):
                return QueryResult(text: text, costUsd: costUsd ?? 0, sessionId: sessionId)

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
                log("ClaudeAgentBridge: Failed to write to stdin pipe: \(error.localizedDescription)")
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

    private func markOOM() {
        lastExitWasOOM = true
    }

    private func handleTermination() {
        let error: BridgeError = lastExitWasOOM ? .outOfMemory : .processExited
        lastExitWasOOM = false
        log("ClaudeAgentBridge: process terminated (\(error))")
        isRunning = false
        closePipes()
        messageContinuation?.resume(throwing: error)
        messageContinuation = nil
    }

    /// Close all pipe file handles to prevent fd leaks and EPIPE in the child
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
        // 1. Check bundled node binary in app resources (preferred — no external dependency)
        let bundledNode = Bundle.resourceBundle.path(forResource: "node", ofType: nil)
        if let bundledNode, FileManager.default.isExecutableFile(atPath: bundledNode) {
            log("Bridge: Found bundled node at \(bundledNode)")
            return bundledNode
        }
        // Log why bundled node failed
        let bundleURL = Bundle.resourceBundle.bundleURL.path
        let mainBundleURL = Bundle.main.bundleURL.path
        if let bundledNode {
            log("Bridge: Bundled node at \(bundledNode) is not executable")
        } else {
            log("Bridge: No bundled node found in resourceBundle (\(bundleURL)), main bundle (\(mainBundleURL))")
            // List what's actually in the resource bundle for debugging
            if let contents = try? FileManager.default.contentsOfDirectory(atPath: bundleURL) {
                log("Bridge: resourceBundle contents: \(contents.prefix(20))")
            }
        }

        // 2. Fall back to system-installed node
        let candidates = [
            "/opt/homebrew/bin/node",
            "/usr/local/bin/node",
            "/usr/bin/node"
        ]

        for path in candidates {
            if FileManager.default.isExecutableFile(atPath: path) {
                log("Bridge: Found system node at \(path)")
                return path
            }
        }
        log("Bridge: No system node found at \(candidates)")

        // 3. Check NVM installations (~/.nvm/versions/node/*)
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let nvmDir = (home as NSString).appendingPathComponent(".nvm/versions/node")
        if let versions = try? FileManager.default.contentsOfDirectory(atPath: nvmDir) {
            // Sort versions descending to prefer the latest
            let sorted = versions.sorted { v1, v2 in
                v1.compare(v2, options: .numeric) == .orderedDescending
            }
            for version in sorted {
                let nodePath = (nvmDir as NSString).appendingPathComponent("\(version)/bin/node")
                if FileManager.default.isExecutableFile(atPath: nodePath) {
                    log("Bridge: Found NVM node at \(nodePath)")
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
            log("Bridge: Found node via 'which' at \(path)")
            return path
        }

        logError("Bridge: Node.js not found anywhere. Bundle: \(bundleURL), main: \(mainBundleURL)")
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

    // MARK: - Playwright Connection Test

    /// Test that the Playwright Chrome extension is connected and working.
    /// Sends a minimal query that triggers a browser_snapshot tool call.
    /// Returns true if the extension responds successfully.
    func testPlaywrightConnection() async throws -> Bool {
        guard isRunning else {
            throw BridgeError.notRunning
        }

        log("ClaudeAgentBridge: Testing Playwright connection...")
        let result = try await query(
            prompt: "Call browser_snapshot to verify the extension is connected. Only call that one tool, then report success or failure.",
            systemPrompt: "You are a connection test agent. Call the browser_snapshot tool exactly once. If it succeeds, respond with exactly 'CONNECTED'. If it fails, respond with 'FAILED' followed by the error.",
            mode: "ask",
            onTextDelta: { _ in },
            onToolCall: { _, _, _ in "" },
            onToolActivity: { name, status, _, _ in
                log("ClaudeAgentBridge: test tool activity: \(name) \(status)")
            },
            onThinkingDelta: { _ in },
            onToolResultDisplay: { _, name, output in
                log("ClaudeAgentBridge: test tool result: \(name) -> \(output.prefix(200))")
            }
        )
        let connected = result.text.contains("CONNECTED")
        log("ClaudeAgentBridge: Playwright test response: \(result.text.prefix(300)), connected=\(connected)")
        return connected
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
