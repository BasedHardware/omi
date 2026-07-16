import Foundation

/// Client-side validator for Telegram bot tokens.
///
/// Telegram bot tokens follow a stable shape produced by @BotFather:
/// `<numeric_bot_id>:<35-ish chars of base64url-ish content>`. We use a
/// permissive but distinctive regex so the UI can give the user
/// immediate feedback (✓ / ⚠) before the plugin round-trip validates
/// server-side.
///
/// This is a UX affordance, not a security boundary — a malicious
/// caller can craft any string they like. The plugin's setWebhook call
/// is the real check.
enum TelegramTokenValidator {

    /// Regex used by `isValid(_:)`. Anchored so an obviously-wrong value
    /// (with trailing whitespace, extra slashes, etc.) is rejected.
    /// Pattern: digits + colon + 30+ alphanumeric / dash / underscore.
    private static let tokenRegex: NSRegularExpression = {
        // Anchored at both ends so partial matches don't pass.
        let pattern = #"^\d+:[A-Za-z0-9_-]{30,}$"#
        // Force-try is fine here: the pattern is a compile-time constant
        // and any failure is a programmer error (typo in the pattern).
        return try! NSRegularExpression(pattern: pattern)
    }()

    /// True iff `raw` looks like a plausible Telegram bot token.
    ///
    /// - Whitespace is trimmed before matching.
    /// - Empty / nil returns false.
    /// - Doesn't verify the token is REGISTERED — only that it has
    ///   the right shape. A token can be syntactically valid but
    ///   rejected by Telegram (e.g. revoked). That's caught later
    ///   when the plugin calls setWebhook.
    static func isValid(_ raw: String?) -> Bool {
        guard let raw, !raw.isEmpty else { return false }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }
        let range = NSRange(trimmed.startIndex..., in: trimmed)
        return tokenRegex.firstMatch(in: trimmed, range: range) != nil
    }

    /// Used by the Connect sheet's status indicator:
    /// - `.empty` — field has no text
    /// - `.valid` — matches the bot-token shape
    /// - `.invalid` — has text but doesn't match (typo / wrong char)
    enum State: Equatable {
        case empty
        case valid
        case invalid
    }

    /// Classify the current field text. Used by the form to drive the
    /// ✓ / ⚠ indicator and the disabled state of the Connect button.
    static func state(_ raw: String?) -> State {
        guard let raw, !raw.isEmpty else { return .empty }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return .empty }
        return isValid(trimmed) ? .valid : .invalid
    }
}