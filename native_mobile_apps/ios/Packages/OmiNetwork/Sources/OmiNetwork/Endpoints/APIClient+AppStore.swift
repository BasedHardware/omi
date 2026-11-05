import Foundation
import OmiCore

/// One review of an app (backend `AppReview`).
public struct AppReview: Identifiable, Hashable, Sendable {
    public var id: String {
        uid
    }

    public let uid: String
    public let score: Double
    public let text: String
    public let username: String?
    public let ratedAt: Date?
    /// The app maker's answer.
    public let response: String?

    public init(uid: String, score: Double, text: String, username: String?, ratedAt: Date?, response: String?) {
        self.uid = uid
        self.score = score
        self.text = text
        self.username = username
        self.ratedAt = ratedAt
        self.response = response
    }

    static func from(_ object: [String: Any]) -> AppReview? {
        guard let uid = object["uid"] as? String else { return nil }
        let response = (object["response"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        return AppReview(
            uid: uid, score: (object["score"] as? NSNumber)?.doubleValue ?? 0, text: object["review"] as? String ?? "",
            username: (object["username"] as? String).flatMap { $0.isEmpty ? nil : $0 },
            ratedAt: BackendDate.parse(object["rated_at"] as? String), response: response
        )
    }
}

/// Everything the app page shows (`GET v1/apps/{id}`).
public struct AppDetail: Hashable, Sendable {
    public struct SetupStep: Hashable, Sendable {
        public let name: String
        public let url: URL
    }

    public var app: OmiApp
    public let reviews: [AppReview]
    public let userReview: AppReview?
    /// Signed in-app links to connect an outside service (`external_integration.auth_steps`).
    public let setupSteps: [SetupStep]
    /// A setup guide: a web page, or markdown text (`setup_instructions_file_path`).
    public let setupInstructionsURL: URL?
    public let setupInstructionsText: String?
    /// Opened after the app is turned on (`app_home_url`).
    public let homeURL: URL?
    public let chatPrompt: String?
    public let conversationPrompt: String?
    public let paymentLink: URL?
    public let paymentPlan: String?
    public let isUserPaid: Bool
    public let isPrivate: Bool
    /// The user made this app (reviewing it is refused).
    public let isOwn: Bool

    public init(
        app: OmiApp, reviews: [AppReview] = [], userReview: AppReview? = nil, setupSteps: [SetupStep] = [],
        setupInstructionsURL: URL? = nil, setupInstructionsText: String? = nil, homeURL: URL? = nil,
        chatPrompt: String? = nil, conversationPrompt: String? = nil, paymentLink: URL? = nil, paymentPlan: String? = nil,
        isUserPaid: Bool = false, isPrivate: Bool = false, isOwn: Bool = false
    ) {
        self.app = app
        self.reviews = reviews
        self.userReview = userReview
        self.setupSteps = setupSteps
        self.setupInstructionsURL = setupInstructionsURL
        self.setupInstructionsText = setupInstructionsText
        self.homeURL = homeURL
        self.chatPrompt = chatPrompt
        self.conversationPrompt = conversationPrompt
        self.paymentLink = paymentLink
        self.paymentPlan = paymentPlan
        self.isUserPaid = isUserPaid
        self.isPrivate = isPrivate
        self.isOwn = isOwn
    }

    /// The user must pay before turning it on.
    public var needsPurchase: Bool {
        app.isPaid && !isUserPaid
    }

    /// Share link (Flutter `share_links.dart`); private apps have none.
    public var shareURL: URL? {
        isPrivate ? nil : URL(string: "https://h.omi.me/apps/\(app.id)")
    }

    static func from(_ object: [String: Any], uid: String?) -> AppDetail? {
        guard let app = OmiApp.from(object) else { return nil }
        let integration = object["external_integration"] as? [String: Any]
        let steps = (integration?["auth_steps"] as? [[String: Any]] ?? []).compactMap { step -> SetupStep? in
            guard let name = step["name"] as? String, let url = (step["url"] as? String).flatMap(URL.init(string:)) else { return nil }
            return SetupStep(name: name, url: url)
        }
        let instructions = (integration?["setup_instructions_file_path"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        let isURL = integration?["is_instructions_url"] as? Bool ?? instructions.map { $0.hasPrefix("http") } ?? false
        func text(_ key: String) -> String? {
            (object[key] as? String).flatMap { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $0 }
        }
        return AppDetail(
            app: app,
            reviews: (object["reviews"] as? [[String: Any]] ?? []).compactMap(AppReview.from).filter { !$0.text.isEmpty },
            userReview: (object["user_review"] as? [String: Any]).flatMap(AppReview.from),
            setupSteps: steps,
            setupInstructionsURL: isURL ? instructions.flatMap(URL.init(string:)) : nil,
            setupInstructionsText: isURL ? nil : instructions,
            homeURL: (integration?["app_home_url"] as? String).flatMap(URL.init(string:)),
            chatPrompt: text("chat_prompt"), conversationPrompt: text("memory_prompt"),
            paymentLink: (object["payment_link"] as? String).flatMap(URL.init(string:)),
            paymentPlan: text("payment_plan"),
            isUserPaid: object["is_user_paid"] as? Bool ?? false,
            isPrivate: object["private"] as? Bool ?? false,
            isOwn: uid != nil && object["uid"] as? String == uid
        )
    }
}

/// `GET v1/app-categories`.
public struct AppCategory: Identifiable, Hashable, Sendable {
    public let id: String
    public let title: String

    public init(id: String, title: String) {
        self.id = id
        self.title = title
    }
}

/// The browse list's search and filters (`GET v2/apps/search`).
public struct AppQuery: Hashable, Sendable {
    public enum Sort: String, CaseIterable, Sendable {
        case installs = "installs_desc"
        case rating = "rating_desc"
        case name = "name_asc"
    }

    public var text = ""
    public var category: String?
    /// `chat`, `memories`, `external_integration`, `proactive_notification`, `tasks`.
    public var capability: String?
    public var minimumRating: Double?
    public var sort: Sort = .installs

    public init(
        text: String = "", category: String? = nil, capability: String? = nil, minimumRating: Double? = nil, sort: Sort = .installs
    ) {
        self.text = text
        self.category = category
        self.capability = capability
        self.minimumRating = minimumRating
        self.sort = sort
    }
}

/// A paid app's subscription (`GET v1/apps/{id}/subscription`).
public struct AppSubscription: Hashable, Sendable {
    public let status: String
    public let cancelAtPeriodEnd: Bool
    public let periodEnd: Date?

    public init(status: String, cancelAtPeriodEnd: Bool, periodEnd: Date?) {
        self.status = status
        self.cancelAtPeriodEnd = cancelAtPeriodEnd
        self.periodEnd = periodEnd
    }

    /// Renews (Flutter `app_detail.dart`: active and not cancelling).
    public var isActive: Bool {
        status == "active" && !cancelAtPeriodEnd
    }
}

public extension APIClient {
    /// `GET v1/apps/{id}`: the app with its reviews, setup and payment state.
    func appDetail(id: String, uid: String?) async throws -> AppDetail {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/apps/\(id)")) as? [String: Any] ?? [:]
        guard let detail = AppDetail.from(object, uid: uid) else { throw APIError.decoding("app without id") }
        return detail
    }

    func appCategories() async throws -> [AppCategory] {
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v1/app-categories")) as? [[String: Any]] ?? []
        return array.compactMap { item in
            guard let id = item["id"] as? String else { return nil }
            return AppCategory(id: id, title: item["title"] as? String ?? id)
        }
    }

    /// `GET v2/apps/search` with filters and sort; `hasMore` from `pagination.hasNext`.
    func browseApps(_ query: AppQuery, offset: Int) async throws -> (apps: [OmiApp], hasMore: Bool) {
        var items = [
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "limit", value: "30"),
            URLQueryItem(name: "sort", value: query.sort.rawValue),
        ]
        let text = query.text.trimmingCharacters(in: .whitespaces)
        if !text.isEmpty { items.append(URLQueryItem(name: "q", value: text)) }
        if let category = query.category { items.append(URLQueryItem(name: "category", value: category)) }
        if let capability = query.capability { items.append(URLQueryItem(name: "capability", value: capability)) }
        if let rating = query.minimumRating { items.append(URLQueryItem(name: "rating", value: String(rating))) }
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v2/apps/search", query: items)) as? [String: Any]
        let apps = (object?["data"] as? [[String: Any]] ?? []).compactMap(OmiApp.from)
        let hasMore = (object?["pagination"] as? [String: Any])?["hasNext"] as? Bool ?? false
        return (apps, hasMore)
    }

    /// `POST v1/apps/review?app_id=` (first review) or `PATCH v1/apps/{id}/review` (changing it).
    func reviewApp(id: String, score: Int, text: String, updating: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["score": score, "review": text])
        if updating {
            _ = try await data(.patch, "v1/apps/\(id)/review", body: .json(body))
        } else {
            _ = try await data(.post, "v1/apps/review", query: [URLQueryItem(name: "app_id", value: id)], body: .json(body))
        }
    }

    func appSubscription(id: String) async throws -> AppSubscription? {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/apps/\(id)/subscription")) as? [String: Any]
        guard let subscription = object?["subscription"] as? [String: Any] else { return nil }
        let end = (subscription["current_period_end"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) }
        return AppSubscription(
            status: subscription["status"] as? String ?? "", cancelAtPeriodEnd: subscription["cancel_at_period_end"] as? Bool ?? false,
            periodEnd: end
        )
    }

    /// `DELETE v1/apps/{id}/subscription`: ends at the close of the paid period.
    func cancelAppSubscription(id: String) async throws {
        _ = try await data(.delete, "v1/apps/\(id)/subscription")
    }
}
