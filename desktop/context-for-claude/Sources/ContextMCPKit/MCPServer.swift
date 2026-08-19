import ContextCore
import Foundation

/// The stdio MCP server Claude Code and Claude Desktop talk to.
///
/// Transport is line-delimited JSON-RPC 2.0: one request object per line in, one response object per
/// line out. **The output handle carries the protocol** — nothing but response lines may ever reach
/// it, so every diagnostic in this file goes to stderr.
public final class MCPServer {
    /// Server-level guidance, surfaced to the model once at connection time.
    ///
    /// Tool descriptions are only read when the model is already shopping for a tool. This is the
    /// earlier lever: it is in front of the model before the first question, and it is where the
    /// habit gets set — check what the user has already lived through *before* asking them to
    /// explain it. Without it the connector sits idle, advertised and never called, which is
    /// exactly what happened in practice.
    public static let instructions = """
    This server holds a continuous record of what this user has said, heard, and had on screen — \
    their real life on this Mac, plus their full Omi history going back months.

    **You are not limited to this conversation.** Questions about what the user was reading, \
    watching, working on, or talking about — a few minutes ago, this morning, last week — are \
    answerable here, and answering them is the entire reason this server is connected. Never tell \
    this user you have no access to what they were doing, that you can only see the current chat, or \
    that they should paste it in, search their browser history or look in past conversations. That \
    answer is wrong whenever these tools are connected, and it is the specific failure they exist to \
    prevent. Call a tool first; if the record genuinely has nothing, `status` will say so and *then* \
    you can report a real gap.

    Consult it early, not as a last resort. Before asking the user to explain who someone is, what \
    a project is, what was decided, when something happened, or what they are working on, search \
    here first — the answer is very often already on record, and asking them to repeat it is the \
    thing this server exists to prevent. A good default at the start of a task is `recall` for the \
    people and topics named in the request, and `recent` when the request assumes context you were \
    not given ("this", "that email", "help me with this").

    When the user asks you to remember a durable fact, preference, identity detail, decision, or \
    standing instruction, call `create_memory` and save it to Omi. Do not say it was saved until the \
    tool succeeds. Use `get_memories` to inspect durable facts, `edit_memory` to correct one, and \
    `delete_memory` only when the user explicitly asks you to forget it. A captured transcript is \
    not the same thing as a durable memory.

    Routing, when the question is about the recent past: `recent` for the current session (the last \
    minutes to an hour, and the only tool that sees them in full), `screen` for the *text* that was \
    on their display, `look` for the display itself as an image, `activity` for where the time \
    went, `recall` to search across everything by name or topic. Reaching for the wrong one of \
    these is recoverable; reaching for none of them is not.

    **`look` returns real pixels, so use it as your own eyes.** Anything the user describes visually \
    — "this looks wrong", "the spacing is off", "does that render properly" — is a thing to look at \
    rather than to ask about. So is your own work: after changing a UI, build it, run it, and look \
    at it before you report on it. Claiming a layout is fixed without looking is a guess dressed as \
    a result, and this is the tool that turns it into a check. Each result states its own age; \
    respect that line rather than assuming the frame is live.

    **This applies to subagents too, and they are where it is most often skipped.** A subagent \
    given a task inherits none of the conversation it came from, so it is the reader most likely to \
    be missing the context these tools hold and least likely to think to ask for it. If you are \
    dispatching one, either look the context up first and pass it in the prompt, or tell the \
    subagent explicitly that these tools exist and to use them. If you *are* a subagent and the \
    task refers to something you were not told — a person, a file, a decision, a screen — call \
    these tools before reporting that you lack context.

    Two rules for reading the results honestly. Hits marked as captured live on this Mac are exact \
    full-text matches. Hits from Omi's history are a semantic search with no relevance floor — it \
    always returns its nearest neighbours, even when nothing genuinely matches — so treat those as \
    leads to confirm rather than as evidence something was said. And before telling the user that \
    something never happened, call `status`: it reports exactly which windows of time were \
    recorded, which is what separates "did not happen" from "was not captured".
    """

