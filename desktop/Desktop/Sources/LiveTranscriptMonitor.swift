import Foundation

/// Dedicated monitor for live transcript segments that doesn't trigger global AppState re-renders.
/// Only views that explicitly observe this class will update when transcript changes.
@MainActor
class LiveTranscriptMonitor: ObservableObject {
    static let shared = LiveTranscriptMonitor()

    /// Live speaker segments for real-time transcript display
    @Published private(set) var segments: [SpeakerSegment] = []

    /// Snapshot of segments saved before clear, so the transcript survives recording stop
    @Published private(set) var savedSegments: [SpeakerSegment] = []

    private init() {}

    /// Update segments - called from transcription service
    func updateSegments(_ newSegments: [SpeakerSegment]) {
        segments = newSegments
    }

    /// Clear live segments, automatically snapshotting them to savedSegments
    func clear() {
        if !segments.isEmpty {
            savedSegments = segments
        }
        segments = []
    }

    /// Clear the saved snapshot (e.g. when user collapses the transcript panel)
    func clearSaved() {
        savedSegments = []
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
