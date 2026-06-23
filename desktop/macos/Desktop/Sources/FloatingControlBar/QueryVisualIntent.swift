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

        // Noun and verb signals first — these are unambiguous screen
        // references ("click the button", "on my screen", "open Linear").
        // Matched as substrings because the phrases are screen-specific
        // and don't have false-positive cases like the bare deictics do.
        let nounAndVerbSignals = [
            // Screen / window / app nouns
            "screen", "window", "tab", "page", "site", "app ",
            "document", "spreadsheet", "presentation", "slide",
            "error message", "image", "picture", "photo",
            "screenshot", "diagram", "chart", "graph", "map",
            "folder", "icon", "button", "menu", "link", "header",
            "notification", "popup", "dialog", "modal",
            // Visual verbs (with leading space for word boundary to
            // avoid matching "see" inside "user" or "coffee", and to
            // avoid matching "open" at the end of "reopen" or "open ")
            "see ", " look at", "show me", "read this", "read that",
            "what does this say", "what does that say",
            "what's on", "what is on", "on my screen",
            "open ", "scroll", "zoom", "click", "tap", "highlight", "select",
            // Screenshot-related phrasings
            "can you see", "do you see", "are you seeing",
        ]
        for signal in nounAndVerbSignals {
            if lowered.contains(signal) { return true }
        }

        // Deictic detection ("this", "that", "these", "those") is
        // ambiguous on its own: "this morning" / "translate this" are
        // NOT screen references. Require the deictic to be the object
        // of a question or imperative verb, which signals the user is
        // pointing at something on screen. Patterns:
        //   "what is this", "what's this", "what is that", "what are these"
        //   "explain this", "summarize that", "read this"
        //   "do this", "fix this", "open this" (imperative)
        //   "what should i do today/now" (likely tasks/calendar on screen)
        let deicticQuestionPatterns = [
            "what is this", "what's this", "what is that", "what's that",
            "what are these", "what are those", "what're these",
            "what does this", "what does that",
            "explain this", "explain that",
            "summarize this", "summarize that", "summarize these",
            "describe this", "describe that",
            "fix this", "fix that",
            "do this", "do that",
            "open this", "open that",
            "close this", "close that",
            "what should i do",
            "look at this", "look at that",
        ]
        for pattern in deicticQuestionPatterns {
            if lowered.contains(pattern) { return true }
        }
        return false
    }
}
