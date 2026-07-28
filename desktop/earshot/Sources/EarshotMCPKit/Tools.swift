import EarshotCore
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

    /// Executes a tool against the store and returns the text payload for the MCP content block.
    public static func call(name: String, arguments: JSONValue?, store: EarshotStore?) throws -> String {
        guard all.contains(where: { $0.name == name }) else { throw ToolError.unknownTool(name) }
        // A missing database is the ordinary "you installed it five minutes ago" state, not an error.
        guard let store else { return neverRanMessage }

        switch name {
        case "recall": return try runRecall(arguments, store)
        case "recent": return try runRecent(arguments, store)
        case "conversations": return try runConversations(arguments, store)
        case "transcript": return try runTranscript(arguments, store)
        case "screen": return try runScreen(arguments, store)
        case "activity": return try runActivity(arguments, store)
        case "status": return try runStatus(store)
        default: throw ToolError.unknownTool(name)
        }
    }

    private static let neverRanMessage = """
    Earshot has not captured anything yet: the app has not run on this Mac, so there is no \
    speech, screen text, or activity history to search.
    """
}

// MARK: - Descriptions
//
// These are the product. They are the only thing Claude sees before deciding whether the answer to
// the user's question already exists on their machine, so they say *when to reach for the tool*.

extension Tools {
    static let recallDescription = """
    Search everything the user has said, heard in a call, or had on their screen — the running \
    record of their real life on this Mac, from speech transcripts and on-screen text.

    Reach for this whenever the user mentions a person, plan, decision, project, meeting, price, \
    place or event you have no record of. The answer is very often already in here. Prefer searching \
    over asking the user to explain context they have obviously already lived through, and search \
    again with different words — a name, a company, a phrase they would have said out loud — before \
    concluding you do not know.

    Results come back newest-first, grouped by day, each line timed and attributed: *me* is the user \
    speaking, *them* is the other side of a call, *screen* is text that was on their display. Bound \
    the search with `since` / `until` when the user anchors it in time. If it comes back empty, check \
    `status` before saying it never happened.
    """

    static let recentDescription = """
    See what the user is doing right now — the last N minutes of their speech and screen, merged in \
    order.

    Reach for this when a request starts mid-thought and assumes context you were never given: \
    "help me with this", "what do you think?", "draft a reply", "summarise that", "why is this \
    failing?". They mean something in front of them. Look before you ask them to paste it.

    Also worth calling at the start of a session to know what they are in the middle of, and right \
    after a call ends to catch what was just discussed.
    """

    static let conversationsDescription = """
    List the user's recent conversations and calls: when each started, how long it ran, which app it \
    happened in, whether both sides were captured, and a short preview.

    Reach for this when the user points at a conversation rather than a fact — "my call with Sarah", \
    "the standup this morning", "that interview last week", "what did I agree to yesterday" — and \
    you need to find the right one before reading it. A session tagged with a meeting app (Zoom, \
    Meet, Slack) and marked *both sides* is a real call; *one side only* is the user talking near \
    their Mac.

    Each entry carries a session id. Pass it to `transcript` to read the conversation in full.
    """

    static let transcriptDescription = """
    Read one whole conversation line by line, attributed to *me* (the user) and *them* (whoever they \
    were speaking with).

    Reach for this once `conversations` or `recall` has pointed you at a session and you need what \
    was actually said — the exact commitment, number, name, date or decision — rather than a \
    paraphrase. Use it before writing anything that must be faithful to a call: follow-up emails, \
    summaries, action items, meeting notes, "what did I promise them?".

    Quote from the transcript when details matter. It is on-device speech recognition, so names and \
    rare words can be misheard; read around a line before treating it as exact.
    """

    static let screenDescription = """
    See what the user was reading, writing, or looking at: the window titles they had open and the \
    text that was on screen, newest-first.

    Reach for this when the question is visual rather than spoken — an article, a document, a \
    dashboard, an error message, a chat thread, a pull request, a booking or checkout page, code \
    they were reading. It is also how you recover something the user saw but never said out loud, \
    which is most of what happens at a computer.

    Filter with `app` ("Safari", "Xcode", "Slack", "Figma") when you know where to look, and bound \
    it with `since` / `until`. For the shape of the day rather than its contents, use `activity`.
    """

    static let activityDescription = """
    Get the shape of the user's day or week: contiguous blocks of time per app and window, with \
    totals.

    Reach for this for questions about time and attention — "what did I do today", "where did the \
    afternoon go", "how long was I in Figma", "was I heads-down or in meetings", "what have I been \
    working on this week" — and whenever you are writing a standup, a status update, a timesheet, or \
    a weekly review for them.

    This is a summary of where they were, not what they saw. When you need the contents of those \
    windows, follow it with `screen` or `recall` over the same time range.
    """

