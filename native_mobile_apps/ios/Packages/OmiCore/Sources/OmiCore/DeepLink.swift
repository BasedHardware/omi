import Foundation

/// A place in the app a notification or an `omi://` link opens. Parsed from the backend's FCM data
/// (`navigate_to` routes such as `/conversation/<id>`, plus the typed payloads that carry no route)
/// and from `omi://conversation/<id>`, `omi://task/<id>`, `omi://recap/<id or yyyy-MM-dd>`, `omi://chat`,
/// plus task share links (`omi://tasks/<token>`, `https://h.omi.me/tasks/<token>`).
public enum DeepLink: Hashable, Sendable {
    case conversation(id: String)
    /// A task; when Omi worked on it, its run (Omi's finished work).
    case task(id: String)
    case tasks
    /// Tasks someone shared by link; opens the sheet to add them (Flutter `AcceptSharedTasksSheet`).
    case sharedTasks(token: String)
    /// A daily recap by summary id or local date (`yyyy-MM-dd`).
    case recap(String)
    case chat
    case memories
    case home
    /// My Devices (the backend's capture-recovery nudge).
    case device
    /// One memory (Siri, Spotlight): the Memories tab.
    case memory(id: String)
    /// A conversation folder: Home showing only that folder.
    case folder(id: String)
    /// The Tasks tab with a new task being written (the "Add task" quick action).
    case newTask
    /// Starts recording with the iPhone (the "Start recording" quick action).
    case record
    /// The chat with a question waiting in the composer (Siri could not answer it).
    case chatDraft(String)
    /// Settings › Account, where the plans are (`h.omi.me/unlimited`).
    case account
    /// One app's page (`h.omi.me/apps/<id>`, Flutter `AppDetailPage`).
    case app(id: String)

    /// The route form (`/task/<id>`) stored in local notifications so a tap parses like a push.
    public var route: String {
        switch self {
        case let .conversation(id): "/conversation/\(Self.encode(id))"
        case let .task(id): "/task/\(Self.encode(id))"
        case .tasks: "/action-items"
        case let .sharedTasks(token): "/tasks/\(Self.encode(token))"
        case let .recap(key): "/daily-summary/\(Self.encode(key))"
        case .chat: "/chat/omi"
        case .memories: "/memories"
        case .home: "/conversations"
        case .device: "/settings/device"
        case let .memory(id): "/memory/\(Self.encode(id))"
        case let .folder(id): "/folder/\(Self.encode(id))"
        case .newTask: "/tasks/new"
        case .record: "/record"
        case let .chatDraft(text): "/chat/omi?q=\(text.addingPercentEncoding(withAllowedCharacters: Self.unreserved) ?? "")"
        case .account: "/settings/account"
        case let .app(id): "/apps/\(Self.encode(id))"
        }
    }

    /// The `omi://` form (`omi://conversation/<id>`): Spotlight items and Siri routes carry it.
    public var url: URL {
        URL(string: "omi:/" + route) ?? URL(string: "omi://home")!
    }

    /// From a notification's `userInfo` (FCM data keys arrive at the top level), mirroring Flutter's
    /// `NotificationUtil.handleFcmDataTap` and `ProactivityPush`. Nil: just open the app.
    public init?(notification userInfo: [AnyHashable: Any]) {
        let value = { (key: String) -> String? in (userInfo[key] as? String).flatMap { $0.isEmpty ? nil : $0 } }
        // Proactivity v2 carries only identity; mentor items keep their chat route.
        if value("notification_type") == "proactivity_v2" {
            if value("navigate_to") == "/chat/mentor" { self = .chat; return }
            guard let target = value("target_id") else { return nil }
            switch value("target_kind") {
            case "conversation": self = .conversation(id: target)
            case "action_item": self = .task(id: target)
            default: return nil
            }
            return
        }
        if value("push_type") == "capture_recovery" {
            guard value("action") == "repair_device" else { return nil }
            self = .device
            return
        }
        if let route = value("navigate_to") {
            self.init(route: route)
            return
        }
        // Typed payloads without a route.
        if let id = value("merged_conversation_id") ?? value("conversation_id") {
            self = .conversation(id: id)
        } else if value("type")?.hasPrefix("action_item") == true, let id = value("action_item_id") {
            self = .task(id: id)
        } else {
            return nil
        }
    }

