import Foundation

/// App Group identifier shared between the main app and the widget extension.
let appGroupIdentifier = "group.com.friend-app-with-wearable.ios12"

/// Keys used to store device battery data in the shared UserDefaults.
enum BatteryWidgetKeys {
    static let deviceName = "widget_device_name"
    static let batteryLevel = "widget_battery_level"
    static let deviceType = "widget_device_type"
    static let isConnected = "widget_is_connected"
    static let lastUpdated = "widget_last_updated"
    static let isMuted = "widget_is_muted"
    static let isCharging = "widget_is_charging"
}

/// Model representing the device battery state shown in the widget.
struct DeviceBatteryInfo {
    let deviceName: String
    let batteryLevel: Int
    let deviceType: String
    let isConnected: Bool
    let lastUpdated: Date
    let isMuted: Bool
    var isCharging: Bool = false

    /// Reads the latest device battery info from the shared App Group UserDefaults.
    static func fromSharedDefaults() -> DeviceBatteryInfo {
        let defaults = UserDefaults(suiteName: appGroupIdentifier)
        let name = defaults?.string(forKey: BatteryWidgetKeys.deviceName) ?? "Omi"
        let battery = defaults?.integer(forKey: BatteryWidgetKeys.batteryLevel) ?? -1
        let type = defaults?.string(forKey: BatteryWidgetKeys.deviceType) ?? "omi"
        let connected = defaults?.bool(forKey: BatteryWidgetKeys.isConnected) ?? false
        let updated = defaults?.object(forKey: BatteryWidgetKeys.lastUpdated) as? Date ?? Date.distantPast
        let muted = defaults?.bool(forKey: BatteryWidgetKeys.isMuted) ?? false
        let charging = defaults?.bool(forKey: BatteryWidgetKeys.isCharging) ?? false
        return DeviceBatteryInfo(
            deviceName: name,
            batteryLevel: battery,
            deviceType: type,
            isConnected: connected,
            lastUpdated: updated,
            isMuted: muted,
            isCharging: charging
        )
    }
}

// MARK: - Home Screen widgets (Devices, Up next, Latest)

/// Keys the app writes for the Home Screen widgets: JSON documents published by Omi (see
/// `lib/services/home_widgets_service.dart`), and the device the Devices widget is showing.
enum HomeWidgetKeys {
    static let devices = "widget_devices"
    static let selectedDevice = "widget_devices_selected"
    static let upNext = "widget_up_next"
    static let latest = "widget_latest"
}

/// A wearable the reader has paired, as the Devices widget shows it. The phone is never one.
struct WidgetDevice: Codable, Hashable {
    let id: String
    let name: String
    /// "pendant" draws the Omi orb; anything else names a picture in the widget's assets.
    let image: String
    let connected: Bool
    /// 0–100, or -1 when unknown.
    let battery: Int
    let charging: Bool
}

struct WidgetDevices: Codable {
    let devices: [WidgetDevice]
}

/// An open task on the Up next widget. [due] is seconds since 1970, nil for a task with no date.
struct UpNextTask: Codable, Hashable {
    let id: String
    let title: String
    let due: Double?

    var dueDate: Date? { due.map { Date(timeIntervalSince1970: $0) } }
}

struct UpNextData: Codable {
    let tasks: [UpNextTask]
    /// All open tasks, not only the ones shown.
    let open: Int
}

/// The newest conversation, for the Latest widget. [detail] is the app's own "1 task · 14 s".
struct LatestConversation: Codable {
    let id: String
    let title: String
    let at: Double
    let detail: String

    var date: Date { Date(timeIntervalSince1970: at) }
}

enum SharedWidgetStore {
    static var defaults: UserDefaults? { UserDefaults(suiteName: appGroupIdentifier) }

    /// A JSON document the app published, or nil before the app has published one.
    static func read<T: Decodable>(_ type: T.Type, key: String) -> T? {
        guard let text = defaults?.string(forKey: key), let data = text.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    /// The wearables to show, the connected one first; falls back to the single device the battery
    /// keys describe until the app publishes the list.
    static func devices() -> [WidgetDevice] {
        if let list = read(WidgetDevices.self, key: HomeWidgetKeys.devices), !list.devices.isEmpty {
            return list.devices
        }
        let info = DeviceBatteryInfo.fromSharedDefaults()
        guard info.isConnected || info.lastUpdated != Date.distantPast else { return [] }
        return [WidgetDevice(id: "", name: info.deviceName, image: "pendant", connected: info.isConnected,
                             battery: info.batteryLevel, charging: info.isCharging)]
    }

    /// The device the reader last switched to, else the connected one, else the first.
    static func selectedDevice(in devices: [WidgetDevice]) -> Int {
        guard !devices.isEmpty else { return 0 }
        if let id = defaults?.string(forKey: HomeWidgetKeys.selectedDevice),
           let index = devices.firstIndex(where: { $0.id == id }) {
            return index
        }
        return devices.firstIndex(where: { $0.connected }) ?? 0
    }
}
