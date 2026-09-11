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
  /// Pendant BLE used to force cloud for named speaker-ID. Identified basic
  /// (non-BYOK) on Apple Silicon now matches mic: local, unnamed. Paid,
  /// unknown, and cache-miss stay on the previous BLE→cloud path.
  func resolveMode(
    audioSource: AudioSource,
    isAppleSilicon: Bool,
    debugForceCloud: Bool,
    preferLocalOnBasic: Bool = false
  ) -> ResolvedMode {
    let forceCloud = !sessionForceLocal && (debugForceCloud || appRunForceCloud)
    if !isAppleSilicon || forceCloud {
      return .cloud
    }
    if audioSource == .bleDevice && !preferLocalOnBasic {
      return .cloud
    }
    return .local
  }

  mutating func beginRecording(
    audioSource: AudioSource,
    isAppleSilicon: Bool,
    debugForceCloud: Bool,
    preferLocalOnBasic: Bool = false
  ) {
    activeMode = resolveMode(
      audioSource: audioSource,
      isAppleSilicon: isAppleSilicon,
      debugForceCloud: debugForceCloud,
      preferLocalOnBasic: preferLocalOnBasic
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
