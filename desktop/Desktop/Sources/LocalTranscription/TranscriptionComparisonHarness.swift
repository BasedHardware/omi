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

struct TranscriptionComparisonHarnessSnapshot: Equatable {
  var isRunning: Bool
  var startedAt: Date?
  var whisper: TranscriptionComparisonProviderSnapshot
  var deepgram: TranscriptionComparisonProviderSnapshot
  var wordDifferenceRate: Double?
  var characterDifferenceRate: Double?

  static let idle = TranscriptionComparisonHarnessSnapshot(
    isRunning: false,
    startedAt: nil,
    whisper: .empty(title: "Local Whisper"),
    deepgram: .empty(title: "Local Deepgram"),
    wordDifferenceRate: nil,
    characterDifferenceRate: nil
  )
}

@MainActor
final class TranscriptionComparisonHarness {
  static let enabledDefaultsKey = "dev_transcription_comparison_harness_enabled"

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
            self?.deepgramStatus = status
            self?.publish()
          }
        },
        onError: { [weak self] error in
          Task { @MainActor in
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
    snapshot = TranscriptionComparisonHarnessSnapshot(
      isRunning: isRunning ?? snapshot.isRunning,
      startedAt: snapshot.startedAt,
      whisper: providerSnapshot(
        title: "Local Whisper",
        status: whisperStatus,
        transcript: whisperText,
        segments: whisperSegments,
        error: whisperError
      ),
      deepgram: providerSnapshot(
        title: "Local Deepgram",
        status: deepgramStatus,
        transcript: deepgramText,
        segments: deepgramSegments,
        error: deepgramError
      ),
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
    error: String?
  ) -> TranscriptionComparisonProviderSnapshot {
    TranscriptionComparisonProviderSnapshot(
      title: title,
      status: status,
      transcript: transcript,
      segmentCount: segments.count,
      wordCount: TranscriptComparison.normalizedWords(transcript).count,
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
  private var isConnected = false
  private var pendingAudio = Data()
  private let pendingAudioLimit = 16_000 * 2 * 5

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
    guard webSocketTask == nil else { return }
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
      guard self.webSocketTask?.state == .running else {
        self.onStatus("Failed to connect")
        return
      }
      self.isConnected = true
      self.onStatus("Connected")
      self.flushPendingAudio()
    }
  }

  func appendAudio(_ data: Data) {
    guard isConnected else {
      pendingAudio.append(data)
      if pendingAudio.count > pendingAudioLimit {
        pendingAudio.removeFirst(pendingAudio.count - pendingAudioLimit)
      }
      return
    }
    sendAudio(data)
  }

  func finish() {
    guard isConnected else { return }
    sendString("{\"type\":\"CloseStream\"}")
    onStatus("Finalizing")
  }

  func stop() {
    isConnected = false
    webSocketTask?.cancel(with: .normalClosure, reason: nil)
    webSocketTask = nil
    urlSession?.invalidateAndCancel()
    urlSession = nil
    pendingAudio.removeAll()
    onStatus("Stopped")
  }

  private func flushPendingAudio() {
    guard !pendingAudio.isEmpty else { return }
    let audio = pendingAudio
    pendingAudio.removeAll()
    sendAudio(audio)
  }

  private func sendAudio(_ data: Data) {
    webSocketTask?.send(.data(data)) { [weak self] error in
      if let error {
        self?.onError(error)
      }
    }
  }

  private func sendString(_ value: String) {
    webSocketTask?.send(.string(value)) { [weak self] error in
      if let error {
        self?.onError(error)
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
        guard self.isConnected else { return }
        self.isConnected = false
        self.onError(error)
      }
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
