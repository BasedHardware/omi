import ContextCore
import Foundation

// MARK: - Tool definition

public struct ToolDefinition: Sendable {
    public let name: String
    public let description: String
    public let inputSchema: JSONValue

    public init(name: String, description: String, inputSchema: JSONValue) {
        self.name = name
        self.description = description
        self.inputSchema = inputSchema
    }
}

/// Failures a tool call can report back to Claude. Every case names the offending value: a filter
/// that was silently dropped is worse than a call that failed loudly, because Claude would then
/// reason over the wrong slice of the user's life without knowing it.
public enum ToolError: LocalizedError, CustomStringConvertible {
    case unknownTool(String)
    case missingArgument(tool: String, argument: String)
    case unparsableDate(argument: String, value: String)
    case invalidArgument(argument: String, value: String, expected: String)

    public var description: String {
        switch self {
        case let .unknownTool(name):
            return "Unknown tool \"\(name)\". Available tools: \(Tools.all.map(\.name).joined(separator: ", "))."
        case let .missingArgument(tool, argument):
            return "\(tool) requires the \"\(argument)\" argument."
        case let .unparsableDate(argument, value):
            return """
            Could not understand \"\(argument)\": \"\(value)\". \
            Use an ISO-8601 timestamp, 2026-07-28, 2026-07-28 14:05, or plain English such as \
            now, today, yesterday, this morning, last night, last week, last month, \
            "30 minutes ago", "2 hours ago", "3 days ago". \
            The call was rejected rather than run without the filter, so nothing here is a partial answer.
            """
        case let .invalidArgument(argument, value, expected):
            return "Invalid \"\(argument)\": \"\(value)\". \(expected)"
        }
    }

    public var errorDescription: String? { description }
}

// MARK: - Origin
//
// Two very different records reach these tools. Claude has to be able to tell them apart without
// guessing: the local half is seconds fresh but only covers this Mac since Context for Claude was installed;
// the Omi half is the user's whole account history but lags a conversation by minutes.

private enum Origin {
    /// Captured by Context for Claude on this Mac.
    case live
    /// The Omi account's own history, read from api.omi.me.
    case omi

    var tag: String { self == .live ? "live" : "omi" }
}

// MARK: - Tools

public enum Tools {
    public static let all: [ToolDefinition] = [
        ToolDefinition(name: "recall", description: recallDescription, inputSchema: recallSchema),
        ToolDefinition(name: "recent", description: recentDescription, inputSchema: recentSchema),
        ToolDefinition(
            name: "conversations",
            description: conversationsDescription,
            inputSchema: conversationsSchema
        ),
        ToolDefinition(name: "transcript", description: transcriptDescription, inputSchema: transcriptSchema),
        ToolDefinition(name: "screen", description: screenDescription, inputSchema: screenSchema),
        ToolDefinition(name: "activity", description: activityDescription, inputSchema: activitySchema),
        ToolDefinition(name: "status", description: statusDescription, inputSchema: statusSchema),
    ]

    /// Executes a tool and returns the text payload for the MCP content block.
    ///
    /// `store` is nil when nothing has been captured on this Mac yet — which is the *normal* state
    /// five minutes after install, and no longer means the tools have nothing to say: the Omi
    /// account's own history answers most of them on its own.
    public static func call(name: String, arguments: JSONValue?, store: ContextStore?) throws -> String {
        guard all.contains(where: { $0.name == name }) else { throw ToolError.unknownTool(name) }

        switch name {
        case "recall": return try runRecall(arguments, store)
        case "recent": return try runRecent(arguments, store)
        case "conversations": return try runConversations(arguments, store)
        case "transcript": return try runTranscript(arguments, store)
        case "screen": return try runScreen(arguments, store)
        case "activity": return try runActivity(arguments, store)
        case "status": return runStatus(store)
        default: throw ToolError.unknownTool(name)
        }
    }

    /// Why this reader has no database, said in the user's terms.
    ///
    /// Never assert an empty life from an unopenable database. `diagnoseMissingDatabase()` reads the
    /// heartbeat, which the app rewrites every 30s and which no reader fault can forge: a live beat
    /// proves capture is running somewhere this process cannot see, which is a fact about *this
    /// binary*, not about the user. Saying "nothing was ever captured here" in that state is the
    /// confident falsehood the coverage-window design exists to prevent.
    fileprivate static func missingDatabaseSentence(subject: String) -> String {
        switch CaptureState.diagnoseMissingDatabase() {
        case let .readerIsStale(capturingSince, age):
            let since = Self.clockFormatter.string(from: Date(timeIntervalSince1970: capturingSince))
            return """
            \(subject) cannot read the capture database — but Context for Claude *is* running and \
            capturing here: its heartbeat was written \(Int(age))s ago, at \(since). This is a fault \
            in this reader, not an empty history. Do not tell the user nothing was recorded. The most \
            likely cause is a stale MCP server left over from an earlier install: restarting Claude \
            reconnects it to the current app.
            """
        case .appNotRunning:
            return """
            \(subject) has not captured anything on this Mac yet — the app is not running here, so \
            there is no local speech, screen text, or activity history from the last few minutes.
            """
        }
    }

    /// Wall-clock only; the date is always today by the time this is reachable.
    fileprivate static let clockFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    /// What a local-only tool says when this Mac has captured nothing. It points at the tools that
    /// *do* reach the account, so "no local database" never reads as "Claude knows nothing".
    fileprivate static var noLocalCaptureMessage: String {
        var out = missingDatabaseSentence(subject: "Context for Claude")
        if OmiBackend.shared.isConfigured {
            out += " "
            out += """
            The user's Omi account history is still available: use `recall` for what they have said \
            and what Omi remembers about them, and `conversations` for their recorded conversations.
            """
        }
        return out
    }
}

// MARK: - Descriptions
//
// These are the product. They are the only thing Claude sees before deciding whether the answer to
// the user's question already exists, so they say *when to reach for the tool* — and, now that these
// tools read the user's whole Omi account, that the answer is very likely in here.

extension Tools {
    static let recallDescription = """
    Search the user's entire recorded life: their Omi account — every conversation Omi has recorded \
    and every durable fact it has learned about them, going back years — merged with what Context for Claude \
    captured on this Mac in the last few seconds.

    Reach for this whenever the user mentions a person, plan, decision, project, meeting, price, \
    place, preference or event you have no record of. The answer is very often already in here. \
    Prefer searching over asking the user to explain context they have obviously already lived \
    through, and search again with different words — a name, a company, a phrase they would have \
    said out loud — before concluding you do not know.

    Results are newest-first, grouped by day, each line timed and labelled with where it came from: \
    `live` is Context for Claude's capture on this Mac (*me* is the user speaking, *them* is the other side of \
    a call, *screen* is text on their display), `omi` is the account's own history. Facts Omi \
    remembers carry no date and are listed separately. Bound the search with `since` / `until` when \
    the user anchors it in time. If it comes back empty, check `status` before saying it never \
    happened.
    """

    static let recentDescription = """
    See what the user is doing right now — the last N minutes of their speech and screen on this \
    Mac, merged in order.

    Reach for this when a request starts mid-thought and assumes context you were never given: \
    "help me with this", "what do you think?", "draft a reply", "summarise that", "why is this \
    failing?". They mean something in front of them. Look before you ask them to paste it.

    This one is deliberately local only: it answers "what is happening this minute", where the Omi \
    account still lags by minutes. For anything older than the current session, use `recall` or \
    `conversations`, which read the account too.
    """

    static let conversationsDescription = """
    List the user's conversations: their Omi account's recorded conversations — each with the title \
    and summary Omi wrote for it — merged with any conversation Context for Claude captured on this Mac that \
    has not reached the account yet.

    Reach for this when the user points at a conversation rather than a fact — "my call with \
    Sarah", "the standup this morning", "that interview last week", "what did I agree to \
    yesterday" — and you need to find the right one before reading it. Bound it with `since` / \
    `until`; without them it returns the most recent conversations across both.

    Every entry carries an id. Pass it to `transcript` to read that conversation in full.
    """

