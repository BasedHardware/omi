import Foundation

/// WebSocket client for desktop proactive AI via /v4/listen.
/// Sends typed JSON messages (screen_frame, etc.) and routes typed responses
/// (focus_result, etc.) back to callers via async continuations.
///
/// This is the Phase 2 replacement for direct GeminiClient calls — all LLM
/// processing happens server-side; the client just sends screenshots and
/// receives structured results.
class BackendProactiveService {

    // MARK: - Types

    enum ServiceError: LocalizedError {
        case missingAPIURL
        case authFailed(String)
        case notConnected
        case timeout
        case serverError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIURL: return "OMI_API_URL not set"
            case .authFailed(let reason): return "Auth failed: \(reason)"
            case .notConnected: return "Backend WebSocket not connected"
            case .timeout: return "Request timed out"
            case .serverError(let msg): return "Server error: \(msg)"
            }
        }
    }

    // MARK: - Properties

    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private(set) var isConnected = false
    private var shouldReconnect = false
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private var reconnectTask: Task<Void, Never>?

    // Keepalive
    private var keepaliveTask: Task<Void, Never>?
    private let keepaliveInterval: TimeInterval = 30.0

    // Pending continuations keyed by frame_id (vision handlers)
    private var pendingFocusRequests: [String: CheckedContinuation<ScreenAnalysis, Error>] = [:]
    private var pendingTasksRequests: [String: CheckedContinuation<TasksExtractedResult, Error>] = [:]
    private var pendingMemoriesRequests: [String: CheckedContinuation<MemoriesExtractedResult, Error>] = [:]
    private var pendingAdviceRequests: [String: CheckedContinuation<AdviceExtractedResult, Error>] = [:]

    // Pending continuations for text-only handlers (one outstanding per type)
    private var pendingLiveNote: CheckedContinuation<String, Error>?
    private var pendingProfile: CheckedContinuation<String, Error>?
    private var pendingRerank: CheckedContinuation<RerankExtractedResult, Error>?
    private var pendingDedup: CheckedContinuation<DedupExtractedResult, Error>?

    private let requestLock = NSLock()
    private let requestTimeout: TimeInterval = 30.0
    private let textRequestTimeout: TimeInterval = 60.0

    // MARK: - Connection

    func connect() {
        shouldReconnect = true
        reconnectAttempts = 0
        startConnect()
    }

    func disconnect() {
        shouldReconnect = false
        reconnectTask?.cancel()
        reconnectTask = nil
        keepaliveTask?.cancel()
        keepaliveTask = nil

        isConnected = false
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil

        cancelAllPending(error: ServiceError.notConnected)
        log("BackendProactiveService: Disconnected")
    }

    // MARK: - Vision Handlers (screen_frame)

    /// Send a screen_frame for focus analysis and wait for the focus_result response.
    func analyzeFocus(imageBase64: String, appName: String, windowTitle: String) async throws -> ScreenAnalysis {
        guard isConnected else { throw ServiceError.notConnected }
        let frameId = UUID().uuidString
        let jsonString = try buildScreenFrameJSON(frameId: frameId, analyzeTypes: ["focus"], imageBase64: imageBase64, appName: appName, windowTitle: windowTitle)

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingFocusRequests[frameId] = continuation
            requestLock.unlock()
            sendAndTimeout(jsonString: jsonString, frameId: frameId, timeout: requestTimeout,
                           remove: { self.pendingFocusRequests.removeValue(forKey: $0) })
        }
    }

    /// Send a screen_frame for task extraction.
    func extractTasks(imageBase64: String, appName: String, windowTitle: String) async throws -> TasksExtractedResult {
        guard isConnected else { throw ServiceError.notConnected }
        let frameId = UUID().uuidString
        let jsonString = try buildScreenFrameJSON(frameId: frameId, analyzeTypes: ["tasks"], imageBase64: imageBase64, appName: appName, windowTitle: windowTitle)

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingTasksRequests[frameId] = continuation
            requestLock.unlock()
            sendAndTimeout(jsonString: jsonString, frameId: frameId, timeout: requestTimeout,
                           remove: { self.pendingTasksRequests.removeValue(forKey: $0) })
        }
    }

    /// Send a screen_frame for memory extraction.
    func extractMemories(imageBase64: String, appName: String, windowTitle: String) async throws -> MemoriesExtractedResult {
        guard isConnected else { throw ServiceError.notConnected }
        let frameId = UUID().uuidString
        let jsonString = try buildScreenFrameJSON(frameId: frameId, analyzeTypes: ["memories"], imageBase64: imageBase64, appName: appName, windowTitle: windowTitle)

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingMemoriesRequests[frameId] = continuation
            requestLock.unlock()
            sendAndTimeout(jsonString: jsonString, frameId: frameId, timeout: requestTimeout,
                           remove: { self.pendingMemoriesRequests.removeValue(forKey: $0) })
        }
    }

    /// Send a screen_frame for advice generation.
    func generateAdvice(imageBase64: String, appName: String, windowTitle: String) async throws -> AdviceExtractedResult {
        guard isConnected else { throw ServiceError.notConnected }
        let frameId = UUID().uuidString
        let jsonString = try buildScreenFrameJSON(frameId: frameId, analyzeTypes: ["advice"], imageBase64: imageBase64, appName: appName, windowTitle: windowTitle)

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingAdviceRequests[frameId] = continuation
            requestLock.unlock()
            sendAndTimeout(jsonString: jsonString, frameId: frameId, timeout: requestTimeout,
                           remove: { self.pendingAdviceRequests.removeValue(forKey: $0) })
        }
    }

    // MARK: - Text-Only Handlers

    /// Send transcript text for live note generation.
    func generateLiveNote(text: String, sessionContext: String = "") async throws -> String {
        guard isConnected else { throw ServiceError.notConnected }
        let jsonString = try buildJSON(["type": "live_notes_text", "text": text, "session_context": sessionContext])

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingLiveNote = continuation
            requestLock.unlock()
            sendAndTimeoutSingle(jsonString: jsonString, timeout: textRequestTimeout,
                                 remove: { let c = self.pendingLiveNote; self.pendingLiveNote = nil; return c })
        }
    }

    /// Request profile generation (server fetches user data from Firestore).
    func requestProfile() async throws -> String {
        guard isConnected else { throw ServiceError.notConnected }
        let jsonString = try buildJSON(["type": "profile_request"])

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingProfile = continuation
            requestLock.unlock()
            sendAndTimeoutSingle(jsonString: jsonString, timeout: textRequestTimeout,
                                 remove: { let c = self.pendingProfile; self.pendingProfile = nil; return c })
        }
    }

    /// Request task reranking (server fetches tasks from Firestore).
    func rerankTasks() async throws -> RerankExtractedResult {
        guard isConnected else { throw ServiceError.notConnected }
        let jsonString = try buildJSON(["type": "task_rerank"])

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingRerank = continuation
            requestLock.unlock()
            sendAndTimeoutSingle(jsonString: jsonString, timeout: textRequestTimeout,
                                 remove: { let c = self.pendingRerank; self.pendingRerank = nil; return c })
        }
    }

    /// Request task deduplication (server fetches tasks from Firestore).
    func deduplicateTasks() async throws -> DedupExtractedResult {
        guard isConnected else { throw ServiceError.notConnected }
        let jsonString = try buildJSON(["type": "task_dedup"])

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingDedup = continuation
            requestLock.unlock()
            sendAndTimeoutSingle(jsonString: jsonString, timeout: textRequestTimeout,
                                 remove: { let c = self.pendingDedup; self.pendingDedup = nil; return c })
        }
    }

    // MARK: - Send Helpers

    private func buildScreenFrameJSON(frameId: String, analyzeTypes: [String], imageBase64: String, appName: String, windowTitle: String) throws -> String {
        try buildJSON([
            "type": "screen_frame",
            "frame_id": frameId,
            "image_b64": imageBase64,
            "app_name": appName,
            "window_title": windowTitle,
            "analyze": analyzeTypes,
        ])
    }

    private func buildJSON(_ dict: [String: Any]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: dict)
        guard let str = String(data: data, encoding: .utf8) else {
            throw ServiceError.serverError("Failed to encode message")
        }
        return str
    }

    /// Send JSON and set up timeout for frame_id-keyed continuations.
    private func sendAndTimeout<T>(jsonString: String, frameId: String, timeout: TimeInterval,
                                   remove: @escaping (String) -> CheckedContinuation<T, Error>?) {
        webSocketTask?.send(.string(jsonString)) { [weak self] error in
            if let error = error {
                self?.requestLock.lock()
                let cont = remove(frameId)
                self?.requestLock.unlock()
                cont?.resume(throwing: error)
            }
        }

        Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
            self?.requestLock.lock()
            let cont = remove(frameId)
            self?.requestLock.unlock()
            cont?.resume(throwing: ServiceError.timeout)
        }
    }

    /// Send JSON and set up timeout for single-slot continuations.
    private func sendAndTimeoutSingle<T>(jsonString: String, timeout: TimeInterval,
                                         remove: @escaping () -> CheckedContinuation<T, Error>?) {
        webSocketTask?.send(.string(jsonString)) { [weak self] error in
            if let error = error {
                self?.requestLock.lock()
                let cont = remove()
                self?.requestLock.unlock()
                cont?.resume(throwing: error)
            }
        }

        Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000))
            self?.requestLock.lock()
            let cont = remove()
            self?.requestLock.unlock()
            cont?.resume(throwing: ServiceError.timeout)
        }
    }

    // MARK: - Connection Internals

    private func startConnect() {
        guard let baseURL = Self.getBaseURL() else {
            log("BackendProactiveService: OMI_API_URL not set")
            return
        }

        Task {
            do {
                let idToken = try await AuthService.shared.getIdToken()
                await connectWithToken(baseURL: baseURL, token: idToken)
            } catch {
                logError("BackendProactiveService: Failed to get ID token", error: error)
                handleDisconnection()
            }
        }
    }

    private func connectWithToken(baseURL: String, token: String) async {
        let wsURL = baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        let base = wsURL.hasSuffix("/") ? wsURL : wsURL + "/"

        var components = URLComponents(string: "\(base)v4/listen")!
        components.queryItems = [
            URLQueryItem(name: "source", value: "desktop"),
            URLQueryItem(name: "sample_rate", value: "16000"),
            URLQueryItem(name: "codec", value: "pcm16"),
            URLQueryItem(name: "channels", value: "1"),
            URLQueryItem(name: "language", value: "en"),
        ]

        guard let url = components.url else {
            log("BackendProactiveService: Invalid URL")
            return
        }

        log("BackendProactiveService: Connecting to \(url.absoluteString)")

        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 30

        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForResource = 0
        urlSession = URLSession(configuration: configuration)
        webSocketTask = urlSession?.webSocketTask(with: request)
        webSocketTask?.resume()

        receiveMessage()

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self = self, self.webSocketTask?.state == .running else {
                self?.handleDisconnection()
                return
            }
            self.isConnected = true
            self.reconnectAttempts = 0
            self.startKeepalive()
            log("BackendProactiveService: Connected")
        }
    }

    private func startKeepalive() {
        keepaliveTask?.cancel()
        keepaliveTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64((self?.keepaliveInterval ?? 30.0) * 1_000_000_000))
                guard !Task.isCancelled, let self = self, self.isConnected else { break }
                self.sendKeepalive()
            }
        }
    }

    private func sendKeepalive() {
        guard isConnected, let ws = webSocketTask else { return }
        ws.send(.string("{\"type\": \"KeepAlive\"}")) { [weak self] error in
            if let error = error {
                logError("BackendProactiveService: Keepalive error", error: error)
                self?.handleDisconnection()
            }
        }
    }

    private func handleDisconnection() {
        guard isConnected || shouldReconnect else { return }

        isConnected = false
        keepaliveTask?.cancel()
        keepaliveTask = nil
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil

        cancelAllPending(error: ServiceError.notConnected)

        if shouldReconnect && reconnectAttempts < maxReconnectAttempts {
            reconnectAttempts += 1
            let delay = min(pow(2.0, Double(reconnectAttempts)), 32.0)
            log("BackendProactiveService: Reconnecting in \(delay)s (attempt \(reconnectAttempts))")

            reconnectTask = Task {
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                guard !Task.isCancelled, self.shouldReconnect else { return }
                self.startConnect()
            }
        } else if reconnectAttempts >= maxReconnectAttempts {
            log("BackendProactiveService: Max reconnect attempts reached")
        }
    }

    // MARK: - Message Handling

    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self = self else { return }

            switch result {
            case .success(let message):
                self.handleMessage(message)
                self.receiveMessage()
            case .failure(let error):
                guard self.isConnected else { return }
                logError("BackendProactiveService: Receive error", error: error)
                self.handleDisconnection()
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        let text: String
        switch message {
        case .string(let s):
            text = s
        case .data(let data):
            guard let s = String(data: data, encoding: .utf8) else { return }
            text = s
        @unknown default:
            return
        }

        if text == "ping" { return }

        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else {
            return
        }

        switch type {
        case "focus_result":
            handleFocusResult(json)
        case "tasks_extracted":
            handleTasksExtracted(json)
        case "memories_extracted":
            handleMemoriesExtracted(json)
        case "advice_extracted":
            handleAdviceExtracted(json)
        case "live_note":
            handleLiveNote(json)
        case "profile_updated":
            handleProfileUpdated(json)
        case "rerank_complete":
            handleRerankComplete(json)
        case "dedup_complete":
            handleDedupComplete(json)
        default:
            break
        }
    }

    // MARK: - Response Handlers

    private func handleFocusResult(_ json: [String: Any]) {
        guard let frameId = json["frame_id"] as? String else { return }
        let analysis = ScreenAnalysis(
            status: FocusStatus(rawValue: json["status"] as? String ?? "focused") ?? .focused,
            appOrSite: json["app_or_site"] as? String ?? "",
            description: json["description"] as? String ?? "",
            message: json["message"] as? String
        )
        requestLock.lock()
        let cont = pendingFocusRequests.removeValue(forKey: frameId)
        requestLock.unlock()
        cont?.resume(returning: analysis)
    }

    private func handleTasksExtracted(_ json: [String: Any]) {
        guard let frameId = json["frame_id"] as? String else { return }
        let tasks = (json["tasks"] as? [[String: Any]]) ?? []
        let result = TasksExtractedResult(frameId: frameId, tasks: tasks)
        requestLock.lock()
        let cont = pendingTasksRequests.removeValue(forKey: frameId)
        requestLock.unlock()
        cont?.resume(returning: result)
    }

    private func handleMemoriesExtracted(_ json: [String: Any]) {
        guard let frameId = json["frame_id"] as? String else { return }
        let memories = (json["memories"] as? [[String: Any]]) ?? []
        let result = MemoriesExtractedResult(frameId: frameId, memories: memories)
        requestLock.lock()
        let cont = pendingMemoriesRequests.removeValue(forKey: frameId)
        requestLock.unlock()
        cont?.resume(returning: result)
    }

    private func handleAdviceExtracted(_ json: [String: Any]) {
        guard let frameId = json["frame_id"] as? String else { return }
        let result = AdviceExtractedResult(frameId: frameId, advice: json["advice"])
        requestLock.lock()
        let cont = pendingAdviceRequests.removeValue(forKey: frameId)
        requestLock.unlock()
        cont?.resume(returning: result)
    }

    private func handleLiveNote(_ json: [String: Any]) {
        let text = json["text"] as? String ?? ""
        requestLock.lock()
        let cont = pendingLiveNote
        pendingLiveNote = nil
        requestLock.unlock()
        cont?.resume(returning: text)
    }

    private func handleProfileUpdated(_ json: [String: Any]) {
        let profileText = json["profile_text"] as? String ?? ""
        requestLock.lock()
        let cont = pendingProfile
        pendingProfile = nil
        requestLock.unlock()
        cont?.resume(returning: profileText)
    }

    private func handleRerankComplete(_ json: [String: Any]) {
        let updatedTasks = (json["updated_tasks"] as? [[String: Any]]) ?? []
        let result = RerankExtractedResult(updatedTasks: updatedTasks)
        requestLock.lock()
        let cont = pendingRerank
        pendingRerank = nil
        requestLock.unlock()
        cont?.resume(returning: result)
    }

    private func handleDedupComplete(_ json: [String: Any]) {
        let deletedIds = (json["deleted_ids"] as? [String]) ?? []
        let reason = json["reason"] as? String ?? ""
        let result = DedupExtractedResult(deletedIds: deletedIds, reason: reason)
        requestLock.lock()
        let cont = pendingDedup
        pendingDedup = nil
        requestLock.unlock()
        cont?.resume(returning: result)
    }

    // MARK: - Helpers

    private func cancelAllPending(error: Error) {
        requestLock.lock()
        let focus = pendingFocusRequests; pendingFocusRequests.removeAll()
        let tasks = pendingTasksRequests; pendingTasksRequests.removeAll()
        let memories = pendingMemoriesRequests; pendingMemoriesRequests.removeAll()
        let advice = pendingAdviceRequests; pendingAdviceRequests.removeAll()
        let liveNote = pendingLiveNote; pendingLiveNote = nil
        let profile = pendingProfile; pendingProfile = nil
        let rerank = pendingRerank; pendingRerank = nil
        let dedup = pendingDedup; pendingDedup = nil
        requestLock.unlock()

        for (_, c) in focus { c.resume(throwing: error) }
        for (_, c) in tasks { c.resume(throwing: error) }
        for (_, c) in memories { c.resume(throwing: error) }
        for (_, c) in advice { c.resume(throwing: error) }
        liveNote?.resume(throwing: error)
        profile?.resume(throwing: error)
        rerank?.resume(throwing: error)
        dedup?.resume(throwing: error)
    }

    private static func getBaseURL() -> String? {
        if let cString = getenv("OMI_API_URL"), let url = String(validatingUTF8: cString), !url.isEmpty {
            return url
        }
        if let envURL = ProcessInfo.processInfo.environment["OMI_API_URL"], !envURL.isEmpty {
            return envURL
        }
        return nil
    }
}

// MARK: - Result Types

/// Tasks extracted from a screen_frame analysis.
struct TasksExtractedResult {
    let frameId: String
    let tasks: [[String: Any]]  // Raw task dicts from backend
}

/// Memories extracted from a screen_frame analysis.
struct MemoriesExtractedResult {
    let frameId: String
    let memories: [[String: Any]]  // Raw memory dicts from backend
}

/// Advice extracted from a screen_frame analysis.
struct AdviceExtractedResult {
    let frameId: String
    let advice: Any?  // Raw advice from backend (dict or null)
}

/// Task reranking result.
struct RerankExtractedResult {
    let updatedTasks: [[String: Any]]  // [{id, new_position}, ...]
}

/// Task deduplication result.
struct DedupExtractedResult {
    let deletedIds: [String]
    let reason: String
}
