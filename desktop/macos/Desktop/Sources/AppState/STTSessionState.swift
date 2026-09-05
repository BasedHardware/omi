import Foundation

/// Pure policy + transition state for cloud ↔ on-device STT fallback.
/// All resolution rules live here so AppState only orchestrates I/O.
struct STTSessionState: Equatable {
  enum ResolvedMode: Equatable {
    case local
    case cloud

    var usesLocalSTT: Bool { self == .local }
  }

  enum FallbackDirection: Equatable {
    case localToCloud
    case cloudToLocal
  }

  /// Sticky for the app run after Parakeet model-load failure (never reset on new recordings).
  private(set) var appRunForceCloud = false
  /// Session sticky: prefer on-device after cloud reconnect exhaustion.
  private(set) var sessionForceLocal = false
  /// One-shot guard: cloud→local fallback already attempted this session.
  private(set) var cloudToLocalFallbackTried = false
  /// Mutex during stop→async-restart fallback choreography.
  private(set) var fallbackInProgress = false
  /// Active transport mode while capture is running (`nil` when stopped).
  var activeMode: ResolvedMode?

  var useLocalSTT: Bool { activeMode?.usesLocalSTT ?? false }

  /// Reset session-scoped flags when starting a new recording (skipped mid-fallback).
  mutating func prepareForStart() {
    guard !fallbackInProgress else { return }
    cloudToLocalFallbackTried = false
    sessionForceLocal = false
  }

  /// Resolve which STT path to use for a new recording.
  ///
  /// `wakeWordNeedsRecognizableName` is the opt-in the wake word needs to work. Ambient
  /// transcription is on-device by default, and the manager that path runs on takes a
  /// language hint and nothing else — `AsrManager.transcribe(_:decoderState:language:)` has
  /// no keyword or vocabulary parameter, so it cannot be told that "Omi" is a word.
  /// FluidAudio does ship term biasing, but only on `SlidingWindowAsrManager`
  /// (`configureVocabularyBoosting(vocabulary:ctcModels:config:)`), which is a different
  /// streaming architecture and pulls a second set of CTC models. That is the upgrade path
  /// out of this flag; it is not a parameter we can pass today. Measured
  /// on one machine, same script and voices, only the lane changed: the phrase was usable
  /// in 12 of 20 utterances on-device against 19 of 20 on the cloud lane, which reaches
  /// `/v4/listen` — and that path prepends "Omi" to the STT keyword vocabulary server-side
  /// (`backend/utils/listen_session_bootstrap.py`), so the recognizer is told the name.
  /// Seven of the eight on-device misses came back as "Only", which cannot be accepted as
  /// a rendering — it opens ordinary sentences.
  ///
  /// Off by default. It trades on-device transcription for cloud transcription while the
  /// wake word is enabled, which is a privacy and cost decision, not a technical one.
  func resolveMode(
    audioSource: AudioSource,
    isAppleSilicon: Bool,
    debugForceCloud: Bool,
    wakeWordNeedsRecognizableName: Bool = false
  ) -> ResolvedMode {
    let forceCloud =
      !sessionForceLocal && (debugForceCloud || appRunForceCloud || wakeWordNeedsRecognizableName)
    if audioSource == .bleDevice || !isAppleSilicon || forceCloud {
      return .cloud
    }
    return .local
  }

  mutating func beginRecording(
    audioSource: AudioSource,
    isAppleSilicon: Bool,
    debugForceCloud: Bool,
    wakeWordNeedsRecognizableName: Bool = false
  ) {
    activeMode = resolveMode(
      audioSource: audioSource,
      isAppleSilicon: isAppleSilicon,
      debugForceCloud: debugForceCloud,
      wakeWordNeedsRecognizableName: wakeWordNeedsRecognizableName
    )
  }

  mutating func endRecording() {
    activeMode = nil
  }

  func canBeginLocalToCloudFallback(isTranscribing: Bool) -> Bool {
    isTranscribing && useLocalSTT && !fallbackInProgress
  }

  mutating func beginLocalToCloudFallback() {
    fallbackInProgress = true
    appRunForceCloud = true
    // Clear a stale session-local preference so resolveMode honors the cloud
    // fallback instead of resolving back to .local.
    sessionForceLocal = false
  }

  func canBeginCloudToLocalFallback(
    isTranscribing: Bool,
    audioSource: AudioSource,
    isAppleSilicon: Bool
  ) -> Bool {
    isTranscribing
      && audioSource != .bleDevice
      && !useLocalSTT
      && isAppleSilicon
      && !appRunForceCloud
      && !cloudToLocalFallbackTried
      && !fallbackInProgress
  }

  mutating func beginCloudToLocalFallback() {
    cloudToLocalFallbackTried = true
    fallbackInProgress = true
    sessionForceLocal = true
  }

  mutating func completeFallback() {
    fallbackInProgress = false
  }

  static func debugForceCloudSTT(
    environmentForceCloud: Bool,
    userDefaultsForceCloud: Bool
  ) -> Bool {
    environmentForceCloud || userDefaultsForceCloud
  }
}
