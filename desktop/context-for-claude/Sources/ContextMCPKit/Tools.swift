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

/// A picture in a tool result, already encoded for the wire.
///
/// Base64 rather than `Data` because that is the only thing MCP's `image` content block carries,
/// and a path is deliberately not an option: the string in here is the image itself, so nothing
/// downstream is holding a reference only this Mac can resolve.
public struct ToolImage: Sendable, Equatable {
    public let base64: String
    public let mimeType: String

    public init(base64: String, mimeType: String) {
        self.base64 = base64
        self.mimeType = mimeType
    }
}

/// What one tool call produced: prose, and — for `look` alone — the pixels behind it.
///
/// The prose is never optional and never empty, including on the calls that carry an image. A
/// picture with no sentence saying *when* it was taken and *whether the screen has changed since*
/// is the one way this tool can mislead: a model reading a two-hour-old screenshot as the current
/// state of an app will confidently describe a UI that no longer exists.
public struct ToolOutput: Sendable, Equatable {
    public var text: String
    public var images: [ToolImage]

    public init(text: String, images: [ToolImage] = []) {
        self.text = text
        self.images = images
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
        ToolDefinition(name: "look", description: lookDescription, inputSchema: lookSchema),
        ToolDefinition(name: "activity", description: activityDescription, inputSchema: activitySchema),
        ToolDefinition(name: "status", description: statusDescription, inputSchema: statusSchema),
        ToolDefinition(name: "get_memories", description: getMemoriesDescription, inputSchema: getMemoriesSchema),
        ToolDefinition(name: "create_memory", description: createMemoryDescription, inputSchema: createMemorySchema),
        ToolDefinition(name: "edit_memory", description: editMemoryDescription, inputSchema: editMemorySchema),
        ToolDefinition(name: "delete_memory", description: deleteMemoryDescription, inputSchema: deleteMemorySchema),
    ]

    /// Executes a tool and returns the payload for the MCP content blocks.
    ///
    /// `store` is nil when nothing has been captured on this Mac yet — which is the *normal* state
    /// five minutes after install, and no longer means the tools have nothing to say: the Omi
    /// account's own history answers most of them on its own.
    public static func call(name: String, arguments: JSONValue?, store: ContextStore?, openError: Error? = nil) throws -> ToolOutput {
        guard all.contains(where: { $0.name == name }) else { throw ToolError.unknownTool(name) }

        if store == nil, let openError = openError, name != "status" {
            throw openError
        }

        var images: [ToolImage] = []
        let text: String
        switch name {
        case "recall": text = try runRecall(arguments, store)
        case "recent": text = try runRecent(arguments, store)
        case "conversations": text = try runConversations(arguments, store)
        case "transcript": text = try runTranscript(arguments, store)
        case "screen": text = try runScreen(arguments, store)
        case "look": (text, images) = try runLook(arguments, store)
        case "activity": text = try runActivity(arguments, store)
        case "status": text = runStatus(store, openError)
        case "get_memories": text = try runGetMemories(arguments)
        case "create_memory": text = try runCreateMemory(arguments)
        case "edit_memory": text = try runEditMemory(arguments)
        case "delete_memory": text = try runDeleteMemory(arguments)
        default: throw ToolError.unknownTool(name)
        }
        // The last thing before the transport, and deliberately here rather than in `renderMerged`:
        // Several tools render outside it and so carry no row budget of their own, and `activity`
        // has no row limit at any layer — a ceiling only some paths respect is not a ceiling. The
        // images are not clamped here and must not be: `FrameImages` bounds each one at the encode,
        // where dropping bytes means a smaller picture rather than half a JPEG.
        return ToolOutput(text: clampToolResult(text, tool: name), images: images)
    }

    /// Carried by every clamped result, so a truncated answer cannot be read as a complete one —
    /// by a model, or by a test asserting the clamp fired.
    static let clampedResultMarker = "Truncated to fit one reply"

    /// Cuts `text` to something the client will inline, on a line boundary, and says that it did.
    ///
    /// Silence is the dangerous failure here. A result that stops early without saying so reads as
    /// a complete account of the window, and "nothing after 1:06 PM" then becomes evidence that
    /// nothing happened after 1:06 PM.
    static func clampToolResult(_ text: String, tool: String) -> String {
        guard text.count > maxToolResultCharacters else { return text }

        let note = "\n\n_\(clampedResultMarker) — the end of this result was dropped. \(narrowingAdvice(for: tool))_"
        var body = String(text.prefix(max(0, maxToolResultCharacters - note.count)))
        // On a line boundary: half a rendered entry reads as a whole one, and half a timestamp is
        // not a shorter timestamp, it is a wrong one.
        if let lastBreak = body.lastIndex(of: "\n") { body = String(body[body.startIndex..<lastBreak]) }
        return body + note
    }

    /// Only the knobs the tool's own schema actually accepts.
    ///
    /// The shared note used to tell every caller to "narrow the range with `since` / `until`, or
    /// ask for a smaller `limit`" — advice `recent`, whose only parameter is `minutes`, cannot
    /// follow. Recovery instructions naming parameters that do not exist leave the model with no
    /// move except to ask again for exactly the same thing.
    private static func narrowingAdvice(for tool: String) -> String {
        switch tool {
        case "recall":
            return "Ask again with a narrower `since` / `until`, a smaller `limit`, or a more specific `query`."
        case "recent":
            return "Ask again with fewer `minutes`."
        case "conversations":
            return "Ask again with a narrower `since` / `until`, or a smaller `limit`."
        case "screen":
            return "Ask again with a narrower `since` / `until`, a single `app`, or a smaller `limit`."
        case "look":
            return "Ask again for fewer frames, or for a single `app`."
        case "activity":
            return "Ask again with a narrower `since` / `until`."
        case "transcript":
            return "This conversation is longer than one reply can carry; use `recall` to find the moment you need inside it."
        default:
            return "Ask again over a narrower range."
        }
    }

    /// Why this reader has no database, said in the user's terms.
    ///
    /// Never assert an empty life from an unopenable database. `diagnoseMissingDatabase()` reads the
    /// heartbeat, which the app rewrites every 30s and which no reader fault can forge: a live beat
    /// proves capture is running somewhere this process cannot see, which is a fact about *this
    /// binary*, not about the user. Saying "nothing was ever captured here" in that state is the
    /// confident falsehood the coverage-window design exists to prevent.
    static func missingDatabaseSentence(subject: String) -> String {
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
        case .databaseAwaitingUpgrade:
            return """
            \(subject) was updated and its capture database has not been upgraded yet, so this \
            reader cannot query it. **Nothing has been lost and the history is not empty** — do not \
            tell the user their recordings are gone. Opening the Context for Claude app once \
            performs the upgrade; it happens on launch, in under a second.
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
            // The account is only a way out of an empty local capture when this process is allowed
            // to reach it. Pointing at `recall` and `conversations` under Airgap Mode would send the
            // reader to two tools that will come back just as empty, and make the switch look like a
            // fault. `recall` still searches the main Omi app's local memories, which is worth
            // saying, because that half never touches the network.
            out += MCPNetworkEgress.isAirgapped()
                ? """
                The user's Omi account history cannot be reached either: Airgap Mode is on in \
                Context for Claude, so this process sends no requests. `recall` still searches the \
                memories the Omi app stored on this Mac, but the account's own conversations are \
                out of reach until Airgap Mode is turned off in Settings › General. None of that \
                means the user's history is empty.
                """
                : """
                The user's Omi account history is still available: use `recall` for what they have \
                said and what Omi remembers about them, and `conversations` for their recorded \
                conversations.
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
    a call, *screen* is text on their display), `omi` is the account's own history. A spoken line \
    marked `(uncertain — may be background audio, not speech)` scored below the transcriber's \
    confidence floor: it is shown rather than hidden, but it may be music or a video written out as \
    speech, so do not quote it or attribute it to anyone. Facts Omi remembers carry no date and are \
    listed separately. Bound the search with `since` / `until` when the user anchors it in time. If \
    it comes back empty, check `status` before saying it never happened.
    """

    static let recentDescription = """
    See what the user is doing right now, and what they were doing a few minutes ago — the last N \
    minutes of their speech and screen on this Mac, merged in order.

    This is the tool for "what was I just reading?", "what was I doing a few minutes ago?", "what \
    was that thing I had open?", "what have I been up to?" — anything anchored to the recent past \
    rather than to a name or a topic. Answer those from here instead of saying you cannot see it: \
    within this window nothing else can, because the Omi account has not received it yet.

    Reach for it too when a request starts mid-thought and assumes context you were never given: \
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
    exact. A line marked `(uncertain — may be background audio, not speech)` is one the recogniser \
    itself was unsure of — it may not be speech at all — so never quote that one.
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

