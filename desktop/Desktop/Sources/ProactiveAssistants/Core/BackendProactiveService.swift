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

    // Pending request continuations keyed by frame_id
    private var pendingFocusRequests: [String: CheckedContinuation<ScreenAnalysis, Error>] = [:]
    private let requestLock = NSLock()
    private let requestTimeout: TimeInterval = 30.0

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

        // Cancel all pending requests
        cancelAllPending(error: ServiceError.notConnected)

        log("BackendProactiveService: Disconnected")
    }

    // MARK: - Public API

    /// Send a screen_frame for focus analysis and wait for the focus_result response.
    func analyzeFocus(
        imageBase64: String,
        appName: String,
        windowTitle: String
    ) async throws -> ScreenAnalysis {
        guard isConnected else {
            throw ServiceError.notConnected
        }

        let frameId = UUID().uuidString

        let message: [String: Any] = [
            "type": "screen_frame",
            "frame_id": frameId,
            "image_b64": imageBase64,
            "app_name": appName,
            "window_title": windowTitle,
            "analyze": ["focus"],
        ]

        let jsonData = try JSONSerialization.data(withJSONObject: message)
        guard let jsonString = String(data: jsonData, encoding: .utf8) else {
            throw ServiceError.serverError("Failed to encode message")
        }

        return try await withCheckedThrowingContinuation { continuation in
            requestLock.lock()
            pendingFocusRequests[frameId] = continuation
            requestLock.unlock()

            webSocketTask?.send(.string(jsonString)) { [weak self] error in
                if let error = error {
                    self?.requestLock.lock()
                    let cont = self?.pendingFocusRequests.removeValue(forKey: frameId)
                    self?.requestLock.unlock()
                    cont?.resume(throwing: error)
                }
            }

            // Timeout guard
            Task { [weak self] in
                try? await Task.sleep(nanoseconds: UInt64((self?.requestTimeout ?? 30.0) * 1_000_000_000))
                self?.requestLock.lock()
                let cont = self?.pendingFocusRequests.removeValue(forKey: frameId)
                self?.requestLock.unlock()
                cont?.resume(throwing: ServiceError.timeout)
            }
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

        // Connect to /v4/listen with source=desktop — same endpoint as audio,
        // but we only send JSON messages (no audio data)
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

        // Confirm connection after short delay
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

        // Skip heartbeat
        if text == "ping" { return }

        guard let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else {
            return
        }

        switch type {
        case "focus_result":
            handleFocusResult(data)
        default:
            // Other event types (memory_created, etc.) — ignore for now
            break
        }
    }

    private func handleFocusResult(_ data: Data) {
        guard let response = try? JSONDecoder().decode(FocusResultResponse.self, from: data) else {
            log("BackendProactiveService: Failed to decode focus_result")
            return
        }

        let analysis = ScreenAnalysis(
            status: FocusStatus(rawValue: response.status) ?? .focused,
            appOrSite: response.appOrSite,
            description: response.description,
            message: response.message
        )

        requestLock.lock()
        let continuation = pendingFocusRequests.removeValue(forKey: response.frameId)
        requestLock.unlock()

        continuation?.resume(returning: analysis)
    }

    // MARK: - Helpers

    private func cancelAllPending(error: Error) {
        requestLock.lock()
        let pending = pendingFocusRequests
        pendingFocusRequests.removeAll()
        requestLock.unlock()

        for (_, continuation) in pending {
            continuation.resume(throwing: error)
        }
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

// MARK: - Response Models

private struct FocusResultResponse: Decodable {
    let type: String
    let frameId: String
    let status: String
    let appOrSite: String
    let description: String
    let message: String?

    enum CodingKeys: String, CodingKey {
        case type
        case frameId = "frame_id"
        case status
        case appOrSite = "app_or_site"
        case description
        case message
    }
}
