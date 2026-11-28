import Foundation
import OmiCore
import OmiNetwork

/// Backend state for what's new, For you and filtered search.
public final class FakeDiscover: @unchecked Sendable {
    /// One entry per call, e.g. `changelogs:1.0.0>1.1.0`, `pending:version_upgrade`, `feedback:fy1=thumbs_up`.
    public internal(set) var log: [String] = []
    public var failing: Set<String> = []
    public var changelogs: [Announcement] = [
        Announcement(id: "cl-1", title: "1.1.0", kind: .changelog(version: "1.1.0", changes: [
            .init(emoji: "🧠", title: "Memory graph", text: "See how what Omi knows connects."),
        ])),
    ]
    public var pending: [Announcement] = []
    /// `nil`: the feed is turned off for the user.
    public var forYou: [ForYouItem]? = [
        ForYouItem(
            id: "fy1", producer: "follow-ups", title: "Reply to Anna", body: "She asked about the launch date.",
            target: .conversation("c1")
        ),
        ForYouItem(id: "fy2", producer: "follow-ups", title: "Send the deck", body: "You promised it by Friday.", target: .task("t1")),
        ForYouItem(id: "fy3", producer: "habits", title: "Walk after lunch", body: "You feel better when you do.", target: nil),
    ]
    /// Every filtered search sent, in order.
    public internal(set) var searches: [(query: String, filter: ConversationSearchFilter)] = []
    public var recaps: [DailySummary] = []

    public init() {}
}

public extension FakeAPIClient {
    private func recordDiscover(_ kind: String, _ entry: String = "") throws {
        try lock.withLock {
            if let _error { throw _error }
            discover.log.append(entry.isEmpty ? kind : "\(kind):\(entry)")
            if discover.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    func changelogs(fromVersion: String?, toVersion: String?, limit: Int) async throws -> [Announcement] {
        try recordDiscover("changelogs", fromVersion.map { "\($0)>\(toVersion ?? "")" } ?? "limit=\(limit)")
        return discover.changelogs
    }

    func pendingAnnouncements(appVersion _: String, versionUpgrade: Bool) async throws -> [Announcement] {
        try recordDiscover("pending", versionUpgrade ? "version_upgrade" : "app_launch")
        return discover.pending
    }

    func dismissAnnouncement(id: String, buttonTapped: Bool) async throws {
        try recordDiscover("dismiss", "\(id)=\(buttonTapped)")
        discover.pending.removeAll { $0.id == id }
    }

    func forYouFeed() async throws -> [ForYouItem]? {
        try recordDiscover("feed")
        return discover.forYou
    }

    func sendForYouFeedback(itemID: String, _ feedback: ForYouItem.Feedback) async throws {
        try recordDiscover("feedback", "\(itemID)=\(feedback.rawValue)")
    }

    func searchConversations(query: String, page: Int, perPage: Int, filter: ConversationSearchFilter) async throws -> [Conversation] {
        lock.withLock { discover.searches.append((query, filter)) }
        try recordDiscover("search", query)
        let all = try await conversations(limit: Int.max, offset: 0)
        let needle = query.trimmingCharacters(in: .whitespaces)
        let hits = all.filter { conversation in
            let text = conversation.title + " " + conversation.overview
            return (needle.isEmpty || text.localizedStandardContains(needle))
                && filter.start.map { conversation.date >= $0 } ?? true
                && filter.end.map { conversation.date <= $0 } ?? true
        }
        return Array(hits.dropFirst((page - 1) * perPage).prefix(perPage))
    }

    func searchRecaps(query: String) async throws -> [DailySummary] {
        try recordDiscover("recaps", query)
        return discover.recaps.filter { $0.headline.localizedStandardContains(query) || $0.overview.localizedStandardContains(query) }
    }
}
