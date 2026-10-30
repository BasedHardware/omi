import Foundation

/// The App Group the app and its widget extension share. Its identifier comes from each bundle's
/// Info.plist (`OmiAppGroup` = `group.$(OMI_BUNDLE_ID)`), so Debug and Release builds keep apart.
public enum OmiAppGroup {
    public static let infoKey = "OmiAppGroup"

    public static var identifier: String? {
        (Bundle.main.object(forInfoDictionaryKey: infoKey) as? String).flatMap { $0.isEmpty ? nil : $0 }
    }

    /// Nil when the bundle declares no group (unit tests, a misconfigured target).
    public static var defaults: UserDefaults? {
        identifier.flatMap(UserDefaults.init(suiteName:))
    }
}

/// The widgets the extension offers; the app reloads one kind when its snapshot changes.
public enum WidgetKind: String, CaseIterable, Sendable {
    case battery = "OmiBatteryWidget"
    case upNext = "OmiUpNextWidget"
    case latest = "OmiLatestWidget"
}

/// The Omi as the battery widgets show it.
public struct DeviceSnapshot: Codable, Equatable, Sendable {
    public var name: String
    public var connected: Bool
    /// 0–100; nil until the Omi reported a level since it connected.
    public var battery: Int?

    public init(name: String, connected: Bool, battery: Int?) {
        self.name = name
        self.connected = connected
        self.battery = battery.map { min(100, max(0, $0)) }
    }
}

/// The next open tasks, as the Up next widget lists them.
public struct UpNextSnapshot: Codable, Equatable, Sendable {
    public struct Task: Codable, Equatable, Sendable, Identifiable {
        public let id: String
        public let title: String
        public let due: Date?

        public init(id: String, title: String, due: Date?) {
            self.id = id
            self.title = title
            self.due = due
        }
    }

    public var tasks: [Task]
    /// Every open task, not only the ones shown.
    public var open: Int

    public init(tasks: [Task], open: Int) {
        self.tasks = tasks
        self.open = open
    }
}

/// The newest conversation, for the Latest widget.
public struct LatestSnapshot: Codable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let at: Date
    public let taskCount: Int
    public let duration: TimeInterval?

    public init(id: String, title: String, at: Date, taskCount: Int, duration: TimeInterval?) {
        self.id = id
        self.title = title
        self.at = at
        self.taskCount = taskCount
        self.duration = duration
    }
}

/// JSON documents in the App Group's defaults: the app writes them, the widgets read them.
public struct SharedStore {
    public enum Key: String, CaseIterable, Sendable {
        case device = "omi.widget.device"
        case upNext = "omi.widget.upNext"
        case latest = "omi.widget.latest"

        public var widget: WidgetKind {
            switch self {
            case .device: .battery
            case .upNext: .upNext
            case .latest: .latest
            }
        }
    }

    private let defaults: UserDefaults

    public init(defaults: UserDefaults) {
        self.defaults = defaults
    }

    /// The shared store, or nil when the App Group is unavailable.
    public static var shared: SharedStore? {
        OmiAppGroup.defaults.map(SharedStore.init(defaults:))
    }

    /// Whether the app has published this document at least once (nil documents included).
    public func isKnown(_ key: Key) -> Bool {
        defaults.object(forKey: key.rawValue) != nil
    }

    public func read<Value: Decodable>(_: Value.Type, for key: Key) -> Value? {
        guard let data = defaults.data(forKey: key.rawValue), !data.isEmpty else { return nil }
        return try? Self.decoder.decode(Value.self, from: data)
    }

    /// Stores `value` (nil clears it but marks the key as published) and reports whether it changed,
    /// so the app reloads a widget only when what it shows is different.
    @discardableResult
    public func write(_ value: (some Encodable)?, for key: Key) -> Bool {
        let data = value.flatMap { try? Self.encoder.encode($0) } ?? Data()
        if defaults.data(forKey: key.rawValue) == data { return false }
        defaults.set(data, forKey: key.rawValue)
        return true
    }

    /// Signing out removes everything, so widgets show nothing of the previous account.
    public func clear() -> [WidgetKind] {
        Key.allCases.compactMap { key in
            guard defaults.object(forKey: key.rawValue) != nil else { return nil }
            defaults.removeObject(forKey: key.rawValue)
            return key.widget
        }
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        encoder.dateEncodingStrategy = .secondsSince1970
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .secondsSince1970
        return decoder
    }()
}

/// Picks what the Up next widget shows, as Flutter's `HomeWidgetsPayload.pickUpNext`: dated tasks
/// soonest first (overdue on top), then undated ones in the app's order.
public enum UpNextPicker {
    public struct Candidate: Sendable {
        public let id: String
        public let title: String
        public let due: Date?
        public let isOpen: Bool

        public init(id: String, title: String, due: Date?, isOpen: Bool) {
            self.id = id
            self.title = title
            self.due = due
            self.isOpen = isOpen
        }
    }

    public static func snapshot(_ candidates: [Candidate], limit: Int = 3) -> UpNextSnapshot {
        let open = candidates.filter { $0.isOpen && !$0.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        let dated = open.compactMap { task in task.due.map { (task, $0) } }.sorted { $0.1 < $1.1 }.map(\.0)
        let undated = open.filter { $0.due == nil }
        let shown = (dated + undated).prefix(limit).map {
            UpNextSnapshot.Task(id: $0.id, title: $0.title.trimmingCharacters(in: .whitespacesAndNewlines), due: $0.due)
        }
        return UpNextSnapshot(tasks: Array(shown), open: open.count)
    }
}
