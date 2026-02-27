import Foundation
import Combine
import QuartzCore

/// Dedicated monitor for audio levels that doesn't trigger global AppState re-renders.
/// Only views that explicitly observe this class will update when audio levels change.
/// Updates are throttled to ~15 Hz to avoid flooding SwiftUI with layout invalidations.
@MainActor
class AudioLevelMonitor: ObservableObject {
    static let shared = AudioLevelMonitor()

    /// Microphone audio level (0.0 - 1.0)
    @Published var microphoneLevel: Float = 0.0

    /// System audio level (0.0 - 1.0)
    @Published var systemLevel: Float = 0.0

    // Throttle: only publish at ~15 Hz (every ~67ms)
    private let updateInterval: Double = 1.0 / 15.0
    private var lastMicUpdate: Double = 0.0
    private var lastSysUpdate: Double = 0.0
    private var pendingMicLevel: Float = 0.0
    private var pendingSysLevel: Float = 0.0

    private init() {}

    /// Update microphone level - called from audio capture callback.
    /// Throttled to ~15 Hz to prevent excessive SwiftUI re-renders.
    func updateMicrophoneLevel(_ level: Float) {
        pendingMicLevel = level
        let now = CACurrentMediaTime()
        if now - lastMicUpdate >= updateInterval {
            lastMicUpdate = now
            microphoneLevel = level
        }
    }

    /// Update system audio level - called from audio capture callback.
    /// Throttled to ~15 Hz to prevent excessive SwiftUI re-renders.
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
        pendingMicLevel = 0.0
        pendingSysLevel = 0.0
    }
}