    One freshness rule matters here: the Omi account's screen history is uploaded in batches and \
    runs hours behind this Mac's own capture, so the last couple of hours come from the `live` half \
    only. A gap there means "not synced yet", not "not on screen" — `recent` is the tool for the \
    current session. Every answer states how far that half has synced ("Screen synced through: …"), \
    so you never need a separate `status` call to tell an unsynced window from an idle one.
    """

    static let lookDescription = """
    Look at the user's actual screen — the real pixels, as an image you can see, from a few seconds \
    ago. `screen` gives you the text that was on the display; this gives you the display.

    **Use this whenever seeing beats being told.** They say "this looks wrong", "the spacing is \
    off", "why does it render like that", "is this centred", "does that look right to you" — look, \
    do not ask them to describe it or to take a screenshot. It is also how you check your own work: \
    after you change a UI, build it, run it, and look at it. A layout you reasoned about is a \
    guess; a layout you looked at is a fact, and this is the difference between "it should render \
    correctly now" and knowing that it does.

    Equally good for anything visual they have not narrated: a diff, a dashboard, a stack trace, a \
    design, a spreadsheet, a device on a video call, a page mid-checkout.

    `at` defaults to now and takes the same times the other tools do, so "what was on my screen at \
    2pm" works. `app` narrows to one application's frames ("Xcode", "Safari", or a bundle id) — \
    reach for it when the window you care about is not the one they are in front of right now.

    Two things to hold on to. **The picture is the newest capture at or before that moment, not a \
    fresh screenshot**, and every result states its age: an idle screen writes no new frame, so a \
    frame minutes old means the screen has not changed, while a frame minutes old *after you just \
    launched something* means capture is not keeping up — look again rather than describing stale \
    pixels. And a frame whose text held a credential comes back with the text and no picture, on \
    purpose; that is redaction working, not a failure.
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

    Read the history-depth section carefully: the dates in it come from a bounded probe of the \
    account, so they are a floor on what was sampled, never the date the user's record begins. \
    Searching with a `since` older than anything printed there is expected and does return results.
    """

    static let getMemoriesDescription = """
    List the durable facts Omi currently remembers about the user. Use this when you need to inspect
    the memory collection itself rather than search for a particular topic. These are account-backed
    Omi memories, not the live transcript captured by Context for Claude.
    """

    static let createMemoryDescription = """
    Save a durable fact to the user's Omi memories. Use this when the user asks you to remember a
    preference, identity detail, decision, standing instruction, or other fact for future chats.
    Save the user's request directly and do not claim it was saved until this tool succeeds. This
    writes to Omi's canonical memory store so the memory is available across Omi and future Context
    for Claude sessions.
    """

    static let editMemoryDescription = """
    Change the content of an existing Omi memory. Use this only when the user identifies a memory
    that should be corrected or updated. Pass the memory id returned by `get_memories` or `recall`.
    """

    static let deleteMemoryDescription = """
    Delete an existing Omi memory. Use this when the user explicitly asks to forget or remove a
    durable fact. Pass the memory id returned by `get_memories` or `recall`.
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

    static var lookSchema: JSONValue {
        Schema.object(properties: [
            ("at", Schema.string("The moment to look at; defaults to now. \(dateHelp)")),
            ("app", Schema.string("""
            Optional application to look at, as macOS shows it ("Xcode", "Safari", "Figma") or as a \
            bundle id. Leave it out for whatever was on screen.
            """)),
            ("count", Schema.integer("""
            How many frames to return, newest first. Defaults to 1. Ask for 2 or 3 to see a change \
            happen — what it looked like before and after — rather than one moment.
            """, default: 1)),
        ])
    }

    static var activitySchema: JSONValue {
        Schema.object(
            properties: [
                (
                    "since",
                    Schema.string(
                        """
                        Start of the range to summarise. At most \(activityMaxRangeDays) days are \
                        read per call; ask for a longer stretch and the most recent \
                        \(activityMaxRangeDays) days of it come back, saying so. \(dateHelp)
                        """)
                ),
                ("until", Schema.string("End of the range to summarise; defaults to now. \(dateHelp)")),
            ],
            required: ["since"]
        )
    }

    static var statusSchema: JSONValue { Schema.object() }

    static var getMemoriesSchema: JSONValue {
        Schema.object(
            properties: [
                ("limit", Schema.integer("Maximum number of durable memories to return.", default: 100)),
                ("offset", Schema.integer("Number of memories to skip before returning results.")),
                ("sort", Schema.string("Ordering: created_desc, updated_desc, scoring_desc, or manual_first.")),
                ("categories", Schema.array("Optional memory categories to include, such as preferences or facts.")),
            ])
    }

    static var createMemorySchema: JSONValue {
        Schema.object(
            properties: [
                ("content", Schema.string("The durable fact to save to Omi.")),
                ("category", Schema.string("Optional Omi memory category.")),
            ],
            required: ["content"])
    }

    static var editMemorySchema: JSONValue {
        Schema.object(
            properties: [
                ("memory_id", Schema.string("The Omi memory id to edit.")),
                ("content", Schema.string("The replacement durable fact text.")),
            ],
            required: ["memory_id", "content"])
    }

    static var deleteMemorySchema: JSONValue {
        Schema.object(
            properties: [("memory_id", Schema.string("The Omi memory id to delete."))],
            required: ["memory_id"])
    }
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

    static func array(_ description: String) -> JSONValue {
        .object([
            "type": .string("array"),
            "description": .string(description),
            "items": .object(["type": .string("string")]),
        ])
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

        var merged = local.rows.map(liveHit)
        merged += omi.conversations.map(omiConversationHit)

        // The headline prints the range it was asked for, so — as in `screen` and `conversations` —
        // the range is applied here rather than trusted to whichever half answered. Omi's search is
        // semantic and its date bounds are a request, not a guarantee. The remembered facts below
        // are deliberately exempt: they carry no timestamp at all, are rendered in their own
        // section, and that section says so.
        let ranged = restrictToRange(merged, since: since, until: until, at: \.at)
        merged = ranged.kept
        notes.append(contentsOf: rangeEnforcementNotes(ranged, noun: "record"))

        merged = dedupe(merged)
        merged = takeReservingScreen(merged, limit: limit)

        // `recall` reaches the account's conversations and memories but not its screen history, so
        // its screen rows are this Mac's alone. The watermark is what stops a reader concluding
        // anything from that — carried here rather than left to a second `status` call. It cannot be
        // observed on this path (no screen row is fetched), so it is honestly an estimate.
        let watermark = screenWatermark(
            newestOmiScreenRow: nil,
            accountRead: omiSearched(omi.failures),
            notReadClause: omiNotSearchedClause(omi.failures),
            estimateReason: """
            `recall` reads the account's conversations and memories, not its screen history — only \
            `screen` reads that
            """
        )

        let memories = Array(omi.memories.prefix(20))
        guard !merged.isEmpty || !memories.isEmpty else {
            return emptyMessage(
                store,
                nothingFound(
                    what: "matches for \"\(query)\"\(rangeSuffix(since, until))",
                    localSearched: local.searched,
                    omiSearched: omiSearched(omi.failures),
                    omiClause: omiNotSearchedClause(omi.failures)
                )
            )
                + "\n\n" + screenWatermarkSentence(watermark)
                + footerBlock(omi.failures, notes, localSearched: local.searched)
        }

        var out = header(
            for: merged,
            memories: memories,
            query: query,
            since: since,
            until: until,
            localSearched: local.searched
        )
        if !merged.isEmpty {
            out += "\n\n" + renderMerged(merged, order: .newestFirst)
        }
        if !memories.isEmpty {
            out += "\n\n" + renderMemories(memories)
        }
        // With the other provenance material rather than above the results: unlike `screen`, screen
        // rows are a minority of this answer, and the freshness note belongs beside the footer that
        // already says where each half came from.
        out += "\n\n" + screenWatermarkSentence(watermark)
        return out + footerBlock(omi.failures, notes, localSearched: local.searched)
    }

    private static func header(
        for hits: [MergedHit],
        memories: [OmiMemory],
        query: String,
        since: Double?,
        until: Double?,
        localSearched: Bool
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

        let headline = recallHeadline(
            query: query,
            range: rangeSuffix(since, until),
            liveMatches: live,
            omiRelated: omi + memories.count,
            localSearched: localSearched
        )

        let breakdown = parts.isEmpty ? "" : " — " + parts.joined(separator: ", ")
        let caveat = (omi > 0 || !memories.isEmpty)
            ? "\n\n_Omi's half of this is a semantic search: it returns the closest things it has, "
                + "even when nothing genuinely matches. Treat those as leads to confirm, not as "
                + "evidence the words were said._"
            : ""
        return headline + breakdown + caveat
    }

