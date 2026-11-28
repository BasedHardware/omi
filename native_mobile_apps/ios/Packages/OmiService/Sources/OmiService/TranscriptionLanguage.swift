import Foundation
import OmiPersistence

/// The `language` capture sends. Several spoken languages that live transcription can mix
/// (Deepgram nova-3 `multi`) become `multi`, so switching mid-sentence is transcribed; otherwise
/// the main language.
public enum TranscriptionLanguage {
    /// Base languages nova-3 transcribes together (backend `deepgram_nova3_multi_languages`).
    static let mixable: Set<String> = ["en", "es", "fr", "de", "hi", "ru", "pt", "ja", "it", "nl"]

    public static func code(main: String, spoken: [String]) -> String {
        let bases = Set(spoken.map(base))
        return bases.count >= 2 && bases.isSubset(of: mixable) ? "multi" : main
    }

    /// Whether these languages are transcribed together when spoken in one conversation.
    public static func mixes(_ spoken: [String]) -> Bool {
        code(main: spoken.first ?? "", spoken: spoken) == "multi"
    }

    static func base(_ code: String) -> String {
        String(code.split(separator: "-").first ?? Substring(code))
    }

    /// The language the iPhone's recognizer listens for: the main one (Apple cannot mix).
    public static func recognizer(_ preferences: Preferences) -> String {
        preferences.string(.userPrimaryLanguage) ?? Locale.current.language.languageCode?.identifier ?? "en"
    }

    static func current(_ preferences: Preferences) -> String {
        let main = preferences.string(.userPrimaryLanguage) ?? Locale.current.language.languageCode?.identifier ?? "en"
        return code(main: main, spoken: preferences.strings(.spokenLanguages))
    }
}
