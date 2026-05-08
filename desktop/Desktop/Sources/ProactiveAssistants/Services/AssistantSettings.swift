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
    private let defaultTranscriptionAutoDetect = true
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
            let value = UserDefaults.standard.string(forKey: transcriptionLanguageKey) ?? defaultTranscriptionLanguage
            let normalized = Self.normalizeTranscriptionLanguageCode(value)
            if normalized != value {
                UserDefaults.standard.set(normalized, forKey: transcriptionLanguageKey)
            }
            return normalized
        }
        set {
            UserDefaults.standard.set(Self.normalizeTranscriptionLanguageCode(newValue), forKey: transcriptionLanguageKey)
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
        if transcriptionAutoDetect && Self.supportsAutoDetect(transcriptionLanguage) {
            return "multi"
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

    /// Canonical backend-supported DeepGram Nova-3 language options for single-language transcription.
    nonisolated static let supportedLanguages: [(code: String, name: String)] = [
        ("ar", "Arabic"),
        ("ar-AE", "Arabic (United Arab Emirates)"),
        ("ar-SA", "Arabic (Saudi Arabia)"),
        ("ar-QA", "Arabic (Qatar)"),
        ("ar-KW", "Arabic (Kuwait)"),
        ("ar-SY", "Arabic (Syria)"),
        ("ar-LB", "Arabic (Lebanon)"),
        ("ar-PS", "Arabic (Palestine)"),
        ("ar-JO", "Arabic (Jordan)"),
        ("ar-EG", "Arabic (Egypt)"),
        ("ar-SD", "Arabic (Sudan)"),
        ("ar-TD", "Arabic (Chad)"),
        ("ar-MA", "Arabic (Morocco)"),
        ("ar-DZ", "Arabic (Algeria)"),
        ("ar-TN", "Arabic (Tunisia)"),
        ("ar-IQ", "Arabic (Iraq)"),
        ("ar-IR", "Arabic (Iran)"),
        ("be", "Belarusian"),
        ("bn", "Bengali"),
        ("bs", "Bosnian"),
        ("en", "English"),
        ("en-US", "English (US)"),
        ("en-GB", "English (UK)"),
        ("en-AU", "English (Australia)"),
        ("en-IN", "English (India)"),
        ("en-NZ", "English (New Zealand)"),
        ("bg", "Bulgarian"),
        ("ca", "Catalan"),
        ("zh-CN", "Chinese (Simplified)"),
        ("zh-HK", "Chinese (Hong Kong)"),
        ("zh-TW", "Chinese (Taiwan)"),
        ("cs", "Czech"),
        ("da", "Danish"),
        ("da-DK", "Danish (Denmark)"),
        ("nl", "Dutch"),
        ("nl-BE", "Dutch (Belgium)"),
        ("et", "Estonian"),
        ("fa", "Persian"),
        ("fi", "Finnish"),
        ("fr", "French"),
        ("fr-CA", "French (Canada)"),
        ("de", "German"),
        ("de-CH", "German (Switzerland)"),
        ("el", "Greek"),
        ("he", "Hebrew"),
        ("hi", "Hindi"),
        ("hr", "Croatian"),
        ("hu", "Hungarian"),
        ("id", "Indonesian"),
        ("it", "Italian"),
        ("ja", "Japanese"),
        ("kn", "Kannada"),
        ("ko", "Korean"),
        ("ko-KR", "Korean (South Korea)"),
        ("lv", "Latvian"),
        ("lt", "Lithuanian"),
        ("mk", "Macedonian"),
        ("mr", "Marathi"),
        ("ms", "Malay"),
        ("no", "Norwegian"),
        ("pl", "Polish"),
        ("pt", "Portuguese"),
        ("pt-BR", "Portuguese (Brazil)"),
        ("pt-PT", "Portuguese (Portugal)"),
        ("ro", "Romanian"),
        ("ru", "Russian"),
        ("sk", "Slovak"),
        ("sl", "Slovenian"),
        ("sr", "Serbian"),
        ("es", "Spanish"),
        ("es-419", "Spanish (Latin America)"),
        ("sv", "Swedish"),
        ("sv-SE", "Swedish (Sweden)"),
        ("ta", "Tamil"),
        ("te", "Telugu"),
        ("th", "Thai"),
        ("th-TH", "Thai (Thailand)"),
        ("tl", "Tagalog"),
        ("tr", "Turkish"),
        ("uk", "Ukrainian"),
        ("ur", "Urdu"),
        ("vi", "Vietnamese"),
    ]

    /// Languages that support multi-language (auto-detect) mode in DeepGram Nova-3
    nonisolated static let multiLanguageSupported: Set<String> = [
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
    nonisolated static func supportsAutoDetect(_ languageCode: String) -> Bool {
        return multiLanguageSupported.contains(normalizeTranscriptionLanguageCode(languageCode))
    }

    nonisolated static func normalizeTranscriptionLanguageCode(_ rawValue: String) -> String {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return "en" }

        let normalizedSeparator = trimmed.replacingOccurrences(of: "_", with: "-")
        let lookupKey = normalizedSeparator.lowercased()

        if let alias = transcriptionLanguageAliases[lookupKey] {
            return alias
        }

        if let supported = supportedLanguages.first(where: {
            $0.code.compare(normalizedSeparator, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
        }) {
            return supported.code
        }

        return normalizedSeparator
    }

    /// Normalizes legacy, backend, and user-entered aliases into codes accepted by `/v4/listen`.
    nonisolated private static let transcriptionLanguageAliases: [String: String] = [
        "br": "pt-BR",
        "chinese": "zh-CN",
        "chinese simplified": "zh-CN",
        "chinese (simplified)": "zh-CN",
        "mandarin": "zh-CN",
        "mandarin chinese": "zh-CN",
        "pt-br": "pt-BR",
        "simplified chinese": "zh-CN",
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-hans": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hant": "zh-TW",
        "zh-hk": "zh-HK",
        "中文": "zh-CN",
        "普通话": "zh-CN",
        "汉语": "zh-CN",
        "国语": "zh-CN",
        "简体中文": "zh-CN",
        "繁体中文": "zh-TW",
        "粤语": "zh-HK",
    ]
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
