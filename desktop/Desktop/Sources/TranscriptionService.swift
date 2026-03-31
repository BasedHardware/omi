import Foundation

/// Service for real-time speech-to-text transcription using DeepGram
/// Streams audio over WebSocket and receives transcript segments
class TranscriptionService: NSObject, URLSessionWebSocketDelegate {

    // MARK: - Types

    /// Connection lifecycle state (thread-safe via stateQueue)
    enum ConnectionState {
        case disconnected
        case connecting
        case connected
        case reconnecting
    }

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

    // MARK: - Thread-safe state

    /// Serial queue protecting all mutable connection state
    private let stateQueue = DispatchQueue(label: "com.omi.transcription.state")
    private var _connectionState: ConnectionState = .disconnected
    private var _webSocketTask: URLSessionWebSocketTask?
    private var _urlSession: URLSession?
    private var _shouldReconnect = false
    private var _reconnectAttempts = 0
    private var _connectionGeneration: UInt64 = 0  // Monotonic ID to discard stale delegate callbacks
    private var _lastDataReceivedAt: Date?
    private var _lastKeepaliveSuccessAt: Date?

    /// Execute a block on the state queue and return its result
    private func withState<T>(_ body: () -> T) -> T {
        stateQueue.sync { body() }
    }

    // MARK: - Properties

    private let apiKey: String

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

    // Reconnection — no hard cap; backoff with jitter, retry while shouldReconnect is true
    private var reconnectTask: Task<Void, Never>?
    private let maxBackoff: TimeInterval = 60.0
    private let backoffJitterRange: ClosedRange<Double> = 0.5...1.5

    // Keepalive
    private var keepaliveTask: Task<Void, Never>?
    private let keepaliveInterval: TimeInterval = 8.0  // Send ping every 8 seconds

    // Watchdog: detect stale connections where WebSocket dies silently
    private var watchdogTask: Task<Void, Never>?
    private let watchdogInterval: TimeInterval = 30.0   // Check every 30 seconds
    private let staleThreshold: TimeInterval = 60.0     // Reconnect if no data for 60 seconds

    // Audio buffering (outbound send coalescing)
    private var audioBuffer = Data()
    private let audioBufferSize = 3200  // ~100ms of 16kHz 16-bit audio (16000 * 2 * 0.1)
    private let audioBufferLock = NSLock()

