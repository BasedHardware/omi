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
}

/// Model representing the device battery state shown in the widget.
struct DeviceBatteryInfo {
    let deviceName: String
    let batteryLevel: Int
    let deviceType: String
    let isConnected: Bool
    let lastUpdated: Date
    let isMuted: Bool

    /// Reads the latest device battery info from the shared App Group UserDefaults.
    static func fromSharedDefaults() -> DeviceBatteryInfo {
        let defaults = UserDefaults(suiteName: appGroupIdentifier)
        let name = defaults?.string(forKey: BatteryWidgetKeys.deviceName) ?? "Omi"
        let battery = defaults?.integer(forKey: BatteryWidgetKeys.batteryLevel) ?? -1
        let type = defaults?.string(forKey: BatteryWidgetKeys.deviceType) ?? "omi"
        let connected = defaults?.bool(forKey: BatteryWidgetKeys.isConnected) ?? false
        let updated = defaults?.object(forKey: BatteryWidgetKeys.lastUpdated) as? Date ?? Date.distantPast
        let muted = defaults?.bool(forKey: BatteryWidgetKeys.isMuted) ?? false
        return DeviceBatteryInfo(
            deviceName: name,
            batteryLevel: battery,
            deviceType: type,
            isConnected: connected,
            lastUpdated: updated,
            isMuted: muted
        )
    }
}