    static let transcriptDescription = """
    Read one whole conversation line by line. From the Omi account the speakers are resolved to real \
    names and the conversation carries Omi's own title and summary; from this Mac's local capture \
    the lines are attributed to *me* (the user) and *them* (whoever they were speaking with).

    Reach for this once `conversations` or `recall` has pointed you at a conversation and you need \
    what was actually said — the exact commitment, number, name, date or decision — rather than a \
    paraphrase. Use it before writing anything that must be faithful to a call: follow-up emails, \
    summaries, action items, meeting notes, "what did I promise them?".

    `session_id` takes either id shape exactly as printed: an Omi conversation id (a UUID) or a \
    local Context for Claude conversation number. Quote from the transcript when details matter — it is speech \
    recognition, so names and rare words can be misheard; read around a line before treating it as \
    exact.
    """

    static let screenDescription = """
    See what the user was reading, writing, or looking at: window titles and on-screen text, \
    newest-first, from the Omi account's screen history and from Context for Claude's capture on this Mac.

    Reach for this when the question is visual rather than spoken — an article, a document, a \
    dashboard, an error message, a chat thread, a pull request, a booking or checkout page, code \
    they were reading. It is also how you recover something the user saw but never said out loud, \
    which is most of what happens at a computer.

    Filter with `app` ("Safari", "Xcode", "Slack", "Figma") when you know where to look, and bound \
    it with `since` / `until`. For the shape of the day rather than its contents, use `activity`.
    """

    static let activityDescription = """
    Get the shape of the user's day or week on this Mac: contiguous blocks of time per app and \
    window, with totals. Local capture only — it measures attention at this machine.

    Reach for this for questions about time and attention — "what did I do today", "where did the \
    afternoon go", "how long was I in Figma", "was I heads-down or in meetings", "what have I been \
    working on this week" — and whenever you are writing a standup, a status update, a timesheet, or \
    a weekly review for them.

    This is a summary of where they were, not what they saw. When you need the contents of those \
    windows, follow it with `screen` or `recall` over the same time range.
    """

    static let statusDescription = """
    Check what these tools can actually see, on both halves: whether Context for Claude is capturing on this \
    Mac right now, which permissions are granted, how much is stored locally — and whether the \
    user's Omi account is reachable, how far back its history goes, and which key source was used.

    Call this before telling the user that something never happened, or that you cannot find \
    anything. An empty search inside the coverage window is real evidence; an empty search outside \
    it, with a capture permission denied, or while the Omi account is unreachable, only means \
    nothing was recorded or nothing could be read. Those must never be reported the same way.

    This is also the tool to reach for when the user asks whether Omi is working, why you seem to be \
    missing something, or how far back your knowledge of their life goes.
    """
}

// MARK: - Schemas

extension Tools {
    private static let dateHelp = """
    ISO-8601 (2026-07-28T14:05:00Z), a date (2026-07-28), a date and time (2026-07-28 14:05), or \
    plain English: now, today, yesterday, this morning, last night, last week, last month, \
    "30 minutes ago", "2 hours ago", "3 days ago". Anything else fails the call rather than being \
    ignored, so a time filter is never silently dropped.
    """

    private static var sinceProperty: JSONValue {
        Schema.string("Optional start of the time range — only include what happened at or after it. \(dateHelp)")
    }

    private static var untilProperty: JSONValue {
        Schema.string("Optional end of the time range — only include what happened at or before it. \(dateHelp)")
    }

    static var recallSchema: JSONValue {
        Schema.object(
            properties: [
                ("query", Schema.string("""
                What to search for. Plain words, not a query language: a person's name, a company, a \
                project, a place, a phrase the user would have said or seen. Any term may match, so \
                two or three strong words beat a whole sentence.
                """)),
                ("since", sinceProperty),
                ("until", untilProperty),
                ("limit", Schema.integer("Maximum number of results, newest-first.", default: 40)),
            ],
            required: ["query"]
        )
    }

    static var recentSchema: JSONValue {
        Schema.object(properties: [
            ("minutes", Schema.integer("How far back to look, in minutes.", default: 30)),
        ])
    }

    static var conversationsSchema: JSONValue {
        Schema.object(properties: [
            ("since", sinceProperty),
            ("until", untilProperty),
            ("limit", Schema.integer("Maximum number of conversations, newest-first.", default: 30)),
        ])
    }

    static var transcriptSchema: JSONValue {
        Schema.object(
            properties: [
                ("session_id", Schema.stringOrInteger("""
                The id of the conversation to read, copied exactly as `conversations` or `recall` \
                printed it. Two shapes are accepted: an Omi conversation id, which is a UUID such as \
                "5db3de8c-3c1c-5fee-bad1-2907d2a5a473", and a local Context for Claude conversation number such \
                as 14 (the number after the #).
                """)),
            ],
            required: ["session_id"]
        )
    }

    static var screenSchema: JSONValue {
        Schema.object(properties: [
            ("since", sinceProperty),
            ("until", untilProperty),
            ("app", Schema.string("""
            Optional app name to filter by, as macOS shows it: "Safari", "Xcode", "Slack", "Figma", \
            "Mail". Leave it out to see everything.
            """)),
            ("limit", Schema.integer("Maximum number of screen observations, newest-first.", default: 60)),
        ])
    }

    static var activitySchema: JSONValue {
        Schema.object(
            properties: [
                ("since", Schema.string("Start of the range to summarise. \(dateHelp)")),
                ("until", Schema.string("End of the range to summarise; defaults to now. \(dateHelp)")),
            ],
            required: ["since"]
        )
    }

    static var statusSchema: JSONValue { Schema.object() }
}

/// Hand-built JSON Schema fragments. Explicit cases rather than literals so the type checker never
/// has to infer through a deeply nested dictionary.
private enum Schema {
    static func object(properties: [(String, JSONValue)] = [], required: [String] = []) -> JSONValue {
        var props: [String: JSONValue] = [:]
        for (key, value) in properties { props[key] = value }
        var schema: [String: JSONValue] = [
            "type": .string("object"),
            "properties": .object(props),
        ]
        if !required.isEmpty {
            schema["required"] = .array(required.map { JSONValue.string($0) })
        }
        return .object(schema)
    }

    static func string(_ description: String) -> JSONValue {
        .object(["type": .string("string"), "description": .string(description)])
    }

    static func integer(_ description: String) -> JSONValue {
        .object(["type": .string("integer"), "description": .string(description)])
    }

    static func integer(_ description: String, default defaultValue: Int) -> JSONValue {
        .object([
            "type": .string("integer"),
            "description": .string(description),
            "default": .number(Double(defaultValue)),
        ])
    }

    /// A union type, because one id space is a UUID and the other is a row number. Declaring only
    /// one of them would make a client coerce — and a coerced UUID is a truncated UUID.
    static func stringOrInteger(_ description: String) -> JSONValue {
        .object([
            "type": .array([.string("string"), .string("integer")]),
            "description": .string(description),
        ])
    }
}

// MARK: - Implementations

