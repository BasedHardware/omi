import Foundation

/// Service for real-time speech-to-text transcription using DeepGram
/// Streams audio over WebSocket and receives transcript segments
class TranscriptionService {

    // MARK: - Types

    /// Transcript segment from DeepGram
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
    typealias TranscriptHandler = (TranscriptSegment) -> Void
    typealias ErrorHandler = (Error) -> Void
    typealias ConnectionHandler = () -> Void

    enum TranscriptionError: LocalizedError {
        case missingAPIKey
        case connectionFailed(Error)
        case invalidResponse
        case payloadTooLarge(statusCode: Int, body: String)
        case webSocketError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:
                return "DEEPGRAM_API_KEY not set"
            case .connectionFailed(let error):
                return "Connection failed: \(error.localizedDescription)"
            case .invalidResponse:
                return "Invalid response from DeepGram"
            case .payloadTooLarge(let statusCode, _):
                return "Payload too large (HTTP \(statusCode))"
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
    private var onTranscript: TranscriptHandler?
    private var onError: ErrorHandler?
    private var onConnected: ConnectionHandler?
    private var onDisconnected: ConnectionHandler?

    // Configuration
    private let model = "nova-3"
    private let language: String
    private let vocabulary: [String]
    private let sampleRate = 16000
    private let encoding = "linear16"

    /// Backend proxy base URL (from OMI_API_URL env var).
    /// Deepgram requests are proxied through the Rust backend to keep API keys server-side.
    private static let proxyBaseURL: String = {
        if let cString = getenv("OMI_API_URL"), let url = String(validatingUTF8: cString), !url.isEmpty {
            return url.hasSuffix("/") ? url : url + "/"
        }
        return ""
    }()

    /// Legacy deepgramBaseURL for backward compatibility during transition.
    /// Reads DEEPGRAM_API_URL if set (developer override), otherwise uses proxy.
    private static let deepgramBaseURL: String = {
        if let envURL = getenv("DEEPGRAM_API_URL"), let url = String(validatingUTF8: envURL), !url.isEmpty {
            return url.hasSuffix("/") ? String(url.dropLast()) : url
        }
        return ""  // Empty means use proxy
    }()
    private let channels: Int  // 2 = stereo (mic + system), 1 = mono (mic only for PTT)

    // Reconnection
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private var reconnectTask: Task<Void, Never>?

    // Keepalive
    private var keepaliveTask: Task<Void, Never>?
    private let keepaliveInterval: TimeInterval = 8.0  // Send ping every 8 seconds

    // Watchdog: detect stale connections where WebSocket dies silently
    private var watchdogTask: Task<Void, Never>?
    private var lastDataReceivedAt: Date?
    private var lastKeepaliveSuccessAt: Date?
    private let watchdogInterval: TimeInterval = 30.0   // Check every 30 seconds
    private let staleThreshold: TimeInterval = 60.0     // Reconnect if no data for 60 seconds

    // Audio buffering
    private var audioBuffer = Data()
    private let audioBufferSize = 3200  // ~100ms of 16kHz 16-bit audio (16000 * 2 * 0.1)
    private let audioBufferLock = NSLock()

    // MARK: - Initialization

    /// Whether this instance uses the backend proxy (no direct Deepgram access)
    private let useProxy: Bool

    /// Initialize the transcription service
    /// - Parameters:
    ///   - apiKey: DeepGram API key (ignored when backend proxy is available)
    ///   - language: Language code for transcription (e.g., "en", "uk", "ru", "multi" for auto-detect)
    ///   - vocabulary: Custom vocabulary/keyterms to improve transcription accuracy (Nova-3 limit: 500 tokens total)
    init(apiKey: String? = nil, language: String = "en", vocabulary: [String] = [], channels: Int = 2) throws {
        // Prefer direct Deepgram if DEEPGRAM_API_URL is explicitly set (developer override)
        if !Self.deepgramBaseURL.isEmpty, let key = apiKey ?? APIKeyService.currentDeepgramKey {
            self.apiKey = key
            self.useProxy = false
        } else if !Self.proxyBaseURL.isEmpty {
            // Backend proxy mode: no client-side API key needed
            self.apiKey = ""
            self.useProxy = true
        } else {
            throw TranscriptionError.missingAPIKey
        }
        self.language = language
        self.vocabulary = vocabulary
        self.channels = channels
        log("TranscriptionService: Initialized with language=\(language), vocabulary=\(self.vocabulary.count) terms, channels=\(channels), proxy=\(self.useProxy)")
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

        // Flush any remaining audio
        flushAudioBuffer()

        disconnect()
    }

