import Foundation

/// Manages Advice Assistant-specific settings stored in UserDefaults
class AdviceAssistantSettings {
    static let shared = AdviceAssistantSettings()

    // MARK: - UserDefaults Keys

    private let enabledKey = "adviceAssistantEnabled"
    private let analysisPromptKey = "adviceAnalysisPrompt"
    private let extractionIntervalKey = "adviceExtractionInterval"
    private let minConfidenceKey = "adviceMinConfidence"
    private let cooldownIntervalKey = "adviceCooldownInterval"

    // MARK: - Default Values

    private let defaultEnabled = true
    private let defaultExtractionInterval: TimeInterval = 10.0 // 10 seconds - analyze frequently for just-in-time advice
    private let defaultMinConfidence: Double = 0.85 // High threshold - only show when very confident
    private let defaultCooldownInterval: TimeInterval = 10.0 // 10 seconds between notifications

    /// Default system prompt for advice extraction
    static let defaultAnalysisPrompt = """
        You are a proactive assistant that provides helpful, contextual advice based on what the user is doing on their screen.

        CRITICAL: ALWAYS return advice with a confidence score. The client-side will filter based on the score. Do NOT self-filter by returning has_advice=false for low-confidence advice. Instead, return the advice WITH a low confidence score.

        WHEN TO SET has_advice=false (ONLY these cases):
        - The advice would be semantically similar to something in PREVIOUSLY PROVIDED ADVICE
        - You literally cannot think of any advice at all (extremely rare)

        PREVIOUSLY PROVIDED ADVICE: You will receive a list of recent advice. Use SEMANTIC comparison - do not repeat advice that means the same thing, even if worded differently.

        CATEGORIES:
        - "productivity": Tips to work more efficiently, keyboard shortcuts, better tools
        - "health": Break reminders, posture, eye strain, hydration
        - "communication": Email/message tone, clarity, timing suggestions
        - "learning": Resources, documentation, tutorials related to current work
        - "other": Anything else helpful

        ADVICE QUALITY RULES:
        1. **Actionable**: Something the user can act on NOW
        2. **Contextual**: Based on what's actually on screen
        3. **Specific**: Include details (shortcuts, tool names, etc.)

        FORMAT: Keep advice concise (100-150 characters max for notification banner)

        CONFIDENCE CALIBRATION - Use the FULL range from 0.0 to 1.0:

        0.90-1.00: CRITICAL/OBVIOUS - User is clearly making a mistake or missing something important
           Example: User typing password in a chat window -> "You appear to be typing sensitive info in a chat - double-check the recipient" (0.95)
           Example: User has unsaved work and is about to close -> "You have unsaved changes" (0.98)

        0.70-0.89: HIGHLY RELEVANT - Clear opportunity to help, directly related to current task
           Example: User searching file-by-file in VS Code -> "Cmd+Shift+F searches all files at once" (0.82)
           Example: User copying text repeatedly between apps -> "Consider using clipboard manager like Raycast" (0.75)

        0.50-0.69: MODERATELY USEFUL - Reasonable advice but user might already know or not need it
           Example: User coding for a while -> "A short break might help maintain focus" (0.55)
           Example: User reading documentation -> "This library also has a Discord community for questions" (0.52)

        0.30-0.49: SPECULATIVE - Might be helpful but uncertain if relevant
           Example: User browsing job listings -> "LinkedIn also has a job alerts feature" (0.40)
           Example: User in a code file -> "Consider adding tests for this function" (0.35)

        0.10-0.29: LOW CONFIDENCE - Generic or tangentially related
           Example: User in any IDE -> "Remember to commit your changes periodically" (0.20)
           Example: User reading email -> "Keyboard shortcuts can speed up email management" (0.15)

        0.00-0.09: VERY UNCERTAIN - Barely related, grasping
           Example: Any context -> "Stay hydrated!" (0.05)

        OUTPUT:
        - has_advice: true (almost always) or false (only if duplicate or truly nothing to say)
        - advice: the advice with appropriate confidence score
        - context_summary: brief summary of what user is looking at
        - current_activity: high-level description of user's activity
        """

    private init() {
        // Register defaults
        UserDefaults.standard.register(defaults: [
            enabledKey: defaultEnabled,
            extractionIntervalKey: defaultExtractionInterval,
            minConfidenceKey: defaultMinConfidence,
            cooldownIntervalKey: defaultCooldownInterval,
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

    /// Cooldown interval between advice notifications in seconds
    var cooldownInterval: TimeInterval {
        get {
            let value = UserDefaults.standard.double(forKey: cooldownIntervalKey)
            return value > 0 ? value : defaultCooldownInterval
        }
        set {
            UserDefaults.standard.set(newValue, forKey: cooldownIntervalKey)
            log("Advice cooldown interval updated to \(newValue) seconds")
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Cooldown in seconds (for NotificationService compatibility)
    var cooldownIntervalSeconds: TimeInterval {
        return cooldownInterval
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
        cooldownInterval = defaultCooldownInterval
        resetPromptToDefault()
    }
}
