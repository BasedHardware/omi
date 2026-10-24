import Foundation

/// A server-side record of Omi working on one task (backend workstreams).
public struct Workstream: Identifiable, Hashable, Sendable {
    public enum Status: String, Sendable { case open, paused, completed, archived, unknown }

    public struct Event: Identifiable, Hashable, Sendable {
        /// An event's `evidence_refs` (kind `chat_message`, `external` …).
        public struct Evidence: Hashable, Sendable {
            public let kind: String
            public let id: String

            public init(kind: String, id: String) {
                self.kind = kind
                self.id = id
            }
        }

        public let id: String
        public let kind: String
        public let summary: String
        public let createdAt: Date?
        /// Position in the workstream's log (1 = first).
        public let sequence: Int
        public let evidence: [Evidence]

        public init(id: String, kind: String, summary: String, createdAt: Date?, sequence: Int = 0, evidence: [Evidence] = []) {
            self.id = id
            self.kind = kind
            self.summary = summary
            self.createdAt = createdAt
            self.sequence = sequence
            self.evidence = evidence
        }
    }

    public let id: String
    public let title: String
    public let status: Status
    public let summary: String?
    public let events: [Event]
    /// When anything last changed, and when the work last moved forward (backend fields).
    public let updatedAt: Date?
    public let lastProgressAt: Date?

    public init(
        id: String, title: String, status: Status, summary: String?, events: [Event], updatedAt: Date? = nil, lastProgressAt: Date? = nil
    ) {
        self.id = id
        self.title = title
        self.status = status
        self.summary = summary
        self.events = events
        self.updatedAt = updatedAt
        self.lastProgressAt = lastProgressAt
    }

    /// The newest moment anything happened on it (an event, an update, progress).
    public var lastActivityAt: Date? {
        ([updatedAt, lastProgressAt] + events.map(\.createdAt)).compactMap(\.self).max()
    }
}

/// One "what matters now" recommendation (backend `models/task_recommendation.py` `Recommendation`).
public struct Recommendation: Identifiable, Hashable, Sendable {
    /// What the user decided about a recommendation; each one goes back as task-intelligence
    /// feedback, so the backend stops (or pauses) showing it.
    public enum Decision: String, CaseIterable, Sendable {
        /// "Omi takes over" or "Do it".
        case doNow
        /// Show it again tomorrow.
        case later
        /// "Not now": the backend keeps it away for a month.
        case dismiss
        /// The user did it.
        case complete
        /// It was dealt with elsewhere (the backend proposes completing the task).
        case alreadyHandled
    }

    /// Where a recommendation comes from (`EvidenceRef`: kind `conversation`, `chat_message`, `external` …).
    public struct Evidence: Hashable, Sendable {
        public let kind: String
        public let id: String

        public init(kind: String, id: String) {
            self.kind = kind
            self.id = id
        }
    }

    /// The intervention id (feedback names it).
    public let id: String
    public let headline: String
    public let whyNow: String
    /// The next action in the backend's words ("Send Anna the Thursday follow-up").
    public let action: String
    public let taskID: String?
    public let workstreamID: String?
    /// The goal or workstream it belongs to, when the backend knows one.
    public let goalLabel: String?
    /// A second way to act, `verb:text` on the wire (`reschedule:Send proof of income`).
    public let alternativeAction: String?
    /// One line on where it comes from ("Created directly by you.", "Due in 2 days.").
    public let evidencePreview: String
    public let evidence: [Evidence]
    /// Feedback addresses this subject (a task, a candidate, a workstream …).
    public let feedbackSubjectKind: String
    public let feedbackSubjectID: String
    /// Stable across evaluations of the same thing: what the app hides after a decision.
    public let dedupeKey: String
    /// After this the recommendation is stale and the backend has to be asked again.
    public let expiresAt: Date?

    public init(
        id: String, headline: String, whyNow: String, action: String, taskID: String?, workstreamID: String? = nil,
        goalLabel: String? = nil, alternativeAction: String? = nil, evidencePreview: String = "", evidence: [Evidence] = [],
        feedbackSubjectKind: String = "task", feedbackSubjectID: String? = nil, dedupeKey: String? = nil, expiresAt: Date? = nil
    ) {
        self.id = id
        self.headline = headline
        self.whyNow = whyNow
        self.action = action
        self.taskID = taskID
        self.workstreamID = workstreamID
        self.goalLabel = goalLabel
        self.alternativeAction = alternativeAction
        self.evidencePreview = evidencePreview
        self.evidence = evidence
        self.feedbackSubjectKind = feedbackSubjectKind
        self.feedbackSubjectID = feedbackSubjectID ?? taskID ?? id
        self.dedupeKey = dedupeKey ?? id
        self.expiresAt = expiresAt
    }

    /// The verb of `alternativeAction` (`reschedule`), when it is coded that way.
    public var alternativeVerb: String? {
        guard let alternativeAction, let colon = alternativeAction.firstIndex(of: ":") else { return nil }
        let verb = alternativeAction[..<colon]
        return !verb.isEmpty && verb.allSatisfy { $0.isLetter || $0 == "_" } ? String(verb) : nil
    }

    /// Conversations the backend cites as the source.
    public var conversationIDs: [String] {
        evidence.filter { $0.kind == "conversation" }.map(\.id)
    }

    public func isExpired(at date: Date) -> Bool {
        expiresAt.map { $0 <= date } ?? false
    }
}

/// Addresses a workstream for writes: its id plus the account generation the backend requires
/// on every task-intelligence mutation (`X-Account-Generation`).
public struct WorkstreamRef: Hashable, Sendable {
    public let id: String
    public let generation: Int

    public init(id: String, generation: Int) {
        self.id = id
        self.generation = generation
    }
}
