import Foundation

/// Links that reach the app from iOS itself: universal links on Omi's share domain and the Home
/// Screen quick actions.
public extension DeepLink {
    /// Hosts in the app's associated domains (`applinks:` in `Omi.entitlements`).
    static let universalLinkHosts: Set<String> = ["h.omi.me", "try.omi.me"]

    /// From `https://h.omi.me/...`: the share pages Omi builds (`share_links.dart`) open the same
    /// thing in the app, as Flutter's `AppShell.openAppLink` does. Shared conversations and recaps
    /// open when the account can see them, `/apps/<id>` the app's page, `/tasks/<token>` the shared
    /// task list to add, `/unlimited` the plans. `/wrapped` (being retired) and anything else is nil:
    /// the app just opens.
    init?(universalLink url: URL) {
        guard ["https", "http"].contains(url.scheme?.lowercased() ?? ""),
              let host = url.host(percentEncoded: false)?.lowercased(), Self.universalLinkHosts.contains(host)
        else { return nil }
        let segments = url.pathComponents.filter { $0 != "/" }
        let id = segments.dropFirst().first.flatMap { $0.isEmpty ? nil : $0 }
        switch segments.first?.lowercased() {
        case "conversations", "conversation":
            guard let id else { return nil }
            self = .conversation(id: id)
        case "recaps", "daily-summary":
            guard let id else { return nil }
            self = .recap(id)
        case "memories":
            self = id.map { .memory(id: $0) } ?? .memories
        case "unlimited":
            self = .account
        case "apps":
            guard let id else { return nil }
            self = .app(id: id)
        case "tasks":
            guard let id else { return nil }
            self = .sharedTasks(token: id)
        default:
            return nil
        }
    }
}

/// The Home Screen quick actions (long press on the icon), as in Flutter's `quick_actions_service`.
/// The raw values are Flutter's shortcut types, so a shortcut iOS kept from the Flutter app still works.
public enum QuickAction: String, CaseIterable, Sendable {
    case askOmi = "ask_omi"
    case addTask = "add_task"
    case startRecording = "start_recording"
    case myOmi = "device_settings"

    /// Flutter's "Connect device" item opens the same place as "Device settings".
    public init?(shortcutType: String) {
        if shortcutType == "connect_device" {
            self = .myOmi
            return
        }
        self.init(rawValue: shortcutType)
    }

    /// Top to bottom in the menu.
    public static let menuOrder: [QuickAction] = [.addTask, .askOmi, .startRecording, .myOmi]

    public var link: DeepLink {
        switch self {
        case .askOmi: .chat
        case .addTask: .newTask
        case .startRecording: .record
        case .myOmi: .device
        }
    }

    public var systemImage: String {
        switch self {
        case .askOmi: "bubble.left.and.text.bubble.right"
        case .addTask: "checklist"
        case .startRecording: "waveform"
        case .myOmi: "dot.radiowaves.left.and.right"
        }
    }
}
