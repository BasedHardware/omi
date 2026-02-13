import Foundation

/// Dedicated monitor for live transcript segments that doesn't trigger global AppState re-renders.
/// Only views that explicitly observe this class will update when transcript changes.
@MainActor
class LiveTranscriptMonitor: ObservableObject {
    static let shared = LiveTranscriptMonitor()

    /// Live speaker segments for real-time transcript display
    @Published private(set) var segments: [SpeakerSegment] = []

    private init() {}

    /// Update segments - called from transcription service
    func updateSegments(_ newSegments: [SpeakerSegment]) {
        segments = newSegments
    }

    /// Clear all segments
    func clear() {
        segments = []
    }

    /// Check if there are any segments
    var isEmpty: Bool {
        segments.isEmpty
    }

    /// Get the latest transcript text
    var latestText: String? {
        segments.last?.text
    }
}
