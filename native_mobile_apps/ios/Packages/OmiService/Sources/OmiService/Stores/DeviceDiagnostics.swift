import Foundation
import Observation
import OmiDevice
import OmiPersistence

/// One link event of the Omi, as My Devices › Diagnostics lists it (Flutter `BleDisconnectEvent`).
public struct DiagnosticsEvent: Codable, Equatable, Sendable {
    public enum Kind: String, Codable, Sendable {
        /// The link was up and dropped.
        case disconnect
        /// A connect attempt that never established (`fail_to_connect` in Flutter's bundle).
        case failedConnect = "fail_to_connect"
    }

    public var kind: Kind
    public var at: Date
    /// CoreBluetooth's wording, when it gave one.
    public var reason: String?
    /// The app let go itself (firmware update, Bluetooth off, forget): not a drop.
    public var manual: Bool
    /// How long the link had been up (disconnects).
    public var connectedFor: TimeInterval?
    /// Until the Omi was back; nil while it is still away, and for failed connects.
    public var reconnectedAfter: TimeInterval?
    /// The last signal strength read before it happened.
    public var lastRSSI: Int?

    public init(
        kind: Kind, at: Date, reason: String? = nil, manual: Bool = false, connectedFor: TimeInterval? = nil,
        reconnectedAfter: TimeInterval? = nil, lastRSSI: Int? = nil
    ) {
        self.kind = kind
        self.at = at
        self.reason = reason
        self.manual = manual
        self.connectedFor = connectedFor
        self.reconnectedAfter = reconnectedAfter
        self.lastRSSI = lastRSSI
    }
}

public struct BatteryReading: Codable, Equatable, Sendable {
    public var at: Date
    public var level: Int
    public var charging: Bool?
}

public struct SignalReading: Equatable, Sendable {
    public var at: Date
    public var rssi: Int
}

/// Signal bands of the diagnostics page (Flutter `diagnosticsSignalFor`).
public enum SignalQuality: Sendable {
    case excellent, good, fair, weak

    public init(rssi: Int) {
        if rssi >= -60 {
            self = .excellent
        } else if rssi >= -75 {
            self = .good
        } else if rssi >= -85 {
            self = .fair
        } else {
            self = .weak
        }
    }
}

/// The "Last 7 days" numbers and verdict (Flutter `summarizeDiagnostics`).
public struct DiagnosticsSummary: Equatable, Sendable {
    /// Drops that came back on their own.
    public var drops: Int
    public var failed: Int
    public var failedLast24h: Int
    public var medianReconnect: TimeInterval?
    public var longestGap: TimeInterval?
    /// Average drops an hour, rounded; nil under an hour of history or when it rounds to zero.
    public var dropsPerHour: Int?

    /// Long gaps are fine (the Omi keeps recording and syncs later); only recent failed connects are trouble.
    public var hasTrouble: Bool {
        failedLast24h > 0
    }

    public static func make(_ events: [DiagnosticsEvent], now: Date, since: Date) -> DiagnosticsSummary {
        let start = max(since, now.addingTimeInterval(-DeviceDiagnosticsLog.retention))
        let window = events.filter { $0.at >= start }
        let gaps = window.compactMap { $0.kind == .disconnect && !$0.manual ? $0.reconnectedAfter : nil }.sorted()
        var median: TimeInterval?
        if !gaps.isEmpty {
            let mid = gaps.count / 2
            median = gaps.count.isMultiple(of: 2) ? (gaps[mid - 1] + gaps[mid]) / 2 : gaps[mid]
        }
        let hours = now.timeIntervalSince(start) / 3600
        let perHour = hours >= 1 && !gaps.isEmpty ? Int((Double(gaps.count) / hours).rounded()) : 0
        let failed = window.filter { $0.kind == .failedConnect }
        return DiagnosticsSummary(
            drops: gaps.count,
            failed: failed.count,
            failedLast24h: failed.filter { $0.at >= now.addingTimeInterval(-24 * 3600) }.count,
            medianReconnect: median,
            longestGap: gaps.last,
            dropsPerHour: perHour > 0 ? perHour : nil
        )
    }
}