    /// The one line a reader takes away from `recall` — and the one that used to lie.
    ///
    /// "Nothing on this Mac matched X" is a **negative result**: it says the local half looked and
    /// came up empty, which is exactly the evidence a model is licensed to act on. It was printed
    /// verbatim when the local half had never run — no database to open, or a read that threw — so
    /// a search that could not execute read as proof that the thing never happened. A search that
    /// did not run is not a result, and this is where the two are kept apart.
    static func recallHeadline(
        query: String,
        range: String,
        liveMatches: Int,
        omiRelated: Int,
        localSearched: Bool
    ) -> String {
        if liveMatches > 0 {
            return "**\(plural(liveMatches, "match", "matches")) for \"\(query)\"\(range)**"
        }
        if !localSearched {
            let tail = omiRelated > 0 ? " Here is what Omi found related to it." : ""
            return """
            **This Mac's local capture was not searched for "\(query)"\(range) — the search could \
            not run, so nothing here is evidence about what was said or on screen at this Mac.\(tail)**
            """
        }
        if omiRelated > 0 {
            return """
            **Context for Claude searched this Mac's local capture for "\(query)"\(range) and found \
            no match — here is what Omi found related to it**
            """
        }
        return "**No results for \"\(query)\"\(range)**"
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
        entries += sessions.rows.map(localConversationEntry)

        // `renderConversations` prints the range it was *asked* for, so the range is enforced here
        // rather than trusted to whichever half answered — the same reason `screen` enforces it.
        // Omi's list endpoint takes date bounds and does not always honour them, and a conversation
        // shown under a header claiming a window it falls outside is worse than no filter at all:
        // the reader believes it is looking at one slice of the user's day while it is looking at
        // another, and nothing in the answer reveals the swap. Before the limit, so the cap is
        // never spent on rows this layer is about to drop.
        let ranged = restrictToRange(entries, since: since, until: until, at: \.at)
        entries = ranged.kept
        notes.append(contentsOf: rangeEnforcementNotes(ranged, noun: "conversation"))

        entries.sort { $0.at > $1.at }
        entries = Array(entries.prefix(limit))

        guard !entries.isEmpty else {
            return emptyMessage(
                store,
                nothingFound(
                    what: "conversations\(rangeSuffix(since, until))",
                    localSearched: sessions.searched,
                    omiSearched: omiSearched(failures),
                    omiClause: omiNotSearchedClause(failures)
                )
            ) + footerBlock(failures, notes, localSearched: sessions.searched)
        }
        return renderConversations(entries, since: since, until: until)
            + footerBlock(failures, notes, localSearched: sessions.searched)
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
                // "Sign in and this will work" is not true while Airgap Mode is on — the app
                // suppresses sign-in under the same switch. Advice that cannot be followed reads as
                // a broken product.
                if let blocked = MCPNetworkEgress.signInBlockedNote { out += " " + blocked }
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
        // `screenPage`, not `screen`: it reports whether the local half was truncated. Without that
        // the caller counts `limit` hits and cannot tell a complete answer from a bounded slice,
        // which is how a partial list gets reported as the whole record.
        var localTruncated = false
        let local = readLocal(store, &notes) { store -> [Hit] in
            let page = try Queries.screenPage(store, since: since, until: until, app: app, limit: limit)
            localTruncated = page.truncated
            return page.hits
        }

        let backend = OmiBackend.shared.screenActivity(since: since, until: until, app: app, limit: limit)
        let failures = backend.failure.map { ["screen history: \($0.reason)"] } ?? []

        // Derived from the rows this answer already holds, so the caller learns the account's screen
        // freshness without a second `status` call and without a second request being spent on it.
        let watermark = screenWatermark(
            newestOmiScreenRow: (backend.value ?? []).compactMap(\.at).max(),
            accountRead: omiSearched(failures),
            notReadClause: omiNotSearchedClause(failures),
            estimateReason: "the account returned no dated screen row for this query"
        )

        var merged = local.rows.map(liveHit)
        merged += (backend.value ?? []).map(omiScreenHit)
        merged = dedupe(merged)

        // The header prints the range it was asked for, so the range is enforced *here* rather than
        // trusted to whichever half answered. Printing a filter that was not applied is the same
        // class of lie as an understated coverage window: the reader believes it is looking at one
        // slice of the user's day while it is actually looking at another.
        let ranged = restrictToRange(merged, since: since, until: until, at: \.at)
        merged = ranged.kept
        notes.append(contentsOf: rangeEnforcementNotes(ranged, noun: "record"))

        // Newest-first is a promise this tool makes in its description and its header; sort for it
        // here so the promise holds whatever order either half happened to return.
        merged.sort { $0.at > $1.at }
        let available = merged.count
        merged = Array(merged.prefix(limit))

        let appSuffix = app.map { " in \($0)" } ?? ""
        guard !merged.isEmpty else {
            var out = emptyMessage(
                store,
                nothingFound(
                    what: "screen observations\(appSuffix)\(rangeSuffix(since, until))",
                    localSearched: local.searched,
                    omiSearched: omiSearched(failures),
                    omiClause: omiNotSearchedClause(failures)
                )
            )
            // The empty answer is exactly where the watermark decides the meaning: a window inside
            // the unsynced tail returns nothing from the account whether or not the user was at
            // their screen, and only the watermark tells those two apart.
            out += "\n\n" + screenWatermarkSentence(watermark)
            if let lag = omiScreenLagCaveat(until: until) { out += "\n\n" + lag }
            return out + footerBlock(failures, notes, localSearched: local.searched)
        }

        let header = """
        **\(plural(merged.count, "screen observation"))\(appSuffix)\(rangeSuffix(since, until))**, \
        newest first
        """
        // Above the rows, because on this tool freshness decides how the whole list should be read.
        var out = header + "\n\n" + screenWatermarkSentence(watermark)
            + "\n\n" + renderMerged(merged, order: .newestFirst)
        // `available` only ever counted the rows this answer already held, so a local half that was
        // itself capped could never trip it — the disclosure was unreachable on a local-only answer.
        if available > merged.count || localTruncated {
            out += "\n\n" + """
            _These are the \(number(merged.count)) newest of at least \(number(available)) \
            observations that matched; raise `limit` or narrow `since` / `until` to see older ones._
            """
        }
        if let lag = omiScreenLagCaveat(until: until) { out += "\n\n" + lag }
        return out + footerBlock(failures, notes, localSearched: local.searched)
    }

    /// `look` — the newest captured frames at or before a moment, as pictures.
    ///
    /// Local only, and unlike every other local-only tool it cannot fall back to the account: the
    /// Omi backend stores screen *text*, never pixels, so there is no remote half to merge. When
    /// this Mac has nothing, the honest answer is that there is nothing to look at.
    ///
    /// The prose is built even when a picture is returned, and it is built first, because the two
    /// failure modes here are both failures of framing rather than of retrieval: a stale frame read
    /// as the live screen, and a redacted frame's pixels handed over anyway.
    private static func runLook(_ args: JSONValue?, _ store: ContextStore?) throws -> (String, [ToolImage]) {
        let at = try dateArg(args, "at") ?? ContextTime.now
        let app = stringArg(args, "app")
        // Three at most. Each image costs roughly as much of the reply as several thousand words of
        // prose, and a fourth screenshot has never been the thing that answered the question.
        let count = clamp(intArg(args, "count") ?? 1, 1, 3)

        guard let store else { return (noLocalCaptureMessage, []) }

        let frames = try RewindQueries.newestFrames(store, at: at, app: app, limit: count)
        guard let newest = frames.first else {
            return (nothingToLookAt(at: at, app: app, store: store), [])
        }

        var out: [String] = [headline(forFrameAt: newest.capturedAt, requestedAt: at)]
        var images: [ToolImage] = []

        for frame in frames {
            out.append("")
            out.append(describe(frame))
            // Evidence the model can act on, in both directions: a picture it can read, or the
            // reason there is none. Silence would leave "the screenshot did not arrive" and "this
            // screen had a credential on it" looking identical.
            if let reason = withheldReason(frame) {
                out.append(reason)
            } else if let image = FrameImages.modelImage(atPath: frame.imagePath) {
                images.append(image)
            } else {
                out.append("""
                _The picture for this moment is no longer on disk — the frame's own retention window \
                has passed, or the file could not be read. The text below is what survives of it._
                """)
            }
            if let text = frameText(frame) { out.append(text) }
        }

        if images.count > 1 {
            out.append("")
            out.append("_The images are in the same order as the moments above: newest first._")
        }
        return (out.joined(separator: "\n"), images)
    }

    /// The first line of a `look`, and the one that stops a stale frame being read as the live
    /// screen. Age is always stated, in the user's own clock time and as an interval.
    private static func headline(forFrameAt capturedAt: Double, requestedAt: Double) -> String {
        let age = max(0, requestedAt - capturedAt)
        let clock = clockFormatter.string(from: Date(timeIntervalSince1970: capturedAt))
        // Two thresholds, and the gap between them is the honest one. Under a minute is "now" at a
        // 3-second capture cadence. Past `idleFrameGrace` an unchanged screen has genuinely stopped
        // producing frames, so the reader is told what old actually means here rather than left to
        // assume the capture failed.
        if age < 60 {
            return "**The user's screen at \(clock)** — \(describeAge(age)), effectively live."
        }
        if age < idleFrameGrace {
            return """
            **The user's screen at \(clock)** — \(describeAge(age)). Capture writes a frame only \
            when the screen changes, so this is very likely still what is in front of them.
            """
        }
        return """
        **The user's screen at \(clock)** — \(describeAge(age)), which is the newest frame there \
        is. Either nothing on screen has changed since then, or screen capture stopped: `status` \
        is what tells those apart. Do not describe this as the current state of anything you have \
        just changed — look again first.
        """
    }

