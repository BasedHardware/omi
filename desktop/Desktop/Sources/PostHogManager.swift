import Foundation
import PostHog
import FirebaseAuth

/// Singleton manager for PostHog analytics with Session Replay
/// Complements MixpanelManager - both track the same events
@MainActor
class PostHogManager {
    static let shared = PostHogManager()

    private var isInitialized = false

    // PostHog configuration
    private let apiKey = "phc_z3qUFhGUgYIOMYnfxVSrLmYISQvbgph8iREQv3sez3Y"
    private let host = "https://us.i.posthog.com"

    private init() {}

    // MARK: - Initialization

    /// Initialize PostHog with analytics
    func initialize() {
        guard !isInitialized else { return }

        let config = PostHogConfig(apiKey: apiKey, host: host)

        // Enable automatic event capture
        config.captureApplicationLifecycleEvents = true
        config.captureScreenViews = true
        config.preloadFeatureFlags = true

        PostHogSDK.shared.setup(config)

        isInitialized = true
        log("PostHog: Initialized successfully")
    }

    // MARK: - User Identification

    /// Identify the current user after sign-in
    func identify() {
        guard isInitialized else { return }

        var userId: String?
        var email: String?
        var name: String?

        // Try Firebase Auth first
        if let user = Auth.auth().currentUser {
            userId = user.uid
            email = user.email
            name = user.displayName
        } else if AuthState.shared.isSignedIn, let storedUserId = AuthState.shared.userId {
            // Fall back to stored auth state (when Firebase SDK auth failed but REST API auth succeeded)
            userId = storedUserId
            email = AuthState.shared.userEmail
            name = AuthService.shared.displayName.isEmpty ? nil : AuthService.shared.displayName
            log("PostHog: Using stored auth state (Firebase SDK auth not available)")
        }

        guard let uid = userId else {
            log("PostHog: Cannot identify - no user signed in")
            return
        }

        var properties: [String: Any] = [
            "platform": "macos",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
        ]

        if let email = email {
            properties["email"] = email
        }

        if let name = name {
            properties["name"] = name
        }

        PostHogSDK.shared.identify(uid, userProperties: properties)
        log("PostHog: Identified user \(uid)")
    }

    /// Set a specific user property
    func setUserProperty(key: String, value: Any) {
        guard isInitialized else { return }
        PostHogSDK.shared.identify(PostHogSDK.shared.getDistinctId(), userProperties: [key: value])
    }

    // MARK: - Event Tracking

    /// Track an event with optional properties
    func track(_ eventName: String, properties: [String: Any]? = nil) {
        guard isInitialized else { return }
        PostHogSDK.shared.capture(eventName, properties: properties)
        log("PostHog: Tracked event '\(eventName)'")
    }

    // MARK: - Screen Tracking

    /// Track a screen view
    func screen(_ screenName: String, properties: [String: Any]? = nil) {
        guard isInitialized else { return }
        PostHogSDK.shared.screen(screenName, properties: properties)
    }

    // MARK: - Opt In/Out

    /// Opt in to tracking
    func optIn() {
        guard isInitialized else { return }
        PostHogSDK.shared.optIn()
    }

    /// Opt out of tracking
    func optOut() {
        guard isInitialized else { return }
        PostHogSDK.shared.optOut()
    }

    /// Check if tracking is opted out
    var hasOptedOut: Bool {
        guard isInitialized else { return true }
        return !PostHogSDK.shared.isOptOut()
    }

    // MARK: - Reset

    /// Reset the user (call on sign out)
    func reset() {
        guard isInitialized else { return }
        PostHogSDK.shared.reset()
        log("PostHog: Reset user")
    }

    // MARK: - Feature Flags

    /// Check if a feature flag is enabled
    func isFeatureEnabled(_ flag: String) -> Bool {
        guard isInitialized else { return false }
        return PostHogSDK.shared.isFeatureEnabled(flag)
    }

    /// Get feature flag value
    func getFeatureFlag(_ flag: String) -> Any? {
        guard isInitialized else { return nil }
        return PostHogSDK.shared.getFeatureFlag(flag)
    }

    /// Reload feature flags
    func reloadFeatureFlags() {
        guard isInitialized else { return }
        PostHogSDK.shared.reloadFeatureFlags()
    }
}

// MARK: - Analytics Events

extension PostHogManager {

    // MARK: - Onboarding Events

