import Foundation
import OmiCore

/// What's new after an update (`backend/routers/announcements.py`).
public struct Announcement: Identifiable, Sendable, Equatable {
    public enum Kind: Sendable, Equatable {
        /// One version's changes.
        case changelog(version: String?, changes: [Change])
        /// A feature walkthrough, one page per step.
        case feature(steps: [Change])
        /// A message with an optional button (`navigate:/route` or `url:https://…`).
        case message(body: String, imageURL: URL?, buttonTitle: String?, buttonURL: URL?)
    }

    public struct Change: Sendable, Equatable, Identifiable {
        public var id: String { title + text }
        public let emoji: String?
        public let title: String
        public let text: String
        public let imageURL: URL?

        public init(emoji: String?, title: String, text: String, imageURL: URL? = nil) {
            self.emoji = emoji
            self.title = title
            self.text = text
            self.imageURL = imageURL
        }
    }

    public let id: String
    public let title: String
    public let kind: Kind

    public init(id: String, title: String, kind: Kind) {
        self.id = id
        self.title = title
        self.kind = kind
    }
}

/// One "For you" card (`GET v1/proactivity/feed`, Flutter `home_for_you`).
public struct ForYouItem: Identifiable, Sendable, Equatable {
    public enum Target: Sendable, Equatable { case conversation(String), task(String) }
    /// Flutter's outcome actions; `stopThese` is `producer_disabled`.
    public enum Feedback: String, Sendable {
        case shown, opened, helpful = "thumbs_up", notHelpful = "thumbs_down", stopThese = "producer_disabled", dismissed
    }

    public let id: String
    /// Who made it; "Stop these" hides every item from the same producer.
    public let producer: String
    public let title: String
    public let body: String
    public let target: Target?
    /// `none`, `thumbs_up`, `thumbs_down`.
    public var feedback: String

    public init(id: String, producer: String, title: String, body: String, target: Target?, feedback: String = "none") {
        self.id = id
        self.producer = producer
        self.title = title
        self.body = body
        self.target = target
        self.feedback = feedback
    }
}

/// Server-side narrowing for conversation search (`SearchRequest`).
public struct ConversationSearchFilter: Sendable, Equatable {
    public var start: Date?
    public var end: Date?
    /// A person id, or `user` for what the user said.
    public var speakerID: String?

    public init(start: Date? = nil, end: Date? = nil, speakerID: String? = nil) {
        self.start = start
        self.end = end
        self.speakerID = speakerID
    }

    public var isEmpty: Bool {
        start == nil && end == nil && speakerID == nil
    }
}

public extension APIClient {
    /// `GET v1/announcements/changelogs`: from `fromVersion` (exclusive) to `toVersion`, or the latest `limit`.
    func changelogs(fromVersion: String?, toVersion: String?, limit: Int) async throws -> [Announcement] {
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        if let fromVersion, let toVersion {
            query = [URLQueryItem(name: "from_version", value: fromVersion), URLQueryItem(name: "to_version", value: toVersion)]
        }
        let data = try await data(.get, "v1/announcements/changelogs", query: query)
        return (try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []).compactMap(AnnouncementMapper.map)
    }

    /// `GET v1/announcements/pending?app_version=X.Y.Z+build&platform=ios&trigger=`.
    func pendingAnnouncements(appVersion: String, versionUpgrade: Bool) async throws -> [Announcement] {
        let data = try await data(.get, "v1/announcements/pending", query: [
            URLQueryItem(name: "app_version", value: appVersion), URLQueryItem(name: "platform", value: "ios"),
            URLQueryItem(name: "trigger", value: versionUpgrade ? "version_upgrade" : "app_launch"),
        ])
        return (try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []).compactMap(AnnouncementMapper.map)
    }

