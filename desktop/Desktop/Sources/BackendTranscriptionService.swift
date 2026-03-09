import Foundation

/// Service for real-time speech-to-text transcription via the OMI backend.
/// Streams mono audio over WebSocket to /v4/listen and receives transcript segments.
/// This replaces direct Deepgram connections — the backend handles STT server-side.
class BackendTranscriptionService {

    // MARK: - Types

    /// Reuse the same TranscriptSegment type for compatibility with existing handlers
    typealias TranscriptSegment = TranscriptionService.TranscriptSegment
    typealias TranscriptHandler = (TranscriptSegment) -> Void
    typealias ErrorHandler = (Error) -> Void
    typealias ConnectionHandler = () -> Void

    enum BackendTranscriptionError: LocalizedError {
        case notSignedIn
        case connectionFailed(Error)
        case invalidResponse
        case webSocketError(String)

        var errorDescription: String? {
            switch self {
            case .notSignedIn:
                return "Not signed in — cannot connect to backend"
            case .connectionFailed(let error):
                return "Connection failed: \(error.localizedDescription)"
            case .invalidResponse:
                return "Invalid response from backend"
            case .webSocketError(let message):
                return "WebSocket error: \(message)"
            }
        }
    }

    // MARK: - Properties

    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var isConnected = false
    private var shouldReconnect = false

    // Callbacks
    private var onTranscript: TranscriptHandler?
    private var onError: ErrorHandler?
    private var onConnected: ConnectionHandler?
    private var onDisconnected: ConnectionHandler?

    // Configuration
    private let language: String
    private let sampleRate = 16000
    private let codec = "pcm16"
    private let channels = 1  // Always mono — backend handles diarization
    private let source: String
    private let conversationTimeout: Int

    // Reconnection
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private var reconnectTask: Task<Void, Never>?

    // Keepalive — send empty data periodically to prevent timeout
    private var keepaliveTask: Task<Void, Never>?
    private let keepaliveInterval: TimeInterval = 8.0

    // Watchdog: detect stale connections where WebSocket dies silently
    private var watchdogTask: Task<Void, Never>?
    private var lastDataReceivedAt: Date?
    private var lastKeepaliveSuccessAt: Date?
    private let watchdogInterval: TimeInterval = 30.0
    private let staleThreshold: TimeInterval = 60.0

    // Audio buffering
    private var audioBuffer = Data()
    private let audioBufferSize = 3200  // ~100ms of 16kHz 16-bit mono (16000 * 2 * 0.1)
    private let audioBufferLock = NSLock()

    // MARK: - Initialization

    /// Initialize the backend transcription service
    /// - Parameters:
    ///   - language: Language code for transcription (e.g., "en", "multi")
    ///   - source: Audio source identifier for backend analytics (e.g., "desktop", "omi", "bee")
    ///   - conversationTimeout: Seconds of silence before the backend creates a memory
    init(language: String = "en", source: String = "desktop", conversationTimeout: Int = 120) {
        self.language = language
        self.source = source
        self.conversationTimeout = conversationTimeout
        log("BackendTranscriptionService: Initialized with language=\(language), source=\(source)")
    }

    // MARK: - Public Methods

    /// Start the transcription service
    func start(
        onTranscript: @escaping TranscriptHandler,
        onError: ErrorHandler? = nil,
        onConnected: ConnectionHandler? = nil,
        onDisconnected: ConnectionHandler? = nil
    ) {
        self.onTranscript = onTranscript
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
        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil

        flushAudioBuffer()
        disconnect()
    }

    /// Signal the backend that no more audio will be sent, but keep connection open
    /// to receive final transcription results. Call stop() later to fully disconnect.
    func finishStream() {
        shouldReconnect = false
        reconnectTask?.cancel()
        reconnectTask = nil
        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil

        flushAudioBuffer()

        // Backend doesn't have a CloseStream message like Deepgram.
        // The connection will be closed when stop() is called.
        log("BackendTranscriptionService: finishStream called, waiting for final results")
    }