    /// Past this, "the screen has not changed" stops being the obvious reading of an old frame.
    ///
    /// Ten minutes is well beyond any capture hiccup at a 3-second cadence, and well inside how
    /// long a person legitimately sits on one unchanged window while reading.
    static let idleFrameGrace: Double = 600

    private static func describeAge(_ seconds: Double) -> String {
        let whole = Int(seconds.rounded())
        if whole < 2 { return "captured just now" }
        if whole < 90 { return "captured \(whole) seconds ago" }
        let minutes = Int((seconds / 60).rounded())
        if minutes < 90 { return "captured \(number(minutes)) minutes ago" }
        let hours = Int((seconds / 3600).rounded())
        if hours < 36 { return "captured \(number(hours)) hours ago" }
        return "captured \(number(Int((seconds / 86400).rounded()))) days ago"
    }

    private static func describe(_ frame: RewindFrame) -> String {
        let clock = clockFormatter.string(from: Date(timeIntervalSince1970: frame.capturedAt))
        let title = frame.windowTitle.flatMap(nonEmpty).map { " — \"\(collapse($0))\"" } ?? ""
        return "**\(clock) · \(frame.appName)\(title)**"
    }

    /// Why this frame's picture is not attached, or nil when it is.
    ///
    /// **The one rule that makes serving pixels safe.** Capture scrubs credential-shaped values out
    /// of a frame's text before storing it (`Redaction.scrub`), but the screenshot beside that text
    /// still shows the token in full — the scrub has never touched pixels, because until `look`
    /// nothing decoded them. So the marker left behind by the scrub is read back as evidence: a
    /// frame whose text was redacted is a frame whose picture would leak exactly what the redaction
    /// removed, and it is withheld. The text still goes back, so the moment is not lost.
    private static func withheldReason(_ frame: RewindFrame) -> String? {
        let sawCredential = [frame.ocrText, frame.axText]
            .compactMap { $0 }
            .contains { $0.contains(Redaction.marker) }
        guard sawCredential else { return nil }
        return """
        _No picture for this moment: a credential was visible on this screen and was redacted out of \
        the text below. The screenshot would show it in full, so it is withheld. This is redaction \
        working — say so rather than reporting a failed capture._
        """
    }

    /// The frame's own text, kept under the picture rather than instead of it.
    ///
    /// Both columns, in the order they are trustworthy: the accessibility text is exact where it
    /// exists, OCR sees everything drawn and guesses. Bounded hard, because the picture is the
    /// answer here and the text is the caption — an unbounded OCR dump would spend the reply that
    /// the image needs.
    private static func frameText(_ frame: RewindFrame) -> String? {
        let joined = [frame.axText, frame.ocrText]
            .compactMap { $0.flatMap(nonEmpty) }
            .joined(separator: "\n")
        guard let text = nonEmpty(joined) else { return nil }
        let bounded = text.count > lookTextBudget
            ? String(text.prefix(lookTextBudget)) + "…"
            : text
        return "```\n\(bounded)\n```"
    }

    /// Characters of frame text carried under one picture.
    static let lookTextBudget = 1_500

    /// What `look` says when there is no frame to look at — which is a different fact depending on
    /// why, and saying the wrong one tells the user their screen was never recorded when the truth
    /// is that they asked about a Tuesday before they installed the app.
    private static func nothingToLookAt(at: Double, app: String?, store: ContextStore) -> String {
        let moment = ContextTime.describe(at)
        let scope = app.map { " from \($0)" } ?? ""
        var out = "No screen capture\(scope) exists at or before \(moment)."

        // Named with the time of the frame that *does* exist, rather than asserting the screen was
        // being captured "then". Some frame at or before the moment asked for is only evidence that
        // capture reached that far back — on a Mac whose screen grant died three days ago it is the
        // three-day-old frame answering, and a sentence implying live capture would be wrong.
        if let app, let anyFrame = try? RewindQueries.newestFrames(store, at: at, app: nil, limit: 1).first {
            out += """
             The newest frame from any app at or before then is \
            \(ContextTime.describe(anyFrame.capturedAt)) — \(anyFrame.appName) — so it is the `app` \
            filter that matched nothing here, not the recording. \(app) either was not on screen or \
            is named differently on this Mac. Look again without the filter.
            """
            return out
        }

        // The heartbeat is the only thing that can tell "the screen is not being recorded right
        // now" from "this moment predates the recording", and it is a fact about the app rather
        // than about the user — so it is worth a sentence before any conclusion is drawn. It is an
        // *addition* to the closing caveat below, never a substitute: whichever branch produced the
        // empty answer, "not recorded" is the reading that must survive it.
        if let state = CaptureState.read(), !state.isStale,
           let screen = state.stream(StreamName.screen), !screen.state.isLive {
            out += """
             Screen capture is currently **\(screen.state.rawValue)**\
            \(screen.detail.flatMap(nonEmpty).map { " — \($0)" } ?? ""), so this is very likely a \
            gap in the recording rather than an idle screen.
            """
        }

        out += """
         Frames older than the retention window are deleted while their text survives, and nothing \
        before the app was installed was ever captured — so this is "not recorded", never "nothing \
        was on screen". `screen` and `activity` may still hold the text and the shape of that time.
        """
        return out
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

        // Clamped to the most recent `activityMaxRangeSeconds`, and said out loud. The tail rather
        // than the head because `until` defaults to now: a caller who names an absurd `since` is
        // asking "what have I been doing", and the recent end is the half that answers it.
        var clampNote = ""
        if until - since > activityMaxRangeSeconds {
            let asked = since
            since = until - activityMaxRangeSeconds
            clampNote = """
                _You asked for \(ContextTime.describe(asked)) to \(ContextTime.describe(until)). \
                `activity` \(clampedRangeMarker), so this covers \(ContextTime.describe(since)) \
                onwards and **nothing before that was read** — a gap in this answer, not an idle \
                Mac. Ask again with `since` and `until` inside the earlier stretch to see it._
                """
        }

        // Above the body, not below it. A month of blocks can outrun `maxToolResultCharacters`, and
        // that clamp cuts the tail — a disclosure appended after the last block is exactly the text
        // a long answer drops, leaving the shortened window reading as the one that was asked for.
        func answer(_ body: String) -> String {
            ([clampNote, body].filter { !$0.isEmpty }).joined(separator: "\n\n") + swappedNote
        }

        let blocks = try Queries.activity(store, since: since, until: until)
        guard !blocks.isEmpty else {
            // The empty answer carries it too. "No screen activity between X and Y" printed over a
            // window the caller never named is the exact sentence that turns "not read" into "never
            // happened" — the thing every empty answer in this file exists to prevent.
            return answer(
                emptyMessage(
                    store,
                    "Context for Claude recorded no screen activity on this Mac between \(ContextTime.describe(since)) and \(ContextTime.describe(until))."
                ))
        }
        return answer(renderActivity(blocks, since: since, until: until))
    }

    /// A store that opens but cannot be queried is a *third* state, and the one `try?` used to erase:
    /// the database is right there and readable enough to open, so reporting "never captured
    /// anything" is a lie about the user rather than a report about the reader. Carry the failure
    /// through and say which of the three actually happened.
    private static func runStatus(_ store: ContextStore?, _ openError: Error? = nil) -> String {
        var local: StatusInfo?
        var queryFailure: String?
        if let store {
            do {
                local = try Queries.status(store)
            } catch {
                queryFailure = error.localizedDescription
            }
        } else if let openError {
            queryFailure = openError.localizedDescription
        }
        return renderStatus(local, queryFailure: queryFailure) + "\n\n" + renderOmiStatus()
    }

