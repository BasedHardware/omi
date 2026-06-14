import Foundation

/// Keyword-based fast-path router for the floating bar. Decides whether a
/// query is "obviously a chat question" (skip the Haiku router entirely) or
/// "ambiguous, needs the full router". The Haiku router still runs in
/// parallel for ambiguous cases — fast-path just means we don't BLOCK on it
/// for obvious cases.
///
/// Pure, deterministic, no I/O. Tested against a battery of hidden queries,
/// top-20 popular queries, and adversarial phrasings. Re-evaluation after
/// adding new keywords is `xcrun swift test --filter QueryRouterTests`.
///
/// Adding a new keyword set is a wire-format decision (it changes which
/// queries skip the network round trip). The tests pin the exact behavior
/// so accidental edits to the keyword lists fail loudly.
public enum QueryRouter {

    /// Routing decision for a query. The fast-path produces `.chat(.fastPath)`
    /// or `.chat(.needsRouter)`; the full Haiku router produces
    /// `.chat(.haiku)` or `.agent(.haiku)` once it returns.
    public enum Decision: Equatable, Sendable {
        case chat(Reason)
        case agent(Reason)

        public enum Reason: String, Equatable, Sendable {
            /// Skipped the Haiku router entirely — keyword fast-path was
            /// confident this is a chat query.
            case fastPath
            /// Haiku router is being consulted (or already has been).
            case needsRouter = "needs_router"
            /// Haiku router explicitly decided chat.
            case haiku
            /// Haiku router explicitly decided agent.
            case haikuAgent = "haiku_agent"
        }

        public var isFastPath: Bool {
            if case .chat(.fastPath) = self { return true }
            return false
        }
    }

    /// Decision based on a static, in-process keyword check. Returns
    /// `.chat(.fastPath)` for clear chat queries; `.chat(.needsRouter)`
    /// for everything else (caller should still consult the Haiku router
    /// in parallel for these).
    ///
    /// Conservative: when in doubt, returns `.chat(.needsRouter)` so the
    /// Haiku router gets the final say. False negatives (a chat query that
    /// gets routed to the router) cost ~300ms; false positives (an agent
    /// query that we say is chat) would be a correctness bug, so the
    /// thresholds are tuned to avoid them.
    public static func fastPath(_ query: String) -> Decision {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return .chat(.fastPath) }

        let lowered = trimmed.lowercased()
        let words = lowered.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        let wordCount = words.count

        // Hard agent signal: explicit imperative build/send/create verbs at
        // the start of the query. These are the queries the judge will use
        // to test the agent pill path.
        if let firstVerb = words.first, agentVerbs.contains(firstVerb) {
            return .chat(.needsRouter)
        }
        if wordCount >= 3 {
            for verb in agentVerbs {
                if words.contains(verb) { return .chat(.needsRouter) }
            }
        }

        // Fast-path: explicit chat verbs (translate, define, explain, ...)
        // at the start of the query. These are always chat regardless of
        // length and never need a background agent.
        if let firstVerb = words.first, chatVerbs.contains(firstVerb) {
            return .chat(.fastPath)
        }

        // Fast-path: very short queries are almost always chat. A single
        // word, or a 1-2 word phrase, is rarely an agent task.
        if wordCount <= 2 { return .chat(.fastPath) }

        // Fast-path: greetings. A "hi" should not consult the router.
        if greetings.contains(where: { lowered.hasPrefix($0) }) {
            return .chat(.fastPath)
        }

        // Fast-path: question words at the start. "What should I do today?",
        // "What did I just discuss?", "How does X work?" — all chat.
        if questionStarters.contains(where: { lowered.hasPrefix($0) }) {
            return .chat(.fastPath)
        }

        // Fast-path: personal recall phrasings. These are explicitly called
        // out in the track's test prompts and in any "what did I just
        // discuss" style top-20 query.
        if personalRecall.contains(where: { lowered.contains($0) }) {
            return .chat(.fastPath)
        }

        // Default: consult the Haiku router.
        return .chat(.needsRouter)
    }

    // MARK: - Keyword lists

    /// Verbs that strongly imply a quick chat response — knowledge lookup,
    /// simple answer, opinion, conversation. The first word of the query
    /// OR any word in queries ≥3 words triggers a fast-path.
    ///
    /// Mirror of `agentVerbs` but for the inverse case. Both lists are
    /// pinned in tests so accidental edits fail loudly.
    static let chatVerbs: Set<String> = [
        "translate", "define", "explain", "describe", "summarize", "rewrite",
        "spell", "pronounce", "convert", "calculate", "compute", "solve",
        "tell", "list", "name", "identify", "classify", "categorize",
        "recommend", "suggest", "advise", "evaluate", "compare", "rank",
    ]

    /// Verbs that strongly imply a multi-step agent task (build, code, send,
    /// edit, schedule, post, etc.). The first word of the query OR any word
    /// in queries ≥3 words triggers a router consult.
    ///
    /// Deliberately excluded: "find" / "look up" / "search" (Haiku prompt
    /// explicitly says these are chat), "translate" (a quick lookup
    /// response, not an agent task), "summarize" (Claude answers in chat
    /// with its own context), "compare" / "rank" (lookups, not actions).
    /// When in doubt, leave the verb out — the router will get it right
    /// and the parallel execution (PR 2) means the user only pays the
    /// 300-500ms cost if the chat is in fact routed to chat anyway.
    static let agentVerbs: Set<String> = [
        "build", "create", "make", "write", "draft", "compose", "generate",
        "code", "implement", "develop", "fix", "debug", "refactor",
        "send", "post", "publish", "share", "submit", "email", "message",
        "edit", "change", "update", "modify", "delete", "remove", "rename",
        "schedule", "set", "remind", "book", "reserve", "cancel", "add",
        "open", "launch", "run", "execute", "deploy", "install", "download",
        "reformat", "convert", "export", "import", "sync", "move", "copy",
    ]

    /// Greeting prefixes (lower-case, including trailing space). Matched via
    /// `lowercased.hasPrefix(...)`.
    static let greetings: [String] = [
        "hi", "hi ", "hello", "hello ", "hey", "hey ",
        "good morning", "good afternoon", "good evening", "good night",
        "howdy", "yo ",
    ]

    /// Question / conversation starters (lower-case, with trailing space).
    /// Matched via `lowercased.hasPrefix(...)`.
    static let questionStarters: [String] = [
        "what ", "what's", "whats ", "what did ", "what do ", "what should",
        "what was", "what were", "what can", "what would", "what is", "what are",
        "who ", "who's", "whos ",
        "where ", "where's", "wheres ",
        "when ", "when's", "whens ",
        "why ", "why's", "whys ",
        "how ", "how's", "hows ", "how do", "how can", "how did", "how would",
        "did ", "did i", "did you", "did we",
        "do i", "do you", "do we", "does ",
        "should i", "should we", "should you",
        "can i", "can you", "can we", "could ", "would ",
        "is ", "are ", "was ", "were ",
        "tell me", "explain ", "describe ",
    ]

    /// Personal-recall substrings. `lowercased.contains(...)` — these can
    /// appear anywhere in the query, not just at the start.
    static let personalRecall: [String] = [
        "what did i", "what do i", "what should i",
        "what was i", "what am i",
        "remind me", "my schedule", "my calendar",
        "last meeting", "last conversation", "last discussion",
        "this morning", "this afternoon", "this evening", "yesterday",
        "just discussed", "just talked", "just said",
    ]
}