    /// Every MCP revision this server's wire behaviour is correct under, newest first.
    ///
    /// The list is short because this server is small: it answers `initialize`, `ping`, `tools/list`
    /// and `tools/call`, and returns `text` content. Nothing in that set changed across these four
    /// revisions. The one removal that could have mattered — `2025-06-18` dropping JSON-RPC batching
    /// — costs us nothing, because ``run(input:output:)`` has only ever read one object per line and
    /// an array frame has always come back as an invalid request. Everything the newer revisions
    /// *added* (elicitation, sampling, tasks, structured output) is capability-gated, and this server
    /// declares `tools` and nothing else, so agreeing to a newer number promises no work it does not
    /// already do.
    public static let supportedProtocolVersions = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

    /// What we answer a client whose requested revision is not in that list.
    ///
    /// The spec's rule is "respond with a version you support, *should* be your latest". We answer
    /// the oldest instead, on purpose: a client asking for something we do not recognise is either
    /// older than every revision here — in which case our latest is further from it, not closer — or
    /// newer, in which case it reads a floor it certainly still supports. This is also the value this
    /// server answered unconditionally before negotiation existed, so no client that works today can
    /// be broken by the change; only clients that ask for something newer see a different number.
    public static let protocolVersion = "2024-11-05"

    /// The revision to run the session under, given what the client asked for in `initialize`.
    ///
    /// **Echoing the client's ask is the MUST**, and until this existed we ignored it and answered
    /// `2024-11-05` to everyone. That was tolerated — every shipping Claude lists `2024-11-05` among
    /// the versions it accepts — but it silently pinned every session to the oldest revision we know,
    /// which is the revision that has no `icons` field in it. Advertising ``ServerIcon`` while
    /// negotiating a version that does not define it would be a field smuggled onto the wire rather
    /// than a thing we agreed to speak.
    ///
    /// A missing or non-string `protocolVersion` falls back rather than erroring: an `initialize`
    /// that cannot be read is still an `initialize`, and refusing it would cost the user every tool
    /// to gain a pedantry.
    static func negotiatedProtocolVersion(requestedBy params: JSONValue?) -> String {
        guard let requested = params?["protocolVersion"]?.stringValue,
              supportedProtocolVersions.contains(requested)
        else { return protocolVersion }
        return requested
    }

    /// What Claude sees this connector called.
    ///
    /// Deliberately identical to `ClaudeConfig.serverName`, the key we write into Claude's config.
    /// Clients namespace tools by that key rather than by this string, so the two disagreeing would
    /// only ever mean the connector answered to one name and was listed under another.
    ///
    /// The name is a weak lever and should not be mistaken for a strong one: a previous comment here
    /// claimed it had been renamed to something self-describing, which was never true of the value
    /// underneath it. Renaming is also not free — the key is what a user's existing registration and
    /// their per-tool approvals hang off, and `ClaudeConfig.legacyServerNames` is the migration cost
    /// of having done it twice already. `instructions` above is the lever that actually steers
    /// selection.
    ///
    /// Literally the same value rather than a matching literal, because it now varies: a
    /// development build registers as `context-for-claude-dev`, and two constants that have to agree
    /// are two constants that can stop agreeing.
    public static let serverName = ClaudeConfig.serverName
    public static let serverVersion = "1.0.0"

    private let store: ContextStore?
    private let openError: Error?
    /// Where a served tool call is recorded so the app can prove Claude reached us.
    private let queryStampURL: URL
    /// Where served calls are *counted*, so the app can report how much this install is used.
    /// Derived from the same place as `queryStampURL` and for the same reason.
    private let toolCallLedgerURL: URL

    /// `store` is nil when nothing has been captured yet; the tools explain that in prose.
    ///
    /// `queryStampURL` defaults to the stamp beside the database this server opened, falling back to
    /// the standard location when there is no database yet. Both resolve to the same file in a real
    /// install; deriving it from the store keeps a server that was pointed at another data directory
    /// from reporting its calls into the default one.
    public init(
        store: ContextStore?,
        openError: Error? = nil,
        queryStampURL: URL? = nil,
        toolCallLedgerURL: URL? = nil
    ) {
        self.store = store
        self.openError = openError
        self.queryStampURL = queryStampURL
            ?? store.map { ContextPaths.queryStampURL(besideDatabaseAt: $0.databaseURL) }
            ?? ContextPaths.queryStampURL
        self.toolCallLedgerURL = toolCallLedgerURL
            ?? store.map { ContextPaths.toolCallLedgerURL(besideDatabaseAt: $0.databaseURL) }
            ?? ContextPaths.toolCallLedgerURL
    }

