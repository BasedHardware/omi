import OmiDesign
import UserNotifications

/// Local notifications about the Omi wearable itself.
@MainActor
enum DeviceNotifications {
    /// Once per discharge (`LowBatteryAlert`); replaces an earlier one still on screen.
    static func lowBattery(_ level: Int, deviceName: String?) {
        let content = UNMutableNotificationContent()
        content.title = L("nativeOmiBatteryLowTitle", deviceName ?? "Omi")
        content.body = L("nativeOmiBatteryLowBody", String(level))
        content.sound = .default
        content.threadIdentifier = "omi.device"
        let request = UNNotificationRequest(identifier: "omi.device.lowBattery", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }

    /// The answer to a question asked with the Omi's button (it is in the chat too).
    static func answer(_ text: String) {
        let content = UNMutableNotificationContent()
        content.title = L("nativeAskOmiAnswerTitle")
        content.body = String(text.prefix(400))
        content.sound = .default
        content.threadIdentifier = "omi.device.ask"
        let request = UNNotificationRequest(identifier: "omi.device.ask.\(UUID().uuidString)", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
