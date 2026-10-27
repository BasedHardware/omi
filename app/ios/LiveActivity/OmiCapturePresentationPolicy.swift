import Foundation

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
        // Native recovery is already exhausted (actionRequired): not a wait, so no grace.
        if status == "noAudio" { return .notice(.unheard) }
        // Reconnecting transcription still saves audio, and a call hold resumes by itself.
        // A pendant still unheard this long after connecting is a real failure: the pendant
        // sends audio only when there is sound, so a confirmed subscription quiets the card
        // long before this (Dart maps a confirmed quiet to listening).
        if ["connecting", "unverified"].contains(status), statusAge >= unheardGrace { return .notice(.unheard) }
        if let battery, battery >= 0, battery <= lowBattery { return .notice(.battery) }
        return .hidden
    }
}