    /// Signal Deepgram that no more audio will be sent, but keep connection open
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

        guard isConnected, let webSocketTask = webSocketTask else { return }

        let closeMsg = "{\"type\": \"CloseStream\"}"
        webSocketTask.send(.string(closeMsg)) { error in
            if let error = error {
                logError("TranscriptionService: CloseStream send error", error: error)
            }
        }
        log("TranscriptionService: CloseStream sent, waiting for final results")
    }

    /// Send audio data to DeepGram (buffered for efficiency)
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

    /// Actually send an audio chunk to DeepGram
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

    /// Send Deepgram Finalize message to flush pending transcripts
    func sendFinalize() {
        guard isConnected, let webSocketTask = webSocketTask else { return }
        let msg = "{\"type\": \"Finalize\"}"
        webSocketTask.send(.string(msg)) { error in
            if let error = error {
                logError("TranscriptionService: Finalize error", error: error)
            }
        }
    }

    /// Public keepalive for VAD gate to call during extended silence
    func sendKeepalivePublic() {
        sendKeepalive()
    }

    /// Check if connected
    var connected: Bool {
        return isConnected
    }

    // MARK: - Private Methods

    private func connect() {
        if useProxy {
            // Proxy mode: get Firebase auth token async, then connect
            Task { [weak self] in
                guard let self = self else { return }
                do {
                    let authService = await MainActor.run { AuthService.shared }
                    let authHeader = try await authService.getAuthHeader()
                    self.connectWithAuth(authHeader: authHeader)
                } catch {
                    logError("TranscriptionService: Failed to get auth token for proxy", error: error)
                    self.onError?(TranscriptionError.connectionFailed(error))
                }
            }
        } else {
            // Direct Deepgram mode (legacy/developer override)
            connectWithAuth(authHeader: "Token \(apiKey)")
        }
    }

    private func connectWithAuth(authHeader: String) {
        // Build WebSocket URL with parameters
        let wsBase: String
        if useProxy {
            // Route through backend proxy WS endpoint
            let base = Self.proxyBaseURL.replacingOccurrences(of: "https://", with: "wss://")
                                        .replacingOccurrences(of: "http://", with: "ws://")
            wsBase = base.hasSuffix("/") ? String(base.dropLast()) : base
        } else {
            wsBase = Self.deepgramBaseURL.replacingOccurrences(of: "https://", with: "wss://")
                                          .replacingOccurrences(of: "http://", with: "ws://")
        }
        let listenPath = useProxy ? "/v1/proxy/deepgram/ws/v1/listen" : "/v1/listen"
        guard var components = URLComponents(string: "\(wsBase)\(listenPath)") else {
            log("TranscriptionService: Invalid URL base: \(wsBase)")
            onError?(TranscriptionError.connectionFailed(NSError(domain: "Invalid URL", code: -1)))
            return
        }
        var queryItems = [
            URLQueryItem(name: "model", value: model),
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "smart_format", value: "true"),
            URLQueryItem(name: "punctuate", value: "true"),
            URLQueryItem(name: "no_delay", value: "true"),         // Don't buffer - send immediately
            URLQueryItem(name: "diarize", value: "true"),          // Enable speaker diarization
            URLQueryItem(name: "interim_results", value: "true"),  // Get real-time partial results
            URLQueryItem(name: "endpointing", value: "300"),       // 300ms silence detection
            URLQueryItem(name: "utterance_end_ms", value: "1000"), // Backup silence detection
            URLQueryItem(name: "vad_events", value: "true"),       // Voice activity events
            URLQueryItem(name: "encoding", value: encoding),
            URLQueryItem(name: "sample_rate", value: String(sampleRate)),
            URLQueryItem(name: "channels", value: String(channels)),
            URLQueryItem(name: "multichannel", value: channels > 1 ? "true" : "false"),
        ]