extension Tools {
    private static func runRecall(_ args: JSONValue?, _ store: ContextStore?) throws -> String {
        guard let query = stringArg(args, "query") else {
            throw ToolError.missingArgument(tool: "recall", argument: "query")
        }
        let since = try dateArg(args, "since")
        let until = try dateArg(args, "until")
        let limit = clamp(intArg(args, "limit") ?? 40, 1, 500)

        var notes: [String] = []
        let local = readLocal(store, &notes) {
            try Queries.recall($0, query: query, since: since, until: until, limit: limit)
        }

        // One round trip, two requests: memories are the durable facts, conversations the episodes.
        let omi = OmiBackend.shared.recall(query: query, since: since, until: until, limit: limit)

        var merged = local.map(liveHit)
        merged += omi.conversations.map(omiConversationHit)
        merged = dedupe(merged)
        merged = Array(merged.prefix(limit))

        let memories = Array(omi.memories.prefix(20))
        guard !merged.isEmpty || !memories.isEmpty else {
            return emptyMessage(
                store,
                "Nothing in \(scopeSearched(omi.failures)) matches \"\(query)\"\(rangeSuffix(since, until))."
            ) + footerBlock(omi.failures, notes)
        }

        var out = header(for: merged, memories: memories, query: query, since: since, until: until)
        if !merged.isEmpty {
            out += "\n\n" + renderMerged(merged, order: .newestFirst)
        }
        if !memories.isEmpty {
            out += "\n\n" + renderMemories(memories)
        }
        return out + footerBlock(omi.failures, notes)
    }

    private static func header(
        for hits: [MergedHit],
        memories: [OmiMemory],
        query: String,
        since: Double?,
        until: Double?
    ) -> String {
        // Local hits are a literal full-text match; Omi's are not. `conversations/search` and
        // `memories/search` are semantic — they return nearest neighbours with no relevance floor,
        // so a word the user has never said still comes back with a page of confident-looking
        // results ("chinchilla" returns a conversation about jewellery). Calling those "matches"
        // is how Claude ends up asserting something happened that never did, which is the exact
        // failure `status` exists to prevent. The two kinds are counted and named separately, and
        // only the local ones are ever called matches.
        var parts: [String] = []
        let live = hits.filter { $0.origin == .live }.count
        let omi = hits.count - live
        if live > 0 { parts.append("\(number(live)) captured live on this Mac") }
        if omi > 0 { parts.append("\(number(omi)) related from Omi's history") }
        if !memories.isEmpty { parts.append(plural(memories.count, "related fact") + " Omi remembers") }

        let headline: String
        if live > 0 {
            headline = "**\(plural(live, "match", "matches")) for \"\(query)\"\(rangeSuffix(since, until))**"
        } else if omi > 0 || !memories.isEmpty {
            headline = "**Nothing on this Mac matched \"\(query)\"\(rangeSuffix(since, until)) — "
                + "here is what Omi found related to it**"
        } else {
            headline = "**No results for \"\(query)\"\(rangeSuffix(since, until))**"
        }

        let breakdown = parts.isEmpty ? "" : " — " + parts.joined(separator: ", ")
        let caveat = (omi > 0 || !memories.isEmpty)
            ? "\n\n_Omi's half of this is a semantic search: it returns the closest things it has, "
                + "even when nothing genuinely matches. Treat those as leads to confirm, not as "
                + "evidence the words were said._"
            : ""
        return headline + breakdown + caveat
    }

    private static func runRecent(_ args: JSONValue?, _ store: ContextStore?) throws -> String {
        guard let store else { return noLocalCaptureMessage }
        let minutes = clamp(intArg(args, "minutes") ?? 30, 1, 24 * 60)
        // `recent` is read as a narrative, so ask for enough lines to actually cover the window and
        // let the output budget do the trimming.
        let limit = clamp(minutes * 10, 120, 1500)

        let hits = try Queries.recent(store, minutes: minutes, limit: limit)
        guard !hits.isEmpty else {
            var out = emptyMessage(store, "Context for Claude captured nothing on this Mac in the last \(plural(minutes, "minute")).")
            if OmiBackend.shared.isConfigured {
                out += "\n\n"
                out += """
                _This tool is local only, by design — it answers "what is happening this minute". \
                The user's Omi account history is not empty just because this window is: reach for \
                `recall` or `conversations` for anything older than the current session._
                """
            }
            return out
        }
        let header = "**The last \(plural(minutes, "minute")) on this Mac — \(plural(hits.count, "entry", "entries"))**"
        return header + "\n\n" + renderHitsOnly(hits, order: .oldestFirst)
    }

    private static func runConversations(_ args: JSONValue?, _ store: ContextStore?) throws -> String {
        let since = try dateArg(args, "since")
        let until = try dateArg(args, "until")
        let limit = clamp(intArg(args, "limit") ?? 30, 1, 200)

        var notes: [String] = []
        let sessions = readLocal(store, &notes) {
            try Queries.sessions($0, since: since, until: until, limit: limit)
        }

        // The account is preferred: it has titles, overviews and speaker-resolved people. Local
        // sessions fill in whatever has not reached it yet.
        let backend = OmiBackend.shared.conversations(since: since, until: until, limit: limit)
        let failures = backend.failure.map { ["conversations: \($0.reason)"] } ?? []

        var entries = (backend.value ?? []).map(omiConversationEntry)
        entries += sessions.map(localConversationEntry)
        entries.sort { $0.at > $1.at }
        entries = Array(entries.prefix(limit))

        guard !entries.isEmpty else {
            return emptyMessage(
                store,
                "No conversations\(rangeSuffix(since, until)) were found in \(scopeSearched(failures))."
            ) + footerBlock(failures, notes)
        }
        return renderConversations(entries, since: since, until: until) + footerBlock(failures, notes)
    }

    private static func runTranscript(_ args: JSONValue?, _ store: ContextStore?) throws -> String {
        guard let raw = args?["session_id"] else {
            throw ToolError.missingArgument(tool: "transcript", argument: "session_id")
        }
        guard let token = identifierToken(raw) else {
            throw ToolError.invalidArgument(
                argument: "session_id",
                value: String(describing: raw),
                expected: """
                It must be an Omi conversation id (a UUID) or the local conversation number printed \
                after the # by `conversations`.
                """
            )
        }

        switch Identifier.classify(token) {
        case let .local(id):
            return try localTranscript(id, store)
        case let .backend(id):
            return backendTranscript(id, fallbackLocal: nil, store)
        case let .ambiguous(id, localID):
            // A bare number is only ever a local id, but an explicit `omi:` prefix on a number, or a
            // token that reads as both, gets one attempt at each before giving up.
            return backendTranscript(id, fallbackLocal: localID, store)
        }
    }

    private static func localTranscript(_ sessionId: Int64, _ store: ContextStore?) throws -> String {
        guard let store else {
            return """
            \(noLocalCaptureMessage)

            \(number(Int(sessionId))) is a local Context for Claude conversation number, and this Mac has no \
            local capture, so there is nothing to read. Omi conversation ids are UUIDs — call \
            `conversations` to list the ids that do exist.
            """
        }
        let hits = try Queries.transcript(store, sessionId: sessionId)
        guard !hits.isEmpty else {
            return emptyMessage(
                store,
                """
                Context for Claude has no local conversation #\(sessionId) — the id may be wrong, or the \
                conversation may live in the Omi account instead, where ids are UUIDs. Call \
                `conversations` to list the ids that exist on both sides.
                """
            )
        }
        let start = hits.map(\.at).min() ?? 0
        let end = hits.map(\.at).max() ?? start
        let header = """
        **Conversation #\(sessionId)** · captured live on this Mac — \(plural(hits.count, "line")), \
        \(ContextTime.describe(start)) to \(timeFormatter.string(from: Date(timeIntervalSince1970: end))) \
        (\(duration(end - start)))
        """
        return header + "\n\n" + renderHitsOnly(hits, order: .oldestFirst)
    }