    func onboardingStepCompleted(step: Int, stepName: String) {
        track("Onboarding Step \(stepName) Completed", properties: [
            "step": step
        ])
    }

    func onboardingCompleted() {
        track("Onboarding Completed")
    }

    // MARK: - Authentication Events

    func signInStarted(provider: String) {
        track("Sign In Started", properties: [
            "provider": provider
        ])
    }

    func signInCompleted(provider: String) {
        track("Sign In Completed", properties: [
            "provider": provider
        ])
    }

    func signInFailed(provider: String, error: String) {
        track("Sign In Failed", properties: [
            "provider": provider,
            "error": error
        ])
    }

    func signedOut() {
        track("Signed Out")
    }

    // MARK: - Monitoring Events

    func monitoringStarted() {
        track("Monitoring Started")
    }

    func monitoringStopped() {
        track("Monitoring Stopped")
    }

    func distractionDetected(app: String, windowTitle: String?) {
        var properties: [String: Any] = [
            "app": app
        ]
        if let title = windowTitle {
            properties["window_title"] = title
        }
        track("Distraction Detected", properties: properties)
    }

    func focusRestored(app: String) {
        track("Focus Restored", properties: [
            "app": app
        ])
    }

    // MARK: - Recording Events

    func transcriptionStarted() {
        track("Phone Mic Recording Started")
    }

    func transcriptionStopped(wordCount: Int) {
        track("Phone Mic Recording Stopped", properties: [
            "word_count": wordCount
        ])
    }

    func recordingError(error: String) {
        track("Phone Mic Recording Error", properties: [
            "error": error
        ])
    }

    // MARK: - Permission Events

    func permissionRequested(permission: String, extraProperties: [String: Any] = [:]) {
        var props: [String: Any] = ["permission": permission]
        for (key, value) in extraProperties {
            props[key] = value
        }
        track("Permission Requested", properties: props)
    }

    func permissionGranted(permission: String, extraProperties: [String: Any] = [:]) {
        var props: [String: Any] = ["permission": permission]
        for (key, value) in extraProperties {
            props[key] = value
        }
        track("Permission Granted", properties: props)
    }

    func permissionDenied(permission: String, extraProperties: [String: Any] = [:]) {
        var props: [String: Any] = ["permission": permission]
        for (key, value) in extraProperties {
            props[key] = value
        }
        track("Permission Denied", properties: props)
    }

    func permissionSkipped(permission: String, extraProperties: [String: Any] = [:]) {
        var props: [String: Any] = ["permission": permission]
        for (key, value) in extraProperties {
            props[key] = value
        }
        track("Permission Skipped", properties: props)
    }

    /// Track when ScreenCaptureKit broken state is detected
    func screenCaptureBrokenDetected() {
        track("Screen Capture Broken Detected", properties: [:])
    }

    /// Track when user clicks reset button or notification
    func screenCaptureResetClicked(source: String) {
        track("Screen Capture Reset Clicked", properties: [
            "source": source
        ])
    }

    /// Track when screen capture reset completes
    func screenCaptureResetCompleted(success: Bool) {
        track("Screen Capture Reset Completed", properties: [
            "success": success
        ])
    }

    func notificationRepairTriggered(reason: String, previousStatus: String, currentStatus: String) {
        track("Notification Repair Triggered", properties: [
            "reason": reason,
            "previous_status": previousStatus,
            "current_status": currentStatus
        ])
    }

    func notificationSettingsChecked(
        authStatus: String,
        alertStyle: String,
        soundEnabled: Bool,
        badgeEnabled: Bool,
        bannersDisabled: Bool
    ) {
        track("Notification Settings Checked", properties: [
            "auth_status": authStatus,
            "alert_style": alertStyle,
            "sound_enabled": soundEnabled,
            "badge_enabled": badgeEnabled,
            "banners_disabled": bannersDisabled
        ])
    }

    // MARK: - App Lifecycle Events

    func appLaunched() {
        track("App Launched", properties: [
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown",
            "os_version": ProcessInfo.processInfo.operatingSystemVersionString
        ])
    }

    /// Track first launch with comprehensive system diagnostics
    func firstLaunch(diagnostics: [String: Any]) {
        track("First Launch", properties: diagnostics)
    }

    func appBecameActive() {
        track("App Became Active")
    }

    func appResignedActive() {
        track("App Resigned Active")
    }

    // MARK: - Page/Screen Views (PostHog specific)

