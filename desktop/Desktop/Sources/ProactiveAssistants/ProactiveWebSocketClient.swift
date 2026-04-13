/// WebSocket client for the server-side ProactiveAI service.
///
/// Manages a persistent WebSocket connection. Sends frames and
/// heartbeats, receives tool-call requests and analysis outcomes, and
/// routes tool results back to the server.
///
/// Replaces the former gRPC client — same public API, JSON/WebSocket transport.

import Foundation
import os

// MARK: - Public result types (decoupled from transport)

public struct ProactiveAnalysisResult: Sendable {
    public enum Outcome: Sendable {
        case extractTask(ExtractedTaskResult)
        case rejectTask(reason: String)
        case noTaskFound
    }

    public let outcome: Outcome
    public let contextSummary: String
    public let currentActivity: String
    public let frameId: String
}

public struct ExtractedTaskResult: Sendable {
    public let title: String
    public let description: String
    public let priority: String
    public let tags: [String]
    public let sourceApp: String
    public let inferredDeadline: String
    public let confidence: Double
    public let sourceCategory: String
    public let sourceSubcategory: String
    public let relevanceScore: Int
}

// MARK: - Session context (JSON Codable, replaces Proactive_V1_SessionContext)

public struct ProactiveSessionContext: Codable, Sendable {
    public var activeTasks: [ProactiveActiveTask]
    public var completedTasks: [ProactiveHistoricalTask]
    public var deletedTasks: [ProactiveHistoricalTask]
    public var goals: [ProactiveGoal]

    public init(
        activeTasks: [ProactiveActiveTask] = [],
        completedTasks: [ProactiveHistoricalTask] = [],
        deletedTasks: [ProactiveHistoricalTask] = [],
        goals: [ProactiveGoal] = []
    ) {
        self.activeTasks = activeTasks
        self.completedTasks = completedTasks
        self.deletedTasks = deletedTasks
        self.goals = goals
    }

    enum CodingKeys: String, CodingKey {
        case activeTasks = "active_tasks"
        case completedTasks = "completed_tasks"
        case deletedTasks = "deleted_tasks"
        case goals
    }
}

public struct ProactiveActiveTask: Codable, Sendable {
    public let taskId: Int64
    public let description: String
    public let priority: String
    public let relevanceScore: Int32?

    public init(taskId: Int64, description: String, priority: String = "medium", relevanceScore: Int32? = nil) {
        self.taskId = taskId
        self.description = description
        self.priority = priority
        self.relevanceScore = relevanceScore
    }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case priority
        case relevanceScore = "relevance_score"
    }
}

public struct ProactiveHistoricalTask: Codable, Sendable {
    public let taskId: Int64
    public let description: String

    public init(taskId: Int64, description: String) {
        self.taskId = taskId
        self.description = description
    }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
    }
}

public struct ProactiveGoal: Codable, Sendable {
    public let goalId: String
    public let title: String
    public let description: String

    public init(goalId: String, title: String, description: String = "") {
        self.goalId = goalId
        self.title = title
        self.description = description
    }

    enum CodingKeys: String, CodingKey {
        case goalId = "goal_id"
        case title
        case description
    }
}

// MARK: - Tool executor callback

/// Callback the coordinator provides so the WebSocket client can delegate
/// local search execution back to the desktop.
public typealias ToolExecutor = @Sendable (
    _ toolKind: String,  // "search_similar" or "search_keywords"
    _ query: String
) async -> [SearchResultEntry]

public struct SearchResultEntry: Sendable, Codable {
    public let taskId: Int64
    public let description: String
    public let status: String
    public let similarity: Double
    public let matchType: String
    public let relevanceScore: Int32

    public init(
        taskId: Int64,
        description: String,
        status: String = "active",
        similarity: Double = 0,
        matchType: String = "unspecified",
        relevanceScore: Int32 = 0
    ) {
        self.taskId = taskId
        self.description = description
        self.status = status
        self.similarity = similarity
        self.matchType = matchType
        self.relevanceScore = relevanceScore
    }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case status
        case similarity
        case matchType = "match_type"
        case relevanceScore = "relevance_score"
    }
}

// MARK: - Server message (flat Decodable struct for all message types)

private struct ServerMessage: Decodable {
    let type: String

