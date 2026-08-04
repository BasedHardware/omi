import Foundation

/// Capture health, per stream and in aggregate.
///
/// This file exists because of one measured failure. On 2 August 2026 the app bundle was re-signed;
/// macOS keys a Screen Recording grant to the code signature, so the grant died with the old
/// signature while the microphone's — which is keyed differently — survived. From that moment the
/// screen stream captured nothing: 2,026 frames on disk, the newest at 14:20:48, and none ever
/// again. The app went on writing `{"capturing": true}` to its heartbeat for the next twenty-nine
/// hours, because the one boolean it published was `!running.isEmpty` — an **or** over three
/// independent sensors, read by every human and every model downstream as an **and**. A live
/// microphone hid a dead screen completely.
///
/// So the wire carries a report per stream, and the aggregate is *derived from* those reports
/// rather than computed beside them. There is no way to publish "capturing" over a stream that is
/// blocked, because nothing anywhere is allowed to write that boolean by hand.
public enum StreamName {
    public static let microphone = "microphone"
    public static let systemAudio = "systemAudio"
    public static let screen = "screen"
    public static let storage = "storage"
}

/// The five things one capture stream can be, and no others.
///
/// The distinction that carries the most weight is **`off` versus `blocked`**, and it is not about
/// the OS's answer — both can read "permission not granted" from TCC. It is about whether the user
/// is getting what they asked for:
///
/// - `off` is the app doing what it was told. A permission never granted, a switch turned off, a
///   capability this macOS does not have. Worth saying, never worth alarming about, and it does
///   **not** make the app degraded — otherwise every install that declined system audio would read
///   as broken forever.
/// - `blocked` is a promise that has stopped being kept. Something that used to work does not any
///   more, or a grant exists that this process cannot use. That is the re-signing case above, and
///   it is the state that has to reach the menu bar loudly.
public enum StreamState: String, Codable, Sendable {
    /// Asked to start; nothing observed from it yet. The launch window, and a few seconds long.
    case starting
    /// Running and producing.
    case live
    /// Needs the user. A grant that was there and is gone, a grant this process cannot use until it
    /// is relaunched, or hardware the OS refuses.
    case blocked
    /// Believed running and producing nothing for longer than the stream's own patience. The
    /// hardest state to notice without being told, and the reason the watchdogs exist.
    case stalled
    /// Deliberately not running: switched off, never permitted, or unsupported here.
    case off

    public var isLive: Bool { self == .live }

    /// Whether being in this state means something the user expects to be recorded is not being
    /// recorded. `off` is excluded on purpose — see the note above.
    public var isDegraded: Bool {
        switch self {
        case .starting, .blocked, .stalled: return true
        case .live, .off: return false
        }
    }
}

/// One capture stream's own account of itself.
public struct StreamReport: Codable, Sendable, Equatable {
    /// One of ``StreamName``. A string rather than an enum so a newer app writing a stream an older
    /// reader has never heard of degrades to "an unfamiliar stream" instead of failing to decode
    /// the whole heartbeat.
    public var name: String
    public var state: StreamState
    /// Why, in the app's own voice, or nil when there is nothing to explain.
    public var detail: String?
    /// Unix time this stream last produced anything. Nil when it never has — which is itself the
    /// difference between "not set up yet" and "stopped working".
    public var lastOutputAt: Double?

    public init(name: String, state: StreamState, detail: String? = nil, lastOutputAt: Double? = nil) {
        self.name = name
        self.state = state
        self.detail = detail
        self.lastOutputAt = lastOutputAt
    }
}

/// What the whole recorder is doing — three values, because two could not tell the truth.
public enum CaptureHealth: String, Codable, Sendable {
    /// Everything that should be running is running.
    case capturing
    /// Something is being recorded and something that should be is not. The state the app was in
    /// for twenty-nine hours with no way to say so.
    case degraded
    /// Nothing is being recorded.
    case off

    /// **The one place the aggregate is computed.** Every surface reads this rather than deciding
    /// for itself, which is what stops the menu bar, the heartbeat file and the MCP `status` tool
    /// from drifting into three different answers about the same machine.
    ///
    /// Storage is special and comes first: it is the single shared dependency, so a database that
    /// will not open makes every live sensor pointless. Everything else is a sensor, and the rule
    /// over sensors is the same one this codebase already applies to permission groups — the
    /// aggregate reads well only when **every** member does.
    public init(of streams: [StreamReport]) {
        if streams.contains(where: { $0.name == StreamName.storage && $0.state == .blocked }) {
            self = .off
            return
        }
        let sensors = streams.filter { $0.name != StreamName.storage }
        guard sensors.contains(where: { $0.state.isLive }) else {
            self = .off
            return
        }
        self = sensors.allSatisfy { $0.state.isLive || $0.state == .off } ? .capturing : .degraded
    }
}
