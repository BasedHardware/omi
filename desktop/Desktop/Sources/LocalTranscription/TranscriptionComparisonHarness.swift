import Foundation

struct TranscriptionComparisonProviderSnapshot: Equatable {
  var title: String
  var status: String
  var transcript: String
  var segmentCount: Int
  var wordCount: Int
  var error: String?

  static func empty(title: String, status: String = "Idle") -> Self {
    Self(title: title, status: status, transcript: "", segmentCount: 0, wordCount: 0, error: nil)
  }
}

struct TranscriptionComparisonTimeBucketSnapshot: Equatable, Identifiable {
  var id: String { "\(Int(startTime))-\(Int(endTime))" }
  var startTime: Double
  var endTime: Double
  var whisperText: String
  var deepgramText: String
  var whisperSegmentCount: Int
  var deepgramSegmentCount: Int

  var hasContent: Bool {
    !whisperText.isEmpty || !deepgramText.isEmpty
  }
}

struct TranscriptionComparisonHarnessSnapshot: Equatable {
  var isRunning: Bool
  var startedAt: Date?
  var whisper: TranscriptionComparisonProviderSnapshot
  var deepgram: TranscriptionComparisonProviderSnapshot
  var timeBuckets: [TranscriptionComparisonTimeBucketSnapshot]
  var wordDifferenceRate: Double?
  var characterDifferenceRate: Double?

  static let idle = TranscriptionComparisonHarnessSnapshot(
    isRunning: false,
    startedAt: nil,
    whisper: .empty(title: "Local Whisper"),
    deepgram: .empty(title: "Local Deepgram"),
    timeBuckets: [],
    wordDifferenceRate: nil,
    characterDifferenceRate: nil
  )
}

@MainActor
final class TranscriptionComparisonHarness {
  static let enabledDefaultsKey = "dev_transcription_comparison_harness_enabled"
  private static let transcriptPreviewLimit = 12_000
  private static let bucketDuration: Double = 30
  private static let maxBuckets = 8
  private static let bucketTextLimit = 900

  static var isEnabled: Bool {
    #if DEBUG
      return UserDefaults.standard.bool(forKey: enabledDefaultsKey)
    #else
      return false
    #endif
  }

  static func configuredDeepgramAPIKey() -> String? {
    APIKeyService.byokKey(.deepgram)
      ?? getenv("DEEPGRAM_API_KEY").flatMap { String(validatingUTF8: $0) }
  }

  private let language: String
  private var deepgramSession: DeepgramBackgroundTranscriptionSession?
  private var whisperSegments: [NormalizedTranscriptSegment] = []
  private var deepgramSegments: [NormalizedTranscriptSegment] = []
  private var whisperStatus = "Waiting for Whisper"
  private var deepgramStatus = "Waiting for Deepgram"
  private var whisperError: String?
  private var deepgramError: String?
  private(set) var snapshot: TranscriptionComparisonHarnessSnapshot
  private let onSnapshot: (TranscriptionComparisonHarnessSnapshot) -> Void

  init(
    language: String,
    deepgramAPIKey: String?,
    onSnapshot: @escaping (TranscriptionComparisonHarnessSnapshot) -> Void
  ) {
    self.language = language
    self.onSnapshot = onSnapshot
    deepgramStatus = deepgramAPIKey == nil ? "Missing Deepgram API key" : "Waiting for Deepgram"
    snapshot = TranscriptionComparisonHarnessSnapshot(
      isRunning: true,
      startedAt: Date(),
      whisper: .empty(title: "Local Whisper", status: "Waiting for Whisper"),
      deepgram: .empty(
        title: "Local Deepgram",
        status: deepgramAPIKey == nil ? "Missing Deepgram API key" : "Connecting"
      ),
      timeBuckets: [],
      wordDifferenceRate: nil,
      characterDifferenceRate: nil
    )

    if let deepgramAPIKey {
      deepgramSession = DeepgramBackgroundTranscriptionSession(
        language: language,
        apiKey: deepgramAPIKey,
        onSegments: { [weak self] segments in
          Task { @MainActor in
            self?.appendDeepgramSegments(segments)
          }
        },
        onStatus: { [weak self] status in
          Task { @MainActor in
            log("TranscriptionComparison: Deepgram \(status)")
            self?.deepgramStatus = status
            self?.publish()
          }
        },
        onError: { [weak self] error in
          Task { @MainActor in
            logError("TranscriptionComparison: Deepgram error", error: error)
            self?.deepgramStatus = "Failed"
            self?.deepgramError = error.localizedDescription
            self?.publish()
          }
        }
      )
    } else {
      deepgramError = "Add a Deepgram key in Developer API Keys or set DEEPGRAM_API_KEY."
    }
  }

