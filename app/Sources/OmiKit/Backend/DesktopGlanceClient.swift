import Foundation

// Port of the desktop glance client (`DesktopHome.tsx` `useRemoteGlanceLine`):
// POST /v1/desktop/glance with light client context — frontmost app, window
// title, read counts, recent topics, local time — and the canonical worker
// composes one short kicker (optionally weather/headline enriched server
// side). Every failure — old backend, offline, malformed body — yields nil so
// the glance keeps rendering its local line.

/// One glance kicker: a ≤4-word title and a one-sentence copy.
public struct DesktopGlanceLine: Sendable, Equatable {
    public var title: String
    public var copy: String

    public init(title: String, copy: String) {
        self.title = title
        self.copy = copy
    }
}

/// The light context the worker tailors the line to. Mirrors the TS request
/// body: strings clamp to 120 chars, topics to six entries of 80 chars.
public struct DesktopGlanceContext: Sendable, Equatable {
    public var frontApp: String
    public var windowTitle: String
    public var conversations: Int
    public var memories: Int
    public var tasks: Int
    public var topics: [String]
    public var localTimeIso: String

    public init(
        frontApp: String, windowTitle: String,
        conversations: Int, memories: Int, tasks: Int,
        topics: [String], localTimeIso: String
    ) {
        self.frontApp = frontApp
        self.windowTitle = windowTitle
        self.conversations = conversations
        self.memories = memories
        self.tasks = tasks
        self.topics = topics
        self.localTimeIso = localTimeIso
    }
}

/// Fetches the composed glance line; nil on any failure (upstream swallows
/// every error — the local fallback line stays in place).
public func loadDesktopGlance(
    _ transport: BackendTransport, context: DesktopGlanceContext
) async -> DesktopGlanceLine? {
    // Upstream checks the API contract before calling; old planes have no
    // glance route and must not be probed.
    guard await transport.apiContract() == .canonical else { return nil }
    let body = JSON.serialize(
        JSONValue.object([
            ("frontApp", JSONValue.string(String(context.frontApp.prefix(120)))),
            ("windowTitle", JSONValue.string(String(context.windowTitle.prefix(120)))),
            (
                "counts", JSONValue.object([
                    ("conversations", JSONValue.number(Double(context.conversations))),
                    ("memories", JSONValue.number(Double(context.memories))),
                    ("tasks", JSONValue.number(Double(context.tasks))),
                ])
            ),
            (
                "topics", JSONValue.array(
                    context.topics.prefix(6).map { JSONValue.string(String($0.prefix(80))) }
                )
            ),
            ("localTimeIso", JSONValue.string(context.localTimeIso)),
        ])
    )
    guard
        let response = try? await transport.request(
            BackendRequest(
                id: "desktop-glance", expectedApiContract: .canonical, method: .POST,
                path: "/v1/desktop/glance", body: body
            )
        ),
        response.status == 200, let raw = response.body,
        let parsed = JSON.parseOrNull(raw), parsed.isRecord,
        let title = parsed["title"]?.stringValue, !title.isEmpty,
        let copy = parsed["copy"]?.stringValue, !copy.isEmpty
    else { return nil }
    return DesktopGlanceLine(title: title, copy: copy)
}
