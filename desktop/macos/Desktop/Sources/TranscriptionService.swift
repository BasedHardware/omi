import Foundation

/// Service for real-time speech-to-text transcription.
/// Conversation capture: Python backend `/v4/listen` WebSocket (speech profiles, speaker assignment, memory events).
/// PTT live streaming: Python backend `/v2/voice-message/transcribe-stream` WebSocket (transcription only).
/// PTT batch: Python backend `/v2/voice-message/transcribe` REST API.
/// Full stereo batch: removed (formerly Rust proxy Deepgram, now dead code).
class TranscriptionService {

    // MARK: - Types

    /// Streaming mode determines which backend endpoint and parameters are used.
    enum StreamingMode {
        /// Conversation capture via `/v4/listen` — full pipeline with speech profiles,
        /// speaker assignment, memory creation events, and conversation lifecycle.
        case conversation
        /// PTT live transcription via `/v2/voice-message/transcribe-stream` — transcription only,
        /// no conversation lifecycle. Supports "finalize" text message for flush.
        case ptt

        var telemetryLabel: String {
            switch self {
            case .conversation: return "conversation"
            case .ptt: return "ptt"
            }
        }
    }

    /// Translation from backend (lang code + translated text)
    struct BackendTranslation: Decodable {
        let lang: String
        let text: String
    }

    /// The backend-selected provider for one pre-recorded PTT request.
    struct BatchTranscriptionResult: Equatable {
        let transcript: String?
        let provider: String?
        let model: String?
    }

    /// Transcript segment from Python backend
    /// Matches `models.transcript_segment.TranscriptSegment` on the backend
    struct BackendSegment: Decodable {
        let id: String?
        let text: String
        let speaker: String?        // e.g. "SPEAKER_00"
        let speaker_id: Int?
        let is_user: Bool
        let person_id: String?
        let start: Double
        let end: Double
        let translations: [BackendTranslation]?
    }

    /// Message event (from `/v4/listen` only — not used by PTT transcribe-stream)
    /// JSON object with a `type` field indicating the event kind
    struct ListenEvent {
        let type: String
        let raw: [String: Any]  // Full JSON for event-specific fields
    }

    /// Callback types
    typealias BackendSegmentsHandler = ([BackendSegment]) -> Void
    typealias ListenEventHandler = (ListenEvent) -> Void
    typealias ErrorHandler = (Error) -> Void
    typealias ConnectionHandler = () -> Void

    enum TranscriptionError: LocalizedError {
        case missingBackendURL
        case connectionFailed(Error)
        case invalidResponse
        case payloadTooLarge
        case webSocketError(String)

        var errorDescription: String? {
            switch self {
            case .missingBackendURL:
                return "Python backend URL not configured (OMI_PYTHON_API_URL or api.omi.me)"
            case .connectionFailed(let error):
                return "Connection failed: \(error.localizedDescription)"
            case .invalidResponse:
                return "Invalid response from backend"
            case .payloadTooLarge:
                return "Recording too long — keep it under 5 minutes"
            case .webSocketError(let message):
                return "WebSocket error: \(message)"
            }
        }
    }

    // MARK: - Properties

    private let apiKey: String
    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var webSocketDelegate: WebSocketConnectionDelegate?
    // Internal for @testable import access in unit tests
    var isConnected = false
    var shouldReconnect = false

    // Callbacks
    private var onBackendSegments: BackendSegmentsHandler?
    private var onListenEvent: ListenEventHandler?
    private var onError: ErrorHandler?
    private var onConnected: ConnectionHandler?
    private var onDisconnected: ConnectionHandler?

    // Configuration
    private let language: String
    private let sampleRate = 16000
    private let encoding = "linear16"
    private let channels = 1  // Always mono for Python backend streaming
    private let streamingMode: StreamingMode
    private let contextKeywords: [String]
    private let clientConversationId: String?

    /// Python backend base URL for transcription endpoints.
    /// Resolution order: beta release channel → OMI_PYTHON_API_URL → https://api.omi.me/
    /// NOTE: Do NOT fall back to OMI_DESKTOP_API_URL — that points to the Rust desktop-backend
    /// (Cloud Run), which does not have /v2/voice-message/* or /v4/listen endpoints.
    private static let pythonBackendBaseURL: String = DesktopBackendEnvironment.pythonBaseURL()

