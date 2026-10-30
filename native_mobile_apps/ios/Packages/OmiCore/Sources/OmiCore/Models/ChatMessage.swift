import Foundation

public struct ChatMessage: Identifiable, Hashable, Sendable {
    public enum Sender: String, Sendable { case user = "human", omi = "ai" }

    public let id: String
    public var text: String
    public let sender: Sender
    public let createdAt: Date
    /// Progress steps the agent reported while answering ("Searching the web").
    public var steps: [String]
    /// Conversations the answer drew on.
    public var references: [Reference]
    /// Set when this answer did not come through as a reply (the UI words it).
    public var failure: Failure?
    /// The backend's id once the message is stored (a streamed answer keeps its local `id`).
    public var serverID: String?
    /// The user's rating: 1 helpful, -1 not helpful, nil none.
    public var rating: Int?
    /// One grounded next question the answer invites (a `followUp` content block).
    public var followUp: String?
    /// A chart the answer draws (`chart_data`).
    public var chart: ChatChart?
    /// Photos and files sent with a question.
    public var files: [ChatFile]
    /// Where the answer came from (backend `evidence`): conversation summaries and moments.
    public var evidence: [ChatEvidence] = []
    /// The answer's structured parts (backend `content_blocks`, the follow-up excluded).
    public var blocks: [ChatBlock] = []
    /// A plain message, or the day's summary Omi posts in the evening (backend `type: day_summary`).
    public var kind: Kind = .text

    public enum Kind: String, Hashable, Sendable {
        case text
        case daySummary = "day_summary"
    }

    public enum Failure: String, Hashable, Sendable {
        /// No answer arrived (network, backend error, canned failure text).
        case couldNotAnswer
        /// The answer broke off part way.
        case interrupted
        /// The user stopped it.
        case stopped
        /// The phone had no connection.
        case offline
        /// The backend gave up waiting for the answer.
        case timeout
        /// The plan's monthly chat limit is used up.
        case quotaExceeded
    }

    public struct Reference: Hashable, Sendable {
        public let conversationID: String
        public let title: String
        public let emoji: String?
        /// When the conversation happened (its `created_at`).
        public let createdAt: Date?

        public init(conversationID: String, title: String, emoji: String?, createdAt: Date? = nil) {
            self.conversationID = conversationID
            self.title = title
            self.emoji = emoji
            self.createdAt = createdAt
        }
    }

    public init(
        id: String, text: String, sender: Sender, createdAt: Date,
        steps: [String] = [], references: [Reference] = [], failure: Failure? = nil,
        serverID: String? = nil, rating: Int? = nil, followUp: String? = nil, chart: ChatChart? = nil, files: [ChatFile] = []
    ) {
        self.id = id
        self.text = text
        self.sender = sender
        self.createdAt = createdAt
        self.steps = steps
        self.references = references
        self.failure = failure
        self.serverID = serverID
        self.rating = rating
        self.followUp = followUp
        self.chart = chart
        self.files = files
    }
}

/// What a chat turn is about (backend `PageContext`).
public struct ChatContext: Hashable, Sendable {
    public enum Kind: String, Sendable { case conversation, task, memory }
    public let kind: Kind
    public let id: String
    public let title: String

    public init(kind: Kind, id: String, title: String) {
        self.kind = kind
        self.id = id
        self.title = title
    }
}
