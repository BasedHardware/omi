import Foundation
import UserNotifications

class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationService()

    /// Per-assistant cooldown tracking
    private var lastNotificationTimes: [String: Date] = [:]

    /// Get cooldown seconds for a specific assistant
    private func cooldownSeconds(for assistantId: String) -> TimeInterval {
        switch assistantId {
        case "focus":
            return FocusAssistantSettings.shared.cooldownIntervalSeconds
        default:
            // Task assistant uses extraction interval instead of notification cooldown
            return AssistantSettings.shared.cooldownIntervalSeconds
        }
    }

    private override init() {
        super.init()
        // Set ourselves as the delegate to show notifications even when app is in foreground
        UNUserNotificationCenter.current().delegate = self
    }

    // MARK: - UNUserNotificationCenterDelegate

    // This allows notifications to be displayed even when the app is in the foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Show banner, play sound, and update badge even when app is frontmost
        completionHandler([.banner, .sound, .badge])
    }

    // Handle notification tap
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        completionHandler()
    }

    @discardableResult
    func sendNotification(title: String, message: String, assistantId: String = "default", applyCooldown: Bool = true) -> Bool {
        if applyCooldown {
            let lastTime = lastNotificationTimes[assistantId] ?? .distantPast
            let timeSinceLast = Date().timeIntervalSince(lastTime)
            let cooldown = cooldownSeconds(for: assistantId)

            if timeSinceLast < cooldown {
                let remaining = cooldown - timeSinceLast
                log("[\(assistantId)] Notification in cooldown (\(String(format: "%.1f", remaining))s remaining), skipping: \(message)")
                return false
            }
            lastNotificationTimes[assistantId] = Date()
        }

        let content = UNMutableNotificationContent()
        content.title = "OMI"
        content.subtitle = title
        content.body = message
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil // Deliver immediately
        )

        print("[\(assistantId)] Sending notification: \(title) - \(message)")
        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("Notification error: \(error)")
                log("Notification error: \(error)")
            } else {
                print("Notification sent successfully")
            }
        }
        return true
    }
}