  func start() {
    deepgramSession?.start()
    publish()
  }

  func appendAudio(_ pcmData: Data) {
    deepgramSession?.appendAudio(pcmData)
  }

  func appendWhisperSegments(_ segments: [NormalizedTranscriptSegment]) {
    guard !segments.isEmpty else { return }
    whisperStatus = "Receiving"
    merge(segments, into: &whisperSegments)
    publish()
  }

  #if DEBUG
    func appendDeepgramSegmentsForTesting(_ segments: [NormalizedTranscriptSegment]) {
      appendDeepgramSegments(segments)
    }
  #endif

  func finish() {
    deepgramSession?.finish()
    whisperStatus = whisperSegments.isEmpty ? "No transcript" : "Finalized"
    deepgramStatus =
      deepgramSegments.isEmpty && deepgramError == nil ? "Finalizing" : deepgramStatus
    publish(isRunning: false)
  }

  func stop() {
    deepgramSession?.stop()
    deepgramSession = nil
    publish(isRunning: false)
  }

  private func appendDeepgramSegments(_ segments: [NormalizedTranscriptSegment]) {
    guard !segments.isEmpty else { return }
    deepgramStatus = "Receiving"
    merge(segments, into: &deepgramSegments)
    publish()
  }

  private func merge(
    _ segments: [NormalizedTranscriptSegment],
    into target: inout [NormalizedTranscriptSegment]
  ) {
    for segment in segments where !segment.text.isEmpty {
      if let id = segment.segmentId,
        let existingIndex = target.firstIndex(where: { $0.segmentId == id })
      {
        target[existingIndex] = segment
      } else {
        target.append(segment)
      }
    }
    target.sort { lhs, rhs in
      if lhs.start == rhs.start {
        return lhs.end < rhs.end
      }
      return lhs.start < rhs.start
    }
  }

  private func publish(isRunning: Bool? = nil) {
    let whisperText = joinedTranscript(whisperSegments)
    let deepgramText = joinedTranscript(deepgramSegments)
    let whisperPreviewText = transcriptPreview(whisperText)
    let deepgramPreviewText = transcriptPreview(deepgramText)
    snapshot = TranscriptionComparisonHarnessSnapshot(
      isRunning: isRunning ?? snapshot.isRunning,
      startedAt: snapshot.startedAt,
      whisper: providerSnapshot(
        title: "Local Whisper",
        status: whisperStatus,
        transcript: whisperPreviewText,
        segments: whisperSegments,
        wordCount: TranscriptComparison.normalizedWords(whisperText).count,
        error: whisperError
      ),
      deepgram: providerSnapshot(
        title: "Local Deepgram",
        status: deepgramStatus,
        transcript: deepgramPreviewText,
        segments: deepgramSegments,
        wordCount: TranscriptComparison.normalizedWords(deepgramText).count,
        error: deepgramError
      ),
      timeBuckets: timeBuckets(whisper: whisperSegments, deepgram: deepgramSegments),
      wordDifferenceRate: comparisonRate(
        reference: whisperText,
        hypothesis: deepgramText,
        scorer: TranscriptComparison.wordErrorRate
      ),
      characterDifferenceRate: comparisonRate(
        reference: whisperText,
        hypothesis: deepgramText,
        scorer: TranscriptComparison.characterErrorRate
      )
    )
    onSnapshot(snapshot)
  }

