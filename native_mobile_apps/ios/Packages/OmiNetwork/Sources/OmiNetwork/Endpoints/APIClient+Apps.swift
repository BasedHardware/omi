import Foundation

/// An Omi app (marketplace): extra skills, tools and summaries Omi can use.
public struct OmiApp: Identifiable, Hashable, Sendable {
    public let id: String
    public let name: String
    public let description: String
    public let author: String?
    public let imageURL: URL?
    public let category: String?
    public let rating: Double?
    public let installs: Int
    public var isEnabled: Bool
    /// `chat`, `persona`, `memories`, `external_integration`, `proactive_notification` …
    public var capabilities: Set<String>
    public var ratingCount: Int
    public var isPaid: Bool
    public var price: Double?

    public init(
        id: String, name: String, description: String, author: String?, imageURL: URL?,
        category: String?, rating: Double?, installs: Int, isEnabled: Bool,
        capabilities: Set<String> = [], ratingCount: Int = 0, isPaid: Bool = false, price: Double? = nil
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.author = author
        self.imageURL = imageURL
        self.category = category
        self.rating = rating
        self.installs = installs
        self.isEnabled = isEnabled
        self.capabilities = capabilities
        self.ratingCount = ratingCount
        self.isPaid = isPaid
        self.price = price
    }

    /// Can be chatted with (Flutter `worksWithChat`).
    public var worksWithChat: Bool {
        capabilities.contains("chat") || capabilities.contains("persona")
    }

    /// From the backend `App` schema (docs/api-reference/app-client-openapi.json).
    static func from(_ item: [String: Any]) -> OmiApp? {
        guard let id = item["id"] as? String, let name = item["name"] as? String else { return nil }
        return OmiApp(
            id: id, name: name,
            description: item["description"] as? String ?? "",
            author: item["author"] as? String,
            imageURL: (item["image"] as? String).flatMap(URL.init(string:)),
            category: item["category"] as? String,
            rating: item["rating_avg"] as? Double,
            installs: item["installs"] as? Int ?? 0,
            isEnabled: item["enabled"] as? Bool ?? false,
            capabilities: Set(item["capabilities"] as? [String] ?? []),
            ratingCount: item["rating_count"] as? Int ?? 0,
            isPaid: item["is_paid"] as? Bool ?? false,
            price: (item["price"] as? NSNumber)?.doubleValue
        )
    }
}

public extension APIClient {
    /// `GET v2/apps/search` (query, installed-only, paging).
    func searchApps(query: String, installedOnly: Bool, offset: Int) async throws -> [OmiApp] {
        var items = [
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "limit", value: "30"),
        ]
        if !query.isEmpty { items.append(URLQueryItem(name: "q", value: query)) }
        if installedOnly { items.append(URLQueryItem(name: "installed_apps", value: "true")) }
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v2/apps/search", query: items)) as? [String: Any]
        return (object?["data"] as? [[String: Any]] ?? []).compactMap(OmiApp.from)
    }

    /// `POST v1/apps/enable|disable?app_id=`
    func setApp(_ id: String, enabled: Bool) async throws {
        _ = try await data(.post, enabled ? "v1/apps/enable" : "v1/apps/disable", query: [URLQueryItem(name: "app_id", value: id)])
    }
}
