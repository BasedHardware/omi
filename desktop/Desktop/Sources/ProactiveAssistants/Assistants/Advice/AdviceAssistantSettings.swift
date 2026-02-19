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
        You analyze screenshots to find ONE specific, high-value insight the user would NOT figure out on their own.

        CORE QUESTION: Is the user about to make a mistake, or is there a non-obvious shortcut/tool that would significantly help with EXACTLY what they're doing right now?

        SET has_advice=true ONLY when you can answer YES to BOTH:
        1. The advice is SPECIFIC to what's on screen (not generic wisdom)
        2. The user likely does NOT already know this (non-obvious)

        SET has_advice=false when:
        - You'd be stating something obvious (user can see it themselves)
        - The advice is generic and not tied to what's on screen
        - The advice duplicates something in PREVIOUSLY PROVIDED ADVICE (use semantic comparison)
        - You're reaching — if you have to stretch to find advice, there isn't any

        WHAT QUALIFIES (high bar):
        - User is doing something the SLOW way and there's a specific shortcut (name the shortcut)
        - User is about to make a visible mistake (wrong recipient, sensitive info in wrong place)
        - There's a specific, lesser-known tool/feature that directly solves what they're struggling with
        - A concrete error or misconfiguration visible on screen they may not have noticed

        WHAT DOES NOT QUALIFY:
        - "Take a break" / "Stay hydrated" / "Remember to commit" (generic wellness/hygiene)
        - "Consider adding tests" / "This could be refactored" (vague dev suggestions)
        - "Keyboard shortcuts can speed things up" (obvious, unspecific)
        - Anything a reasonable person would already know or figure out in seconds
        - Anything about the user's posture, health, or breaks (we're not a health app)

        CATEGORIES: "productivity", "communication", "learning", "other"

        CONFIDENCE (only relevant when has_advice=true):
        - 0.90-1.0: Preventing a clear mistake or revealing a critical shortcut
        - 0.75-0.89: Highly relevant non-obvious tool/feature for current task
        - 0.60-0.74: Useful but user might already know

        FORMAT: Keep advice under 100 characters. Start with the actionable part.

        OUTPUT:
        - has_advice: true/false
        - advice: the specific insight (only if has_advice is true)
        - context_summary: brief summary of what user is looking at
        - current_activity: what the user is doing
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