    private static func backendTranscript(_ id: String, fallbackLocal: Int64?, _ store: ContextStore?) -> String {
        switch OmiBackend.shared.conversation(id: id) {
        case let .ok(full):
            return renderOmiTranscript(full)
        case let .unavailable(error):
            if let fallbackLocal, let text = try? localTranscript(fallbackLocal, store) { return text }
            // "The account does not have it" and "the account could not be read" are opposite
            // conclusions for a reader, so they never share wording.
            if error == .notFound {
                return """
                The Omi account holds no conversation with the id `\(id)`. The id may be mistyped, or \
                it may be a local Context for Claude conversation number rather than an Omi id — those are plain \
                numbers, not UUIDs. Call `conversations` to list the ids that exist on both sides.
                """
            }
            var out = "The Omi conversation `\(id)` could not be read: \(error.reason)."
            if error == .notConfigured {
                out += "\n\n" + OmiBackend.notConfiguredSentence
            }
            out += "\n\n"
            out += """
            That is "could not be reached", not "the conversation does not exist" — do not tell the \
            user it is missing. Call `status` to see whether the Omi account is reachable at all.
            """
            return out
        }
    }

    private static func runScreen(_ args: JSONValue?, _ store: ContextStore?) throws -> String {
        let since = try dateArg(args, "since")
        let until = try dateArg(args, "until")
        let app = stringArg(args, "app")
        let limit = clamp(intArg(args, "limit") ?? 60, 1, 500)

        var notes: [String] = []
        let local = readLocal(store, &notes) {
            try Queries.screen($0, since: since, until: until, app: app, limit: limit)
        }

        let backend = OmiBackend.shared.screenActivity(since: since, until: until, app: app, limit: limit)
        let failures = backend.failure.map { ["screen history: \($0.reason)"] } ?? []

        var merged = local.map(liveHit)
        merged += (backend.value ?? []).map(omiScreenHit)
        merged = dedupe(merged)
        merged = Array(merged.prefix(limit))

        let appSuffix = app.map { " in \($0)" } ?? ""
        guard !merged.isEmpty else {
            return emptyMessage(
                store,
                "Nothing on screen\(appSuffix)\(rangeSuffix(since, until)) was found in \(scopeSearched(failures))."
            ) + footerBlock(failures, notes)
        }
        let header = "**\(plural(merged.count, "screen observation"))\(appSuffix)\(rangeSuffix(since, until))**"
        return header + "\n\n" + renderMerged(merged, order: .newestFirst) + footerBlock(failures, notes)
    }

    private static func runActivity(_ args: JSONValue?, _ store: ContextStore?) throws -> String {
        guard let store else { return noLocalCaptureMessage }
        // `dateArg` throws on an unreadable value, so nil here means the argument was simply absent.
        guard var since = try dateArg(args, "since") else {
            throw ToolError.missingArgument(tool: "activity", argument: "since")
        }
        var until = try dateArg(args, "until") ?? ContextTime.now
        var swappedNote = ""
        if until < since {
            swap(&since, &until)
            swappedNote = "\n\n_`since` was later than `until`; the range was read the other way round._"
        }

        let blocks = try Queries.activity(store, since: since, until: until)
        guard !blocks.isEmpty else {
            return emptyMessage(
                store,
                "Context for Claude recorded no screen activity on this Mac between \(ContextTime.describe(since)) and \(ContextTime.describe(until))."
            )
        }
        return renderActivity(blocks, since: since, until: until) + swappedNote
    }

    /// A store that opens but cannot be queried is a *third* state, and the one `try?` used to erase:
    /// the database is right there and readable enough to open, so reporting "never captured
    /// anything" is a lie about the user rather than a report about the reader. Carry the failure
    /// through and say which of the three actually happened.
    private static func runStatus(_ store: ContextStore?) -> String {
        var local: StatusInfo?
        var queryFailure: String?
        if let store {
            do {
                local = try Queries.status(store)
            } catch {
                queryFailure = error.localizedDescription
            }
        }
        return renderStatus(local, queryFailure: queryFailure) + "\n\n" + renderOmiStatus()
    }
}

// MARK: - Local reads
//
// A local failure degrades exactly like a backend failure. Once these tools answer from two
// sources, either one being down is a partial answer, never an exception.

extension Tools {
    /// Runs a local query, turning a missing or unreadable database into an empty result plus a
    /// note. Absent is not the same as broken, and neither is the same as an exception.
    private static func readLocal<Element>(
        _ store: ContextStore?,
        _ notes: inout [String],
        _ body: (ContextStore) throws -> [Element]
    ) -> [Element] {
        guard let store else { return [] }
        do {
            return try body(store)
        } catch {
            notes.append("Context for Claude's local database on this Mac could not be read (\(error)).")
            return []
        }
    }
}

// MARK: - Identifiers

/// One tool, two id spaces. `transcript` accepts either shape rather than making Claude know which
/// surface a conversation came from — it copies back whatever was printed.
private enum Identifier {
    case local(Int64)
    case backend(String)
    case ambiguous(String, Int64)

    static func classify(_ raw: String) -> Identifier {
        var token = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        var forcedBackend = false
        for prefix in ["omi:", "omi/", "omi "] where token.lowercased().hasPrefix(prefix) {
            token = String(token.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
            forcedBackend = true
        }
        while token.hasPrefix("#") { token = String(token.dropFirst()) }
        token = token.trimmingCharacters(in: CharacterSet(charactersIn: "`\"'"))

        if let id = Int64(token) {
            return forcedBackend ? .ambiguous(token, id) : .local(id)
        }
        return .backend(token)
    }
}

// MARK: - Merged rendering
//
// Markdown, not JSON. Claude reads a dated, attributed list of sentences far better than it reads a
// wall of records, and the day headings are what let it answer "on Tuesday you said…".

/// One rendered line plus everything needed to order, dedupe and budget it. Pre-rendering the line
/// is what lets a local `Hit` and an Omi conversation share one timeline without either being
/// squeezed into the other's shape.
private struct MergedHit {
    let at: Double
    let origin: Origin
    /// Content fingerprint used to drop the same moment reported by both halves.
    let key: String
    /// Speech before the screen it was said in front of, on an exact tie.
    let rank: Int
    let line: String
}

extension Tools {
    fileprivate enum HitOrder { case oldestFirst, newestFirst }

    /// Roughly 1500 rendered lines, whichever of the two limits bites first.
    private static let maxHitLines = 1500
    private static let maxHitCharacters = 120_000
    private static let omiOverviewLimit = 400
    private static let omiScreenTextLimit = 600

    // MARK: Building

    private static func liveHit(_ hit: Hit) -> MergedHit {
        MergedHit(
            at: hit.at,
            origin: .live,
            key: fingerprint(hit.text, at: hit.at),
            rank: hit.kind == "screen" ? 1 : 0,
            line: hitLine(hit, origin: .live)
        )
    }

    private static func omiConversationHit(_ conversation: OmiConversation) -> MergedHit {
        let at = conversation.startedAt ?? 0
        var line = "- "
        line += at > 0 ? "**\(timeFormatter.string(from: Date(timeIntervalSince1970: at)))** · " : "**undated** · "
        line += "*conversation* · omi: **\(collapse(conversation.title))**"
        let overview = collapse(conversation.overview)
        if !overview.isEmpty { line += " — \(truncate(overview, to: omiOverviewLimit))" }
        line += " (id `\(conversation.id)`)"
        return MergedHit(
            at: at,
            origin: .omi,
            key: fingerprint(conversation.title + " " + conversation.overview, at: at),
            rank: 0,
            line: line
        )
    }

    private static func omiScreenHit(_ row: OmiScreenRow) -> MergedHit {
        let at = row.at ?? 0
        let hit = Hit(
            kind: "screen",
            at: at,
            text: truncate(collapse(row.ocr ?? row.window ?? row.app ?? ""), to: omiScreenTextLimit),
            app: row.app.flatMap(nonEmpty),
            window: row.window.flatMap(nonEmpty)
        )
        return MergedHit(
            at: at,
            origin: .omi,
            key: fingerprint(hit.text, at: at),
            rank: 1,
            line: hitLine(hit, origin: .omi)
        )
    }