        // Add keyterm parameters for custom vocabulary (Nova-3 uses "keyterm" not "keywords")
        for term in vocabulary {
            queryItems.append(URLQueryItem(name: "keyterm", value: term))
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

        // Mark as connected (DeepGram doesn't send a connect confirmation)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self = self, self.webSocketTask?.state == .running else { return }
            self.isConnected = true
            self.reconnectAttempts = 0
            self.lastDataReceivedAt = Date()
            self.lastKeepaliveSuccessAt = Date()
            log("TranscriptionService: Connected")
            self.startKeepalive()
            self.startWatchdog()
            self.onConnected?()
        }
    }

    /// Start keepalive ping task to prevent connection timeout
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

    /// Send a keepalive ping to DeepGram
    private func sendKeepalive() {
        guard isConnected, let webSocketTask = webSocketTask else { return }

        // Send a small JSON keepalive message
        let keepalive = "{\"type\": \"KeepAlive\"}"
        let message = URLSessionWebSocketTask.Message.string(keepalive)
        webSocketTask.send(message) { [weak self] error in
            if let error = error {
                logError("TranscriptionService: Keepalive error", error: error)
                self?.handleDisconnection()
            } else {
                self?.lastKeepaliveSuccessAt = Date()
            }
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
                    // Check if keepalives are still succeeding — if so, the connection
                    // is alive and Deepgram just has nothing to return (silent room).
                    // Only force reconnect when keepalives have also gone stale.
                    if let lastKeepalive = self.lastKeepaliveSuccessAt,
                       Date().timeIntervalSince(lastKeepalive) < self.staleThreshold {
                        // Keepalives working — connection is alive, just no speech to transcribe
                        continue
                    }
                    log("TranscriptionService: Watchdog detected stale connection (no data for \(String(format: "%.0f", Date().timeIntervalSince(lastData)))s, keepalives also failing) - forcing reconnect")
                    self.handleDisconnection()
                }
            }
        }
    }

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
        log("TranscriptionService: Disconnected")
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
            parseResponse(text)
        case .data(let data):
            if let text = String(data: data, encoding: .utf8) {
                parseResponse(text)
            }
        @unknown default:
            break
        }
    }

    private func parseResponse(_ jsonString: String) {
        guard let data = jsonString.data(using: .utf8) else { return }

        do {
            let response = try JSONDecoder().decode(DeepgramResponse.self, from: data)

            // Handle different message types
            if let type = response.type {
                switch type {
                case "Results":
                    if let transcript = extractTranscript(from: response) {
                        onTranscript?(transcript)
                    }
                case "UtteranceEnd":
                    log("TranscriptionService: Utterance end detected")
                case "SpeechStarted":
                    log("TranscriptionService: Speech started")
                case "Metadata":
                    log("TranscriptionService: Received metadata")
                default:
                    break
                }
            } else if response.channel != nil {
                // Legacy format without type field
                if let transcript = extractTranscript(from: response) {
                    onTranscript?(transcript)
                }
            }
        } catch {
            // Log but don't treat as fatal - some messages may be metadata
            logError("TranscriptionService: Parse warning", error: error)
        }
    }

    private func extractTranscript(from response: DeepgramResponse) -> TranscriptSegment? {
        guard let channel = response.channel,
              let alternative = channel.alternatives.first else {
            return nil
        }

        let text = alternative.transcript
        guard !text.isEmpty else { return nil }

        let words = alternative.words?.map { word in
            TranscriptSegment.Word(
                word: word.word,
                start: word.start,
                end: word.end,
                confidence: word.confidence,
                speaker: word.speaker,
                punctuatedWord: word.punctuated_word ?? word.word
            )
        } ?? []

        // Extract channel index from response
        // channel_index is [channelNum, totalChannels], e.g., [0, 2] or [1, 2]
        let channelIndex = response.channel_index?.first ?? 0

        return TranscriptSegment(
            text: text,
            isFinal: response.is_final ?? false,
            speechFinal: response.speech_final ?? false,
            confidence: alternative.confidence,
            words: words,
            channelIndex: channelIndex
        )
    }
}

