import Foundation

/// A day in review (`v1/users/daily-summaries`, Omi's "Daily Recaps").
public struct DailySummary: Identifiable, Hashable, Sendable {
    public struct Highlight: Hashable, Sendable {
        public let topic: String
        public let emoji: String?
        public let summary: String

        public init(topic: String, emoji: String?, summary: String) {
            self.topic = topic
            self.emoji = emoji
            self.summary = summary
        }
    }

    public let id: String
    /// Local calendar date, `YYYY-MM-DD`.
    public let date: String
    public let headline: String
    public let overview: String
    public let emoji: String?
    public let conversationCount: Int?
    public let highlights: [Highlight]
    public let decisions: [String]

    public init(
        id: String, date: String, headline: String, overview: String, emoji: String?,
        conversationCount: Int?, highlights: [Highlight], decisions: [String]
    ) {
        self.id = id
        self.date = date
        self.headline = headline
        self.overview = overview
        self.emoji = emoji
        self.conversationCount = conversationCount
        self.highlights = highlights
        self.decisions = decisions
    }

    /// The date as a `Date` at local midnight.
    public var day: Date? {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: date)
    }
}