/// What the Omi's link did lately: drops, failed connects, battery and signal. Flutter reads these
/// from its native BLE layer; here `DeviceStore` records them as events arrive. Kept for 7 days
/// (signal only while the app runs), cleared when the Omi is forgotten.
@MainActor
@Observable
public final class DeviceDiagnosticsLog {
    public private(set) var connectedAt: Date?
    public private(set) var events: [DiagnosticsEvent] = []
    public private(set) var battery: [BatteryReading] = []
    public private(set) var signal: [SignalReading] = []
    /// When counting started (first record after pairing).
    public private(set) var since: Date

    nonisolated static let retention: TimeInterval = 7 * 24 * 3600
    static let maxEvents = 300
    static let maxSignal = 120
    /// One battery reading a quarter hour unless the level or charging changes.
    static let batteryEvery: TimeInterval = 15 * 60

    private let preferences: Preferences
    private let now: () -> Date

    private struct Stored: Codable {
        var since: Date
        var events: [DiagnosticsEvent]
        var battery: [BatteryReading]
    }

    public init(preferences: Preferences, now: @escaping () -> Date = Date.init) {
        self.preferences = preferences
        self.now = now
        let stored = preferences.string(.deviceDiagnostics)
            .flatMap { try? JSONDecoder().decode(Stored.self, from: Data($0.utf8)) }
        since = stored?.since ?? now()
        events = stored?.events ?? []
        battery = stored?.battery ?? []
        prune()
    }

    public var summary: DiagnosticsSummary {
        DiagnosticsSummary.make(events, now: now(), since: since)
    }

    /// The disconnects and failed connects worth showing, newest first.
    public var recent: [DiagnosticsEvent] {
        Array(events.reversed().prefix(20))
    }

    public var latestSignal: Int? {
        signal.last?.rssi
    }

    func connected() {
        let date = now()
        connectedAt = date
        if let index = events.lastIndex(where: { $0.kind == .disconnect }), events[index].reconnectedAfter == nil,
           !events[index].manual
        {
            events[index].reconnectedAfter = date.timeIntervalSince(events[index].at)
        }
        save()
    }

    /// - Parameter wasConnected: false when the attempt itself failed.
    func disconnected(reason: String?, wasConnected: Bool, manual: Bool = false) {
        let date = now()
        if wasConnected {
            events.append(DiagnosticsEvent(
                kind: .disconnect, at: date, reason: reason, manual: manual,
                connectedFor: connectedAt.map { date.timeIntervalSince($0) }, lastRSSI: latestSignal
            ))
        } else {
            events.append(DiagnosticsEvent(kind: .failedConnect, at: date, reason: reason, manual: manual, lastRSSI: latestSignal))
        }
        connectedAt = nil
        prune()
        save()
    }

    func batteryRead(_ level: Int, charging: Bool?) {
        let date = now()
        if let last = battery.last, last.level == level, last.charging == charging,
           date.timeIntervalSince(last.at) < Self.batteryEvery { return }
        battery.append(BatteryReading(at: date, level: level, charging: charging))
        prune()
        save()
    }

    func signalRead(_ rssi: Int) {
        signal.append(SignalReading(at: now(), rssi: rssi))
        if signal.count > Self.maxSignal { signal.removeFirst(signal.count - Self.maxSignal) }
    }

    /// Forgetting the Omi starts the history over.
    func reset() {
        events = []
        battery = []
        signal = []
        connectedAt = nil
        since = now()
        preferences.set(nil as String?, for: .deviceDiagnostics)
    }

    private func prune() {
        let cutoff = now().addingTimeInterval(-Self.retention)
        events.removeAll { $0.at < cutoff }
        if events.count > Self.maxEvents { events.removeFirst(events.count - Self.maxEvents) }
        battery.removeAll { $0.at < cutoff }
    }

