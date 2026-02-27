import Foundation

/// Manages shared settings for all Proactive Assistants stored in UserDefaults
@MainActor
class AssistantSettings {
    static let shared = AssistantSettings()

    // MARK: - UserDefaults Keys

    private let cooldownIntervalKey = "assistantsCooldownInterval"
    private let glowOverlayEnabledKey = "assistantsGlowOverlayEnabled"
    private let analysisDelayKey = "assistantsAnalysisDelay"
    private let screenAnalysisEnabledKey = "screenAnalysisEnabled"
    private let transcriptionEnabledKey = "transcriptionEnabled"
    private let transcriptionLanguageKey = "transcriptionLanguage"
    private let transcriptionAutoDetectKey = "transcriptionAutoDetect"
    private let transcriptionVocabularyKey = "transcriptionVocabulary"
    private let vadGateEnabledKey = "vadGateEnabled"
    private let batchTranscriptionEnabledKey = "batchTranscriptionEnabled"

    // MARK: - Default Values

    private let defaultCooldownInterval = 10 // minutes
    private let defaultGlowOverlayEnabled = false
    private let defaultAnalysisDelay = 60 // seconds (1 minute)
    private let defaultScreenAnalysisEnabled = true
    private let defaultTranscriptionEnabled = true
    private let defaultTranscriptionLanguage = "en"
    private let defaultTranscriptionAutoDetect = false
    private let defaultTranscriptionVocabulary: [String] = []
    private let defaultVadGateEnabled = false
    private let defaultBatchTranscriptionEnabled = false

    private init() {
        // Register defaults
        UserDefaults.standard.register(defaults: [
            cooldownIntervalKey: defaultCooldownInterval,
            glowOverlayEnabledKey: defaultGlowOverlayEnabled,
            analysisDelayKey: defaultAnalysisDelay,
            screenAnalysisEnabledKey: defaultScreenAnalysisEnabled,
            transcriptionEnabledKey: defaultTranscriptionEnabled,
            transcriptionLanguageKey: defaultTranscriptionLanguage,
            transcriptionAutoDetectKey: defaultTranscriptionAutoDetect,
            transcriptionVocabularyKey: defaultTranscriptionVocabulary,
            vadGateEnabledKey: defaultVadGateEnabled,
            batchTranscriptionEnabledKey: defaultBatchTranscriptionEnabled,
        ])
    }

    // MARK: - Properties

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

    /// Cooldown interval in seconds (for NotificationService)
    var cooldownIntervalSeconds: TimeInterval {
        return TimeInterval(cooldownInterval * 60)
    }

    /// Whether the glow overlay effect is enabled
    var glowOverlayEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: glowOverlayEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: glowOverlayEnabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Delay in seconds before analyzing after an app switch (0 = instant, 60 = 1 min, 300 = 5 min)
    var analysisDelay: Int {
        get {
            let value = UserDefaults.standard.integer(forKey: analysisDelayKey)
            return value >= 0 ? value : defaultAnalysisDelay
        }
        set {
            UserDefaults.standard.set(newValue, forKey: analysisDelayKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Whether screen analysis (proactive monitoring) should be enabled
    var screenAnalysisEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: screenAnalysisEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: screenAnalysisEnabledKey)
            NotificationCenter.default.post(name: .assistantSettingsDidChange, object: nil)
        }
    }

