import AVFoundation
import Foundation

@MainActor
final class FloatingBarVoicePlaybackService: NSObject, AVAudioPlayerDelegate {
  static let shared = FloatingBarVoicePlaybackService()

  static let devAPIKeyDefaultsKey = "dev_elevenlabs_api_key"
  static let devVoiceIDDefaultsKey = "dev_elevenlabs_voice_id"

  nonisolated private static let defaultVoiceID = "BAMYoBHLZM7lJgJAmFz0"  // Sloane
  nonisolated private static let defaultModelID = "eleven_turbo_v2_5"
  nonisolated private static let minimumChunkLength = 40
  nonisolated private static let preferredChunkLength = 120
  nonisolated private static let emergencyChunkLength = 200
  private var playbackRate: Float { ShortcutSettings.shared.voicePlaybackSpeed }

  nonisolated private static let fillerPhrases: [String] = [
    "Let me check.",
    "One moment.",
    "Looking into it.",
    "Let me see.",
    "Checking now.",
    "Hold on.",
    "One sec.",
    "Working on it.",
  ]

  private var playbackTask: Task<Void, Never>?
  private var fillerTask: Task<Void, Never>?
  private var currentMode: PlaybackMode?
  private var streamedText = ""
  private var bufferedText = ""
  private var synthesisQueue: [String] = []
  private var audioQueue: [Data] = []
  private var isSynthesizing = false
  private var hasStartedRealPlayback = false
  private var audioPlayer: AVAudioPlayer?
  private let speechSynthesizer = AVSpeechSynthesizer()

  private override init() {}

  var isSpeaking: Bool {
    if audioPlayer?.isPlaying == true { return true }
    if speechSynthesizer.isSpeaking { return true }
    if fillerTask != nil || playbackTask != nil { return true }
    if isSynthesizing { return true }
    return !audioQueue.isEmpty || !synthesisQueue.isEmpty
  }

  func playFillerIfEnabled() {
    guard ShortcutSettings.shared.hasAnyFloatingBarVoiceAnswersEnabled else { return }

    if currentMode == nil {
      currentMode = resolvePlaybackMode()
    }
    guard let mode = currentMode, case .elevenLabs(let apiKey, let voiceID) = mode else { return }

    hasStartedRealPlayback = false
    let phrase = Self.fillerPhrases.randomElement()!
    fillerTask = Task { [weak self] in
      do {
        let audioData = try await Self.synthesizeSpeech(
          text: phrase, apiKey: apiKey, voiceID: voiceID)
        try Task.checkCancellation()
        await MainActor.run {
          guard let self, !self.hasStartedRealPlayback else { return }
          self.startPlayback(audioData)
        }
      } catch {}
    }
  }

  func playResponseIfEnabled(_ message: ChatMessage?) {
    guard ShortcutSettings.shared.hasAnyFloatingBarVoiceAnswersEnabled else { return }
    updateStreamingResponseIfEnabled(message, isFinal: true)
  }

  func updateStreamingResponseIfEnabled(_ message: ChatMessage?, isFinal: Bool) {
    guard ShortcutSettings.shared.hasAnyFloatingBarVoiceAnswersEnabled else { return }

    let text = Self.cleanedPlaybackText(from: message)
    guard !text.isEmpty, Self.shouldSpeak(text) else { return }

    if currentMode == nil {
      currentMode = resolvePlaybackMode()
    }

    guard let mode = currentMode else {
      return
    }

    if !text.hasPrefix(streamedText) {
      streamedText = ""
      bufferedText = ""
      synthesisQueue.removeAll()
      audioQueue.removeAll()
    }

    // Cancel filler and stop filler audio when first real chunk is ready
    if !hasStartedRealPlayback && text.count > 0 {
      hasStartedRealPlayback = true
      fillerTask?.cancel()
      fillerTask = nil
      audioPlayer?.stop()
      audioPlayer = nil
      speechSynthesizer.stopSpeaking(at: .immediate)
    }

    if text.count > streamedText.count {
      let newText = String(text.dropFirst(streamedText.count))
      streamedText = text
      bufferedText += newText
      drainBufferedText(isFinal: isFinal, mode: mode)
    } else if isFinal {
      drainBufferedText(isFinal: true, mode: mode)
    }
  }

