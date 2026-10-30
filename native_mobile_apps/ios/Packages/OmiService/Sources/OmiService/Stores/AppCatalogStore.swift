import Foundation
import Observation
import OmiNetwork

/// The app store (Flutter `pages/apps/**`): browse with category, kind and sort, an app's page with
/// setup, reviews and payment. Turning apps on and off stays in `CapabilitiesStore`.
@MainActor
@Observable
public final class AppCatalogStore {
    public var query = AppQuery()
    public private(set) var results: [OmiApp] = []
    public private(set) var hasMore = false
    public private(set) var isLoading = false
    /// The last first-page search failed (offline, server error); the browse screen offers Try again.
    public private(set) var searchFailed = false
    public private(set) var categories: [AppCategory] = []
    public private(set) var details: [String: AppDetail] = [:]
    public private(set) var subscriptions: [String: AppSubscription] = [:]
    /// Apps whose purchase is being waited for (the payment page is open).
    public private(set) var awaitingPurchase: Set<String> = []
    public internal(set) var lastError: String?

    /// The kinds of app the browse list filters by (backend capability ids).
    public static let capabilities = ["chat", "memories", "external_integration", "proactive_notification", "tasks"]

    let api: any APIClientProtocol
    private let capabilities: CapabilitiesStore
    private let userID: () -> String?
    private let purchasePoll: Duration
    @ObservationIgnored private var searchGeneration = 0

    public init(
        api: any APIClientProtocol, capabilities: CapabilitiesStore, userID: @escaping () -> String?,
        purchasePoll: Duration = .seconds(5)
    ) {
        self.api = api
        self.capabilities = capabilities
        self.userID = userID
        self.purchasePoll = purchasePoll
    }

    public func loadCategories() async {
        guard categories.isEmpty else { return }
        categories = await (try? api.appCategories()) ?? []
    }

    /// The first page for `query`; an older search finishing late never overwrites a newer one.
    public func search() async {
        searchGeneration += 1
        let generation = searchGeneration
        isLoading = true
        defer { if generation == searchGeneration { isLoading = false } }
        let page: (apps: [OmiApp], hasMore: Bool)
        do {
            page = try await api.browseApps(query, offset: 0)
        } catch {
            if generation == searchGeneration { searchFailed = true }
            return
        }
        guard generation == searchGeneration else { return }
        searchFailed = false
        results = page.apps
        hasMore = page.hasMore
    }

    public func loadMore() async {
        guard hasMore, !isLoading else { return }
        let generation = searchGeneration
        isLoading = true
        defer { isLoading = false }
        guard let page = try? await api.browseApps(query, offset: results.count), generation == searchGeneration else { return }
        let known = Set(results.map(\.id))
        results += page.apps.filter { !known.contains($0.id) }
        hasMore = page.hasMore
    }

    // MARK: One app

    public func loadDetail(_ id: String) async {
        do {
            let detail = try await api.appDetail(id: id, uid: userID())
            details[id] = detail
            if detail.app.isPaid { subscriptions[id] = try? await api.appSubscription(id: id) }
            replace(detail.app)
        } catch {
            lastError = String(describing: error)
        }
    }

    /// Turns the app on or off; returns the backend's reason when it refuses (setup not finished,
    /// payment required …).
    public func setEnabled(_ app: OmiApp, _ enabled: Bool) async -> String? {
        lastError = nil
        do {
            try await api.setApp(app.id, enabled: enabled)
        } catch let APIError.http(_, body) {
            return Self.detail(from: body) ?? L10nFallback.couldNotChange
        } catch {
            return L10nFallback.couldNotChange
        }
        var updated = details[app.id]?.app ?? app
        updated.isEnabled = enabled
        details[app.id]?.app = updated
        replace(updated)
        await capabilities.loadApps()
        return nil
    }

    /// Writes (or changes) the user's own rating; the page reloads to show it.
    @discardableResult
    public func review(_ id: String, score: Int, text: String) async -> Bool {
        let updating = details[id]?.userReview != nil
        do {
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            try await api.reviewApp(id: id, score: min(5, max(1, score)), text: trimmed, updating: updating)
        } catch {
            lastError = String(describing: error)
            return false
        }
        await loadDetail(id)
        return true
    }

    /// After the payment page opened: checks every few seconds (for up to five minutes, like
    /// Flutter) until the backend reports the app paid, then turns it on.
    public func awaitPurchase(_ id: String, attempts: Int = 60) async {
        guard !awaitingPurchase.contains(id) else { return }
        awaitingPurchase.insert(id)
        defer { awaitingPurchase.remove(id) }
        for _ in 0 ..< attempts {
            try? await Task.sleep(for: purchasePoll)
            guard !Task.isCancelled else { return }
            await loadDetail(id)
            if let detail = details[id], detail.isUserPaid {
                if !detail.app.isEnabled { _ = await setEnabled(detail.app, true) }
                return
            }
        }
    }

    /// Cancels at the end of the paid period.
    @discardableResult
    public func cancelSubscription(_ id: String) async -> Bool {
        do {
            try await api.cancelAppSubscription(id: id)
        } catch {
            lastError = String(describing: error)
            return false
        }
        subscriptions[id] = try? await api.appSubscription(id: id)
        return true
    }

    /// A setup link with the user's id (Flutter sets `uid=` on auth steps and the setup check).
    public func signedSetupURL(_ url: URL) -> URL {
        guard let uid = userID(), var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return url }
        var items = (components.queryItems ?? []).filter { $0.name != "uid" }
        items.append(URLQueryItem(name: "uid", value: uid))
        components.queryItems = items
        return components.url ?? url
    }

    private func replace(_ app: OmiApp) {
        if let index = results.firstIndex(where: { $0.id == app.id }) { results[index] = app }
    }

    static func detail(from body: String) -> String? {
        guard let data = body.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return object["detail"] as? String
    }
}

/// Used when the backend gives no reason; the screen words it.
public enum L10nFallback {
    public static let couldNotChange = "could_not_change"
}
