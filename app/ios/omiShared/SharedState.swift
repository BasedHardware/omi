// Created by Barrett Jacobsen

import Foundation
import WidgetKit

struct SharedState {
    static let suiteName = "group.com.omi.watchapp"

    private static var defaults: UserDefaults? {
        UserDefaults(suiteName: suiteName)
    }

    // MARK: - Watch Recording State

    static var isWatchRecording: Bool {
        get { defaults?.bool(forKey: "isWatchRecording") ?? false }
        set {
            defaults?.set(newValue, forKey: "isWatchRecording")
            defaults?.set(Date(), forKey: "lastUpdated")
            WidgetCenter.shared.reloadAllTimelines()
        }
    }

    // MARK: - Omi Device State (Omi hardware state, forwarded from iPhone via WatchConnectivity)

    static var isDeviceRecording: Bool {
        get { defaults?.bool(forKey: "isDeviceRecording") ?? false }
        set {
            defaults?.set(newValue, forKey: "isDeviceRecording")
            defaults?.set(Date(), forKey: "lastUpdated")
            WidgetCenter.shared.reloadAllTimelines()
        }
    }

    static var isDeviceConnected: Bool {
        get { defaults?.bool(forKey: "isDeviceConnected") ?? false }
        set {
            defaults?.set(newValue, forKey: "isDeviceConnected")
            defaults?.set(Date(), forKey: "lastUpdated")
            WidgetCenter.shared.reloadAllTimelines()
        }
    }

    static var deviceBatteryLevel: Float {
        get { defaults?.float(forKey: "deviceBatteryLevel") ?? -1 }
        set {
            defaults?.set(newValue, forKey: "deviceBatteryLevel")
            defaults?.set(Date(), forKey: "lastUpdated")
            WidgetCenter.shared.reloadAllTimelines()
        }
    }

    static func updateDeviceState(isRecording: Bool, isConnected: Bool, batteryLevel: Float) {
        defaults?.set(isRecording, forKey: "isDeviceRecording")
        defaults?.set(isConnected, forKey: "isDeviceConnected")
        defaults?.set(batteryLevel, forKey: "deviceBatteryLevel")
        defaults?.set(Date(), forKey: "lastUpdated")
        WidgetCenter.shared.reloadAllTimelines()
    }

    static var lastUpdated: Date {
        defaults?.object(forKey: "lastUpdated") as? Date ?? .distantPast
    }
}
