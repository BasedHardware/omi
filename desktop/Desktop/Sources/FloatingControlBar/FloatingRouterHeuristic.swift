import Foundation

/// Cheap, local pre-classifier for the floating-bar router.
///
/// The LLM router (`AgentPillsManager.classify` → Haiku) runs on *every* query
/// and adds ~300-700ms of serial latency before the answer can start. But its
/// own rule is "when in doubt, choose chat", and the overwhelming majority of
/// floating-bar queries are conversational (questions, lookups, summaries).
///
/// This heuristic returns `.chat` ONLY when a query shows no sign of wanting a
/// real computer/browser/app action — letting us skip the LLM router entirely.
/// Anything with an action signal returns `.uncertain`, which keeps the
/// existing LLM-router decision. So this never creates a misroute the router
/// wouldn't also make (an "agent" task by definition involves an action verb);
/// it only removes latency from the obvious-chat majority.
enum FloatingRouterHeuristic {
    enum Precheck {
        /// Unambiguously conversational — safe to skip the LLM router.
        case chat
        /// Possible action request — defer to the LLM router for accuracy.
        case uncertain
    }

    /// Verbs/phrases that signal the user wants the assistant to *act* on their
    /// machine/apps (the router's definition of an "agent" task). Lookups
    /// ("search", "find", "look up") are intentionally excluded — the router
    /// treats those as chat. Matched on word boundaries, case-insensitive.
    ///
    /// Tuning note: a signal here only costs a router round-trip (the safe
    /// fallback), never correctness — so err toward listing strong action verbs
    /// and leave ambiguous/conversational words out to maximize the fast-path.
    private static let actionSignals: [String] = [
        "build", "rebuild", "implement", "refactor", "debug",
        "create a", "create an", "make me", "generate a", "compose", "draft a",
        "write a", "write an", "write me", "write some", "edit", "modify",
        "rename", "delete the", "remove the",
        "send", "email", "reply to", "respond to", "post", "tweet", "dm",
        "open", "launch", "navigate", "go to", "browse", "click", "fill out",
        "download", "install", "deploy", "commit", "push the",
        "schedule a", "book a", "order", "automate", "set up", "set-up",
        "move the", "organize", "clean up", "update the", "code up",
    ]

    static func precheck(_ rawMessage: String) -> Precheck {
        let message = rawMessage.lowercased()
        guard !message.isEmpty else { return .chat }
        for signal in actionSignals where containsWord(message, signal) {
            return .uncertain
        }
        return .chat
    }

    /// Boundary-aware containment so "code" doesn't fire on "encode" and "post"
    /// doesn't fire on "important". For multi-word signals the boundary check
    /// applies to the phrase's outer edges, which is sufficient here.
    private static func containsWord(_ haystack: String, _ needle: String) -> Bool {
        guard let range = haystack.range(of: needle) else { return false }
        let before: Character? = range.lowerBound == haystack.startIndex
            ? nil : haystack[haystack.index(before: range.lowerBound)]
        let after: Character? = range.upperBound == haystack.endIndex
            ? nil : haystack[range.upperBound]
        func isBoundary(_ ch: Character?) -> Bool {
            guard let ch = ch else { return true }
            return !(ch.isLetter || ch.isNumber)
        }
        return isBoundary(before) && isBoundary(after)
    }
}
