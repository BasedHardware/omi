import Foundation

/// A captured conversation, reduced to what the app renders. Adapted from the generated
/// `OmiAPI.Conversation` wire type in OmiNetwork; screens never see wire types.
public struct Conversation: Identifiable, Hashable, Sendable {
    public enum Status: String, Sendable {
        case inProgress, processing, merging, completed, failed, unknown
    }

    /// Who can open the conversation: only the owner, or anyone with its link.
    public enum Visibility: String, Sendable {
        case `private`, shared, `public`
    }

    public let id: String
    public var title: String
    public let overview: String
    public let emoji: String?
    public let category: String?
    public let createdAt: Date
    public let startedAt: Date?
    public let finishedAt: Date?
    public var status: Status
    public var isStarred: Bool
    public let actionItemCount: Int
    public var folderID: String?
    public var visibility: Visibility
    /// Behind the paywall: it cannot be merged or moved.
    public let isLocked: Bool
    /// The summary failed and the backend can try again (`summary_retryable`).
    public let summaryRetryable: Bool
    /// Where it was recorded (location allowed at the time).
    public let location: ConversationLocation?
    /// Omi judged it not worth keeping (shown only when the list includes discarded ones).
    public let isDiscarded: Bool
    /// Other devices recorded the same moment (`capture_group`): the group, and the recording the
    /// list shows for it.
    public let captureGroupID: String?
    public let captureGroupPrimaryID: String?
    /// Who took part: the summary's participants, then calendar attendees (`EntityVisual`).
    public let people: [ConversationPerson]

    public init(
        id: String,
        title: String,
        overview: String,
        emoji: String?,
        category: String?,
        createdAt: Date,
        startedAt: Date?,
        finishedAt: Date?,
        status: Status,
        isStarred: Bool,
        actionItemCount: Int,
        folderID: String? = nil,
        visibility: Visibility = .private,
        isLocked: Bool = false,
        summaryRetryable: Bool = false,
        location: ConversationLocation? = nil,
        isDiscarded: Bool = false,
        captureGroupID: String? = nil,
        captureGroupPrimaryID: String? = nil,
        people: [ConversationPerson] = []
    ) {
        self.id = id
        self.title = title
        self.overview = overview
        self.emoji = emoji
        self.category = category
        self.createdAt = createdAt
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.status = status
        self.isStarred = isStarred
        self.actionItemCount = actionItemCount
        self.folderID = folderID
        self.visibility = visibility
        self.isLocked = isLocked
        self.summaryRetryable = summaryRetryable
        self.location = location
        self.isDiscarded = isDiscarded
        self.captureGroupID = captureGroupID
        self.captureGroupPrimaryID = captureGroupPrimaryID
        self.people = people
    }

    /// When the conversation happened (start if known, else creation).
    public var date: Date {
        startedAt ?? createdAt
    }

    public var duration: TimeInterval? {
        guard let startedAt, let finishedAt, finishedAt > startedAt else { return nil }
        return finishedAt.timeIntervalSince(startedAt)
    }

    /// The summary did not come out: failed, or finished without one while the backend offers a retry.
    public var summaryFailed: Bool {
        status == .failed || (status == .completed && summaryRetryable)
    }

    /// The backend merges only finished, unlocked conversations (`validate_merge_compatibility`).
    public var canMerge: Bool {
        status == .completed && !isLocked
    }
}

/// Someone in a conversation, as far as the backend knows them (any field may be missing).
public struct ConversationPerson: Hashable, Sendable {
    public let name: String?
    public let email: String?
    public let organization: String?

    public init(name: String?, email: String?, organization: String? = nil) {
        self.name = name
        self.email = email
        self.organization = organization
    }
}