    private func save() {
        let stored = Stored(since: since, events: events, battery: battery)
        preferences.set((try? JSONEncoder().encode(stored)).flatMap { String(data: $0, encoding: .utf8) }, for: .deviceDiagnostics)
    }
}

// MARK: Support bundle

public extension DeviceDiagnosticsLog {
    /// What the phone and app are, for the bundle.
    struct Environment: Sendable {
        public var appVersion: String
        public var appBuild: String
        public var osVersion: String
        public var phoneModel: String

        public init(appVersion: String, appBuild: String, osVersion: String, phoneModel: String) {
            self.appVersion = appVersion
            self.appBuild = appBuild
            self.osVersion = osVersion
            self.phoneModel = phoneModel
        }
    }

    /// The JSON Flutter's "Share" and "Send to support" produce (schema 2, the backend checks it).
    /// Firmware diagnostics and BLE logs come from Flutter's native layer and stay empty here.
    func bundle(device: PairedDevice?, battery level: Int?, charging: Bool?, environment: Environment) -> Data {
        let date = now()
        let milliseconds = { (date: Date) in Int((date.timeIntervalSince1970 * 1000).rounded()) }
        let windowStart = max(since, date.addingTimeInterval(-Self.retention))
        let window = events.filter { $0.at >= windowStart }
        let sinceMS = milliseconds(since)
        var object: [String: Any] = [
            "schema_version": 2,
            "device_id": device?.id ?? "",
            "exported_at": ISO8601DateFormatter().string(from: date),
            "app_version": environment.appVersion,
            "app_build": environment.appBuild,
            "platform": "ios",
            "os_version": environment.osVersion,
            "phone_model": environment.phoneModel,
            "timezone_offset_minutes": TimeZone.current.secondsFromGMT(for: date) / 60,
            "connected_at": connectedAt.map(milliseconds) ?? 0,
            "reconnection_count": events.filter { $0.kind == .disconnect && $0.reconnectedAfter != nil }.count,
            "fail_to_connect_count": events.filter { $0.kind == .failedConnect }.count,
            "counters_since": ["reconnection_count": sinceMS, "fail_to_connect_count": sinceMS],
            "reconnection_count_window": window.filter { $0.kind == .disconnect && ($0.reconnectedAfter ?? 0) > 0 }.count,
            "fail_to_connect_count_window": window.filter { $0.kind == .failedConnect }.count,
            "rssi_samples": signal.map { ["ts": milliseconds($0.at), "rssi": $0.rssi] },
            "battery_history": battery.map { reading -> [String: Any] in
                var entry: [String: Any] = ["ts": milliseconds(reading.at), "level": reading.level]
                entry["charging"] = reading.charging ?? NSNull()
                return entry
            },
            "disconnect_history": events.map { event -> [String: Any] in
                [
                    "ts": milliseconds(event.at),
                    "reason": event.reason ?? NSNull(),
                    "code": NSNull(),
                    "manual": event.manual,
                    "event_type": event.kind.rawValue,
                    "last_rssi": event.lastRSSI ?? NSNull(),
                    "connection_duration_ms": event.connectedFor.map { Int($0 * 1000) } ?? NSNull(),
                    "time_to_reconnect_ms": event.reconnectedAfter.map { Int($0 * 1000) } ?? 0,
                ]
            },
            "firmware_diagnostics": [Any](),
            "lifecycle_events": [Any](),
            "ble_log": [Any](),
        ]
        object["device_model"] = device?.modelNumber ?? NSNull()
        object["hardware_revision"] = device?.hardwareRevision ?? NSNull()
        object["firmware"] = device?.firmwareRevision ?? NSNull()
        object["battery"] = level ?? NSNull()
        object["charging"] = charging ?? NSNull()
        return (try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])) ?? Data()
    }
}
