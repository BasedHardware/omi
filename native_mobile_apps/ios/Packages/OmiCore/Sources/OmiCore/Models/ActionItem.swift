import Foundation

/// A task (the backend still calls them action items). Mirrors `ActionItemResponse`.
public struct ActionItem: Identifiable, Hashable, Sendable {
    /// Who has to do it. `.other` means someone else committed to it ("waiting on").
    public enum Owner: String, Sendable { case user, other, unknown }
    /// The backend's canonical state. `cancelled` ("Not a task") and `superseded` (merged into
    /// `supersededBy`) are gone for the user, though the list still returns them.
    public enum Status: String, Sendable { case active, completed, cancelled, superseded }
    public enum Priority: String, Sendable { case high, medium, low }
    /// Where the task was heard (`EvidenceRef`: kind `conversation`, `chat_message` …).
    public struct Evidence: Hashable, Sendable {
        public let kind: String
        public let id: String

        public init(kind: String, id: String) {
            self.kind = kind
            self.id = id
        }
    }

    public let id: String
    public var description: String
    /// Ticking a task off (or back on) moves `status` with it, as the backend does.
    public var isCompleted: Bool {
        didSet {
            if status == .active || status == .completed { status = isCompleted ? .completed : .active }
        }
    }
    public var dueAt: Date?
    public let conversationID: String?
    public let owner: Owner
    /// Set when an agent workstream works on this task (PLAN.md §4.4, wired in P4).
    public let workstreamID: String?
    public let createdAt: Date?
    /// Subtask depth 0...3: a row is the child of the nearest row above it with a smaller level
    /// (`indent_level`, as in Flutter's Tasks page).
    public var indentLevel: Int
    /// Manual order inside a bucket; 0 means "not placed by hand" (`sort_order`).
    public var sortOrder: Int
    /// The task app it was sent to (`todoist`, `apple_reminders`, …); nil when not exported.
    public var exportPlatform: String?
    /// The `EKReminder.calendarItemIdentifier` it is linked to (Apple Reminders sync).
    public var appleReminderID: String?
    public var updatedAt: Date?
    public var status: Status
    /// The task this one was merged into (`status == .superseded`).
    public var supersededBy: String?
    public var priority: Priority?
    /// How sure the backend is about `dueAt` (0...1); nil when set by hand.
    public var dueConfidence: Double?
    public var provenance: [Evidence]
    public var goalID: String?

    public var isExported: Bool { exportPlatform != nil }

    /// Still something to do: not completed, not cancelled, not merged into another task.
    public var isOpen: Bool { !isCompleted && status == .active }

    public init(
        id: String,
        description: String,
        isCompleted: Bool,
        dueAt: Date?,
        conversationID: String?,
        owner: Owner,
        workstreamID: String?,
        createdAt: Date?,
        indentLevel: Int = 0,
        sortOrder: Int = 0,
        exportPlatform: String? = nil,
        appleReminderID: String? = nil,
        updatedAt: Date? = nil,
        status: Status? = nil,
        supersededBy: String? = nil,
        priority: Priority? = nil,
        dueConfidence: Double? = nil,
        provenance: [Evidence] = [],
        goalID: String? = nil
    ) {
        self.id = id
        self.description = description
        self.isCompleted = isCompleted
        self.dueAt = dueAt
        self.conversationID = conversationID
        self.owner = owner
        self.workstreamID = workstreamID
        self.createdAt = createdAt
        self.indentLevel = indentLevel
        self.sortOrder = sortOrder
        self.exportPlatform = exportPlatform
        self.appleReminderID = appleReminderID
        self.updatedAt = updatedAt
        self.status = status ?? (isCompleted ? .completed : .active)
        self.supersededBy = supersededBy
        self.priority = priority
        self.dueConfidence = dueConfidence
        self.provenance = provenance
        self.goalID = goalID
    }
}
