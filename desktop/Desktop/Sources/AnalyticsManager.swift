import AppKit
import Foundation

/// Unified analytics manager that sends events to PostHog.
/// Use this instead of calling PostHogManager directly
@MainActor
class AnalyticsManager {
  static let shared = AnalyticsManager()

  /// Returns true for non-production Omi bundles so test apps don't pollute production analytics.
  nonisolated static var isDevBuild: Bool {
    AppBuild.isNonProduction
  }

  private var lastTranscriptionStartedAt: Date?

  private init() {}

  // MARK: - Initialization

  func initialize() {
    // Skip analytics in development builds
    guard !Self.isDevBuild else {
      log("Analytics: Skipping initialization (development build)")
      return
    }
    PostHogManager.shared.initialize()
  }

  // MARK: - User Identification

  func identify() {
    PostHogManager.shared.identify()
  }

  func reset() {
    PostHogManager.shared.reset()
  }

  // MARK: - Opt In/Out

  func optInTracking() {
    PostHogManager.shared.optIn()
  }

  func optOutTracking() {
    PostHogManager.shared.optOut()
  }

  // MARK: - Onboarding Events

  func onboardingStepCompleted(step: Int, stepName: String) {
    PostHogManager.shared.onboardingStepCompleted(step: step, stepName: stepName)
  }

  func onboardingHowDidYouHear(source: String) {
    let props: [String: Any] = ["source": source, "is_referral": source == "Friend"]
    PostHogManager.shared.track("Onboarding How Did You Hear", properties: props)
  }

  func onboardingCompleted() {
    PostHogManager.shared.onboardingCompleted()
  }

  func onboardingChatToolUsed(tool: String, properties: [String: Any] = [:]) {
    var props = properties
    props["tool"] = tool
    PostHogManager.shared.track("Onboarding Chat Tool Used", properties: props)
  }

  func onboardingChatMessage(role: String, step: String) {
    let props: [String: Any] = ["role": role, "step": step]
    PostHogManager.shared.track("Onboarding Chat Message", properties: props)
  }

  /// Track full onboarding chat message content for debugging user issues.
  func onboardingChatMessageDetailed(role: String, text: String, step: String, toolCalls: [String]? = nil, model: String? = nil, error: String? = nil) {
    var props: [String: Any] = [
      "role": role,
      "step": step,
      "text": String(text.prefix(2000)),
      "text_length": text.count,
    ]
    if let toolCalls = toolCalls, !toolCalls.isEmpty {
      props["tool_calls"] = toolCalls.joined(separator: ", ")
    }
    if let model = model { props["model"] = model }
    if let error = error { props["error"] = error }
    PostHogManager.shared.track("onboarding_chat_message_detailed", properties: props)
  }

  // MARK: - Authentication Events

  func signInStarted(provider: String) {
    PostHogManager.shared.signInStarted(provider: provider)
  }

  func signInCompleted(provider: String) {
    PostHogManager.shared.signInCompleted(provider: provider)
  }

  func signInFailed(provider: String, error: String) {
    PostHogManager.shared.signInFailed(provider: provider, error: error)
  }

  func signedOut() {
    PostHogManager.shared.signedOut()
  }

  // MARK: - Monitoring Events

  func monitoringStarted() {
    PostHogManager.shared.monitoringStarted()
  }

  func monitoringStopped() {
    PostHogManager.shared.monitoringStopped()
  }

  func distractionDetected(app: String, windowTitle: String?) {
    PostHogManager.shared.distractionDetected(app: app, windowTitle: windowTitle)
  }

  func focusRestored(app: String) {
    PostHogManager.shared.focusRestored(app: app)
  }

  // MARK: - Recording Events

  func transcriptionStarted() {
    // Debounce: skip if called within 5 seconds (catches rapid wake/reconnect double-fires)
    if let last = lastTranscriptionStartedAt, Date().timeIntervalSince(last) < 5 {
      return
    }
    lastTranscriptionStartedAt = Date()
    PostHogManager.shared.transcriptionStarted()
  }

  func transcriptionStopped(wordCount: Int) {
    PostHogManager.shared.transcriptionStopped(wordCount: wordCount)
  }

  func recordingError(error: String) {
    PostHogManager.shared.recordingError(error: error)
  }