    func pageViewed(_ pageName: String) {
        screen(pageName)
        track("Page Viewed", properties: ["page": pageName])
    }

    // MARK: - Conversation Events
    // Note: The event is named "Memory Created" in analytics for historical reasons,
    // but it actually tracks when a conversation/recording is created, not a "memory".
    // This matches Flutter's naming for analytics consistency.

    func conversationCreated(conversationId: String, source: String, durationSeconds: Int? = nil) {
        var properties: [String: Any] = [
            "conversation_id": conversationId,
            "source": source
        ]
        if let duration = durationSeconds {
            properties["duration_seconds"] = duration
        }
        track("Memory Created", properties: properties)
    }

    func memoryDeleted(conversationId: String) {
        track("Memory Deleted", properties: [
            "conversation_id": conversationId
        ])
    }

    func memoryShareButtonClicked(conversationId: String) {
        track("Memory Share Button Clicked", properties: [
            "conversation_id": conversationId
        ])
    }

    func memoryListItemClicked(conversationId: String) {
        track("Memory List Item Clicked", properties: [
            "conversation_id": conversationId
        ])
    }

    // MARK: - Chat Events

    func chatMessageSent(messageLength: Int, hasContext: Bool = false, source: String) {
        track("Chat Message Sent", properties: [
            "message_length": messageLength,
            "has_context": hasContext,
            "source": source
        ])
    }

    // MARK: - Search Events

    func searchQueryEntered(query: String) {
        track("Search Query Entered", properties: [
            "query_length": query.count
        ])
    }

    func searchBarFocused() {
        track("Search Bar Focused")
    }

    // MARK: - Settings Events

    func settingsPageOpened() {
        track("Settings Page Opened")
    }

    // MARK: - Account Events

    func deleteAccountClicked() {
        track("Delete Account Clicked")
    }

    func deleteAccountConfirmed() {
        track("Delete Account Confirmed")
    }

    func deleteAccountCancelled() {
        track("Delete Account Cancelled")
    }

    // MARK: - Navigation Events

    func tabChanged(tabName: String) {
        track("Tab Changed", properties: [
            "tab_name": tabName
        ])
    }

    func conversationDetailOpened(conversationId: String) {
        track("Conversation Detail Opened", properties: [
            "conversation_id": conversationId
        ])
    }

    // MARK: - Chat Events (Additional)

    func chatAppSelected(appId: String?, appName: String?) {
        var properties: [String: Any] = [:]
        if let id = appId { properties["app_id"] = id }
        if let name = appName { properties["app_name"] = name }
        track("Chat App Selected", properties: properties.isEmpty ? nil : properties)
    }

    func chatCleared() {
        track("Chat Cleared")
    }

    // MARK: - Conversation Events (Additional)

    func conversationReprocessed(conversationId: String, appId: String) {
        track("Conversation Reprocessed", properties: [
            "conversation_id": conversationId,
            "app_id": appId
        ])
    }

    // MARK: - Settings Events (Additional)

    func settingToggled(setting: String, enabled: Bool) {
        track("Setting Toggled", properties: [
            "setting": setting,
            "enabled": enabled
        ])
    }

    func languageChanged(language: String) {
        track("Language Changed", properties: [
            "language": language
        ])
    }

    // MARK: - Launch At Login Events

    func launchAtLoginStatusChecked(enabled: Bool) {
        track("Launch At Login Status", properties: [
            "enabled": enabled
        ])
    }

    func launchAtLoginChanged(enabled: Bool, source: String) {
        track("Launch At Login Changed", properties: [
            "enabled": enabled,
            "source": source
        ])
    }

    // MARK: - Feedback Events

    func feedbackOpened() {
        track("Feedback Opened")
    }

    func feedbackSubmitted(feedbackLength: Int) {
        track("Feedback Submitted", properties: [
            "feedback_length": feedbackLength
        ])
    }

    // MARK: - Rewind Events (Desktop-specific)

    func rewindSearchPerformed(queryLength: Int) {
        track("Rewind Search Performed", properties: [
            "query_length": queryLength
        ])
    }

    func rewindScreenshotViewed(timestamp: Date) {
        track("Rewind Screenshot Viewed", properties: [
            "timestamp": ISO8601DateFormatter().string(from: timestamp)
        ])
    }

    func ffmpegResolved(source: String, path: String) {
        track("FFmpeg Resolved", properties: [
            "source": source,
            "path": path
        ])
    }

