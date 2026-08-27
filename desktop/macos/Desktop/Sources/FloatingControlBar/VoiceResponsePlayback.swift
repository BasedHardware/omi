import Combine
import Foundation
import VoiceTurnDomain

/// Single entry point for "stop the AI voice answer" across app TTS and native
/// realtime PCM. Escape, composer Stop-speaking, and agent Stop all share this
/// so one surface never leaves another lane talking.
@MainActor
enum VoiceResponsePlayback {
  /// True while either the selected-voice / system TTS pipeline or the hub's
  /// native realtime player is producing audible response audio.
  static var isActive: Bool {
    FloatingBarVoicePlaybackService.shared.isSpeaking
      || RealtimeHubController.shared.reducerNativePlaybackActive
  }

  /// Stops every response-audio lane. Returns whether any lane was active.
  @discardableResult
  static func interrupt() -> Bool {
    let wasActive = isActive
    if let lease = VoiceTurnCoordinator.shared.outputSnapshot.activeLease,
      lease.lane == .nativeRealtime
    {
      _ = RealtimeHubController.shared.stopNativePlayback(lease: lease)
    }
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    VoiceResponsePlaybackMonitor.shared.refresh()
    return wasActive
  }
}

/// Publishes whether response audio is playing so composers can show a stop
/// control without polling `isSpeaking`.
@MainActor
final class VoiceResponsePlaybackMonitor: ObservableObject {
  static let shared = VoiceResponsePlaybackMonitor()

  @Published private(set) var isActive = false

  private init() {}

  func refresh() {
    let next = VoiceResponsePlayback.isActive
    if next != isActive {
      isActive = next
    }
  }
}
