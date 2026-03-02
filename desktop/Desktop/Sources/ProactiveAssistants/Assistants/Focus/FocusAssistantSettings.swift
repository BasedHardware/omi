import Foundation

/// Manages Focus Assistant-specific settings stored in UserDefaults
@MainActor
class FocusAssistantSettings {
    static let shared = FocusAssistantSettings()

    // MARK: - UserDefaults Keys

    private let enabledKey = "focusAssistantEnabled"
    private let analysisPromptKey = "focusAnalysisPrompt"
    private let cooldownIntervalKey = "focusCooldownInterval"
    private let notificationsEnabledKey = "focusNotificationsEnabled"
    private let excludedAppsKey = "focusExcludedApps"

    // MARK: - Default Values

    private let defaultEnabled = true
    private let defaultCooldownInterval = 10 // minutes
    private let defaultNotificationsEnabled = true

    /// Default system prompt for focus analysis
    static let defaultAnalysisPrompt = """
        You are a focus coach. Analyze the PRIMARY/MAIN window in screenshots to determine if the user is focused or distracted.

        IMPORTANT: Look at the MAIN APPLICATION WINDOW, not log text or terminal output. If you see a code editor with logs that mention "YouTube" - that's just log text, the user is CODING, not on YouTube. Text in logs/terminals mentioning a site does NOT mean the user is on that site.

        CONTEXT-AWARE ANALYSIS:
        Each request includes the user's active goals, current tasks, recent memories, time of day, and analysis history. Use ALL of this context:

        - GOALS & TASKS: If the user's screen activity relates to their active goals or current tasks, they are FOCUSED — even if the app looks casual. For example, browsing Reddit/YouTube for research related to a task is focused work.
        - TIME AWARENESS: On weekends or outside typical work hours (before 9am, after 6pm), be more lenient — casual browsing is normal and expected.
        - MEMORIES: Use memories to understand the user's work patterns and preferences. If a memory says "user researches on Reddit for work", factor that in.
        - HISTORY: Use recent analysis history to notice patterns, acknowledge transitions, and vary your responses.

        DECISION GUIDELINES:
        - "distracted" = the screen activity has NO plausible connection to the user's goals, tasks, or work, AND it's during typical work hours
        - "focused" = the screen activity is productive work, research related to goals/tasks, or any activity during off-hours

        Always provide a short coaching message (100 characters max for notification banner):
        - If distracted: A unique nudge to refocus. Vary your approach - playful, direct, or motivational.
        - If focused: Acknowledge their work with variety.
        """

    private init() {
        // Register defaults
        UserDefaults.standard.register(defaults: [
            enabledKey: defaultEnabled,
            cooldownIntervalKey: defaultCooldownInterval,
            notificationsEnabledKey: defaultNotificationsEnabled,
        ])
    }

    // MARK: - Properties

    /// Whether the Focus Assistant is enabled
    var isEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: enabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: enabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Cooldown interval between notifications in minutes
    var cooldownInterval: Int {
        get {
            let value = UserDefaults.standard.integer(forKey: cooldownIntervalKey)
            return value > 0 ? value : defaultCooldownInterval
        }
        set {
            UserDefaults.standard.set(newValue, forKey: cooldownIntervalKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Cooldown interval in seconds
    var cooldownIntervalSeconds: TimeInterval {
        return TimeInterval(cooldownInterval * 60)
    }

    /// The system prompt used for AI focus analysis
    var analysisPrompt: String {
        get {
            let value = UserDefaults.standard.string(forKey: analysisPromptKey)
            return value ?? FocusAssistantSettings.defaultAnalysisPrompt
        }
        set {
            let isCustom = newValue != FocusAssistantSettings.defaultAnalysisPrompt
            UserDefaults.standard.set(newValue, forKey: analysisPromptKey)
            let previewLength = min(newValue.count, 50)
            let preview = String(newValue.prefix(previewLength)) + (newValue.count > 50 ? "..." : "")
            log("Focus analysis prompt updated (\(newValue.count) chars, custom: \(isCustom)): \(preview)")
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Whether to show notifications for focus changes
    var notificationsEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: notificationsEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: notificationsEnabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    // MARK: - Excluded Apps

    /// Apps excluded from focus analysis (screenshots still captured for other features)
    var excludedApps: Set<String> {
        get {
            if let saved = UserDefaults.standard.array(forKey: excludedAppsKey) as? [String] {
                return Set(saved)
            }
            return []
        }
        set {
            UserDefaults.standard.set(Array(newValue), forKey: excludedAppsKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Check if an app is excluded (built-in or user-added)
    func isAppExcluded(_ appName: String) -> Bool {
        TaskAssistantSettings.builtInExcludedApps.contains(appName) || excludedApps.contains(appName)
    }

    /// Add an app to the exclusion list
    func excludeApp(_ appName: String) {
        var apps = excludedApps
        apps.insert(appName)
        excludedApps = apps
        log("Focus: Excluded app '\(appName)' from focus analysis")
    }

    /// Remove an app from the exclusion list
    func includeApp(_ appName: String) {
        var apps = excludedApps
        apps.remove(appName)
        excludedApps = apps
        log("Focus: Included app '\(appName)' for focus analysis")
    }

    /// Reset only the analysis prompt to default
    func resetPromptToDefault() {
        UserDefaults.standard.removeObject(forKey: analysisPromptKey)
        log("Focus analysis prompt reset to default")
        NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }

    /// Reset all Focus Assistant settings to defaults
    func resetToDefaults() {
        isEnabled = defaultEnabled
        resetPromptToDefault()
        UserDefaults.standard.removeObject(forKey: excludedAppsKey)
    }
}
