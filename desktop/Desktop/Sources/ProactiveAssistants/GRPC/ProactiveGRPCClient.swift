/// gRPC client for the server-side ProactiveAI service.
///
/// Manages a persistent bidirectional Session stream. Sends frames and
/// heartbeats, receives tool-call requests and analysis outcomes, and
/// routes tool results back to the server.

import Foundation
import GRPC
import NIO
import SwiftProtobuf
import os

// MARK: - Public result types (decoupled from proto)

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

/// Callback the coordinator provides so the gRPC client can delegate
/// local search execution back to the desktop.
public typealias ToolExecutor = @Sendable (
    _ toolKind: Proactive_V1_ToolKind,
    _ query: String
) async -> [SearchResultEntry]

public struct SearchResultEntry: Sendable {
    public let taskId: Int64
    public let description: String
    public let status: Proactive_V1_TaskStatus
    public let similarity: Double
    public let matchType: Proactive_V1_MatchType
    public let relevanceScore: Int32

    public init(
        taskId: Int64,
        description: String,
        status: Proactive_V1_TaskStatus = .active,
        similarity: Double = 0,
        matchType: Proactive_V1_MatchType = .unspecified,
        relevanceScore: Int32 = 0
    ) {
        self.taskId = taskId
        self.description = description
        self.status = status
        self.similarity = similarity
        self.matchType = matchType
        self.relevanceScore = relevanceScore
    }
}

// MARK: - Client actor