    /// Send audio data to the backend (buffered for efficiency)
    func sendAudio(_ data: Data) {
        guard isConnected else { return }

        audioBufferLock.lock()
        audioBuffer.append(data)

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

    /// Actually send an audio chunk over the WebSocket
    private func sendAudioChunk(_ data: Data) {
        guard isConnected, let webSocketTask = webSocketTask else { return }

        let message = URLSessionWebSocketTask.Message.data(data)
        webSocketTask.send(message) { [weak self] error in
            if let error = error {
                logError("BackendTranscriptionService: Send error", error: error)
                self?.handleDisconnection()
            }
        }
    }

    /// No-op for backend (Deepgram-specific Finalize message not needed)
    func sendFinalize() {
        // Backend handles segmentation server-side
    }

    /// Public keepalive for VAD gate to call during extended silence
    func sendKeepalivePublic() {
        sendKeepalive()
    }

    /// Check if connected
    var connected: Bool {
        return isConnected
    }

    // MARK: - Connection

    private func connect() {
        Task {
            do {
                let token = try await AuthService.shared.getIdToken()
                let baseURL = await APIClient.shared.baseURL
                self.connectWithToken(token, baseURL: baseURL)
            } catch {
                logError("BackendTranscriptionService: Failed to get auth token", error: error)
                self.onError?(BackendTranscriptionError.notSignedIn)
            }
        }
    }

    private func connectWithToken(_ token: String, baseURL: String) {

        // Convert http(s) to ws(s)
        let wsBaseURL: String
        if baseURL.hasPrefix("https://") {
            wsBaseURL = "wss://" + baseURL.dropFirst("https://".count)
        } else if baseURL.hasPrefix("http://") {
            wsBaseURL = "ws://" + baseURL.dropFirst("http://".count)
        } else {
            wsBaseURL = "wss://" + baseURL
        }

        // Strip trailing slash before appending path
        let cleanBase = wsBaseURL.hasSuffix("/") ? String(wsBaseURL.dropLast()) : wsBaseURL

        var components = URLComponents(string: cleanBase + "/v4/listen")!
        components.queryItems = [
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "sample_rate", value: String(sampleRate)),
            URLQueryItem(name: "codec", value: codec),
            URLQueryItem(name: "channels", value: String(channels)),
            URLQueryItem(name: "source", value: source),
            URLQueryItem(name: "include_speech_profile", value: "true"),
            URLQueryItem(name: "speaker_auto_assign", value: "enabled"),
            URLQueryItem(name: "conversation_timeout", value: String(conversationTimeout)),
        ]

        guard let url = components.url else {
            onError?(BackendTranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1)))
            return
        }

        log("BackendTranscriptionService: Connecting to \(url.absoluteString)")

        // Create URL request with Bearer auth header (same as mobile app)
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        // Create URLSession and WebSocket task
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 0  // No resource timeout for long-lived WebSocket
        urlSession = URLSession(configuration: configuration)
        webSocketTask = urlSession?.webSocketTask(with: request)

        // Start the connection
        webSocketTask?.resume()

        // Start receiving messages
        receiveMessage()

        // Mark as connected after a short delay (backend doesn't send a connect confirmation)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self = self, self.webSocketTask?.state == .running else { return }
            self.isConnected = true
            self.reconnectAttempts = 0
            self.lastDataReceivedAt = Date()
            self.lastKeepaliveSuccessAt = Date()
            log("BackendTranscriptionService: Connected")
            self.startKeepalive()
            self.startWatchdog()
            self.onConnected?()
        }
    }

    // MARK: - Keepalive

    private func startKeepalive() {
        keepaliveTask?.cancel()
        keepaliveTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(self?.keepaliveInterval ?? 8.0) * 1_000_000_000)
                guard !Task.isCancelled, let self = self, self.isConnected else { break }
                self.sendKeepalive()
            }
        }
    }

    private func sendKeepalive() {
        guard isConnected, let webSocketTask = webSocketTask else { return }

        // Send a small chunk of silence as keepalive (2 bytes of zero = 1 silent sample)
        let silence = Data(repeating: 0, count: 2)
        let message = URLSessionWebSocketTask.Message.data(silence)
        webSocketTask.send(message) { [weak self] error in
            if let error = error {
                logError("BackendTranscriptionService: Keepalive error", error: error)
                self?.handleDisconnection()
            } else {
                self?.lastKeepaliveSuccessAt = Date()
            }
        }
    }

    // MARK: - Watchdog

    private func startWatchdog() {
        watchdogTask?.cancel()
        watchdogTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(self?.watchdogInterval ?? 30.0) * 1_000_000_000)
                guard !Task.isCancelled, let self = self, self.isConnected else { break }

                if let lastData = self.lastDataReceivedAt,
                   Date().timeIntervalSince(lastData) > self.staleThreshold {
                    if let lastKeepalive = self.lastKeepaliveSuccessAt,
                       Date().timeIntervalSince(lastKeepalive) < self.staleThreshold {
                        continue
                    }
                    log("BackendTranscriptionService: Watchdog detected stale connection — forcing reconnect")
                    self.handleDisconnection()
                }
            }
        }
    }

    // MARK: - Disconnect / Reconnect

    private func disconnect() {
        isConnected = false
        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        log("BackendTranscriptionService: Disconnected")
        onDisconnected?()
    }

    private func handleDisconnection() {
        guard isConnected else { return }

        isConnected = false
        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        onDisconnected?()

        if shouldReconnect && reconnectAttempts < maxReconnectAttempts {
            reconnectAttempts += 1
            let delay = min(pow(2.0, Double(reconnectAttempts)), 32.0)
            log("BackendTranscriptionService: Reconnecting in \(delay)s (attempt \(reconnectAttempts))")

            reconnectTask = Task {
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                guard !Task.isCancelled, self.shouldReconnect else { return }
                self.connect()
            }
        } else if reconnectAttempts >= maxReconnectAttempts {
            log("BackendTranscriptionService: Max reconnect attempts reached")
            onError?(BackendTranscriptionError.webSocketError("Max reconnect attempts reached"))
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
                logError("BackendTranscriptionService: Receive error", error: error)
                self.handleDisconnection()
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        lastDataReceivedAt = Date()

        switch message {
        case .string(let text):
            parseResponse(text)
        case .data(let data):
            if let text = String(data: data, encoding: .utf8) {
                parseResponse(text)
            }
        @unknown default:
            break
        }
    }

    private func parseResponse(_ text: String) {
        // Handle heartbeat ping from backend
        if text == "ping" {
            return
        }

        guard let data = text.data(using: .utf8) else { return }

        // Try parsing as array of transcript segments (main response format)
        if let segments = try? JSONDecoder().decode([BackendSegment].self, from: data) {
            for segment in segments {
                // Map backend is_user to channel index:
                //   is_user=true  → channelIndex=0 (mic/user)
                //   is_user=false → channelIndex=1 (system/others)
                let channelIndex = segment.is_user ? 0 : 1

                let transcriptSegment = TranscriptSegment(
                    text: segment.text,
                    isFinal: true,
                    speechFinal: true,
                    confidence: 1.0,
                    words: [TranscriptSegment.Word(
                        word: segment.text,
                        start: segment.start,
                        end: segment.end,
                        confidence: 1.0,
                        speaker: segment.speaker_id,
                        punctuatedWord: segment.text
                    )],
                    channelIndex: channelIndex
                )
                onTranscript?(transcriptSegment)
            }
            return
        }

        // Try parsing as event object (memory_created, service_status, etc.)
        if let event = try? JSONDecoder().decode(BackendEvent.self, from: data) {
            switch event.type {
            case "memory_created":
                log("BackendTranscriptionService: Memory created")
            case "service_status":
                log("BackendTranscriptionService: Service status: \(event.status ?? "unknown")")
            default:
                log("BackendTranscriptionService: Event: \(event.type)")
            }
            return
        }

        // Unknown message — log for debugging
        log("BackendTranscriptionService: Unknown message: \(text.prefix(200))")
    }
}

// MARK: - Backend Response Models

/// Transcript segment from the OMI backend
private struct BackendSegment: Decodable {
    let text: String
    let speaker: String?
    let speaker_id: Int?
    let is_user: Bool
    let start: Double
    let end: Double
    let person_id: String?
}

/// Event message from the OMI backend
private struct BackendEvent: Decodable {
    let type: String
    let status: String?

    enum CodingKeys: String, CodingKey {
        case type
        case status
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        status = try container.decodeIfPresent(String.self, forKey: .status)
    }
}
