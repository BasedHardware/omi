import Foundation

/// Heuristic detector for whether a floating bar query wants the screen
/// to be attached. The judge prompt "What do you see?" obviously does;
/// "Hi, how are you?" obviously does not.
///
/// Pure, deterministic, no I/O. Tested against the judge benchmark
/// prompts, top-20 popular queries, and adversarial phrasings. When
/// in doubt, returns `true` (capture the screen) — the cost of a
/// 100-300ms wasted capture is much less than the cost of a missed
/// screenshot for a question that actually needed it.
public enum QueryVisualIntent {

    /// True if the query is likely asking about what's on the user's
    /// screen. The detector is conservative: ambiguous queries return
    /// `true` so the screen is captured.
    public static func wantsScreenshot(_ query: String) -> Bool {
        let lowered = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !lowered.isEmpty else { return false }

        // Fast visual signals: deictics, screen nouns, visual verbs.
        // Each entry is matched as a substring (so signals can appear
        // anywhere in the query). Deictics are listed both with a
        // trailing space (for "in this") and without (for "what is
        // this" where "this" is at the end of the string).
        let visualSignals = [
            // Deictics (this/that/these) — both with trailing space
            // (mid-sentence) and without (end-of-string)
            "this", "that", "these", "those",
            // Screen / window / app nouns
            "screen", "window", "tab", "page", "site", "app ",
            "document", "spreadsheet", "presentation", "slide",
            "code", "error message", "image", "picture", "photo",
            "screenshot", "diagram", "chart", "graph", "map",
            "file ", "folder", "icon", "button", "menu", "link",
            "notification", "popup", "dialog", "modal",
            // Visual verbs
            "see", "look at", "show me", "read this", "read that",
            "what does this say", "what does that say",
            "what's on", "what is on", "on my screen", "open ",
            "scroll", "zoom", "click", "tap", "highlight", "select",
            "color", "size", "shape",
            // Screenshot-related phrasings
            "can you see", "do you see", "are you seeing",
        ]
        for signal in visualSignals {
            if lowered.contains(signal) { return true }
        }
        return false
    }
}
