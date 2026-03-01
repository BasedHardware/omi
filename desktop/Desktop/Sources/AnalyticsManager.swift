import Foundation
import AppKit
import Mixpanel

/// Unified analytics manager that sends events to both Mixpanel and PostHog
/// Use this instead of calling MixpanelManager and PostHogManager directly
@MainActor
class AnalyticsManager {
    static let shared = AnalyticsManager()

    /// Returns true if this is a development build (bundle ID ends with "-dev")
    /// Development builds don't send analytics to avoid polluting production data
    nonisolated static var isDevBuild: Bool {
        Bundle.main.bundleIdentifier?.hasSuffix("-dev") == true
    }

    private init() {}

    // MARK: - Initialization

    func initialize() {
        // Skip analytics in development builds
        guard !Self.isDevBuild else {
            log("Analytics: Skipping initialization (development build)")
            return
        }
        MixpanelManager.shared.initialize()
        PostHogManager.shared.initialize()
    }

    // MARK: - User Identification

    func identify() {
        MixpanelManager.shared.identify()
        PostHogManager.shared.identify()
    }

    func reset() {
        MixpanelManager.shared.reset()
        PostHogManager.shared.reset()
    }

    // MARK: - Opt In/Out

    func optInTracking() {
        MixpanelManager.shared.optInTracking()
        PostHogManager.shared.optIn()
    }

    func optOutTracking() {
        MixpanelManager.shared.optOutTracking()
        PostHogManager.shared.optOut()
    }

    // MARK: - Onboarding Events

    func onboardingStepCompleted(step: Int, stepName: String) {
        MixpanelManager.shared.onboardingStepCompleted(step: step, stepName: stepName)
        PostHogManager.shared.onboardingStepCompleted(step: step, stepName: stepName)
    }

    func onboardingCompleted() {
        MixpanelManager.shared.onboardingCompleted()
        PostHogManager.shared.onboardingCompleted()
    }

    func onboardingChatToolUsed(tool: String, properties: [String: Any] = [:]) {
        var props = properties
        props["tool"] = tool
        let mixpanelProps = props.compactMapValues { $0 as? MixpanelType }
        MixpanelManager.shared.track("Onboarding Chat Tool Used", properties: mixpanelProps)
        PostHogManager.shared.track("Onboarding Chat Tool Used", properties: props)
    }

    func onboardingChatMessage(role: String, step: String) {
        let props: [String: Any] = ["role": role, "step": step]
        let mixpanelProps = props.compactMapValues { $0 as? MixpanelType }
        MixpanelManager.shared.track("Onboarding Chat Message", properties: mixpanelProps)
        PostHogManager.shared.track("Onboarding Chat Message", properties: props)
    }

    // MARK: - Authentication Events

    func signInStarted(provider: String) {
        MixpanelManager.shared.signInStarted(provider: provider)
        PostHogManager.shared.signInStarted(provider: provider)
    }

    func signInCompleted(provider: String) {
        MixpanelManager.shared.signInCompleted(provider: provider)
        PostHogManager.shared.signInCompleted(provider: provider)
    }

    func signInFailed(provider: String, error: String) {
        MixpanelManager.shared.signInFailed(provider: provider, error: error)
        PostHogManager.shared.signInFailed(provider: provider, error: error)
    }

    func signedOut() {
        MixpanelManager.shared.signedOut()
        PostHogManager.shared.signedOut()
    }

    // MARK: - Monitoring Events

    func monitoringStarted() {
        MixpanelManager.shared.monitoringStarted()
        PostHogManager.shared.monitoringStarted()
    }

    func monitoringStopped() {
        MixpanelManager.shared.monitoringStopped()
        PostHogManager.shared.monitoringStopped()
    }

    func distractionDetected(app: String, windowTitle: String?) {
        MixpanelManager.shared.distractionDetected(app: app, windowTitle: windowTitle)
        PostHogManager.shared.distractionDetected(app: app, windowTitle: windowTitle)
    }

    func focusRestored(app: String) {
        MixpanelManager.shared.focusRestored(app: app)
        PostHogManager.shared.focusRestored(app: app)
    }

    // MARK: - Recording Events

    func transcriptionStarted() {
        MixpanelManager.shared.transcriptionStarted()
        PostHogManager.shared.transcriptionStarted()
    }

    func transcriptionStopped(wordCount: Int) {
        MixpanelManager.shared.transcriptionStopped(wordCount: wordCount)
        PostHogManager.shared.transcriptionStopped(wordCount: wordCount)
    }

    func recordingError(error: String) {
        MixpanelManager.shared.recordingError(error: error)
        PostHogManager.shared.recordingError(error: error)
    }

    // MARK: - Permission Events

    func permissionRequested(permission: String, extraProperties: [String: Any] = [:]) {
        let mixpanelProps = extraProperties.compactMapValues { $0 as? MixpanelType }
        MixpanelManager.shared.permissionRequested(permission: permission, extraProperties: mixpanelProps)
        PostHogManager.shared.permissionRequested(permission: permission, extraProperties: extraProperties)
    }