  // MARK: - Permission Events

  func permissionRequested(permission: String, extraProperties: [String: Any] = [:]) {
    PostHogManager.shared.permissionRequested(
      permission: permission, extraProperties: extraProperties)
  }

  func permissionGranted(permission: String, extraProperties: [String: Any] = [:]) {
    PostHogManager.shared.permissionGranted(
      permission: permission, extraProperties: extraProperties)
  }

  func permissionDenied(permission: String, extraProperties: [String: Any] = [:]) {
    PostHogManager.shared.permissionDenied(permission: permission, extraProperties: extraProperties)
  }

  func permissionSkipped(permission: String, extraProperties: [String: Any] = [:]) {
    PostHogManager.shared.permissionSkipped(
      permission: permission, extraProperties: extraProperties)
  }

  /// Track Bluetooth state changes for debugging
  func bluetoothStateChanged(
    oldState: String, newState: String, oldStateRaw: Int, newStateRaw: Int, authorization: String,
    authorizationRaw: Int
  ) {
    let properties: [String: Any] = [
      "old_state": oldState,
      "new_state": newState,
      "old_state_raw": oldStateRaw,
      "new_state_raw": newStateRaw,
      "authorization": authorization,
      "authorization_raw": authorizationRaw,
    ]
    PostHogManager.shared.track("Bluetooth State Changed", properties: properties)
  }

  /// Track when ScreenCaptureKit broken state is detected (TCC granted but capture failing)
  func screenCaptureBrokenDetected() {
    PostHogManager.shared.screenCaptureBrokenDetected()
  }

  /// Track when user clicks reset button or notification to reset screen capture
  func screenCaptureResetClicked(source: String) {
    PostHogManager.shared.screenCaptureResetClicked(source: source)
  }

  /// Track when screen capture reset completes (success or failure)
  func screenCaptureResetCompleted(success: Bool) {
    PostHogManager.shared.screenCaptureResetCompleted(success: success)
  }

  /// Track when notification repair is triggered (auto-repair or error-triggered)
  func notificationRepairTriggered(reason: String, previousStatus: String, currentStatus: String) {
    PostHogManager.shared.notificationRepairTriggered(
      reason: reason, previousStatus: previousStatus, currentStatus: currentStatus)
  }

  /// Track notification settings status (auth, alertStyle, sound, badge)
  func notificationSettingsChecked(
    authStatus: String,
    alertStyle: String,
    soundEnabled: Bool,
    badgeEnabled: Bool,
    bannersDisabled: Bool
  ) {
    PostHogManager.shared.notificationSettingsChecked(
      authStatus: authStatus,
      alertStyle: alertStyle,
      soundEnabled: soundEnabled,
      badgeEnabled: badgeEnabled,
      bannersDisabled: bannersDisabled
    )
  }

  // MARK: - Crash Detection

  /// Detect if the previous session crashed (no clean exit) and report to PostHog.
  /// Must be called AFTER analytics initialization but BEFORE appLaunched().
  func detectAndReportCrash() {
    guard !Self.isDevBuild else { return }

    let cleanExitKey = "lastSessionCleanExit"
    let hasLaunchedBeforeKey = "crashDetection_hasLaunchedBefore"

    let hadPreviousSession = UserDefaults.standard.bool(forKey: hasLaunchedBeforeKey)
    let lastCleanExit = UserDefaults.standard.bool(forKey: cleanExitKey)

    // Mark that we've launched at least once (skip crash report on very first launch)
    UserDefaults.standard.set(true, forKey: hasLaunchedBeforeKey)

    // Clear the flag — will be set back to true only on clean exit
    UserDefaults.standard.set(false, forKey: cleanExitKey)

    if hadPreviousSession && !lastCleanExit {
      log("Analytics: Previous session did not exit cleanly — reporting crash")
      let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
      PostHogManager.shared.track("App Crash Detected", properties: [
        "app_version": version,
        "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
      ])
    }
  }

  // MARK: - App Lifecycle Events

  func appLaunched() {
    PostHogManager.shared.appLaunched()
  }

