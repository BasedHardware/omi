import Combine
import Foundation
import QuartzCore

/// Dedicated monitor for audio levels that doesn't trigger global AppState re-renders.
/// Only views that explicitly observe this class will update when audio levels change.
/// Updates are throttled to ~5 Hz to avoid flooding SwiftUI with layout invalidations.
@MainActor
class AudioLevelMonitor: ObservableObject {
  static let shared = AudioLevelMonitor()

  /// Microphone audio level (0.0 - 1.0)
  @Published private(set) var microphoneLevel: Float = 0.0

  /// System audio level (0.0 - 1.0)
  @Published private(set) var systemLevel: Float = 0.0

  /// Latest un-throttled mic level for frame-rate visualizations (notch
  /// waveform). Deliberately not @Published: TimelineView-driven canvases poll
  /// it every animation frame, so publishing at capture rate would only flood
  /// SwiftUI with invalidations the canvas doesn't need.
  private(set) var liveMicrophoneLevel: Float = 0.0

  /// Latest assistant voice playback output level (0.0 - 1.0), fed by the
  /// realtime PCM player's output tap. Same poll-per-frame contract as
  /// `liveMicrophoneLevel`.
  private(set) var liveVoicePlaybackLevel: Float = 0.0

  // Throttle: only publish at ~5 Hz (every ~200ms)
  private let updateInterval: Double = 1.0 / 5.0
  private var lastMicUpdate: Double = 0.0
  private var lastSysUpdate: Double = 0.0
  private var pendingMicLevel: Float = 0.0
  private var pendingSysLevel: Float = 0.0

  private init() {}

  /// Update microphone level - called from audio capture callback.
  /// Throttled to ~5 Hz to prevent excessive SwiftUI re-renders.
  func updateMicrophoneLevel(_ level: Float) {
    liveMicrophoneLevel = level
    pendingMicLevel = level
    let now = CACurrentMediaTime()
    if now - lastMicUpdate >= updateInterval {
      lastMicUpdate = now
      microphoneLevel = level
    }
  }

  /// Update assistant voice playback level - called (on the main queue) from
  /// the realtime PCM player's output tap. Un-throttled; see
  /// `liveVoicePlaybackLevel`.
  func updateVoicePlaybackLevel(_ level: Float) {
    liveVoicePlaybackLevel = level
  }

  /// Update system audio level - called from audio capture callback.
  /// Throttled to ~5 Hz to prevent excessive SwiftUI re-renders.
  func updateSystemLevel(_ level: Float) {
    pendingSysLevel = level
    let now = CACurrentMediaTime()
    if now - lastSysUpdate >= updateInterval {
      lastSysUpdate = now
      systemLevel = level
    }
  }

  /// Reset both levels to zero
  func reset() {
    microphoneLevel = 0.0
    systemLevel = 0.0
    liveMicrophoneLevel = 0.0
    liveVoicePlaybackLevel = 0.0
    pendingMicLevel = 0.0
    pendingSysLevel = 0.0
  }
}
