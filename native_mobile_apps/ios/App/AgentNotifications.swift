import OmiCore
import OmiDesign
import UIKit
import UserNotifications

/// Tells the user when a hand-over ends while Omi is not on screen.
@MainActor
enum AgentNotifications {
    static func runEnded(_ task: ActionItem, finished: Bool) {
        guard UIApplication.shared.applicationState != .active else { return }
        let content = UNMutableNotificationContent()
        content.title = finished ? L("nativeOmiFinished") : L("nativeOmiCouldNotFinish")
        content.body = task.description
        content.sound = .default
        content.threadIdentifier = "omi.agent"
        // A tap opens the task's run (`DeepLinkRouter`).
        content.userInfo = ["navigate_to": DeepLink.task(id: task.id).route]
        let request = UNNotificationRequest(identifier: "omi.agent.\(task.id)", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(request)
    }
}