    func permissionGranted(permission: String, extraProperties: [String: Any] = [:]) {
        let mixpanelProps = extraProperties.compactMapValues { $0 as? MixpanelType }
        MixpanelManager.shared.permissionGranted(permission: permission, extraProperties: mixpanelProps)
        PostHogManager.shared.permissionGranted(permission: permission, extraProperties: extraProperties)
    }

    func permissionDenied(permission: String, extraProperties: [String: Any] = [:]) {
        let mixpanelProps = extraProperties.compactMapValues { $0 as? MixpanelType }
        MixpanelManager.shared.permissionDenied(permission: permission, extraProperties: mixpanelProps)
        PostHogManager.shared.permissionDenied(permission: permission, extraProperties: extraProperties)
    }

    func permissionSkipped(permission: String, extraProperties: [String: Any] = [:]) {
        let mixpanelProps = extraProperties.compactMapValues { $0 as? MixpanelType }
        MixpanelManager.shared.permissionSkipped(permission: permission, extraProperties: mixpanelProps)
        PostHogManager.shared.permissionSkipped(permission: permission, extraProperties: extraProperties)
    }

    /// Track Bluetooth state changes for debugging
    func bluetoothStateChanged(oldState: String, newState: String, oldStateRaw: Int, newStateRaw: Int, authorization: String, authorizationRaw: Int) {
        let properties: [String: MixpanelType] = [
            "old_state": oldState,
            "new_state": newState,
            "old_state_raw": oldStateRaw,
            "new_state_raw": newStateRaw,
            "authorization": authorization,
            "authorization_raw": authorizationRaw
        ]
        MixpanelManager.shared.track("Bluetooth State Changed", properties: properties)
        PostHogManager.shared.track("Bluetooth State Changed", properties: properties as [String: Any])
    }

    /// Track when ScreenCaptureKit broken state is detected (TCC granted but capture failing)
    func screenCaptureBrokenDetected() {
        MixpanelManager.shared.screenCaptureBrokenDetected()
        PostHogManager.shared.screenCaptureBrokenDetected()
    }

    /// Track when user clicks reset button or notification to reset screen capture
    func screenCaptureResetClicked(source: String) {
        MixpanelManager.shared.screenCaptureResetClicked(source: source)
        PostHogManager.shared.screenCaptureResetClicked(source: source)
    }

    /// Track when screen capture reset completes (success or failure)
    func screenCaptureResetCompleted(success: Bool) {
        MixpanelManager.shared.screenCaptureResetCompleted(success: success)
        PostHogManager.shared.screenCaptureResetCompleted(success: success)
    }

    /// Track when notification repair is triggered (auto-repair or error-triggered)
    func notificationRepairTriggered(reason: String, previousStatus: String, currentStatus: String) {
        MixpanelManager.shared.notificationRepairTriggered(reason: reason, previousStatus: previousStatus, currentStatus: currentStatus)
        PostHogManager.shared.notificationRepairTriggered(reason: reason, previousStatus: previousStatus, currentStatus: currentStatus)
    }

    /// Track notification settings status (auth, alertStyle, sound, badge)
    func notificationSettingsChecked(
        authStatus: String,
        alertStyle: String,
        soundEnabled: Bool,
        badgeEnabled: Bool,
        bannersDisabled: Bool
    ) {
        MixpanelManager.shared.notificationSettingsChecked(
            authStatus: authStatus,
            alertStyle: alertStyle,
            soundEnabled: soundEnabled,
            badgeEnabled: badgeEnabled,
            bannersDisabled: bannersDisabled
        )
        PostHogManager.shared.notificationSettingsChecked(
            authStatus: authStatus,
            alertStyle: alertStyle,
            soundEnabled: soundEnabled,
            badgeEnabled: badgeEnabled,
            bannersDisabled: bannersDisabled
        )
    }

    // MARK: - App Lifecycle Events

    func appLaunched() {
        MixpanelManager.shared.appLaunched()
        PostHogManager.shared.appLaunched()
    }

    func trackStartupTiming(dbInitMs: Double, timeToInteractiveMs: Double, hadUncleanShutdown: Bool, databaseInitFailed: Bool) {
        guard !Self.isDevBuild else { return }
        let properties: [String: Any] = [
            "db_init_ms": round(dbInitMs),
            "time_to_interactive_ms": round(timeToInteractiveMs),
            "had_unclean_shutdown": hadUncleanShutdown,
            "database_init_failed": databaseInitFailed
        ]
        PostHogManager.shared.track("App Startup Timing", properties: properties)
        MixpanelManager.shared.track("App Startup Timing", properties: properties.compactMapValues { $0 as? MixpanelType })
    }