    /// Whether transcription should be enabled
    var transcriptionEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: transcriptionEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: transcriptionEnabledKey)
            NotificationCenter.default.post(name: .transcriptionSettingsDidChange, object: nil)
        }
    }

    /// The language code for transcription (e.g., "en", "uk", "ru")
    var transcriptionLanguage: String {
        get {
            let value = UserDefaults.standard.string(forKey: transcriptionLanguageKey)
            return value ?? defaultTranscriptionLanguage
        }
        set {
            UserDefaults.standard.set(newValue, forKey: transcriptionLanguageKey)
            NotificationCenter.default.post(name: .transcriptionSettingsDidChange, object: nil)
        }
    }

    /// Whether auto-detect (multi-language) mode is enabled
    /// When true, DeepGram will auto-detect the language
    /// When false, uses the specific language set in transcriptionLanguage
    var transcriptionAutoDetect: Bool {
        get { UserDefaults.standard.bool(forKey: transcriptionAutoDetectKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: transcriptionAutoDetectKey)
            NotificationCenter.default.post(name: .transcriptionSettingsDidChange, object: nil)
        }
    }

    /// Returns the effective language to send to DeepGram
    /// If auto-detect is enabled and the language supports multi-language mode, returns "multi"
    /// Otherwise returns the specific language code
    var effectiveTranscriptionLanguage: String {
        if transcriptionAutoDetect {
            // Languages that support multi-language detection in DeepGram Nova-3
            let multiLanguageSupported: Set<String> = [
                "en", "en-US", "en-AU", "en-GB", "en-IN", "en-NZ",
                "es", "es-419",
                "fr", "fr-CA",
                "de",
                "hi",
                "ru",
                "pt", "pt-BR", "pt-PT",
                "ja",
                "it",
                "nl"
            ]

            // If the selected language supports multi-language mode, use "multi"
            // Otherwise fall back to single language (e.g., Ukrainian doesn't support multi)
            if multiLanguageSupported.contains(transcriptionLanguage) {
                return "multi"
            }
        }
        return transcriptionLanguage
    }

    /// Custom vocabulary for improved transcription accuracy
    /// Array of words/terms that DeepGram should recognize (Nova-3 limit: 500 tokens total)
    var transcriptionVocabulary: [String] {
        get {
            let value = UserDefaults.standard.stringArray(forKey: transcriptionVocabularyKey)
            return value ?? defaultTranscriptionVocabulary
        }
        set {
            UserDefaults.standard.set(newValue, forKey: transcriptionVocabularyKey)
            NotificationCenter.default.post(name: .transcriptionSettingsDidChange, object: nil)
        }
    }

    /// Returns vocabulary as comma-separated string for display
    var transcriptionVocabularyString: String {
        get {
            return transcriptionVocabulary.joined(separator: ", ")
        }
        set {
            let terms = newValue
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
            transcriptionVocabulary = terms
        }
    }

    /// Whether batch transcription mode is enabled (transcribes audio in chunks at silence boundaries)
    var batchTranscriptionEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: batchTranscriptionEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: batchTranscriptionEnabledKey)
            NotificationCenter.default.post(name: .transcriptionSettingsDidChange, object: nil)
        }
    }

    /// Whether local VAD gate is enabled to skip silence and reduce Deepgram usage
    var vadGateEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: vadGateEnabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: vadGateEnabledKey)
            NotificationCenter.default.post(name: .transcriptionSettingsDidChange, object: nil)
        }
    }

    /// Returns vocabulary with "Omi" always included (for DeepGram)
    var effectiveVocabulary: [String] {
        var vocab = Set(transcriptionVocabulary)
        vocab.insert("Omi")
        return Array(vocab)
    }

    /// Reset all settings to defaults
    func resetToDefaults() {
        cooldownInterval = defaultCooldownInterval
        glowOverlayEnabled = defaultGlowOverlayEnabled
        analysisDelay = defaultAnalysisDelay
        screenAnalysisEnabled = defaultScreenAnalysisEnabled
        transcriptionEnabled = defaultTranscriptionEnabled
        transcriptionLanguage = defaultTranscriptionLanguage
        transcriptionAutoDetect = defaultTranscriptionAutoDetect
        transcriptionVocabulary = defaultTranscriptionVocabulary
        vadGateEnabled = defaultVadGateEnabled
        batchTranscriptionEnabled = defaultBatchTranscriptionEnabled
    }

    // MARK: - Supported Languages

    /// All languages supported by DeepGram Nova-3 for single-language transcription
    static let supportedLanguages: [(code: String, name: String)] = [
        ("en", "English"),
        ("en-US", "English (US)"),
        ("en-GB", "English (UK)"),
        ("en-AU", "English (Australia)"),
        ("en-IN", "English (India)"),
        ("en-NZ", "English (New Zealand)"),
        ("bg", "Bulgarian"),
        ("ca", "Catalan"),
        ("cs", "Czech"),
        ("da", "Danish"),
        ("nl", "Dutch"),
        ("nl-BE", "Dutch (Belgium)"),
        ("et", "Estonian"),
        ("fi", "Finnish"),
        ("fr", "French"),
        ("fr-CA", "French (Canada)"),
        ("de", "German"),
        ("de-CH", "German (Switzerland)"),
        ("el", "Greek"),
        ("hi", "Hindi"),
        ("hu", "Hungarian"),
        ("id", "Indonesian"),
        ("it", "Italian"),
        ("ja", "Japanese"),
        ("ko", "Korean"),
        ("lv", "Latvian"),
        ("lt", "Lithuanian"),
        ("ms", "Malay"),
        ("no", "Norwegian"),
        ("pl", "Polish"),
        ("pt", "Portuguese"),
        ("pt-BR", "Portuguese (Brazil)"),
        ("pt-PT", "Portuguese (Portugal)"),
        ("ro", "Romanian"),
        ("ru", "Russian"),
        ("sk", "Slovak"),
        ("es", "Spanish"),
        ("es-419", "Spanish (Latin America)"),
        ("sv", "Swedish"),
        ("tr", "Turkish"),
        ("uk", "Ukrainian"),
        ("vi", "Vietnamese"),
    ]

    /// Languages that support multi-language (auto-detect) mode in DeepGram Nova-3
    static let multiLanguageSupported: Set<String> = [
        "en", "en-US", "en-AU", "en-GB", "en-IN", "en-NZ",
        "es", "es-419",
        "fr", "fr-CA",
        "de",
        "hi",
        "ru",
        "pt", "pt-BR", "pt-PT",
        "ja",
        "it",
        "nl"
    ]

    /// Check if a language supports auto-detect mode
    static func supportsAutoDetect(_ languageCode: String) -> Bool {
        return multiLanguageSupported.contains(languageCode)
    }
}

// MARK: - Notification Names

extension Notification.Name {
    static let assistantSettingsDidChange = Notification.Name("assistantSettingsDidChange")
    static let assistantMonitoringStateDidChange = Notification.Name("assistantMonitoringStateDidChange")
    static let assistantMonitoringToggleRequested = Notification.Name("assistantMonitoringToggleRequested")
    static let transcriptionSettingsDidChange = Notification.Name("transcriptionSettingsDidChange")
}

// MARK: - Backward Compatibility

/// Alias for backward compatibility
typealias FocusSettings = AssistantSettings

extension Notification.Name {
    static let focusSettingsDidChange = Notification.Name.assistantSettingsDidChange
    static let focusMonitoringStateDidChange = Notification.Name.assistantMonitoringStateDidChange
}