    // Reconnect audio ring buffer: holds audio produced while disconnected/reconnecting
    // 30s of stereo 16kHz 16-bit = ~1.92MB; cap at 960KB (~15s) to stay conservative
    private var reconnectBuffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 960_000)

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
        super.init()
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
        withState {
            _shouldReconnect = true
            _reconnectAttempts = 0
        }

        connect()
    }

    /// Stop the transcription service
    func stop() {
        withState { _shouldReconnect = false }
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
        withState { _shouldReconnect = false }
        reconnectTask?.cancel()
        reconnectTask = nil
        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil

        flushAudioBuffer()

        let task: URLSessionWebSocketTask? = withState {
            guard _connectionState == .connected else { return nil }
            return _webSocketTask
        }
        guard let task = task else { return }

        let closeMsg = "{\"type\": \"CloseStream\"}"
        task.send(.string(closeMsg)) { error in
            if let error = error {
                logError("TranscriptionService: CloseStream send error", error: error)
            }
        }
        log("TranscriptionService: CloseStream sent, waiting for final results")
    }

    /// Send audio data to DeepGram (buffered for efficiency).
    /// When disconnected/reconnecting, audio is queued in a ring buffer and replayed on reconnect.
    func sendAudio(_ data: Data) {
        guard !data.isEmpty else { return }

        let shouldSendNow: Bool = withState {
            reconnectBuffer.prune()
            switch _connectionState {
            case .connected:
                return true
            case .connecting, .reconnecting:
                reconnectBuffer.append(data)
                return false
            case .disconnected:
                if _shouldReconnect {
                    reconnectBuffer.append(data)
                }
                return false
            }
        }

        guard shouldSendNow else { return }

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
        let task: URLSessionWebSocketTask? = withState {
            guard _connectionState == .connected else { return nil }
            return _webSocketTask
        }
        guard let task = task else { return }

        let message = URLSessionWebSocketTask.Message.data(data)
        task.send(message) { [weak self] error in
            if let error = error {
                logError("TranscriptionService: Send error", error: error)
                self?.handleDisconnection()
            }
        }
    }

    /// Replay audio buffered during reconnection.
    /// Sends chunks sequentially so only the first failure controls the retry path,
    /// preventing duplicate rebuffering from concurrent failure callbacks.
    private func replayBufferedAudio() {
        let (task, chunks): (URLSessionWebSocketTask?, [Data]) = withState {
            guard _connectionState == .connected else { return (nil, []) }
            return (_webSocketTask, reconnectBuffer.drain())
        }
        guard let task = task, !chunks.isEmpty else { return }

        log("TranscriptionService: Replaying \(chunks.count) buffered audio chunks")
        replayChunksSequentially(task: task, chunks: chunks, index: 0)
    }

    /// Send chunks one at a time; on first failure, re-buffer the rest and reconnect.
    private func replayChunksSequentially(task: URLSessionWebSocketTask, chunks: [Data], index: Int) {
        guard index < chunks.count else { return }

        task.send(.data(chunks[index])) { [weak self] error in
            if let error = error {
                logError("TranscriptionService: Replay send error at chunk \(index)", error: error)
                if let self = self {
                    self.withState {
                        for remaining in chunks[index...] {
                            self.reconnectBuffer.append(remaining)
                        }
                    }
                    self.handleDisconnection()
                }
                return
            }
            // Success — send next chunk
            self?.replayChunksSequentially(task: task, chunks: chunks, index: index + 1)
        }
    }

    /// Send Deepgram Finalize message to flush pending transcripts
    func sendFinalize() {
        let task: URLSessionWebSocketTask? = withState {
            guard _connectionState == .connected else { return nil }
            return _webSocketTask
        }
        guard let task = task else { return }
        let msg = "{\"type\": \"Finalize\"}"
        task.send(.string(msg)) { error in
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
        return withState { _connectionState == .connected }
    }

    // MARK: - Test accessors (internal for @testable import)

    /// Current connection state (read-only, for testing)
    var testConnectionState: ConnectionState {
        withState { _connectionState }
    }

    /// Current generation token (read-only, for testing)
    var testConnectionGeneration: UInt64 {
        withState { _connectionGeneration }
    }

    /// Directly set state for testing state machine behavior.
    /// Only callable from tests via @testable import.
    func testSetState(_ state: ConnectionState) {
        withState { _connectionState = state }
    }

    /// Expose handleDisconnection for idempotency testing
    func testHandleDisconnection() {
        handleDisconnection()
    }

    /// Expose shouldReconnect setter for testing
    func testSetShouldReconnect(_ value: Bool) {
        withState { _shouldReconnect = value }
    }

    /// Compute reconnect delay: exponential backoff capped at maxBackoff, then jittered.
    /// Exposed as static for testability.
    static func reconnectDelay(
        attempt: Int,
        maxBackoff: TimeInterval = 60.0,
        jitterRange: ClosedRange<Double> = 0.5...1.5
    ) -> TimeInterval {
        let baseDelay = min(pow(2.0, Double(attempt)), maxBackoff)
        let jitter = Double.random(in: jitterRange)
        return baseDelay * jitter
    }

    // MARK: - Private Methods

    private func connect() {
        let generation: UInt64 = withState {
            guard _connectionState == .disconnected || _connectionState == .reconnecting else {
                return 0  // 0 = signal not to proceed
            }
            _connectionState = .connecting
            _connectionGeneration += 1
            return _connectionGeneration
        }
        guard generation > 0 else { return }

        if useProxy {
            // Proxy mode: get Firebase auth token async, then connect
            Task { [weak self] in
                guard let self = self else { return }
                do {
                    let authService = await MainActor.run { AuthService.shared }
                    let authHeader = try await authService.getAuthHeader()
                    // Re-check: stop() may have been called while fetching auth token
                    let stillValid = self.withState {
                        self._connectionGeneration == generation && self._shouldReconnect && self._connectionState == .connecting
                    }
                    guard stillValid else {
                        log("TranscriptionService: Auth fetched but connection no longer wanted (gen \(generation))")
                        return
                    }
                    self.connectWithAuth(authHeader: authHeader, generation: generation)
                } catch {
                    logError("TranscriptionService: Failed to get auth token for proxy", error: error)
                    self.onError?(TranscriptionError.connectionFailed(error))
                    self.handleDisconnection()
                }
            }
        } else {
            // Direct Deepgram mode (legacy/developer override)
            connectWithAuth(authHeader: "Token \(apiKey)", generation: generation)
        }
    }

    private func connectWithAuth(authHeader: String, generation: UInt64) {
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
            handleDisconnection()
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
            handleDisconnection()
            return
        }

        // Verify this generation is still current before creating network resources
        let stillValid = withState { _connectionGeneration == generation && _connectionState == .connecting }
        guard stillValid else {
            log("TranscriptionService: Connection no longer wanted (gen \(generation))")
            return
        }
        log("TranscriptionService: Connecting to \(url.host ?? "?") (gen \(generation))")

        // Create URL request with authorization header
        var request = URLRequest(url: url)
        request.setValue(authHeader, forHTTPHeaderField: "Authorization")

        // Create URLSession with self as delegate to receive WebSocket lifecycle callbacks
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 0  // No resource timeout for long-lived WebSocket
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
        let task = session.webSocketTask(with: request)

        withState {
            _urlSession = session
            _webSocketTask = task
        }

        // Start the connection — didOpenWithProtocol delegate will confirm handshake
        task.resume()

        // Start receiving messages immediately (queued until handshake completes)
        receiveMessage(generation: generation)

        // Connect timeout: if handshake hasn't completed in 10s, treat as failure
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 10_000_000_000)
            guard let self = self else { return }
            let shouldTimeout: Bool = self.withState {
                self._connectionGeneration == generation && self._connectionState == .connecting
            }
            if shouldTimeout {
                log("TranscriptionService: Connect timeout (gen \(generation))")
                self.handleDisconnection()
            }
        }
    }

    // MARK: - URLSessionWebSocketDelegate

    /// Called when WebSocket handshake completes successfully
    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        let (isValid, generation): (Bool, UInt64) = withState {
            // Only accept if this is the current session AND we still want to be connected
            guard _urlSession === session && _shouldReconnect && _connectionState == .connecting else {
                return (false, _connectionGeneration)
            }
            _connectionState = .connected
            _reconnectAttempts = 0
            _lastDataReceivedAt = Date()
            _lastKeepaliveSuccessAt = Date()
            return (true, _connectionGeneration)
        }
        guard isValid else {
            log("TranscriptionService: Ignoring stale didOpen (gen \(generation))")
            // Clean up the unwanted session
            session.invalidateAndCancel()
            return
        }

        log("TranscriptionService: Connected (gen \(generation), protocol=\(`protocol` ?? "none"))")
        startKeepalive()
        startWatchdog()
        replayBufferedAudio()
        onConnected?()
    }

    /// Called when WebSocket receives a close frame from server
    func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        let isCurrentSession: Bool = withState { _urlSession === session }
        guard isCurrentSession else { return }

        let reasonText = reason.flatMap { String(data: $0, encoding: .utf8) } ?? "none"
        log("TranscriptionService: Server closed connection (code=\(closeCode.rawValue), reason=\(reasonText))")
        handleDisconnection()
    }

    /// Start keepalive ping task to prevent connection timeout
    private func startKeepalive() {
        keepaliveTask?.cancel()
        keepaliveTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(self?.keepaliveInterval ?? 8.0) * 1_000_000_000)
                guard !Task.isCancelled, let self = self else { break }
                let isConn = self.withState { self._connectionState == .connected }
                guard isConn else { break }
                self.sendKeepalive()
            }
        }
    }

    /// Send a keepalive ping to DeepGram
    private func sendKeepalive() {
        let task: URLSessionWebSocketTask? = withState {
            guard _connectionState == .connected else { return nil }
            return _webSocketTask
        }
        guard let task = task else { return }

        let keepalive = "{\"type\": \"KeepAlive\"}"
        let message = URLSessionWebSocketTask.Message.string(keepalive)
        task.send(message) { [weak self] error in
            if let error = error {
                logError("TranscriptionService: Keepalive error", error: error)
                self?.handleDisconnection()
            } else {
                self?.withState { self?._lastKeepaliveSuccessAt = Date() }
            }
        }
    }

    /// Start watchdog to detect stale connections (WebSocket dies silently)
    private func startWatchdog() {
        watchdogTask?.cancel()
        watchdogTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(self?.watchdogInterval ?? 30.0) * 1_000_000_000)
                guard !Task.isCancelled, let self = self else { break }

                let (isConn, lastData, lastKeepalive) = self.withState {
                    (self._connectionState == .connected, self._lastDataReceivedAt, self._lastKeepaliveSuccessAt)
                }
                guard isConn else { break }

                if let lastData = lastData,
                   Date().timeIntervalSince(lastData) > self.staleThreshold {
                    // Check if keepalives are still succeeding — if so, the connection
                    // is alive and Deepgram just has nothing to return (silent room).
                    if let lastKeepalive = lastKeepalive,
                       Date().timeIntervalSince(lastKeepalive) < self.staleThreshold {
                        continue
                    }
                    log("TranscriptionService: Watchdog detected stale connection (no data for \(String(format: "%.0f", Date().timeIntervalSince(lastData)))s, keepalives also failing) - forcing reconnect")
                    self.handleDisconnection()
                }
            }
        }
    }

    private func disconnect() {
        let oldSession: URLSession? = withState {
            _connectionState = .disconnected
            _connectionGeneration += 1  // Invalidate any in-flight receive callbacks
            let s = _urlSession
            _webSocketTask?.cancel(with: .normalClosure, reason: nil)
            _webSocketTask = nil
            _urlSession = nil
            return s
        }
        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil
        oldSession?.invalidateAndCancel()
        log("TranscriptionService: Disconnected")
        onDisconnected?()
    }

    private func handleDisconnection() {
        let (shouldAttemptReconnect, attempt): (Bool, Int) = withState {
            // Idempotent: if already reconnecting or disconnected, this is a duplicate callback
            guard _connectionState == .connected || _connectionState == .connecting else { return (false, 0) }

            _connectionGeneration += 1  // Invalidate any in-flight receive/keepalive callbacks
            let oldSession = _urlSession
            _connectionState = .reconnecting
            _webSocketTask = nil
            _urlSession = nil
            oldSession?.invalidateAndCancel()

            guard _shouldReconnect else {
                _connectionState = .disconnected
                return (false, 0)
            }
            _reconnectAttempts += 1
            return (true, _reconnectAttempts)
        }

        keepaliveTask?.cancel()
        keepaliveTask = nil
        watchdogTask?.cancel()
        watchdogTask = nil

        // Salvage any partial audio in the coalescing buffer into the reconnect buffer
        audioBufferLock.lock()
        let partialAudio = audioBuffer
        audioBuffer = Data()
        audioBufferLock.unlock()
        if !partialAudio.isEmpty {
            withState { reconnectBuffer.append(partialAudio) }
        }

        onDisconnected?()

        guard shouldAttemptReconnect else { return }

        // Exponential backoff with jitter, no hard cap on attempts
        let delay = Self.reconnectDelay(attempt: attempt, maxBackoff: maxBackoff, jitterRange: backoffJitterRange)
        log("TranscriptionService: Reconnecting in \(String(format: "%.1f", delay))s (attempt \(attempt))")

        reconnectTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            guard !Task.isCancelled else { return }
            guard let self = self else { return }
            let shouldReconnect = self.withState { self._shouldReconnect }
            guard shouldReconnect else { return }
            self.connect()
        }
    }

    private func receiveMessage(generation: UInt64) {
        let task: URLSessionWebSocketTask? = withState { _webSocketTask }
        task?.receive { [weak self] result in
            guard let self = self else { return }

            // Discard callbacks from stale connections
            let currentGen = self.withState { self._connectionGeneration }
            guard currentGen == generation else { return }

            switch result {
            case .success(let message):
                self.handleMessage(message)
                self.receiveMessage(generation: generation)

            case .failure(let error):
                let isActive = self.withState { self._connectionState == .connected || self._connectionState == .connecting }
                guard isActive else { return }
                logError("TranscriptionService: Receive error", error: error)
                self.handleDisconnection()
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        // Track that we received data (for watchdog stale detection)
        withState { _lastDataReceivedAt = Date() }

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

        // Transcribe both halves (recursively split if still too large)
        let firstSegments = try await batchTranscribeWithSplitting(
            audioData: Data(firstHalf), language: language, vocabulary: vocabulary
        )
        let secondSegments = try await batchTranscribeWithSplitting(
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

// MARK: - Reconnect Audio Ring Buffer

/// Bounded ring buffer that holds audio chunks produced while WebSocket is reconnecting.
/// Chunks older than `ttl` or exceeding `maxBytes` are evicted automatically.
/// Internal access level for testability via @testable import.
struct ReconnectAudioRingBuffer {
    struct Chunk {
        let data: Data
        let createdAt: Date
    }

    let ttl: TimeInterval
    let maxBytes: Int
    private(set) var chunks: [Chunk] = []
    private(set) var totalBytes = 0

    init(ttl: TimeInterval = 30, maxBytes: Int = 960_000) {
        self.ttl = ttl
        self.maxBytes = maxBytes
    }

    mutating func append(_ data: Data, now: Date = Date()) {
        guard !data.isEmpty else { return }
        evictExpired(now: now)

        if data.count >= maxBytes {
            let truncated = Data(data.suffix(maxBytes))
            chunks = [Chunk(data: truncated, createdAt: now)]
            totalBytes = truncated.count
            return
        }

        chunks.append(Chunk(data: data, createdAt: now))
        totalBytes += data.count
        evictOverflow()
    }

    mutating func drain(now: Date = Date()) -> [Data] {
        evictExpired(now: now)
        let drained = chunks.map(\.data)
        chunks.removeAll(keepingCapacity: true)
        totalBytes = 0
        return drained
    }

    mutating func prune(now: Date = Date()) {
        evictExpired(now: now)
    }

    private mutating func evictExpired(now: Date) {
        while let first = chunks.first, now.timeIntervalSince(first.createdAt) > ttl {
            totalBytes -= first.data.count
            chunks.removeFirst()
        }
    }

    private mutating func evictOverflow() {
        while totalBytes > maxBytes, !chunks.isEmpty {
            totalBytes -= chunks.removeFirst().data.count
        }
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
