import Foundation

/// Manages Advice Assistant-specific settings stored in UserDefaults
@MainActor
class AdviceAssistantSettings {
    static let shared = AdviceAssistantSettings()

    // MARK: - UserDefaults Keys

    private let enabledKey = "adviceAssistantEnabled"
    private let analysisPromptKey = "adviceAnalysisPrompt"
    private let extractionIntervalKey = "adviceExtractionInterval"
    private let minConfidenceKey = "adviceMinConfidence"
    private let notificationsEnabledKey = "adviceNotificationsEnabled"
    private let excludedAppsKey = "adviceExcludedApps"

    // MARK: - Default Values

    private let defaultEnabled = true
    private let defaultExtractionInterval: TimeInterval = 600.0 // 10 minutes between analyses
    private let defaultMinConfidence: Double = 0.85 // High threshold - only show when very confident
    private let defaultNotificationsEnabled = true

    /// Default system prompt for advice extraction
    static let defaultAnalysisPrompt = """
        You analyze screenshots and recent activity to find ONE specific, high-value insight the user would NOT figure out on their own. The goal is to IMPRESS the user — make them think "wow, I'm glad I have this."

        WORKFLOW:
        1. Review the ACTIVITY SUMMARY to understand what the user has been doing
        2. Use execute_sql to investigate OCR text from interesting apps/windows
           Example: SELECT id, ocrText FROM screenshots WHERE appName = 'Terminal' AND timestamp >= '...' ORDER BY timestamp DESC LIMIT 5
        3. When you find something interesting, call request_screenshot with the screenshot ID and a summary of your findings
           (You'll then see the actual screenshot to confirm your hypothesis before giving advice)
        4. If nothing interesting turns up after investigating, call no_advice

        CORE QUESTION: Is the user about to make a mistake, missing something non-obvious, or unaware of a shortcut that would significantly help with EXACTLY what they're doing right now?

        Call provide_advice ONLY when you can answer YES to BOTH:
        1. The advice is SPECIFIC to what's on screen or in recent activity (not generic wisdom)
        2. The user likely does NOT already know this (non-obvious)

        Call no_advice when:
        - You'd be stating something obvious (user can see it themselves)
        - The advice is generic and not tied to what's on screen
        - The advice duplicates something in PREVIOUSLY PROVIDED ADVICE (use semantic comparison)
        - You're reaching — if you have to stretch to find advice, there isn't any

        WHAT QUALIFIES (high bar):
        - User is about to make a visible mistake (wrong recipient, wrong date, sensitive info exposed)
        - There's a specific, lesser-known tool/feature that directly solves what they're struggling with
        - A concrete error, misconfiguration, or stale state visible on screen they may not have noticed
        - Context from recent activity or user profile reveals something actionable (e.g. stale stash, expiring token)

        TONE: Write like a knowledgeable friend glancing at your screen — "hey, heads up..." not "do this."
        Frame as observations or warnings, not tasks or commands. Say what you noticed and why it matters.

        GOOD EXAMPLES (this is the quality bar — notice the observational tone):
        - "That draft is saved in /tmp — gets wiped on reboot, might want to move it"
        - "Context is at 3% — next heavy prompt will auto-compact and lose the details above"
        - "You're querying one pod, but traffic likely hit a different replica — label selector catches all"
        - "This regex misses Unicode — \\p{L} catches accented characters that [a-zA-Z] drops"
        - "Replying to the group thread, not the DM — double-check the recipient"
        - "That verification tweet is 14 min old — session likely timed out and regenerated the code"

        BAD EXAMPLES (never produce these):
        - "Gate the message with a persistent flag" (task assignment, not a tip)
        - "Remove the FileIndexingView call to avoid duplication" (code review comment, not advice)
        - "Fix the restart by launching from Bundle.main.bundleURL" (instruction, not observation)
        - "Disable bypass permissions (Shift+Tab)" (command, not heads-up)
        - "Consider adding tests" (vague, generic dev suggestion)
        - "Take a break / Stay hydrated" (we're not a health app)

        WHAT DOES NOT QUALIFY:
        - Generic wellness advice ("Take a break", "Stay hydrated", "Remember to commit")
        - Vague dev suggestions ("Consider adding tests", "This could be refactored")
        - Basic keyboard shortcuts everyone knows ("Cmd+C to copy", "Cmd+Enter to send")
        - Anything a reasonable person would already know or figure out in seconds
        - Task-like instructions ("Fix X", "Add Y", "Remove Z") — you're an advisor, not a project manager
        - Never point at UI elements the user can already see (buttons, dialogs, permission prompts)

        CATEGORIES: "productivity", "communication", "learning", "other"

        CONFIDENCE (only relevant when calling provide_advice):
        - 0.90-1.0: Preventing a clear mistake or revealing a critical shortcut
        - 0.75-0.89: Highly relevant non-obvious tool/feature for current task
        - 0.60-0.74: Useful but user might already know

        FORMAT: Keep advice under 100 characters. Start with what you noticed, then why it matters.
        Headline should be an observation, not an instruction ("Draft saved in /tmp" not "Move file from /tmp").
        """