  func trackStartupTiming(
    dbInitMs: Double, timeToInteractiveMs: Double, hadUncleanShutdown: Bool,
    databaseInitFailed: Bool
  ) {
    guard !Self.isDevBuild else { return }
    let properties: [String: Any] = [
      "db_init_ms": round(dbInitMs),
      "time_to_interactive_ms": round(timeToInteractiveMs),
      "had_unclean_shutdown": hadUncleanShutdown,
      "database_init_failed": databaseInitFailed,
    ]
    PostHogManager.shared.track("App Startup Timing", properties: properties)
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

    // Track in all analytics systems
    PostHogManager.shared.firstLaunch(diagnostics: diagnostics)

    log("Analytics: First launch diagnostics tracked")
  }

  /// Collect comprehensive system diagnostics for first launch event
  private func collectSystemDiagnostics() -> [String: Any] {
    var diagnostics: [String: Any] = [:]

    // App version
    diagnostics["app_version"] =
      Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    diagnostics["build_number"] =
      Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"

    // macOS version (detailed)
    let osVersion = ProcessInfo.processInfo.operatingSystemVersion
    diagnostics["os_version"] =
      "\(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)"
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
    PostHogManager.shared.appBecameActive()
  }

  func appResignedActive() {
    PostHogManager.shared.appResignedActive()
  }

  // MARK: - Conversation Events
  // Note: The event is named "Memory Created" in analytics for historical reasons,
  // but it actually tracks when a conversation/recording is created, not a "memory".

  func conversationCreated(conversationId: String, source: String, durationSeconds: Int? = nil) {
    PostHogManager.shared.conversationCreated(
      conversationId: conversationId, source: source, durationSeconds: durationSeconds)
  }

  func memoryDeleted(conversationId: String) {
    PostHogManager.shared.memoryDeleted(conversationId: conversationId)
  }

  func memoryShareButtonClicked(conversationId: String) {
    PostHogManager.shared.memoryShareButtonClicked(conversationId: conversationId)
  }

  func shareAction(category: String, properties: [String: Any] = [:]) {
    var props = properties
    props["category"] = category
    PostHogManager.shared.track("Share Action", properties: props)
  }

  func memoryListItemClicked(conversationId: String) {
    PostHogManager.shared.memoryListItemClicked(conversationId: conversationId)
  }

  // MARK: - Chat Events

  func chatMessageSent(messageLength: Int, hasContext: Bool = false, source: String) {
    PostHogManager.shared.chatMessageSent(
      messageLength: messageLength, hasContext: hasContext, source: source)
  }

  // MARK: - Search Events

  func searchQueryEntered(query: String) {
    PostHogManager.shared.searchQueryEntered(query: query)
  }

  func searchBarFocused() {
    PostHogManager.shared.searchBarFocused()
  }

  // MARK: - Settings Events

  func settingsPageOpened() {
    PostHogManager.shared.settingsPageOpened()
  }

  // MARK: - Page/Screen Views (PostHog specific, but tracked in both)

  func pageViewed(_ pageName: String) {
    PostHogManager.shared.pageViewed(pageName)
  }

  // MARK: - Account Events

  func deleteAccountClicked() {
    PostHogManager.shared.deleteAccountClicked()
  }

  func deleteAccountConfirmed() {
    PostHogManager.shared.deleteAccountConfirmed()
  }

  func deleteAccountCancelled() {
    PostHogManager.shared.deleteAccountCancelled()
  }

  // MARK: - Navigation Events

  func tabChanged(tabName: String) {
    PostHogManager.shared.tabChanged(tabName: tabName)
  }

  func conversationDetailOpened(conversationId: String) {
    PostHogManager.shared.conversationDetailOpened(conversationId: conversationId)
  }

  // MARK: - Chat Events (Additional)

  func chatAppSelected(appId: String?, appName: String?) {
    PostHogManager.shared.chatAppSelected(appId: appId, appName: appName)
  }

  func chatCleared() {
    PostHogManager.shared.chatCleared()
  }

  func chatSessionCreated() {
    PostHogManager.shared.track("chat_session_created", properties: [:])
  }

  func chatSessionDeleted() {
    PostHogManager.shared.track("chat_session_deleted", properties: [:])
  }

  func messageRated(rating: Int) {
    let ratingString = rating == 1 ? "thumbs_up" : "thumbs_down"
    PostHogManager.shared.track("message_rated", properties: ["rating": ratingString])
  }