    func rewindTimelineNavigated(direction: String) {
        track("Rewind Timeline Navigated", properties: [
            "direction": direction
        ])
    }

    // MARK: - Proactive Assistant Events (Desktop-specific)

    func focusAlertShown(app: String) {
        track("Focus Alert Shown", properties: [
            "app": app
        ])
    }

    func focusAlertDismissed(app: String, action: String) {
        track("Focus Alert Dismissed", properties: [
            "app": app,
            "action": action
        ])
    }

    func taskExtracted(taskCount: Int) {
        track("Task Extracted", properties: [
            "task_count": taskCount
        ])
    }

    func taskPromoted(taskCount: Int) {
        track("Task Promoted", properties: [
            "task_count": taskCount
        ])
    }

    func memoryExtracted(memoryCount: Int) {
        track("Memory Extracted", properties: [
            "memory_count": memoryCount
        ])
    }

    func adviceGenerated(category: String?) {
        var properties: [String: Any] = [:]
        if let cat = category { properties["category"] = cat }
        track("Advice Generated", properties: properties.isEmpty ? nil : properties)
    }

    // MARK: - Apps Events

    func appEnabled(appId: String, appName: String) {
        track("App Enabled", properties: [
            "app_id": appId,
            "app_name": appName
        ])
    }

    func appDisabled(appId: String, appName: String) {
        track("App Disabled", properties: [
            "app_id": appId,
            "app_name": appName
        ])
    }

    func appDetailViewed(appId: String, appName: String) {
        track("App Detail Viewed", properties: [
            "app_id": appId,
            "app_name": appName
        ])
    }

    // MARK: - Update Events

    func updateCheckStarted() {
        track("Update Check Started")
    }

    func updateAvailable(version: String) {
        track("Update Available", properties: [
            "version": version
        ])
    }

    func updateInstalled(version: String) {
        track("Update Installed", properties: [
            "version": version
        ])
    }

    func updateNotFound() {
        track("Update Not Found")
    }

    func updateCheckFailed(error: String) {
        track("Update Check Failed", properties: [
            "error": error
        ])
    }

    // MARK: - Notification Events

    func notificationSent(notificationId: String, title: String, assistantId: String) {
        track("Notification Sent", properties: [
            "notification_id": notificationId,
            "title": title,
            "assistant_id": assistantId
        ])
    }

    func notificationClicked(notificationId: String, title: String, assistantId: String) {
        track("Notification Clicked", properties: [
            "notification_id": notificationId,
            "title": title,
            "assistant_id": assistantId
        ])
    }

    func notificationDismissed(notificationId: String, title: String, assistantId: String) {
        track("Notification Dismissed", properties: [
            "notification_id": notificationId,
            "title": title,
            "assistant_id": assistantId
        ])
    }

    func notificationWillPresent(notificationId: String, title: String) {
        track("Notification Will Present", properties: [
            "notification_id": notificationId,
            "title": title
        ])
    }

    func notificationDelegateReady() {
        track("Notification Delegate Ready")
    }

    // MARK: - Menu Bar Events

    func menuBarOpened() {
        track("Menu Bar Opened")
    }

    func menuBarActionClicked(action: String) {
        track("Menu Bar Action Clicked", properties: [
            "action": action
        ])
    }

    // MARK: - Tier Events

    func tierChanged(tier: Int, reason: String) {
        track("Tier Changed", properties: [
            "tier": tier,
            "reason": reason
        ])
    }

    func chatBridgeModeChanged(from oldMode: String, to newMode: String) {
        track("chat_bridge_mode_changed", properties: [
            "from": oldMode,
            "to": newMode
        ])
    }

    // MARK: - Settings State

    func settingsStateTracked(screenshotsEnabled: Bool, memoryExtractionEnabled: Bool, memoryNotificationsEnabled: Bool) {
        track("Settings State", properties: [
            "screenshots_enabled": screenshotsEnabled,
            "memory_extraction_enabled": memoryExtractionEnabled,
            "memory_notifications_enabled": memoryNotificationsEnabled
        ])
    }

    /// Comprehensive all-settings snapshot (fired on app launch, at most once per day)
    func allSettingsStateTracked(properties: [String: Any]) {
        track("All Settings State", properties: properties)
    }

    // MARK: - Display Info

    func displayInfoTracked(info: [String: Any]) {
        track("Display Info", properties: info)
    }
}
