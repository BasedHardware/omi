import Foundation

/// Dedicated timer for recording duration that doesn't trigger global AppState re-renders.
/// Only views that explicitly observe this class will update when duration changes.
@MainActor
class RecordingTimer: ObservableObject {
    static let shared = RecordingTimer()

    /// Current recording duration in seconds
    @Published private(set) var duration: TimeInterval = 0

    private var timer: Timer?
    private var startTime: Date?

    private init() {}

    /// Start the recording timer
    func start() {
        startTime = Date()
        duration = 0

        // Update every second
        timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self = self, let start = self.startTime else { return }
                self.duration = Date().timeIntervalSince(start)
            }
        }
    }

    /// Stop the recording timer
    func stop() {
        timer?.invalidate()
        timer = nil
        startTime = nil
    }

    /// Reset the timer to zero
    func reset() {
        stop()
        duration = 0
    }

    /// Formatted duration string (HH:MM:SS)
    var formattedDuration: String {
        let total = Int(duration)
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let seconds = total % 60
        return String(format: "%02d:%02d:%02d", hours, minutes, seconds)
    }
}