  func initialMessageGenerated(hasApp: Bool) {
    PostHogManager.shared.track("initial_message_generated", properties: ["has_app": hasApp])
  }

  func sessionTitleGenerated() {
    PostHogManager.shared.track("session_title_generated", properties: [:])
  }

  func chatStarredFilterToggled(enabled: Bool) {
    PostHogManager.shared.track("chat_starred_filter_toggled", properties: ["enabled": enabled])
  }

  func sessionRenamed() {
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
      "response_length": messageLength,
    ]
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
      "duration_ms": durationMs,
    ]
    PostHogManager.shared.track("chat_tool_call_completed", properties: props)
  }

  /// Track when the Claude agent bridge fails to start or errors
  func chatAgentError(error: String, rawError: String? = nil) {
    var props: [String: Any] = ["error": error]
    if let raw = rawError, raw != error {
      props["raw_error"] = String(raw.prefix(500))
    }
    PostHogManager.shared.track("chat_agent_error", properties: props)
  }

  // MARK: - Conversation Events (Additional)

  func conversationReprocessed(conversationId: String, appId: String) {
    PostHogManager.shared.conversationReprocessed(conversationId: conversationId, appId: appId)
  }

  // MARK: - Settings Events (Additional)

  func settingToggled(setting: String, enabled: Bool) {
    PostHogManager.shared.settingToggled(setting: setting, enabled: enabled)
  }

  func languageChanged(language: String) {
    PostHogManager.shared.languageChanged(language: language)
  }

  // MARK: - Launch At Login Events

  /// Track launch at login status once per app launch (not continuously)
  func launchAtLoginStatusChecked(enabled: Bool) {
    PostHogManager.shared.launchAtLoginStatusChecked(enabled: enabled)
  }

  /// Track when launch at login state changes
  /// - Parameters:
  ///   - enabled: New state
  ///   - source: What triggered the change (user, migration, onboarding)
  func launchAtLoginChanged(enabled: Bool, source: String) {
    PostHogManager.shared.launchAtLoginChanged(enabled: enabled, source: source)
  }

  // MARK: - Feedback Events

  func feedbackOpened() {
    PostHogManager.shared.feedbackOpened()
  }

  func feedbackSubmitted(feedbackLength: Int) {
    PostHogManager.shared.feedbackSubmitted(feedbackLength: feedbackLength)
  }

  // MARK: - Rewind Events (Desktop-specific)

  func rewindSearchPerformed(queryLength: Int) {
    PostHogManager.shared.rewindSearchPerformed(queryLength: queryLength)
  }

  func rewindScreenshotViewed(timestamp: Date) {
    PostHogManager.shared.rewindScreenshotViewed(timestamp: timestamp)
  }

  func rewindTimelineNavigated(direction: String) {
    PostHogManager.shared.rewindTimelineNavigated(direction: direction)
  }

  // MARK: - Proactive Assistant Events (Desktop-specific)

  func focusAlertShown(app: String) {
    PostHogManager.shared.focusAlertShown(app: app)
  }

  func focusAlertDismissed(app: String, action: String) {
    PostHogManager.shared.focusAlertDismissed(app: app, action: action)
  }

  func taskExtracted(taskCount: Int) {
    PostHogManager.shared.taskExtracted(taskCount: taskCount)
  }

  func taskPromoted(taskCount: Int) {
    PostHogManager.shared.taskPromoted(taskCount: taskCount)
  }

  func taskCompleted(source: String?) {
    PostHogManager.shared.taskCompleted(source: source)
  }

  func taskDeleted(source: String?) {
    PostHogManager.shared.taskDeleted(source: source)
  }

  func taskAdded() {
    PostHogManager.shared.taskAdded()
  }

  func memoryExtracted(memoryCount: Int) {
    PostHogManager.shared.memoryExtracted(memoryCount: memoryCount)
  }

  func insightGenerated(category: String?) {
    PostHogManager.shared.insightGenerated(category: category)
  }

  // MARK: - Apps Events

  func appEnabled(appId: String, appName: String) {
    PostHogManager.shared.appEnabled(appId: appId, appName: appName)
  }

  func appDisabled(appId: String, appName: String) {
    PostHogManager.shared.appDisabled(appId: appId, appName: appName)
  }

  func appDetailViewed(appId: String, appName: String) {
    PostHogManager.shared.appDetailViewed(appId: appId, appName: appName)
  }

  // MARK: - Update Events

  func updateCheckStarted() {
    PostHogManager.shared.updateCheckStarted()
  }

  func updateAvailable(version: String) {
    PostHogManager.shared.updateAvailable(version: version)
  }

  func updateInstalled(version: String) {
    PostHogManager.shared.updateInstalled(version: version)
  }

  func updateNotFound() {
    PostHogManager.shared.updateNotFound()
  }

  func updateCheckFailed(
    error: String, errorDomain: String, errorCode: Int, underlyingError: String? = nil,
    underlyingDomain: String? = nil, underlyingCode: Int? = nil
  ) {
    PostHogManager.shared.updateCheckFailed(
      error: error, errorDomain: errorDomain, errorCode: errorCode,
      underlyingError: underlyingError, underlyingDomain: underlyingDomain,
      underlyingCode: underlyingCode)
  }

  // MARK: - Notification Events

  func notificationSent(notificationId: String, title: String, assistantId: String, surface: String) {
    PostHogManager.shared.notificationSent(
      notificationId: notificationId, title: title, assistantId: assistantId, surface: surface)
  }

  func notificationClicked(notificationId: String, title: String, assistantId: String, surface: String) {
    PostHogManager.shared.notificationClicked(
      notificationId: notificationId, title: title, assistantId: assistantId, surface: surface)
  }

  func notificationDismissed(notificationId: String, title: String, assistantId: String, surface: String) {
    PostHogManager.shared.notificationDismissed(
      notificationId: notificationId, title: title, assistantId: assistantId, surface: surface)
  }

  func notificationWillPresent(notificationId: String, title: String) {
    PostHogManager.shared.notificationWillPresent(notificationId: notificationId, title: title)
  }

  func notificationDelegateReady() {
    PostHogManager.shared.notificationDelegateReady()
  }

  // MARK: - Menu Bar Events

  /// Track when user opens the menu bar dropdown
  func menuBarOpened() {
    PostHogManager.shared.menuBarOpened()
  }

  /// Track when user clicks an action in the menu bar
  func menuBarActionClicked(action: String) {
    PostHogManager.shared.menuBarActionClicked(action: action)
  }

  // MARK: - Tier Events

  func tierChanged(tier: Int, reason: String) {
    PostHogManager.shared.tierChanged(tier: tier, reason: reason)
  }

  func chatBridgeModeChanged(from oldMode: String, to newMode: String) {
    PostHogManager.shared.chatBridgeModeChanged(from: oldMode, to: newMode)
  }

  // MARK: - Settings State

  /// Track the current state of key settings (screenshots, memory extraction, notifications)
  /// Called when monitoring starts and daily while monitoring is active
  func trackSettingsState(
    screenshotsEnabled: Bool, memoryExtractionEnabled: Bool, memoryNotificationsEnabled: Bool
  ) {
    PostHogManager.shared.settingsStateTracked(
      screenshotsEnabled: screenshotsEnabled, memoryExtractionEnabled: memoryExtractionEnabled,
      memoryNotificationsEnabled: memoryNotificationsEnabled)
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
    props["focus_has_custom_prompt"] =
      focus.analysisPrompt != FocusAssistantSettings.defaultAnalysisPrompt
    props["focus_prompt_length"] = focus.analysisPrompt.count
    props["focus_excluded_apps_count"] = focus.excludedApps.count

    // -- Task Extraction Assistant --
    let task = TaskAssistantSettings.shared
    props["task_enabled"] = task.isEnabled
    props["task_notifications_enabled"] = task.notificationsEnabled
    props["task_extraction_interval"] = task.extractionInterval
    props["task_min_confidence"] = task.minConfidence
    props["task_has_custom_prompt"] =
      task.analysisPrompt != TaskAssistantSettings.defaultAnalysisPrompt
    props["task_prompt_length"] = task.analysisPrompt.count
    props["task_allowed_apps_count"] = task.allowedApps.count
    props["task_browser_keywords_count"] = task.browserKeywords.count

    // -- Memory Assistant --
    let memory = MemoryAssistantSettings.shared
    props["memory_enabled"] = memory.isEnabled
    props["memory_extraction_interval"] = memory.extractionInterval
    props["memory_min_confidence"] = memory.minConfidence
    props["memory_notifications_enabled"] = memory.notificationsEnabled
    props["memory_has_custom_prompt"] =
      memory.analysisPrompt != MemoryAssistantSettings.defaultAnalysisPrompt
    props["memory_prompt_length"] = memory.analysisPrompt.count
    props["memory_excluded_apps_count"] = memory.excludedApps.count

    // -- Insight Assistant --
    let insight = InsightAssistantSettings.shared
    props["insight_enabled"] = insight.isEnabled
    props["insight_notifications_enabled"] = insight.notificationsEnabled
    props["insight_extraction_interval"] = insight.extractionInterval
    props["insight_min_confidence"] = insight.minConfidence
    props["insight_has_custom_prompt"] =
      insight.analysisPrompt != InsightAssistantSettings.defaultAnalysisPrompt
    props["insight_prompt_length"] = insight.analysisPrompt.count
    props["insight_excluded_apps_count"] = insight.excludedApps.count

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
    props["conversations_compact_view"] =
      ud.object(forKey: "conversationsCompactView") as? Bool ?? true
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
      "source": source,
    ]
    PostHogManager.shared.track("floating_bar_toggled", properties: props)
  }

  /// Track when Ask OMI is opened (AI input panel shown)
  func floatingBarAskOmiOpened(source: String) {
    let props: [String: Any] = ["source": source]
    PostHogManager.shared.track("floating_bar_ask_omi_opened", properties: props)
  }

  /// Track when the AI conversation is closed
  func floatingBarAskOmiClosed() {
    PostHogManager.shared.track("floating_bar_ask_omi_closed")
  }

  /// Track when an AI query is sent from the floating bar
  func floatingBarQuerySent(messageLength: Int, hasScreenshot: Bool) {
    let props: [String: Any] = [
      "message_length": messageLength,
      "has_screenshot": hasScreenshot,
    ]
    PostHogManager.shared.track("floating_bar_query_sent", properties: props)
  }

  /// Track when push-to-talk starts listening
  func floatingBarPTTStarted(mode: String) {
    let props: [String: Any] = ["mode": mode]
    PostHogManager.shared.track("floating_bar_ptt_started", properties: props)
  }

  /// Track when push-to-talk ends and sends (or discards) transcript
  func floatingBarPTTEnded(mode: String, hadTranscript: Bool, transcriptLength: Int) {
    let props: [String: Any] = [
      "mode": mode,
      "had_transcript": hadTranscript,
      "transcript_length": transcriptLength,
    ]
    PostHogManager.shared.track("floating_bar_ptt_ended", properties: props)
  }

  // MARK: - Knowledge Graph Events

  /// Track when knowledge graph generation starts during onboarding
  func knowledgeGraphBuildStarted(filesIndexed: Int, hadExistingGraph: Bool) {
    let props: [String: Any] = [
      "files_indexed": filesIndexed,
      "had_existing_graph": hadExistingGraph,
    ]
    PostHogManager.shared.track("knowledge_graph_build_started", properties: props)
  }

  /// Track when knowledge graph generation completes (successfully loaded with data)
  func knowledgeGraphBuildCompleted(
    nodeCount: Int, edgeCount: Int, pollAttempts: Int, hadExistingGraph: Bool
  ) {
    let props: [String: Any] = [
      "node_count": nodeCount,
      "edge_count": edgeCount,
      "poll_attempts": pollAttempts,
      "had_existing_graph": hadExistingGraph,
    ]
    PostHogManager.shared.track("knowledge_graph_build_completed", properties: props)
  }

  /// Track when knowledge graph generation fails or times out empty
  func knowledgeGraphBuildFailed(reason: String, pollAttempts: Int, filesIndexed: Int) {
    let props: [String: Any] = [
      "reason": reason,
      "poll_attempts": pollAttempts,
      "files_indexed": filesIndexed,
    ]
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
      "scale_factor": screen.backingScaleFactor,
    ]

    PostHogManager.shared.displayInfoTracked(info: displayInfo)
  }
}
