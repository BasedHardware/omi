import Foundation
#if canImport(ActivityKit) && os(iOS)
    import ActivityKit
#endif

/// The one Live Activity type Omi shows, in two kinds: a recording (Omi, iPhone microphone or Apple
/// Watch) and a task Omi works on. Each kind is its own activity, so both can be on the Lock Screen.
/// The recording card is the Flutter app's capture card (`OmiCaptureAttributes`), field for field
/// where our app has the data.
public struct OmiActivityAttributes: Codable, Hashable, Sendable {
    public enum Kind: String, Codable, Hashable, Sendable {
        case capture
        case agent
    }

    public let kind: Kind

    public init(kind: Kind) {
        self.kind = kind
    }

    public struct ContentState: Codable, Hashable, Sendable {
        public enum Phase: String, Codable, Hashable, Sendable {
            /// Capture is on (see `status`).
            case recording
            /// Omi works on a task.
            case working
            /// Omi finished the task; the card stays a few minutes.
            case finished
            /// Omi could not finish it.
            case failed
        }

        public enum Source: String, Codable, Hashable, Sendable {
            case omi
            case iPhone
            case watch
        }

        /// What the recording does with its audio (Flutter's `status`).
        public enum CaptureStatus: String, Codable, Hashable, Sendable {
            /// Streamed and transcribed live.
            case listening
            /// Saved on the phone and transcribed later (Transcribe later, or the connection dropped).
            case recording
            /// Stopped by the user; the conversation stays open until Start or End.
            case paused
            /// Over; shown for the card's brief exit.
            case ended
        }

        /// What the card follows: the recording or the run. A card swiped away stays away for it.
        public var id: String
        public var phase: Phase
        /// When the clock reads zero. A recording's start moves on by the time it was stopped.
        public var startedAt: Date
        /// Where the running clock's range ends (see `clockEnd(since:now:)`).
        public var clockEnd: Date
        /// The clock's frozen value in seconds while stopped or over; nil while it runs.
        public var elapsed: Int?
        public var source: Source?
        public var status: CaptureStatus
        /// The card offers Stop and Start (the Omi and the iPhone microphone; not the watch).
        public var canPause: Bool
        /// The task the run belongs to (opens it on tap).
        public var taskID: String?
        public var title: String
        /// The agent's current step ("Searching the web").
        public var step: String
        /// Other runs still going besides the one shown.
        public var otherRuns: Int

        public init(
            id: String, phase: Phase, startedAt: Date, clockEnd: Date? = nil, elapsed: Int? = nil, source: Source? = nil,
            status: CaptureStatus = .listening, canPause: Bool = false, taskID: String? = nil, title: String = "",
            step: String = "", otherRuns: Int = 0
        ) {
            self.id = id
            self.phase = phase
            self.startedAt = startedAt
            self.clockEnd = clockEnd ?? startedAt.addingTimeInterval(3600)
            self.elapsed = elapsed
            self.source = source
            self.status = status
            self.canPause = canPause
            self.taskID = taskID
            self.title = title
            self.step = step
            self.otherRuns = otherRuns
        }

        /// A recording. `startedAt` is its start moved on by the time it was stopped; `elapsed` the
        /// frozen clock while stopped.
        public static func capture(
            id: String, startedAt: Date, source: Source, status: CaptureStatus, elapsed: Int? = nil, canPause: Bool,
            now: Date = .now
        ) -> Self {
            Self(id: id, phase: .recording, startedAt: startedAt, clockEnd: clockEnd(since: startedAt, now: now),
                 elapsed: status == .paused || status == .ended ? max(0, elapsed ?? 0) : nil, source: source,
                 status: status, canPause: canPause)
        }

        /// The last content before the card closes: the clock stops where it is and the actions go.
        public func ended(at now: Date) -> Self {
            var final = self
            final.elapsed = elapsed ?? max(0, Int(now.timeIntervalSince(startedAt)))
            final.canPause = false
            if phase == .recording { final.status = .ended }
            return final
        }

        /// Only the agent's step moved on: such updates wait for the throttle; everything else
        /// (a phase, a status, the clock's range) goes out at once.
        public func isRoutineChange(from old: Self) -> Bool {
            var aligned = old
            aligned.step = step
            return aligned == self && step != old.step
        }

        /// A live recording's card is refreshed every `heartbeat` seconds; one Omi stopped refreshing
        /// (killed, or suspended) turns stale and says so. A stopped one never goes stale: iOS may
        /// suspend Omi while the microphone is off, and Start must stay on the card (as in Flutter).
        public func staleDate(now: Date) -> Date? {
            guard phase == .recording, status == .listening || status == .recording else { return nil }
            return now.addingTimeInterval(Self.staleAfter)
        }

        public static let heartbeat: TimeInterval = 60
        public static let staleAfter: TimeInterval = 90
    }
}

#if canImport(ActivityKit) && os(iOS)
    extension OmiActivityAttributes: ActivityAttributes {}
#endif

/// ActivityKit budgets updates, so routine changes (an agent's step) go out at most every
/// `interval`; urgent ones (a phase, status or clock change) after a short `floor` that only
/// merges bursts. The caller sends when told `.send` and re-asks after `.wait`.
public struct ActivityUpdateThrottle: Sendable {
    public enum Decision: Equatable, Sendable {
        case send
        case wait(TimeInterval)
    }

    public let interval: TimeInterval
    public let floor: TimeInterval
    public private(set) var lastSent: Date?

    public init(interval: TimeInterval = 4, floor: TimeInterval = 1) {
        self.interval = interval
        self.floor = floor
    }

    public func decide(urgent: Bool, at now: Date) -> Decision {
        guard let lastSent else { return .send }
        let elapsed = now.timeIntervalSince(lastSent)
        let required = urgent ? floor : interval
        return elapsed >= required ? .send : .wait(required - elapsed)
    }

    public mutating func didSend(at now: Date) {
        lastSent = now
    }

    public mutating func reset() {
        lastSent = nil
    }
}

/// The paused time a recording has built up, so its clock skips it (Flutter shifts `startedAt` by
/// the stopped time). Feed it every observed state; it starts over for a new recording.
public struct CapturePauseClock: Sendable {
    private var recording: Date?
    private var pausedTotal: TimeInterval = 0
    private var pausedAt: Date?

    public init() {}

    /// The recording's clock start (`since` moved on by the time stopped) and, while stopped, its
    /// frozen seconds.
    public mutating func observe(since: Date, paused: Bool, now: Date) -> (startedAt: Date, elapsed: Int?) {
        if recording != since {
            recording = since
            pausedTotal = 0
            pausedAt = nil
        }
        if paused, pausedAt == nil { pausedAt = now }
        if !paused, let pausedAt {
            pausedTotal += max(0, now.timeIntervalSince(pausedAt))
            self.pausedAt = nil
        }
        let start = since.addingTimeInterval(pausedTotal)
        guard let pausedAt else { return (start, nil) }
        return (start, max(0, Int(pausedAt.timeIntervalSince(start))))
    }
}