    /// Same content, same couple of minutes, both halves: report it once.
    ///
    /// Buckets rather than exact timestamps, because two recorders never agree to the second — and
    /// under-deduping is the safe direction: a repeated line costs a reader a moment, a dropped one
    /// costs them the fact.
    private static func dedupe(_ hits: [MergedHit]) -> [MergedHit] {
        // Rank first: on a duplicate, the copy the ranker liked best is the one worth keeping.
        let ordered = hits.sorted { lhs, rhs in
            if lhs.rank != rhs.rank { return lhs.rank < rhs.rank }
            if lhs.at != rhs.at { return lhs.at > rhs.at }
            // On an exact tie the live record wins: it is the raw thing the user just said.
            return lhs.origin == .live && rhs.origin == .omi
        }
        var seen = Set<String>()
        var kept: [MergedHit] = []
        kept.reserveCapacity(ordered.count)
        for hit in ordered where seen.insert(hit.key).inserted {
            kept.append(hit)
        }
        return kept
    }

    private static func fingerprint(_ text: String, at: Double) -> String {
        let letters = text.lowercased().filter { $0.isLetter || $0.isNumber || $0 == " " }
        let squeezed = letters.split(separator: " ").joined(separator: " ")
        let head = String(squeezed.prefix(120))
        guard at > 0 else { return "undated|" + head }
        return "\(Int((at / 120).rounded()))|\(head)"
    }

    // MARK: Rendering

    private static func renderHitsOnly(_ hits: [Hit], order: HitOrder) -> String {
        renderMerged(
            hits.map {
                MergedHit(at: $0.at, origin: .live, key: "", rank: 0, line: hitLine($0, origin: nil))
            },
            order: order,
            deduped: true
        )
    }

    private static func renderMerged(_ hits: [MergedHit], order: HitOrder, deduped: Bool = false) -> String {
        // Which hits survive the budget is decided by **relevance**, not recency. `Queries.recall`
        // ranks by match quality now, and truncating the oldest end threw that away — the one
        // genuine match for a query could be dropped for three newer incidental ones, and an empty
        // answer inside the coverage window is something the model is explicitly licensed to report
        // as proof the thing never happened. Selection is therefore by rank; only the *display*
        // order below is chronological, because a dated list is what a person can read.
        let deduplicated = deduped ? hits : dedupe(hits)
        let byRelevance = deduplicated.sorted { lhs, rhs in
            if lhs.rank != rhs.rank { return lhs.rank < rhs.rank }
            return lhs.at > rhs.at
        }
        var kept: [MergedHit] = []
        var characters = 0
        var omitted = 0
        for hit in byRelevance {
            if kept.count >= maxHitLines || characters + hit.line.count > maxHitCharacters {
                omitted += 1
                continue
            }
            characters += hit.line.count + 1
            kept.append(hit)
        }

        let display = order == .oldestFirst ? kept.sorted { $0.at < $1.at } : kept.sorted { $0.at > $1.at }
        var out: [String] = []
        var currentDay: Date?
        var undated: [String] = []
        let calendar = Calendar.current
        for entry in display {
            guard entry.at > 0 else {
                undated.append(entry.line)
                continue
            }
            let day = calendar.startOfDay(for: Date(timeIntervalSince1970: entry.at))
            if day != currentDay {
                if currentDay != nil { out.append("") }
                out.append(dayHeading(for: entry.at))
                out.append("")
                currentDay = day
            }
            out.append(entry.line)
        }
        if !undated.isEmpty {
            if !out.isEmpty { out.append("") }
            out.append("## Undated")
            out.append("")
            out.append(contentsOf: undated)
        }

        if omitted > 0 {
            out.append("")
            out.append("""
            _\(plural(omitted, "older entry", "older entries")) omitted to keep this readable. \
            Narrow the range with `since` / `until`, or ask for a smaller `limit`._
            """)
        }
        return out.joined(separator: "\n")
    }

    private static func hitLine(_ hit: Hit, origin: Origin?) -> String {
        let time = hit.at > 0
            ? timeFormatter.string(from: Date(timeIntervalSince1970: hit.at))
            : "undated"
        let tag = origin.map { " · \($0.tag)" } ?? ""
        let text = collapse(hit.text)
        switch hit.kind {
        case "said":
            return "- **\(time)** · *me*\(tag): \(text)"
        case "heard":
            return "- **\(time)** · *them*\(tag): \(text)"
        case "screen":
            let app = hit.app.flatMap(nonEmpty)
            // Window titles are quoted, so a title of its own quotes ("Re: "the plan"") would read
            // as broken markup.
            let window = hit.window.flatMap(nonEmpty).map {
                "\"\(collapse($0).replacingOccurrences(of: "\"", with: "'"))\""
            }
            let context: String
            switch (app, window) {
            case let (app?, window?): context = " (\(app) — \(window))"
            case let (app?, nil): context = " (\(app))"
            case let (nil, window?): context = " (\(window))"
            case (nil, nil): context = ""
            }
            return text.isEmpty
                ? "- **\(time)** · *screen*\(tag)\(context)"
                : "- **\(time)** · *screen*\(tag)\(context): \(text)"
        default:
            return "- **\(time)** · *\(hit.kind)*\(tag): \(text)"
        }
    }

    private static func renderMemories(_ memories: [OmiMemory]) -> String {
        var out: [String] = [
            "**What Omi remembers about the user** · omi",
            "",
        ]
        for memory in memories {
            let content = collapse(memory.content)
            guard !content.isEmpty else { continue }
            let category = memory.category.flatMap(nonEmpty).map { " _(\($0))_" } ?? ""
            out.append("- \(content)\(category)")
        }
        out.append("")
        out.append("""
        _These are durable facts Omi has learned, not moments — the Omi API returns them without a \
        timestamp, so they are listed undated rather than placed on the timeline._
        """)
        return out.joined(separator: "\n")
    }
}

// MARK: - Conversation rendering

/// A conversation from either half, flattened to the same shape so one list can carry both.
private struct ConversationEntry {
    let at: Double
    let origin: Origin
    let title: String
    /// The line of facts under the title: when, how long, which app, how many lines.
    let meta: String
    /// Copy-paste id for `transcript`.
    let identifier: String
    let body: [String]
}

extension Tools {
    private static func omiConversationEntry(_ conversation: OmiConversation) -> ConversationEntry {
        let at = conversation.startedAt ?? 0
        var meta: [String] = ["Omi"]
        if at > 0 { meta.append(sessionHeaderFormatter.string(from: Date(timeIntervalSince1970: at))) }
        if let seconds = conversation.durationSeconds { meta.append(duration(seconds)) }
        if let category = conversation.category.flatMap(nonEmpty) { meta.append(category) }
        if let language = conversation.language.flatMap(nonEmpty) { meta.append(language) }
        meta.append("id `\(conversation.id)`")

        var body: [String] = []
        let overview = collapse(conversation.overview)
        if !overview.isEmpty { body.append("  " + overview) }
        // Omi's own apps often carry the action items; one is a useful hint, all of them is a wall.
        if let note = conversation.appNotes.first.map(collapse), !note.isEmpty {
            body.append("  " + truncate(note, to: omiOverviewLimit))
        }
        return ConversationEntry(
            at: at,
            origin: .omi,
            title: collapse(conversation.title),
            meta: meta.joined(separator: " · "),
            identifier: conversation.id,
            body: body
        )
    }

