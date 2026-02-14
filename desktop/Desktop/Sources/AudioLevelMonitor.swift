import Foundation
import Combine

/// Dedicated monitor for audio levels that doesn't trigger global AppState re-renders.
/// Only views that explicitly observe this class will update when audio levels change.
@MainActor
class AudioLevelMonitor: ObservableObject {
    static let shared = AudioLevelMonitor()

    /// Microphone audio level (0.0 - 1.0)
    @Published var microphoneLevel: Float = 0.0

    /// System audio level (0.0 - 1.0)
    @Published var systemLevel: Float = 0.0

    private init() {}

    /// Update microphone level - called from audio capture callback
    func updateMicrophoneLevel(_ level: Float) {
        microphoneLevel = level
    }

    /// Update system audio level - called from audio capture callback
    func updateSystemLevel(_ level: Float) {
        systemLevel = level
    }

    /// Reset both levels to zero
    func reset() {
        microphoneLevel = 0.0
        systemLevel = 0.0
    }
}
