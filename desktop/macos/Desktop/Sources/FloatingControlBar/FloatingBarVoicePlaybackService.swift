import AVFoundation
import CryptoKit
import Foundation
import OmiSupport

@MainActor
final class FloatingBarVoicePlaybackService: NSObject, AVAudioPlayerDelegate, AVSpeechSynthesizerDelegate {
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
  nonisolated static let backgroundAgentKickoffPhrases: [String] = [
    "I'll get an agent on that.",
    "Starting an agent for that now.",
    "Got it. I'm handing this to an agent.",
    "I'll have an agent work on that.",
    "I'm getting an agent started.",
    "I'll have an agent take it from here.",
    "Got it. I'm starting an agent now.",
    "I'll put an agent on that.",
    "An agent is getting started on that.",
    "I'm kicking off an agent now.",
  ]

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
  private var isFillerSynthesizing = false
  private var isOneShotSynthesizing = false
  private var isSynthesizing = false
  private var hasStartedRealPlayback = false
  private var hasEmittedFirstChunk = false
  private var audioPlayer: AVAudioPlayer?
  private var activePlayerFallbackText = ""
  private var playbackGeneration: UInt64 = 0
  private var localSpeechActive = false
  private var activePTTLease: VoiceOutputLease?

  /// QueryTracer for the in-flight query, handed in by the floating-bar window.
  /// Used to bracket the `tts_start` span (first real chunk → first audio out).
  var tracer: QueryTracer?
  private let speechSynthesizer = AVSpeechSynthesizer()

  private override init() {
    super.init()
    speechSynthesizer.delegate = self
  }

  var isSpeaking: Bool {
    if audioPlayer?.isPlaying == true { return true }
    if localSpeechActive { return true }
    if speechSynthesizer.isSpeaking { return true }
    if isFillerSynthesizing { return true }
    if isOneShotSynthesizing { return true }
    if isSynthesizing { return true }
    return !audioQueue.isEmpty || !synthesisQueue.isEmpty
  }