    // MARK: - Transport

    /// Reads lines from `input`, writes response lines to `output`. Returns when input closes.
    ///
    /// Reads incrementally through the handle rather than `readLine()`, which would bind this loop to
    /// the process's own stdin and make the class untestable with a pipe.
    public func run(input: FileHandle = .standardInput, output: FileHandle = .standardOutput) {
        var buffer = Data()
        while true {
            let chunk = input.availableData
            if chunk.isEmpty { break } // EOF: the client closed the pipe.
            buffer.append(chunk)
            while let newline = buffer.firstIndex(of: 0x0A) {
                let line = Data(buffer[buffer.startIndex..<newline])
                buffer.removeSubrange(buffer.startIndex...newline)
                respond(to: line, on: output)
            }
        }
        // A final frame with no trailing newline still deserves an answer.
        if !buffer.isEmpty {
            respond(to: buffer, on: output)
        }
    }

    private func respond(to lineData: Data, on output: FileHandle) {
        guard let raw = String(data: lineData, encoding: .utf8) else {
            write(RPC.error(id: nil, code: RPC.Code.parseError, message: "Parse error: line is not UTF-8"),
                  to: output)
            return
        }
        guard let response = handle(line: raw) else { return }
        write(response, to: output)
    }

    private func write(_ response: String, to output: FileHandle) {
        guard let data = (response + "\n").data(using: .utf8) else { return }
        do {
            try output.write(contentsOf: data)
        } catch {
            // A closed pipe is the client going away, not a crash.
            Self.note("write failed: \(error)")
        }
    }

    // MARK: - Dispatch

    /// Testable single-message path. Returns the response line, or nil for a notification.
    /// Never throws: a tool failure is reported to the model as a result, not as a crash.
    public func handle(line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }

        guard let frame = RPC.json(line: trimmed) else {
            return RPC.error(id: nil, code: RPC.Code.parseError, message: "Parse error")
        }
        guard let request = RPC.request(from: frame) else {
            return RPC.error(id: frame["id"], code: RPC.Code.invalidRequest, message: "Invalid Request")
        }
        // Notifications carry no id and take no reply — answering one desynchronizes the client.
        if request.isNotification || request.method.hasPrefix("notifications/") { return nil }

