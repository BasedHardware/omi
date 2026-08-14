import ContextCore
import Foundation

// MARK: - Key resolution

/// Where the Omi MCP API key came from.
///
/// `status` reports this **by name**. The key itself is never printed, logged, cached to disk, or
/// echoed back to the model — this process only ever reads it and puts it in an Authorization
/// header.
///
/// `appSupportFile` is the credential this product actually owns; the environment variable is a
/// development override only.
public enum OmiKeySource: Sendable {
    case environment
    case appSupportFile

    public var label: String {
        switch self {
        case .environment: return "the CONTEXT_OMI_MCP_KEY environment variable"
        case .appSupportFile: return "~/Library/Application Support/ContextForClaude/mcp-key"
        }
    }
}

/// Resolves the key in a fixed order, first hit wins.
///
/// `context-for-claude-mcp` is spawned per Claude session and lives for seconds, so OAuth is not an option:
/// there is nowhere to show a browser and nothing to persist a refresh token into. A pre-issued
/// read key is the only credential shape that fits the process.
///
/// **The key file is the one that is meant to answer.** The app provisions it: signed in with a real
/// Firebase ID token, `MCPKeyProvisioner` asks the backend for an `omi_mcp_…` key of this account's
/// own and writes it there. The environment variable is an override for development only; nothing else
/// on the machine is a legitimate credential source.
enum OmiKeyResolver {
    static let environmentVariable = "CONTEXT_OMI_MCP_KEY"

    /// `~/Library/Application Support/ContextForClaude/mcp-key` — the key the app provisions for
    /// itself, written 0600 by `MCPKeyProvisioner` once the user is signed in. On a healthy install
    /// this is where the credential comes from.
    static var keyFileURL: URL {
        ContextPaths.supportDirectory.appendingPathComponent("mcp-key")
    }

    /// True when running inside XCTest.
    ///
    /// Ambient credential discovery and a test suite are a bad combination: without this, running
    /// `swift test` silently picked up the developer's own key and every tool assertion started
    /// making live calls against a real person's Omi account — non-hermetic, rate-limited, and
    /// dependent on what happened to be in someone's history that day. Tests that want the backend
    /// must opt in explicitly by constructing `OmiBackend(credential:)` themselves.
    /// `XCTestConfigurationFilePath` is set by Xcode but **not** by `swift test`, which is how this
    /// leaked in the first place. Asking whether XCTest is loaded into the process works for both.
    private static let isRunningTests: Bool = {
        if NSClassFromString("XCTestCase") != nil { return true }
        let env = ProcessInfo.processInfo.environment
        return env["XCTestConfigurationFilePath"] != nil || env["XCTestBundlePath"] != nil
    }()

    static func resolve() -> (key: String, source: OmiKeySource)? {
        guard !isRunningTests else { return nil }
        if let key = fromEnvironment() { return (key, .environment) }
        // The expected source.
        if let key = fromKeyFile() { return (key, .appSupportFile) }
        return nil
    }