// MARK: - Batch (Pre-Recorded) Transcription

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
            if statusCode == 413 {
                throw TranscriptionError.payloadTooLarge(statusCode: statusCode, body: body)
            }
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

    // MARK: - Batch Transcription with Splitting

    /// Maximum audio payload size for a single batch transcription request.
    /// Matches VADGateService.maxBatchBytes. Audio larger than this is proactively split.
    static let maxBatchPayloadBytes = VADGateService.maxBatchBytes

    /// Bytes per second for stereo 16kHz Int16 PCM audio.
    static let stereoBytesPerSecond = 64_000

    /// Transcribe audio with automatic splitting for large payloads.
    /// Proactively splits audio exceeding maxBatchPayloadBytes, and retries with splitting on 413.
    static func batchTranscribeWithSplitting(
        audioData: Data,
        language: String = "en",
        vocabulary: [String] = []
    ) async throws -> [TranscriptSegment] {
        // Proactive split if audio exceeds max payload
        if audioData.count > maxBatchPayloadBytes {
            log("TranscriptionService: Audio \(audioData.count) bytes exceeds \(maxBatchPayloadBytes) — splitting")
            return try await splitAndTranscribe(audioData: audioData, language: language, vocabulary: vocabulary)
        }

        // Try direct transcription, retry with split on 413
        do {
            return try await batchTranscribeFull(audioData: audioData, language: language, vocabulary: vocabulary)
        } catch TranscriptionError.payloadTooLarge {
            log("TranscriptionService: Got 413, retrying with split")
            return try await splitAndTranscribe(audioData: audioData, language: language, vocabulary: vocabulary)
        }
    }

    /// Split audio at midpoint with 1s overlap, transcribe each half, merge results.
    /// Only one level of splitting — halves are sent directly via batchTranscribeFull.
    static func splitAndTranscribe(
        audioData: Data,
        language: String,
        vocabulary: [String]
    ) async throws -> [TranscriptSegment] {
        let overlapBytes = stereoBytesPerSecond  // 1 second overlap
        let bytesPerFrame = 4  // Stereo Int16: 2 channels * 2 bytes

        // Align midpoint to frame boundary
        let rawMid = audioData.count / 2
        let mid = (rawMid / bytesPerFrame) * bytesPerFrame

        // First half: [0, mid + overlap/2)
        let firstEnd = min(mid + overlapBytes / 2, audioData.count)
        let alignedFirstEnd = (firstEnd / bytesPerFrame) * bytesPerFrame
        let firstHalf = audioData.prefix(alignedFirstEnd)

        // Second half: [mid - overlap/2, end)
        let secondStart = max(mid - overlapBytes / 2, 0)
        let alignedSecondStart = (secondStart / bytesPerFrame) * bytesPerFrame
        let secondHalf = audioData.suffix(from: alignedSecondStart)

        let splitStartSec = Double(alignedSecondStart) / Double(stereoBytesPerSecond)

        log("TranscriptionService: Split — first=\(firstHalf.count) bytes, second=\(secondHalf.count) bytes, offset=\(String(format: "%.1f", splitStartSec))s")

        // Transcribe both halves (sequentially to avoid doubling concurrent load)
        let firstSegments = try await batchTranscribeFull(
            audioData: Data(firstHalf), language: language, vocabulary: vocabulary
        )
        let secondSegments = try await batchTranscribeFull(
            audioData: Data(secondHalf), language: language, vocabulary: vocabulary
        )

        // Merge per channel: offset second-half timestamps, dedupe overlap
        return mergeSegments(first: firstSegments, second: secondSegments, secondOffsetSec: splitStartSec)
    }

    /// Merge segments from two halves per channel.
    /// Second-half word timestamps are offset by secondOffsetSec.
    /// Words in the overlap window are deduped by matching text and timestamp proximity.
    static func mergeSegments(
        first: [TranscriptSegment],
        second: [TranscriptSegment],
        secondOffsetSec: Double
    ) -> [TranscriptSegment] {
        // Group by channel
        var firstByChannel: [Int: TranscriptSegment] = [:]
        for seg in first { firstByChannel[seg.channelIndex] = seg }

        var secondByChannel: [Int: TranscriptSegment] = [:]
        for seg in second { secondByChannel[seg.channelIndex] = seg }

        let allChannels = Set(firstByChannel.keys).union(secondByChannel.keys)
        var merged: [TranscriptSegment] = []

        for ch in allChannels.sorted() {
            let firstWords = firstByChannel[ch]?.words ?? []
            let secondWords = (secondByChannel[ch]?.words ?? []).map { word in
                TranscriptSegment.Word(
                    word: word.word,
                    start: word.start + secondOffsetSec,
                    end: word.end + secondOffsetSec,
                    confidence: word.confidence,
                    speaker: word.speaker,
                    punctuatedWord: word.punctuatedWord
                )
            }

            // Dedupe: find where first-half ends and second-half begins
            let deduped = dedupeOverlapWords(first: firstWords, second: secondWords)

            let combinedText = deduped.map { $0.punctuatedWord }.joined(separator: " ")
            let avgConfidence = deduped.isEmpty ? 0.0 : deduped.reduce(0.0) { $0 + $1.confidence } / Double(deduped.count)

            merged.append(TranscriptSegment(
                text: combinedText,
                isFinal: true,
                speechFinal: true,
                confidence: avgConfidence,
                words: deduped,
                channelIndex: ch
            ))
        }

        return merged
    }

    /// Deduplicate words in the overlap window between first and second halves.
    /// Words from the second half that match a first-half word (same text, within 0.5s) are dropped.
    static func dedupeOverlapWords(
        first: [TranscriptSegment.Word],
        second: [TranscriptSegment.Word]
    ) -> [TranscriptSegment.Word] {
        guard let lastFirstWord = first.last else { return second }
        let overlapEnd = lastFirstWord.end

        var result = first
        for word in second {
            // Skip words that fall within the overlap window and match a first-half word
            if word.start <= overlapEnd + 0.5 {
                let isDuplicate = first.contains { firstWord in
                    firstWord.word.lowercased() == word.word.lowercased() &&
                    abs(firstWord.start - word.start) < 0.5
                }
                if isDuplicate { continue }
            }
            result.append(word)
        }

        return result
    }
}