    private static func sanitizedContextKeywords(_ keywords: [String]) -> [String] {
        let stopWords: Set<String> = [
            "about", "after", "again", "all", "also", "and", "app", "are", "ask", "back", "browser", "but", "can",
            "chat", "code", "done", "each", "for", "from", "get", "has", "have", "help", "here", "home", "how",
            "into", "just", "like", "means", "more", "next", "not", "now", "open", "question", "read", "right",
            "said", "screen", "sent", "show", "some", "task", "test", "text", "that", "the", "this", "time",
            "use", "user", "voice", "was", "what", "when", "window", "with", "you", "your"
        ]
        var seen = Set<String>()
        var result: [String] = []
        for keyword in ["Omi", "OMI"] + keywords {
            let normalized = keyword
                .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)

            let pattern = #"\b[A-Za-z][A-Za-z'\-]{1,31}\b"#
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let nsText = normalized as NSString
            let matches = regex.matches(in: normalized, range: NSRange(location: 0, length: nsText.length))

            for match in matches {
                let term = nsText.substring(with: match.range)
                let key = term.lowercased()
                guard term.count >= 2 && term.count <= 32 else { continue }
                guard !stopWords.contains(key), !seen.contains(key) else { continue }
                seen.insert(key)
                result.append(term)
                if result.count >= 40 {
                    return result
                }
            }
        }
        return result
    }

    // Reconnection (internal for @testable import)
    var reconnectAttempts = 0
    let maxReconnectAttempts = 10
    private var reconnectTask: Task<Void, Never>?

    // Watchdog: detect stale connections where WebSocket dies silently
    private var watchdogTask: Task<Void, Never>?
    private var lastDataReceivedAt: Date?
    private let watchdogInterval: TimeInterval = 30.0   // Check every 30 seconds
    private let staleThreshold: TimeInterval = 60.0     // Reconnect if no data for 60 seconds

    // Audio buffering
    private var audioBuffer = Data()
    private let audioBufferSize = 3200  // ~100ms of 16kHz 16-bit audio (16000 * 2 * 0.1)
    private let audioBufferLock = NSLock()

    // MARK: - Initialization

    /// Initialize the transcription service for streaming.
    /// - Parameters:
    ///   - language: Language code for transcription (e.g., "en", "uk", "ru", "multi" for auto-detect)
    ///   - mode: Streaming mode — `.conversation` for `/v4/listen` (default), `.ptt` for `/v2/voice-message/transcribe-stream`
    init(
        language: String = "en",
        mode: StreamingMode = .conversation,
        contextKeywords: [String] = [],
        clientConversationId: String? = nil
    ) throws {
        self.apiKey = ""  // Not needed — Python backend uses Firebase auth
        self.language = language
        self.streamingMode = mode
        self.contextKeywords = Self.sanitizedContextKeywords(contextKeywords)
        self.clientConversationId = clientConversationId?.trimmingCharacters(in: .whitespacesAndNewlines)
        log("TranscriptionService: Initialized for \(mode == .conversation ? "/v4/listen" : "/v2/voice-message/transcribe-stream"), language=\(language), contextKeywords=\(self.contextKeywords.count)")
    }

    /// Initialize for batch (PTT) mode only — uses Python backend `/v2/voice-message/transcribe`
    /// - Parameters:
    ///   - apiKey: Ignored (kept for API compatibility with callers)
    ///   - language: Language code
    ///   - forBatchOnly: Must be true
    init(apiKey: String? = nil, language: String = "en", forBatchOnly: Bool) throws {
        guard forBatchOnly else {
            throw TranscriptionError.webSocketError("Use init(language:) for streaming mode")
        }
        // Batch mode uses Firebase auth + Python backend — no DG key needed
        self.apiKey = ""
        self.language = language
        self.streamingMode = .ptt  // Batch doesn't stream, but PTT is the correct context
        self.contextKeywords = []
        self.clientConversationId = nil
        log("TranscriptionService: Initialized for batch (PTT) mode via Python backend")
    }

    // MARK: - Legacy Streaming API (PTT backward compatibility)

    /// Legacy init with channels parameter — used by PushToTalkManager for PTT live mode.
    /// Routes to `/v2/voice-message/transcribe-stream` (PTT-only transcription).
    convenience init(language: String = "en", channels: Int, contextKeywords: [String] = []) throws {
        try self.init(language: language, mode: .ptt, contextKeywords: contextKeywords)
    }

    /// Flush remaining audio and (for PTT mode) tell the backend to finalize transcription.
    /// PTT live mode calls this to get the final transcript segment before closing.
    /// In PTT mode, sends a "finalize" text message so the backend flushes any sub-threshold
    /// audio to Deepgram and triggers its endpointing/finalization.
    /// In conversation mode, just flushes the local audio buffer (no "finalize" — `/v4/listen`
    /// manages its own endpointing via the pusher pipeline).
    func finishStream() {
        flushAudioBuffer()

        // Only PTT mode uses the "finalize" protocol — conversation mode (/v4/listen) doesn't support it
        guard streamingMode == .ptt else { return }
        guard isConnected, let webSocketTask = webSocketTask else { return }
        let message = URLSessionWebSocketTask.Message.string("finalize")
        webSocketTask.send(message) { error in
            if let error = error {
                logError("TranscriptionService: finishStream send error", error: error)
            }
        }
    }

    // MARK: - Public Methods (Streaming)

    /// Start the streaming transcription service (endpoint selected by `streamingMode`)
    func start(
        onSegments: @escaping BackendSegmentsHandler,
        onEvent: @escaping ListenEventHandler,
        onError: ErrorHandler? = nil,
        onConnected: ConnectionHandler? = nil,
        onDisconnected: ConnectionHandler? = nil
    ) {
        self.onBackendSegments = onSegments
        self.onListenEvent = onEvent
        self.onError = onError
        self.onConnected = onConnected
        self.onDisconnected = onDisconnected
        self.shouldReconnect = true
        self.reconnectAttempts = 0

        connect()
    }

    /// Stop the transcription service
    func stop() {
        shouldReconnect = false
        reconnectTask?.cancel()
        reconnectTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil

        // Flush any remaining audio
        flushAudioBuffer()

        disconnect()
    }

    /// Send audio data to the backend (buffered for efficiency)
    func sendAudio(_ data: Data) {
        guard isConnected else { return }

        audioBufferLock.lock()
        audioBuffer.append(data)

        // Send when buffer is full enough
        if audioBuffer.count >= audioBufferSize {
            let chunk = audioBuffer
            audioBuffer = Data()
            audioBufferLock.unlock()
            sendAudioChunk(chunk)
        } else {
            audioBufferLock.unlock()
        }
    }

    /// Flush any remaining audio in the buffer
    private func flushAudioBuffer() {
        audioBufferLock.lock()
        let chunk = audioBuffer
        audioBuffer = Data()
        audioBufferLock.unlock()

        if !chunk.isEmpty {
            sendAudioChunk(chunk)
        }
    }

    /// Actually send an audio chunk to the backend
    private func sendAudioChunk(_ data: Data) {
        guard isConnected, let webSocketTask = webSocketTask else { return }

        let message = URLSessionWebSocketTask.Message.data(data)
        webSocketTask.send(message) { [weak self] error in
            if let error = error {
                logError("TranscriptionService: Send error", error: error)
                self?.handleDisconnection()
            }
        }
    }

    /// Check if connected
    var connected: Bool {
        return isConnected
    }

    // MARK: - Private Methods (Connection)

    private func connect() {
        // Test hook: simulate the cloud WS being unreachable (reconnects exhausted) to exercise
        // the on-device fallback. Toggle with `defaults write <bundle> forceCloudReconnectFail -bool true`.
        if UserDefaults.standard.bool(forKey: "forceCloudReconnectFail") {
            log("TranscriptionService: forceCloudReconnectFail set — simulating max reconnects reached")
            onError?(TranscriptionError.webSocketError("Max reconnect attempts reached"))
            return
        }
        // Always use Firebase auth for Python backend
        Task { [weak self] in
            guard let self = self else { return }
            do {
                let authService = await MainActor.run { AuthService.shared }
                let authHeader = try await authService.getAuthHeader(forceRefresh: self.reconnectAttempts > 0)
                self.connectToBackend(authHeader: authHeader)
            } catch {
                logError("TranscriptionService: Failed to get auth token", error: error)
                self.onError?(TranscriptionError.connectionFailed(error))
            }
        }
    }

    private func connectToBackend(authHeader: String) {
        let base = Self.pythonBackendBaseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        let wsBase = base.hasSuffix("/") ? String(base.dropLast()) : base

        // Select endpoint and query params based on streaming mode
        let path: String
        let queryItems: [URLQueryItem]

        switch streamingMode {
        case .conversation:
            // Full conversation pipeline with speech profiles, speaker assignment, memory events
            path = "/v4/listen"
            var items = [
                URLQueryItem(name: "language", value: language),
                URLQueryItem(name: "sample_rate", value: String(sampleRate)),
                URLQueryItem(name: "codec", value: encoding),
                URLQueryItem(name: "channels", value: String(channels)),
                URLQueryItem(name: "include_speech_profile", value: "true"),
                URLQueryItem(name: "source", value: "desktop"),
                URLQueryItem(name: "speaker_auto_assign", value: "enabled"),
            ]
            if let clientConversationId, !clientConversationId.isEmpty {
                items.append(URLQueryItem(name: "client_conversation_id", value: clientConversationId))
            }
            queryItems = items
        case .ptt:
            // PTT-only transcription — no conversation lifecycle
            path = "/v2/voice-message/transcribe-stream"
            var items = [
                URLQueryItem(name: "language", value: language),
                URLQueryItem(name: "sample_rate", value: String(sampleRate)),
                URLQueryItem(name: "codec", value: encoding),
                URLQueryItem(name: "channels", value: String(channels)),
            ]
            if !contextKeywords.isEmpty {
                items.append(URLQueryItem(name: "keywords", value: contextKeywords.joined(separator: ",")))
            }
            queryItems = items
        }

        guard var components = URLComponents(string: "\(wsBase)\(path)") else {
            log("TranscriptionService: Invalid URL base: \(wsBase)")
            onError?(TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1)))
            return
        }

        components.queryItems = queryItems

        guard let url = components.url else {
            onError?(TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1)))
            return
        }

        log("TranscriptionService: Connecting to \(url.absoluteString)")

        // Create URL request with authorization header
        var request = URLRequest(url: url)
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        // Keep capture provenance on the WebSocket upgrade as well as regular
        // API requests. The backend stamps this onto the conversation, which
        // flows through evidence into canonical memory device filtering.
        request.setValue("macos", forHTTPHeaderField: "X-App-Platform")
        request.setValue(ClientDeviceService.shared.deviceIdHash, forHTTPHeaderField: "X-Device-Id-Hash")
        request.setValue(
          Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
          forHTTPHeaderField: "X-App-Version"
        )

        // BYOK: attach user keys so the transcription backend can use the user's
        // Deepgram token for this session (and any downstream LLM calls).
        for (provider, entry) in APIKeyService.byokSnapshot {
            request.setValue(entry.key, forHTTPHeaderField: provider.headerName)
        }

        // Create URLSession and WebSocket task
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 0  // No resource timeout for long-lived WebSocket
        let delegate = WebSocketConnectionDelegate()
        let session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
        let task = session.webSocketTask(with: request)
        webSocketDelegate = delegate
        urlSession = session
        webSocketTask = task

        delegate.onOpen = { [weak self, weak task] in
            guard let self,
                  WebSocketConnectionAttempt.matches(task, current: self.webSocketTask)
            else { return }
            DispatchQueue.main.async { [weak self, weak task] in
                guard let self,
                      WebSocketConnectionAttempt.matches(task, current: self.webSocketTask)
                else { return }
                self.handleWebSocketOpen()
            }
        }
        delegate.onClose = { [weak self, weak task] closeCode in
            guard let self,
                  WebSocketConnectionAttempt.matches(task, current: self.webSocketTask)
            else { return }
            log("TranscriptionService: WebSocket closed with code \(closeCode.rawValue)")
            if self.isConnected {
                self.handleDisconnection()
            } else if self.shouldReconnect {
                self.cleanupAndReconnect()
            }
        }

        // Start the connection
        task.resume()

        // Start receiving messages
        receiveMessage()

        // Connect timeout: if still not connected after 10s, force reconnect
        Task { [weak self, weak task] in
            try? await Task.sleep(nanoseconds: 10_000_000_000)
            guard let self,
                  WebSocketConnectionAttempt.matches(task, current: self.webSocketTask),
                  !self.isConnected,
                  self.shouldReconnect
            else { return }
            log("TranscriptionService: Connect timeout (10s) — forcing reconnect")
            self.cleanupAndReconnect()
        }
    }

    private func handleWebSocketOpen() {
        guard !isConnected else { return }
        isConnected = true
        reconnectAttempts = 0
        lastDataReceivedAt = Date()
        log("TranscriptionService: WebSocket opened (handshake complete)")
        startWatchdog()
        onConnected?()
    }

    /// Start watchdog to detect stale connections (WebSocket dies silently)
    private func startWatchdog() {
        watchdogTask?.cancel()
        watchdogTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(self?.watchdogInterval ?? 30.0) * 1_000_000_000)
                guard !Task.isCancelled, let self = self, self.isConnected else { break }

                if let lastData = self.lastDataReceivedAt,
                   Date().timeIntervalSince(lastData) > self.staleThreshold {
                    log("TranscriptionService: Watchdog detected stale connection (no data for \(String(format: "%.0f", Date().timeIntervalSince(lastData)))s) - forcing reconnect")
                    self.handleDisconnection()
                }
            }
        }
    }

    private func disconnect() {
        isConnected = false
        watchdogTask?.cancel()
        watchdogTask = nil
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        webSocketDelegate = nil
        log("TranscriptionService: Disconnected")
        onDisconnected?()
    }

    func handleDisconnection() {
        guard isConnected else { return }

        isConnected = false
        watchdogTask?.cancel()
        watchdogTask = nil
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        webSocketDelegate = nil
        onDisconnected?()

        // Attempt reconnection if enabled
        if shouldReconnect && reconnectAttempts < maxReconnectAttempts {
            reconnectAttempts += 1
            let delay = min(pow(2.0, Double(reconnectAttempts)), 32.0) // Exponential backoff, max 32s
            log("TranscriptionService: Reconnecting in \(delay)s (attempt \(reconnectAttempts))")

            reconnectTask = Task {
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                guard !Task.isCancelled, self.shouldReconnect else { return }
                self.connect()
            }
        } else if reconnectAttempts >= maxReconnectAttempts {
            log(
                "TranscriptionService: Max reconnect attempts reached "
                    + "(failure_class=ws_reconnect_exhausted recovery_action=surface_error recovery_result=exhausted)")
            DesktopDiagnosticsManager.shared.recordTranscriptionWsReconnectExhausted(
                reconnectAttempts: reconnectAttempts,
                streamingMode: streamingMode.telemetryLabel
            )
            onError?(TranscriptionError.webSocketError("Max reconnect attempts reached"))
        }
    }

    /// Cleanup a failed/pending connection and schedule reconnect.
    /// Unlike handleDisconnection(), this works even when isConnected is false (pre-handshake failures).
    func cleanupAndReconnect() {
        isConnected = false
        webSocketTask?.cancel(with: .abnormalClosure, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        webSocketDelegate = nil

        guard shouldReconnect, reconnectAttempts < maxReconnectAttempts else {
            if reconnectAttempts >= maxReconnectAttempts {
                log(
                    "TranscriptionService: Max reconnect attempts reached (pre-connect) "
                        + "(failure_class=ws_reconnect_exhausted recovery_action=surface_error recovery_result=exhausted)")
                DesktopDiagnosticsManager.shared.recordTranscriptionWsReconnectExhausted(
                    reconnectAttempts: reconnectAttempts,
                    streamingMode: streamingMode.telemetryLabel
                )
                onError?(TranscriptionError.webSocketError("Max reconnect attempts reached"))
            }
            return
        }

        reconnectAttempts += 1
        let delay = min(pow(2.0, Double(reconnectAttempts)), 32.0)
        log("TranscriptionService: Reconnecting in \(delay)s (attempt \(reconnectAttempts), pre-connect failure)")

        reconnectTask = Task {
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled, self.shouldReconnect else { return }
            self.connect()
        }
    }

    private func receiveMessage() {
        webSocketTask?.receive { [weak self] result in
            guard let self = self else { return }

            switch result {
            case .success(let message):
                self.handleMessage(message)
                // Continue receiving
                self.receiveMessage()

            case .failure(let error):
                guard self.isConnected else { return }
                logError("TranscriptionService: Receive error", error: error)
                self.handleDisconnection()
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        // Track that we received data (for watchdog stale detection)
        lastDataReceivedAt = Date()

        switch message {
        case .string(let text):
            parseBackendResponse(text)
        case .data(let data):
            if let text = String(data: data, encoding: .utf8) {
                parseBackendResponse(text)
            }
        @unknown default:
            break
        }
    }

    /// Parse response from Python backend transcription WebSocket.
    /// Message types:
    /// 1. JSON array = transcript segments (primary, from `/v2/voice-message/transcribe-stream`)
    /// 2. JSON object with "type" field = message event (from `/v4/listen` only, kept for compatibility)
    /// 3. Plain text "ping" = heartbeat (ignore)
    /// Visible to tests (`@testable import`) so ListenProtocolTests can drive real callback dispatch.
    func parseBackendResponse(_ text: String) {
        // Handle heartbeat ping
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed == "ping" {
            return
        }

        guard let data = text.data(using: .utf8) else { return }

        do {
            let json = try JSONSerialization.jsonObject(with: data)

            if json is [[String: Any]] {
                // JSON array = transcript segments
                let segments = try JSONDecoder().decode([BackendSegment].self, from: data)
                if !segments.isEmpty {
                    onBackendSegments?(segments)
                }
            } else if let dict = json as? [String: Any], let type = dict["type"] as? String {
                // JSON object with "type" = message event
                let event = ListenEvent(type: type, raw: dict)
                onListenEvent?(event)
            }
        } catch {
            logError("TranscriptionService: Parse error", error: error)
        }
    }
}

final class WebSocketConnectionDelegate: NSObject, URLSessionWebSocketDelegate {
    var onOpen: (() -> Void)?
    var onClose: ((URLSessionWebSocketTask.CloseCode) -> Void)?

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        onOpen?()
    }

    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        onClose?(closeCode)
    }
}