    /// What the key file looks like from the outside — modification time and size — so a rewrite can
    /// be noticed without opening it.
    ///
    /// The app rewrites this file out of band (a fresh sign-in, a key the backend rejected, a new
    /// mint) and tells nobody: this process is spawned per Claude session, and the session can
    /// outlive the credential it started with by hours. Asking one `stat` before every remote read is
    /// what makes the new key take effect on the next tool call rather than the next Claude restart,
    /// and it is cheap enough to do on that path — unlike re-reading and re-normalizing the contents,
    /// which would also reprint the permissions warning above on every call.
    ///
    /// nil when there is no file, which is itself a revision: "no key" → "a key" has to be noticed
    /// too, because the MCP server is routinely spawned before the user has signed in.
    static func keyFileRevision() -> String? {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: keyFileURL.path) else { return nil }
        let modified = (attributes[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
        let size = (attributes[.size] as? NSNumber)?.intValue ?? 0
        return "\(modified)/\(size)"
    }

    // MARK: Sources

    private static func fromEnvironment() -> String? {
        normalize(ProcessInfo.processInfo.environment[environmentVariable])
    }

    /// The app's own credential: the whole file is the key, trimmed. No JSON, no envelope — the
    /// writer and this reader are the two halves of one contract, and the simplest possible format
    /// is what keeps them from drifting apart across two targets.
    private static func fromKeyFile() -> String? {
        let url = keyFileURL
        guard let data = try? Data(contentsOf: url), let text = String(data: data, encoding: .utf8) else {
            return nil
        }
        // Read it either way — refusing a readable key would only make Context for Claude look broken — but say
        // so once on stderr, because a shared secret at 0644 is worth noticing.
        if let mode = (try? FileManager.default.attributesOfItem(atPath: url.path))?[.posixPermissions] as? NSNumber,
           mode.int16Value & 0o077 != 0 {
            MCPServer.note("omi: key file is group/other-readable; it should be chmod 600")
        }
        return normalize(text)
    }

    // MARK: Normalization

    private static func normalize(_ raw: String?) -> String? {
        guard var value = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        if value.lowercased().hasPrefix("bearer ") {
            value = String(value.dropFirst("bearer ".count)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // Quotes survive a copy-paste out of a shell or a JSON blob more often than not.
        value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
        return value.isEmpty ? nil : value
    }
}

/// Where the credential comes from, as a *source* rather than a value.
///
/// The distinction is the whole of this file's account-recovery behaviour: a value read once at
/// construction is a value that cannot be repaired, and this client is built once per process into
/// `OmiBackend.shared`. Everything that reads the credential goes through here, so a rewritten key
/// file and a rejected key have exactly one place to be noticed.
struct OmiCredentialSource: Sendable {
    /// The credential as it is right now. Called only when `revision` says the file moved, or after a
    /// rejection — never on a hot path.
    let read: @Sendable () -> (key: String, source: OmiKeySource)?
    /// A cheap value that changes whenever the key file does. Asked before every read.
    let revision: @Sendable () -> String?

    static let live = OmiCredentialSource(
        read: { OmiKeyResolver.resolve() },
        revision: { OmiKeyResolver.keyFileRevision() })

    /// A credential that cannot change — the shape the tests that are about something else want, and
    /// the shape the environment-variable override actually has.
    static func fixed(_ credential: (key: String, source: OmiKeySource)?) -> OmiCredentialSource {
        OmiCredentialSource(read: { credential }, revision: { nil })
    }
}

// MARK: - Failure

/// Every way a read can fail. Each case carries a clause that reads inside
/// "Omi history could not be reached: <reason>." — the model is told what broke, never nothing.
public enum OmiBackendError: Error, Sendable, Equatable {
    case notConfigured
    /// The user turned Airgap Mode on, so no request was sent. Not a failure of the account or of
    /// the network — a refusal by this process, and the one failure the user can undo in a click.
    case airgapped
    case unauthorized
    case forbidden
    case notFound
    case rateLimited
    case timedOut
    case offline(String)
    case httpStatus(Int)
    case malformedResponse(String)

    public var reason: String {
        switch self {
        case .notConfigured:
            return """
            no Omi MCP API key is configured, so this process has no way to authenticate to the \
            account
            """
        case .airgapped:
            // Every tool that renders a backend failure — the footers, the "nothing found" prose,
            // `status`, `transcript` — gets the airgap explanation for free by carrying it here,
            // rather than each of them growing its own branch that could drift or be forgotten.
            return MCPNetworkEgress.suppressedReadClause
        case .unauthorized:
            return "the Omi MCP API key was rejected (HTTP 401) — it has expired or been revoked"
        case .forbidden:
            return "the Omi MCP API key does not carry the required access for this operation (HTTP 403)"
        case .notFound:
            return "the Omi account holds no such record (HTTP 404)"
        case .rateLimited:
            return "the account hit Omi's MCP rate limit (HTTP 429) — it will recover on its own within the hour"
        case .timedOut:
            return "the request timed out after \(Int(OmiBackend.requestTimeout)) s"
        case let .offline(detail):
            return "this Mac could not reach api.omi.me (\(detail))"
        case let .httpStatus(code):
            return "Omi answered HTTP \(code)"
        case let .malformedResponse(detail):
            return "Omi's answer could not be read (\(detail))"
        }
    }

    /// True when retrying with the same credential is pointless, so the failure is cached for the
    /// life of *that credential* instead of burning the hourly budget on a call that cannot succeed.
    ///
    /// Not for the life of the process, which is what it used to mean and what made a 401 permanent:
    /// the app re-provisions the key file underneath a running session, so "this key is rejected" and
    /// "this account is unreachable" are different claims. `ResponseCache` scopes these entries to the
    /// credential that produced them for exactly that reason.
    var isTerminal: Bool {
        switch self {
        // 404 included: an id the account does not hold will not start existing mid-session.
        case .notConfigured, .unauthorized, .forbidden, .notFound: return true
        default: return false
        }
    }
}

/// A read that is allowed to fail. Making the failure part of the *type* is what guarantees the
/// contract "a backend outage never breaks a tool": there is no `throws` for a caller to forget.
public enum OmiResult<Value: Sendable>: Sendable {
    case ok(Value)
    case unavailable(OmiBackendError)

    public var value: Value? {
        if case let .ok(value) = self { return value }
        return nil
    }

    public var failure: OmiBackendError? {
        if case let .unavailable(error) = self { return error }
        return nil
    }
}

// MARK: - Wire shapes
//
// Only the fields Context for Claude renders. Everything is optional and every decode is defensive: one
// malformed record out of five thousand must not blank the whole answer.

public struct OmiConversation: Sendable {
    public let id: String
    /// Unix epoch seconds, when Omi recorded one.
    public let startedAt: Double?
    public let finishedAt: Double?
    public let title: String
    public let overview: String
    public let category: String?
    public let language: String?
    /// Whatever Omi's own apps wrote about the conversation (summaries, action items).
    public let appNotes: [String]

    public var durationSeconds: Double? {
        guard let startedAt, let finishedAt, finishedAt > startedAt else { return nil }
        return finishedAt - startedAt
    }
}

extension OmiConversation: Decodable {
    private enum Key: String, CodingKey {
        case id, structured, language
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case appsResults = "apps_results"
    }

    private enum StructuredKey: String, CodingKey { case title, overview, category }

    private struct AppNote: Decodable { let content: String? }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: Key.self)
        id = container.optionalString(.id) ?? ""
        startedAt = OmiDate.parse(container.optionalString(.startedAt))
        finishedAt = OmiDate.parse(container.optionalString(.finishedAt))
        language = container.optionalString(.language)

        let structured = try? container.nestedContainer(keyedBy: StructuredKey.self, forKey: .structured)
        title = (structured?.optionalString(.title) ?? nil) ?? "Untitled conversation"
        overview = (structured?.optionalString(.overview) ?? nil) ?? ""
        category = structured?.optionalString(.category) ?? nil

        appNotes = container.optionalArray(AppNote.self, .appsResults).compactMap { note in
            guard let content = note.content?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !content.isEmpty else { return nil }
            return content
        }
    }
}

public struct OmiTranscriptSegment: Decodable, Sendable {
    public let text: String
    /// Omi resolves speakers against the account's people, so this is a real name when it knows one.
    public let speakerName: String?
    public let speakerID: Int?
    /// Seconds from the start of the conversation.
    public let start: Double
    public let end: Double

    private enum Key: String, CodingKey {
        case text, start, end
        case speakerName = "speaker_name"
        case speakerID = "speaker_id"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: Key.self)
        text = container.optionalString(.text) ?? ""
        speakerName = container.optionalString(.speakerName)
        speakerID = container.optionalInt(.speakerID)
        start = container.optionalDouble(.start) ?? 0
        end = container.optionalDouble(.end) ?? 0
    }
}

public struct OmiFullConversation: Decodable, Sendable {
    public let conversation: OmiConversation
    public let segments: [OmiTranscriptSegment]

