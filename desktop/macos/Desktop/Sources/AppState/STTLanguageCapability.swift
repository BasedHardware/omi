import Foundation

/// Which transcription engine can decode a configured language. Pure policy, no I/O:
/// `STTSessionState.resolveMode` consults it so a language no on-device model covers goes to
/// the cloud instead of being force-decoded into another model's vocabulary. Japanese on v3
/// came back as English/Spanish word salad — v3 has no CJK tokens to emit.
enum STTLanguageCapability {
  /// On-device Parakeet models (FluidAudio `AsrModelVersion`; mapped in `LocalTranscriptionService`).
  enum OnDeviceModel: Equatable, CaseIterable {
    /// `parakeet-tdt-0.6b-v2`: English only, better English recall than v3.
    case englishV2
    /// `parakeet-tdt-0.6b-v3`: the 25 European languages in `europeanV3Languages`.
    case europeanV3
    /// `parakeet-tdt_ctc-0.6b-ja` (`.tdtJa`, ~1.25 GB): Japanese only.
    case japanese

    var languages: Set<String> {
      switch self {
      case .englishV2: return ["en"]
      case .europeanV3: return STTLanguageCapability.europeanV3Languages
      case .japanese: return ["ja"]
      }
    }
  }

  /// The selected language, captured once per recording start.
  struct Selection: Equatable {
    /// `AssistantSettings.effectiveTranscriptionLanguage`: a language code, or `autoDetect`.
    let effective: String
    /// `AssistantSettings.transcriptionLanguage`: the language picked in Settings.
    let primary: String

    static let english = Selection(effective: "en", primary: "en")

    var isAutoDetect: Bool { STTLanguageCapability.baseCode(effective) == STTLanguageCapability.autoDetect }
    var onDeviceModel: OnDeviceModel? { STTLanguageCapability.onDeviceModel(for: self) }
    var isCoveredOnDevice: Bool { onDeviceModel != nil }

    /// Script-filter hint for the decoder. Only v3 uses it; v2 and tdtJa ignore it by design.
    var decodeHint: String? { isAutoDetect ? nil : STTLanguageCapability.baseCode(effective) }
  }

  /// `effectiveTranscriptionLanguage` returns this when auto-detect is on.
  static let autoDetect = "multi"

  /// NVIDIA's published v3 language list. No Asian languages.
  static let europeanV3Languages: Set<String> = [
    "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "hr", "hu", "it",
    "lt", "lv", "mt", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "uk",
  ]

  /// Cloud STT (`/v4/listen`, Deepgram Nova-3) covers every language the picker offers.
  static func cloudSupports(_ language: String) -> Bool {
    let code = AssistantSettings.normalizeTranscriptionLanguageCode(language)
    if baseCode(code) == autoDetect { return true }
    return AssistantSettings.supportedLanguages.contains { $0.code.caseInsensitiveCompare(code) == .orderedSame }
  }

  /// The on-device model for `selection`, or nil when only the cloud covers it.
  ///
  /// Auto-detect stays on v3, which identifies the spoken language among its own 25. That only
  /// holds when the primary language is one of them; otherwise it goes to the cloud's multi mode.
  static func onDeviceModel(for selection: Selection) -> OnDeviceModel? {
    if selection.isAutoDetect {
      return europeanV3Languages.contains(baseCode(selection.primary)) ? .europeanV3 : nil
    }
    let code = baseCode(selection.effective)
    return OnDeviceModel.allCases.first { $0.languages.contains(code) }
  }

  static func baseCode(_ language: String) -> String {
    AssistantSettings.baseLanguageCode(AssistantSettings.normalizeTranscriptionLanguageCode(language))
  }
}