  func playFillerIfEnabled() {
    guard ShortcutSettings.shared.hasAnyFloatingBarVoiceAnswersEnabled else { return }
    if VoiceTurnCoordinator.shared.activeTurnID != nil,
      acquirePTTLeaseIfNeeded(.filler) == nil
    {
      return
    }
    setFloatingPillResponseGlow(true)

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
      isFillerSynthesizing = true
      let generation = playbackGeneration
      fillerTask = Task { [weak self] in
        do {
          let audioData = try await Self.synthesizeOpenAISpeech(
            text: phrase, voiceID: voiceID, instructions: instructions)
          try Task.checkCancellation()
          await MainActor.run {
            guard let self else { return }
            guard self.playbackGeneration == generation else { return }
            self.isFillerSynthesizing = false
            self.fillerTask = nil
            guard !self.hasStartedRealPlayback else {
              self.clearFloatingPillResponseGlowIfIdle()
              return
            }
            self.startPlayback(audioData, fallbackText: phrase)
            self.clearFloatingPillResponseGlowIfIdle()
          }
        } catch {
          await MainActor.run {
            guard let self else { return }
            guard self.playbackGeneration == generation else { return }
            self.isFillerSynthesizing = false
            self.fillerTask = nil
            self.clearFloatingPillResponseGlowIfIdle()
          }
        }
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
      resetPlaybackPipeline(clearMode: false, notifyPTTDrain: true)
      currentResponseID = message.id
      interruptedResponseID = shouldInterruptNextResponse ? message.id : nil
      shouldInterruptNextResponse = false
    }

    let text = Self.cleanedPlaybackText(from: message)
    guard !text.isEmpty, Self.shouldSpeak(text) else { return }
    if interruptedResponseID == message.id {
      streamedText = text
      bufferedText = ""
      clearFloatingPillResponseGlowIfIdle()
      return
    }
    if VoiceTurnCoordinator.shared.activeTurnID != nil,
      acquirePTTLeaseIfNeeded(.selectedVoiceFallback) == nil
    {
      return
    }
    setFloatingPillResponseGlow(true)

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
    let generation = playbackGeneration
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
          guard self.playbackGeneration == generation else { return }
          self.isSynthesizing = false
          self.playbackTask = nil
          self.audioQueue.append((audio: audioData, text: text))
          self.startPlaybackIfNeeded()
          self.startSynthesisIfNeeded(mode: mode)
          self.clearFloatingPillResponseGlowIfIdle()
        }
      } catch is CancellationError {
        await MainActor.run {
          guard let self else { return }
          guard self.playbackGeneration == generation else { return }
          self.isSynthesizing = false
          self.playbackTask = nil
          self.startSynthesisIfNeeded(mode: mode)
          self.clearFloatingPillResponseGlowIfIdle()
        }
      } catch {
        if Self.isCancellation(error) {
          await MainActor.run {
            guard let self else { return }
            guard self.playbackGeneration == generation else { return }
            self.isSynthesizing = false
            self.playbackTask = nil
            self.startSynthesisIfNeeded(mode: mode)
            self.clearFloatingPillResponseGlowIfIdle()
          }
          return
        }

        await MainActor.run {
          guard let self else { return }
          guard self.playbackGeneration == generation else { return }
          self.isSynthesizing = false
          self.playbackTask = nil
          log(
            "FloatingBarVoicePlaybackService: cloud TTS chunk synthesis failed, falling back to system voice: \(error.localizedDescription)"
          )
          self.recordSelectedVoiceFallback(
            to: "system_voice_fallback", reason: Self.ttsFallbackReason(for: error), outcome: .degraded)
          self.enqueueSystemSpeech(text)
          self.startSynthesisIfNeeded(mode: mode)
          self.clearFloatingPillResponseGlowIfIdle()
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
    guard VoiceTurnCoordinator.shared.activeTurnID == nil else {
      log("FloatingBarVoicePlaybackService: voice sample denied while PTT owns audible output")
      return
    }
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
      let generation = playbackGeneration
      playbackTask = Task { [weak self] in
        do {
          let audioData = try await Self.synthesizeOpenAISpeech(
            text: phrase, voiceID: openAIVoice, instructions: voice.openAIInstructions ?? "")
          try Task.checkCancellation()
          await MainActor.run {
            guard let self else { return }
            guard self.playbackGeneration == generation else { return }
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
  func speakOneShot(_ text: String, lease: VoiceOutputLease? = nil) {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    if let lease {
      guard VoiceTurnCoordinator.shared.outputSnapshot.activeLease == lease else {
        log("FloatingBarVoicePlaybackService: dropping one-shot with stale PTT lease")
        return
      }
      activePTTLease = lease
    } else if VoiceTurnCoordinator.shared.activeTurnID != nil,
      acquirePTTLeaseIfNeeded(.deterministicAgentAck) == nil
    {
      return
    }
    setFloatingPillResponseGlow(true)
    let mode = currentMode ?? resolvePlaybackMode()
    currentMode = mode
    switch mode {
    case .openAI(let voiceID, let instructions):
      let generation = playbackGeneration
      isOneShotSynthesizing = true
      Task { [weak self] in
        do {
          let audio = try await Self.synthesizeOpenAISpeech(
            text: trimmed, voiceID: voiceID, instructions: instructions)
          await MainActor.run {
            guard let self, self.playbackGeneration == generation else { return }
            self.isOneShotSynthesizing = false
            self.startPlayback(audio, fallbackText: trimmed)
          }
        } catch {
          await MainActor.run {
            guard let self, self.playbackGeneration == generation else { return }
            self.isOneShotSynthesizing = false
            self.recordSelectedVoiceFallback(
              to: "system_voice_fallback", reason: Self.ttsFallbackReason(for: error), outcome: .degraded)
            self.enqueueSystemSpeech(trimmed)
          }
        }
      }
    case .systemVoice:
      enqueueSystemSpeech(trimmed)
    }
  }

  func speakBackgroundAgentKickoff() {
    if VoiceTurnCoordinator.shared.activeTurnID != nil,
      acquirePTTLeaseIfNeeded(.deterministicAgentAck) == nil
    {
      return
    }
    let phrase = Self.randomBackgroundAgentKickoffPhrase()
    setFloatingPillResponseGlow(true)
    let mode = currentMode ?? resolvePlaybackMode()
    currentMode = mode

    switch mode {
    case .openAI(let voiceID, let instructions):
      let generation = playbackGeneration
      isOneShotSynthesizing = true
      Task { [weak self] in
        do {
          let audio = try await Self.cachedOrSynthesizedBackgroundAgentKickoffAudio(
            text: phrase, voiceID: voiceID, instructions: instructions)
          await MainActor.run {
            guard let self, self.playbackGeneration == generation else { return }
            self.isOneShotSynthesizing = false
            self.startPlayback(audio, fallbackText: phrase)
          }
        } catch {
          let cachedFallback = Self.cachedBackgroundAgentKickoffAudio(
            voiceID: voiceID, instructions: instructions)
          await MainActor.run {
            guard let self, self.playbackGeneration == generation else { return }
            self.isOneShotSynthesizing = false
            if let cachedFallback {
              self.recordSelectedVoiceFallback(
                to: "cached_openai_tts", reason: Self.ttsFallbackReason(for: error), outcome: .recovered)
              self.startPlayback(cachedFallback, fallbackText: phrase)
            } else {
              self.recordSelectedVoiceFallback(
                to: "system_voice_fallback", reason: Self.ttsFallbackReason(for: error), outcome: .degraded)
              self.enqueueSystemSpeech(phrase)
            }
          }
        }
      }
    case .systemVoice:
      enqueueSystemSpeech(phrase)
    }
  }

  func prewarmBackgroundAgentKickoffPhrases() {
    let mode = currentMode ?? resolvePlaybackMode()
    currentMode = mode
    guard case .openAI(let voiceID, let instructions) = mode else { return }

    Task {
      for phrase in Self.backgroundAgentKickoffPhrases {
        do {
          _ = try await Self.cachedOrSynthesizedBackgroundAgentKickoffAudio(
            text: phrase, voiceID: voiceID, instructions: instructions)
        } catch {
          log(
            "FloatingBarVoicePlaybackService: background agent kickoff cache prewarm failed: \(error.localizedDescription)"
          )
          return
        }
      }
    }
  }

  @discardableResult
  func interruptCurrentResponse(
    leaseID expectedLeaseID: VoiceLeaseID? = nil,
    armNextResponse: Bool = false
  ) -> Bool {
    if let expectedLeaseID, activePTTLease?.id != expectedLeaseID {
      log("FloatingBarVoicePlaybackService: ignored stale playback stop lease=\(expectedLeaseID)")
      return false
    }
    if let currentResponseID {
      interruptedResponseID = currentResponseID
      shouldInterruptNextResponse = false
    } else {
      shouldInterruptNextResponse = armNextResponse
    }
    resetPlaybackPipeline(clearMode: false)
    clearFloatingPillResponseGlowIfIdle()
    return true
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
      let started = !UserDefaults.standard.bool(forKey: .forceTTSPlaybackStartFalse)
        && player.play()
      guard VoicePlaybackStartPolicy.accepts(started: started) else {
        throw NSError(
          domain: "TTSPlayback",
          code: -2,
          userInfo: [NSLocalizedDescriptionKey: "audio player refused to start"])
      }
      audioPlayer = player
      activePlayerFallbackText = fallbackText
      tracer?.end("tts_start")
    } catch {
      // Don't drop the reply silently — speak this chunk with the system voice instead.
      log(
        "FloatingBarVoicePlaybackService: audio playback failed, falling back to system voice: \(error.localizedDescription)"
      )
      recordSelectedVoiceFallback(
        to: fallbackText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          ? "none" : "system_voice_fallback",
        reason: "enqueue_failed",
        outcome: fallbackText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          ? .exhausted : .degraded)
      enqueueSystemSpeech(fallbackText)
    }
  }

  private func recordSelectedVoiceFallback(
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  ) {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: activePTTLease == nil ? "other" : "ptt_cascade",
      from: "openai_tts",
      to: to,
      reason: reason,
      outcome: outcome,
      extra: ["user_visible": outcome != .recovered])
  }

  private func enqueueSystemSpeech(_ text: String) {
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      if let lease = activePTTLease {
        activePTTLease = nil
        VoiceTurnCoordinator.shared.send(
          .playbackFailedScoped(
            turnID: lease.turnID,
            identity: lease.identity,
            leaseID: lease.id,
            message: "no fallback speech available"))
      }
      clearFloatingPillResponseGlowIfIdle()
      return
    }
    localSpeechActive = true
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
      guard self.audioPlayer === player else { return }
      let fallbackText = self.activePlayerFallbackText
      self.audioPlayer = nil
      self.activePlayerFallbackText = ""
      if !flag, !fallbackText.isEmpty {
        log("FloatingBarVoicePlaybackService: player ended unsuccessfully; using system voice")
        self.recordSelectedVoiceFallback(
          to: "system_voice_fallback", reason: "enqueue_failed", outcome: .degraded)
        self.enqueueSystemSpeech(fallbackText)
        return
      }
      self.startPlaybackIfNeeded()
      self.clearFloatingPillResponseGlowIfIdle()
    }
  }

  nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.localSpeechActive = false
      self.startPlaybackIfNeeded()
      self.clearFloatingPillResponseGlowIfIdle()
    }
  }

  nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
    Task { @MainActor [weak self] in
      guard let self else { return }
      self.localSpeechActive = false
      self.clearFloatingPillResponseGlowIfIdle()
    }
  }

  private func resetPlaybackPipeline(clearMode: Bool, notifyPTTDrain: Bool = false) {
    let leaseToRelease = activePTTLease
    playbackGeneration &+= 1
    playbackTask?.cancel()
    playbackTask = nil
    fillerTask?.cancel()
    fillerTask = nil
    isFillerSynthesizing = false
    isOneShotSynthesizing = false
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
    activePlayerFallbackText = ""
    speechSynthesizer.stopSpeaking(at: .immediate)
    localSpeechActive = false
    activePTTLease = nil
    if let lease = leaseToRelease, notifyPTTDrain {
      _ = VoiceTurnCoordinator.shared.releaseOutput(lease)
    }
    setFloatingPillResponseGlow(false)
  }

  private func setFloatingPillResponseGlow(_ active: Bool) {
    if let lease = activePTTLease {
      VoiceTurnCoordinator.shared.send(
        .responseActiveChanged(turnID: lease.turnID, active: active))
      return
    }
    VoiceTurnCoordinator.shared.setUnscopedResponseActive(active)
  }

  private func clearFloatingPillResponseGlowIfIdle() {
    if !isSpeaking {
      finishActivePTTLeaseIfIdle()
      setFloatingPillResponseGlow(false)
    }
  }

  private func acquirePTTLeaseIfNeeded(_ lane: VoiceOutputLane) -> VoiceOutputLease? {
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
      _ = preemptFillerIfNeeded(for: lane, turnID: turnID)
    }
    if let activePTTLease {
      return activePTTLease.lane == lane ? activePTTLease : nil
    }
    guard let turnID = VoiceTurnCoordinator.shared.activeTurnID else { return nil }
    switch VoiceTurnCoordinator.shared.acquireOutput(lane, turnID: turnID) {
    case .acquired(let lease):
      activePTTLease = lease
      guard let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity else {
        log("FloatingBarVoicePlaybackService: dropping PTT output without provider effect identity")
        activePTTLease = nil
        return nil
      }
      VoiceTurnCoordinator.shared.send(
        .providerResponseStartedScoped(
          turnID: turnID,
          identity: providerIdentity,
          sessionID: nil,
          responseID: nil))
      return lease
    case .denied(let active):
      log(
        "FloatingBarVoicePlaybackService: dropping \(lane.rawValue) PTT output; "
          + "active_lane=\(active.lane.rawValue)")
      return nil
    case .staleTurn:
      log("FloatingBarVoicePlaybackService: dropping stale \(lane.rawValue) PTT output")
      return nil
    }
  }

  /// Real output always wins over a provisional filler phrase. Stop the audio
  /// engine before releasing its lease so the incoming lane cannot overlap it.
  @discardableResult
  func preemptFillerIfNeeded(for incomingLane: VoiceOutputLane, turnID: VoiceTurnID) -> Bool {
    guard let lease = activePTTLease,
      VoiceOutputHandoffPolicy.fillerCanYield(
        active: lease,
        to: incomingLane,
        turnID: turnID)
    else { return false }

    playbackGeneration &+= 1
    fillerTask?.cancel()
    fillerTask = nil
    isFillerSynthesizing = false
    audioPlayer?.stop()
    audioPlayer = nil
    speechSynthesizer.stopSpeaking(at: .immediate)
    localSpeechActive = false
    activePTTLease = nil
    return VoiceTurnCoordinator.shared.releaseOutput(lease)
  }

  private func finishActivePTTLeaseIfIdle() {
    guard !isSpeaking, let lease = activePTTLease else { return }
    activePTTLease = nil
    _ = VoiceTurnCoordinator.shared.releaseOutput(lease)
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
    let byokKey = APIKeyService.isByokActive ? APIKeyService.byokKey(.openai) : nil
    let fingerprint = byokKey.map(APIKeyService.byokFingerprint)
    if let fingerprint {
      let canUseKey = await MainActor.run {
        CredentialHealthManager.shared.canUseBYOK(provider: .openai, fingerprint: fingerprint)
      }
      guard canUseKey else {
        throw CredentialHealthError.providerAuth(
          provider: .openai,
          mode: .byok,
          message: "Your OpenAI key was rejected. Update it in Settings."
        )
      }
    }

    do {
      return try await APIClient.shared.synthesizeSpeech(
        request: APIClient.TtsSynthesizeRequest(
          text: text,
          voiceId: voiceID,
          instructions: instructions.isEmpty ? nil : instructions
        )
      )
    } catch let error as CredentialHealthError {
      await MainActor.run {
        if case .providerAuth(let provider, let mode, _) = error {
          CredentialHealthManager.shared.recordProviderFailure(
            error.failureClass,
            provider: provider,
            authMode: mode,
            fingerprint: fingerprint,
            context: "openai_tts"
          )
        } else {
          CredentialHealthManager.shared.record(error, context: "openai_tts")
        }
      }
      throw error
    }
  }

  private nonisolated static func ttsFallbackReason(for error: Error) -> String {
    if let apiError = error as? APIError,
      case .httpError(let statusCode, _) = apiError,
      statusCode == 429
    {
      return "quota"
    }
    guard let credentialError = error as? CredentialHealthError else { return "provider_5xx" }
    switch credentialError.failureClass {
    case .providerAuthFailed:
      return "auth"
    case .providerQuotaExceeded:
      return "provider_429"
    default:
      return "provider_5xx"
    }
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
        case .agentSpawn(_, _, _, _, let title, let objective, _):
          return "\(title). \(objective)"
        case .agentCompletion(_, _, _, _, let title, _, let output, _):
          return "\(title). \(output)"
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

  private nonisolated static func randomBackgroundAgentKickoffPhrase() -> String {
    backgroundAgentKickoffPhrases.randomElement() ?? "Starting an agent for that now."
  }

  private nonisolated static func cachedOrSynthesizedBackgroundAgentKickoffAudio(
    text: String,
    voiceID: String,
    instructions: String
  ) async throws -> Data {
    let cacheURL = backgroundAgentKickoffCacheURL(
      text: text, voiceID: voiceID, instructions: instructions)
    if let cached = try? Data(contentsOf: cacheURL), !cached.isEmpty {
      return cached
    }

    let audio = try await synthesizeOpenAISpeech(text: text, voiceID: voiceID, instructions: instructions)
    try FileManager.default.createDirectory(
      at: cacheURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try audio.write(to: cacheURL, options: [.atomic])
    return audio
  }

  private nonisolated static func cachedBackgroundAgentKickoffAudio(
    voiceID: String,
    instructions: String
  ) -> Data? {
    let cached = backgroundAgentKickoffPhrases.shuffled().lazy.compactMap { phrase -> Data? in
      let url = backgroundAgentKickoffCacheURL(
        text: phrase, voiceID: voiceID, instructions: instructions)
      guard let data = try? Data(contentsOf: url), !data.isEmpty else { return nil }
      return data
    }
    return cached.first
  }

  private nonisolated static func backgroundAgentKickoffCacheURL(
    text: String,
    voiceID: String,
    instructions: String
  ) -> URL {
    let fingerprint = SHA256.hash(data: Data("\(voiceID)\n\(instructions)\n\(text)".utf8))
      .map { String(format: "%02x", $0) }
      .joined()
    return DesktopLocalProfile.applicationSupportURL()
      .appendingPathComponent("VoicePhraseCache", isDirectory: true)
      .appendingPathComponent("background-agent-kickoff-v1", isDirectory: true)
      .appendingPathComponent("\(fingerprint).mp3")
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

enum VoicePlaybackStartPolicy {
  static func accepts(started: Bool) -> Bool { started }
}

private enum PlaybackMode: Sendable {
  case openAI(voiceID: String, instructions: String)
  case systemVoice(ShortcutSettings.VoiceOption)
}