        switch request.method {
        case "initialize":
            return RPC.result(id: request.id, [
                "protocolVersion": .string(Self.negotiatedProtocolVersion(requestedBy: request.params)),
                "capabilities": ["tools": [:]],
                // `icons` is the only place MCP lets a server say what it looks like, and it rides
                // here or nowhere: there is no per-tool, per-call or config-file route a client
                // reads instead. Sent unconditionally, including to clients whose negotiated
                // revision predates the field — it is an unknown key those clients drop, which is
                // cheaper than tracking which of them would have used it.
                "serverInfo": [
                    "name": .string(Self.serverName),
                    "version": .string(Self.serverVersion),
                    "icons": .array([ServerIcon.json]),
                ],
                "instructions": .string(Self.instructions),
            ])

        case "ping":
            return RPC.result(id: request.id, [:])

        case "tools/list":
            let tools = Tools.all.map { tool in
                JSONValue.object([
                    "name": .string(tool.name),
                    "description": .string(tool.description),
                    "inputSchema": tool.inputSchema,
                ])
            }
            return RPC.result(id: request.id, ["tools": .array(tools)])

        case "tools/call":
            return callTool(request)

        default:
            return RPC.error(id: request.id,
                             code: RPC.Code.methodNotFound,
                             message: "Method not found: \(request.method)")
        }
    }

    private func callTool(_ request: RPCRequest) -> String {
        guard let name = request.params?["name"]?.stringValue else {
            return RPC.error(id: request.id,
                             code: RPC.Code.invalidParams,
                             message: "tools/call requires a string \"name\"")
        }
        // Only a tool this server advertises is proof that Claude reached *us*. An unknown name is
        // the model guessing, or another connector's tool arriving here by mistake, and must not
        // light up the tutorial's payoff beat.
        let isOurTool = Tools.all.contains { $0.name == name }
        // Fires on the failure path too: a `recall` that threw still proves Claude called us, and a
        // tool that only leaves a trace when it succeeds would make the beat depend on the answer
        // rather than on the connection.
        defer { if isOurTool { recordServedCall(name) } }
        do {
            let output = try Tools.call(name: name, arguments: request.params?["arguments"], store: store, openError: openError)
            return RPC.result(id: request.id, Self.content(output, isError: false))
        } catch {
            // MCP models a tool failure as a *result* so the model can read the reason and recover;
            // a JSON-RPC error would be swallowed by the client instead.
            Self.note("tool \(name) failed: \(error)")
            return RPC.result(id: request.id, Self.content(ToolOutput(text: Self.describe(error)), isError: true))
        }
    }

    /// Leaves the durable trace the app watches for, so the first-run tutorial's "found it" fires
    /// only when Claude has genuinely called one of our tools.
    ///
    /// **Only the tool name and the time are recorded, and that must stay true.** Never add the
    /// query, the arguments, or the result: this is a plaintext file whose entire purpose is a UI
    /// animation, and putting the user's questions — and so the private context behind them — on
    /// disk to earn an animation is the wrong trade. `QueryStamp` has no field for them, and
    /// `QueryStampRecordingTests.testTheStampNeverContainsTheQueryText` fails if that changes.
    ///
    /// A failure here is noted and dropped. The stamp is a nicety; the tool result is the contract,
    /// and an unwritable data directory must not turn an answered question into an error.
    ///
    /// The same call is also counted in `ToolCallLedger`, which the app drains into analytics. The
    /// two writes are deliberately separate files: the stamp is monotonic-latest and answers "did
    /// Claude just call us", the ledger is cumulative and answers "how much" — see `ToolCallLedger`.
    /// The ledger swallows its own failures for the reason stated above, so it cannot be the thing
    /// that turns an answered question into an error either.
    private func recordServedCall(_ tool: String) {
        do {
            try QueryStamp.record(tool: tool, to: queryStampURL)
        } catch {
            Self.note("could not record the query stamp: \(error)")
        }
        ToolCallLedger.bump(tool: tool, at: toolCallLedgerURL)
    }

    /// The `content` array for a tool result: the prose, then any pictures.
    ///
    /// **Text first, always.** An `image` block carries no timestamp and no caption — MCP has no
    /// field for either — so everything that keeps a screenshot from being misread (when it was
    /// taken, whether the screen has changed since, that a redacted frame's picture was withheld)
    /// lives in the text block and only works if the model meets it first.
    private static func content(_ output: ToolOutput, isError: Bool) -> JSONValue {
        var blocks: [JSONValue] = [["type": "text", "text": .string(output.text)]]
        for image in output.images {
            blocks.append([
                "type": "image",
                // Base64 with no `data:` prefix and no padding games: MCP's image block is the raw
                // encoding plus a separate mime type, and a data URI here is silently rejected.
                "data": .string(image.base64),
                "mimeType": .string(image.mimeType),
            ])
        }
        return [
            "content": .array(blocks),
            "isError": .bool(isError),
        ]
    }

    private static func describe(_ error: Error) -> String {
        if let localized = error as? LocalizedError, let description = localized.errorDescription {
            return description
        }
        // `localizedDescription` on a bare Swift error is the useless "operation couldn't be
        // completed" boilerplate; the case name is what the model can actually act on.
        return String(describing: error)
    }

    /// Diagnostics go to stderr only. Anything printed to stdout corrupts the protocol stream and
    /// Claude drops the connection.
    static func note(_ message: String) {
        guard let data = "context-for-claude: \(message)\n".data(using: .utf8) else { return }
        try? FileHandle.standardError.write(contentsOf: data)
    }
}