enum WebSocketConnectionAttempt {
    static func matches(_ candidate: URLSessionWebSocketTask?, current: URLSessionWebSocketTask?) -> Bool {
        guard let candidate, let current else { return false }
        return candidate === current
    }
}

// MARK: - Batch (Pre-Recorded) Transcription (PTT only)

extension TranscriptionService {
    /// Transcribe a complete audio buffer using the Python backend `/v2/voice-message/transcribe`.
    /// Returns the transcript plus the provider/model selected by the backend.
    static func batchTranscribe(
        audioData: Data,
        language: String = "en",
        apiKey: String? = nil,
        contextKeywords: [String] = []
    ) async throws -> BatchTranscriptionResult {
        // Always use Firebase auth + Python backend
        let authService = await MainActor.run { AuthService.shared }
        let authHeader = try await authService.getAuthHeader()
        let baseURLString = "\(pythonBackendBaseURL)v2/voice-message/transcribe"

        guard var components = URLComponents(string: baseURLString) else {
            throw TranscriptionError.connectionFailed(NSError(domain: "Invalid backend URL", code: -1))
        }
        let sanitizedKeywords = sanitizedContextKeywords(contextKeywords)
        var queryItems = [
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "sample_rate", value: "16000"),
            URLQueryItem(name: "encoding", value: "linear16"),
            URLQueryItem(name: "channels", value: "1"),
        ]
        if !sanitizedKeywords.isEmpty {
            queryItems.append(URLQueryItem(name: "keywords", value: sanitizedKeywords.joined(separator: ",")))
        }
        components.queryItems = queryItems