  private func providerSnapshot(
    title: String,
    status: String,
    transcript: String,
    segments: [NormalizedTranscriptSegment],
    wordCount: Int,
    error: String?
  ) -> TranscriptionComparisonProviderSnapshot {
    TranscriptionComparisonProviderSnapshot(
      title: title,
      status: status,
      transcript: transcript,
      segmentCount: segments.count,
      wordCount: wordCount,
      error: error
    )
  }

  private func joinedTranscript(_ segments: [NormalizedTranscriptSegment]) -> String {
    segments
      .map(\.text)
      .joined(separator: " ")
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func transcriptPreview(_ joined: String) -> String {
    guard joined.count > Self.transcriptPreviewLimit else { return joined }
    return String(joined.suffix(Self.transcriptPreviewLimit))
  }

  private func timeBuckets(
    whisper: [NormalizedTranscriptSegment],
    deepgram: [NormalizedTranscriptSegment]
  ) -> [TranscriptionComparisonTimeBucketSnapshot] {
    let allSegments = whisper + deepgram
    guard let maxEnd = allSegments.map(\.end).max(), maxEnd > 0 else { return [] }

    let lastBucketIndex = max(0, Int(maxEnd / Self.bucketDuration))
    let firstBucketIndex = max(0, lastBucketIndex - Self.maxBuckets + 1)

    return (firstBucketIndex...lastBucketIndex).compactMap { index in
      let start = Double(index) * Self.bucketDuration
      let end = start + Self.bucketDuration
      let whisperInBucket = segments(whisper, overlappingStart: start, end: end)
      let deepgramInBucket = segments(deepgram, overlappingStart: start, end: end)
      let bucket = TranscriptionComparisonTimeBucketSnapshot(
        startTime: start,
        endTime: end,
        whisperText: bucketText(whisperInBucket),
        deepgramText: bucketText(deepgramInBucket),
        whisperSegmentCount: whisperInBucket.count,
        deepgramSegmentCount: deepgramInBucket.count
      )
      return bucket.hasContent ? bucket : nil
    }
  }

  private func segments(
    _ segments: [NormalizedTranscriptSegment],
    overlappingStart start: Double,
    end: Double
  ) -> [NormalizedTranscriptSegment] {
    segments
      .filter { $0.end > start && $0.start < end }
      .sorted { lhs, rhs in
        if lhs.start == rhs.start {
          return lhs.end < rhs.end
        }
        return lhs.start < rhs.start
      }
  }

  private func bucketText(_ segments: [NormalizedTranscriptSegment]) -> String {
    let joined =
      segments
      .map(\.text)
      .joined(separator: " ")
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard joined.count > Self.bucketTextLimit else { return joined }
    return String(joined.prefix(Self.bucketTextLimit)) + "..."
  }

  private func comparisonRate(
    reference: String,
    hypothesis: String,
    scorer: (String, String) -> Double
  ) -> Double? {
    guard !TranscriptComparison.normalizedText(reference).isEmpty,
      !TranscriptComparison.normalizedText(hypothesis).isEmpty
    else {
      return nil
    }
    return scorer(reference, hypothesis)
  }
}

final class DeepgramBackgroundTranscriptionSession {
  private struct Response: Decodable {
    struct Channel: Decodable {
      struct Alternative: Decodable {
        var transcript: String?
      }

      var alternatives: [Alternative]
    }

    var type: String?
    var channel: Channel?
    var isFinal: Bool?
    var speechFinal: Bool?
    var start: Double?
    var duration: Double?

    enum CodingKeys: String, CodingKey {
      case type
      case channel
      case isFinal = "is_final"
      case speechFinal = "speech_final"
      case start
      case duration
    }
  }