    // session_ready
    let sessionId: String?
    let protocolVersion: String?
    let contextVersion: String?
    let maxModelIterations: Int?
    let supportedToolKinds: [String]?

    // tool_call_request
    let requestId: String?
    let toolKind: String?
    let query: String?
    let deadlineMs: Int?
    let frameId: String?

    // analysis_outcome
    let outcomeKind: String?
    let task: TaskMessage?
    let reason: String?
    let contextSummary: String?
    let currentActivity: String?

    // server_error
    let code: String?
    let message: String?
    let retryable: Bool?

    enum CodingKeys: String, CodingKey {
        case type
        case sessionId = "session_id"
        case protocolVersion = "protocol_version"
        case contextVersion = "context_version"
        case maxModelIterations = "max_model_iterations"
        case supportedToolKinds = "supported_tool_kinds"
        case requestId = "request_id"
        case toolKind = "tool_kind"
        case query
        case deadlineMs = "deadline_ms"
        case frameId = "frame_id"
        case outcomeKind = "outcome_kind"
        case task, reason
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
        case code, message, retryable
    }
}

private struct TaskMessage: Decodable {
    let title: String
    let description: String?
    let priority: String?
    let tags: [String]?
    let sourceApp: String?
    let inferredDeadline: String?
    let confidence: Double?
    let sourceCategory: String?
    let sourceSubcategory: String?
    let relevanceScore: Int?

    enum CodingKeys: String, CodingKey {
        case title, description, priority, tags
        case sourceApp = "source_app"
        case inferredDeadline = "inferred_deadline"
        case confidence
        case sourceCategory = "source_category"
        case sourceSubcategory = "source_subcategory"
        case relevanceScore = "relevance_score"
    }
}

// MARK: - Client actor