public actor ProactiveGRPCClient {
    private let logger = Logger(subsystem: "me.omi.desktop", category: "ProactiveGRPC")

    private let host: String
    private let port: Int
    private let group: EventLoopGroup
    private var channel: ClientConnection?
    private var sessionCall: BidirectionalStreamingCall<Proactive_V1_ClientEvent, Proactive_V1_ServerEvent>?
    private var sessionId: String?
    private var contextVersion: String = ""

    // Pending tool-call requests awaiting local execution
    private var pendingToolCallContinuation: CheckedContinuation<Proactive_V1_ServerEvent, Error>?

    // Server events stream
    private var serverEventsContinuation: AsyncStream<Proactive_V1_ServerEvent>.Continuation?
    private var serverEvents: AsyncStream<Proactive_V1_ServerEvent>?

    public private(set) var isConnected = false

    /// How long to wait for SessionReady after sending ClientHello.
    private let connectTimeout: TimeInterval = 15
    /// How long to wait for a terminal AnalysisOutcome per frame.
    private let analyzeTimeout: TimeInterval = 60

    public init(host: String = "localhost", port: Int = 50051) {
        self.host = host
        self.port = port
        self.group = PlatformSupport.makeEventLoopGroup(loopCount: 1)
    }

    deinit {
        try? group.syncShutdownGracefully()
    }

    // MARK: - Connection lifecycle

    /// Connect to the gRPC server and open a Session stream.
    public func connect(authToken: String, context: Proactive_V1_SessionContext, appVersion: String = "", osVersion: String = "") async throws -> Proactive_V1_SessionReady {
        // Create channel — use TLS for remote hosts, insecure for localhost/dev
        let conn: ClientConnection
        let isLocal = (host == "localhost" || host == "127.0.0.1")
        if isLocal {
            conn = ClientConnection
                .insecure(group: group)
                .connect(host: host, port: port)
        } else {
            conn = ClientConnection
                .usingTLSBackedByNIOSSL(on: group)
                .connect(host: host, port: port)
        }
        self.channel = conn

        // Add auth token to call options
        var callOptions = CallOptions()
        callOptions.customMetadata.add(name: "authorization", value: "Bearer \(authToken)")

        // Create bidirectional stream
        let (stream, continuation) = AsyncStream<Proactive_V1_ServerEvent>.makeStream()
        self.serverEvents = stream
        self.serverEventsContinuation = continuation

        let client = Proactive_V1_ProactiveAINIOClient(channel: conn, defaultCallOptions: callOptions)
        let call = client.session { [weak self] event in
            Task { [weak self] in
                await self?.handleServerEvent(event)
            }
        }
        self.sessionCall = call

        // Monitor gRPC call status — finish the AsyncStream when transport dies
        call.status.whenComplete { [weak self] result in
            Task { [weak self] in
                await self?.handleCallEnded(result: result)
            }
        }

        // Send ClientHello
        let hello = Proactive_V1_ClientEvent.with {
            $0.clientHello = Proactive_V1_ClientHello.with {
                $0.protocolVersion = "1.0"
                $0.appVersion = appVersion
                $0.osVersion = osVersion
                $0.contextVersion = UUID().uuidString
                $0.sessionContext = context
            }
        }
        call.sendMessage(hello, promise: nil)
        self.contextVersion = hello.clientHello.contextVersion

        // Wait for SessionReady with timeout
        guard let events = serverEvents else {
            throw ProactiveGRPCError.notConnected
        }

        // Schedule a timeout that finishes the stream if connect takes too long
        let timeoutTask = Task { [weak self] in
            try await Task.sleep(nanoseconds: UInt64(connectTimeout * 1_000_000_000))
            await self?.handleConnectTimeout()
        }

        defer { timeoutTask.cancel() }

        for await event in events {
            if case .sessionReady(let ready) = event.event {
                self.sessionId = ready.sessionID
                self.isConnected = true
                logger.info("Session established: \(ready.sessionID)")
                return ready
            }
            if case .serverError(let err) = event.event {
                throw ProactiveGRPCError.serverError(
                    code: err.code,
                    message: err.message
                )
            }
        }

        throw ProactiveGRPCError.connectionFailed("No SessionReady received")
    }

    /// Disconnect the session gracefully.
    public func disconnect() async {
        sessionCall?.sendEnd(promise: nil)
        serverEventsContinuation?.finish()
        _ = try? await sessionCall?.status.get()
        try? await channel?.close().get()
        channel = nil
        sessionCall = nil
        sessionId = nil
        isConnected = false
        logger.info("Session disconnected")
    }

    // MARK: - Frame analysis

    /// Send a frame for analysis and handle the full tool-call loop.
    ///
    /// Returns once the server sends a terminal `AnalysisOutcome` or `ServerError`.
    /// Executes local searches via `toolExecutor` when the server requests them.
    public func analyzeFrame(
        jpegData: Data?,
        appName: String,
        windowTitle: String,
        ocrText: String,
        frameNumber: Int64,
        screenshotId: String,
        updatedContext: Proactive_V1_SessionContext? = nil,
        toolExecutor: ToolExecutor
    ) async throws -> ProactiveAnalysisResult {
        guard let call = sessionCall, isConnected else {
            throw ProactiveGRPCError.notConnected
        }

        // Build FrameEvent
        var frame = Proactive_V1_FrameEvent()
        if let jpeg = jpegData {
            frame.jpegBytes = jpeg
        }
        frame.appName = appName
        frame.windowTitle = windowTitle
        frame.ocrText = ocrText
        frame.frameNumber = frameNumber
        frame.screenshotID = screenshotId
        frame.captureTime = Google_Protobuf_Timestamp(date: Date())

        if let ctx = updatedContext {
            let newVersion = UUID().uuidString
            frame.contextVersion = newVersion
            frame.sessionContext = ctx
            self.contextVersion = newVersion
        }

        let event = Proactive_V1_ClientEvent.with {
            $0.frameEvent = frame
        }
        call.sendMessage(event, promise: nil)

        // Process server events until we get a terminal outcome (with timeout)
        guard let events = serverEvents else {
            throw ProactiveGRPCError.notConnected
        }

        // Schedule a timeout that finishes the stream if analysis takes too long
        let timeoutTask = Task { [weak self] in
            try await Task.sleep(nanoseconds: UInt64(analyzeTimeout * 1_000_000_000))
            await self?.handleAnalyzeTimeout()
        }

        defer { timeoutTask.cancel() }

        for await serverEvent in events {
            guard let eventKind = serverEvent.event else { continue }

            switch eventKind {
            case .toolCallRequest(let req):
                let toolKindStr = String(describing: req.toolKind)
                logger.info("Tool call: \(toolKindStr) query=\(req.arguments.query.prefix(50))")

                // Execute local search
                let results = await toolExecutor(req.toolKind, req.arguments.query)

                // Send ToolResult back
                let toolResult = Proactive_V1_ClientEvent.with {
                    $0.toolResult = Proactive_V1_ToolResult.with {
                        $0.requestID = req.requestID
                        $0.frameID = req.frameID
                        $0.result = Proactive_V1_SearchResults.with {
                            $0.items = results.map { entry in
                                Proactive_V1_SearchResult.with {
                                    $0.taskID = entry.taskId
                                    $0.description_p = entry.description
                                    $0.status = entry.status
                                    $0.similarity = entry.similarity
                                    $0.matchType = entry.matchType
                                    $0.relevanceScore = entry.relevanceScore
                                }
                            }
                        }
                    }
                }
                call.sendMessage(toolResult, promise: nil)

            case .analysisOutcome(let outcome):
                return convertOutcome(outcome)

            case .serverError(let err):
                logger.error("Server error: \(err.code) — \(err.message)")
                if err.retryable {
                    throw ProactiveGRPCError.retryableError(code: err.code, message: err.message)
                }
                throw ProactiveGRPCError.serverError(code: err.code, message: err.message)

            case .cancelToolRequest(let cancel):
                logger.info("Tool call cancelled: \(cancel.requestID)")

            case .sessionReady:
                break  // Unexpected during frame analysis
            }
        }

        throw ProactiveGRPCError.streamEnded
    }

    // MARK: - Heartbeat

    /// Send a keepalive heartbeat.
    public func sendHeartbeat() {
        guard let call = sessionCall else { return }
        let event = Proactive_V1_ClientEvent.with {
            $0.heartbeat = Proactive_V1_Heartbeat.with {
                $0.sentAt = Google_Protobuf_Timestamp(date: Date())
            }
        }
        call.sendMessage(event, promise: nil)
    }

    // MARK: - Private

    private func handleServerEvent(_ event: Proactive_V1_ServerEvent) {
        serverEventsContinuation?.yield(event)
    }

    /// Timeout handler for connect — finishes the event stream so the `for await` loop exits.
    private func handleConnectTimeout() {
        logger.error("Connect timed out after \(self.connectTimeout)s")
        serverEventsContinuation?.finish()
    }

    /// Timeout handler for analyzeFrame — finishes the event stream so the `for await` loop exits.
    private func handleAnalyzeTimeout() {
        logger.error("Frame analysis timed out after \(self.analyzeTimeout)s")
        serverEventsContinuation?.finish()
    }

    /// Called when the gRPC call terminates (server close, transport error, etc.)
    /// Must be called on the actor (dispatched via Task in the whenComplete callback).
    private func handleCallEnded(result: Result<GRPCStatus, Error>) {
        let reason: String
        switch result {
        case .success(let status) where status.code == .ok:
            reason = "server closed stream normally"
        case .success(let status):
            reason = "gRPC status \(status.code): \(status.message ?? "")"
        case .failure(let error):
            reason = "transport error: \(error.localizedDescription)"
        }
        logger.info("gRPC call ended: \(reason)")
        isConnected = false
        serverEventsContinuation?.finish()
    }

    private func convertOutcome(_ outcome: Proactive_V1_AnalysisOutcome) -> ProactiveAnalysisResult {
        let resultOutcome: ProactiveAnalysisResult.Outcome
        switch outcome.outcomeKind {
        case .extractTask:
            let t = outcome.task
            resultOutcome = .extractTask(ExtractedTaskResult(
                title: t.title,
                description: t.description_p,
                priority: priorityString(t.priority),
                tags: t.tags,
                sourceApp: t.sourceApp,
                inferredDeadline: t.inferredDeadline,
                confidence: t.confidence,
                sourceCategory: t.sourceCategory,
                sourceSubcategory: t.sourceSubcategory,
                relevanceScore: Int(t.relevanceScore)
            ))
        case .rejectTask:
            resultOutcome = .rejectTask(reason: outcome.reason)
        case .noTaskFound, .unspecified, .UNRECOGNIZED:
            resultOutcome = .noTaskFound
        }

        return ProactiveAnalysisResult(
            outcome: resultOutcome,
            contextSummary: outcome.contextSummary,
            currentActivity: outcome.currentActivity,
            frameId: outcome.frameID
        )
    }

    private func priorityString(_ p: Proactive_V1_TaskPriority) -> String {
        switch p {
        case .priorityHigh: return "high"
        case .priorityMedium: return "medium"
        case .priorityLow: return "low"
        default: return "medium"
        }
    }
}

// MARK: - Errors

public enum ProactiveGRPCError: Error, LocalizedError {
    case notConnected
    case connectionFailed(String)
    case serverError(code: String, message: String)
    case retryableError(code: String, message: String)
    case streamEnded
    case timeout

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