    private static func runGetMemories(_ args: JSONValue?) throws -> String {
        let limit = clamp(intArg(args, "limit") ?? 100, 1, 500)
        let offset = max(0, intArg(args, "offset") ?? 0)
        let sort = stringArg(args, "sort") ?? "created_desc"
        guard ["created_desc", "updated_desc", "scoring_desc", "manual_first"].contains(sort) else {
            throw ToolError.invalidArgument(
                argument: "sort",
                value: sort,
                expected: "Use created_desc, updated_desc, scoring_desc, or manual_first.")
        }
        let categories: [String]
        if let raw = args?["categories"] {
            guard let values = raw.arrayValue else {
                throw ToolError.invalidArgument(
                    argument: "categories",
                    value: literalDescription(raw),
                    expected: "It must be an array of category strings.")
            }
            categories = values.compactMap(\.stringValue).compactMap(nonEmpty)
            guard categories.count == values.count else {
                throw ToolError.invalidArgument(
                    argument: "categories",
                    value: literalDescription(raw),
                    expected: "Every category must be a string.")
            }
        } else {
            categories = []
        }

        switch OmiBackend.shared.getMemories(limit: limit, offset: offset, categories: categories, sort: sort) {
        case let .ok(memories):
            guard !memories.isEmpty else {
                return offset == 0
                    ? "Omi has no durable memories matching that request."
                    : "Omi has no more durable memories at offset \(offset)."
            }
            return "**Omi memories** · \(memories.count) returned\n\n" + renderMemories(memories)
        case let .unavailable(error):
            return memoryOperationFailure("read Omi memories", error)
        }
    }

    private static func runCreateMemory(_ args: JSONValue?) throws -> String {
        guard let content = stringArg(args, "content") else {
            throw ToolError.missingArgument(tool: "create_memory", argument: "content")
        }
        let category = stringArg(args, "category")
        switch OmiBackend.shared.createMemory(content: content, category: category) {
        case let .ok(memory):
            let categorySuffix = memory.category.flatMap(nonEmpty).map { " (\($0))" } ?? ""
            return "Saved Omi memory\(categorySuffix): \(collapse(memory.content))\nMemory id: `\(memory.id)`"
        case let .unavailable(error):
            return memoryOperationFailure("save this Omi memory", error)
        }
    }

    private static func runEditMemory(_ args: JSONValue?) throws -> String {
        guard let id = stringArg(args, "memory_id") else {
            throw ToolError.missingArgument(tool: "edit_memory", argument: "memory_id")
        }
        guard let content = stringArg(args, "content") else {
            throw ToolError.missingArgument(tool: "edit_memory", argument: "content")
        }
        switch OmiBackend.shared.editMemory(id: id, content: content) {
        case .ok:
            return "Updated Omi memory `\(id)`."
        case let .unavailable(error):
            return memoryOperationFailure("update Omi memory `\(id)`", error)
        }
    }

    private static func runDeleteMemory(_ args: JSONValue?) throws -> String {
        guard let id = stringArg(args, "memory_id") else {
            throw ToolError.missingArgument(tool: "delete_memory", argument: "memory_id")
        }
        switch OmiBackend.shared.deleteMemory(id: id) {
        case .ok:
            return "Deleted Omi memory `\(id)`."
        case let .unavailable(error):
            return memoryOperationFailure("delete Omi memory `\(id)`", error)
        }
    }

    private static func memoryOperationFailure(_ operation: String, _ error: OmiBackendError) -> String {
        var out = "Could not \(operation): \(error.reason)."
        if error == .notConfigured { out += "\n\n" + OmiBackend.notConfiguredSentence }
        if error == .airgapped, let blocked = MCPNetworkEgress.signInBlockedNote { out += " " + blocked }
        return out
    }
}

// MARK: - Local reads
//
// A local failure degrades exactly like a backend failure. Once these tools answer from two
// sources, either one being down is a partial answer, never an exception.

extension Tools {
    /// The outcome of a local query, keeping apart the two things a bare `[]` destroys: **a search
    /// that ran and found nothing is evidence; a search that never ran is not.** Collapsing them is
    /// how `recall` came to headline "Nothing on this Mac matched X" for a database it had not
    /// managed to open — a failed search rendered as proof of absence.
    fileprivate struct LocalRead<Element> {
        let rows: [Element]
        /// True only when the query actually executed against a readable database.
        let searched: Bool
    }

    /// Runs a local query, turning a missing or unreadable database into a *non-result* plus a
    /// note. Absent is not the same as broken, and neither is the same as an empty history.
    private static func readLocal<Element>(
        _ store: ContextStore?,
        _ notes: inout [String],
        _ body: (ContextStore) throws -> [Element]
    ) -> LocalRead<Element> {
        guard let store else {
            let note = """
            Context for Claude has no readable capture database on this Mac, so its local half was \
            not searched at all — an absence above is not evidence about this Mac.
            """
            notes.append(note)
            return LocalRead(rows: [], searched: false)
        }
        do {
            return LocalRead(rows: try body(store), searched: true)
        } catch {
            let note = """
            Context for Claude's local database on this Mac is present but could not be read \
            (\(error)), so its local half was not searched — that is a reader fault, not an empty \
            history.
            """
            notes.append(note)
            return LocalRead(rows: [], searched: false)
        }
    }

    /// True when the Omi half actually ran. `isConfigured` alone is not enough: a configured account
    /// that answered 429 was not searched either.
    fileprivate static func omiSearched(_ backendFailures: [String]) -> Bool {
        OmiBackend.shared.isConfigured && backendFailures.isEmpty
    }

    /// Why the Omi half did not run, as a clause that reads inside a sentence.
    fileprivate static func omiNotSearchedClause(_ backendFailures: [String]) -> String {
        guard OmiBackend.shared.isConfigured else { return "no Omi MCP API key is configured" }
        guard !backendFailures.isEmpty else { return "it was searched" }
        return "it could not be read (\(backendFailures.joined(separator: "; ")))"
    }
}

// MARK: - Freshness
//
// The two halves are not equally fresh, and the gap is widest exactly where it hurts most. Speech
// reaches the Omi account within minutes; **screen observations reach it hours later**, because they
// are uploaded in batches behind everything else. So the freshest hour of the user's screen is
// precisely the hour the account cannot show — and a model that does not know this reads the gap as
// "the user was not looking at that", when the truth is "this has not synced yet".

extension Tools {
    /// How far the Omi account's screen half is expected to trail this Mac's own capture. Measured
    /// against a live account: conversations arrived in minutes, screen rows in roughly two hours.
    static let omiScreenSyncLag: Double = 2 * 3_600

    /// Printed only when the account is readable at all and the window the caller asked for reaches
    /// into the unsynced tail — the same caveat on a query about last March would be noise.
    static func omiScreenLagCaveat(until: Double?, now: Double = ContextTime.now) -> String? {
        guard OmiBackend.shared.isConfigured else { return nil }
        return screenLagSentence(until: until, now: now)
    }

    /// The pure half: does this window reach into the part of the day Omi has not ingested yet?
    /// `until` in the past by more than the lag means the whole window has had time to arrive.
    static func screenLagSentence(until: Double?, now: Double) -> String? {
        if let until, until < now - omiScreenSyncLag { return nil }
        return """
        _Freshness: the Omi account's screen history syncs in batches and runs roughly \
        \(duration(omiScreenSyncLag)) behind this Mac, while its conversations lag only minutes. \
        Anything on screen in the last couple of hours therefore exists only in the `live` rows from \
        this Mac — a gap there means "not synced to Omi yet", never "not on screen". Use `recent` \
        for the current session._
        """
    }

    /// How far the Omi account's screen history has actually synced, as this response can honestly
    /// state it.
    ///
    /// `screenLagSentence` says the account is *behind*; it never says *how far, as of when*. A
    /// caller asking `screen` for "the last hour" therefore had to make a second `status` call to
    /// find out whether an empty answer meant "nothing was on screen" or "not uploaded yet" — and a
    /// caller who skipped that call read a sync gap as a fact about the user. The watermark is that
    /// missing fact, carried on the answer itself.
    ///
    /// Three cases, because they are three different amounts of evidence and only the first is a
    /// measurement. None of them costs an extra request: a `status`-style probe on every `recall`
    /// would spend the account's 300-reads-an-hour budget to restate what the response already knows.
    enum ScreenWatermark: Equatable {
        /// Proven by a dated row the account actually returned here. A floor, never a ceiling — this
        /// query's own `until` and `app` filters cap what could come back — so it is printed as
        /// "at least".
        case observed(Double)
        /// No dated screen row came back, so the only thing available is the measured batch lag.
        /// Carries *why* it is only an estimate, because "estimated" without a reason invites a
        /// reader to round it up to "known".
        case estimated(Double, String)
        /// The account was not read at all. An estimate of something nobody looked at is a number
        /// with no evidence behind it, so this case prints no time whatsoever.
        case unavailable(String)
    }

    static func screenWatermark(
        newestOmiScreenRow: Double?,
        accountRead: Bool,
        notReadClause: String,
        estimateReason: String,
        now: Double = ContextTime.now
    ) -> ScreenWatermark {
        guard accountRead else { return .unavailable(notReadClause) }
        if let at = newestOmiScreenRow, at > 0 { return .observed(at) }
        return .estimated(now - omiScreenSyncLag, estimateReason)
    }

