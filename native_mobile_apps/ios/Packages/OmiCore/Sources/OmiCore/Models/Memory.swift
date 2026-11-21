import Foundation

/// Something Omi knows about the user.
public struct Memory: Identifiable, Hashable, Sendable {
    /// Who may see it: private memories stay with the user, public ones feed their persona.
    public enum Visibility: String, Sendable { case `private`, `public` }

    public let id: String
    public var content: String
    public let headline: String?
    public let category: String
    public let createdAt: Date
    public let conversationID: String?
    public var visibility: Visibility
    /// Pinned as a baseline fact Omi always keeps.
    public var isBaseline: Bool
    /// The user answered "Is this right?" (`userReview` holds the answer).
    public var reviewed: Bool
    public var userReview: Bool?
    /// `{platform}_{hash}` of the phone or computer that captured it (Flutter `ClientDeviceService`).
    public let captureDevice: String?
    /// Locked behind a plan upgrade: shown, not editable.
    public let isLocked: Bool
    /// The backend's belief in it (0…1) and how cleanly its source was captured (0…1).
    public var veracity: Double?
    public var captureConfidence: Double?
    /// Why it needs caution (`single_source`, `low_capture_signal`, `contradicted_by`, `stale`,
    /// `third_party_subject`; backend `UncertaintyReason`), as sent.
    public var uncertaintyReasons: [String]
    /// Who it is about: `user`, `third_party`, `unknown`, `legacy_assumed`.
    public var subjectAttribution: String?
    /// The person it is about when the backend names one (`arguments.subject` …).
    public var subjectName: String?
    /// Where it was heard (conversation ids and the like), newest first.
    public var evidence: [Evidence]

    /// One source of a memory (backend `Evidence`).
    public struct Evidence: Hashable, Sendable {
        public let sourceType: String
        public let sourceID: String?
        public let capturedAt: Date?

        public init(sourceType: String, sourceID: String?, capturedAt: Date?) {
            self.sourceType = sourceType
            self.sourceID = sourceID
            self.capturedAt = capturedAt
        }
    }

    public init(
        id: String, content: String, headline: String?, category: String, createdAt: Date, conversationID: String?,
        visibility: Visibility = .private, isBaseline: Bool = false, reviewed: Bool = false, userReview: Bool? = nil,
        captureDevice: String? = nil, isLocked: Bool = false, veracity: Double? = nil, captureConfidence: Double? = nil,
        uncertaintyReasons: [String] = [], subjectAttribution: String? = nil, subjectName: String? = nil, evidence: [Evidence] = []
    ) {
        self.id = id
        self.content = content
        self.headline = headline
        self.category = category
        self.createdAt = createdAt
        self.conversationID = conversationID
        self.visibility = visibility
        self.isBaseline = isBaseline
        self.reviewed = reviewed
        self.userReview = userReview
        self.captureDevice = captureDevice
        self.isLocked = isLocked
        self.veracity = veracity
        self.captureConfidence = captureConfidence
        self.uncertaintyReasons = uncertaintyReasons
        self.subjectAttribution = subjectAttribution
        self.subjectName = subjectName
        self.evidence = evidence
    }
}
