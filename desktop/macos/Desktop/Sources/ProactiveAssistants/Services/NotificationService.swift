import AppKit
import Foundation
import UserNotifications

/// Sound options for notifications
enum NotificationSound {
    case `default`
    case focusLost
    case focusRegained
    case none

    var unSound: UNNotificationSound? {
        switch self {
        case .default:
            return .default
        case .focusLost, .focusRegained:
            // Custom sounds are played manually via NSSound (see playCustomSound)
            // because UNNotificationSound(named:) can't find SPM-bundled resources.
            return nil
        case .none:
            return nil
        }
    }

    /// Play the custom sound manually from the SPM resource bundle.
    func playCustomSound() {
        let filename: String
        switch self {
        case .focusLost:
            filename = "focus-lost"
        case .focusRegained:
            filename = "focus-regained"
        default:
            return
        }

        guard let url = Bundle.resourceBundle.url(forResource: filename, withExtension: "aiff") else {
            log("NotificationSound: Could not find \(filename).aiff in bundle")
            return
        }

        guard let sound = NSSound(contentsOf: url, byReference: true) else {
            log("NotificationSound: Could not load sound from \(url)")
            return
        }

        sound.play()
    }
}

@MainActor
class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationService()

    /// Category ID for notifications that track dismissal
    private static let trackableCategoryId = "omi.trackable"

    /// Category ID for screen capture reset notifications with action button
    private static let screenCaptureResetCategoryId = "omi.screen_capture_reset"

    /// Action ID for the "Reset Now" button
    private static let resetNowActionId = "RESET_SCREEN_CAPTURE_NOW"

    /// Title that identifies screen capture reset notifications
    static let screenCaptureResetTitle = "Screen Recording Needs Reset"

    /// UserDefaults key that records whether the screen capture reset notification
    /// has already been shown in the current broken-capture episode. Cleared by
    /// `AppState.checkScreenRecordingPermission()` as soon as capture recovers,
    /// so a new breakage re-notifies exactly once.
    static let screenCaptureResetShownKey = "screenCaptureResetNotificationShown"

    /// UserDefaults key mirroring the user's `notification_frequency` setting from the backend.
    /// 0=Off (default), 1=Minimal, 2=Low, 3=Balanced, 4=High, 5=Maximum.
    /// The Settings page writes this on load and on slider change; `sendNotification`
    /// reads it synchronously to throttle proactive notifications.
    static let frequencyDefaultsKey = "notification_frequency"

    /// One-time migration flag: when set, the notifications-off-by-default migration
    /// has already run for this install, so we never re-disable a user who opted back in.
    static let offByDefaultMigrationKey = "notificationsOffByDefaultMigrationDone"

    /// Default level used when the key has never been written (e.g. first run before
    /// the Settings page has hydrated from the backend). Mirrors the backend default.
    /// Proactive notifications are OFF by default — users opt in via the Settings slider.
    private static let defaultFrequencyLevel = 0

    /// Stores metadata for sent notifications so we can retrieve it in delegate callbacks
    /// Key: notification identifier, Value: (title, assistantId)
    private var notificationMetadata: [String: (title: String, assistantId: String)] = [:]

    /// Last time we triggered a notification repair (debounce to avoid hammering lsregister)
    private var lastRepairAttempt: Date?

    /// Last proactive-notification timestamp per assistantId. Used by the frequency
    /// throttle so one chatty assistant cannot starve another.
    private var lastNotificationAt: [String: Date] = [:]

    /// Last proactive-notification timestamp across all assistants. Used by the
    /// frequency throttle as a global rate limit.
    private var lastNotificationAtGlobal: Date?

    private override init() {
        super.init()
        // Set ourselves as the delegate to show notifications even when app is in foreground
        UNUserNotificationCenter.current().delegate = self
        // Set up notification categories for tracking
        setupNotificationCategories()
        // Track that delegate is ready
        AnalyticsManager.shared.notificationDelegateReady()
        log("NotificationService: Delegate initialized and ready")
    }

    /// Set up notification categories to enable dismiss tracking
    private func setupNotificationCategories() {
        // Create a category that tracks custom dismiss action
        // This allows us to know when a user explicitly dismisses a notification
        let trackableCategory = UNNotificationCategory(
            identifier: Self.trackableCategoryId,
            actions: [],
            intentIdentifiers: [],
            options: [.customDismissAction]  // This enables didReceive callback on dismiss
        )

        // Create "Reset Now" action for screen capture reset notifications
        let resetNowAction = UNNotificationAction(
            identifier: Self.resetNowActionId,
            title: "Reset Now",
            options: [.foreground]  // Bring app to foreground when tapped
        )

        // Create category for screen capture reset with the action button
        let screenCaptureResetCategory = UNNotificationCategory(
            identifier: Self.screenCaptureResetCategoryId,
            actions: [resetNowAction],
            intentIdentifiers: [],
            options: [.customDismissAction]
        )

        UNUserNotificationCenter.current().setNotificationCategories([trackableCategory, screenCaptureResetCategory])
    }

    // MARK: - UNUserNotificationCenterDelegate

    // This allows notifications to be displayed even when the app is in the foreground
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        // Track that willPresent was called (confirms delegate is working)
        let notificationId = notification.request.identifier
        let title = notification.request.content.title
        Task { @MainActor in
            AnalyticsManager.shared.notificationWillPresent(notificationId: notificationId, title: title)
        }
        // Show banner and badge; only include .sound if the notification has a sound attached
        // (custom focus sounds are played via NSSound, so their content.sound is nil)
        var options: UNNotificationPresentationOptions = [.banner, .badge]
        if notification.request.content.sound != nil {
            options.insert(.sound)
        }
        completionHandler(options)
    }

    // Handle notification interactions (click or dismiss)
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let notificationId = response.notification.request.identifier

        Task { @MainActor in
            // Retrieve stored metadata
            let metadata = self.notificationMetadata[notificationId]
            let title = metadata?.title ?? response.notification.request.content.title
            let assistantId = metadata?.assistantId ?? "unknown"

            switch response.actionIdentifier {
            case UNNotificationDefaultActionIdentifier:
                // User clicked/tapped the notification
                print("[\(assistantId)] Notification clicked: \(title)")
                AnalyticsManager.shared.notificationClicked(
                    notificationId: notificationId,
                    title: title,
                    assistantId: assistantId,
                    surface: "system_notification"
                )

                // If this is a screen capture reset notification, trigger the reset
                if title == Self.screenCaptureResetTitle {
                    self.handleScreenCaptureResetAction(source: "notification_click")
                }

            case UNNotificationDismissActionIdentifier:
                // User explicitly dismissed the notification (X button, swipe, or Clear)
                print("[\(assistantId)] Notification dismissed: \(title)")
                AnalyticsManager.shared.notificationDismissed(
                    notificationId: notificationId,
                    title: title,
                    assistantId: assistantId,
                    surface: "system_notification"
                )

            case Self.resetNowActionId:
                // User clicked the "Reset Now" action button
                print("[\(assistantId)] Reset Now action clicked: \(title)")
                AnalyticsManager.shared.notificationClicked(
                    notificationId: notificationId,
                    title: title,
                    assistantId: assistantId,
                    surface: "system_notification"
                )
                self.handleScreenCaptureResetAction(source: "notification_action_button")

            default:
                // Custom action (if we add action buttons in the future)
                print("[\(assistantId)] Notification action: \(response.actionIdentifier)")
            }

            // Clean up metadata
            self.notificationMetadata.removeValue(forKey: notificationId)
        }

        completionHandler()
    }

    /// Handle screen capture reset action from notification click or action button
    private func handleScreenCaptureResetAction(source: String) {
        log("Screen capture reset triggered from \(source)")
        AnalyticsManager.shared.screenCaptureResetClicked(source: source)
        ScreenCaptureService.resetScreenCapturePermissionAndRestart()
    }

    /// Send a notification via the floating bar, and optionally as a native macOS system banner.
    ///
    /// `deliverSystemBanner` defaults to `false` because proactive AI notifications are
    /// floating-bar only — users who disabled the floating bar reported clicking the
    /// top-right system banner and getting no conversation context, which was confusing.
    /// Functional notifications (Crisp support replies, screen-recording permission
    /// prompts with a repair action) must pass `deliverSystemBanner: true` so they
    /// still surface as a system banner — they either have no floating-bar equivalent
    /// or must reach the user even when the floating bar is hidden/snoozed.
    func sendNotification(
        title: String,
        message: String,
        assistantId: String = "default",
        sound: NotificationSound = .default,
        context: FloatingBarNotificationContext? = nil,
        screenshotData: Data? = nil,
        deliverSystemBanner: Bool = false,
        respectFrequency: Bool = true
    ) {
        // Rate-limit the screen-capture reset notification to one per broken-capture
        // episode. The recovery loop in ProactiveAssistantsPlugin.attemptAutoReset
        // re-fires this on every session (soft-recovery + app restart), which buried
        // users in duplicate banners when a stale TCC csreq from an auto-update made
        // the capture path unrecoverable without a manual toggle in System Settings.
        if title == Self.screenCaptureResetTitle {
            if UserDefaults.standard.bool(forKey: Self.screenCaptureResetShownKey) {
                log("NotificationService: suppressing duplicate screen capture reset notification")
                return
            }
            UserDefaults.standard.set(true, forKey: Self.screenCaptureResetShownKey)
        }

        // Honor the floating-bar snooze for both the in-bar preview and the native
        // macOS banner — the user opted into "no notifications for 2h".
        if FloatingControlBarManager.shared.isSnoozed {
            log("NotificationService: suppressing notification because floating bar is snoozed")
            return
        }

        // Proactive notifications honor the user's frequency setting. Functional
        // notifications (Crisp support replies, screen-recording permission prompts,
        // onboarding test) pass `respectFrequency: false` to bypass the gate.
        if respectFrequency && !shouldAllowProactiveNotification(assistantId: assistantId) {
            log("NotificationService: throttled \(assistantId) notification (frequency=\(Self.currentFrequencyLevel()))")
            return
        }

        FloatingControlBarManager.shared.showNotification(
            title: title,
            message: message,
            assistantId: assistantId,
            sound: sound,
            context: context,
            screenshotData: screenshotData
        )

        // Default path: floating-bar only. Functional callers opt-in via
        // `deliverSystemBanner: true` (see the parameter doc above).
        guard deliverSystemBanner else { return }

        UNUserNotificationCenter.current().getNotificationSettings { [weak self] settings in
            Task { @MainActor in
                guard settings.authorizationStatus == .authorized else {
                    log("Notification skipped (auth=\(settings.authorizationStatus.rawValue)): \(title)")

                    // If auth reverted to notDetermined (not explicitly denied), trigger repair.
                    // Debounce: at most once per 10 minutes to avoid hammering lsregister.
                    if settings.authorizationStatus == .notDetermined {
                        let now = Date()
                        if self?.lastRepairAttempt == nil || now.timeIntervalSince(self?.lastRepairAttempt ?? .distantPast) > 600 {
                            self?.lastRepairAttempt = now
                            log("Notification auth is notDetermined at send time — triggering repair")
                            AnalyticsManager.shared.notificationRepairTriggered(
                                reason: "send_time_not_determined",
                                previousStatus: "unknown",
                                currentStatus: "notDetermined"
                            )
                            ProactiveAssistantsPlugin.repairNotificationRegistration()
                        }
                    }

                    return
                }

                self?.deliverNotification(title: title, message: message, assistantId: assistantId, sound: sound)
            }
        }
    }

    private func deliverNotification(title: String, message: String, assistantId: String, sound: NotificationSound) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = message
        content.sound = sound.unSound

        // Use screen capture reset category for reset notifications (adds "Reset Now" button)
        if title == Self.screenCaptureResetTitle {
            content.categoryIdentifier = Self.screenCaptureResetCategoryId
        } else {
            content.categoryIdentifier = Self.trackableCategoryId  // Enable dismiss tracking
        }

        let notificationId = UUID().uuidString
        let request = UNNotificationRequest(
            identifier: notificationId,
            content: content,
            trigger: nil // Deliver immediately
        )

        // Store metadata for later retrieval in delegate callbacks
        notificationMetadata[notificationId] = (title: title, assistantId: assistantId)

        // Play custom sound manually (SPM resources aren't found by UNNotificationSound)
        sound.playCustomSound()

        print("[\(assistantId)] Sending notification: \(title) - \(message)")
        UNUserNotificationCenter.current().add(request) { [weak self] error in
            if let error = error {
                print("Notification error: \(error)")
                logError("Notification error", error: error)
                // Clean up metadata on error
                Task { @MainActor in
                    self?.notificationMetadata.removeValue(forKey: notificationId)
                }
            } else {
                print("Notification sent successfully")
                // Track notification sent
                Task { @MainActor in
                    AnalyticsManager.shared.notificationSent(
                        notificationId: notificationId,
                        title: title,
                        assistantId: assistantId,
                        surface: "system_notification"
                    )
                }
            }
        }
    }

    // MARK: - Frequency throttle

    /// One-time migration to make proactive notifications OFF by default for ALL users.
    /// Runs once per install (guarded by `offByDefaultMigrationKey`): sets the local
    /// frequency to Off and persists it to the backend so the choice sticks across
    /// devices and is reflected in Settings. Because it is guarded by the flag, a user
    /// who later turns notifications back on is never re-disabled on subsequent launches.
    /// Call early at launch, before any proactive assistant can fire.
    static func migrateToOffByDefaultIfNeeded() {
        guard !UserDefaults.standard.bool(forKey: Self.offByDefaultMigrationKey) else { return }
        UserDefaults.standard.set(0, forKey: Self.frequencyDefaultsKey)
        UserDefaults.standard.set(true, forKey: Self.offByDefaultMigrationKey)
        log("NotificationService: applied notifications-off-by-default migration (frequency=0)")
        guard AuthService.shared.isSignedIn else { return }
        Task {
            do {
                _ = try await APIClient.shared.updateNotificationSettings(enabled: nil, frequency: 0)
            } catch {
                logError(
                    "NotificationService: off-by-default migration backend push failed", error: error)
            }
        }
    }

    /// Current frequency level from UserDefaults, clamped to [0, 5]. Falls back to
    /// `defaultFrequencyLevel` when the key is absent (first run before sync).
    static func currentFrequencyLevel() -> Int {
        guard UserDefaults.standard.object(forKey: Self.frequencyDefaultsKey) != nil else {
            return Self.defaultFrequencyLevel
        }
        let raw = UserDefaults.standard.integer(forKey: Self.frequencyDefaultsKey)
        return max(0, min(5, raw))
    }

    /// Minimum interval between proactive notifications for a given level.
    /// `nil` means no throttle (Maximum); `.infinity` means drop everything (Off).
    private static func minInterval(forLevel level: Int) -> TimeInterval? {
        switch level {
        case 0: return .infinity   // Off
        case 1: return 60 * 60     // Minimal:  1 per hour
        case 2: return 30 * 60     // Low:      1 per 30 min
        case 3: return 10 * 60     // Balanced: 1 per 10 min
        case 4: return 3 * 60      // High:     1 per 3 min
        default: return nil        // Maximum:  no throttle
        }
    }

    /// Decide whether a proactive notification from `assistantId` should be delivered.
    /// Records the timestamp when allowed so subsequent calls within the window are
    /// suppressed. Per-assistant + global limits combine so a chatty assistant cannot
    /// starve another.
    private func shouldAllowProactiveNotification(assistantId: String) -> Bool {
        let level = Self.currentFrequencyLevel()
        guard let interval = Self.minInterval(forLevel: level) else {
            return true  // Maximum
        }
        if interval == .infinity {
            return false  // Off
        }
        let now = Date()
        if let last = lastNotificationAtGlobal, now.timeIntervalSince(last) < interval {
            return false
        }
        if let last = lastNotificationAt[assistantId], now.timeIntervalSince(last) < interval {
            return false
        }
        lastNotificationAt[assistantId] = now
        lastNotificationAtGlobal = now
        return true
    }
}
// Updated Gemini API key in Codemagic secret — triggering release
