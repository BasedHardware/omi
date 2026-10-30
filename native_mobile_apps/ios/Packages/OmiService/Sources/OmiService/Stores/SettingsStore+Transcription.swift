import Foundation
import OmiNetwork

/// Capture & Transcription › Detect languages (Flutter's "Automatic translation" on the language
/// page): the backend's `single_language_mode`, read at the start of every recording.
public extension SettingsStore {
    /// Last known value (Flutter's `cachedSingleLanguageMode`), shown before the backend answers.
    var detectsLanguages: Bool {
        !preferences.bool(.cachedSingleLanguageMode, default: false)
    }

    /// Asks the backend; returns the current value.
    func loadLanguageDetection() async -> Bool {
        if let single = try? await api.singleLanguageMode() { preferences.set(single, for: .cachedSingleLanguageMode) }
        return detectsLanguages
    }

    /// Returns whether the backend took it (the switch goes back otherwise).
    @discardableResult
    func setLanguageDetection(_ detects: Bool) async -> Bool {
        lastError = nil
        do {
            try await api.setSingleLanguageMode(!detects)
            preferences.set(!detects, for: .cachedSingleLanguageMode)
            return true
        } catch {
            lastError = String(describing: error)
            return false
        }
    }
}
