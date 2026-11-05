import Foundation

/// Who is signed in, as the backend knows it (`GET v1/users/profile`): the name and email shown on
/// top of Settings when this iPhone has none saved.
public struct UserProfile: Sendable, Equatable {
    public let name: String?
    public let email: String?

    public init(name: String?, email: String?) {
        self.name = name
        self.email = email
    }
}

/// Usage for one period (`GET v1/users/me/usage`, Flutter `usage_page`).
public struct UsageStats: Sendable, Equatable {
    public enum Period: String, Sendable, CaseIterable {
        case today, monthly, yearly
        case allTime = "all_time"
    }

    public struct Totals: Sendable, Equatable {
        public let transcriptionSeconds: Int
        public let words: Int
        public let insights: Int
        public let memories: Int

        public init(transcriptionSeconds: Int, words: Int, insights: Int, memories: Int) {
            self.transcriptionSeconds = transcriptionSeconds
            self.words = words
            self.insights = insights
            self.memories = memories
        }

        public var isEmpty: Bool {
            transcriptionSeconds == 0 && words == 0 && insights == 0 && memories == 0
        }
    }

    public let totals: Totals
    /// Hourly (today), daily (month), monthly (year) or yearly (all time) buckets, oldest first.
    public let history: [(date: String, totals: Totals)]

    public init(totals: Totals, history: [(date: String, totals: Totals)]) {
        self.totals = totals
        self.history = history
    }

    public static func == (lhs: UsageStats, rhs: UsageStats) -> Bool {
        lhs.totals == rhs.totals && lhs.history.map(\.date) == rhs.history.map(\.date)
            && lhs.history.map(\.totals) == rhs.history.map(\.totals)
    }
}

/// Fair-use standing (`GET v1/fair-use/status`).
public struct FairUseStatus: Sendable, Equatable {
    public struct Window: Sendable, Equatable {
        public let usedHours: Double
        public let limitHours: Double
        public let percent: Double
    }

    /// `none`, `warning`, `throttle` or `restrict`.
    public let stage: String
    public let caseReference: String?
    public let today: Window
    public let threeDays: Window
    public let week: Window
    /// Ready-to-show text from the server.
    public let message: String

    public init(stage: String, caseReference: String?, today: Window, threeDays: Window, week: Window, message: String) {
        self.stage = stage
        self.caseReference = caseReference
        self.today = today
        self.threeDays = threeDays
        self.week = week
        self.message = message
    }
}

public extension FairUseStatus.Window {
    init(used: Double, limit: Double) {
        self.init(usedHours: used, limitHours: limit, percent: limit > 0 ? used / limit * 100 : 0)
    }
}

/// An installed app that reads or writes the user's data (Flutter `data_privacy_page`).
public struct AppDataAccess: Identifiable, Sendable, Equatable {
    public let id: String
    public let name: String
    public let imageURL: URL?
    public let readsConversations: Bool
    public let readsMemories: Bool
    /// `memory_creation`, `transcript_processed`, `audio_bytes`.
    public let trigger: String?

    public init(id: String, name: String, imageURL: URL?, readsConversations: Bool, readsMemories: Bool, trigger: String?) {
        self.id = id
        self.name = name
        self.imageURL = imageURL
        self.readsConversations = readsConversations
        self.readsMemories = readsMemories
        self.trigger = trigger
    }
}

/// Omi Wrapped for one year (`GET v1/wrapped/{year}`; the backend serves 2025 only).
public struct Wrapped: Sendable, Equatable {
    public enum Status: String, Sendable { case notGenerated = "not_generated", processing, done, error }

    public struct Highlight: Sendable, Equatable, Identifiable {
        public var id: String { title + text }
        public let emoji: String?
        public let title: String
        public let text: String

        public init(emoji: String?, title: String, text: String) {
            self.emoji = emoji
            self.title = title
            self.text = text
        }
    }

    public let year: Int
    public let status: Status
    public let progress: String?
    public let conversations: Int
    public let daysActive: Int
    public let hours: Double
    public let topCategories: [String]
    public let tasksDone: Int
    public let tasks: Int
    public let topPhrases: [String]
    public let buddies: [Highlight]
    /// Memorable days, best moments, struggle and win: one card each.
    public let highlights: [Highlight]

    public init(
        year: Int, status: Status, progress: String? = nil, conversations: Int = 0, daysActive: Int = 0, hours: Double = 0,
        topCategories: [String] = [], tasksDone: Int = 0, tasks: Int = 0, topPhrases: [String] = [],
        buddies: [Highlight] = [], highlights: [Highlight] = []
    ) {
        self.year = year
        self.status = status
        self.progress = progress
        self.conversations = conversations
        self.daysActive = daysActive
        self.hours = hours
        self.topCategories = topCategories
        self.tasksDone = tasksDone
        self.tasks = tasks
        self.topPhrases = topPhrases
        self.buddies = buddies
        self.highlights = highlights
    }
}