    static let statusDescription = """
    Check what Earshot has actually recorded: whether it is capturing right now, which \
    permissions are granted, how much is stored, and the exact window of time it covers.

    Call this before telling the user that something never happened, or that you cannot find \
    anything. An empty search inside the coverage window is real evidence; an empty search outside \
    it, or with the microphone, system audio, or screen permission denied, only means nothing was \
    captured. Those two must never be reported to the user the same way.

    This is also the tool to reach for when the user asks whether Omi is working, why you seem to be \
    missing something, or how far back your knowledge of their machine goes.
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
                ("session_id", Schema.integer("""
                The id of the conversation to read, as printed by `conversations` (the number after \
                the #) or carried on a `recall` hit.
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
}

// MARK: - Implementations

extension Tools {
    private static func runRecall(_ args: JSONValue?, _ store: EarshotStore) throws -> String {
        guard let query = stringArg(args, "query") else {
            throw ToolError.missingArgument(tool: "recall", argument: "query")
        }
        let since = try dateArg(args, "since")
        let until = try dateArg(args, "until")
        let limit = clamp(intArg(args, "limit") ?? 40, 1, 500)

        let hits = try Queries.recall(store, query: query, since: since, until: until, limit: limit)
        guard !hits.isEmpty else {
            return emptyMessage(
                store,
                "Nothing Earshot captured matches \"\(query)\"\(rangeSuffix(since, until))."
            )
        }
        let header = "**\(plural(hits.count, "match", "matches")) for \"\(query)\"\(rangeSuffix(since, until))**"
        return header + "\n\n" + renderHits(hits, order: .newestFirst)
    }

    private static func runRecent(_ args: JSONValue?, _ store: EarshotStore) throws -> String {
        let minutes = clamp(intArg(args, "minutes") ?? 30, 1, 24 * 60)
        // `recent` is read as a narrative, so ask for enough lines to actually cover the window and
        // let the output budget do the trimming.
        let limit = clamp(minutes * 10, 120, 1500)

        let hits = try Queries.recent(store, minutes: minutes, limit: limit)
        guard !hits.isEmpty else {
            return emptyMessage(store, "Earshot captured nothing in the last \(plural(minutes, "minute")).")
        }
        let header = "**The last \(plural(minutes, "minute")) — \(plural(hits.count, "entry", "entries"))**"
        return header + "\n\n" + renderHits(hits, order: .oldestFirst)
    }

    private static func runConversations(_ args: JSONValue?, _ store: EarshotStore) throws -> String {
        let since = try dateArg(args, "since")
        let until = try dateArg(args, "until")
        let limit = clamp(intArg(args, "limit") ?? 30, 1, 200)

        let sessions = try Queries.sessions(store, since: since, until: until, limit: limit)
        guard !sessions.isEmpty else {
            return emptyMessage(store, "Earshot recorded no conversations\(rangeSuffix(since, until)).")
        }
        return renderSessions(sessions, since: since, until: until)
    }

    private static func runTranscript(_ args: JSONValue?, _ store: EarshotStore) throws -> String {
        guard let raw = args?["session_id"] else {
            throw ToolError.missingArgument(tool: "transcript", argument: "session_id")
        }
        guard let sessionId = raw.int64Value else {
            throw ToolError.invalidArgument(
                argument: "session_id",
                value: raw.stringValue ?? String(describing: raw),
                expected: "It must be the whole number printed after the # by `conversations`."
            )
        }

        let hits = try Queries.transcript(store, sessionId: sessionId)
        guard !hits.isEmpty else {
            return emptyMessage(
                store,
                """
                Earshot has no conversation #\(sessionId) — the id may be wrong, or the \
                conversation may predate what it recorded. Call `conversations` to list the ids it holds.
                """
            )
        }
        let start = hits.map(\.at).min() ?? 0
        let end = hits.map(\.at).max() ?? start
        let header = """
        **Conversation #\(sessionId)** — \(plural(hits.count, "line")), \
        \(EarshotTime.describe(start)) to \(timeFormatter.string(from: Date(timeIntervalSince1970: end))) \
        (\(duration(end - start)))
        """
        return header + "\n\n" + renderHits(hits, order: .oldestFirst)
    }

    private static func runScreen(_ args: JSONValue?, _ store: EarshotStore) throws -> String {
        let since = try dateArg(args, "since")
        let until = try dateArg(args, "until")
        let app = stringArg(args, "app")
        let limit = clamp(intArg(args, "limit") ?? 60, 1, 500)

        let hits = try Queries.screen(store, since: since, until: until, app: app, limit: limit)
        let appSuffix = app.map { " in \($0)" } ?? ""
        guard !hits.isEmpty else {
            return emptyMessage(
                store,
                "Earshot captured nothing on screen\(appSuffix)\(rangeSuffix(since, until))."
            )
        }
        let header = "**\(plural(hits.count, "screen observation"))\(appSuffix)\(rangeSuffix(since, until))**"
        return header + "\n\n" + renderHits(hits, order: .newestFirst)
    }