    private init() {
        // Register defaults
        UserDefaults.standard.register(defaults: [
            enabledKey: defaultEnabled,
            extractionIntervalKey: defaultExtractionInterval,
            minConfidenceKey: defaultMinConfidence,
            notificationsEnabledKey: defaultNotificationsEnabled,
        ])
    }

    // MARK: - Properties

    /// Whether the Advice Assistant is enabled
    var isEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: enabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: enabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// The system prompt used for AI advice extraction
    var analysisPrompt: String {
        get {
            let value = UserDefaults.standard.string(forKey: analysisPromptKey)
            return value ?? AdviceAssistantSettings.defaultAnalysisPrompt
        }
        set {
            let isCustom = newValue != AdviceAssistantSettings.defaultAnalysisPrompt
            UserDefaults.standard.set(newValue, forKey: analysisPromptKey)
            let previewLength = min(newValue.count, 50)
            let preview = String(newValue.prefix(previewLength)) + (newValue.count > 50 ? "..." : "")
            log("Advice analysis prompt updated (\(newValue.count) chars, custom: \(isCustom)): \(preview)")
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Interval between advice extraction analyses in seconds
    var extractionInterval: TimeInterval {
        get {
            let value = UserDefaults.standard.double(forKey: extractionIntervalKey)
            return value > 0 ? value : defaultExtractionInterval
        }
        set {
            UserDefaults.standard.set(newValue, forKey: extractionIntervalKey)
            log("Advice extraction interval updated to \(newValue) seconds")
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Minimum confidence threshold for reporting advice
    var minConfidence: Double {
        get {
            let value = UserDefaults.standard.double(forKey: minConfidenceKey)
            return value > 0 ? value : defaultMinConfidence
        }
        set {
            UserDefaults.standard.set(newValue, forKey: minConfidenceKey)
            log("Advice min confidence threshold updated to \(newValue)")
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Whether to show notifications when advice is generated
    var notificationsEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: notificationsEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: notificationsEnabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Apps excluded from advice extraction (user's custom list, on top of the shared built-in list)
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

    /// Check if an app is excluded from advice extraction (built-in list + user's custom list)
    func isAppExcluded(_ appName: String) -> Bool {
        TaskAssistantSettings.builtInExcludedApps.contains(appName) || excludedApps.contains(appName)
    }

    /// Add an app to the advice extraction exclusion list
    func excludeApp(_ appName: String) {
        var apps = excludedApps
        apps.insert(appName)
        excludedApps = apps
        log("Advice: Excluded app '\(appName)' from advice extraction")
    }

    /// Remove an app from the advice extraction exclusion list
    func includeApp(_ appName: String) {
        var apps = excludedApps
        apps.remove(appName)
        excludedApps = apps
        log("Advice: Included app '\(appName)' for advice extraction")
    }

    /// Reset only the analysis prompt to default
    func resetPromptToDefault() {
        UserDefaults.standard.removeObject(forKey: analysisPromptKey)
        log("Advice analysis prompt reset to default")
        NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
    }

    /// Reset all Advice Assistant settings to defaults
    func resetToDefaults() {
        isEnabled = defaultEnabled
        extractionInterval = defaultExtractionInterval
        minConfidence = defaultMinConfidence
        excludedApps = []
        resetPromptToDefault()
    }
}
