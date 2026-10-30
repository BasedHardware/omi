import Foundation

/// Parses the backend's ISO-8601 timestamps. Python emits microseconds
/// (`2026-07-18T20:30:00.123456+00:00`); Foundation's formatter tops out at milliseconds,
/// so the fraction is trimmed to three digits before parsing.
public enum BackendDate {
    public static func parse(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        let normalized = trimFraction(string)
        for candidate in [normalized, normalized + "Z"] {
            if let date = fractional.date(from: candidate) ?? whole.date(from: candidate) {
                return date
            }
        }
        return nil
    }

    /// ISO8601DateFormatter is thread-safe; it is only configured here.
    private nonisolated(unsafe) static let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private nonisolated(unsafe) static let whole: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func trimFraction(_ value: String) -> String {
        guard let dot = value.firstIndex(of: ".") else { return value }
        let afterDot = value[value.index(after: dot)...]
        let digits = afterDot.prefix { $0.isNumber }
        guard digits.count > 3 else { return value }
        let rest = afterDot.dropFirst(digits.count)
        return String(value[..<dot]) + "." + digits.prefix(3) + rest
    }
}