    static func screenWatermarkSentence(_ watermark: ScreenWatermark) -> String {
        switch watermark {
        case let .observed(at):
            return """
            _Screen synced through: **at least \(ContextTime.describe(at))** — the newest screen row \
            the Omi account returned for this query. That is a floor rather than a ceiling, since \
            this query's own filters cap what could come back. Anything after it may exist only in \
            the `live` rows captured on this Mac, so read a gap there as "not synced to Omi yet", \
            never as "not on screen"._
            """
        case let .estimated(at, reason):
            return """
            _Screen synced through: **not confirmed — estimated at about \(approximateTime(at))**, \
            i.e. now minus the \(duration(omiScreenSyncLag)) batch lag measured against a live \
            account (\(reason)). It is an estimate from that lag, not a time Omi reported, which is \
            why it is stated to the hour: do not quote it back as the sync time. Treat anything after \
            it as "may not have synced yet" rather than as absent, and use `recent` for the current \
            session._
            """
        case let .unavailable(clause):
            return """
            _Screen synced through: **unknown** — the Omi account's screen history was not read for \
            this answer (\(clause)), so nothing here establishes how far it has synced. A missing \
            screen record is therefore not evidence that nothing was on screen._
            """
        }
    }

    /// An estimate rendered to the hour. A guess printed to the minute reads as a measurement, and
    /// this one is only ever as good as a lag measured once against one account.
    private static func approximateTime(_ epoch: Double) -> String {
        ContextTime.describe((epoch / 3_600).rounded(.down) * 3_600)
    }

    /// The same fact, said in `status`, where a model goes to find out what these tools can see.
    static var screenLagStatusLine: String {
        """
        Freshness: this Mac's own capture is seconds old. The Omi account's *conversations* trail it \
        by minutes, but its *screen* history trails it by roughly \(duration(omiScreenSyncLag)) — it \
        is uploaded in batches. The most recent couple of hours of screen text therefore exist only \
        here, on this Mac, and are missing from the account half of `recall` and `screen`. Do not \
        read that gap as "it was not on screen".
        """
    }
}

// MARK: - Transcription confidence
//
// A transcript line is a guess with a probability attached, and this layer used to render every one
// of them as a fact. Music playing in the room reached the microphone and the recogniser turned the
// lyrics into first-person speech: the song was printed as *me*, in the user's own voice, beside
// things they had genuinely said and typographically identical to them. Nothing in the page let a
// reader doubt it, so the fabrication was inherited whole by whatever was written next.
//
// The fix is *not* to drop the line. Filtering low-confidence speech would make the record look
// cleaner than it is — the same lie facing the other way, and a quieter one, because the reader
// would see a tidy transcript and never learn the recogniser had been guessing. Mark it, keep it,
// and say once what the mark means.

extension Tools {
    /// The parenthetical every uncertain line carries. Written to be read by a model rather than
    /// decorated for a person: it names the doubt *and* its likeliest cause, so the mark still does
    /// its job in a page of results pasted somewhere the legend did not follow.
    static let uncertainTranscriptMarker = "(uncertain — may be background audio, not speech)"

    /// The bar this layer renders against, which is **not this layer's to choose**: `Hit` owns the
    /// number and the reasoning behind it, and a second copy of it here would let the query layer
    /// and the rendering layer disagree about which lines are doubtful while both looked right.
    static var transcriptConfidenceFloor: Double { Hit.lowConfidenceFloor }

    /// Whether this line is rendered with the marker.
    ///
    /// Recomputed from the score rather than read off `Hit.isLowConfidence`, which is derived at
    /// init: `confidence` is a `var`, so a hit rebuilt or adjusted after construction can carry a
    /// flag that no longer matches its own number, and the direction that failure takes is silent
    /// under-marking. The floor is still `Hit`'s.
    ///
    /// Three things are deliberately *not* marked:
    /// - `nil` confidence — every line recorded before the column existed. Unknown is not doubtful,
    ///   and back-dating doubt onto the whole archive would empty the marker of meaning.
    /// - screen hits — OCR confidence measures a different thing and is a separate problem; this
    ///   field is transcription-only, and a screen row must never wear a "background audio" mark.
    ///   `Queries` carries a collapsed hit's score through rather than defaulting it, so this guard
    ///   is what keeps that from ever reaching the page as speech doubt.
    /// - a score outside 0...1 — not a probability on the scale this layer reads, so it says
    ///   nothing at all. Treating an unreadable number as doubt would mark every line in the
    ///   database the day an upstream layer started storing log-probabilities.
    static func isUncertainTranscript(_ hit: Hit) -> Bool {
        guard hit.kind == "said" || hit.kind == "heard" else { return false }
        guard let confidence = hit.confidence, (0...1).contains(confidence) else { return false }
        return confidence < transcriptConfidenceFloor
    }

    /// The convention, stated once per response and above the first line that uses it. A marker met
    /// cold is a decoration; a marker whose meaning arrived first is evidence about the evidence.
    static let uncertainTranscriptLegend = """
    _Confidence: a line marked \(uncertainTranscriptMarker) scored below the transcriber's \
    confidence floor of \(String(format: "%.2f", transcriptConfidenceFloor)) — the recogniser was \
    not sure it was hearing speech at all, and what it writes in that state is often music, a video, \
    or room noise rendered as if the user had said it. Marked lines are kept rather than dropped, but \
    do not quote one, attribute it to anybody, or act on it without corroboration elsewhere. Lines \
    without the mark are not certified correct — most predate confidence scoring — and the mark is \
    never applied to screen text, whose accuracy is a separate question._
    """
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
    /// True when `line` carries the low-confidence marker. Tracked rather than scraped back out of
    /// the rendered text, so the legend is printed exactly when a marked line survives the budget.
    let uncertain: Bool
    /// Whether this row is something the user was looking at rather than something said. Carried
    /// rather than inferred from `rank`, which breaks exact ties and is not a statement of modality.
    let isScreen: Bool

    init(
        at: Double,
        origin: Origin,
        key: String,
        rank: Int,
        line: String,
        uncertain: Bool = false,
        isScreen: Bool = false
    ) {
        self.isScreen = isScreen
        self.at = at
        self.origin = origin
        self.key = key
        self.rank = rank
        self.line = line
        self.uncertain = uncertain
    }
}

extension Tools {
    enum HitOrder { case oldestFirst, newestFirst }

    /// What enforcing the caller's window actually cost, so the tool can say it rather than hide it.
    ///
    /// Generic over the record because the window is a promise every listing tool prints, and the
    /// three that print it hold three different shapes: `screen` and `recall` merge hits, and
    /// `conversations` merges conversation entries. One enforcement seam is what keeps them from
    /// drifting into three different meanings of the same header.
    struct RangedRecords<Element> {
        let kept: [Element]
        let droppedOutOfRange: Int
        /// Undated records are kept — dropping real history over missing metadata is worse — but
        /// they are counted, because a reader must know they were never checked against the range.
        let undated: Int
    }

    /// Whether a record may be shown under the range the header prints.
    ///
    /// The header is a claim about what was filtered. If the filter did not run — a query that
    /// ignored `since`, a backend that ignored `start_date` — then the header is a lie unless the
    /// rendering layer makes it true. Undated records cannot be judged, so they are kept and
    /// reported separately rather than silently counted as in-range.
    static func isWithinRange(_ at: Double, since: Double?, until: Double?) -> Bool {
        guard at > 0 else { return true }
        if let since, at < since { return false }
        if let until, at > until { return false }
        return true
    }

    static func restrictToRange<Element>(
        _ records: [Element],
        since: Double?,
        until: Double?,
        at timestamp: (Element) -> Double
    ) -> RangedRecords<Element> {
        guard since != nil || until != nil else {
            return RangedRecords(kept: records, droppedOutOfRange: 0, undated: 0)
        }
        var kept: [Element] = []
        var dropped = 0
        var undated = 0
        for record in records {
            let at = timestamp(record)
            if at <= 0 { undated += 1 }
            if isWithinRange(at, since: since, until: until) {
                kept.append(record)
            } else {
                dropped += 1
            }
        }
        return RangedRecords(kept: kept, droppedOutOfRange: dropped, undated: undated)
    }

    /// What the enforcement cost, said out loud. Silently dropping a row is the same class of
    /// dishonesty as printing one that does not belong: either way the reader is looking at a
    /// different slice of the day than the one it believes, and only these notes close that gap.
    static func rangeEnforcementNotes<Element>(
        _ ranged: RangedRecords<Element>,
        noun: String
    ) -> [String] {
        var notes: [String] = []
        if ranged.droppedOutOfRange > 0 {
            notes.append("""
            \(plural(ranged.droppedOutOfRange, noun)) came back outside the \
            `since` / `until` range that was asked for and \
            \(ranged.droppedOutOfRange == 1 ? "was" : "were") dropped here, so the range printed \
            above is the range actually applied.
            """)
        }
        if ranged.undated > 0 {
            notes.append("""
            \(plural(ranged.undated, noun)) carried no timestamp, so \
            \(ranged.undated == 1 ? "it" : "they") could not be checked against the range and \
            \(ranged.undated == 1 ? "is" : "are") kept rather than dropped.
            """)
        }
        return notes
    }

