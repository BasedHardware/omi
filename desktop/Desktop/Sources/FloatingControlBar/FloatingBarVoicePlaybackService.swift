import AVFoundation
import Foundation

@MainActor
final class FloatingBarVoicePlaybackService: NSObject, AVAudioPlayerDelegate {
  static let shared = FloatingBarVoicePlaybackService()

  nonisolated private static let openAITTSModelID = "gpt-4o-mini-tts"
  // First chunk stays small so playback starts fast.
  nonisolated private static let firstChunkMinimumLength = 40
  nonisolated private static let firstChunkPreferredLength = 120
  nonisolated private static let firstChunkEmergencyLength = 200
  // Follow-up chunks are much larger so the response is stitched from fewer
  // generated audio clips. Each chunk boundary carries leading/trailing silence,
  // so fewer chunks means far less perceived pausing between sentences and
  // paragraphs of a long answer.
  nonisolated private static let followupChunkMinimumLength = 320
  nonisolated private static let followupChunkPreferredLength = 520
  nonisolated private static let followupChunkEmergencyLength = 800
  private var playbackRate: Float { ShortcutSettings.shared.voicePlaybackSpeed }

  nonisolated private static let voiceSampleText = "Hey, how is it going?"

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
  private var currentResponseID: String?
  private var interruptedResponseID: String?
  private var shouldInterruptNextResponse = false
  private var streamedText = ""
  private var bufferedText = ""
  private var synthesisQueue: [String] = []
  private var audioQueue: [Data] = []
  private var isSynthesizing = false
  private var hasStartedRealPlayback = false
  private var hasEmittedFirstChunk = false
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
    hasStartedRealPlayback = false
    let phrase = Self.fillerPhrases.randomElement()!