    private static func localConversationEntry(_ session: SessionSummary) -> ConversationEntry {
        var meta: [String] = [
            "live on this Mac",
            sessionHeaderFormatter.string(from: Date(timeIntervalSince1970: session.startedAt)),
            session.endedAt == nil ? "ongoing" : duration(session.durationSeconds),
        ]
        if let app = session.appHint.flatMap(nonEmpty) { meta.append(app) }
        meta.append(session.bothSidesPresent ? "both sides" : "one side only")
        meta.append(plural(session.lineCount, "line"))
        meta.append("id `\(session.id)`")

        var body: [String] = []
        let preview = session.preview.trimmingCharacters(in: .whitespacesAndNewlines)
        for line in preview.split(separator: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if !trimmed.isEmpty { body.append("  " + trimmed) }
        }
        return ConversationEntry(
            at: session.startedAt,
            origin: .live,
            title: "Conversation #\(session.id)",
            meta: meta.joined(separator: " · "),
            identifier: String(session.id),
            body: body
        )
    }

    private static func renderConversations(
        _ entries: [ConversationEntry],
        since: Double?,
        until: Double?
    ) -> String {
        let omi = entries.filter { $0.origin == .omi }.count
        let live = entries.count - omi
        var parts: [String] = []
        if omi > 0 { parts.append("\(number(omi)) from the Omi account") }
        if live > 0 { parts.append("\(number(live)) captured live on this Mac") }
        let breakdown = parts.isEmpty ? "" : " — " + parts.joined(separator: ", ")

        var out: [String] = [
            "**\(plural(entries.count, "conversation"))\(rangeSuffix(since, until))**\(breakdown)",
            "",
        ]
        for entry in entries {
            out.append("### \(entry.title)")
            out.append(entry.meta)
            out.append(contentsOf: entry.body)
            out.append("")
        }
        out.append("""
        _Read any of these in full with `transcript`, passing the id exactly as printed: a UUID reads \
        the Omi record (title, overview, speaker names), a number reads Context for Claude's local capture on \
        this Mac._
        """)
        return out.joined(separator: "\n")
    }

    private static func renderOmiTranscript(_ full: OmiFullConversation) -> String {
        let conversation = full.conversation
        let start = conversation.startedAt ?? 0

        var meta: [String] = ["Omi conversation `\(conversation.id)`"]
        if start > 0 { meta.append(ContextTime.describe(start)) }
        if let seconds = conversation.durationSeconds { meta.append(duration(seconds)) }
        if let category = conversation.category.flatMap(nonEmpty) { meta.append(category) }
        meta.append(plural(full.segments.count, "line"))

        var out: [String] = [
            "**\(collapse(conversation.title))**",
            meta.joined(separator: " · "),
        ]
        let overview = collapse(conversation.overview)
        if !overview.isEmpty {
            out.append("")
            out.append(overview)
        }

        if full.segments.isEmpty {
            out.append("")
            out.append("""
            Omi kept the summary above but no transcript for this conversation, so nothing here can \
            be quoted as an exact line.
            """)
        } else {
            out.append("")
            for segment in full.segments {
                let text = collapse(segment.text)
                guard !text.isEmpty else { continue }
                let speaker = speakerLabel(segment)
                // Segment offsets are seconds from the start of the conversation.
                let time = start > 0
                    ? timeFormatter.string(from: Date(timeIntervalSince1970: start + segment.start))
                    : offsetLabel(segment.start)
                out.append("- **\(time)** · *\(speaker)*: \(text)")
            }
        }

        if !conversation.appNotes.isEmpty {
            out.append("")
            out.append("**What Omi's apps wrote about this conversation**")
            out.append("")
            for note in conversation.appNotes.prefix(3) {
                out.append(note)
                out.append("")
            }
        }

        out.append("""
        _Speakers are resolved by Omi against the account's known people; an unrecognised voice is \
        numbered rather than named. It is speech recognition, so read around a line before treating \
        it as exact._
        """)
        return out.joined(separator: "\n")
    }

    private static func speakerLabel(_ segment: OmiTranscriptSegment) -> String {
        if let name = segment.speakerName.flatMap(nonEmpty) {
            // Omi labels the account owner "User"; the rest of this surface calls them "me".
            return name.lowercased() == "user" ? "me" : name
        }
        if let id = segment.speakerID { return "speaker \(id)" }
        return "unknown"
    }

    private static func offsetLabel(_ seconds: Double) -> String {
        let total = Int(max(0, seconds).rounded())
        return String(format: "+%d:%02d", total / 60, total % 60)
    }
}

// MARK: - Activity and status rendering

extension Tools {
    private static func renderActivity(_ blocks: [ActivityBlock], since: Double, until: Double) -> String {
        var out: [String] = [
            "**Activity on this Mac from \(ContextTime.describe(since)) to \(ContextTime.describe(until))**",
            "",
        ]
        let calendar = Calendar.current
        var currentDay: Date?
        var dayTotals: [String: Double] = [:]

        func flushTotals() {
            guard !dayTotals.isEmpty else { return }
            let ranked = dayTotals.sorted { $0.value > $1.value }.prefix(8)
            out.append("")
            out.append("**Time by app:** " + ranked.map { "\($0.key) \(duration($0.value))" }.joined(separator: " · "))
            dayTotals = [:]
        }

        for block in blocks.sorted(by: { $0.startedAt < $1.startedAt }) {
            let day = calendar.startOfDay(for: Date(timeIntervalSince1970: block.startedAt))
            if day != currentDay {
                flushTotals()
                if currentDay != nil { out.append("") }
                out.append(dayHeading(for: block.startedAt))
                out.append("")
                currentDay = day
            }
            let start = timeFormatter.string(from: Date(timeIntervalSince1970: block.startedAt))
            let end = timeFormatter.string(from: Date(timeIntervalSince1970: block.endedAt))
            // The same formatter `flushTotals` uses, deliberately. Rounding a 20-second block up to
            // "1 min" here while the per-app rollup reported "20 sec" for the very same seconds made
            // one response contradict itself, and a reader has no way to tell which half to believe.
            var line = "- **\(start)–\(end)** (\(duration(block.durationSeconds))) · \(block.app)"
            if let window = block.window.flatMap(nonEmpty) { line += " — \(collapse(window))" }
            out.append(line)
            dayTotals[block.app, default: 0] += block.durationSeconds
        }
        flushTotals()
        return out.joined(separator: "\n")
    }

    private static func renderStatus(_ status: StatusInfo?, queryFailure: String? = nil) -> String {
        var out: [String] = ["**This Mac — Context for Claude's live capture**", ""]

        guard let status else {
            // The database opened and then refused to answer. That is a reader fault with the file
            // sitting right there, so it must never be phrased as an empty history.
            if let queryFailure {
                out.append("""
                The capture database opened but could not be read: \(queryFailure). This is a fault \
                in this reader — it says nothing about whether the user was recorded. Do not report \
                an empty history.
                """)
                return out.joined(separator: "\n")
            }
            out.append(missingDatabaseSentence(subject: "This reader"))
            return out.joined(separator: "\n")
        }

        let headline: String
        if status.capturing {
            headline = "Context for Claude is capturing right now."
        } else if let reason = status.pausedReason.flatMap(nonEmpty) {
            headline = "Context for Claude is not capturing right now — \(reason)."
        } else {
            headline = "Context for Claude is not capturing right now."
        }

        if status.segmentCount == 0 && status.frameCount == 0 {
            out.append("""
            \(headline) It has recorded nothing locally so far — no speech and no screen text — so an \
            empty answer from `recent` or `activity` means "not captured", never "did not happen".
            """)
        } else {
            out.append("""
            \(headline) It holds \(plural(status.segmentCount, "transcript line")) across \
            \(plural(status.sessionCount, "conversation")) and \
            \(plural(status.frameCount, "screen observation")) on this Mac.
            """)
            out.append("")
            out.append("""
            Local coverage: **\(status.coverage)**. Anything inside that window was recorded here, so \
            an empty local search there is real evidence it did not happen at this Mac. Anything \
            outside it was never captured here — check the Omi account below before concluding \
            anything.
            """)
        }

        out.append("")
        if status.capabilities.isEmpty {
            out.append("""
            - No permission report available — Context for Claude is not running, so it cannot say which of \
            microphone, system audio, and screen recording are granted.
            """)
        } else {
            for capability in status.capabilities {
                let state = capability.granted ? "granted" : "not granted"
                let detail = nonEmpty(capability.detail).map { " — \($0)" } ?? ""
                out.append("- **\(capability.name)**: \(state)\(detail)")
            }
            if status.capabilities.contains(where: { !$0.granted }) {
                out.append("")
                out.append("""
                At least one capture permission is off, so a whole class of local context is missing \
                rather than absent. Say that plainly instead of concluding something never happened.
                """)
            }
        }

        out.append("")
        out.append("Database: `\(status.databasePath)`")
        return out.joined(separator: "\n")
    }