    /// The most a tool result can be and still reach the model *as text*.
    ///
    /// An MCP client does not shorten an oversized result — it writes it to a file and hands the
    /// model a path. In the incident this ceiling exists to prevent, a 67,000-character `recent`
    /// became a file path and was never opened: the one line that answered the question had been
    /// captured, was returned, and went unread. A shorter answer that arrives beats a complete one
    /// that does not.
    ///
    /// The gate that fires is a *character* count, not a token estimate — worth stating because the
    /// obvious guess is wrong. Claude Code decides with a plain `.length` comparison against
    /// `min(tool.maxResultSizeChars, 50_000)`, inclusive, and MCP tools carry `maxResultSizeChars`
    /// of 100,000, so the real limit is 50,000 characters. The separate 25,000-token
    /// `MAX_MCP_OUTPUT_TOKENS` gate runs first but did not fire on the failing result: at 4
    /// characters per token it would have needed text denser than 2.68 chars/token to trip.
    ///
    /// 40,000 leaves a fifth of the budget spare, for the day a client ships a smaller cap or a
    /// caller's own wrapper adds to the payload.
    static let maxToolResultCharacters = 40_000

    /// Roughly 1500 rendered lines, whichever of the two limits bites first.
    ///
    /// Under `maxToolResultCharacters` by the headroom headers, watermarks and footers need, since
    /// those are appended *after* this budget. The renderer drops the least relevant lines and says
    /// how many; the boundary clamp can only cut the tail. Whichever one bites should be this one.
    private static let maxHitLines = 1500
    private static let maxHitCharacters = 36_000
    private static let omiOverviewLimit = 400
    private static let omiScreenTextLimit = 600

    /// The widest stretch `activity` will read in one call.
    ///
    /// Every other tool carries a `limit` that bounds the rows it touches. `activity` has none, and
    /// its range came straight from the model — whatever date it named, over a store the default
    /// retention never prunes. `Queries.activity` folds its rows through a cursor, so a huge range
    /// no longer *holds* them, but it still reads every one: on a synthetic year of capture at a
    /// frame a minute (525,600 frames), the walk was 5.5 s spent inside a single tool call, on the
    /// user's Mac, while Claude waits. The same read over 31 days was 0.47 s — the cost is linear in
    /// the range, which is exactly why bounding the range is the fix.
    ///
    /// 31 days because it is wider than the job the tool's own description describes — today, the
    /// afternoon, this week, a weekly review — so no ordinary call notices it. `clampToolResult`
    /// cannot serve here: it trims the *rendered* answer after the read has already happened, and
    /// the read is the cost.
    static let activityMaxRangeSeconds: Double = 31 * 86_400
    static var activityMaxRangeDays: Int { Int(activityMaxRangeSeconds / 86_400) }

    /// Carried by every answer whose range was clamped, for the same reason `clampedResultMarker`
    /// is carried by every clamped body: a bounded read that does not announce itself is read as a
    /// complete account of the window it prints.
    static var clampedRangeMarker: String { "reads at most \(activityMaxRangeDays) days in one call" }

    // MARK: Building

    /// Takes `limit` rows, but never lets the account's episodes crowd out what was on screen.
    ///
    /// `recall` merges this Mac's capture with the account's conversations and then keeps the top
    /// `limit` by rank. Screen loses that competition structurally: a conversation the account has
    /// already titled and summarised outranks a page the user was reading, so at the default limit
    /// screen vanished entirely. Measured on the search that prompted this — `recall("boston")`
    /// returned ten spoken lines and **none** of the six screen moments that matched, one of which
    /// was the travel page the user was actually looking at. Raising `limit` to 200 brought them
    /// back, which is what proves the rows were found and then discarded rather than never fetched.
    ///
    /// Speech and screen answer different questions — what was said, and what was in front of them
    /// — so neither may starve the other. A quarter of the answer is held for screen when screen
    /// matched at all; whatever that share does not need returns immediately to everything else.
    private static func takeReservingScreen(_ hits: [MergedHit], limit: Int) -> [MergedHit] {
        guard hits.count > limit else { return hits }
        let screen = hits.indices.filter { hits[$0].isScreen }
        guard !screen.isEmpty else { return Array(hits.prefix(limit)) }

        // The best `floor` screen rows are admitted first, then the remaining slots fill in rank
        // order. Selection only — the rows are returned in their original ranking, and the renderer
        // sorts for display, so reserving a share never reorders what the reader sees.
        var chosen = Set(screen.prefix(min(max(1, limit / 4), screen.count)))
        for index in hits.indices where chosen.count < limit {
            chosen.insert(index)
        }
        return hits.indices.filter { chosen.contains($0) }.map { hits[$0] }
    }

