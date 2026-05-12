import AVFoundation
import Foundation

@MainActor
final class FloatingBarVoicePlaybackService: NSObject, AVAudioPlayerDelegate {
  static let shared = FloatingBarVoicePlaybackService()

  static let devVoiceIDDefaultsKey = "dev_elevenlabs_voice_id"

  nonisolated private static let defaultVoiceID = "shimmer"  // OpenAI Shimmer (sultry, $15/1M)
  nonisolated private static let elevenLabsModelID = "eleven_turbo_v2_5"
  // First chunk stays small so playback starts fast.
  nonisolated private static let firstChunkMinimumLength = 40
  nonisolated private static let firstChunkPreferredLength = 120
  nonisolated private static let firstChunkEmergencyLength = 200
  // Follow-up chunks are much larger so the response is stitched from fewer
  // ElevenLabs MP3s. Each chunk boundary carries leading/trailing silence, so
  // fewer chunks means far less perceived pausing between sentences and
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
    // Cloud-provider filler only — local AVSpeechSynthesizer starts speaking
    // instantly, so it has no use for a "let me check" filler.
    guard let mode = currentMode, case .backend(let voiceID, let provider) = mode else { return }

    hasStartedRealPlayback = false
    let phrase = Self.fillerPhrases.randomElement()!
    fillerTask = Task { [weak self] in
      do {
        let audioData = try await Self.synthesizeSpeech(
          text: phrase, voiceID: voiceID, provider: provider)
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
    let voiceID = ShortcutSettings.shared.selectedVoiceID
    let resolvedVoiceID = voiceID.isEmpty ? Self.defaultVoiceID : voiceID
    let option = ShortcutSettings.voiceOption(for: resolvedVoiceID)
    switch option.provider {
    case .local:
      return .local(voiceKey: option.id)
    case .openai, .elevenLabs:
      // Backend-routed providers require the desktop API URL. Fall back to a
      // local Apple voice if the backend isn't configured (e.g. dev with no
      // tunnel) so the user still hears speech.
      guard getenv("OMI_DESKTOP_API_URL") != nil else {
        return .local(voiceKey: option.name)
      }
      return .backend(voiceID: resolvedVoiceID, provider: option.provider)
    }
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
    case .local(let voiceKey):
      enqueueSystemSpeech(text, voiceKey: voiceKey)
    case .backend:
      synthesisQueue.append(text)
      startSynthesisIfNeeded(mode: mode)
    }
  }