    /// From an `omi://` URL. OAuth callbacks (`omi://<key>/callback`) are not links.
    public init?(url: URL) {
        if ["https", "http"].contains(url.scheme?.lowercased() ?? ""), url.host()?.lowercased() == "h.omi.me" {
            let segments = url.pathComponents.filter { $0 != "/" }
            guard segments.count == 2, segments[0] == "tasks", !segments[1].isEmpty else { return nil }
            self = .sharedTasks(token: segments[1])
            return
        }
        guard url.scheme?.lowercased() == "omi" else { return nil }
        var segments = url.pathComponents.filter { $0 != "/" }
        if let host = url.host(percentEncoded: false), !host.isEmpty { segments.insert(host, at: 0) }
        guard segments.last != "callback" else { return nil }
        self.init(segments: segments, query: URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
    }

    /// From a backend route (`/conversation/abc?share=1`, `/daily-summary/<id>`, `/chat/<app>`, `/facts`).
    public init?(route: String) {
        let path = route.hasPrefix("/") ? route : "/" + route
        guard let components = URLComponents(string: path) else { return nil }
        let segments = components.percentEncodedPath.split(separator: "/").map { String($0).removingPercentEncoding ?? String($0) }
        self.init(segments: segments, query: components.queryItems)
    }

    private init?(segments: [String], query: [URLQueryItem]? = nil) {
        guard let alias = segments.first?.lowercased() else { return nil }
        let id = segments.dropFirst().first.flatMap { $0.isEmpty ? nil : $0 }
        switch alias {
        case "conversation":
            guard let id else { return nil }
            self = .conversation(id: id)
        case "conversations", "home":
            self = .home
        case "task":
            guard let id else { return nil }
            self = .task(id: id)
        case "tasks":
            if id == "new" {
                self = .newTask
            } else {
                self = id.map { .sharedTasks(token: $0) } ?? .tasks
            }
        case "action-items":
            self = id == "new" ? .newTask : .tasks
        case "daily-summary", "recap":
            guard let id else { return nil }
            self = .recap(id)
        case "chat":
            let draft = query?.first { $0.name == "q" }?.value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            self = draft.isEmpty ? .chat : .chatDraft(draft)
        case "memory":
            self = id.map { .memory(id: $0) } ?? .memories
        case "facts", "memories":
            self = .memories
        case "folder":
            guard let id else { return nil }
            self = .folder(id: id)
        case "record":
            self = .record
        case "device":
            self = .device
        case "settings":
            switch id {
            case "device": self = .device
            case "account": self = .account
            default: return nil
            }
        case "apps", "app":
            guard let id else { return nil }
            self = .app(id: id)
        default:
            // `/wrapped/2025` (Wrapped is going away) and anything unknown: the app just opens.
            return nil
        }
    }

    /// RFC 3986 unreserved characters: everything else in a query value is percent-encoded.
    private static let unreserved = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")

    private static func encode(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }
}

/// What a background action-item push asks for: the backend schedules task reminders through
/// data-only messages (`action_item_reminder` / `_update` / `_delete` / `_batch_delete`), as in
/// Flutter's `ActionItemNotificationHandler`. The reminder fires an hour before the due time.
public enum TaskReminderChange: Equatable, Sendable {
    case schedule(taskID: String, description: String, fireAt: Date)
    case cancel(taskIDs: [String])

    public static let lead: TimeInterval = 60 * 60

    /// Nil for any other payload. A reminder whose time has passed only cancels the old one.
    public init?(notification userInfo: [AnyHashable: Any], now: Date = .now) {
        let value = { (key: String) -> String? in (userInfo[key] as? String).flatMap { $0.isEmpty ? nil : $0 } }
        switch value("type") {
        case "action_item_reminder", "action_item_update":
            guard let id = value("action_item_id") else { return nil }
            guard let description = value("description"), let due = BackendDate.parse(value("due_at")),
                  due.addingTimeInterval(-Self.lead) > now
            else {
                self = .cancel(taskIDs: [id])
                return
            }
            self = .schedule(taskID: id, description: description, fireAt: due.addingTimeInterval(-Self.lead))
        case "action_item_delete":
            guard let id = value("action_item_id") else { return nil }
            self = .cancel(taskIDs: [id])
        case "action_item_batch_delete":
            let ids = (value("ids") ?? "").split(separator: ",").map(String.init).filter { !$0.isEmpty }
            guard !ids.isEmpty else { return nil }
            self = .cancel(taskIDs: ids)
        default:
            return nil
        }
    }
}
