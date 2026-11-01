import Foundation

/// Engine order for the on-device live preview (display only; never the record):
/// SpeechAnalyzer/SpeechTranscriber (iOS 26+) → on-device SFSpeech → Omi's own
/// model (not built for streaming in this release) → none. There is never a
/// cloud fallback. Pure policy, so it is testable without Speech or Flutter.
enum LivePreviewTier: Equatable {
    case ready
    /// The tier cannot run; `reason` is one of the closed wire reasons.
    case unavailable(String)
}

struct LivePreviewChoice: Equatable {
    let engine: String
    let reason: String
    let bundledInstalled: Bool

    var wire: [String: Any] { ["engine": engine, "reason": reason, "bundledInstalled": bundledInstalled] }
}

enum LivePreviewSelection {
    static let reasons: Set<String> = [
        "ok", "not_admitted", "kill_switch", "os_too_old", "os_engine_unavailable", "locale_unsupported",
        "locale_asset_missing", "speech_permission_denied", "bundled_not_installed", "bundled_not_built", "engine_error",
    ]

    /// `analyzer` is `.unavailable("os_too_old")` below iOS 26. The reported
    /// reason for "none" is the preferred OS engine's refusal: the analyzer's
    /// when this OS has it, otherwise SFSpeech's. Omi's model is never selected
    /// in this release (`bundled_not_built`); its presence is reported separately.
    static func choose(analyzer: LivePreviewTier, sfSpeech: LivePreviewTier, bundledInstalled: Bool) -> LivePreviewChoice {
        if analyzer == .ready {
            return LivePreviewChoice(engine: "speech_transcriber", reason: "ok", bundledInstalled: bundledInstalled)
        }
        if sfSpeech == .ready {
            return LivePreviewChoice(engine: "sf_speech", reason: "ok", bundledInstalled: bundledInstalled)
        }
        let primary: LivePreviewTier = analyzer == .unavailable("os_too_old") ? sfSpeech : analyzer
        var reason = "engine_error"
        if case .unavailable(let refused) = primary, reasons.contains(refused), refused != "ok" { reason = refused }
        return LivePreviewChoice(engine: "none", reason: reason, bundledInstalled: bundledInstalled)
    }

    /// The language the app asked for, as a bare code. "multi"/empty use the device language.
    static func languageCode(_ language: String, deviceLanguage: String?) -> String {
        if language.isEmpty || language == "multi" { return deviceLanguage ?? "en" }
        let separators = CharacterSet(charactersIn: "-_")
        return language.components(separatedBy: separators).first?.lowercased() ?? language
    }

    /// Picks an installed locale for `code` (preferring the device locale), or
    /// reports whether it is merely supported (asset missing) or unsupported.
    /// Never triggers an asset download.
    static func pickLocale(code: String, installed: [String], supported: [String], device: String) -> (locale: String?, reason: String) {
        func matching(_ identifiers: [String]) -> [String] {
            identifiers.filter { languageCode($0, deviceLanguage: nil) == code }.sorted()
        }
        let ready = matching(installed)
        if let chosen = ready.first(where: { $0 == device }) ?? ready.first { return (chosen, "ok") }
        return (nil, matching(supported).isEmpty ? "locale_unsupported" : "locale_asset_missing")
    }
}

/// Segment ids for one preview session: volatile hypotheses share the open
/// id; a final result settles it and the next hypothesis opens a new one.
struct LivePreviewSegmentIds {
    let prefix: String
    private(set) var counter = 0

    init(prefix: String) { self.prefix = prefix }

    var current: String { "\(prefix)\(counter)" }

    /// Returns the id for this result and advances after a final one.
    mutating func id(isFinal: Bool) -> String {
        let id = current
        if isFinal { counter += 1 }
        return id
    }
}