    private enum Key: String, CodingKey { case transcriptSegments = "transcript_segments" }

    public init(from decoder: Decoder) throws {
        conversation = try OmiConversation(from: decoder)
        let container = try decoder.container(keyedBy: Key.self)
        segments = container.optionalArray(OmiTranscriptSegment.self, .transcriptSegments)
    }
}

/// A durable fact Omi has learned about the user. The MCP surface returns these **without a
/// timestamp**, which is why they are rendered as an undated section rather than interleaved into
/// the timeline — dating them would be a fabrication.
public struct OmiMemory: Decodable, Sendable {
    public let id: String
    public let content: String
    public let category: String?
    public let relevance: Double?

    private enum Key: String, CodingKey {
        case id, content, category
        case relevance = "relevance_score"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: Key.self)
        id = container.optionalString(.id) ?? ""
        content = container.optionalString(.content) ?? ""
        category = container.optionalString(.category)
        relevance = container.optionalDouble(.relevance)
    }

    public init(id: String, content: String, category: String?, relevance: Double? = nil) {
        self.id = id
        self.content = content
        self.category = category
        self.relevance = relevance
    }
}

public struct OmiScreenRow: Decodable, Sendable {
    public let id: String?
    public let at: Double?
    public let app: String?
    public let window: String?
    public let ocr: String?

    private enum Key: String, CodingKey {
        case id, timestamp
        case app = "app_name"
        case window = "window_title"
        case ocr = "ocr_text"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: Key.self)
        id = container.optionalString(.id)
        at = OmiDate.parse(container.optionalString(.timestamp))
        app = container.optionalString(.app)
        window = container.optionalString(.window)
        ocr = container.optionalString(.ocr)
    }
}

/// Everything `recall` needs from the account, fetched in one round trip. Failures are values here
/// too: a memory outage and a conversation outage are reported separately because they mean
/// different things to the reader.
public struct OmiRecallResults: Sendable {
    public let memories: [OmiMemory]
    public let conversations: [OmiConversation]
    /// One clause per failed half, ready to drop into a footer sentence.
    public let failures: [String]

    public var isEmpty: Bool { memories.isEmpty && conversations.isEmpty }
}

/// How far back the account reaches, established with at most two calls.
public struct OmiHistoryProbe: Sendable {
    public let newest: OmiConversation?
    /// The offset that was probed, counting back from the newest conversation.
    public let probeOffset: Int
    /// The conversation at `probeOffset`, or nil when the account holds fewer than that many.
    public let atProbeOffset: OmiConversation?
}

// MARK: - Client

/// Client for `https://api.omi.me/v1/mcp/*`.
///
/// Synchronous on purpose: `Tools.call` is synchronous and the process exists only to answer one
/// question at a time, so an async ladder would buy nothing and cost a bridge at every call site.
/// Every public method returns a value — nothing here throws into a tool. Memory mutations use the
/// same provisioned MCP key as reads; the backend's persisted `memories.write` grant is the
/// authorization boundary, not a second credential or a local shadow database.
public final class OmiBackend: @unchecked Sendable {
    public static let shared = OmiBackend()

    public static let baseURL = URL(string: "https://api.omi.me/")!

    /// Claude is blocked on this call, so the ceiling is what a person will sit through, not what
    /// the network might eventually manage.
    public static let requestTimeout: TimeInterval = 10

    /// Deep enough to prove real history, cheap enough to be one row. `status` reports a *lower
    /// bound* from it: the exact floor would need a binary search, and the read budget is 300
    /// requests an hour.
    public static let historyProbeOffset = 500

    /// The name this client answers to in the app's audited egress list.
    ///
    /// `ContextApp` cannot link this target — it is a library the *other* executable is built from —
    /// so `NetworkEgress.Client.mcpOmiBackend` carries this string as its raw value rather than
    /// importing it. That is what makes the record this process emits and the record the app would
    /// emit for it the same line, and it is checked from both sides: `AirgapTests` here, and
    /// `AirgapEgressTests` there.
    public static let egressClientName = "omi-backend"

    private let credentials: CredentialReader
    private let cache = ResponseCache()
    private let seen = SeenRange()
    /// Reads Airgap Mode. A closure rather than a stored `Bool` because the answer has to be taken
    /// afresh at each attempt — see the gate in `get` — and injectable so a test can drive both
    /// answers, and count the reads, without a network or a configuration file.
    private let isAirgapped: @Sendable () -> Bool
    /// The one function in this target that opens a socket.
    ///
    /// Injectable for the same reason `ScreenActivityUploader` takes a `transport` on the app side:
    /// it is the difference between a test that *infers* no request was issued from the error it got
    /// back, and one that fails on contact. Without it, a green airgap test and a test that quietly
    /// reached `api.omi.me` and came back `.unauthorized` are told apart only by reading the error
    /// — and the account behind that host is rate-limited, so "the suite proves the guard by
    /// exercising it" is not a trade this file may make.
    private let transport: @Sendable (URLRequest) -> Result<Data, OmiBackendError>

    /// Deliberately not public: the credential never leaves this module, and no caller outside it
    /// can hand one in or read one back out.
    init(
        credential: OmiCredentialSource = .live,
        isAirgapped: @escaping @Sendable () -> Bool = { MCPNetworkEgress.isAirgapped() },
        transport: (@Sendable (URLRequest) -> Result<Data, OmiBackendError>)? = nil
    ) {
        self.credentials = CredentialReader(credential)
        self.isAirgapped = isAirgapped
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = Self.requestTimeout
        configuration.timeoutIntervalForResource = Self.requestTimeout
        // Offline must fail now and let the tool fall back to local data, not queue for later.
        configuration.waitsForConnectivity = false
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.httpShouldSetCookies = false
        let session = URLSession(configuration: configuration)
        self.transport = transport ?? { request in Self.perform(request, on: session) }
    }

