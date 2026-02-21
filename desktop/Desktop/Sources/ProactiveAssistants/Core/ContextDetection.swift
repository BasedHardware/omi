import Foundation

/// Shared context detection utilities for determining when the user switches contexts
/// (app changes, browser tab switches, etc.)
enum ContextDetection {
    /// Normalize a window title by stripping cosmetic noise (spinners, timers, terminal dimensions)
    /// so that rapid updates from apps like Claude Code or Toggl don't trigger re-analysis.
    static func normalizeWindowTitle(_ title: String?) -> String? {
        guard var result = title else { return nil }

        // Strip Braille spinner characters (U+2800-U+28FF)
        result = result.unicodeScalars.filter { !($0.value >= 0x2800 && $0.value <= 0x28FF) }
            .reduce(into: "") { $0.append(String($1)) }

        // Strip common spinner/progress characters
        let spinnerChars: Set<Character> = ["✳", "↻", "◐", "◑", "◒", "◓", "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏",
                                             "⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷",
                                             "◴", "◷", "◶", "◵", "◰", "◳", "◲", "◱",
                                             "▖", "▘", "▝", "▗", "⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈"]
        result = String(result.filter { !spinnerChars.contains($0) })

        // Strip timer patterns like "12:34", "1:23:45", "00:05:23"
        result = result.replacingOccurrences(
            of: #"\b\d{1,2}:\d{2}(:\d{2})?\b"#,
            with: "",
            options: .regularExpression
        )

        // Strip terminal dimension patterns like "80×24", "60x88"
        result = result.replacingOccurrences(
            of: #"\b\d+[×x]\d+\b"#,
            with: "",
            options: .regularExpression
        )

        // Strip parenthetical/bracketed counts like "(2)", "(16)", "[3]"
        // These are almost always unread/notification counts in browser titles
        result = result.replacingOccurrences(
            of: #"\(\d+\)"#,
            with: "",
            options: .regularExpression
        )
        result = result.replacingOccurrences(
            of: #"\[\d+\]"#,
            with: "",
            options: .regularExpression
        )

        // Collapse whitespace
        result = result.replacingOccurrences(
            of: #"\s+"#,
            with: " ",
            options: .regularExpression
        ).trimmingCharacters(in: .whitespaces)

        return result.isEmpty ? nil : result
    }

    /// Determine if the user switched contexts by comparing app name and normalized window title.
    /// Returns true if either the app changed or the normalized window title changed.
    static func didContextChange(
        fromApp: String?,
        fromWindowTitle: String?,
        toApp: String?,
        toWindowTitle: String?
    ) -> Bool {
        // App changed
        if fromApp != toApp {
            return true
        }

        // Window title changed (after normalization)
        let normalizedFrom = normalizeWindowTitle(fromWindowTitle)
        let normalizedTo = normalizeWindowTitle(toWindowTitle)
        if normalizedFrom != normalizedTo {
            return true
        }

        return false
    }
}