    /// The other half of honesty: an unreachable account and an empty account must never read the
    /// same way, and the key's *source* is reportable while its value is not.
    private static func renderOmiStatus() -> String {
        let backend = OmiBackend.shared
        guard let source = backend.keySourceLabel else {
            return """
            **The Omi account — history**

            Not configured: no Omi MCP API key was found in the \(OmiKeyResolver.environmentVariable) \
            environment variable, in ~/Library/Application Support/ContextForClaude/mcp-key, or in the \
            omi-memory entry in ~/.claude.json. The account's conversations and remembered facts \
            cannot be read, so every tool above answers from this Mac's local capture only. That is a \
            missing connection, not an empty life — do not tell the user their history is empty.
            """
        }

        var out: [String] = ["**The Omi account — history**", ""]
        switch backend.history() {
        case let .ok(probe):
            out.append("Reachable. Key source: \(source) — Context for Claude reads that key and never prints, copies, or stores it.")
            out.append("")
            if let newest = probe.newest, let at = newest.startedAt {
                out.append("Newest record in the account: \(ContextTime.describe(at)) — \"\(collapse(newest.title))\".")
            } else {
                out.append("The account is reachable but holds no conversations yet.")
            }
            if let deep = probe.atProbeOffset, let at = deep.startedAt {
                out.append("""
                History depth: at least \(number(probe.probeOffset + 1)) conversations — counting back, \
                number \(number(probe.probeOffset + 1)) starts at \(ContextTime.describe(at)), so the \
                account reaches at least that far. Context for Claude stops probing there to stay inside Omi's \
                300-reads-an-hour limit; the real history may go back further.
                """)
            } else if probe.newest != nil {
                out.append("""
                History depth: fewer than \(number(probe.probeOffset + 1)) conversations, ending at the \
                date above.
                """)
            }
            if let range = backend.seenRange, range.oldest > 0 {
                out.append("Oldest Omi record read in this session: \(ContextTime.describe(range.oldest)).")
            }
            out.append("")
            out.append("""
            `recall`, `conversations`, `transcript` and `screen` read this history and merge it with \
            the local capture above; `recent` and `activity` are local only, by design.
            """)
        case let .unavailable(error):
            out.append("Unreachable: \(error.reason). Key source: \(source).")
            out.append("")
            out.append("""
            Only this Mac's local capture is searchable right now. An empty result from `recall` or \
            `conversations` currently means "the account could not be read", never "it did not \
            happen" — say so rather than concluding anything about the user's history.
            """)
        }
        return out.joined(separator: "\n")
    }

    /// The single most important non-result in the product: it is what stops Claude from turning
    /// "not captured" into "never happened".
    private static func emptyMessage(_ store: ContextStore?, _ sentence: String) -> String {
        guard let store, let status = try? Queries.status(store) else {
            return sentence + "\n\n" + """
            Context for Claude has captured nothing on this Mac (no local database), so this answer rests \
            entirely on the Omi account. Treat it as "not found in what could be read" rather than \
            "did not happen", and call `status` to see which halves are actually available.
            """
        }
        if status.segmentCount == 0 && status.frameCount == 0 {
            return sentence + "\n\n" + """
            Context for Claude has recorded nothing locally on this Mac yet, so nothing here rules anything out. \
            Call `status` to see whether the Omi account is reachable before telling the user this \
            did not happen.
            """
        }

        var out = sentence
        out += "\n\n"
        out += """
        Context for Claude has recorded \(plural(status.segmentCount, "transcript line")) and \
        \(plural(status.frameCount, "screen observation")) on this Mac, covering **\(status.coverage)**.
        """
        if !status.capturing {
            let reason = status.pausedReason.flatMap(nonEmpty) ?? "it is not running"
            out += " It is not capturing right now — \(reason)."
        }
        if status.capabilities.contains(where: { !$0.granted }) {
            let denied = status.capabilities.filter { !$0.granted }.map(\.name).joined(separator: ", ")
            out += " Not granted: \(denied) — that context was never captured at all."
        }
        out += "\n\n"
        out += """
        Try different wording, widen `since` / `until`, or call `status` for the full picture — \
        including whether the Omi account was reachable for this answer — before telling the user it \
        did not happen.
        """
        return out
    }

    /// Names what was actually searched, so an empty answer never claims to have looked somewhere it
    /// could not reach. This is the difference between "your Omi history has nothing on that" and
    /// "your Omi history was not read".
    private static func scopeSearched(_ backendFailures: [String]) -> String {
        guard OmiBackend.shared.isConfigured, backendFailures.isEmpty else {
            return "Context for Claude's local capture on this Mac (the Omi account could not be searched)"
        }
        return "the Omi account or Context for Claude's local capture on this Mac"
    }

    /// The one place a degraded answer is explained. Everything above it is real; this says exactly
    /// what is missing and why, which is what makes reasoning over a partial answer safe.
    private static func footerBlock(_ backendFailures: [String], _ localNotes: [String]) -> String {
        var lines: [String] = []

        if !OmiBackend.shared.isConfigured {
            lines.append("_\(OmiBackend.notConfiguredSentence)_")
        } else if !backendFailures.isEmpty {
            lines.append("""
            _Omi account history could not be reached — \(backendFailures.joined(separator: "; ")). \
            Everything above is only what Context for Claude captured locally on this Mac, so an absence here is \
            not evidence about the user's history._
            """)
        } else {
            lines.append("""
            _Origins: `live` = captured by Context for Claude on this Mac, seconds fresh; `omi` = the user's Omi \
            account history, which lags a conversation by a few minutes._
            """)
        }

        for note in localNotes {
            lines.append("_\(note) Results above come from the Omi account only._")
        }

        return lines.isEmpty ? "" : "\n\n" + lines.joined(separator: "\n\n")
    }
}

// MARK: - Formatting helpers

extension Tools {
    private static func fixedFormatter(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = format
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }

    fileprivate static let timeFormatter = fixedFormatter("h:mm a")
    private static let dayFormatter = fixedFormatter("EEEE d MMMM")
    private static let dayWithYearFormatter = fixedFormatter("EEEE d MMMM yyyy")
    fileprivate static let sessionHeaderFormatter = fixedFormatter("EEE d MMM yyyy, h:mm a")