    /// A credential that cannot change, for callers that are testing something else.
    convenience init(
        credential: (key: String, source: OmiKeySource)?,
        isAirgapped: @escaping @Sendable () -> Bool = { MCPNetworkEgress.isAirgapped() },
        transport: (@Sendable (URLRequest) -> Result<Data, OmiBackendError>)? = nil
    ) {
        self.init(credential: .fixed(credential), isAirgapped: isAirgapped, transport: transport)
    }

    /// Both of these re-read the key on demand rather than answering from a snapshot taken at
    /// construction. `status` renders straight off them, and it is the tool a reader is sent to when
    /// something looks wrong — reporting a credential the process has already stopped using is the
    /// one thing it may never do.
    public var isConfigured: Bool { credentials.current() != nil }

    /// The *name* of the source, never the key.
    public var keySourceLabel: String? { credentials.current()?.source.label }

    /// Oldest / newest conversation start this process has seen from Omi, across every call made so
    /// far. Cheap extra evidence for `status` that costs no request.
    public var seenRange: (oldest: Double, newest: Double)? { seen.range }

    /// The sentence every tool uses when there is no key at all, so the wording never drifts.
    ///
    /// It names the one action that fixes it. The app provisions its own key the first time it is
    /// signed in, so "no key" almost always means "signed out", not "misconfigured" — and telling
    /// the reader to go hunting through environment variables would send them the wrong way.
    public static let notConfiguredSentence = """
    Omi account history is unavailable: no Omi MCP API key is configured. Context for Claude provisions \
    one for itself at ~/Library/Application Support/ContextForClaude/mcp-key once you are signed in, and \
    nothing is there yet — open Context for Claude in the menu bar and sign in to your Omi account. Only \
    what Context for Claude captured locally on this Mac was searched.
    """

    // MARK: Reads

    /// Search memories and conversations at once. Two calls, issued in parallel, because `recall`
    /// genuinely needs both: memories are the durable facts, conversations are the episodes.
    ///
    /// Local memories from the main Omi app's `omi.db` are always included — even when the API key
    /// is not configured — so memories that have not synced yet are still searchable.
    public func recall(query: String, since: Double?, until: Double?, limit: Int) -> OmiRecallResults {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return OmiRecallResults(memories: [], conversations: [], failures: []) }

        let memoryBox = Box<OmiResult<[OmiMemory]>>(.unavailable(.timedOut))
        let conversationBox = Box<OmiResult<[OmiConversation]>>(.unavailable(.timedOut))

        let group = DispatchGroup()
        let queue = DispatchQueue.global(qos: .userInitiated)
        queue.async(group: group) { memoryBox.value = self.searchMemories(query: trimmed, limit: limit) }
        queue.async(group: group) {
            guard self.isConfigured else {
                conversationBox.value = .unavailable(.notConfigured)
                return
            }
            conversationBox.value = self.searchConversations(query: trimmed, since: since, until: until, limit: limit)
        }
        // The URLSession timeout is the real bound; this only stops a hung callback from stranding
        // the process forever.
        _ = group.wait(timeout: .now() + Self.requestTimeout + 5)

