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
        // Set by LiveActivityManager, never by Flutter, so they are optional to decode.
        /// What needs the user's attention (CaptureNotice); nil is the recording card.
        var notice: String?
        /// When the current status began, in Unix seconds.
        var noticeSince: Double?
        /// The pendant's battery percentage, when one is known.
        var pendantBattery: Int?
    }
}

/// Healthy pendant capture is the default, so it shows nothing. A card appears only
/// when capture needs the user; the order here is the order in which they win.
enum CaptureNotice: String {
    case muted
    case unheard
    case battery
}

enum CapturePresentationPolicy {
    /// Connecting at the start of a recording is normal; a pendant still unheard after
    /// this long is not.
    static let unheardGrace: TimeInterval = 120
    static let lowBattery = 15

    enum Decision: Equatable {
        case hidden
        /// The recording card with its clock: a phone recording the user started.
        case recording
        case notice(CaptureNotice)
    }

    /// `battery` is nil when no fresh reading from a connected, discharging pendant exists.
    static func decide(status: String, source: String, statusAge: TimeInterval, battery: Int?) -> Decision {
        if status == "ended" { return .hidden }
        if source == "phone" { return .recording }
        if status == "paused" { return .notice(.muted) }
        // Reconnecting transcription still saves audio, and a call hold resumes by itself.
        if ["connecting", "unverified"].contains(status), statusAge >= unheardGrace { return .notice(.unheard) }
        if let battery, battery >= 0, battery <= lowBattery { return .notice(.battery) }
        return .hidden
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