    private static let decimalFormatter: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter
    }()

    private static func dayHeading(for epoch: Double) -> String {
        let calendar = Calendar.current
        let date = Date(timeIntervalSince1970: epoch)
        let now = Date()
        let sameYear = calendar.component(.year, from: date) == calendar.component(.year, from: now)
        var heading = (sameYear ? dayFormatter : dayWithYearFormatter).string(from: date)

        let day = calendar.startOfDay(for: date)
        let today = calendar.startOfDay(for: now)
        if day == today {
            heading += " (today)"
        } else if let yesterday = calendar.date(byAdding: .day, value: -1, to: today), day == yesterday {
            heading += " (yesterday)"
        }
        return "## " + heading
    }

    private static func rangeSuffix(_ since: Double?, _ until: Double?) -> String {
        switch (since, until) {
        case (nil, nil): return ""
        case let (since?, nil): return " since \(ContextTime.describe(since))"
        case let (nil, until?): return " before \(ContextTime.describe(until))"
        case let (since?, until?):
            return " between \(ContextTime.describe(since)) and \(ContextTime.describe(until))"
        }
    }

    /// The only duration formatter in this file, so no two lines of one response can disagree about
    /// how long the same stretch of time was. Seconds below a minute, whole minutes below an hour,
    /// hours and minutes above — never a sub-minute span rounded up to "1 min".
    fileprivate static func duration(_ seconds: Double) -> String {
        let total = Int(max(0, seconds).rounded())
        if total < 60 { return "\(total) sec" }
        let minutes = total / 60
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remainder = minutes % 60
        return remainder == 0 ? "\(hours) h" : "\(hours) h \(remainder) min"
    }

    fileprivate static func number(_ value: Int) -> String {
        decimalFormatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    fileprivate static func plural(_ value: Int, _ singular: String, _ plural: String? = nil) -> String {
        value == 1 ? "\(number(value)) \(singular)" : "\(number(value)) \(plural ?? singular + "s")"
    }

    /// One hit is one line, so newlines and runs of whitespace have to go.
    fileprivate static func collapse(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace || $0.isNewline }).joined(separator: " ")
    }

    fileprivate static func nonEmpty(_ text: String) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Word-boundary truncation. The result, ellipsis included, is never longer than `limit`.
    fileprivate static func truncate(_ text: String, to limit: Int) -> String {
        guard limit > 1, text.count > limit else { return text }
        var cut = String(text.prefix(limit - 1))
        if let space = cut.lastIndex(of: " ") {
            let word = cut[cut.startIndex..<space]
            // Only honour the word boundary when it does not throw away most of the snippet.
            if word.count >= (limit - 1) / 2 { cut = String(word) }
        }
        return cut.trimmingCharacters(in: .whitespaces) + "…"
    }
}

// MARK: - Argument helpers

extension Tools {
    private static func stringArg(_ args: JSONValue?, _ key: String) -> String? {
        guard let raw = args?[key]?.stringValue else { return nil }
        return nonEmpty(raw)
    }

    /// `JSONValue.intValue` already unquotes numbers the model sent as strings.
    private static func intArg(_ args: JSONValue?, _ key: String) -> Int? {
        args?[key]?.intValue
    }

    /// An id may arrive as a JSON string (a UUID) or a JSON number (a local row). Both become text
    /// here so one classifier can read them; a number is rendered without a decimal point, because
    /// "14.0" is not an id anybody printed.
    private static func identifierToken(_ raw: JSONValue) -> String? {
        if let text = raw.stringValue.flatMap(nonEmpty) { return text }
        if let value = raw.int64Value { return String(value) }
        return nil
    }

    /// The subscript treats an explicit `null` as absent, so nil here means "no filter asked for" —
    /// which is the one case that may quietly pass through. Anything present but unreadable throws.
    private static func dateArg(_ args: JSONValue?, _ key: String) throws -> Double? {
        guard let value = args?[key] else { return nil }
        if let text = value.stringValue.flatMap(nonEmpty) {
            if let epoch = DateArg.parse(text) { return epoch }
            // A quoted epoch is unambiguous; accept it rather than failing a well-meaning caller.
            if let epoch = Double(text), epoch > 1_000_000_000 { return epoch }
            throw ToolError.unparsableDate(argument: key, value: text)
        }
        if case .number(let epoch) = value { return epoch }
        return nil
    }

    private static func clamp(_ value: Int, _ lower: Int, _ upper: Int) -> Int {
        min(max(value, lower), upper)
    }
}

// MARK: - Dates

/// Turns whatever Claude writes into an epoch. Returns nil for anything it cannot read, because the
/// caller must fail the tool call loudly: a date filter that is quietly dropped makes Claude reason
/// over the wrong slice of the user's life and never know it did.
public enum DateArg {
    public static func parse(_ s: String) -> Double? {
        let trimmed = s.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if let absolute = absolute(trimmed) { return absolute }
        let normalized = trimmed
            .lowercased()
            .trimmingCharacters(in: CharacterSet(charactersIn: ".,;:!?\"'"))
            .split(separator: " ", omittingEmptySubsequences: true)
            .joined(separator: " ")
        return relative(normalized)
    }

    // MARK: Absolute

    private static let isoFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    /// Longest first: `DateFormatter` happily matches a prefix, so a loose pattern must never get
    /// first look at a full timestamp.
    private static let fixedFormatters: [DateFormatter] = [
        "yyyy-MM-dd'T'HH:mm:ss.SSS",
        "yyyy-MM-dd'T'HH:mm:ss",
        "yyyy-MM-dd HH:mm:ss",
        "yyyy-MM-dd'T'HH:mm",
        "yyyy-MM-dd HH:mm",
        "yyyy/MM/dd HH:mm",
        "yyyy-MM-dd",
        "yyyy/MM/dd",
    ].map { format in
        let formatter = DateFormatter()
        formatter.dateFormat = format
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        return formatter
    }

    private static func absolute(_ s: String) -> Double? {
        if let date = isoFractional.date(from: s) { return date.timeIntervalSince1970 }
        if let date = iso.date(from: s) { return date.timeIntervalSince1970 }
        for formatter in fixedFormatters {
            if let date = formatter.date(from: s) { return date.timeIntervalSince1970 }
        }
        return nil
    }

    // MARK: Relative

    private static func relative(_ s: String) -> Double? {
        switch s {
        case "now": return ContextTime.now
        case "today": return localTime(daysAgo: 0, hour: 0)
        case "yesterday": return localTime(daysAgo: 1, hour: 0)
        // Deliberately early: as a lower bound, being an hour generous loses nothing, while being
        // late silently hides the start of the user's day.
        case "this morning": return localTime(daysAgo: 0, hour: 5)
        case "last night": return localTime(daysAgo: 1, hour: 18)
        case "last week", "this week": return localTime(daysAgo: 7, hour: 0)
        case "last month", "this month": return localTime(daysAgo: 30, hour: 0)
        default: return ago(s)
        }
    }

    /// Midnight-anchored so day boundaries land where the user thinks they do, DST included.
    private static func localTime(daysAgo: Int, hour: Int) -> Double? {
        let calendar = Calendar.current
        guard let day = calendar.date(byAdding: .day, value: -daysAgo, to: Date()) else { return nil }
        var components = calendar.dateComponents([.year, .month, .day], from: day)
        components.hour = hour
        components.minute = 0
        components.second = 0
        return calendar.date(from: components)?.timeIntervalSince1970
    }

    /// `"30 minutes ago"`, `"2 days ago"`, `"an hour ago"`.
    private static func ago(_ s: String) -> Double? {
        let parts = s.split(separator: " ").map(String.init)
        guard parts.count == 3, parts[2] == "ago" else { return nil }

        let count: Int
        if parts[0] == "a" || parts[0] == "an" {
            count = 1
        } else if let parsed = Int(parts[0]), parsed >= 0 {
            count = parsed
        } else {
            return nil
        }

        var unit = parts[1]
        if unit.count > 1, unit.hasSuffix("s") { unit.removeLast() }

        switch unit {
        case "second", "sec": return ContextTime.now - Double(count)
        case "minute", "min": return ContextTime.now - Double(count) * 60
        case "hour", "hr": return ContextTime.now - Double(count) * 3600
        case "day": return calendarAgo(.day, count)
        case "week": return calendarAgo(.weekOfYear, count)
        case "month": return calendarAgo(.month, count)
        case "year": return calendarAgo(.year, count)
        default: return nil
        }
    }

    private static func calendarAgo(_ component: Calendar.Component, _ count: Int) -> Double? {
        Calendar.current.date(byAdding: component, value: -count, to: Date())?.timeIntervalSince1970
    }
}