        var failures: [String] = []
        if let error = memoryBox.value.failure { failures.append("memories: \(error.reason)") }
        if let error = conversationBox.value.failure { failures.append("conversations: \(error.reason)") }
        return OmiRecallResults(
            memories: memoryBox.value.value ?? [],
            conversations: conversationBox.value.value ?? [],
            failures: failures
        )
    }

    public func searchMemories(query: String, limit: Int) -> OmiResult<[OmiMemory]> {
        let clamped = clamp(limit, 1, 50)
        // Local memories from the main Omi app's omi.db — always available when the app has run,
        // even without an API key. These include memories that have not synced to the backend yet.
        let local = OmiMemoryStore.shared.searchMemories(query: query, limit: clamped)
        let localMemories = local.map {
            OmiMemory(id: $0.id, content: $0.content, category: $0.category)
        }

        guard isConfigured else {
            return localMemories.isEmpty
                ? .unavailable(.notConfigured)
                : .ok(localMemories)
        }

        // Merge local with API results, deduplicating by id.
        let apiResult = get(
            [OmiMemory].self,
            path: "v1/mcp/memories/search",
            // The endpoint clamps to 20 anyway; asking for more only wastes the budget.
            query: [.init(name: "query", value: query), .init(name: "limit", value: String(clamp(clamped, 1, 20)))],
            ttl: 600
        )

        switch apiResult {
        case let .ok(apiMemories):
            let seen = Set(localMemories.map(\.id))
            let merged = (localMemories + apiMemories.filter { !seen.contains($0.id) }).prefix(clamped)
            return .ok(Array(merged))
        case let .unavailable(error):
            return localMemories.isEmpty ? .unavailable(error) : .ok(localMemories)
        }
    }

    /// Lists durable Omi memories without the semantic search used by `recall`.
    public func getMemories(
        limit: Int,
        offset: Int = 0,
        categories: [String] = [],
        sort: String = "created_desc"
    ) -> OmiResult<[OmiMemory]> {
        var items: [URLQueryItem] = [
            .init(name: "limit", value: String(clamp(limit, 1, 500))),
            .init(name: "offset", value: String(max(0, offset))),
            .init(name: "sort", value: sort),
        ]
        let categoryValue = categories
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: ",")
        if !categoryValue.isEmpty { items.append(.init(name: "categories", value: categoryValue)) }

        return get([OmiMemory].self, path: "v1/mcp/memories", query: items, ttl: 30)
    }

    /// Creates a durable Omi memory. The server assigns the category when one is not supplied.
    public func createMemory(content: String, category: String? = nil) -> OmiResult<OmiMemory> {
        let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return .unavailable(.malformedResponse("memory content must not be empty"))
        }
        let request = CreateMemoryRequest(content: trimmed, category: category?.nonEmpty)
        guard let body = try? JSONEncoder().encode(request) else {
            return .unavailable(.malformedResponse("could not encode memory content"))
        }
        let result = write(
            OmiMemory.self,
            method: "POST",
            path: "v1/mcp/memories",
            body: body)
        if case .ok = result { cache.remove(matching: "/v1/mcp/memories") }
        return result
    }

    /// Changes only the content of an existing durable Omi memory.
    public func editMemory(id: String, content: String) -> OmiResult<Bool> {
        guard let path = memoryPath(id), let value = content.nonEmpty else {
            return .unavailable(.malformedResponse("memory id and content must not be empty"))
        }
        let result = write(
            OmiMutationResponse.self,
            method: "PATCH",
            path: path,
            query: [.init(name: "value", value: value)])
        let mapped = map(result) { _ in true }
        if case .ok = mapped { cache.remove(matching: "/v1/mcp/memories") }
        return mapped
    }

    /// Deletes an existing durable Omi memory.
    public func deleteMemory(id: String) -> OmiResult<Bool> {
        guard let path = memoryPath(id) else {
            return .unavailable(.malformedResponse("memory id must not be empty"))
        }
        let result = write(OmiMutationResponse.self, method: "DELETE", path: path)
        let mapped = map(result) { _ in true }
        if case .ok = mapped { cache.remove(matching: "/v1/mcp/memories") }
        return mapped
    }

    /// Vector search over the account's conversations.
    ///
    /// This endpoint takes plain `YYYY-MM-DD` dates and reads them in the server's own calendar, so
    /// the window is sent a day wide on each side and narrowed back to the caller's exact epochs
    /// here. A timezone off-by-one must not silently hide the day the user asked about.
    public func searchConversations(
        query: String,
        since: Double?,
        until: Double?,
        limit: Int
    ) -> OmiResult<[OmiConversation]> {
        var items: [URLQueryItem] = [
            .init(name: "query", value: query),
            .init(name: "limit", value: String(clamp(limit, 1, 50))),
        ]
        if let since { items.append(.init(name: "start_date", value: OmiDate.day(since - 86_400))) }
        if let until { items.append(.init(name: "end_date", value: OmiDate.day(until + 86_400))) }

        let result = get([OmiConversation].self, path: "v1/mcp/conversations/search", query: items, ttl: 600)
        return map(result) { self.record($0).filter { conversation in
            within(conversation.startedAt, since: since, until: until)
        } }
    }

    /// Conversation headers, newest first.
    public func conversations(
        since: Double?,
        until: Double?,
        limit: Int,
        offset: Int = 0
    ) -> OmiResult<[OmiConversation]> {
        var items: [URLQueryItem] = [
            .init(name: "limit", value: String(clamp(limit, 1, 1000))),
            .init(name: "offset", value: String(max(0, offset))),
        ]
        if let since { items.append(.init(name: "start_date", value: OmiDate.iso(since))) }
        if let until { items.append(.init(name: "end_date", value: OmiDate.iso(until))) }

        let result = get([OmiConversation].self, path: "v1/mcp/conversations", query: items, ttl: 300)
        return map(result) { self.record($0) }
    }

    /// One conversation in full, with Omi's speaker-resolved transcript.
    public func conversation(id: String) -> OmiResult<OmiFullConversation> {
        let trimmed = id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return .unavailable(.malformedResponse("empty conversation id")) }
        // Stricter than `.urlPathAllowed`, which would let a "/" in an id walk off the endpoint.
        let unreserved = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        let escaped = trimmed.addingPercentEncoding(withAllowedCharacters: unreserved) ?? trimmed
        // A finished conversation does not change, so hold it for the life of the process.
        let result = get(OmiFullConversation.self, path: "v1/mcp/conversations/\(escaped)", query: [], ttl: 3600)
        return map(result) { full in
            self.record([full.conversation])
            return full
        }
    }

    public func screenActivity(
        since: Double?,
        until: Double?,
        app: String?,
        limit: Int
    ) -> OmiResult<[OmiScreenRow]> {
        var items: [URLQueryItem] = [
            .init(name: "limit", value: String(clamp(limit, 1, 200))),
            .init(name: "summary", value: "false"),
        ]
        if let since { items.append(.init(name: "start_date", value: OmiDate.iso(since))) }
        if let until { items.append(.init(name: "end_date", value: OmiDate.iso(until))) }
        if let app = app?.trimmingCharacters(in: .whitespacesAndNewlines), !app.isEmpty {
            items.append(.init(name: "app", value: app))
        }
        return get([OmiScreenRow].self, path: "v1/mcp/screen-activity", query: items, ttl: 300)
    }

    /// Reachability plus a lower bound on how far back the account goes.
    ///
    /// Two calls, and this is the one tool that genuinely needs two: one row proves the key works
    /// and dates the newest record, one row `historyProbeOffset` deep proves the history is real.
    /// Pulling the whole list instead would be a megabyte and well over the timeout.
    public func history() -> OmiResult<OmiHistoryProbe> {
        guard isConfigured else { return .unavailable(.notConfigured) }
        let newest = conversations(since: nil, until: nil, limit: 1)
        if let error = newest.failure { return .unavailable(error) }
        let newestConversation = newest.value?.first

        let deep = conversations(since: nil, until: nil, limit: 1, offset: Self.historyProbeOffset)
        return .ok(
            OmiHistoryProbe(
                newest: newestConversation,
                probeOffset: Self.historyProbeOffset,
                // A failed probe is not a failed status: the newest row already proved reachability.
                atProbeOffset: deep.value?.first
            )
        )
    }

    // MARK: Transport

    private func get<T: Decodable & Sendable>(
        _ type: T.Type,
        path: String,
        query: [URLQueryItem],
        ttl: TimeInterval
    ) -> OmiResult<T> {
        // Asked *before* the cache, because this read is what notices the app having rewritten the
        // key file: a rejection cached against the superseded key must never get to answer first.
        // That ordering is the whole fix — a process that latched a 401 at breakfast was still
        // reporting the account unreachable at lunchtime, over a key file that had been replaced
        // with a working one in between and a `curl` with those exact bytes returning 200.
        guard let credential = credentials.current() else { return .unavailable(.notConfigured) }
        guard var components = URLComponents(url: Self.baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        else { return .unavailable(.malformedResponse("could not build a URL for \(path)")) }
        components.queryItems = query.isEmpty ? nil : query
        guard let url = components.url else {
            return .unavailable(.malformedResponse("could not build a URL for \(path)"))
        }

        let cacheKey = url.absoluteString
        if let cached = cache.lookup(cacheKey, generation: credential.generation) {
            switch cached {
            case let .success(data): return decode(type, data, path: path, method: "GET")
            case let .failure(error): return .unavailable(error)
            }
        }

        // Airgap Mode, asked *here*: after the cache, immediately before the only path in this
        // process that opens a socket. Every remote read in this target funnels through this
        // function, so this one line is the whole enforcement surface.
        //
        // Here rather than at construction because this binary is spawned per Claude session and
        // outlives the click: the switch can go on while Claude is still open, and a value read at
        // startup would keep this process talking to `api.omi.me` for the rest of the session.
        //
        // After the cache lookup because serving a response already fetched costs no network, and
        // refusing it would degrade the answer for no privacy gained.
        //
        // **The refusal is deliberately never stored in the cache.** The flag is live in both
        // directions: a cached refusal would keep answering "airgapped" after the user turned the
        // switch back off, for as long as its TTL — and the terminal-failure branch below would pin
        // it for the life of the process. Returning before either is what makes the switch reversible.
        if isAirgapped() {
            MCPNetworkEgress.recordSuppression()
            return .unavailable(.airgapped)
        }

        let (result, used) = authorized(credential, path: path, method: "GET") { key in
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.timeoutInterval = Self.requestTimeout
            request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue("context-for-claude-mcp/1.0", forHTTPHeaderField: "User-Agent")
            return request
        }

        switch result {
        case let .success(data):
            cache.store(cacheKey, .success(data), ttl: ttl, generation: used.generation)
            return decode(type, data, path: path, method: "GET")
        case let .failure(error):
            // Terminal failures are held for the life of the credential that earned them; a
            // transient one is held only briefly, so a flaky network recovers within the session
            // without hammering the budget. Stored against the credential actually used, which is
            // the retried one when there was a retry.
            cache.store(
                cacheKey, .failure(error),
                ttl: error.isTerminal ? .greatestFiniteMagnitude : 60,
                generation: used.generation)
            return .unavailable(error)
        }
    }

    private func write<T: Decodable & Sendable>(
        _ type: T.Type,
        method: String,
        path: String,
        query: [URLQueryItem] = [],
        body: Data? = nil
    ) -> OmiResult<T> {
        guard let credential = credentials.current() else { return .unavailable(.notConfigured) }
        guard var components = URLComponents(url: Self.baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        else { return .unavailable(.malformedResponse("could not build a URL for \(path)")) }
        components.queryItems = query.isEmpty ? nil : query
        guard let url = components.url else {
            return .unavailable(.malformedResponse("could not build a URL for \(path)"))
        }
        guard !isAirgapped() else {
            MCPNetworkEgress.recordSuppression()
            return .unavailable(.airgapped)
        }

        let (result, _) = authorized(credential, path: path, method: method) { key in
            var request = URLRequest(url: url)
            request.httpMethod = method
            request.timeoutInterval = Self.requestTimeout
            request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("context-for-claude-mcp/1.0", forHTTPHeaderField: "User-Agent")
            request.httpBody = body
            return request
        }

        switch result {
        case let .success(data): return decode(type, data, path: path, method: method)
        case let .failure(error): return .unavailable(error)
        }
    }

    /// Sends a request carrying the credential, and answers a 401 by re-reading the key file once.
    ///
    /// **One re-read and one retry per call, and that is the ceiling.** The key on disk is rewritten
    /// by the app, not by this process, so a rejection is worth exactly one look at what is there
    /// now: if the file has changed the new key is tried immediately, and if it has not — or if the
    /// replacement is rejected too — that is the account's answer and this stops asking. Anything
    /// looser turns a revoked key into a request storm against a rate limit of 300 an hour, and the
    /// second 401 tells the caller nothing the first one did not.
    ///
    /// It answers with the credential the reported result actually belongs to, because that is what
    /// the caller must cache the result against.
    private func authorized(
        _ credential: CredentialReader.Value,
        path: String,
        method: String,
        _ build: (String) -> URLRequest
    ) -> (result: Result<Data, OmiBackendError>, credential: CredentialReader.Value) {
        let first = send(build(credential.key), path: path, method: method)
        guard case .failure(.unauthorized) = first else { return (first, credential) }

        credentials.invalidate()
        // An unchanged key means there is nothing new to try: the file has not moved since this call
        // started, so re-sending it would only spend the budget to be told the same thing.
        guard let replacement = credentials.current(), replacement.key != credential.key else {
            return (first, credential)
        }
        MCPServer.note("omi: the key was rejected; a newer one is in \(replacement.source.label) — retrying once")
        return (send(build(replacement.key), path: path, method: method), replacement)
    }

    /// Runs `request` through whatever transport this instance was built with, and names the failure
    /// in the log. Method and path only — never the query, which carries the user's own words.
    private func send(_ request: URLRequest, path: String, method: String) -> Result<Data, OmiBackendError> {
        let result = transport(request)
        if case let .failure(error) = result {
            MCPServer.note("omi: \(method) /\(path) failed — \(error.reason)")
        }
        return result
    }

    private static func perform(
        _ request: URLRequest, on session: URLSession
    ) -> Result<Data, OmiBackendError> {
        let box = Box<Result<Data, OmiBackendError>>(.failure(.timedOut))
        let semaphore = DispatchSemaphore(value: 0)

        let task = session.dataTask(with: request) { data, response, error in
            defer { semaphore.signal() }
            if let error {
                // Read it as an NSError rather than casting to URLError: a few transport failures
                // (a sandboxed process, some VPN clients) arrive as a plain NSError in the URL
                // domain and would otherwise degrade to a reason that tells the reader nothing.
                let ns = error as NSError
                guard ns.domain == NSURLErrorDomain else {
                    box.value = .failure(.offline("\(ns.domain) \(ns.code)"))
                    return
                }
                let code = URLError.Code(rawValue: ns.code)
                box.value = .failure(code == .timedOut ? .timedOut : .offline(code.humanReason))
                return
            }
            guard let http = response as? HTTPURLResponse else {
                box.value = .failure(.malformedResponse("no HTTP response"))
                return
            }
            switch http.statusCode {
            case 200...299:
                box.value = .success(data ?? Data())
            case 401:
                box.value = .failure(.unauthorized)
            case 402, 403:
                box.value = .failure(.forbidden)
            case 404:
                box.value = .failure(.notFound)
            case 429:
                box.value = .failure(.rateLimited)
            default:
                box.value = .failure(.httpStatus(http.statusCode))
            }
        }
        task.resume()

        // Belt and braces over URLSession's own timeout: a wedged callback must never hold the MCP
        // read loop, because Claude is waiting on stdout.
        if semaphore.wait(timeout: .now() + requestTimeout + 2) == .timedOut {
            task.cancel()
            return .failure(.timedOut)
        }
        return box.value
    }

    private func decode<T: Decodable & Sendable>(
        _ type: T.Type,
        _ data: Data,
        path: String,
        method: String
    ) -> OmiResult<T> {
        do {
            return .ok(try JSONDecoder().decode(type, from: data))
        } catch {
            MCPServer.note("omi: \(method) /\(path) decode failed")
            return .unavailable(.malformedResponse("unexpected response shape"))
        }
    }

    // MARK: Helpers

    private func map<A: Sendable, B: Sendable>(_ result: OmiResult<A>, _ transform: (A) -> B) -> OmiResult<B> {
        switch result {
        case let .ok(value): return .ok(transform(value))
        case let .unavailable(error): return .unavailable(error)
        }
    }

    @discardableResult
    private func record(_ conversations: [OmiConversation]) -> [OmiConversation] {
        seen.observe(conversations.compactMap(\.startedAt))
        return conversations
    }

    private func within(_ at: Double?, since: Double?, until: Double?) -> Bool {
        // An undated record is kept: dropping it would hide real history over missing metadata.
        guard let at else { return true }
        if let since, at < since { return false }
        if let until, at > until { return false }
        return true
    }

    private func memoryPath(_ id: String) -> String? {
        let trimmed = id.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let unreserved = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._~"))
        guard let escaped = trimmed.addingPercentEncoding(withAllowedCharacters: unreserved), !escaped.isEmpty else {
            return nil
        }
        return "v1/mcp/memories/\(escaped)"
    }

    private func clamp(_ value: Int, _ lower: Int, _ upper: Int) -> Int { min(max(value, lower), upper) }
}

private struct CreateMemoryRequest: Encodable {
    let content: String
    let category: String?
}

private struct OmiMutationResponse: Decodable, Sendable {
    let status: String?
}

private extension String {
    var nonEmpty: String? {
        let value = trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}

// MARK: - Process-local state

/// The credential as it is *now*, re-read rather than remembered.
///
/// **This process outlives its own credential.** `context-for-claude-mcp` is spawned per Claude
/// session, and a session runs for as long as someone leaves Claude open; the app rewrites
/// `~/Library/Application Support/ContextForClaude/mcp-key` whenever it re-provisions and has no way
/// to tell this process it did. Reading the file once at construction therefore meant a key replaced
/// mid-session was never picked up, and every account-backed tool spent the rest of the day telling
/// Claude the history was unreachable while the file on disk answered 200 — the worst failure this
/// product has, because Claude then states with confidence that the user has no history.
///
/// Lazily, on demand, and with no timer: the revision is a `stat`, taken on the same call that was
/// going to open a socket anyway. `invalidate()` is the other trigger — a rejection is the strongest
/// possible hint that the key on disk has moved on.
private final class CredentialReader: @unchecked Sendable {
    /// A credential and the generation it belongs to. The generation moves only when the key itself
    /// changes, so it is safe to hold results against: a file merely touched must not throw away
    /// cached failures that are still true of the same key.
    struct Value: Sendable {
        let key: String
        let source: OmiKeySource
        let generation: Int
    }

    private let lock = NSLock()
    private let source: OmiCredentialSource
    private var cached: Value?
    private var lastRevision: String?
    private var hasRead = false
    private var generation = 0

    init(_ source: OmiCredentialSource) { self.source = source }

    func current() -> Value? {
        lock.lock()
        defer { lock.unlock() }
        let revision = source.revision()
        if hasRead, revision == lastRevision { return cached }

        let read = source.read()
        if read?.key != cached?.key { generation += 1 }
        cached = read.map { Value(key: $0.key, source: $0.source, generation: generation) }
        hasRead = true
        lastRevision = revision
        return cached
    }

    /// Makes the next `current()` go back to disk regardless of what the revision says. Called on a
    /// 401 and nowhere else.
    func invalidate() {
        lock.lock()
        hasRead = false
        lock.unlock()
    }
}

/// In-process response cache. The rate limit is 300 reads an hour and Claude re-asks the same
/// question constantly inside one session, so repeating a call is a bug, not a cost.
private final class ResponseCache: @unchecked Sendable {
    private struct Entry {
        let expiresAt: Double
        let generation: Int
        let result: Result<Data, OmiBackendError>
    }

    private let lock = NSLock()
    private var entries: [String: Entry] = [:]

    func lookup(_ key: String, generation: Int) -> Result<Data, OmiBackendError>? {
        lock.lock()
        defer { lock.unlock() }
        guard let entry = entries[key] else { return nil }
        // **A failure belongs to the credential that earned it.** `.unauthorized` is cached forever
        // so a revoked key cannot burn the hourly budget, and that is right — but "forever" has to
        // end when the key does, or a re-provisioned Mac keeps being told its own account is
        // unreachable. A success is kept either way: it is the account's data, and the account did
        // not change when its key did.
        if case .failure = entry.result, entry.generation != generation {
            entries.removeValue(forKey: key)
            return nil
        }
        guard entry.expiresAt > Date().timeIntervalSince1970 else {
            entries.removeValue(forKey: key)
            return nil
        }
        return entry.result
    }

    func store(_ key: String, _ result: Result<Data, OmiBackendError>, ttl: TimeInterval, generation: Int) {
        lock.lock()
        defer { lock.unlock() }
        let expiry = ttl == .greatestFiniteMagnitude ? Double.greatestFiniteMagnitude
            : Date().timeIntervalSince1970 + ttl
        entries[key] = Entry(expiresAt: expiry, generation: generation, result: result)
    }

    func remove(matching path: String) {
        lock.lock()
        defer { lock.unlock() }
        entries = entries.filter { !$0.key.contains(path) }
    }
}

/// The span of Omi history this process has actually observed. Free evidence for `status`.
private final class SeenRange: @unchecked Sendable {
    private let lock = NSLock()
    private var oldest: Double?
    private var newest: Double?

    func observe(_ timestamps: [Double]) {
        guard !timestamps.isEmpty else { return }
        lock.lock()
        defer { lock.unlock() }
        for at in timestamps where at > 0 {
            oldest = min(oldest ?? at, at)
            newest = max(newest ?? at, at)
        }
    }

    var range: (oldest: Double, newest: Double)? {
        lock.lock()
        defer { lock.unlock() }
        guard let oldest, let newest else { return nil }
        return (oldest, newest)
    }
}

/// Mutable state shared with a URLSession callback thread.
private final class Box<Value>: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: Value

    init(_ initial: Value) { stored = initial }

    var value: Value {
        get {
            lock.lock()
            defer { lock.unlock() }
            return stored
        }
        set {
            lock.lock()
            stored = newValue
            lock.unlock()
        }
    }
}

// MARK: - Dates

/// Omi returns several timestamp shapes (`…Z`, six-digit fractions, no zone at all). Parsing them
/// leniently is the difference between a dated timeline and a wall of undated text.
enum OmiDate {
    static func parse(_ raw: String?) -> Double? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        let normalized = normalize(trimmed)
        for formatter in formatters {
            if let date = formatter.date(from: normalized) { return date.timeIntervalSince1970 }
        }
        return nil
    }

    /// `2026-07-28T14:05:00Z` — what the `datetime` query parameters accept.
    static func iso(_ epoch: Double) -> String {
        isoOut.string(from: Date(timeIntervalSince1970: epoch))
    }

    /// `2026-07-28` — what `conversations/search` accepts, and only that.
    static func day(_ epoch: Double) -> String {
        dayOut.string(from: Date(timeIntervalSince1970: epoch))
    }

    /// Drops fractional seconds (Firestore emits six digits, which `DateFormatter` will not read)
    /// and supplies UTC when the string carries no zone, which is how Omi stores naive timestamps.
    private static func normalize(_ value: String) -> String {
        var text = value
        if let dot = text.firstIndex(of: ".") {
            var end = text.index(after: dot)
            while end < text.endIndex, text[end].isNumber { end = text.index(after: end) }
            text.removeSubrange(dot..<end)
        }
        let hasZone = text.hasSuffix("Z") || text.hasSuffix("z")
            // A trailing "+05:30" / "-08:00", never the date's own hyphens.
            || text.dropFirst(11).contains("+")
            || text.dropFirst(11).contains("-")
        if !hasZone, text.contains("T") || text.contains(" ") { text += "Z" }
        return text
    }

    private static func fixed(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = format
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }

    // Longest first: DateFormatter happily matches a prefix, so a loose pattern must never get
    // first look at a full timestamp.
    private static let formatters: [DateFormatter] = [
        fixed("yyyy-MM-dd'T'HH:mm:ssXXXXX"),
        fixed("yyyy-MM-dd HH:mm:ssXXXXX"),
        fixed("yyyy-MM-dd'T'HH:mm:ss'Z'"),
        fixed("yyyy-MM-dd HH:mm:ss'Z'"),
        fixed("yyyy-MM-dd'T'HH:mm:ss"),
        fixed("yyyy-MM-dd"),
    ]

    private static let isoOut = fixed("yyyy-MM-dd'T'HH:mm:ss'Z'")
    private static let dayOut = fixed("yyyy-MM-dd")
}