  private func resolvePlaybackMode() -> PlaybackMode {
    guard
      let apiKey = APIKeyService.currentElevenLabsKey?.trimmingCharacters(
        in: .whitespacesAndNewlines),
      !apiKey.isEmpty
    else {
      return .systemFallback
    }

    return .elevenLabs(apiKey: apiKey, voiceID: Self.defaultVoiceID)
  }

  private func drainBufferedText(isFinal: Bool, mode: PlaybackMode) {
    while let boundary = Self.nextChunkBoundary(in: bufferedText, isFinal: isFinal) {
      let chunk = String(bufferedText[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)
      bufferedText = String(bufferedText[boundary...]).trimmingCharacters(
        in: .whitespacesAndNewlines)

      guard !chunk.isEmpty, Self.shouldSpeak(chunk) else { continue }
      enqueueChunk(chunk, mode: mode)
    }
  }

  private func enqueueChunk(_ text: String, mode: PlaybackMode) {
    switch mode {
    case .systemFallback:
      enqueueSystemSpeech(text)
    case .elevenLabs:
      synthesisQueue.append(text)
      startSynthesisIfNeeded(mode: mode)
    }
  }

  private func startSynthesisIfNeeded(mode: PlaybackMode) {
    guard !isSynthesizing else { return }
    guard case .elevenLabs(let apiKey, let voiceID) = mode else { return }
    guard !synthesisQueue.isEmpty else { return }

    let text = synthesisQueue.removeFirst()
    isSynthesizing = true
    playbackTask?.cancel()
    playbackTask = Task { [weak self] in
      do {
        let audioData = try await Self.synthesizeSpeech(
          text: text, apiKey: apiKey, voiceID: voiceID)
        try Task.checkCancellation()
        await MainActor.run {
          guard let self else { return }
          self.isSynthesizing = false
          self.audioQueue.append(audioData)
          self.startPlaybackIfNeeded()
          self.startSynthesisIfNeeded(mode: mode)
        }
      } catch is CancellationError {
      } catch {
        await MainActor.run {
          guard let self else { return }
          self.isSynthesizing = false
          log(
            "FloatingBarVoicePlaybackService: ElevenLabs chunk synthesis failed, falling back to system voice: \(error.localizedDescription)"
          )
          self.enqueueSystemSpeech(text)
          self.startSynthesisIfNeeded(mode: mode)
        }
      }
    }
  }

  func stop() {
    playbackTask?.cancel()
    playbackTask = nil
    fillerTask?.cancel()
    fillerTask = nil
    currentMode = nil
    streamedText = ""
    bufferedText = ""
    synthesisQueue.removeAll()
    audioQueue.removeAll()
    isSynthesizing = false
    hasStartedRealPlayback = false
    audioPlayer?.stop()
    audioPlayer = nil
    speechSynthesizer.stopSpeaking(at: .immediate)
  }

  private func startPlaybackIfNeeded() {
    guard audioPlayer == nil else { return }
    guard !audioQueue.isEmpty else { return }
    startPlayback(audioQueue.removeFirst())
  }

  private func startPlayback(_ data: Data) {
    do {
      let player = try AVAudioPlayer(data: data)
      player.delegate = self
      player.enableRate = true
      player.rate = playbackRate
      player.prepareToPlay()
      player.play()
      audioPlayer = player
    } catch {
      log(
        "FloatingBarVoicePlaybackService: could not start audio playback: \(error.localizedDescription)"
      )
    }
  }

  private func enqueueSystemSpeech(_ text: String) {
    let utterance = AVSpeechUtterance(string: text)
    utterance.rate = 0.47
    utterance.pitchMultiplier = 1.02
    utterance.volume = 1.0
    utterance.voice = preferredSystemVoice()
    speechSynthesizer.speak(utterance)
  }

  nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.audioPlayer = nil
      self.startPlaybackIfNeeded()
    }
  }

  private func preferredSystemVoice() -> AVSpeechSynthesisVoice? {
    let preferredNames = ["Ava", "Allison", "Samantha", "Karen", "Moira"]
    for name in preferredNames {
      if let voice = AVSpeechSynthesisVoice.speechVoices().first(where: {
        $0.name.localizedCaseInsensitiveContains(name)
      }) {
        return voice
      }
    }
    return AVSpeechSynthesisVoice(language: "en-US")
  }

  private nonisolated static func synthesizeSpeech(text: String, apiKey: String, voiceID: String)
    async throws -> Data
  {
    var request = URLRequest(
      url: URL(string: "https://api.elevenlabs.io/v1/text-to-speech/\(voiceID)")!)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("audio/mpeg", forHTTPHeaderField: "Accept")
    request.setValue(apiKey, forHTTPHeaderField: "xi-api-key")
    request.timeoutInterval = 45

    let body = ElevenLabsSpeechRequest(
      text: text,
      modelID: defaultModelID,
      outputFormat: "mp3_44100_128",
      voiceSettings: .init(
        stability: 0.34,
        similarityBoost: 0.88,
        style: 0.12,
        useSpeakerBoost: true
      )
    )
    request.httpBody = try JSONEncoder().encode(body)

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw FloatingBarVoicePlaybackError.invalidResponse
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
      let errorBody = String(data: data.prefix(300), encoding: .utf8) ?? "Unknown error"
      throw FloatingBarVoicePlaybackError.requestFailed(
        statusCode: httpResponse.statusCode, body: errorBody)
    }
    return data
  }

  private nonisolated static func cleanedPlaybackText(from message: ChatMessage?) -> String {
    guard let message else { return "" }

    let baseText: String
    if !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      baseText = message.text
    } else {
      baseText = message.contentBlocks.compactMap { block in
        switch block {
        case .text(_, let text):
          return text
        case .discoveryCard(_, let title, let summary, _):
          return "\(title). \(summary)"
        case .toolCall, .thinking:
          return nil
        }
      }.joined(separator: "\n\n")
    }

    let collapsedWhitespace = baseText.replacingOccurrences(
      of: "\\s+", with: " ", options: .regularExpression)
    return collapsedWhitespace.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private nonisolated static func shouldSpeak(_ text: String) -> Bool {
    let lowercased = text.lowercased()
    if lowercased == "failed to get a response. please try again." {
      return false
    }
    if lowercased.hasPrefix("⚠️") || lowercased.hasPrefix("warning:") {
      return false
    }
    return true
  }

  private nonisolated static func nextChunkBoundary(in text: String, isFinal: Bool) -> String.Index?
  {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }

    if isFinal {
      return text.endIndex
    }

    guard text.count >= minimumChunkLength else { return nil }

    let preferredLimit = text.index(
      text.startIndex, offsetBy: min(text.count, preferredChunkLength))
    let preferredSlice = text[..<preferredLimit]

    if let punctuationIndex = preferredSlice.lastIndex(where: { ".!?\n".contains($0) }) {
      return text.index(after: punctuationIndex)
    }

    guard text.count >= preferredChunkLength else { return nil }

    let emergencyLimit = text.index(
      text.startIndex, offsetBy: min(text.count, emergencyChunkLength))
    let emergencySlice = text[..<emergencyLimit]

    if let punctuationIndex = emergencySlice.lastIndex(where: { ".!?\n".contains($0) }) {
      return text.index(after: punctuationIndex)
    }

    guard text.count >= emergencyChunkLength else { return nil }

    if let clauseIndex = emergencySlice.lastIndex(where: { ",;:\n".contains($0) }) {
      return text.index(after: clauseIndex)
    }

    if let whitespaceIndex = emergencySlice.lastIndex(where: \.isWhitespace) {
      return whitespaceIndex
    }

    return emergencyLimit
  }
}

private enum PlaybackMode {
  case elevenLabs(apiKey: String, voiceID: String)
  case systemFallback
}

private struct ElevenLabsSpeechRequest: Encodable {
  let text: String
  let modelID: String
  let outputFormat: String
  let voiceSettings: ElevenLabsVoiceSettings

  enum CodingKeys: String, CodingKey {
    case text
    case modelID = "model_id"
    case outputFormat = "output_format"
    case voiceSettings = "voice_settings"
  }
}

private struct ElevenLabsVoiceSettings: Encodable {
  let stability: Double
  let similarityBoost: Double
  let style: Double
  let useSpeakerBoost: Bool

  enum CodingKeys: String, CodingKey {
    case stability
    case similarityBoost = "similarity_boost"
    case style
    case useSpeakerBoost = "use_speaker_boost"
  }
}

private enum FloatingBarVoicePlaybackError: LocalizedError {
  case invalidResponse
  case requestFailed(statusCode: Int, body: String)

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Invalid ElevenLabs response"
    case .requestFailed(let statusCode, let body):
      return "ElevenLabs request failed (\(statusCode)): \(body)"
  }
}
}
