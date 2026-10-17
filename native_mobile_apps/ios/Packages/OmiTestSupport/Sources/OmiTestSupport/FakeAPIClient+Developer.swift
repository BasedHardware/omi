import Foundation
import OmiCore
import OmiNetwork

/// Developer settings, the app store, chat apps and task app settings as the fake backend keeps them.
public final class FakeDevAppsBackend: @unchecked Sendable {
    let lock = NSLock()
    public var webhookURLs: [DeveloperWebhook: String] = [:]
    public var webhookEnabled: [DeveloperWebhook: Bool] = [:]
    public var keys: [DeveloperKey.Kind: [DeveloperKey]] = [:]
    public var log: [String] = []
    /// Thrown by the next write (then cleared).
    public var nextWriteError: APIError?
    public var details: [String: AppDetail] = [:]
    public var categories = [
        AppCategory(id: "productivity-and-organization", title: "Productivity"), AppCategory(id: "other", title: "Other"),
    ]
    public var browseQueries: [AppQuery] = []
    public var browsePages: [[OmiApp]] = []
    public var subscriptions: [String: AppSubscription] = [:]
    /// Chat sessions per app id.
    public var appSessions: [String: [(id: String, title: String)]] = [:]
    public var options: [TaskAppLevel: [String: [TaskAppOption]]] = [:]
    public var defaultTaskApp: String?
    public var singleLanguageMode = false
    /// The session of every history page and every send, in order.
    public var historySessions: [String?] = []
    public var sentSessions: [String?] = []

    init() {}

    func write(_ entry: String) throws {
        try lock.withLock {
            if let error = nextWriteError {
                nextWriteError = nil
                throw error
            }
            log.append(entry)
        }
    }
}

public extension FakeAPIClient {
    // MARK: Developer

    func webhookStatus() async throws -> [DeveloperWebhook: Bool] {
        devApps.lock.withLock { devApps.webhookEnabled }
    }

    func webhookURL(_ hook: DeveloperWebhook) async throws -> String {
        devApps.lock.withLock { devApps.webhookURLs[hook] ?? "" }
    }

    func setWebhookURL(_ hook: DeveloperWebhook, url: String) async throws {
        try devApps.write("url:\(hook.rawValue):\(url)")
        devApps.lock.withLock {
            devApps.webhookURLs[hook] = url
            devApps.webhookEnabled[hook] = !url.isEmpty
        }
    }

    func setWebhook(_ hook: DeveloperWebhook, enabled: Bool) async throws {
        try devApps.write("\(enabled ? "enable" : "disable"):\(hook.rawValue)")
        devApps.lock.withLock { devApps.webhookEnabled[hook] = enabled }
    }

    func developerKeys(_ kind: DeveloperKey.Kind) async throws -> [DeveloperKey] {
        devApps.lock.withLock { devApps.keys[kind] ?? [] }
    }

    func createDeveloperKey(_ kind: DeveloperKey.Kind, name: String, scopes: [String]?) async throws -> DeveloperKey {
        try devApps.write("create:\(kind.rawValue):\(name):\(scopes?.joined(separator: ",") ?? "-")")
        return devApps.lock.withLock {
            let id = "\(kind.rawValue)-\((devApps.keys[kind] ?? []).count + 1)"
            let key = DeveloperKey(
                id: id, name: name, prefix: "omi_\(kind.rawValue)_ab...cd", createdAt: Fixtures.now, lastUsedAt: nil,
                scopes: scopes ?? [], secret: nil
            )
            devApps.keys[kind, default: []].append(key)
            return DeveloperKey(
                id: id, name: name, prefix: key.prefix, createdAt: key.createdAt, lastUsedAt: nil, scopes: key.scopes,
                secret: "omi_\(kind.rawValue)_secret_\(id)"
            )
        }
    }

    func revokeDeveloperKey(_ kind: DeveloperKey.Kind, id: String) async throws {
        try devApps.write("revoke:\(kind.rawValue):\(id)")
        devApps.lock.withLock { devApps.keys[kind]?.removeAll { $0.id == id } }
    }

    // MARK: App store

    func appDetail(id: String, uid _: String?) async throws -> AppDetail {
        if let detail = devApps.lock.withLock({ devApps.details[id] }) { return detail }
        guard let app = apps.first(where: { $0.id == id }) else { throw APIError.http(status: 404, body: "") }
        return AppDetail(app: app)
    }

    func appCategories() async throws -> [AppCategory] {
        devApps.lock.withLock { devApps.categories }
    }

    func browseApps(_ query: AppQuery, offset: Int) async throws -> (apps: [OmiApp], hasMore: Bool) {
        let pages = devApps.lock.withLock {
            devApps.browseQueries.append(query)
            return devApps.browsePages
        }
        guard !pages.isEmpty else {
            let matching = apps.filter { query.text.isEmpty || $0.name.localizedCaseInsensitiveContains(query.text) }
            return (offset == 0 ? matching : [], false)
        }
        // Page n starts after the apps of pages 0 ..< n.
        var start = 0
        for (index, page) in pages.enumerated() {
            if start == offset { return (page, index < pages.count - 1) }
            start += page.count
        }
        return ([], false)
    }

    func reviewApp(id: String, score: Int, text: String, updating: Bool) async throws {
        try devApps.write("\(updating ? "update" : "review"):\(id):\(score):\(text)")
    }

    func appSubscription(id: String) async throws -> AppSubscription? {
        devApps.lock.withLock { devApps.subscriptions[id] }
    }

    func cancelAppSubscription(id: String) async throws {
        try devApps.write("cancel:\(id)")
        devApps.lock.withLock {
            if let current = devApps.subscriptions[id] {
                devApps.subscriptions[id] = AppSubscription(status: current.status, cancelAtPeriodEnd: true, periodEnd: current.periodEnd)
            }
        }
    }

    // MARK: Chat apps

    func chatSessions(appID: String) async throws -> [(id: String, title: String)] {
        devApps.lock.withLock { devApps.appSessions[appID] ?? [] }
    }

    func createChatSession(title: String, appID: String) async throws -> String {
        try devApps.write("session:\(appID)")
        return devApps.lock.withLock {
            let id = "app-session-\(appID)-\((devApps.appSessions[appID] ?? []).count + 1)"
            devApps.appSessions[appID, default: []].insert((id, title), at: 0)
            return id
        }
    }

    // MARK: Task app settings

    func taskAppOptions(_ level: TaskAppLevel, parent: String?) async throws -> [TaskAppOption] {
        devApps.lock.withLock { devApps.options[level]?[parent ?? ""] ?? [] }
    }

    func saveTaskAppSelection(_ app: String, selection: [TaskAppLevel: TaskAppOption?]) async throws {
        let fields = selection.sorted { $0.key.rawValue < $1.key.rawValue }.map { "\($0.key.rawValue)=\($0.value?.id ?? "nil")" }
        try devApps.write("select:\(app):\(fields.joined(separator: ","))")
    }

    func defaultTaskApp() async throws -> String? {
        devApps.lock.withLock { devApps.defaultTaskApp }
    }

    func setDefaultTaskApp(_ app: String) async throws {
        try devApps.write("default:\(app)")
        devApps.lock.withLock { devApps.defaultTaskApp = app }
    }

    // MARK: Transcription

    func singleLanguageMode() async throws -> Bool {
        devApps.lock.withLock { devApps.singleLanguageMode }
    }

    func setSingleLanguageMode(_ value: Bool) async throws {
        try devApps.write("singleLanguage:\(value)")
        devApps.lock.withLock { devApps.singleLanguageMode = value }
    }
}