private extension URLError.Code {
    /// Short, non-technical clause for a tool footer.
    var humanReason: String {
        switch self {
        case .notConnectedToInternet: return "this Mac is offline"
        case .cannotFindHost, .dnsLookupFailed: return "DNS could not resolve api.omi.me"
        case .cannotConnectToHost: return "the connection was refused"
        case .networkConnectionLost: return "the connection dropped"
        case .secureConnectionFailed, .serverCertificateUntrusted: return "TLS failed"
        case .cancelled: return "the request was cancelled"
        default: return "network error \(rawValue)"
        }
    }
}

// MARK: - Decoding helpers
//
// One bad field must never fail a whole record: Omi's history spans years of schema changes.

private extension KeyedDecodingContainer {
    func optionalString(_ key: K) -> String? {
        if let value = (try? decodeIfPresent(String.self, forKey: key)) ?? nil { return value }
        if let value = (try? decodeIfPresent(Int.self, forKey: key)) ?? nil { return String(value) }
        return nil
    }

    func optionalDouble(_ key: K) -> Double? {
        if let value = (try? decodeIfPresent(Double.self, forKey: key)) ?? nil { return value }
        if let value = (try? decodeIfPresent(String.self, forKey: key)) ?? nil { return Double(value) }
        return nil
    }

    func optionalInt(_ key: K) -> Int? {
        if let value = (try? decodeIfPresent(Int.self, forKey: key)) ?? nil { return value }
        if let value = optionalDouble(key), value.isFinite { return Int(value) }
        return nil
    }

    func optionalArray<Element: Decodable>(_ type: Element.Type, _ key: K) -> [Element] {
        ((try? decodeIfPresent([Element].self, forKey: key)) ?? nil) ?? []
    }
}