  private let language: String
  private let apiKey: String
  private let onSegments: ([NormalizedTranscriptSegment]) -> Void
  private let onStatus: (String) -> Void
  private let onError: (Error) -> Void
  private var webSocketTask: URLSessionWebSocketTask?
  private var urlSession: URLSession?
  private let queue = DispatchQueue(label: "com.omi.transcription.deepgram-comparison")
  private var isConnected = false
  private var pendingAudioChunks: [Data] = []
  private var pendingAudioBytes = 0
  private var isSendingAudio = false
  private let pendingAudioLimit = 16_000 * 2 * 8
  private var keepAliveTimer: DispatchSourceTimer?
  private var shouldReconnect = false
  private var isFinishing = false
  private var reconnectAttempt = 0

  init(
    language: String,
    apiKey: String,
    onSegments: @escaping ([NormalizedTranscriptSegment]) -> Void,
    onStatus: @escaping (String) -> Void,
    onError: @escaping (Error) -> Void
  ) {
    self.language = language
    self.apiKey = apiKey
    self.onSegments = onSegments
    self.onStatus = onStatus
    self.onError = onError
  }

  func start() {
    queue.async {
      guard self.webSocketTask == nil else { return }
      self.shouldReconnect = true
      self.isFinishing = false
      self.reconnectAttempt = 0
      self.openSocket()
    }
  }

  private func openSocket() {
    guard var components = URLComponents(string: "wss://api.deepgram.com/v1/listen") else {
      return
    }
    var queryItems = [
      URLQueryItem(name: "model", value: "nova-3"),
      URLQueryItem(name: "encoding", value: "linear16"),
      URLQueryItem(name: "sample_rate", value: "16000"),
      URLQueryItem(name: "channels", value: "1"),
      URLQueryItem(name: "interim_results", value: "false"),
      URLQueryItem(name: "smart_format", value: "true"),
      URLQueryItem(name: "punctuate", value: "true"),
    ]
    if language != "multi" {
      queryItems.append(URLQueryItem(name: "language", value: language))
    }
    components.queryItems = queryItems

    guard let url = components.url else { return }
    var request = URLRequest(url: url)
    request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")

    let configuration = URLSessionConfiguration.default
    configuration.timeoutIntervalForRequest = 30
    configuration.timeoutIntervalForResource = 0
    let session = URLSession(configuration: configuration)
    urlSession = session
    webSocketTask = session.webSocketTask(with: request)
    webSocketTask?.resume()
    receiveMessage()

    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
      guard let self else { return }
      self.queue.async {
        guard self.webSocketTask?.state == .running else {
          self.handleConnectionFailure(
            NSError(
              domain: "DeepgramBackgroundTranscriptionSession",
              code: 1,
              userInfo: [NSLocalizedDescriptionKey: "Failed to connect to Deepgram"]
            )
          )
          return
        }
        self.isConnected = true
        self.reconnectAttempt = 0
        self.onStatus("Connected")
        self.startKeepAliveTimer()
        self.drainAudioQueue()
      }
    }
  }

  func appendAudio(_ data: Data) {
    queue.async {
      self.enqueueAudio(data)
      self.drainAudioQueue()
    }
  }

  func finish() {
    queue.async {
      self.isFinishing = true
      self.shouldReconnect = false
      guard self.isConnected else {
        self.stopKeepAliveTimer()
        self.onStatus("Finalized")
        return
      }
      self.sendString("{\"type\":\"CloseStream\"}")
      self.onStatus("Finalizing")
    }
  }

  func stop() {
    queue.async {
      self.shouldReconnect = false
      self.isFinishing = false
      self.isConnected = false
      self.isSendingAudio = false
      self.stopKeepAliveTimer()
      self.webSocketTask?.cancel(with: .normalClosure, reason: nil)
      self.webSocketTask = nil
      self.urlSession?.invalidateAndCancel()
      self.urlSession = nil
      self.pendingAudioChunks.removeAll()
      self.pendingAudioBytes = 0
      self.onStatus("Stopped")
    }
  }