    /// `POST v1/announcements/{id}/dismiss` with `{"cta_clicked": …}`.
    func dismissAnnouncement(id: String, buttonTapped: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["cta_clicked": buttonTapped])
        _ = try await data(.post, "v1/announcements/\(id)/dismiss", body: .json(body))
    }

    /// `GET v1/proactivity/feed?limit=20`; `nil` when the feed is turned off for the user.
    func forYouFeed() async throws -> [ForYouItem]? {
        let data = try await data(.get, "v1/proactivity/feed", query: [URLQueryItem(name: "limit", value: "20")])
        let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        guard root["enabled"] as? Bool ?? false else { return nil }
        return (root["items"] as? [[String: Any]] ?? []).compactMap { item -> ForYouItem? in
            guard let id = item["id"] as? String, !(item["dismissed"] as? Bool ?? false) else { return nil }
            let target = item["target"] as? [String: Any]
            let targetID = target?["id"] as? String
            return ForYouItem(
                id: id, producer: item["producer"] as? String ?? "", title: item["title"] as? String ?? "",
                body: item["body"] as? String ?? "",
                target: targetID.flatMap { target?["kind"] as? String == "action_item" ? .task($0) : .conversation($0) },
                feedback: item["feedback"] as? String ?? "none"
            )
        }
    }

    /// `POST v1/proactivity/items/{id}/outcomes` with a fresh `event_id` (extra fields are rejected).
    func sendForYouFeedback(itemID: String, _ feedback: ForYouItem.Feedback) async throws {
        let body = try JSONSerialization.data(withJSONObject: [
            "event_id": UUID().uuidString.lowercased(), "action": feedback.rawValue, "surface": "ios", "channel": "feed",
        ])
        _ = try await data(.post, "v1/proactivity/items/\(itemID)/outcomes", body: .json(body))
    }

    /// `POST v1/conversations/search` with `start_date` / `end_date` / `speaker_id`; an empty query
    /// with a filter browses.
    func searchConversations(query: String, page: Int, perPage: Int, filter: ConversationSearchFilter) async throws -> [Conversation] {
        var fields: [String: Any] = ["query": query, "page": page, "per_page": perPage, "include_discarded": false]
        let format = ISO8601DateFormatter()
        if let start = filter.start { fields["start_date"] = format.string(from: start) }
        if let end = filter.end { fields["end_date"] = format.string(from: end) }
        if let speaker = filter.speakerID { fields["speaker_id"] = speaker }
        let data = try await data(.post, "v1/conversations/search", body: .json(JSONSerialization.data(withJSONObject: fields)))
        return try decode(FilteredSearchPage.self, from: data).items.map(ConversationMapper.map)
    }

    /// `GET v1/users/daily-summaries/search?query=`: day recaps where every word appears.
    func searchRecaps(query: String) async throws -> [DailySummary] {
        let data = try await data(.get, "v1/users/daily-summaries/search", query: [
            URLQueryItem(name: "query", value: query), URLQueryItem(name: "limit", value: "10"),
        ])
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (object?["summaries"] as? [[String: Any]] ?? []).compactMap(DailySummaryMapper.map)
    }
}

private struct FilteredSearchPage: Decodable {
    let items: [OmiAPI.Conversation]
}

enum AnnouncementMapper {
    static func map(_ json: [String: Any]) -> Announcement? {
        guard let id = json["id"] as? String, let content = json["content"] as? [String: Any] else { return nil }
        let title = content["title"] as? String ?? ""
        func changes(_ key: String) -> [Announcement.Change] {
            (content[key] as? [[String: Any]] ?? []).compactMap { item in
                guard let title = item["title"] as? String else { return nil }
                return .init(
                    emoji: item["icon"] as? String, title: title, text: item["description"] as? String ?? "",
                    imageURL: (item["image_url"] as? String).flatMap(URL.init(string:))
                )
            }
        }
        switch json["type"] as? String {
        case "changelog":
            let version = json["app_version"] as? String
            return Announcement(id: id, title: title, kind: .changelog(version: version, changes: changes("changes")))
        case "feature":
            return Announcement(id: id, title: title, kind: .feature(steps: changes("steps")))
        case "announcement":
            let button = content["cta"] as? [String: Any]
            return Announcement(id: id, title: title, kind: .message(
                body: content["body"] as? String ?? "",
                imageURL: (content["image_url"] as? String).flatMap(URL.init(string:)),
                buttonTitle: button?["text"] as? String,
                buttonURL: (button?["action"] as? String).flatMap(link)
            ))
        default:
            return nil
        }
    }

    /// `url:https://…` or a bare https link opens in the browser; `navigate:/route` becomes `omi://route`.
    static func link(_ action: String) -> URL? {
        if action.hasPrefix("url:") { return URL(string: String(action.dropFirst(4))).flatMap(web) }
        if action.hasPrefix("navigate:") { return URL(string: "omi:/" + String(action.dropFirst(9))) }
        if action.hasPrefix("/") { return URL(string: "omi:/" + action) }
        return URL(string: action).flatMap(web)
    }

    private static func web(_ url: URL) -> URL? {
        ["http", "https"].contains(url.scheme?.lowercased() ?? "") ? url : nil
    }
}