        guard let url = components.url else {
            throw TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1))
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        for (provider, entry) in APIKeyService.byokSnapshot {
            request.setValue(entry.key, forHTTPHeaderField: provider.headerName)
        }
        request.httpBody = audioData

        log("TranscriptionService: Batch transcribing \(audioData.count) bytes via Python backend, contextKeywords=\(sanitizedKeywords.count)")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            let body = String(data: data, encoding: .utf8) ?? "no body"
            logError("TranscriptionService: Batch transcription failed with status \(statusCode): \(body)", error: nil)
            if statusCode == 413 {
                throw TranscriptionError.payloadTooLarge
            }
            throw TranscriptionError.invalidResponse
        }

        // Parse Python backend response, including the provider selected by routed STT.
        let json = try JSONDecoder().decode(PythonTranscribeResponse.self, from: data)
        let transcript = json.transcript.isEmpty ? nil : json.transcript
        let result = BatchTranscriptionResult(
            transcript: transcript,
            provider: json.stt_provider,
            model: json.stt_model)
        log(
            "TranscriptionService: Batch transcription result provider=\(result.provider ?? "unknown") "
                + "model=\(result.model ?? "unknown") transcriptCharacters=\(transcript?.count ?? 0)")
        return result
    }

}

/// Response model for Python backend `/v2/voice-message/transcribe` (batch PTT)
private struct PythonTranscribeResponse: Decodable {
    let transcript: String
    let language: String?
    let stt_provider: String?
    let stt_model: String?
}