    private static func runActivity(_ args: JSONValue?, _ store: EarshotStore) throws -> String {
        // `dateArg` throws on an unreadable value, so nil here means the argument was simply absent.
        guard var since = try dateArg(args, "since") else {
            throw ToolError.missingArgument(tool: "activity", argument: "since")
        }
        var until = try dateArg(args, "until") ?? EarshotTime.now
        var swappedNote = ""
        if until < since {
            swap(&since, &until)
            swappedNote = "\n\n_`since` was later than `until`; the range was read the other way round._"
        }

        let blocks = try Queries.activity(store, since: since, until: until)
        guard !blocks.isEmpty else {
            return emptyMessage(
                store,
                "Earshot recorded no screen activity between \(EarshotTime.describe(since)) and \(EarshotTime.describe(until))."
            )
        }
        return renderActivity(blocks, since: since, until: until) + swappedNote
    }

    private static func runStatus(_ store: EarshotStore) throws -> String {
        let status = try Queries.status(store)
        return renderStatus(status)
    }
}

// MARK: - Rendering
//
// Markdown, not JSON. Claude reads a dated, attributed list of sentences far better than it reads a
// wall of records, and the day headings are what let it answer "on Tuesday you said…".

extension Tools {
    private enum HitOrder { case oldestFirst, newestFirst }

    /// Roughly 1500 rendered lines, whichever of the two limits bites first.
    private static let maxHitLines = 1500
    private static let maxHitCharacters = 120_000

