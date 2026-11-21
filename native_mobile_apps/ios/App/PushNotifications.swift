import CryptoKit
@preconcurrency import FirebaseCore
@preconcurrency import FirebaseMessaging
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import os
import UIKit
import UserNotifications

/// APNs registration. Firebase's app-delegate swizzling is off (`FirebaseAppDelegateProxyEnabled`),
/// so the APNs token and background pushes are handed over here.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions _: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // No prompt: the token comes without permission; alerts show once onboarding's
        // Permissions step (or iOS Settings) allows them.
        application.registerForRemoteNotifications()
        return true
    }

    func application(_: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Messaging.messaging().apnsToken = deviceToken
        SupportChat.registerPushToken(deviceToken)
    }

    func application(_: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: any Error) {
        PushNotifications.log.error("APNs registration failed: \(error.localizedDescription, privacy: .public)")
    }

    /// Data-only pushes (task reminder scheduling) arrive here, in the foreground and the background.
    func application(_: UIApplication, didReceiveRemoteNotification userInfo: [AnyHashable: Any]) async -> UIBackgroundFetchResult {
        Messaging.messaging().appDidReceiveMessage(userInfo)
        guard let change = TaskReminderChange(notification: userInfo) else { return .noData }
        await TaskReminders.apply(change)
        return .newData
    }
}

/// Push for the signed-in user: the FCM token goes to `POST v1/users/fcm-token` after sign-in and
/// on every refresh; banners show in the foreground; a tap opens its `DeepLink`.
@MainActor
final class PushNotifications: NSObject {
    nonisolated static let log = Logger(subsystem: "omi", category: "push")

    private let api: any APIClientProtocol
    private let router: DeepLinkRouter
    private var token: String?
    private var userID: String?
    /// `uid|token` last stored by the backend (once per launch, as Flutter does).
    private var uploaded: String?

    init(api: any APIClientProtocol, router: DeepLinkRouter) {
        self.api = api
        self.router = router
        super.init()
        // Set before launch finishes, so the tap that launched the app is delivered too.
        UNUserNotificationCenter.current().delegate = self
        // The local harness's Firebase project (`demo-…`) has no messaging backend.
        guard FirebaseApp.app()?.options.projectID?.hasPrefix("demo-") == false else { return }
        Messaging.messaging().delegate = self
        Messaging.messaging().isAutoInitEnabled = true
    }

    func sessionChanged(_ phase: SessionStore.Phase) {
        switch phase {
        case let .consent(id), let .onboarding(id), let .ready(id): userID = id
        case .launching, .signedOut: userID = nil
        }
        upload()
    }

    fileprivate func tokenChanged(_ token: String?) {
        self.token = token
        upload()
    }

    fileprivate func open(_ link: DeepLink?) {
        router.open(link)
    }

    private func upload() {
        guard let userID, let token, uploaded != "\(userID)|\(token)" else { return }
        let key = "\(userID)|\(token)"
        uploaded = key
        let api = api
        let hash = Self.deviceIDHash()
        Task {
            do {
                try await api.saveNotificationToken(token, timeZone: TimeZone.current.identifier, deviceIDHash: hash)
            } catch {
                Self.log.error("FCM token upload failed: \(String(describing: error), privacy: .public)")
                if uploaded == key { uploaded = nil }
            }
        }
    }

    /// Flutter's `PlatformManager.deviceIdHash` (first 8 hex of SHA-256 of identifierForVendor), read
    /// from its preferences when present, so the backend's `ios_<hash>` token entry is replaced.
    private static func deviceIDHash() -> String? {
        let key = "flutter.deviceIdHash"
        if let stored = UserDefaults.standard.string(forKey: key), !stored.isEmpty { return stored }
        guard let vendor = UIDevice.current.identifierForVendor?.uuidString else { return nil }
        let hash = SHA256.hash(data: Data(vendor.utf8)).map { String(format: "%02x", $0) }.joined().prefix(8)
        UserDefaults.standard.set(String(hash), forKey: key)
        return String(hash)
    }
}

extension PushNotifications: MessagingDelegate {
    nonisolated func messaging(_: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        Task { @MainActor in self.tokenChanged(fcmToken) }
    }
}

extension PushNotifications: UNUserNotificationCenterDelegate {
    nonisolated func userNotificationCenter(
        _: UNUserNotificationCenter, willPresent _: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    nonisolated func userNotificationCenter(_: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let userInfo = response.notification.request.content.userInfo
        Messaging.messaging().appDidReceiveMessage(userInfo)
        let link = DeepLink(notification: userInfo)
        await open(link)
    }
}

/// Local task reminders the backend schedules through data pushes, an hour before the due time.
@MainActor
enum TaskReminders {
    static func apply(_ change: TaskReminderChange) async {
        let center = UNUserNotificationCenter.current()
        switch change {
        case let .cancel(ids):
            center.removePendingNotificationRequests(withIdentifiers: ids.map(identifier))
        case let .schedule(id, description, fireAt):
            let content = UNMutableNotificationContent()
            content.title = "⏰ " + L("actionItemReminderTitle")
            content.body = description
            content.sound = .default
            content.threadIdentifier = "omi.reminder"
            content.userInfo = ["navigate_to": DeepLink.task(id: id).route]
            let parts = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second], from: fireAt)
            let trigger = UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)
            try? await center.add(UNNotificationRequest(identifier: identifier(id), content: content, trigger: trigger))
        }
    }

    private static func identifier(_ taskID: String) -> String {
        "omi.reminder.\(taskID)"
    }
}
