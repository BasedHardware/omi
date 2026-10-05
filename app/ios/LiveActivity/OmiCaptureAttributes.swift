import ActivityKit
import Foundation

@available(iOS 16.1, *)
struct OmiCaptureAttributes: ActivityAttributes {
    let recordingId: String

    struct ContentState: Codable, Hashable {
        var conversationRevision: Int
        var status: String
        var source: String
        var startedAt: Double
        var elapsed: Int
        var paused: Bool
        var canPause: Bool
        var canFinish: Bool
        var busy: Bool
        var actionFailed: Bool = false
    }
}

/// Lives in both targets, but the handler is installed only in Runner. The
/// extension renders attributes; it never accesses Flutter or opens a recorder.
@available(iOS 17.0, *)
@MainActor
enum OmiCaptureActionDispatcher {
    typealias Handler = (String, Int, String) async throws -> Void
    static var handler: Handler?

    static func perform(recordingId: String, revision: Int, action: String) async throws {
        // A cold intent launches Omi in the background, and Flutter registers its ready
        // handler only once the engine is up, which can take seconds on older iPhones.
        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline {
            if let handler {
                try await handler(recordingId, revision, action)
                return
            }
            try await Task.sleep(nanoseconds: 150_000_000)
        }
        throw CaptureActionError.unavailable
    }
}

enum CaptureActionError: LocalizedError {
    case unavailable
    var errorDescription: String? { NSLocalizedString("Open Omi to control this recording", comment: "Live Activity action failure") }
}
