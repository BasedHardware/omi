import AVFoundation
import Foundation

@MainActor
final class FloatingBarVoicePlaybackService: NSObject, AVAudioPlayerDelegate {
  static let shared = FloatingBarVoicePlaybackService()

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
  // Carries each chunk's source text alongside its synthesized audio so playback can fall
  // back to the system voice (speaking the text) if AVAudioPlayer can't play the audio.
  private var audioQueue: [(audio: Data, text: String)] = []
  private var isSynthesizing = false
  private var hasStartedRealPlayback = false
  private var hasEmittedFirstChunk = false
  private var audioPlayer: AVAudioPlayer?

  /// QueryTracer for the in-flight query, handed in by the floating-bar window.
  /// Used to bracket the `tts_start` span (first real chunk → first audio out).
  var tracer: QueryTracer?
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
    case .systemVoice:
      enqueueSystemSpeech(phrase)
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
      tracer?.begin("tts_start")
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
    case .systemVoice:
      enqueueSystemSpeech(text)
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
          self.audioQueue.append((audio: audioData, text: text))
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
          self.enqueueSystemSpeech(text)
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
      enqueueSystemSpeech(phrase)
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

    enqueueSystemSpeech(phrase)
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
            self?.startPlayback(audio, fallbackText: trimmed)
          }
        } catch {
          await MainActor.run {
            self?.enqueueSystemSpeech(trimmed)
          }
        }
      }
    case .systemVoice:
      enqueueSystemSpeech(trimmed)
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
    let next = audioQueue.removeFirst()
    startPlayback(next.audio, fallbackText: next.text)
  }

  private func startPlayback(_ data: Data, fallbackText: String = "") {
    do {
      if UserDefaults.standard.bool(forKey: "forceTTSPlaybackFail") {
        throw NSError(domain: "TTSPlayback", code: -1, userInfo: [NSLocalizedDescriptionKey: "forced playback failure"])
      }
      let player = try AVAudioPlayer(data: data)
      player.delegate = self
      player.enableRate = true
      player.rate = playbackRate
      player.prepareToPlay()
      player.play()
      audioPlayer = player
      tracer?.end("tts_start")
    } catch {
      // Don't drop the reply silently — speak this chunk with the system voice instead.
      log(
        "FloatingBarVoicePlaybackService: audio playback failed, falling back to system voice: \(error.localizedDescription)"
      )
      enqueueSystemSpeech(fallbackText)
    }
  }

  private func enqueueSystemSpeech(_ text: String) {
    let utterance = AVSpeechUtterance(string: text)
    utterance.rate = 0.47
    utterance.pitchMultiplier = 1.02
    utterance.volume = 1.0
    utterance.voice = preferredSystemVoice()
    speechSynthesizer.speak(utterance)
    tracer?.end("tts_start")
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
      // Drop the tracer only on full teardown. interruptCurrentResponse uses
      // clearMode:false and runs just before the next query assigns a fresh
      // tracer, so clearing there would discard the live one.
      tracer = nil
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

  private func preferredSystemVoice() -> AVSpeechSynthesisVoice? {
    let voices = AVSpeechSynthesisVoice.speechVoices()
    let preferredNames = ["Ava", "Allison", "Samantha", "Karen", "Moira"]
    for name in preferredNames {
      if let voice = voices.first(where: {
        $0.name.localizedCaseInsensitiveContains(name)
      }) {
        return voice
      }
    }
    return AVSpeechSynthesisVoice(language: "en-US")
  }

  /// Synthesize speech through the desktop backend's OpenAI TTS proxy.
  /// APIClient attaches a user BYOK key when one is configured; otherwise the
  /// backend uses its server-side key.
  private nonisolated static func synthesizeOpenAISpeech(
    text: String,
    voiceID: String,
    instructions: String
  ) async throws -> Data {
    try await APIClient.shared.synthesizeSpeech(
      request: APIClient.TtsSynthesizeRequest(
        text: text,
        voiceId: voiceID,
        instructions: instructions.isEmpty ? nil : instructions
      )
    )
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
