import Foundation

public enum OmiSttFactory {
  public static func makeStreaming(
    engine: OmiSttEngine,
    deepgramAPIKey: String? = nil,
    parakeetAPIURL: String? = ProcessInfo.processInfo.environment["HOSTED_PARAKEET_API_URL"],
    sampleRate: Int = 16000,
    onTranscript: @escaping OmiTranscriptHandler
  ) throws -> OmiStreamingTranscriber {
    switch engine {
    case .deepgram:
      guard let key = deepgramAPIKey, !key.isEmpty else {
        throw NSError(domain: "omi.stt", code: 2, userInfo: [NSLocalizedDescriptionKey: "Deepgram API key required"])
      }
      return OmiDeepgramTranscriber(apiKey: key, sampleRate: sampleRate, onTranscript: onTranscript)
    case .parakeet:
      guard let url = parakeetAPIURL, !url.isEmpty else {
        throw NSError(
          domain: "omi.stt", code: 3, userInfo: [NSLocalizedDescriptionKey: "HOSTED_PARAKEET_API_URL required"])
      }
      return OmiParakeetTranscriber(apiURLString: url, sampleRate: sampleRate, onTranscript: onTranscript)
    case .whisper:
      throw NSError(
        domain: "omi.stt", code: 4,
        userInfo: [
          NSLocalizedDescriptionKey:
            "Use OmiWhisperTranscriber for offline frames; streaming Whisper uses getLiveTranscription"
        ])
    }
  }
}