    private static func renderHits(_ hits: [Hit], order: HitOrder) -> String {
        // Fit the *newest* hits into the budget regardless of display order, so truncation always
        // drops the least relevant end.
        let newestFirst = hits.sorted { $0.at > $1.at }
        var kept: [(hit: Hit, line: String)] = []
        var characters = 0
        var omitted = 0
        for hit in newestFirst {
            let line = hitLine(hit)
            if kept.count >= maxHitLines || characters + line.count > maxHitCharacters {
                omitted += 1
                continue
            }
            characters += line.count + 1
            kept.append((hit, line))
        }

        let display = order == .oldestFirst ? kept.sorted { $0.hit.at < $1.hit.at } : kept
        var out: [String] = []
        var currentDay: Date?
        let calendar = Calendar.current
        for entry in display {
            let day = calendar.startOfDay(for: Date(timeIntervalSince1970: entry.hit.at))
            if day != currentDay {
                if currentDay != nil { out.append("") }
                out.append(dayHeading(for: entry.hit.at))
                out.append("")
                currentDay = day
            }
            out.append(entry.line)
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

    private static func hitLine(_ hit: Hit) -> String {
        let time = timeFormatter.string(from: Date(timeIntervalSince1970: hit.at))
        let text = collapse(hit.text)
        switch hit.kind {
        case "said":
            return "- **\(time)** · *me*: \(text)"
        case "heard":
            return "- **\(time)** · *them*: \(text)"
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
                ? "- **\(time)** · *screen*\(context)"
                : "- **\(time)** · *screen*\(context): \(text)"
        default:
            return "- **\(time)** · *\(hit.kind)*: \(text)"
        }
    }

    private static func renderSessions(_ sessions: [SessionSummary], since: Double?, until: Double?) -> String {
        var out: [String] = [
            "**\(plural(sessions.count, "conversation"))\(rangeSuffix(since, until))**",
            "",
        ]
        for session in sessions.sorted(by: { $0.startedAt > $1.startedAt }) {
            var parts: [String] = [
                "#\(session.id)",
                sessionHeaderFormatter.string(from: Date(timeIntervalSince1970: session.startedAt)),
                session.endedAt == nil ? "ongoing" : duration(session.durationSeconds),
            ]
            if let app = session.appHint.flatMap(nonEmpty) { parts.append(app) }
            parts.append(session.bothSidesPresent ? "both sides" : "one side only")
            parts.append(plural(session.lineCount, "line"))
            out.append("### " + parts.joined(separator: " · "))

            let preview = session.preview.trimmingCharacters(in: .whitespacesAndNewlines)
            if !preview.isEmpty {
                for line in preview.split(separator: "\n") {
                    let trimmed = line.trimmingCharacters(in: .whitespaces)
                    if !trimmed.isEmpty { out.append("  " + trimmed) }
                }
            }
            out.append("")
        }
        out.append("_Call `transcript` with one of the session ids above to read that conversation in full._")
        return out.joined(separator: "\n")
    }

    private static func renderActivity(_ blocks: [ActivityBlock], since: Double, until: Double) -> String {
        var out: [String] = [
            "**Activity from \(EarshotTime.describe(since)) to \(EarshotTime.describe(until))**",
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
            let minutes = max(1, Int((block.durationSeconds / 60).rounded()))
            var line = "- **\(start)–\(end)** (\(minutes) min) · \(block.app)"
            if let window = block.window.flatMap(nonEmpty) { line += " — \(collapse(window))" }
            out.append(line)
            dayTotals[block.app, default: 0] += block.durationSeconds
        }
        flushTotals()
        return out.joined(separator: "\n")
    }

    private static func renderStatus(_ status: StatusInfo) -> String {
        var out: [String] = []

        let headline: String
        if status.capturing {
            headline = "Earshot is capturing right now."
        } else if let reason = status.pausedReason.flatMap(nonEmpty) {
            headline = "Earshot is not capturing right now — \(reason)."
        } else {
            headline = "Earshot is not capturing right now."
        }

        if status.segmentCount == 0 && status.frameCount == 0 {
            out.append("""
            \(headline) It has recorded nothing so far — no speech and no screen text — so an empty \
            answer from any other tool means "not captured", never "did not happen".
            """)
        } else {
            out.append("""
            \(headline) It holds \(plural(status.segmentCount, "transcript line")) across \
            \(plural(status.sessionCount, "conversation")) and \
            \(plural(status.frameCount, "screen observation")) on this Mac.
            """)
            out.append("")
            out.append("""
            Coverage: **\(status.coverage)**. Anything inside that window was recorded, so an empty \
            search there is real evidence it did not happen. Anything outside it was never captured.
            """)
        }

        out.append("")
        if status.capabilities.isEmpty {
            out.append("""
            - No permission report available — Earshot is not running, so it cannot say which of \
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
                At least one capture permission is off, so a whole class of context is missing rather \
                than absent. Say that plainly instead of concluding something never happened.
                """)
            }
        }

        out.append("")
        out.append("Database: `\(status.databasePath)`")
        return out.joined(separator: "\n")
    }

    /// The single most important non-result in the product: it is what stops Claude from turning
    /// "not captured" into "never happened".
    private static func emptyMessage(_ store: EarshotStore, _ sentence: String) -> String {
        guard let status = try? Queries.status(store) else {
            return sentence + "\n\n" + """
            Earshot could not read its own capture status, so treat this as "not captured" rather \
            than "did not happen".
            """
        }
        if status.segmentCount == 0 && status.frameCount == 0 {
            return """
            Earshot has not captured anything yet — no speech and no screen text has been recorded \
            on this Mac so far, so there is nothing to search. This is not evidence that anything did \
            or did not happen.
            """
        }

        var out = sentence
        out += "\n\n"
        out += """
        Earshot has recorded \(plural(status.segmentCount, "transcript line")) and \
        \(plural(status.frameCount, "screen observation")), covering **\(status.coverage)**.
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
        Inside that window an empty result is real evidence; outside it, nothing was ever recorded. \
        Try different wording, widen `since` / `until`, or call `status` for the full picture before \
        telling the user it did not happen.
        """
        return out
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

    private static let timeFormatter = fixedFormatter("h:mm a")
    private static let dayFormatter = fixedFormatter("EEEE d MMMM")
    private static let dayWithYearFormatter = fixedFormatter("EEEE d MMMM yyyy")
    private static let sessionHeaderFormatter = fixedFormatter("EEE d MMM, h:mm a")

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
        case let (since?, nil): return " since \(EarshotTime.describe(since))"
        case let (nil, until?): return " before \(EarshotTime.describe(until))"
        case let (since?, until?):
            return " between \(EarshotTime.describe(since)) and \(EarshotTime.describe(until))"
        }
    }

    private static func duration(_ seconds: Double) -> String {
        let total = Int(max(0, seconds).rounded())
        if total < 60 { return "\(total) sec" }
        let minutes = total / 60
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let remainder = minutes % 60
        return remainder == 0 ? "\(hours) h" : "\(hours) h \(remainder) min"
    }

    private static func number(_ value: Int) -> String {
        decimalFormatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    private static func plural(_ value: Int, _ singular: String, _ plural: String? = nil) -> String {
        value == 1 ? "\(number(value)) \(singular)" : "\(number(value)) \(plural ?? singular + "s")"
    }

    /// One hit is one line, so newlines and runs of whitespace have to go.
    private static func collapse(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace || $0.isNewline }).joined(separator: " ")
    }

    private static func nonEmpty(_ text: String) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
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
        case "now": return EarshotTime.now
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
        case "second", "sec": return EarshotTime.now - Double(count)
        case "minute", "min": return EarshotTime.now - Double(count) * 60
        case "hour", "hr": return EarshotTime.now - Double(count) * 3600
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