    /// Track first launch with comprehensive system diagnostics
    /// This only fires once per installation
    func trackFirstLaunchIfNeeded() {
        // Skip in dev builds
        guard !Self.isDevBuild else { return }

        let defaults = UserDefaults.standard
        let hasLaunchedKey = "hasLaunchedBefore"

        // Check if this is the first launch
        guard !defaults.bool(forKey: hasLaunchedKey) else {
            return
        }

        // Mark as launched so this only fires once
        defaults.set(true, forKey: hasLaunchedKey)

        // Collect system diagnostics
        let diagnostics = collectSystemDiagnostics()

        // Track in both analytics systems
        MixpanelManager.shared.firstLaunch(diagnostics: diagnostics)
        PostHogManager.shared.firstLaunch(diagnostics: diagnostics)

        log("Analytics: First launch diagnostics tracked")
    }

    /// Collect comprehensive system diagnostics for first launch event
    private func collectSystemDiagnostics() -> [String: Any] {
        var diagnostics: [String: Any] = [:]

        // App version
        diagnostics["app_version"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        diagnostics["build_number"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"

        // macOS version (detailed)
        let osVersion = ProcessInfo.processInfo.operatingSystemVersion
        diagnostics["os_version"] = "\(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)"
        diagnostics["os_major_version"] = osVersion.majorVersion
        diagnostics["os_minor_version"] = osVersion.minorVersion
        diagnostics["os_patch_version"] = osVersion.patchVersion
        diagnostics["os_version_string"] = ProcessInfo.processInfo.operatingSystemVersionString

        // Architecture (Apple Silicon vs Intel)
        #if arch(arm64)
        diagnostics["architecture"] = "arm64"
        diagnostics["is_apple_silicon"] = true
        #elseif arch(x86_64)
        diagnostics["architecture"] = "x86_64"
        diagnostics["is_apple_silicon"] = false
        #else
        diagnostics["architecture"] = "unknown"
        diagnostics["is_apple_silicon"] = false
        #endif

        // App bundle location - helps diagnose installation issues
        if let bundlePath = Bundle.main.bundlePath as String? {
            diagnostics["bundle_path"] = bundlePath

            // Categorize the installation location
            if bundlePath.hasPrefix("/Volumes/") {
                diagnostics["install_location"] = "dmg_mounted"
            } else if bundlePath.contains("/Downloads/") {
                diagnostics["install_location"] = "downloads_folder"
            } else if bundlePath.hasPrefix("/Applications/") {
                diagnostics["install_location"] = "applications_system"
            } else if bundlePath.contains("/Applications/") {
                diagnostics["install_location"] = "applications_user"
            } else if bundlePath.contains("DerivedData") || bundlePath.contains("Xcode") {
                diagnostics["install_location"] = "xcode_build"
            } else {
                diagnostics["install_location"] = "other"
            }
        }

        // Device info
        diagnostics["processor_count"] = ProcessInfo.processInfo.processorCount
        diagnostics["physical_memory_gb"] = Int(ProcessInfo.processInfo.physicalMemory / 1_073_741_824)

        // Locale info
        diagnostics["locale"] = Locale.current.identifier
        diagnostics["timezone"] = TimeZone.current.identifier

        return diagnostics
    }

    func appBecameActive() {
        MixpanelManager.shared.appBecameActive()
        PostHogManager.shared.appBecameActive()
    }

    func appResignedActive() {
        MixpanelManager.shared.appResignedActive()
        PostHogManager.shared.appResignedActive()
    }

    // MARK: - Conversation Events
    // Note: The event is named "Memory Created" in analytics for historical reasons,
    // but it actually tracks when a conversation/recording is created, not a "memory".

    func conversationCreated(conversationId: String, source: String, durationSeconds: Int? = nil) {
        MixpanelManager.shared.conversationCreated(conversationId: conversationId, source: source, durationSeconds: durationSeconds)
        PostHogManager.shared.conversationCreated(conversationId: conversationId, source: source, durationSeconds: durationSeconds)
        // Flush immediately to ensure this important event is sent
        MixpanelManager.shared.flush()
    }

    func memoryDeleted(conversationId: String) {
        MixpanelManager.shared.memoryDeleted(conversationId: conversationId)
        PostHogManager.shared.memoryDeleted(conversationId: conversationId)
    }

    func memoryShareButtonClicked(conversationId: String) {
        MixpanelManager.shared.memoryShareButtonClicked(conversationId: conversationId)
        PostHogManager.shared.memoryShareButtonClicked(conversationId: conversationId)
    }

    func memoryListItemClicked(conversationId: String) {
        MixpanelManager.shared.memoryListItemClicked(conversationId: conversationId)
        PostHogManager.shared.memoryListItemClicked(conversationId: conversationId)
    }

    // MARK: - Chat Events

    func chatMessageSent(messageLength: Int, hasContext: Bool = false, source: String) {
        MixpanelManager.shared.chatMessageSent(messageLength: messageLength, hasContext: hasContext, source: source)
        PostHogManager.shared.chatMessageSent(messageLength: messageLength, hasContext: hasContext, source: source)
    }

    // MARK: - Search Events

    func searchQueryEntered(query: String) {
        MixpanelManager.shared.searchQueryEntered(query: query)
        PostHogManager.shared.searchQueryEntered(query: query)
    }

    func searchBarFocused() {
        MixpanelManager.shared.searchBarFocused()
        PostHogManager.shared.searchBarFocused()
    }

    // MARK: - Settings Events

    func settingsPageOpened() {
        MixpanelManager.shared.settingsPageOpened()
        PostHogManager.shared.settingsPageOpened()
    }

    // MARK: - Page/Screen Views (PostHog specific, but tracked in both)

    func pageViewed(_ pageName: String) {
        PostHogManager.shared.pageViewed(pageName)
        // Mixpanel doesn't have a dedicated screen view, but we track as an event
        MixpanelManager.shared.track("Page Viewed", properties: ["page": pageName])
    }

    // MARK: - Account Events

    func deleteAccountClicked() {
        MixpanelManager.shared.deleteAccountClicked()
        PostHogManager.shared.deleteAccountClicked()
    }

    func deleteAccountConfirmed() {
        MixpanelManager.shared.deleteAccountConfirmed()
        PostHogManager.shared.deleteAccountConfirmed()
    }

    func deleteAccountCancelled() {
        MixpanelManager.shared.deleteAccountCancelled()
        PostHogManager.shared.deleteAccountCancelled()
    }

    // MARK: - Navigation Events

    func tabChanged(tabName: String) {
        MixpanelManager.shared.tabChanged(tabName: tabName)
        PostHogManager.shared.tabChanged(tabName: tabName)
    }

    func conversationDetailOpened(conversationId: String) {
        MixpanelManager.shared.conversationDetailOpened(conversationId: conversationId)
        PostHogManager.shared.conversationDetailOpened(conversationId: conversationId)
    }

    // MARK: - Chat Events (Additional)

    func chatAppSelected(appId: String?, appName: String?) {
        MixpanelManager.shared.chatAppSelected(appId: appId, appName: appName)
        PostHogManager.shared.chatAppSelected(appId: appId, appName: appName)
    }

    func chatCleared() {
        MixpanelManager.shared.chatCleared()
        PostHogManager.shared.chatCleared()
    }

    func chatSessionCreated() {
        MixpanelManager.shared.track("Chat Session Created", properties: [:])
        PostHogManager.shared.track("chat_session_created", properties: [:])
    }

    func chatSessionDeleted() {
        MixpanelManager.shared.track("Chat Session Deleted", properties: [:])
        PostHogManager.shared.track("chat_session_deleted", properties: [:])
    }

    func messageRated(rating: Int) {
        let ratingString = rating == 1 ? "thumbs_up" : "thumbs_down"
        MixpanelManager.shared.track("Message Rated", properties: ["rating": ratingString])
        PostHogManager.shared.track("message_rated", properties: ["rating": ratingString])
    }

    func initialMessageGenerated(hasApp: Bool) {
        MixpanelManager.shared.track("Initial Message Generated", properties: ["has_app": hasApp])
        PostHogManager.shared.track("initial_message_generated", properties: ["has_app": hasApp])
    }

    func sessionTitleGenerated() {
        MixpanelManager.shared.track("Session Title Generated", properties: [:])
        PostHogManager.shared.track("session_title_generated", properties: [:])
    }

    func chatStarredFilterToggled(enabled: Bool) {
        MixpanelManager.shared.track("Chat Starred Filter Toggled", properties: ["enabled": enabled])
        PostHogManager.shared.track("chat_starred_filter_toggled", properties: ["enabled": enabled])
    }

    func sessionRenamed() {
        MixpanelManager.shared.track("Session Renamed", properties: [:])
        PostHogManager.shared.track("session_renamed", properties: [:])
    }

    // MARK: - Claude Agent Events

    /// Track when a Claude agent query completes (one full send → response cycle)
    func chatAgentQueryCompleted(
        durationMs: Int,
        toolCallCount: Int,
        toolNames: [String],
        costUsd: Double,
        messageLength: Int
    ) {
        let props: [String: Any] = [
            "duration_ms": durationMs,
            "tool_call_count": toolCallCount,
            "tool_names": toolNames.joined(separator: ","),
            "cost_usd": costUsd,
            "response_length": messageLength
        ]
        MixpanelManager.shared.track("Chat Agent Query Completed", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("chat_agent_query_completed", properties: props)
    }

    /// Track individual tool calls made by the Claude agent
    func chatToolCallCompleted(toolName: String, durationMs: Int) {
        let cleanName: String
        if toolName.hasPrefix("mcp__") {
            cleanName = String(toolName.split(separator: "__").last ?? Substring(toolName))
        } else {
            cleanName = toolName
        }
        let props: [String: Any] = [
            "tool_name": cleanName,
            "duration_ms": durationMs
        ]
        MixpanelManager.shared.track("Chat Tool Call Completed", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("chat_tool_call_completed", properties: props)
    }

    /// Track when the Claude agent bridge fails to start or errors
    func chatAgentError(error: String) {
        let props: [String: Any] = ["error": error]
        MixpanelManager.shared.track("Chat Agent Error", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("chat_agent_error", properties: props)
    }

    // MARK: - Conversation Events (Additional)

    func conversationReprocessed(conversationId: String, appId: String) {
        MixpanelManager.shared.conversationReprocessed(conversationId: conversationId, appId: appId)
        PostHogManager.shared.conversationReprocessed(conversationId: conversationId, appId: appId)
    }

    // MARK: - Settings Events (Additional)

    func settingToggled(setting: String, enabled: Bool) {
        MixpanelManager.shared.settingToggled(setting: setting, enabled: enabled)
        PostHogManager.shared.settingToggled(setting: setting, enabled: enabled)
    }

    func languageChanged(language: String) {
        MixpanelManager.shared.languageChanged(language: language)
        PostHogManager.shared.languageChanged(language: language)
    }

    // MARK: - Launch At Login Events

    /// Track launch at login status once per app launch (not continuously)
    func launchAtLoginStatusChecked(enabled: Bool) {
        MixpanelManager.shared.launchAtLoginStatusChecked(enabled: enabled)
        PostHogManager.shared.launchAtLoginStatusChecked(enabled: enabled)
    }

    /// Track when launch at login state changes
    /// - Parameters:
    ///   - enabled: New state
    ///   - source: What triggered the change (user, migration, onboarding)
    func launchAtLoginChanged(enabled: Bool, source: String) {
        MixpanelManager.shared.launchAtLoginChanged(enabled: enabled, source: source)
        PostHogManager.shared.launchAtLoginChanged(enabled: enabled, source: source)
    }

    // MARK: - Feedback Events

    func feedbackOpened() {
        MixpanelManager.shared.feedbackOpened()
        PostHogManager.shared.feedbackOpened()
    }

    func feedbackSubmitted(feedbackLength: Int) {
        MixpanelManager.shared.feedbackSubmitted(feedbackLength: feedbackLength)
        PostHogManager.shared.feedbackSubmitted(feedbackLength: feedbackLength)
    }

    // MARK: - Rewind Events (Desktop-specific)

    func rewindSearchPerformed(queryLength: Int) {
        MixpanelManager.shared.rewindSearchPerformed(queryLength: queryLength)
        PostHogManager.shared.rewindSearchPerformed(queryLength: queryLength)
    }

    func rewindScreenshotViewed(timestamp: Date) {
        MixpanelManager.shared.rewindScreenshotViewed(timestamp: timestamp)
        PostHogManager.shared.rewindScreenshotViewed(timestamp: timestamp)
    }

    func rewindTimelineNavigated(direction: String) {
        MixpanelManager.shared.rewindTimelineNavigated(direction: direction)
        PostHogManager.shared.rewindTimelineNavigated(direction: direction)
    }

    // MARK: - Proactive Assistant Events (Desktop-specific)

    func focusAlertShown(app: String) {
        MixpanelManager.shared.focusAlertShown(app: app)
        PostHogManager.shared.focusAlertShown(app: app)
    }

    func focusAlertDismissed(app: String, action: String) {
        MixpanelManager.shared.focusAlertDismissed(app: app, action: action)
        PostHogManager.shared.focusAlertDismissed(app: app, action: action)
    }

    func taskExtracted(taskCount: Int) {
        MixpanelManager.shared.taskExtracted(taskCount: taskCount)
        PostHogManager.shared.taskExtracted(taskCount: taskCount)
    }

    func taskPromoted(taskCount: Int) {
        MixpanelManager.shared.taskPromoted(taskCount: taskCount)
        PostHogManager.shared.taskPromoted(taskCount: taskCount)
    }

    func memoryExtracted(memoryCount: Int) {
        MixpanelManager.shared.memoryExtracted(memoryCount: memoryCount)
        PostHogManager.shared.memoryExtracted(memoryCount: memoryCount)
    }

    func adviceGenerated(category: String?) {
        MixpanelManager.shared.adviceGenerated(category: category)
        PostHogManager.shared.adviceGenerated(category: category)
    }

    // MARK: - Apps Events

    func appEnabled(appId: String, appName: String) {
        MixpanelManager.shared.appEnabled(appId: appId, appName: appName)
        PostHogManager.shared.appEnabled(appId: appId, appName: appName)
    }

    func appDisabled(appId: String, appName: String) {
        MixpanelManager.shared.appDisabled(appId: appId, appName: appName)
        PostHogManager.shared.appDisabled(appId: appId, appName: appName)
    }

    func appDetailViewed(appId: String, appName: String) {
        MixpanelManager.shared.appDetailViewed(appId: appId, appName: appName)
        PostHogManager.shared.appDetailViewed(appId: appId, appName: appName)
    }

    // MARK: - Update Events

    func updateCheckStarted() {
        MixpanelManager.shared.updateCheckStarted()
        PostHogManager.shared.updateCheckStarted()
    }

    func updateAvailable(version: String) {
        MixpanelManager.shared.updateAvailable(version: version)
        PostHogManager.shared.updateAvailable(version: version)
    }

    func updateInstalled(version: String) {
        MixpanelManager.shared.updateInstalled(version: version)
        PostHogManager.shared.updateInstalled(version: version)
    }

    func updateNotFound() {
        MixpanelManager.shared.updateNotFound()
        PostHogManager.shared.updateNotFound()
    }

    func updateCheckFailed(error: String, errorDomain: String, errorCode: Int, underlyingError: String? = nil, underlyingDomain: String? = nil, underlyingCode: Int? = nil) {
        MixpanelManager.shared.updateCheckFailed(error: error, errorDomain: errorDomain, errorCode: errorCode, underlyingError: underlyingError, underlyingDomain: underlyingDomain, underlyingCode: underlyingCode)
        PostHogManager.shared.updateCheckFailed(error: error, errorDomain: errorDomain, errorCode: errorCode, underlyingError: underlyingError, underlyingDomain: underlyingDomain, underlyingCode: underlyingCode)
    }

    // MARK: - Notification Events

    func notificationSent(notificationId: String, title: String, assistantId: String) {
        MixpanelManager.shared.notificationSent(notificationId: notificationId, title: title, assistantId: assistantId)
        PostHogManager.shared.notificationSent(notificationId: notificationId, title: title, assistantId: assistantId)
    }

    func notificationClicked(notificationId: String, title: String, assistantId: String) {
        MixpanelManager.shared.notificationClicked(notificationId: notificationId, title: title, assistantId: assistantId)
        PostHogManager.shared.notificationClicked(notificationId: notificationId, title: title, assistantId: assistantId)
    }

    func notificationDismissed(notificationId: String, title: String, assistantId: String) {
        MixpanelManager.shared.notificationDismissed(notificationId: notificationId, title: title, assistantId: assistantId)
        PostHogManager.shared.notificationDismissed(notificationId: notificationId, title: title, assistantId: assistantId)
    }

    func notificationWillPresent(notificationId: String, title: String) {
        MixpanelManager.shared.notificationWillPresent(notificationId: notificationId, title: title)
        PostHogManager.shared.notificationWillPresent(notificationId: notificationId, title: title)
    }

    func notificationDelegateReady() {
        MixpanelManager.shared.notificationDelegateReady()
        PostHogManager.shared.notificationDelegateReady()
    }

    // MARK: - Menu Bar Events

    /// Track when user opens the menu bar dropdown
    func menuBarOpened() {
        MixpanelManager.shared.menuBarOpened()
        PostHogManager.shared.menuBarOpened()
    }

    /// Track when user clicks an action in the menu bar
    func menuBarActionClicked(action: String) {
        MixpanelManager.shared.menuBarActionClicked(action: action)
        PostHogManager.shared.menuBarActionClicked(action: action)
    }

    // MARK: - Tier Events

    func tierChanged(tier: Int, reason: String) {
        MixpanelManager.shared.tierChanged(tier: tier, reason: reason)
        PostHogManager.shared.tierChanged(tier: tier, reason: reason)
    }

    func chatBridgeModeChanged(from oldMode: String, to newMode: String) {
        MixpanelManager.shared.chatBridgeModeChanged(from: oldMode, to: newMode)
        PostHogManager.shared.chatBridgeModeChanged(from: oldMode, to: newMode)
    }

    // MARK: - Settings State

    /// Track the current state of key settings (screenshots, memory extraction, notifications)
    /// Called when monitoring starts and daily while monitoring is active
    func trackSettingsState(screenshotsEnabled: Bool, memoryExtractionEnabled: Bool, memoryNotificationsEnabled: Bool) {
        MixpanelManager.shared.settingsStateTracked(screenshotsEnabled: screenshotsEnabled, memoryExtractionEnabled: memoryExtractionEnabled, memoryNotificationsEnabled: memoryNotificationsEnabled)
        PostHogManager.shared.settingsStateTracked(screenshotsEnabled: screenshotsEnabled, memoryExtractionEnabled: memoryExtractionEnabled, memoryNotificationsEnabled: memoryNotificationsEnabled)
    }

    // MARK: - All Settings State (Comprehensive daily report)

    private let lastAllSettingsReportKey = "lastAllSettingsReportDate"

    /// Report comprehensive settings state on app launch, throttled to once per calendar day.
    /// Sends all ~45 user settings as a single analytics event for unified visibility.
    func reportAllSettingsIfNeeded() {
        guard !Self.isDevBuild else { return }

        let defaults = UserDefaults.standard
        let lastReport = defaults.object(forKey: lastAllSettingsReportKey) as? Date ?? .distantPast
        guard !Calendar.current.isDateInToday(lastReport) else {
            log("Analytics: All settings already reported today, skipping")
            return
        }

        defaults.set(Date(), forKey: lastAllSettingsReportKey)

        let properties = collectAllSettings()

        MixpanelManager.shared.allSettingsStateTracked(properties: properties)
        PostHogManager.shared.allSettingsStateTracked(properties: properties)

        log("Analytics: All settings state reported (\(properties.count) properties)")
    }

    /// Collect all user settings into a flat dictionary for analytics reporting.
    /// For string settings (custom prompts), reports has_custom + length instead of full text.
    /// For array settings (excluded apps, keywords), reports count instead of contents.
    private func collectAllSettings() -> [String: Any] {
        var props: [String: Any] = [:]

        // -- General / Shared Assistant Settings --
        let shared = AssistantSettings.shared
        props["screen_analysis_enabled"] = shared.screenAnalysisEnabled
        props["transcription_enabled"] = shared.transcriptionEnabled
        props["transcription_language"] = shared.transcriptionLanguage
        props["transcription_auto_detect"] = shared.transcriptionAutoDetect
        props["transcription_vocabulary_count"] = shared.transcriptionVocabulary.count
        props["analysis_delay"] = shared.analysisDelay
        props["cooldown_interval"] = shared.cooldownInterval
        props["glow_overlay_enabled"] = shared.glowOverlayEnabled

        // -- Focus Assistant --
        let focus = FocusAssistantSettings.shared
        props["focus_enabled"] = focus.isEnabled
        props["focus_notifications_enabled"] = focus.notificationsEnabled
        props["focus_cooldown_interval"] = focus.cooldownInterval
        props["focus_has_custom_prompt"] = focus.analysisPrompt != FocusAssistantSettings.defaultAnalysisPrompt
        props["focus_prompt_length"] = focus.analysisPrompt.count
        props["focus_excluded_apps_count"] = focus.excludedApps.count

        // -- Task Extraction Assistant --
        let task = TaskAssistantSettings.shared
        props["task_enabled"] = task.isEnabled
        props["task_notifications_enabled"] = task.notificationsEnabled
        props["task_extraction_interval"] = task.extractionInterval
        props["task_min_confidence"] = task.minConfidence
        props["task_has_custom_prompt"] = task.analysisPrompt != TaskAssistantSettings.defaultAnalysisPrompt
        props["task_prompt_length"] = task.analysisPrompt.count
        props["task_allowed_apps_count"] = task.allowedApps.count
        props["task_browser_keywords_count"] = task.browserKeywords.count

        // -- Memory Assistant --
        let memory = MemoryAssistantSettings.shared
        props["memory_enabled"] = memory.isEnabled
        props["memory_extraction_interval"] = memory.extractionInterval
        props["memory_min_confidence"] = memory.minConfidence
        props["memory_notifications_enabled"] = memory.notificationsEnabled
        props["memory_has_custom_prompt"] = memory.analysisPrompt != MemoryAssistantSettings.defaultAnalysisPrompt
        props["memory_prompt_length"] = memory.analysisPrompt.count
        props["memory_excluded_apps_count"] = memory.excludedApps.count

        // -- Advice Assistant --
        let advice = AdviceAssistantSettings.shared
        props["advice_enabled"] = advice.isEnabled
        props["advice_notifications_enabled"] = advice.notificationsEnabled
        props["advice_extraction_interval"] = advice.extractionInterval
        props["advice_min_confidence"] = advice.minConfidence
        props["advice_has_custom_prompt"] = advice.analysisPrompt != AdviceAssistantSettings.defaultAnalysisPrompt
        props["advice_prompt_length"] = advice.analysisPrompt.count
        props["advice_excluded_apps_count"] = advice.excludedApps.count

        // -- Task Agent --
        let agent = TaskAgentSettings.shared
        props["task_agent_enabled"] = agent.isEnabled
        props["task_agent_auto_launch"] = agent.autoLaunch
        props["task_agent_skip_permissions"] = agent.skipPermissions
        props["task_agent_has_custom_prompt"] = !agent.customPromptPrefix.isEmpty

        // -- Rewind (read from UserDefaults since these are @AppStorage in views) --
        let ud = UserDefaults.standard
        props["rewind_retention_days"] = ud.object(forKey: "rewindRetentionDays") as? Double ?? 7.0
        props["rewind_capture_interval"] = ud.object(forKey: "rewindCaptureInterval") as? Double ?? 1.0

        // -- AI Chat Mode --
        props["chat_bridge_mode"] = ud.string(forKey: "chatBridgeMode") ?? "agentSDK"

        // -- UI Preferences --
        props["multi_chat_enabled"] = ud.bool(forKey: "multiChatEnabled")
        props["conversations_compact_view"] = ud.object(forKey: "conversationsCompactView") as? Bool ?? true
        props["tier_level"] = ud.integer(forKey: "currentTierLevel")

        // -- Device --
        let deviceId = ud.string(forKey: "pairedDeviceId") ?? ""
        props["has_paired_device"] = !deviceId.isEmpty
        props["paired_device_type"] = ud.string(forKey: "pairedDeviceType") ?? ""

        // -- Launch at Login --
        props["launch_at_login_enabled"] = LaunchAtLoginManager.shared.isEnabled

        // -- Floating Bar (AskOmi) --
        props["floating_bar_enabled"] = FloatingControlBarManager.shared.isEnabled
        props["floating_bar_visible"] = FloatingControlBarManager.shared.isVisible

        // -- Dev Mode --
        props["dev_mode_enabled"] = ud.bool(forKey: "devModeEnabled")

        return props
    }

    // MARK: - Floating Bar Events

    /// Track when the floating bar is toggled visible/hidden
    func floatingBarToggled(visible: Bool, source: String) {
        let props: [String: Any] = [
            "visible": visible,
            "source": source
        ]
        MixpanelManager.shared.track("Floating Bar Toggled", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("floating_bar_toggled", properties: props)
    }

    /// Track when Ask OMI is opened (AI input panel shown)
    func floatingBarAskOmiOpened(source: String) {
        let props: [String: Any] = ["source": source]
        MixpanelManager.shared.track("Floating Bar Ask OMI Opened", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("floating_bar_ask_omi_opened", properties: props)
    }

    /// Track when the AI conversation is closed
    func floatingBarAskOmiClosed() {
        MixpanelManager.shared.track("Floating Bar Ask OMI Closed")
        PostHogManager.shared.track("floating_bar_ask_omi_closed")
    }

    /// Track when an AI query is sent from the floating bar
    func floatingBarQuerySent(messageLength: Int, hasScreenshot: Bool) {
        let props: [String: Any] = [
            "message_length": messageLength,
            "has_screenshot": hasScreenshot
        ]
        MixpanelManager.shared.track("Floating Bar Query Sent", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("floating_bar_query_sent", properties: props)
    }

    /// Track when push-to-talk starts listening
    func floatingBarPTTStarted(mode: String) {
        let props: [String: Any] = ["mode": mode]
        MixpanelManager.shared.track("Floating Bar PTT Started", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("floating_bar_ptt_started", properties: props)
    }

    /// Track when push-to-talk ends and sends (or discards) transcript
    func floatingBarPTTEnded(mode: String, hadTranscript: Bool, transcriptLength: Int) {
        let props: [String: Any] = [
            "mode": mode,
            "had_transcript": hadTranscript,
            "transcript_length": transcriptLength
        ]
        MixpanelManager.shared.track("Floating Bar PTT Ended", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("floating_bar_ptt_ended", properties: props)
    }

    // MARK: - Knowledge Graph Events

    /// Track when knowledge graph generation starts during onboarding
    func knowledgeGraphBuildStarted(filesIndexed: Int, hadExistingGraph: Bool) {
        let props: [String: Any] = [
            "files_indexed": filesIndexed,
            "had_existing_graph": hadExistingGraph
        ]
        MixpanelManager.shared.track("Knowledge Graph Build Started", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("knowledge_graph_build_started", properties: props)
    }

    /// Track when knowledge graph generation completes (successfully loaded with data)
    func knowledgeGraphBuildCompleted(nodeCount: Int, edgeCount: Int, pollAttempts: Int, hadExistingGraph: Bool) {
        let props: [String: Any] = [
            "node_count": nodeCount,
            "edge_count": edgeCount,
            "poll_attempts": pollAttempts,
            "had_existing_graph": hadExistingGraph
        ]
        MixpanelManager.shared.track("Knowledge Graph Build Completed", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("knowledge_graph_build_completed", properties: props)
    }

    /// Track when knowledge graph generation fails or times out empty
    func knowledgeGraphBuildFailed(reason: String, pollAttempts: Int, filesIndexed: Int) {
        let props: [String: Any] = [
            "reason": reason,
            "poll_attempts": pollAttempts,
            "files_indexed": filesIndexed
        ]
        MixpanelManager.shared.track("Knowledge Graph Build Failed", properties: props.compactMapValues { $0 as? MixpanelType })
        PostHogManager.shared.track("knowledge_graph_build_failed", properties: props)
    }

    // MARK: - Display Info

    /// Track display characteristics (notch, screen size, etc.)
    /// Called at app launch to help diagnose menu bar visibility issues
    func trackDisplayInfo() {
        guard let screen = NSScreen.main else { return }

        let frame = screen.frame
        let visibleFrame = screen.visibleFrame
        let safeAreaInsets = screen.safeAreaInsets

        // Detect notch: MacBooks with notch have safeAreaInsets.top > 0
        let hasNotch = safeAreaInsets.top > 0

        // Calculate menu bar height (difference between frame and visible frame at top)
        let menuBarHeight = frame.height - visibleFrame.height - visibleFrame.origin.y

        let displayInfo: [String: Any] = [
            "screen_width": Int(frame.width),
            "screen_height": Int(frame.height),
            "has_notch": hasNotch,
            "safe_area_top": Int(safeAreaInsets.top),
            "menu_bar_height": Int(menuBarHeight),
            "scale_factor": screen.backingScaleFactor
        ]

        MixpanelManager.shared.displayInfoTracked(info: displayInfo)
        PostHogManager.shared.displayInfoTracked(info: displayInfo)
    }
}
