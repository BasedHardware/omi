import Foundation

/// Localized string by ARB key. Keys are shared with the Flutter app (`app/lib/l10n/*.arb`);
/// `make strings` regenerates `Localizable.xcstrings` from the ARB files for every key used
/// here, plus native-only keys from `Tools/l10n/native.json`.
public func L(_ key: String) -> String {
    Bundle.module.localizedString(forKey: key, value: key, table: "Localizable")
}

/// Localized string with positional arguments (`{name}` placeholders become `%1$@` …).
public func L(_ key: String, _ arguments: any CVarArg...) -> String {
    String(format: L(key), locale: .current, arguments: arguments)
}

/// The string in a given language (`de`, `en-GB`) rather than the app's, when the catalog has a
/// translation for it; nil otherwise. For text the user reads out loud in the language they speak,
/// which need not be the iPhone's.
public func L(_ key: String, inLanguage language: String) -> String? {
    let exact = language.replacingOccurrences(of: "_", with: "-")
    let base = String(exact.split(separator: "-").first ?? Substring(exact))
    let missing = "\u{0}"
    for code in [exact, base] {
        guard let path = Bundle.module.path(forResource: code, ofType: "lproj"), let bundle = Bundle(path: path) else { continue }
        let value = bundle.localizedString(forKey: key, value: missing, table: "Localizable")
        if value != missing { return value }
    }
    return nil
}
