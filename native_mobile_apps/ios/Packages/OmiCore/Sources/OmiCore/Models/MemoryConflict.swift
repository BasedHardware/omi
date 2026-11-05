import Foundation

/// A memory the backend holds back because it contradicts what Omi already knows (backend
/// `models/memory_review.py`, `GET v3/memories/review-queue`): the new candidate and the
/// memories it conflicts with. The user decides which is right.
public struct MemoryConflict: Identifiable, Hashable, Sendable {
    /// How a conflict is resolved (`POST v3/memories/review-queue/{id}/resolve`).
    public enum Decision: String, Sendable {
        /// The new candidate is right (it replaces the earlier ones).
        case accept
        /// The new candidate is wrong (the earlier memory stays).
        case reject
    }

    /// `review_id`.
    public let id: String
    /// The candidate's memory id (`fact_id`).
    public let factID: String
    /// What Omi heard now.
    public let candidate: String
    /// The memories it contradicts.
    public let conflictsWith: [String]
    public let createdAt: Date?

    public init(id: String, factID: String, candidate: String, conflictsWith: [String], createdAt: Date?) {
        self.id = id
        self.factID = factID
        self.candidate = candidate
        self.conflictsWith = conflictsWith
        self.createdAt = createdAt
    }
}
