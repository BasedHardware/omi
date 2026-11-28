import Foundation

/// A photo or file sent with a chat message (backend `FileChat`).
public struct ChatFile: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let mimeType: String
    /// The backend's thumbnail for images.
    public let thumbnailURL: URL?
    /// A small JPEG kept on the phone, so a photo shows before (and without) the backend's thumbnail.
    public var localPreview: Data?

    public var isImage: Bool {
        mimeType.hasPrefix("image")
    }

    public init(id: String, name: String, mimeType: String, thumbnailURL: URL? = nil, localPreview: Data? = nil) {
        self.id = id
        self.name = name
        self.mimeType = mimeType
        self.thumbnailURL = thumbnailURL
        self.localPreview = localPreview
    }
}

/// A chart an answer draws (backend `ChartData`): one line or bar chart, one or more series.
public struct ChatChart: Hashable, Sendable {
    public enum Kind: String, Sendable { case line, bar }

    public struct Point: Hashable, Sendable {
        public let label: String
        public let value: Double

        public init(label: String, value: Double) {
            self.label = label
            self.value = value
        }
    }

    public struct Series: Hashable, Sendable {
        public let label: String
        public let points: [Point]
        /// `#RRGGBB`, when the backend picks one.
        public let color: String?

        public init(label: String, points: [Point], color: String?) {
            self.label = label
            self.points = points
            self.color = color
        }
    }

    public let kind: Kind
    public let title: String
    public let xLabel: String?
    public let yLabel: String?
    public let series: [Series]

    public init(kind: Kind, title: String, xLabel: String?, yLabel: String?, series: [Series]) {
        self.kind = kind
        self.title = title
        self.xLabel = xLabel
        self.yLabel = yLabel
        self.series = series
    }
}

/// One source an answer drew on (backend `ChatEvidenceReference`). The answer text stays the
/// authority; these are chips under it. Unknown kinds and states from a newer backend decode as
/// `.unknown` and are not shown.
public struct ChatEvidence: Identifiable, Hashable, Sendable {
    public enum Kind: String, Sendable {
        case conversationSummary = "conversation_summary"
        case conversationSegment = "conversation_segment"
        case screen, keyframe, request, unknown
    }

    public enum State: String, Sendable { case available, loading, offline, pruned, failed, unknown }

    public let id: String
    public let kind: Kind
    public let state: State
    public let title: String?
    public let summary: String?
    public let conversationID: String?
    public let segmentID: String?
    /// The moment inside the conversation (milliseconds from its start).
    public let startMs: Int?
    public let endMs: Int?
    /// When it was captured (epoch milliseconds), for screen evidence.
    public let capturedAtMs: Int?

    public init(
        id: String, kind: Kind, state: State, title: String? = nil, summary: String? = nil, conversationID: String? = nil,
        segmentID: String? = nil, startMs: Int? = nil, endMs: Int? = nil, capturedAtMs: Int? = nil
    ) {
        self.id = id
        self.kind = kind
        self.state = state
        self.title = title
        self.summary = summary
        self.conversationID = conversationID
        self.segmentID = segmentID
        self.startMs = startMs
        self.endMs = endMs
        self.capturedAtMs = capturedAtMs
    }

    /// A conversation the app can open (summary or moment, and still there).
    public var opensConversation: Bool {
        conversationID != nil && (kind == .conversationSummary || kind == .conversationSegment)
            && state != .pruned && state != .failed
    }
}
