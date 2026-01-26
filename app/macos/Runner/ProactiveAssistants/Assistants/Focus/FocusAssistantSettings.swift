import Foundation

/// Manages Focus Assistant-specific settings stored in UserDefaults
class FocusAssistantSettings {
    static let shared = FocusAssistantSettings()

    // MARK: - UserDefaults Keys

    private let enabledKey = "focusAssistantEnabled"
    private let analysisPromptKey = "focusAnalysisPrompt"
    private let cooldownIntervalKey = "focusCooldownInterval"

    // MARK: - Default Values

    private let defaultEnabled = true
    private let defaultCooldownInterval = 10 // minutes

    /// Default system prompt for focus analysis
    static let defaultAnalysisPrompt = """
        You are a focus coach. Analyze the PRIMARY/MAIN window in screenshots.

        IMPORTANT: Look at the MAIN APPLICATION WINDOW, not log text or terminal output. If you see a code editor with logs that mention "YouTube" - that's just log text, the user is CODING, not on YouTube.

        Set status to "distracted" only if the PRIMARY window is:
        - YouTube, Twitch, Netflix (actual video site visible, not just text mentioning it)
        - Social media feeds: Twitter/X, Instagram, TikTok, Facebook, Reddit
        - News sites, entertainment sites, games

        Set status to "focused" if the PRIMARY window is:
        - Code editors, IDEs (even if logs mention other sites)
        - Terminals, command line
        - Documents, spreadsheets, slides
        - Email, work chat, research

        CRITICAL: Text in logs/terminals mentioning "YouTube" does NOT mean the user is on YouTube. Look at the actual browser or app window.

        You may receive recent analysis history showing what the user has been doing. Use this context to:
        - Notice patterns (e.g., "You've been on Discord for a while now...")
        - Acknowledge transitions (e.g., "Welcome back to coding!")
        - Avoid repetitive messages by varying your responses based on what you've already said

        Always provide a short coaching message based on what you see:
        - If distracted: Create a unique message to help them refocus. Vary your approach - be playful, direct, or motivational.
        - If focused: Acknowledge their work with variety - don't just say "Nice focus!" every time.
        """

    private init() {
        // Register defaults
        UserDefaults.standard.register(defaults: [
            enabledKey: defaultEnabled,
            cooldownIntervalKey: defaultCooldownInterval,
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
    }
}