  private func enqueueAudio(_ data: Data) {
    pendingAudioChunks.append(data)
    pendingAudioBytes += data.count
    while pendingAudioBytes > pendingAudioLimit, !pendingAudioChunks.isEmpty {
      pendingAudioBytes -= pendingAudioChunks.removeFirst().count
    }
  }

  private func drainAudioQueue() {
    guard isConnected, !isSendingAudio, !pendingAudioChunks.isEmpty else { return }
    let data = pendingAudioChunks.removeFirst()
    pendingAudioBytes -= data.count
    isSendingAudio = true
    webSocketTask?.send(.data(data)) { [weak self] error in
      guard let self else { return }
      self.queue.async {
        self.isSendingAudio = false
        if let error {
          self.handleConnectionFailure(error)
          return
        }
        self.drainAudioQueue()
      }
    }
  }

  private func sendString(_ value: String) {
    webSocketTask?.send(.string(value)) { [weak self] error in
      if let error {
        self?.queue.async {
          self?.handleConnectionFailure(error)
        }
      }
    }
  }

  private func receiveMessage() {
    webSocketTask?.receive { [weak self] result in
      guard let self else { return }
      switch result {
      case .success(let message):
        self.handleMessage(message)
        self.receiveMessage()
      case .failure(let error):
        self.queue.async {
          self.handleConnectionFailure(error)
        }
      }
    }
  }

  private func startKeepAliveTimer() {
    stopKeepAliveTimer()
    let timer = DispatchSource.makeTimerSource(queue: queue)
    timer.schedule(deadline: .now() + 5, repeating: 5)
    timer.setEventHandler { [weak self] in
      guard let self, self.isConnected else { return }
      self.sendString("{\"type\":\"KeepAlive\"}")
    }
    keepAliveTimer = timer
    timer.resume()
  }

  private func stopKeepAliveTimer() {
    keepAliveTimer?.cancel()
    keepAliveTimer = nil
  }

  private func handleConnectionFailure(_ error: Error) {
    guard shouldReconnect || isConnected else { return }
    isConnected = false
    isSendingAudio = false
    stopKeepAliveTimer()
    webSocketTask?.cancel(with: .goingAway, reason: nil)
    webSocketTask = nil
    urlSession?.invalidateAndCancel()
    urlSession = nil

    guard shouldReconnect, !isFinishing else {
      onError(error)
      return
    }

    reconnectAttempt += 1
    let delay = min(10.0, pow(2.0, Double(min(reconnectAttempt, 3))))
    onStatus("Reconnecting in \(Int(delay))s")
    queue.asyncAfter(deadline: .now() + delay) { [weak self] in
      guard let self, self.shouldReconnect, self.webSocketTask == nil else { return }
      self.onStatus("Reconnecting")
      self.openSocket()
    }
  }

  private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
    let data: Data?
    switch message {
    case .string(let text):
      data = text.data(using: .utf8)
    case .data(let messageData):
      data = messageData
    @unknown default:
      data = nil
    }

    guard let data,
      let response = try? JSONDecoder().decode(Response.self, from: data),
      response.isFinal == true,
      let transcript = response.channel?.alternatives.first?.transcript?
        .trimmingCharacters(in: .whitespacesAndNewlines),
      !transcript.isEmpty
    else {
      return
    }

    let start = response.start ?? 0
    let end = start + (response.duration ?? 0)
    onSegments([
      NormalizedTranscriptSegment(
        segmentId: "deepgram-bg-\(UUID().uuidString)",
        speaker: 0,
        speakerLabel: nil,
        text: transcript,
        start: start,
        end: end,
        isUser: true,
        personId: nil,
        translations: []
      )
    ])
  }
}
