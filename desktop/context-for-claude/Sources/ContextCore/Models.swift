import Foundation
import GRDB

// MARK: - Stored records

/// A contiguous run of speech. A gap longer than `SessionPolicy.gapSeconds` starts a new one.
public struct Session: Codable, Sendable, Identifiable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "sessions"

    public var id: Int64?
    /// Unix epoch seconds.
    public var startedAt: Double
    /// Unix epoch seconds; nil while the session is still open.
    public var endedAt: Double?
    /// Frontmost app when the session opened. Turns a Zoom/Meet session into an identifiable
    /// meeting without any meeting-detection logic.
    public var appHint: String?

    public init(id: Int64? = nil, startedAt: Double, endedAt: Double? = nil, appHint: String? = nil) {
        self.id = id
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.appHint = appHint
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

/// Where a transcript line came from. Mic is the user; the system tap is everyone else.
public enum SegmentSource: String, Codable, Sendable, CaseIterable {
    case mic
    case system

    /// Speaker attribution without a diarization model — the floor, not the ceiling. A line the
    /// backend diarized carries `Segment.speakerLabel` and `Segment.personId` on top of this.
    public var speaker: String { self == .mic ? "me" : "them" }
}

/// One transcribed line of speech.
public struct Segment: Codable, Sendable, Identifiable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "segments"

    public var id: Int64?
    public var sessionId: Int64
    /// Unix epoch seconds.
    public var startedAt: Double
    /// Unix epoch seconds.
    public var endedAt: Double
    /// Raw value of `SegmentSource`.
    public var source: String
    /// "me" or "them".
    public var speaker: String
    public var text: String
    /// The diarization label the backend gave this voice, e.g. `"SPEAKER_00"`.
    ///
    /// Stable **within one backend conversation only**, and meaningless across two. What it is good
    /// for is separating voices that this app's own attribution cannot: three people on a call all
    /// arrive through the system tap and are all `speaker == "them"`, and this is the only thing in
    /// the row that says they were three people rather than one.
    ///
    /// Nil for every locally transcribed line, which never had a diarizer, and for any cloud line
    /// the server did not label. Nil means "nobody separated the voices here" — never "one voice".
    public var speakerLabel: String?
    /// The Omi person the backend's speech-profile matching identified on this line.
    ///
    /// An **opaque backend id**, deliberately not a name. The account's people are renamed, merged
    /// and re-enrolled by the user long after a line is captured, and a name copied into this row at
    /// capture time would keep asserting the old one forever with nothing to correct it. The id
    /// stays true to whoever the person becomes; resolving it to today's name belongs to the reader,
    /// which holds an Omi credential and can ask.
    ///
    /// Nil is the common case and carries no claim: no speech profile matched, no profile is
    /// enrolled, or the line never went through the cloud at all. An absent person must never render
    /// as an identified one.
    public var personId: String?
    /// The transcriber's own confidence in this line, 0–1.
    ///
    /// Optional because it is unknowable for every row written before it was recorded, and because
    /// an absent score must never read as a low one: nil means "nobody asked the model", not "the
    /// model was unsure". A default of 0 here would turn a year of perfectly good transcript into
    /// evidence that the app never understood a word.
    public var confidence: Double?
    /// Stable Omi conversation identity for a cloud-transcribed segment. Nil for local lines.
    public var backendConversationId: String?
    /// Stable only within `backendConversationId`. Nil means the backend supplied no safe revision key.
    public var backendSegmentId: String?

    public init(
        id: Int64? = nil,
        sessionId: Int64,
        startedAt: Double,
        endedAt: Double,
        source: SegmentSource,
        text: String,
        speakerLabel: String? = nil,
        personId: String? = nil,
        confidence: Double? = nil,
        backendConversationId: String? = nil,
        backendSegmentId: String? = nil
    ) {
        self.id = id
        self.sessionId = sessionId
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.source = source.rawValue
        self.speaker = source.speaker
        self.text = text
        // Blank is the same absence as missing, and the wire is full of empty strings. Normalising
        // here means one reading of "unattributed" reaches the database, so a `personId IS NOT NULL`
        // in SQL cannot disagree with a `!= nil` in Swift.
        self.speakerLabel = Segment.attribute(speakerLabel)
        self.personId = Segment.attribute(personId)
        self.confidence = confidence
        self.backendConversationId = Segment.attribute(backendConversationId)
        self.backendSegmentId = Segment.attribute(backendSegmentId)
    }

    private static func attribute(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty
        else { return nil }
        return trimmed
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

/// One screen observation: the active window, its title, and whatever text was on it.
public struct Frame: Codable, Sendable, Identifiable, FetchableRecord, MutablePersistableRecord {
    public static let databaseTableName = "frames"

    public var id: Int64?
    /// Unix epoch seconds.
    public var capturedAt: Double
    public var appName: String?
    /// The owning application's bundle identifier, e.g. `com.todesktop.230313mzl4w4u92`.
    ///
    /// Kept alongside `appName` rather than instead of it, because the two answer different
    /// questions and only one of them survives a rename: the display name is what a person reads
    /// back on a timeline, and the identifier is the only thing that can find the app again on disk
    /// to draw its icon. Nil for every row captured before the column existed, and nil means "not
    /// recorded" — never "this app has no bundle".
    public var bundleId: String?
    public var windowTitle: String?
    public var ocrText: String?
    /// Absolute path to the stored image, if one was kept.
    public var imagePath: String?
    /// The focused window's accessibility text, in reading order.
    ///
    /// Kept beside `ocrText` rather than replacing it, because the two fail differently: OCR sees
    /// everything drawn and guesses at it, while this is exact but covers only what the application
    /// chose to expose. A window rendered as one canvas has OCR text and no accessibility text; a
    /// window of small dense type has both, and only one of them is right.
    public var axText: String?
    /// Content address of the captured tree, or nil when nothing was captured.
    public var axRootHash: Data?

    public init(
        id: Int64? = nil,
        capturedAt: Double,
        appName: String? = nil,
        bundleId: String? = nil,
        windowTitle: String? = nil,
        ocrText: String? = nil,
        imagePath: String? = nil,
        axText: String? = nil,
        axRootHash: Data? = nil
    ) {
        self.id = id
        self.capturedAt = capturedAt
        self.appName = appName
        self.bundleId = bundleId
        self.windowTitle = windowTitle
        self.ocrText = ocrText
        self.imagePath = imagePath
        self.axText = axText
        self.axRootHash = axRootHash
    }

    public mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

// MARK: - Query results (the MCP wire shape)

/// A single dated, attributed piece of context. The one shape every search returns.
public struct Hit: Codable, Sendable, Equatable {
    /// The score at or below which a transcript line is *marked* uncertain. Nothing is ever dropped
    /// for being under it.
    ///
    /// Per-window confidence in this app's logs runs from about 0.5 to 0.99, and the failure that
    /// prompted this — background music transcribed through the microphone as the user's own
    /// first-person speech — sat at the bottom of that band (0.57 in the dogfooding session). 0.65
    /// is roughly the lowest third of the observed range: above the band those lines occupy, and
    /// below where ordinary clean speech lands, so the mark stays rare enough to still mean
    /// something. A bar set where everything trips it says nothing at all.
    ///
    /// This is a marking bar, not a filter, which is exactly what makes the precise number safe to
    /// be wrong about in either direction: the raw score travels on every hit, so a consuming model
    /// that wants a stricter or a looser one can apply it. Hiding a line the user really said is
    /// the only unrecoverable choice, so it is the one never made here.
    public static let lowConfidenceFloor: Double = 0.65

    /// "said" (you), "heard" (someone else), or "screen".
    public var kind: String
    /// Unix epoch seconds.
    public var at: Double
    /// Local human-readable timestamp — Claude reasons about "last Tuesday", not about epochs.
    public var when: String
    public var text: String
    public var app: String?
    public var window: String?
    public var sessionId: Int64?
    /// How sure the transcriber was of this line, 0–1. Nil for screen hits, which have no such
    /// score, and for speech captured before the score was kept — never a stand-in for "low".
    public var confidence: Double?
    /// True only when a score exists and sits below `Hit.lowConfidenceFloor`.
    ///
    /// The point of a separate flag is that the reader does not have to know the bar to honour it,
    /// and that an unscored line cannot be mistaken for a doubtful one.
    public var isLowConfidence: Bool
    /// The backend's diarization label for the voice on this line, e.g. `"SPEAKER_00"`. Nil for
    /// screen hits and for any line nothing diarized.
    ///
    /// `kind` says which side of the microphone a line came from and never stops being true; this
    /// says which voice it was. Two `heard` lines with different labels are two people, which is
    /// more than `kind` alone can ever express.
    public var speakerLabel: String?
    /// The Omi person the backend matched this voice to, as an **opaque id** — never a name.
    ///
    /// Names live in the account and change there; this layer stores what was captured. A reader
    /// with a credential turns the id into today's name, and a reader without one still knows that
    /// two lines sharing an id came from the same person. Nil means nobody was identified, which is
    /// the ordinary case and is not a claim about who was speaking.
    public var personId: String?

    public init(
        kind: String,
        at: Double,
        text: String,
        app: String? = nil,
        window: String? = nil,
        sessionId: Int64? = nil,
        confidence: Double? = nil,
        speakerLabel: String? = nil,
        personId: String? = nil
    ) {
        self.kind = kind
        self.at = at
        self.when = ContextTime.describe(at)
        self.text = text
        self.app = app
        self.window = window
        self.sessionId = sessionId
        self.confidence = confidence
        self.speakerLabel = speakerLabel
        self.personId = personId
        // Derived here rather than at the call sites: a hit whose flag disagreed with its own score
        // would be worse than carrying no flag at all.
        self.isLowConfidence = confidence.map { $0 < Hit.lowConfidenceFloor } ?? false
    }
}

public struct SessionSummary: Codable, Sendable, Equatable {
    public var id: Int64
    public var startedAt: Double
    public var endedAt: Double?
    public var when: String
    public var durationSeconds: Double
    public var appHint: String?
    public var lineCount: Int
    /// Whether the other side was captured at all — a one-sided session is you talking, not a call.
    public var bothSidesPresent: Bool
    /// The Omi people the backend identified in this conversation, as opaque ids, in the order they
    /// first spoke.
    ///
    /// This is what makes "my call with Sarah" answerable: a reader resolves the ids against the
    /// account and picks the session, instead of reading every transcript looking for a name.
    /// Empty means nobody was identified — a session nothing diarized, or one with no enrolled voice
    /// in it. It never means the user was alone; `bothSidesPresent` is the field that speaks to that.
    public var personIds: [String]
    /// First few lines, enough for Claude to decide whether to pull the transcript.
    public var preview: String

    public init(
        id: Int64,
        startedAt: Double,
        endedAt: Double?,
        durationSeconds: Double,
        appHint: String?,
        lineCount: Int,
        bothSidesPresent: Bool,
        preview: String,
        personIds: [String] = []
    ) {
        self.id = id
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.when = ContextTime.describe(startedAt)
        self.durationSeconds = durationSeconds
        self.appHint = appHint
        self.lineCount = lineCount
        self.bothSidesPresent = bothSidesPresent
        self.preview = preview
        self.personIds = personIds
    }
}

/// A contiguous stretch spent in one app — the shape of a day.
public struct ActivityBlock: Codable, Sendable, Equatable {
    public var app: String
    public var window: String?
    public var startedAt: Double
    public var endedAt: Double
    public var when: String
    public var durationSeconds: Double
    public var sampleText: String?

    public init(app: String, window: String?, startedAt: Double, endedAt: Double, sampleText: String?) {
        self.app = app
        self.window = window
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.when = ContextTime.describe(startedAt)
        self.durationSeconds = max(0, endedAt - startedAt)
        self.sampleText = sampleText
    }
}

public struct CapabilityReport: Codable, Sendable, Equatable {
    public var name: String
    public var granted: Bool
    public var detail: String

    /// The word a report carries when the capability is in. Here rather than in the app because
    /// ``CaptureState`` writes it too, when it reconciles a report against a stream that is live —
    /// and a status the app spells one way and the heartbeat another is two claims a reader has to
    /// work out are the same one.
    public static let grantedDetail = "Granted"

    public init(name: String, granted: Bool, detail: String) {
        self.name = name
        self.granted = granted
        self.detail = detail
    }
}

/// Capture health. Lets Claude say "I only have data from 2pm" instead of guessing.
public struct StatusInfo: Codable, Sendable, Equatable {
    public var capturing: Bool
    /// Three-valued, because "capturing" and "not capturing" cannot say *half*. A recorder with a
    /// live microphone and a dead screen is neither, and reporting it as either is the failure this
    /// field exists to end.
    public var health: CaptureHealth
    public var pausedReason: String?
    public var capabilities: [CapabilityReport]
    /// The per-stream reports out of the heartbeat, so `status` can name which half is down rather
    /// than leaving a reader to infer it from a permission list.
    public var streams: [StreamReport]
    public var segmentCount: Int
    public var frameCount: Int
    public var sessionCount: Int
    public var oldestAt: Double?
    public var newestAt: Double?
    public var coverage: String
    public var databasePath: String

    public init(
        capturing: Bool,
        health: CaptureHealth? = nil,
        pausedReason: String?,
        capabilities: [CapabilityReport],
        streams: [StreamReport] = [],
        segmentCount: Int,
        frameCount: Int,
        sessionCount: Int,
        oldestAt: Double?,
        newestAt: Double?,
        databasePath: String
    ) {
        self.capturing = capturing
        self.health = health ?? (capturing ? .capturing : .off)
        self.pausedReason = pausedReason
        self.capabilities = capabilities
        self.streams = streams
        self.segmentCount = segmentCount
        self.frameCount = frameCount
        self.sessionCount = sessionCount
        self.oldestAt = oldestAt
        self.newestAt = newestAt
        self.databasePath = databasePath
        if let oldestAt, let newestAt {
            self.coverage = "\(ContextTime.describe(oldestAt)) → \(ContextTime.describe(newestAt))"
        } else {
            self.coverage = "no data captured yet"
        }
    }

    /// First sentence of MCP `status` for the local half. Kept here so hermetic tests can assert
    /// `capturing + transcription gap` without writing the real heartbeat file.
    ///
    /// Prefer this for the fully-capturing case; `StatusTool.headline` still owns the degraded
    /// wording that names which streams are down.
    public var localCaptureHeadline: String {
        if capturing {
            if let reason = Self.nonEmptyReason(pausedReason) {
                return "Context for Claude is capturing right now — \(reason)."
            }
            return "Context for Claude is capturing right now."
        }
        if let reason = Self.nonEmptyReason(pausedReason) {
            return "Context for Claude is not capturing right now — \(reason)."
        }
        return "Context for Claude is not capturing right now."
    }

    private static func nonEmptyReason(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

// MARK: - Time

public enum ContextTime {
    public static var now: Double { Date().timeIntervalSince1970 }

    private static let formatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEE d MMM yyyy 'at' h:mm a"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    /// Local human-readable timestamp, e.g. "Tue 28 Jul 2026 at 2:14 PM".
    public static func describe(_ epoch: Double) -> String {
        formatter.string(from: Date(timeIntervalSince1970: epoch))
    }
}