public actor ProactiveWebSocketClient {
    private let logger = Logger(subsystem: "me.omi.desktop", category: "ProactiveWS")

    private let host: String
    private let port: Int
    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var receiveLoopTask: Task<Void, Never>?

    // Server events stream
    private var serverEventsContinuation: AsyncStream<ServerMessage>.Continuation?
    private var serverEvents: AsyncStream<ServerMessage>?

    public private(set) var isConnected = false

    /// Called when the WebSocket transport disconnects (idle or mid-analysis).
    private var onDisconnect: (@Sendable () -> Void)?

    /// Set the disconnect callback (called from ProactiveAssistantsPlugin).
    public func setOnDisconnect(_ handler: @escaping @Sendable () -> Void) {
        onDisconnect = handler
    }

    /// How long to wait for SessionReady after sending ClientHello.
    private let connectTimeout: TimeInterval = 15
    /// How long to wait for a terminal AnalysisOutcome per frame.
    private let analyzeTimeout: TimeInterval = 60

    private let decoder = JSONDecoder()

    public init(host: String = "localhost", port: Int = 8080) {
        self.host = host
        self.port = port
    }

    // MARK: - Connection lifecycle

    /// Connect to the proactive WebSocket endpoint and establish a session.
    public func connect(
        authToken: String,
        context: ProactiveSessionContext,
        appVersion: String = "",
        osVersion: String = ""
    ) async throws -> String {
        // Build WebSocket URL
        let scheme = (host == "localhost" || host == "127.0.0.1") ? "ws" : "wss"
        guard let url = URL(string: "\(scheme)://\(host):\(port)/v1/proactive") else {
            throw ProactiveWSError.connectionFailed("Invalid URL")
        }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = connectTimeout

        let session = URLSession(configuration: .default)
        let ws = session.webSocketTask(with: request)
        ws.resume()

        self.urlSession = session
        self.webSocketTask = ws

        // Set up event stream
        let (stream, continuation) = AsyncStream<ServerMessage>.makeStream()
        self.serverEvents = stream
        self.serverEventsContinuation = continuation

        // Start receive loop
        receiveLoopTask = Task { [weak self] in
            await self?.receiveLoop()
        }

        // Encode session context
        let encoder = JSONEncoder()
        let contextData = try encoder.encode(context)
        let contextJSON = try JSONSerialization.jsonObject(with: contextData) as? [String: Any] ?? [:]

        // Send ClientHello
        let contextVersionStr = UUID().uuidString
        let hello: [String: Any] = [
            "type": "client_hello",
            "protocol_version": "1.0",
            "app_version": appVersion,
            "os_version": osVersion,
            "context_version": contextVersionStr,
            "session_context": contextJSON,
        ]
        try await sendJSON(hello)

        // Wait for SessionReady with timeout
        guard let events = serverEvents else {
            throw ProactiveWSError.notConnected
        }

        let timeoutTask = Task { [weak self] in
            try await Task.sleep(nanoseconds: UInt64(connectTimeout * 1_000_000_000))
            await self?.handleConnectTimeout()
        }
        defer { timeoutTask.cancel() }

        for await event in events {
            if event.type == "session_ready" {
                let sessionId = event.sessionId ?? ""
                self.isConnected = true
                logger.info("Session established: \(sessionId)")
                return sessionId
            }
            if event.type == "server_error" {
                throw ProactiveWSError.serverError(
                    code: event.code ?? "UNKNOWN",
                    message: event.message ?? "Unknown error"
                )
            }
        }

        throw ProactiveWSError.connectionFailed("No session_ready received")
    }

    /// Disconnect the session gracefully.
    public func disconnect() async {
        receiveLoopTask?.cancel()
        receiveLoopTask = nil
        serverEventsContinuation?.finish()
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        isConnected = false
        logger.info("Session disconnected")
    }

    // MARK: - Frame analysis

    /// Send a frame for analysis and handle the full tool-call loop.
    public func analyzeFrame(
        jpegData: Data?,
        appName: String,
        windowTitle: String,
        ocrText: String,
        frameNumber: Int64,
        screenshotId: String,
        updatedContext: ProactiveSessionContext? = nil,
        toolExecutor: ToolExecutor
    ) async throws -> ProactiveAnalysisResult {
        guard webSocketTask != nil, isConnected else {
            throw ProactiveWSError.notConnected
        }

        // Build FrameEvent JSON
        var frame: [String: Any] = [
            "type": "frame_event",
            "app_name": appName,
            "window_title": windowTitle,
            "ocr_text": ocrText,
            "frame_number": frameNumber,
            "screenshot_id": screenshotId,
        ]

        if let jpeg = jpegData {
            frame["jpeg_base64"] = jpeg.base64EncodedString()
        }

        if let ctx = updatedContext {
            let encoder = JSONEncoder()
            if let contextData = try? encoder.encode(ctx),
               let contextJSON = try? JSONSerialization.jsonObject(with: contextData) as? [String: Any] {
                frame["context_version"] = UUID().uuidString
                frame["session_context"] = contextJSON
            }
        }

        try await sendJSON(frame)

        // Process server events until terminal outcome
        guard let events = serverEvents else {
            throw ProactiveWSError.notConnected
        }

        let timeoutTask = Task { [weak self] in
            try await Task.sleep(nanoseconds: UInt64(analyzeTimeout * 1_000_000_000))
            await self?.handleAnalyzeTimeout()
        }
        defer { timeoutTask.cancel() }

        for await serverEvent in events {
            switch serverEvent.type {
            case "tool_call_request":
                let toolKind = serverEvent.toolKind ?? "search_similar"
                let query = serverEvent.query ?? ""
                let requestId = serverEvent.requestId ?? ""
                logger.info("Tool call: \(toolKind) query=\(query.prefix(50))")

                // Execute local search
                let results = await toolExecutor(toolKind, query)

                // Send ToolResult back
                let resultEntries: [[String: Any]] = results.map { entry in
                    [
                        "task_id": entry.taskId,
                        "description": entry.description,
                        "status": entry.status,
                        "similarity": entry.similarity,
                        "match_type": entry.matchType,
                        "relevance_score": entry.relevanceScore,
                    ]
                }
                let toolResult: [String: Any] = [
                    "type": "tool_result",
                    "request_id": requestId,
                    "frame_id": serverEvent.frameId ?? "",
                    "results": resultEntries,
                ]
                try await sendJSON(toolResult)

            case "analysis_outcome":
                return convertOutcome(serverEvent)

            case "server_error":
                let code = serverEvent.code ?? "UNKNOWN"
                let message = serverEvent.message ?? ""
                logger.error("Server error: \(code) — \(message)")
                if serverEvent.retryable == true {
                    throw ProactiveWSError.retryableError(code: code, message: message)
                }
                throw ProactiveWSError.serverError(code: code, message: message)

            default:
                break
            }
        }

        throw ProactiveWSError.streamEnded
    }

    // MARK: - Heartbeat

    /// Send a keepalive heartbeat.
    public func sendHeartbeat() {
        guard let ws = webSocketTask else { return }
        let msg: [String: Any] = ["type": "heartbeat"]
        if let data = try? JSONSerialization.data(withJSONObject: msg),
           let text = String(data: data, encoding: .utf8) {
            ws.send(.string(text)) { _ in }
        }
    }

    // MARK: - Private

    private func sendJSON(_ dict: [String: Any]) async throws {
        guard let ws = webSocketTask else { throw ProactiveWSError.notConnected }
        let data = try JSONSerialization.data(withJSONObject: dict)
        guard let text = String(data: data, encoding: .utf8) else {
            throw ProactiveWSError.connectionFailed("Failed to encode JSON")
        }
        try await ws.send(.string(text))
    }

    private func receiveLoop() async {
        guard let ws = webSocketTask else { return }
        while !Task.isCancelled {
            do {
                let message = try await ws.receive()
                switch message {
                case .string(let text):
                    if let data = text.data(using: .utf8),
                       let serverMsg = try? decoder.decode(ServerMessage.self, from: data) {
                        serverEventsContinuation?.yield(serverMsg)
                    }
                case .data(let data):
                    if let serverMsg = try? decoder.decode(ServerMessage.self, from: data) {
                        serverEventsContinuation?.yield(serverMsg)
                    }
                @unknown default:
                    break
                }
            } catch {
                break
            }
        }
        serverEventsContinuation?.finish()
        handleTransportEnded()
    }

    private func handleConnectTimeout() {
        logger.error("Connect timed out after \(self.connectTimeout)s")
        serverEventsContinuation?.finish()
    }

    private func handleAnalyzeTimeout() {
        logger.error("Frame analysis timed out after \(self.analyzeTimeout)s")
        serverEventsContinuation?.finish()
        webSocketTask?.cancel(with: .abnormalClosure, reason: nil)
    }

    private func handleTransportEnded() {
        logger.info("WebSocket transport ended")
        isConnected = false
        serverEventsContinuation?.finish()
        onDisconnect?()
    }

    private func convertOutcome(_ event: ServerMessage) -> ProactiveAnalysisResult {
        let resultOutcome: ProactiveAnalysisResult.Outcome
        switch event.outcomeKind {
        case "extract_task":
            if let t = event.task {
                resultOutcome = .extractTask(ExtractedTaskResult(
                    title: t.title,
                    description: t.description ?? "",
                    priority: t.priority ?? "medium",
                    tags: t.tags ?? [],
                    sourceApp: t.sourceApp ?? "",
                    inferredDeadline: t.inferredDeadline ?? "",
                    confidence: t.confidence ?? 0.0,
                    sourceCategory: t.sourceCategory ?? "",
                    sourceSubcategory: t.sourceSubcategory ?? "",
                    relevanceScore: t.relevanceScore ?? 0
                ))
            } else {
                resultOutcome = .noTaskFound
            }
        case "reject_task":
            resultOutcome = .rejectTask(reason: event.reason ?? "")
        default:
            resultOutcome = .noTaskFound
        }

        return ProactiveAnalysisResult(
            outcome: resultOutcome,
            contextSummary: event.contextSummary ?? "",
            currentActivity: event.currentActivity ?? "",
            frameId: event.frameId ?? ""
        )
    }
}

// MARK: - Errors

public enum ProactiveWSError: Error, LocalizedError {
    case notConnected
    case connectionFailed(String)
    case serverError(code: String, message: String)
    case retryableError(code: String, message: String)
    case streamEnded
    case timeout

    /// Whether this error is transient and the connection should be kept alive.
    public var isRetryable: Bool {
        if case .retryableError = self { return true }
        return false
    }

    public var errorDescription: String? {
        switch self {
        case .notConnected: return "Not connected to ProactiveAI service"
        case .connectionFailed(let msg): return "Connection failed: \(msg)"
        case .serverError(let code, let msg): return "Server error [\(code)]: \(msg)"
        case .retryableError(let code, let msg): return "Retryable error [\(code)]: \(msg)"
        case .streamEnded: return "Server stream ended unexpectedly"
        case .timeout: return "Request timed out"
        }
    }
}