    private static func liveHit(_ hit: Hit) -> MergedHit {
        MergedHit(
            at: hit.at,
            origin: .live,
            key: fingerprint(hit.text, at: hit.at),
            rank: hit.kind == "screen" ? 1 : 0,
            line: hitLine(hit, origin: .live),
            uncertain: isUncertainTranscript(hit),
            isScreen: hit.kind == "screen"
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

    /// Internal like the other honesty seams in this file: this is the exact path `recent` and
    /// `transcript` render through, so a test of what a marked line looks like is a test of what the
    /// user's model will actually read.
    static func renderHitsOnly(_ hits: [Hit], order: HitOrder) -> String {
        renderMerged(
            hits.map {
                MergedHit(
                    at: $0.at,
                    origin: .live,
                    key: "",
                    rank: 0,
                    line: hitLine($0, origin: nil),
                    uncertain: isUncertainTranscript($0)
                )
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
        // Said once, before the first line that uses it, and only when one survived the budget: a
        // reader who meets the marker cold has no reason to weigh it, and a legend printed over a
        // page with nothing marked teaches them to expect doubt everywhere.
        if kept.contains(where: \.uncertain) {
            out.append(uncertainTranscriptLegend)
            out.append("")
        }
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
            Ask again over a narrower range to see them._
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
        // Before the text, never after it: the doubt has to reach the reader in the same glance as
        // the words, not as a footnote they meet once they have already believed the sentence.
        let doubt = isUncertainTranscript(hit) ? " \(uncertainTranscriptMarker)" : ""
        switch hit.kind {
        case "said":
            return "- **\(time)** · *me*\(tag)\(doubt): \(text)"
        case "heard":
            return "- **\(time)** · *them*\(tag)\(doubt): \(text)"
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

    /// The single most important non-result in the product: it is what stops Claude from turning
    /// "not captured" into "never happened".
    private static func emptyMessage(_ store: ContextStore?, _ sentence: String) -> String {
        // Every empty answer in the product is built here — `recall`, `recent`, `conversations`, an
        // empty `transcript`, `screen`, `activity` — which makes it the one place a sensor that was
        // switched off can be named without being said twice or missed on one path.
        let sensorOff = deniedCaptureClause().map { "\n\n" + $0 } ?? ""

        guard let store else {
            return sentence + "\n\n" + """
            Context for Claude has captured nothing on this Mac (no local database), so this answer rests \
            entirely on the Omi account. Treat it as "not found in what could be read" rather than \
            "did not happen", and call `status` to see which halves are actually available.
            """ + sensorOff
        }
        // A database that opens and then refuses to answer is the third state, and the one a `try?`
        // used to fold into "nothing was captured". The file is right there: this is a fault in the
        // reader, and saying anything about the user's history from it is a fabrication.
        guard let status = try? Queries.status(store) else {
            return sentence + "\n\n" + """
            Context for Claude's local database is present on this Mac but could not be read for this \
            answer, so its coverage window is unknown and its half of the search did not run. That is \
            a reader fault, not an empty history — do not report this as "nothing was captured". Call \
            `status` for the detail.
            """ + sensorOff
        }
        if status.segmentCount == 0 && status.frameCount == 0 {
            return sentence + "\n\n" + """
            Context for Claude has recorded nothing locally on this Mac yet, so nothing here rules anything out. \
            Call `status` to see whether the Omi account is reachable before telling the user this \
            did not happen.
            """ + sensorOff
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
        // Was a second, differently-worded rendering of the same permissions read from the same
        // heartbeat, on the one path of four that reached it. One clause, every path.
        out += sensorOff
        out += "\n\n"
        out += """
        Try different wording, widen `since` / `until`, or call `status` for the full picture — \
        including whether the Omi account was reachable for this answer — before telling the user it \
        did not happen.
        """
        return out
    }

    /// Capture permissions that were switched off, named so an empty answer cannot be mistaken for
    /// an empty life.
    ///
    /// "Both halves were searched, so this is a real empty result" is true and, on its own,
    /// misleading: if Screen Recording is denied there was never anything to search, and that
    /// sentence licenses a model to report that nothing was on screen. A search that ran perfectly
    /// over a sensor that was off is a fact about the sensor, not about the user.
    ///
    /// **Unknown stays unknown, in both directions.** No heartbeat, an unreadable one, or one that
    /// reports no capabilities at all produces no clause whatsoever — never a reassurance that the
    /// sensors were on. A *stale* beat is still reported, marked as last-known: a TCC grant outlives
    /// the process that wrote it, and while the app was gone nothing was being captured either, so
    /// silence there would be the more misleading answer of the two.
    ///
    /// The state is a parameter so the decision is testable without the machine's own heartbeat
    /// deciding what a test observes.
    static func deniedCaptureClause(_ state: CaptureState? = CaptureState.read()) -> String? {
        guard let state else { return nil }

        // Deliberately the wording `status` uses for the same fact. A reader that meets "not
        // granted" in one answer and a synonym in another has to work out that they are the same
        // claim, and the one place that matters is the answer that looks empty.
        let asOf = state.isStale
            ? " when Context for Claude last reported, \(duration(ContextTime.now - state.updatedAt)) ago"
            : ""

        var clauses: [String] = []
        let denied = state.capabilities.filter { !$0.granted }.map { capabilityPhrase($0.name) }
        if !denied.isEmpty {
            clauses.append("""
                **Not granted\(asOf): \(sentenceList(denied)).** That context was never captured at \
                all, so the absence above is a sensor that was switched off rather than evidence \
                about the user — do not report it as something that did not happen. `status` lists \
                every capture permission.
                """)
        }

        // **The second clause, and the reason this function was not enough on its own.** A stream
        // can be dead while its permission still reads "granted" — a grant this process cannot use
        // until it is relaunched, or a WindowServer that has stopped answering — and the capability
        // list above says nothing at all about that. That combination is what produced twenty-nine
        // hours of confident, empty answers about a screen that had not been captured since the
        // previous afternoon.
        let failing = state.failingStreams
        if !failing.isEmpty {
            let names = failing.map { streamPhrase($0.name) }
            let last = failing.compactMap(\.lastOutputAt).max()
            let since = last.map { " Nothing since \(ContextTime.describe($0))." } ?? ""
            clauses.append("""
                **Stopped working\(asOf): \(sentenceList(names)).**\(since) That half of the record \
                is missing rather than empty, whatever the permission list says — say so instead of \
                concluding anything about the user.
                """)
        }

        return clauses.isEmpty ? nil : clauses.joined(separator: "\n\n")
    }

    /// The `Capability` raw values as a reader meets them: `systemAudio` is a developer's word for
    /// the other side of a call.
    private static func capabilityPhrase(_ name: String) -> String {
        switch name {
        case "microphone": return "the microphone"
        case "systemAudio": return "call and system audio"
        case "screen": return "screen recording"
        // Named for what it costs the reader rather than for the TCC record, because
        // "accessibility" says nothing at all about which answers get worse. Screen capture still
        // reads the pixels without it; what is missing is the application's own strings.
        case "accessibility": return "reading the exact text in windows"
        default: return name
        }
    }

    /// Internal rather than file-private: `StatusTool` lists the same streams in the same answer,
    /// and two list-joiners is two places for the phrasing to drift apart.
    static func sentenceList(_ items: [String]) -> String {
        guard items.count > 1 else { return items.first ?? "" }
        return items.dropLast().joined(separator: ", ") + " and " + items[items.count - 1]
    }

    /// Says whether an empty answer is evidence at all.
    ///
    /// Two very different things end in nothing to show — "both halves were searched and there is
    /// nothing there" and "nothing could be searched" — and only the first is a result. A tool that
    /// prints one sentence for both teaches a reader to treat a broken search as proof of absence,
    /// which is the exact failure this product exists to prevent. So the sentence is built from the
    /// two facts, and names the half that did not run.
    ///
    /// It says nothing about capture permissions: a sensor that was off is a third fact, it applies
    /// to empty answers this sentence never reaches (`recent`, `activity`, an empty `transcript`),
    /// and `emptyMessage` — which every one of them goes through — is where it is said once.
    static func nothingFound(
        what: String,
        localSearched: Bool,
        omiSearched: Bool,
        omiClause: String
    ) -> String {
        // Neutral on purpose: it covers "there is no database here" and "the database would not
        // answer" alike, and the footer note below names which of the two it was.
        let localClause = "Context for Claude's capture on this Mac could not be read"
        switch (localSearched, omiSearched) {
        case (true, true):
            return """
            No \(what) were found in the Omi account or Context for Claude's local capture on this \
            Mac. Both halves were searched, so this is a real empty result rather than a failed \
            search.
            """
        case (true, false):
            return """
            No \(what) were found in Context for Claude's local capture on this Mac. The Omi account \
            was **not** searched — \(omiClause) — so nothing here is evidence about the user's \
            account history.
            """
        case (false, true):
            return """
            No \(what) were found in the user's Omi account. This Mac's local capture was **not** \
            searched — \(localClause) — so nothing here is evidence about what was said or on screen \
            at this Mac.
            """
        case (false, false):
            return """
            **No search ran.** Neither half could be read: \(localClause), and \(omiClause). This is \
            a failed search, not a negative result — it says nothing at all about whether there are \
            \(what), so do not report this as something that did not happen.
            """
        }
    }

    /// The one place a degraded answer is explained. Everything above it is real; this says exactly
    /// what is missing and why, which is what makes reasoning over a partial answer safe.
    private static func footerBlock(
        _ backendFailures: [String],
        _ localNotes: [String],
        localSearched: Bool = true
    ) -> String {
        var lines: [String] = []

        if !OmiBackend.shared.isConfigured {
            // The shared sentence ends by saying the local capture *was* searched. True in the
            // normal case, and a lie in the one where the local half did not run either — so that
            // case gets its own wording rather than a claim plus a contradiction two lines later.
            lines.append(localSearched ? "_\(OmiBackend.notConfiguredSentence)_" : """
            _Omi account history is unavailable: no Omi MCP API key is configured — sign in to the \
            Omi account from Context for Claude in the menu bar. This Mac's local capture could not \
            be read either, so nothing at all was searched for this answer._
            """)
            // Both branches above end by telling the reader to sign in, which Airgap Mode also
            // blocks. Appended once, after the branch, so the two wordings cannot drift apart.
            if let blocked = MCPNetworkEgress.signInBlockedNote { lines.append("_\(blocked)_") }
        } else if !backendFailures.isEmpty {
            lines.append("""
            _Omi account history could not be reached — \(backendFailures.joined(separator: "; ")). \
            Everything above is only what Context for Claude captured locally on this Mac, so an absence here is \
            not evidence about the user's history._
            """)
        } else {
            lines.append("""
            _Origins: `live` = captured by Context for Claude on this Mac, seconds fresh; `omi` = the user's Omi \
            account history, which lags a conversation by a few minutes and its screen text by \
            about \(duration(omiScreenSyncLag))._
            """)
        }

        // The notes are already whole sentences that say which half did not run and why — appending
        // a fixed clause to them used to assert "results above come from the Omi account only" even
        // when the Omi half had not run either.
        for note in localNotes {
            lines.append("_\(note)_")
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

    static func number(_ value: Int) -> String {
        decimalFormatter.string(from: NSNumber(value: value)) ?? String(value)
    }

    static func plural(_ value: Int, _ singular: String, _ plural: String? = nil) -> String {
        value == 1 ? "\(number(value)) \(singular)" : "\(number(value)) \(plural ?? singular + "s")"
    }

    /// One hit is one line, so newlines and runs of whitespace have to go.
    static func collapse(_ text: String) -> String {
        text.split(whereSeparator: { $0.isWhitespace || $0.isNewline }).joined(separator: " ")
    }

    static func nonEmpty(_ text: String) -> String? {
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
        if case .string(let raw) = value {
            // An empty string is "no filter asked for" — the header then prints no range, so
            // nothing is claimed that was not applied.
            guard let text = nonEmpty(raw) else { return nil }
            if let epoch = DateArg.parse(text) { return epoch }
            // A quoted epoch is unambiguous; accept it rather than failing a well-meaning caller.
            if let epoch = Double(text), epoch > 1_000_000_000 { return epoch }
            throw ToolError.unparsableDate(argument: key, value: text)
        }
        if case .number(let epoch) = value { return epoch }
        // A boolean, an array or an object is not a date under any reading. This used to fall
        // through to nil, which the caller reads as "no filter asked for": the search then ran over
        // the whole corpus, the header printed no range at all, and the caller believed it had
        // bounded the question with no way to find out that it had not.
        throw ToolError.invalidArgument(
            argument: key,
            value: literalDescription(value),
            expected: """
            A time filter must be text or an epoch number. \(dateHelp) The call was rejected rather \
            than run without the filter, so nothing here is a partial answer.
            """
        )
    }

    /// A short, quotable rendering of a value that is not the shape a tool asked for.
    private static func literalDescription(_ value: JSONValue) -> String {
        switch value {
        case .null: return "null"
        case let .bool(flag): return flag ? "true" : "false"
        case let .number(number): return String(number)
        case let .string(text): return text
        case .array: return "an array"
        case .object: return "an object"
        }
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