    guard let mode = currentMode else { return }
    switch mode {
    case .systemVoice(let voice):
      enqueueSystemSpeech(phrase, voice: voice)
    case .openAI(let voiceID, let instructions):
      fillerTask = Task { [weak self] in
        do {
          let audioData = try await Self.synthesizeOpenAISpeech(
            text: phrase, voiceID: voiceID, instructions: instructions)
          try Task.checkCancellation()
          await MainActor.run {
            guard let self, !self.hasStartedRealPlayback else { return }
            self.startPlayback(audioData)
          }
        } catch {}
      }
    }
  }

  func playResponseIfEnabled(_ message: ChatMessage?) {
    guard ShortcutSettings.shared.hasAnyFloatingBarVoiceAnswersEnabled else { return }
    updateStreamingResponseIfEnabled(message, isFinal: true)
  }

  func updateStreamingResponseIfEnabled(_ message: ChatMessage?, isFinal: Bool) {
    guard ShortcutSettings.shared.hasAnyFloatingBarVoiceAnswersEnabled else { return }
    guard let message else { return }

    if currentResponseID != message.id {
      resetPlaybackPipeline(clearMode: false)
      currentResponseID = message.id
      interruptedResponseID = shouldInterruptNextResponse ? message.id : nil
      shouldInterruptNextResponse = false
    }

    let text = Self.cleanedPlaybackText(from: message)
    guard !text.isEmpty, Self.shouldSpeak(text) else { return }

    if interruptedResponseID == message.id {
      streamedText = text
      bufferedText = ""
      return
    }

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
    let selectedVoice = ShortcutSettings.voiceOption(for: ShortcutSettings.shared.selectedVoiceID)

    if selectedVoice.isOpenAI, let openAIVoice = selectedVoice.openAIVoice {
      guard Self.openAIAPIKey() != nil else {
        log("FloatingBarVoicePlaybackService: OpenAI TTS selected but no OpenAI BYOK key is configured")
        return .systemVoice(ShortcutSettings.voiceOption(for: ShortcutSettings.localShelleyVoiceID))
      }
      return .openAI(
        voiceID: openAIVoice,
        instructions: selectedVoice.openAIInstructions ?? ""
      )
    }

    return .systemVoice(selectedVoice)
  }

  private func drainBufferedText(isFinal: Bool, mode: PlaybackMode) {
    while let boundary = Self.nextChunkBoundary(
      in: bufferedText, isFinal: isFinal, isFirstChunk: !hasEmittedFirstChunk)
    {
      let chunk = String(bufferedText[..<boundary]).trimmingCharacters(in: .whitespacesAndNewlines)
      bufferedText = String(bufferedText[boundary...]).trimmingCharacters(
        in: .whitespacesAndNewlines)

      guard !chunk.isEmpty, Self.shouldSpeak(chunk) else { continue }
      hasEmittedFirstChunk = true
      enqueueChunk(chunk, mode: mode)
    }
  }

  private func enqueueChunk(_ text: String, mode: PlaybackMode) {
    switch mode {
    case .systemVoice(let voice):
      enqueueSystemSpeech(text, voice: voice)
    case .openAI:
      synthesisQueue.append(text)
      startSynthesisIfNeeded(mode: mode)
    }
  }

  private func startSynthesisIfNeeded(mode: PlaybackMode) {
    guard !isSynthesizing else { return }
    guard !synthesisQueue.isEmpty else { return }

    let text = synthesisQueue.removeFirst()
    isSynthesizing = true
    playbackTask?.cancel()
    playbackTask = Task { [weak self] in
      do {
        let audioData: Data
        switch mode {
        case .openAI(let voiceID, let instructions):
          audioData = try await Self.synthesizeOpenAISpeech(
            text: text, voiceID: voiceID, instructions: instructions)
        case .systemVoice:
          return
        }
        try Task.checkCancellation()
        await MainActor.run {
          guard let self else { return }
          self.isSynthesizing = false
          self.audioQueue.append(audioData)
          self.startPlaybackIfNeeded()
          self.startSynthesisIfNeeded(mode: mode)
        }
      } catch is CancellationError {
        await MainActor.run {
          guard let self else { return }
          self.isSynthesizing = false
          self.startSynthesisIfNeeded(mode: mode)
        }
      } catch {
        if Self.isCancellation(error) {
          await MainActor.run {
            guard let self else { return }
            self.isSynthesizing = false
            self.startSynthesisIfNeeded(mode: mode)
          }
          return
        }

        await MainActor.run {
          guard let self else { return }
          self.isSynthesizing = false
          log(
            "FloatingBarVoicePlaybackService: cloud TTS chunk synthesis failed, falling back to system voice: \(error.localizedDescription)"
          )
          self.enqueueSystemSpeech(
            text, voice: ShortcutSettings.voiceOption(for: ShortcutSettings.localShelleyVoiceID))
          self.startSynthesisIfNeeded(mode: mode)
        }
      }
    }
  }

  func stop() {
    resetPlaybackPipeline(clearMode: true)
    currentResponseID = nil
    interruptedResponseID = nil
    shouldInterruptNextResponse = false
  }

  /// Play a short preview of the given voice so the user can hear it
  /// when switching voices in settings.
  func playVoiceSample(voiceID: String) {
    resetPlaybackPipeline(clearMode: true)
    currentResponseID = nil
    interruptedResponseID = nil
    shouldInterruptNextResponse = false

    let phrase = Self.voiceSampleText
    let voice = ShortcutSettings.voiceOption(for: voiceID)

    if voice.isLocalSystem {
      enqueueSystemSpeech(phrase, voice: voice)
      return
    }

    if voice.isOpenAI, let openAIVoice = voice.openAIVoice {
      playbackTask = Task { [weak self] in
        do {
          let audioData = try await Self.synthesizeOpenAISpeech(
            text: phrase, voiceID: openAIVoice, instructions: voice.openAIInstructions ?? "")
          try Task.checkCancellation()
          await MainActor.run {
            guard let self else { return }
            self.startPlayback(audioData)
          }
        } catch is CancellationError {
          return
        } catch {
          if Self.isCancellation(error) { return }
          log(
            "FloatingBarVoicePlaybackService: OpenAI voice sample failed: \(error.localizedDescription)"
          )
        }
      }
      return
    }

    enqueueSystemSpeech(
      phrase, voice: ShortcutSettings.voiceOption(for: ShortcutSettings.localShelleyVoiceID))
  }

  /// Synthesize and play a single short phrase via the selected voice. Used by
  /// agent pills to speak a short acknowledgement like "On it" before the agent kicks off.
  func speakOneShot(_ text: String) {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    let mode = currentMode ?? resolvePlaybackMode()
    currentMode = mode
    switch mode {
    case .openAI(let voiceID, let instructions):
      Task { [weak self] in
        do {
          let audio = try await Self.synthesizeOpenAISpeech(
            text: trimmed, voiceID: voiceID, instructions: instructions)
          await MainActor.run {
            self?.startPlayback(audio)
          }
        } catch {
          await MainActor.run {
            self?.enqueueSystemSpeech(
              trimmed,
              voice: ShortcutSettings.voiceOption(for: ShortcutSettings.localShelleyVoiceID))
          }
        }
      }
    case .systemVoice(let voice):
      enqueueSystemSpeech(trimmed, voice: voice)
    }
  }

  func interruptCurrentResponse() {
    if let currentResponseID {
      interruptedResponseID = currentResponseID
      shouldInterruptNextResponse = false
    } else {
      shouldInterruptNextResponse = true
    }
    resetPlaybackPipeline(clearMode: false)
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

  private func enqueueSystemSpeech(_ text: String, voice: ShortcutSettings.VoiceOption) {
    let utterance = AVSpeechUtterance(string: text)
    utterance.rate = localSpeechRate()
    utterance.pitchMultiplier = localPitchMultiplier(for: voice)
    utterance.volume = 1.0
    utterance.voice = preferredSystemVoice(for: voice)
    speechSynthesizer.speak(utterance)
  }

  private func localSpeechRate() -> Float {
    let baseRate: Float = 0.42
    let scaledRate = baseRate * (playbackRate / 1.4)
    return min(
      AVSpeechUtteranceMaximumSpeechRate,
      max(AVSpeechUtteranceMinimumSpeechRate, scaledRate)
    )
  }

  private func localPitchMultiplier(for voice: ShortcutSettings.VoiceOption) -> Float {
    switch voice.id {
    case ShortcutSettings.localShelleyVoiceID:
      return 0.82
    case "local:deep":
      return 0.88
    default:
      return 1.02
    }
  }

  nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.audioPlayer = nil
      self.startPlaybackIfNeeded()
    }
  }

  private func resetPlaybackPipeline(clearMode: Bool) {
    playbackTask?.cancel()
    playbackTask = nil
    fillerTask?.cancel()
    fillerTask = nil
    if clearMode {
      currentMode = nil
    }
    streamedText = ""
    bufferedText = ""
    synthesisQueue.removeAll()
    audioQueue.removeAll()
    isSynthesizing = false
    hasStartedRealPlayback = false
    hasEmittedFirstChunk = false
    audioPlayer?.stop()
    audioPlayer = nil
    speechSynthesizer.stopSpeaking(at: .immediate)
  }

  private func preferredSystemVoice(for option: ShortcutSettings.VoiceOption) -> AVSpeechSynthesisVoice? {
    let voices = AVSpeechSynthesisVoice.speechVoices()
    for identifier in option.preferredSystemVoiceIdentifiers {
      if let voice = AVSpeechSynthesisVoice(identifier: identifier) {
        return voice
      }
    }
    for name in option.preferredSystemVoiceNames {
      if let voice = voices.first(where: {
        $0.language == "en-US" && $0.name.localizedCaseInsensitiveContains(name)
      }) {
        return voice
      }
      if let voice = voices.first(where: {
        $0.language.hasPrefix("en") && $0.name.localizedCaseInsensitiveContains(name)
      }) {
        return voice
      }
    }
    return voices.first(where: { $0.language == "en-US" })
      ?? AVSpeechSynthesisVoice(language: "en-US")
  }

  /// Synthesize speech directly through the user's OpenAI BYOK key.
  private nonisolated static func synthesizeOpenAISpeech(
    text: String,
    voiceID: String,
    instructions: String
  ) async throws -> Data {
    guard let apiKey = openAIAPIKey() else {
      throw FloatingBarVoicePlaybackError.missingAPIKey("OpenAI")
    }

    let url = URL(string: "https://api.openai.com/v1/audio/speech")!
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.timeoutInterval = 60
    request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")

    request.httpBody = try JSONEncoder().encode(
      OpenAISpeechRequest(
        model: openAITTSModelID,
        input: text,
        voice: voiceID,
        instructions: instructions.isEmpty ? nil : instructions,
        responseFormat: "mp3"
      )
    )

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw FloatingBarVoicePlaybackError.invalidResponse
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
      let body = String(data: data, encoding: .utf8) ?? ""
      throw FloatingBarVoicePlaybackError.requestFailed(statusCode: httpResponse.statusCode, body: body)
    }
    return data
  }

  private nonisolated static func openAIAPIKey() -> String? {
    if let key = APIKeyService.byokKey(.openai) {
      return key
    }
    if let key = ProcessInfo.processInfo.environment["OPENAI_API_KEY"]?
      .trimmingCharacters(in: .whitespacesAndNewlines),
      !key.isEmpty
    {
      return key
    }
    return nil
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

  private nonisolated static func nextChunkBoundary(
    in text: String, isFinal: Bool, isFirstChunk: Bool
  ) -> String.Index? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }

    if isFinal {
      return text.endIndex
    }

    let minLength = isFirstChunk ? firstChunkMinimumLength : followupChunkMinimumLength
    let preferredLength =
      isFirstChunk ? firstChunkPreferredLength : followupChunkPreferredLength
    let emergencyLength =
      isFirstChunk ? firstChunkEmergencyLength : followupChunkEmergencyLength

    guard text.count >= minLength else { return nil }

    let preferredLimit = text.index(
      text.startIndex, offsetBy: min(text.count, preferredLength))
    let preferredSlice = text[..<preferredLimit]

    if let punctuationIndex = preferredSlice.lastIndex(where: { ".!?\n".contains($0) }) {
      return text.index(after: punctuationIndex)
    }

    guard text.count >= preferredLength else { return nil }

    let emergencyLimit = text.index(
      text.startIndex, offsetBy: min(text.count, emergencyLength))
    let emergencySlice = text[..<emergencyLimit]

    if let punctuationIndex = emergencySlice.lastIndex(where: { ".!?\n".contains($0) }) {
      return text.index(after: punctuationIndex)
    }

    guard text.count >= emergencyLength else { return nil }

    if let clauseIndex = emergencySlice.lastIndex(where: { ",;:\n".contains($0) }) {
      return text.index(after: clauseIndex)
    }

    if let whitespaceIndex = emergencySlice.lastIndex(where: \.isWhitespace) {
      return whitespaceIndex
    }

    return emergencyLimit
  }

  private nonisolated static func isCancellation(_ error: Error) -> Bool {
    if error is CancellationError {
      return true
    }

    let nsError = error as NSError
    if nsError.domain == NSURLErrorDomain, nsError.code == NSURLErrorCancelled {
      return true
    }

    if let urlError = error as? URLError, urlError.code == .cancelled {
      return true
    }

    return false
  }
}

private enum PlaybackMode: Sendable {
  case openAI(voiceID: String, instructions: String)
  case systemVoice(ShortcutSettings.VoiceOption)
}

private struct OpenAISpeechRequest: Encodable {
  let model: String
  let input: String
  let voice: String
  let instructions: String?
  let responseFormat: String

  enum CodingKeys: String, CodingKey {
    case model
    case input
    case voice
    case instructions
    case responseFormat = "response_format"
  }
}

private enum FloatingBarVoicePlaybackError: LocalizedError {
  case invalidResponse
  case missingAPIKey(String)
  case requestFailed(statusCode: Int, body: String)

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Invalid TTS response"
    case .missingAPIKey(let provider):
      return "\(provider) API key is not configured"
    case .requestFailed(let statusCode, let body):
      return "TTS request failed (\(statusCode)): \(body)"
  }
}
}
