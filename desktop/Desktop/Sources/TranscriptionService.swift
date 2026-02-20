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
        case webSocketError(String)

        var errorDescription: String? {
            switch self {
            case .missingAPIKey:
                return "DEEPGRAM_API_KEY not set"
            case .connectionFailed(let error):
                return "Connection failed: \(error.localizedDescription)"
            case .invalidResponse:
                return "Invalid response from DeepGram"
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

    /// Initialize the transcription service
    /// - Parameters:
    ///   - apiKey: DeepGram API key (defaults to DEEPGRAM_API_KEY environment variable)
    ///   - language: Language code for transcription (e.g., "en", "uk", "ru", "multi" for auto-detect)
    ///   - vocabulary: Custom vocabulary/keyterms to improve transcription accuracy (Nova-3 limit: 500 tokens total)
    init(apiKey: String? = nil, language: String = "en", vocabulary: [String] = [], channels: Int = 2) throws {
        guard let key = apiKey ?? ProcessInfo.processInfo.environment["DEEPGRAM_API_KEY"] else {
            throw TranscriptionError.missingAPIKey
        }
        self.apiKey = key
        self.language = language
        self.vocabulary = vocabulary
        self.channels = channels
        log("TranscriptionService: Initialized with language=\(language), vocabulary=\(self.vocabulary.count) terms, channels=\(channels)")
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

    /// Check if connected
    var connected: Bool {
        return isConnected
    }

    // MARK: - Private Methods

    private func connect() {
        // Build DeepGram WebSocket URL with parameters
        var components = URLComponents(string: "wss://api.deepgram.com/v1/listen")!
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
        request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")

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
        guard let key = apiKey ?? ProcessInfo.processInfo.environment["DEEPGRAM_API_KEY"] else {
            throw TranscriptionError.missingAPIKey
        }

        var components = URLComponents(string: "https://api.deepgram.com/v1/listen")!
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
        request.setValue("Token \(key)", forHTTPHeaderField: "Authorization")
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