  private func startSynthesisIfNeeded(mode: PlaybackMode) {
    guard !isSynthesizing else { return }
    guard case .backend(let voiceID, let provider) = mode else { return }
    guard !synthesisQueue.isEmpty else { return }

    let text = synthesisQueue.removeFirst()
    isSynthesizing = true
    playbackTask?.cancel()
    playbackTask = Task { [weak self] in
      do {
        let audioData = try await Self.synthesizeSpeech(
          text: text, voiceID: voiceID, provider: provider)
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
            "FloatingBarVoicePlaybackService: \(provider.rawValue) chunk synthesis failed, falling back to system voice: \(error.localizedDescription)"
          )
          self.enqueueSystemSpeech(text, voiceKey: nil)
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

  /// Play a short preview of the given voice so the user can hear it when
  /// switching voices in settings. Routes to the correct provider.
  func playVoiceSample(voiceID: String) {
    resetPlaybackPipeline(clearMode: true)
    currentResponseID = nil
    interruptedResponseID = nil
    shouldInterruptNextResponse = false

    let phrase = Self.voiceSampleText
    let option = ShortcutSettings.voiceOption(for: voiceID)

    // Local voices are demoed via AVSpeechSynthesizer with the named voice;
    // no network round-trip and no API cost.
    if option.provider == .local {
      enqueueSystemSpeech(phrase, voiceKey: option.id)
      return
    }

    // Backend-routed providers need the desktop API URL. Without it fall back
    // to the on-device system voice so the user still hears _something_.
    guard getenv("OMI_DESKTOP_API_URL") != nil else {
      enqueueSystemSpeech(phrase, voiceKey: nil)
      return
    }

    playbackTask = Task { [weak self] in
      do {
        let audioData = try await Self.synthesizeSpeech(
          text: phrase, voiceID: voiceID, provider: option.provider)
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
          "FloatingBarVoicePlaybackService: voice sample failed (\(option.provider.rawValue)): \(error.localizedDescription)"
        )
      }
    }
  }

  /// Synthesize and play a single short phrase via the current provider (or fall
  /// back to the system voice). Used by agent pills to speak a short
  /// acknowledgement like "On it" before the agent kicks off.
  func speakOneShot(_ text: String) {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    let mode = currentMode ?? resolvePlaybackMode()
    currentMode = mode
    switch mode {
    case .backend(let voiceID, let provider):
      Task { [weak self] in
        do {
          let audio = try await Self.synthesizeSpeech(
            text: trimmed, voiceID: voiceID, provider: provider)
          await MainActor.run {
            self?.startPlayback(audio)
          }
        } catch {
          // Network/API error — fall back to system voice on the main thread.
          await MainActor.run {
            self?.enqueueSystemSpeech(trimmed, voiceKey: nil)
          }
        }
      }
    case .local(let voiceKey):
      enqueueSystemSpeech(trimmed, voiceKey: voiceKey)
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

  private func enqueueSystemSpeech(_ text: String, voiceKey: String?) {
    let utterance = AVSpeechUtterance(string: text)
    utterance.rate = 0.47
    utterance.pitchMultiplier = 1.02
    utterance.volume = 1.0
    utterance.voice = preferredSystemVoice(matching: voiceKey)
    speechSynthesizer.speak(utterance)
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

  /// Pick an installed Apple voice. When `voiceKey` is provided we look for a
  /// voice whose name contains that key (e.g. "Ava", "Zoe"). When it's nil or
  /// no match is found we fall through to a curated preference list, then to
  /// any en-US voice.
  private func preferredSystemVoice(matching voiceKey: String?) -> AVSpeechSynthesisVoice? {
    let installed = AVSpeechSynthesisVoice.speechVoices()

    if let key = voiceKey, !key.isEmpty {
      // Prefer premium / enhanced variants of the requested voice when installed.
      let matches = installed.filter { $0.name.localizedCaseInsensitiveContains(key) }
      if let premium = matches.first(where: { $0.quality == .premium }) {
        return premium
      }
      if let enhanced = matches.first(where: { $0.quality == .enhanced }) {
        return enhanced
      }
      if let any = matches.first {
        return any
      }
    }

    let fallbackNames = ["Ava", "Allison", "Samantha", "Karen", "Moira"]
    for name in fallbackNames {
      if let voice = installed.first(where: {
        $0.name.localizedCaseInsensitiveContains(name)
      }) {
        return voice
      }
    }
    return AVSpeechSynthesisVoice(language: "en-US")
  }

  /// Synthesize speech via the backend TTS proxy. The provider (ElevenLabs or
  /// OpenAI) is selected server-side via the request's `provider` field; keys
  /// stay on the backend.
  private nonisolated static func synthesizeSpeech(
    text: String, voiceID: String, provider: ShortcutSettings.VoiceOption.Provider
  )
    async throws -> Data
  {
    // ElevenLabs needs `model_id` + voice_settings (stability/similarity/style);
    // OpenAI ignores those and uses model="gpt-4o-mini-tts" (set server-side).
    let isElevenLabs = (provider == .elevenLabs)
    let request = APIClient.TtsSynthesizeRequest(
      text: text,
      voiceId: voiceID,
      modelId: isElevenLabs ? elevenLabsModelID : "tts",
      outputFormat: "mp3_44100_128",
      voiceSettings: isElevenLabs
        ? .init(stability: 0.34, similarityBoost: 0.88, style: 0.12, useSpeakerBoost: true)
        : nil,
      provider: provider.backendValue
    )
    return try await APIClient.shared.synthesizeSpeech(request: request)
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

private enum PlaybackMode {
  /// A cloud TTS provider routed through the backend proxy. `voiceID` is the
  /// upstream-specific id ("shimmer" for OpenAI, base62 for ElevenLabs).
  case backend(voiceID: String, provider: ShortcutSettings.VoiceOption.Provider)
  /// Apple's on-device `AVSpeechSynthesizer`. `voiceKey` is matched against the
  /// installed voice catalog (e.g. "Ava", "Zoe", "Samantha").
  case local(voiceKey: String)
}

private enum FloatingBarVoicePlaybackError: LocalizedError {
  case invalidResponse
  case requestFailed(statusCode: Int, body: String)

  var errorDescription: String? {
    switch self {
    case .invalidResponse:
      return "Invalid TTS response"
    case .requestFailed(let statusCode, let body):
      return "TTS request failed (\(statusCode)): \(body)"
  }
}
}