/// Response model for Deepgram pre-recorded API
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

// MARK: - DeepGram Response Models

private struct DeepgramResponse: Decodable {
    let type: String?
    let channel: Channel?           // For Results messages (object with alternatives)
    let channelArray: [Int]?        // For SpeechStarted/UtteranceEnd (array like [0, 2])
    let is_final: Bool?
    let speech_final: Bool?
    let channel_index: [Int]?
    let duration: Double?
    let start: Double?
    let timestamp: Double?          // For SpeechStarted
    let last_word_end: Double?      // For UtteranceEnd

    struct Channel: Decodable {
        let alternatives: [Alternative]
    }

    struct Alternative: Decodable {
        let transcript: String
        let confidence: Double
        let words: [Word]?
    }

    struct Word: Decodable {
        let word: String
        let start: Double
        let end: Double
        let confidence: Double
        let speaker: Int?
        let punctuated_word: String?
    }

    enum CodingKeys: String, CodingKey {
        case type, channel, is_final, speech_final, channel_index, duration, start, timestamp, last_word_end
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)

        type = try container.decodeIfPresent(String.self, forKey: .type)
        is_final = try container.decodeIfPresent(Bool.self, forKey: .is_final)
        speech_final = try container.decodeIfPresent(Bool.self, forKey: .speech_final)
        channel_index = try container.decodeIfPresent([Int].self, forKey: .channel_index)
        duration = try container.decodeIfPresent(Double.self, forKey: .duration)
        start = try container.decodeIfPresent(Double.self, forKey: .start)
        timestamp = try container.decodeIfPresent(Double.self, forKey: .timestamp)
        last_word_end = try container.decodeIfPresent(Double.self, forKey: .last_word_end)

        // Handle "channel" which can be either an object (Results) or array (SpeechStarted/UtteranceEnd)
        if container.contains(.channel) {
            // Try decoding as Channel object first (for Results messages)
            if let channelObj = try? container.decode(Channel.self, forKey: .channel) {
                channel = channelObj
                channelArray = nil
            }
            // Otherwise try as [Int] array (for SpeechStarted/UtteranceEnd)
            else if let channelArr = try? container.decode([Int].self, forKey: .channel) {
                channel = nil
                channelArray = channelArr
            } else {
                channel = nil
                channelArray = nil
            }
        } else {
            channel = nil
            channelArray = nil
        }
    }
}
