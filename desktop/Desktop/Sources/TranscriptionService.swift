import Foundation

/// Service for real-time speech-to-text transcription using the Python backend `/v4/listen` WebSocket API.
/// Streams audio over WebSocket and receives transcript segments and message events.
/// Batch transcription (PTT) still uses the Rust proxy's Deepgram endpoint.
class TranscriptionService {

    // MARK: - Types

    /// Transcript segment from Python backend `/v4/listen`
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
    }

    /// Message event from Python backend `/v4/listen`
    /// JSON object with a `type` field indicating the event kind
    struct ListenEvent {
        let type: String
        let raw: [String: Any]  // Full JSON for event-specific fields
    }

    /// Legacy TranscriptSegment for batch (PTT) mode — kept for backward compatibility
    struct TranscriptSegment {
        let text: String
        let isFinal: Bool
        let speechFinal: Bool
        let confidence: Double
        let words: [Word]
        let channelIndex: Int  // 0 = mic (user), 1 = system audio (others)

        struct Word {
            let word: String
            let start: Double
            let end: Double
            let confidence: Double
            let speaker: Int?
            let punctuatedWord: String
        }
    }

    /// Callback types
    typealias BackendSegmentsHandler = ([BackendSegment]) -> Void
    typealias ListenEventHandler = (ListenEvent) -> Void
    typealias TranscriptHandler = (TranscriptSegment) -> Void  // Legacy PTT callback
    typealias ErrorHandler = (Error) -> Void
    typealias ConnectionHandler = () -> Void

    enum TranscriptionError: LocalizedError {
        case missingAPIKey
        case missingBackendURL
        case connectionFailed(Error)
        case invalidResponse
        case webSocketError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:
                return "DEEPGRAM_API_KEY not set"
            case .missingBackendURL:
                return "Python backend URL not configured (OMI_PYTHON_API_URL or api.omi.me)"
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

    private let apiKey: String
    private var webSocketTask: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var isConnected = false
    private var shouldReconnect = false

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

    /// Python backend base URL for streaming transcription.
    /// Uses OMI_PYTHON_API_URL env var or falls back to https://api.omi.me/
    private static let pythonBackendBaseURL: String = {
        if let cString = getenv("OMI_PYTHON_API_URL"), let url = String(validatingUTF8: cString), !url.isEmpty {
            return url.hasSuffix("/") ? url : url + "/"
        }
        return "https://api.omi.me/"
    }()

    /// Rust backend proxy base URL (from OMI_API_URL env var).
    /// Only used for batch (PTT) transcription via Deepgram proxy.
    private static let proxyBaseURL: String = {
        if let cString = getenv("OMI_API_URL"), let url = String(validatingUTF8: cString), !url.isEmpty {
            return url.hasSuffix("/") ? url : url + "/"
        }
        return ""
    }()

    /// Legacy deepgramBaseURL for backward compatibility (batch/PTT only).
    private static let deepgramBaseURL: String = {
        if let envURL = getenv("DEEPGRAM_API_URL"), let url = String(validatingUTF8: envURL), !url.isEmpty {
            return url.hasSuffix("/") ? String(url.dropLast()) : url
        }
        return ""  // Empty means use proxy
    }()

    // Reconnection
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
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

    /// Initialize the transcription service for streaming via Python backend `/v4/listen`
    /// - Parameters:
    ///   - language: Language code for transcription (e.g., "en", "uk", "ru", "multi" for auto-detect)
    init(language: String = "en") throws {
        self.apiKey = ""  // Not needed — Python backend uses Firebase auth
        self.language = language
        log("TranscriptionService: Initialized for Python backend streaming, language=\(language), channels=\(channels)")
    }

    /// Initialize for batch (PTT) mode only — uses Deepgram proxy
    /// - Parameters:
    ///   - apiKey: DeepGram API key (ignored when backend proxy is available)
    ///   - language: Language code
    ///   - forBatchOnly: Must be true
    init(apiKey: String? = nil, language: String = "en", forBatchOnly: Bool) throws {
        guard forBatchOnly else {
            throw TranscriptionError.webSocketError("Use init(language:) for streaming mode")
        }
        // Batch mode needs either direct Deepgram or proxy
        if !Self.deepgramBaseURL.isEmpty, let key = apiKey ?? APIKeyService.currentDeepgramKey {
            self.apiKey = key
        } else if !Self.proxyBaseURL.isEmpty {
            self.apiKey = ""
        } else {
            throw TranscriptionError.missingAPIKey
        }
        self.language = language
        log("TranscriptionService: Initialized for batch (PTT) mode")
    }

    // MARK: - Legacy Streaming API (PTT backward compatibility)

    /// Legacy init with channels parameter — delegates to new streaming init.
    /// PTT live mode on main branch uses `TranscriptionService(language:, channels:)`.
    convenience init(language: String = "en", channels: Int) throws {
        try self.init(language: language)
    }

    /// Legacy start with `onTranscript:` callback — wraps the new `onSegments:` API.
    /// Converts BackendSegments to the old TranscriptSegment format for PTT compatibility.
    func start(
        onTranscript: @escaping TranscriptHandler,
        onError: ErrorHandler? = nil,
        onConnected: ConnectionHandler? = nil,
        onDisconnected: ConnectionHandler? = nil
    ) {
        start(
            onSegments: { segments in
                // Convert backend segments to legacy TranscriptSegment format
                for seg in segments {
                    let legacySeg = TranscriptSegment(
                        text: seg.text,
                        isFinal: true,  // Backend segments are always final
                        speechFinal: true,
                        confidence: 1.0,
                        words: [],
                        channelIndex: seg.is_user ? 0 : 1
                    )
                    onTranscript(legacySeg)
                }
            },
            onEvent: { _ in },  // PTT doesn't use events
            onError: onError,
            onConnected: onConnected,
            onDisconnected: onDisconnected
        )
    }

    /// Legacy finishStream — delegates to stop() for backward compatibility.
    /// PTT live mode calls this to flush remaining audio before finalizing.
    func finishStream() {
        flushAudioBuffer()
        // Note: unlike stop(), finishStream keeps the service alive briefly
        // for any remaining server responses. With the Python backend, segments
        // arrive as they're processed, so flushing the buffer is sufficient.
    }

    // MARK: - Public Methods (Streaming)

    /// Start the streaming transcription service via Python backend `/v4/listen`
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
        // Always use Firebase auth for Python backend
        Task { [weak self] in
            guard let self = self else { return }
            do {
                let authService = await MainActor.run { AuthService.shared }
                let authHeader = try await authService.getAuthHeader()
                self.connectToBackend(authHeader: authHeader)
            } catch {
                logError("TranscriptionService: Failed to get auth token", error: error)
                self.onError?(TranscriptionError.connectionFailed(error))
            }
        }
    }

    private func connectToBackend(authHeader: String) {
        // Build WebSocket URL for Python backend /v4/listen
        let base = Self.pythonBackendBaseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
        let wsBase = base.hasSuffix("/") ? String(base.dropLast()) : base

        guard var components = URLComponents(string: "\(wsBase)/v4/listen") else {
            log("TranscriptionService: Invalid URL base: \(wsBase)")
            onError?(TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1)))
            return
        }

        components.queryItems = [
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "sample_rate", value: String(sampleRate)),
            URLQueryItem(name: "codec", value: encoding),
            URLQueryItem(name: "channels", value: String(channels)),
            URLQueryItem(name: "include_speech_profile", value: "true"),
            URLQueryItem(name: "source", value: "desktop"),
            URLQueryItem(name: "speaker_auto_assign", value: "enabled"),
        ]

        guard let url = components.url else {
            onError?(TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1)))
            return
        }

        log("TranscriptionService: Connecting to \(url.absoluteString)")

        // Create URL request with authorization header
        var request = URLRequest(url: url)
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")

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

        // Mark as connected after a brief delay to allow WebSocket handshake.
        // Also set a connect timeout — if the handshake hasn't completed in 10s, trigger reconnect.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self = self else { return }
            guard self.webSocketTask?.state == .running else {
                log("TranscriptionService: WebSocket not running after handshake — triggering reconnect")
                self.cleanupAndReconnect()
                return
            }
            self.isConnected = true
            self.reconnectAttempts = 0
            self.lastDataReceivedAt = Date()
            log("TranscriptionService: Connected to Python backend")
            self.startWatchdog()
            self.onConnected?()
        }

        // Connect timeout: if still not connected after 10s, force reconnect
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 10_000_000_000)
            guard let self = self, !self.isConnected, self.shouldReconnect else { return }
            log("TranscriptionService: Connect timeout (10s) — forcing reconnect")
            self.cleanupAndReconnect()
        }
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
        log("TranscriptionService: Disconnected")
        onDisconnected?()
    }

    private func handleDisconnection() {
        guard isConnected else { return }

        isConnected = false
        watchdogTask?.cancel()
        watchdogTask = nil
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
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
            log("TranscriptionService: Max reconnect attempts reached")
            onError?(TranscriptionError.webSocketError("Max reconnect attempts reached"))
        }
    }

    /// Cleanup a failed/pending connection and schedule reconnect.
    /// Unlike handleDisconnection(), this works even when isConnected is false (pre-handshake failures).
    private func cleanupAndReconnect() {
        webSocketTask?.cancel(with: .abnormalClosure, reason: nil)
        webSocketTask = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil

        guard shouldReconnect, reconnectAttempts < maxReconnectAttempts else {
            if reconnectAttempts >= maxReconnectAttempts {
                log("TranscriptionService: Max reconnect attempts reached (pre-connect)")
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

    /// Parse response from Python backend `/v4/listen`
    /// Three message types:
    /// 1. JSON array = transcript segments
    /// 2. JSON object with "type" field = message event
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

            if let array = json as? [[String: Any]] {
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

// MARK: - Batch (Pre-Recorded) Transcription (PTT only)

extension TranscriptionService {
    /// Transcribe a complete audio buffer using Deepgram's pre-recorded REST API.
    /// Returns the transcript string, or nil if transcription failed.
    static func batchTranscribe(
        audioData: Data,
        language: String = "en",
        apiKey: String? = nil
    ) async throws -> String? {
        // Determine auth and base URL
        let authHeader: String
        let baseURLString: String
        if !proxyBaseURL.isEmpty && deepgramBaseURL.isEmpty {
            // Proxy mode: use Firebase auth, route through backend
            let authService = await MainActor.run { AuthService.shared }
            authHeader = try await authService.getAuthHeader()
            baseURLString = "\(proxyBaseURL)v1/proxy/deepgram/v1/listen"
        } else {
            guard let key = apiKey ?? APIKeyService.currentDeepgramKey else {
                throw TranscriptionError.missingAPIKey
            }
            authHeader = "Token \(key)"
            baseURLString = "\(deepgramBaseURL)/v1/listen"
        }

        guard var components = URLComponents(string: baseURLString) else {
            throw TranscriptionError.connectionFailed(NSError(domain: "Invalid Deepgram URL", code: -1))
        }
        components.queryItems = [
            URLQueryItem(name: "model", value: "nova-3"),
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "smart_format", value: "true"),
            URLQueryItem(name: "punctuate", value: "true"),
            URLQueryItem(name: "diarize", value: "true"),
            // Raw PCM parameters (same as streaming API uses)
            URLQueryItem(name: "encoding", value: "linear16"),
            URLQueryItem(name: "sample_rate", value: "16000"),
            URLQueryItem(name: "channels", value: "1"),
        ]

        guard let url = components.url else {
            throw TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1))
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.httpBody = audioData

        log("TranscriptionService: Batch transcribing \(audioData.count) bytes")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            let body = String(data: data, encoding: .utf8) ?? "no body"
            logError("TranscriptionService: Batch transcription failed with status \(statusCode): \(body)", error: nil)
            throw TranscriptionError.invalidResponse
        }

        // Parse the response — same structure as streaming but wrapped in "results"
        let json = try JSONDecoder().decode(BatchResponse.self, from: data)
        let transcript = json.results?.channels.first?.alternatives.first?.transcript
        log("TranscriptionService: Batch transcription result: \(transcript ?? "(empty)")")
        return transcript
    }

    /// Transcribe a stereo audio buffer using Deepgram's pre-recorded REST API.
    /// Returns full TranscriptSegment per channel with word-level timestamps.
    static func batchTranscribeFull(
        audioData: Data,
        language: String = "en",
        vocabulary: [String] = [],
        apiKey: String? = nil
    ) async throws -> [TranscriptSegment] {
        // Determine auth and base URL
        let authHeader: String
        let baseURLString: String
        if !proxyBaseURL.isEmpty && deepgramBaseURL.isEmpty {
            let authService = await MainActor.run { AuthService.shared }
            authHeader = try await authService.getAuthHeader()
            baseURLString = "\(proxyBaseURL)v1/proxy/deepgram/v1/listen"
        } else {
            guard let key = apiKey ?? APIKeyService.currentDeepgramKey else {
                throw TranscriptionError.missingAPIKey
            }
            authHeader = "Token \(key)"
            baseURLString = "\(deepgramBaseURL)/v1/listen"
        }

        guard var components = URLComponents(string: baseURLString) else {
            throw TranscriptionError.connectionFailed(NSError(domain: "Invalid Deepgram URL", code: -1))
        }
        var queryItems = [
            URLQueryItem(name: "model", value: "nova-3"),
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "channels", value: "2"),
            URLQueryItem(name: "multichannel", value: "true"),
            URLQueryItem(name: "diarize", value: "true"),
            URLQueryItem(name: "smart_format", value: "true"),
            URLQueryItem(name: "punctuate", value: "true"),
            URLQueryItem(name: "utterances", value: "true"),
            URLQueryItem(name: "utt_split", value: "0.8"),
            URLQueryItem(name: "encoding", value: "linear16"),
            URLQueryItem(name: "sample_rate", value: "16000"),
        ]

        for term in vocabulary {
            queryItems.append(URLQueryItem(name: "keyterm", value: term))
        }

        components.queryItems = queryItems

        guard let url = components.url else {
            throw TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1))
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.httpBody = audioData

        log("TranscriptionService: Batch transcribing (full) \(audioData.count) bytes (\(String(format: "%.1f", Double(audioData.count) / 64000.0))s stereo)")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            let body = String(data: data, encoding: .utf8) ?? "no body"
            logError("TranscriptionService: Batch full transcription failed with status \(statusCode): \(body)", error: nil)
            throw TranscriptionError.invalidResponse
        }

        let json = try JSONDecoder().decode(BatchResponse.self, from: data)

        var segments: [TranscriptSegment] = []
        guard let channels = json.results?.channels else { return segments }

        for (channelIndex, channel) in channels.enumerated() {
            guard let alt = channel.alternatives.first,
                  !alt.transcript.isEmpty else { continue }

            let words = alt.words?.map { bw in
                TranscriptSegment.Word(
                    word: bw.word,
                    start: bw.start,
                    end: bw.end,
                    confidence: bw.confidence,
                    speaker: bw.speaker,
                    punctuatedWord: bw.punctuated_word ?? bw.word
                )
            } ?? []

            segments.append(TranscriptSegment(
                text: alt.transcript,
                isFinal: true,
                speechFinal: true,
                confidence: alt.confidence,
                words: words,
                channelIndex: channelIndex
            ))

            log("TranscriptionService: Batch ch\(channelIndex): \(words.count) words, \(alt.transcript.prefix(80))...")
        }

        return segments
    }
}

/// Response model for Deepgram pre-recorded API (batch/PTT only)
private struct BatchResponse: Decodable {
    let results: BatchResults?

    struct BatchResults: Decodable {
        let channels: [BatchChannel]
    }

    struct BatchChannel: Decodable {
        let alternatives: [BatchAlternative]
    }

    struct BatchAlternative: Decodable {
        let transcript: String
        let confidence: Double
        let words: [BatchWord]?
    }

    struct BatchWord: Decodable {
        let word: String
        let start: Double
        let end: Double
        let confidence: Double
        let speaker: Int?
        let punctuated_word: String?
    }
}
