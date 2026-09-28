import Foundation

// Port of `react-native/src/desktopReadClient.ts` and `legacyOmiReads.ts` —
// projection reads over both planes with the ratified page envelopes.

public struct TaskRead: Sendable, Equatable {
    public var apiContract: APIContract?
    public var items: [TaskProjection]
    public var page: ReadPageState
    public var accountEpoch: Int64?

    public init(
        apiContract: APIContract? = nil, items: [TaskProjection], page: ReadPageState,
        accountEpoch: Int64? = nil
    ) {
        self.apiContract = apiContract
        self.items = items
        self.page = page
        self.accountEpoch = accountEpoch
    }
}

public enum ReadOutcome<Value: Sendable>: Sendable {
    case success(Value)
    case error(String)

    public var failureMessage: String? {
        switch self {
        case .success: return nil
        case .error(let message): return message
        }
    }
}

public struct DesktopReadOutcomes: Sendable {
    public var conversations: ReadOutcome<DomainRead<ConversationProjection>>
    public var memories: ReadOutcome<DomainRead<MemoryProjection>>
    public var tasks: ReadOutcome<TaskRead>

    public init(
        conversations: ReadOutcome<DomainRead<ConversationProjection>>,
        memories: ReadOutcome<DomainRead<MemoryProjection>>,
        tasks: ReadOutcome<TaskRead>
    ) {
        self.conversations = conversations
        self.memories = memories
        self.tasks = tasks
    }
}

// Failure copy (exact strings from desktopReadClient.ts).
public let desktopCloudBaseURL = "https://api.omi.me"
public let desktopBackendConfigurationCopy =
    "Sign in to Omi cloud to load conversations and memories."
public let desktopBackendUnauthorizedCopy = "Omi cloud needs a signed-in session."
public let desktopBackendServiceCopy =
    "The selected Omi service is unavailable. Check the connection, then retry."
public let desktopLocalBackendServiceCopy =
    "The configured local Omi service is unavailable. Check its connection, then retry."
public let desktopProjectionUnavailableCopy =
    "This saved data is not available from the selected Omi service yet. Retry after its persisted projection is connected."
public let desktopBackendForbiddenCopy = "This saved data is not available for this account."
let desktopReadFailureCopy = "This saved data could not be loaded. Retry without changing it."
let desktopRecoveryGenericCopy =
    "Omi could not load saved conversations or memories. Your saved data has not been changed."

public func desktopRecoveryCopy(
    _ conversations: ReadOutcome<DomainRead<ConversationProjection>>,
    _ memories: ReadOutcome<DomainRead<MemoryProjection>>
) -> String {
    let failures = [conversations.failureMessage, memories.failureMessage]
    for failure in failures {
        guard let failure else { continue }
        switch failure {
        case desktopBackendConfigurationCopy, desktopBackendUnauthorizedCopy,
            desktopBackendServiceCopy, desktopLocalBackendServiceCopy,
            desktopProjectionUnavailableCopy, desktopBackendForbiddenCopy:
            return failure
        default:
            continue
        }
    }
    return desktopRecoveryGenericCopy
}

public func desktopReadErrorCopy(_ error: Error) -> String {
    switch error {
    case TransportFailure.unconfigured:
        return desktopBackendConfigurationCopy
    case TransportFailure.unauthorized:
        return desktopBackendUnauthorizedCopy
    case TransportFailure.transportFailed:
        return desktopBackendServiceCopy
    case ReadClientError.projectionUnavailable:
        return desktopProjectionUnavailableCopy
    default:
        if let message = error as? ReadCopyError { return message.copy }
        return desktopReadFailureCopy
    }
}

/// Carries pre-rendered failure copy through the error channel, mirroring the
/// TS idiom of throwing `new Error(<copy>)`.
public struct ReadCopyError: Error, Sendable, Equatable {
    public let copy: String
    public init(_ copy: String) { self.copy = copy }
}

public enum ReadCursorError: Error, Sendable, Equatable {
    case conversationExpired
    case taskExpired
}

public func matchesSearchQuery(_ searchableText: String, _ query: String) -> Bool {
    let normalized = trimWhitespace(query).lowercased()
    if normalized.isEmpty { return true }
    return searchableText.lowercased().contains(normalized)
}

// MARK: - Epoch → ISO helpers

func epochMillisecondsTimestamp(_ value: JSONValue?, _ label: String) throws -> String {
    guard let integer = value?.safeIntegerValue else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return isoString(fromEpochMilliseconds: integer)
}

func nullableEpochMillisecondsTimestamp(
    _ value: JSONValue?, _ label: String
) throws -> String? {
    if isNullValue(value) { return nil }
    return try epochMillisecondsTimestamp(value, label)
}

/// `new Date(ms).toISOString()`.
public func isoString(fromEpochMilliseconds milliseconds: Int64) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(identifier: "UTC")
    formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"
    return formatter.string(from: Date(timeIntervalSince1970: Double(milliseconds) / 1000))
}

/// `new Date(value).toISOString()` for legacy `date()` fields; nil when the
/// value does not parse as an ISO timestamp.
public func isoString(fromDate value: JSONValue?) -> String? {
    guard let text = value?.stringValue else { return nil }
    let bytes = Array(text.utf8)
    guard bytes.count >= 11,
        (0...3).allSatisfy({ bytes[$0] >= 0x30 && bytes[$0] <= 0x39 }),
        bytes[4] == UInt8(ascii: "-"), bytes[7] == UInt8(ascii: "-"),
        bytes[10] == UInt8(ascii: "T")
    else { return nil }
    guard let seconds = ISO8601Reader.epochSeconds(text) else { return nil }
    return isoString(fromEpochMilliseconds: Int64(seconds * 1000))
}

public func epochMilliseconds(fromDate value: JSONValue?) -> Int64? {
    guard let iso = isoString(fromDate: value) else { return nil }
    guard let seconds = ISO8601Reader.epochSeconds(iso) else { return nil }
    return Int64(seconds * 1000)
}

// MARK: - Read plumbing

public enum ReadClientError: Error, Sendable, Equatable {
    case malformed(String)
    case projectionUnavailable
}

func read(
    _ transport: BackendTransport, id: String, path: String,
    expectedApiContract: APIContract? = .canonical
) async throws -> JSONValue {
    let response = try await transport.request(
        BackendRequest(id: id, expectedApiContract: expectedApiContract, method: .GET, path: path)
    )
    if response.status != 200 {
        if response.status == 400, id == "desktop-tasks-read", path.contains("?cursor=") {
            throw ReadCursorError.taskExpired
        }
        if response.status == 400, id == "desktop-conversations-read",
            path.contains("&cursor=")
        {
            throw ReadCursorError.conversationExpired
        }
        if response.status == 401 {
            throw ReadCopyError(desktopBackendUnauthorizedCopy)
        }
        if response.status == 403 {
            throw ReadCopyError(desktopBackendForbiddenCopy)
        }
        if response.status == 503, let body = response.body,
            let parsed = JSON.parseOrNull(body), parsed.isRecord,
            let error = parsed["error"], error.isRecord,
            error["code"]?.stringValue == "projection_unavailable",
            error["retryable"]?.boolValue == true,
            error["action"]?.stringValue == "retry"
        {
            throw ReadClientError.projectionUnavailable
        }
        throw ReadCopyError(
            response.status >= 500 ? desktopBackendServiceCopy : desktopReadFailureCopy)
    }
    guard let body = response.body else {
        throw ReadClientError.malformed("\(id) returned an empty response")
    }
    guard let parsed = JSON.parseOrNull(body) else {
        throw ReadClientError.malformed("\(id) returned invalid JSON")
    }
    return parsed
}

func requireObject(_ value: JSONValue?, _ label: String) throws -> JSONValue {
    guard let value, value.isRecord else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return value
}

func requireString(_ value: JSONValue?, _ label: String) throws -> String {
    guard let text = value?.stringValue, !text.isEmpty else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return text
}

func requireText(_ value: JSONValue?, _ label: String) throws -> String {
    guard let text = value?.stringValue else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return text
}

func requireBool(_ value: JSONValue?, _ label: String) throws -> Bool {
    guard let flag = value?.boolValue else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return flag
}

func requireFinite(_ value: JSONValue?, _ label: String) throws -> Double {
    guard let number = value?.numberValue, number.isFinite else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return number
}

func requireInteger(_ value: JSONValue?, _ label: String) throws -> Int64 {
    guard let integer = value?.safeIntegerValue else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return integer
}

func requireNullableInteger(_ value: JSONValue?, _ label: String) throws -> Int64? {
    if isNullValue(value) { return nil }
    return try requireInteger(value, label)
}

func requireStringArray(_ value: JSONValue?, _ label: String) throws -> [String] {
    guard let array = value?.arrayValue, array.allSatisfy({ $0.stringValue != nil }) else {
        throw ReadClientError.malformed("\(label) is malformed")
    }
    return array.compactMap { $0.stringValue }
}

// MARK: - Page envelope validation (validatePage)

func validatePage(
    _ value: JSONValue, _ label: String, _ completenessVersion: String
) throws -> (items: [JSONValue], page: ReadPageState) {
    let page = try requireObject(value, label)
    guard page["contractVersion"]?.stringValue == "1.0.0" else {
        throw ReadClientError.malformed("\(label) contractVersion is malformed")
    }
    guard let rawItems = page["items"]?.arrayValue else {
        throw ReadClientError.malformed("\(label) items are malformed")
    }
    let window = try requireObject(page["window"], "\(label) window")
    let windowStatus = try requireString(window["status"], "\(label) window status")
    guard windowStatus == "complete" || windowStatus == "more"
        || windowStatus == "incomplete"
    else {
        throw ReadClientError.malformed("\(label) window status is malformed")
    }
    let complete = try requireBool(window["complete"], "\(label) window complete")
    let hasMore = try requireBool(window["hasMore"], "\(label) window hasMore")
    guard isNullValue(window["nextCursor"]) || window["nextCursor"]?.stringValue != nil else {
        throw ReadClientError.malformed("\(label) window cursor is malformed")
    }
    let nextCursor = window["nextCursor"]?.stringValue
    if (hasMore && (nextCursor == nil || nextCursor!.isEmpty)) || (complete && hasMore) {
        throw ReadClientError.malformed("\(label) window is malformed")
    }
    let completeness = try requireObject(page["completeness"], "\(label) completeness")
    guard completeness["version"]?.stringValue == completenessVersion else {
        throw ReadClientError.malformed("\(label) completeness version is malformed")
    }
    let completenessStatus = try requireString(
        completeness["status"], "\(label) completeness status")
    guard completenessStatus == "complete" || completenessStatus == "incomplete"
        || completenessStatus == "degraded" || completenessStatus == "partial"
    else {
        throw ReadClientError.malformed("\(label) completeness status is malformed")
    }
    guard let reasons = completeness["reasons"]?.arrayValue,
        reasons.allSatisfy({ $0.stringValue != nil })
    else {
        throw ReadClientError.malformed("\(label) completeness reasons are malformed")
    }
    if !isNullValue(page["absence"]) {
        _ = try requireObject(page["absence"], "\(label) absence")
    }
    return (
        rawItems.compactMap { $0.isRecord ? $0 : nil },
        ReadPageState(
            windowStatus: ReadWindowStatus(rawValue: windowStatus) ?? .unknown,
            complete: complete, hasMore: hasMore, nextCursor: nextCursor,
            completenessStatus:
                ReadCompletenessStatus(rawValue: completenessStatus) ?? .unknown,
            reasons: reasons.compactMap { $0.stringValue })
    )
}

// MARK: - Canonical conversations

public func loadConversations(
    _ transport: BackendTransport, cursor: String? = nil
) async throws -> DomainRead<ConversationProjection> {
    if await transport.apiContract() == .omi {
        return try await loadOmiConversations(transport, cursor: cursor)
    }
    if let cursor, cursor.isEmpty || cursor.count > 16384 {
        throw ReadClientError.malformed("Conversation cursor is malformed")
    }
    let path =
        "/v1/conversations?limit=50"
        + (cursor == nil ? "" : "&cursor=\(encodeQueryComponent(cursor!))")
    let value = try await read(transport, id: "desktop-conversations-read", path: path)
    let page = try validatePage(
        value, "Conversations response", "conversations-completeness-v1")
    var ids = Set<String>()
    let items = try page.items.enumerated().map { index, record -> ConversationProjection in
        let id = try requireString(record["id"], "Conversation \(index) id")
        if ids.contains(id) {
            throw ReadClientError.malformed("Conversation IDs are duplicated")
        }
        ids.insert(id)
        let title = try requireText(record["title"], "Conversation \(index) title")
        let summary = try requireText(record["overview"], "Conversation \(index) overview")
        let createdAt = try epochMillisecondsTimestamp(
            record["createdAt"], "Conversation \(index) createdAt")
        let updatedAt = try epochMillisecondsTimestamp(
            record["updatedAt"], "Conversation \(index) updatedAt")
        let startedAt = try nullableEpochMillisecondsTimestamp(
            record["startedAt"], "Conversation \(index) startedAt")
        let finishedAt = try nullableEpochMillisecondsTimestamp(
            record["finishedAt"], "Conversation \(index) finishedAt")
        let source = try requireString(record["source"], "Conversation \(index) source")
        let status = try requireString(record["status"], "Conversation \(index) status")
        let discarded = try requireBool(record["discarded"], "Conversation \(index) discarded")
        let capturedAtMs = record["capturedAtMs"]?.safeIntegerValue
        guard isOptionalCaptureTimestamp(capturedAtMs) else {
            throw ReadClientError.malformed(
                "Conversation \(index) capturedAtMs is malformed")
        }
        let starred = try requireBool(record["starred"], "Conversation \(index) starred")
        let visibility = try requireString(
            record["visibility"], "Conversation \(index) visibility")
        guard visibility == "public" || visibility == "private" || visibility == "shared"
        else {
            throw ReadClientError.malformed(
                "Conversation \(index) visibility is malformed")
        }
        let locked = try requireBool(record["isLocked"], "Conversation \(index) isLocked")
        guard isNullValue(record["folderId"]) || record["folderId"]?.stringValue != nil else {
            throw ReadClientError.malformed("Conversation \(index) folderId is malformed")
        }
        return ConversationProjection(
            capturedAtMs: capturedAtMs, id: id, title: title, summary: summary,
            searchableText: "\(title)\n\(summary)", createdAt: createdAt,
            updatedAt: updatedAt, startedAt: startedAt, finishedAt: finishedAt,
            starred: starred, status: status, source: source,
            visibility: ProjectionVisibility(rawValue: visibility) ?? .priv,
            folderId: record["folderId"]?.stringValue, locked: locked,
            discarded: discarded
        )
    }
    return DomainRead(items: items, page: page.page)
}

// MARK: - Memories

/// Port of `parseMemoryText` — the provenance-label prefixes are matched
/// without NSRegularExpression so the file stays Skip-transpilable.
public func parseMemoryText(_ text: String) -> (text: String, provenanceLabel: String?) {
    // Pattern 1: ((?:[a-z0-9_-]+:){2,}[a-z0-9_-]+)\s+(.+)$ — two or more
    // colon-terminated tokens, one final token without a colon, whitespace,
    // remainder.
    if let match = matchProvenanceList(text) {
        return match
    }
    // Pattern 2: ([a-z0-9]+(?:-[a-z0-9]+){2,}):\s+(.+)$ — a hyphenated token
    // (2+ hyphens) ending in a colon.
    if let match = matchHyphenatedProvenance(text) {
        return match
    }
    return (text, nil)
}

private func tokenChar(_ scalar: Unicode.Scalar) -> Bool {
    (scalar.value >= 0x30 && scalar.value <= 0x39)
        || (scalar.value >= 0x61 && scalar.value <= 0x7A)
        || scalar == "_" || scalar == "-"
}

private func isTokenCharacter(_ character: Character) -> Bool {
    // Case-insensitive token class [a-z0-9_-].
    character.unicodeScalars.allSatisfy {
        tokenChar(Unicode.Scalar(String($0).lowercased().unicodeScalars.first!))
    }
}

private func isWhitespaceCharacter(_ character: Character) -> Bool {
    character == " " || character == "\t" || character == "\n" || character == "\r"
        || character == "\u{0B}" || character == "\u{0C}"
}

private func matchProvenanceList(_ text: String) -> (text: String, provenanceLabel: String?)? {
    // ((?:[a-z0-9_-]+:){2,}[a-z0-9_-]+)\s+(.+)$ with ignoreCase + dotall.
    var tokens = [String]()
    var token = ""
    var index = text.startIndex
    while index < text.endIndex {
        let character = text[index]
        if isTokenCharacter(character) {
            token.append(character)
            index = text.index(after: index)
        } else if character == ":" {
            if token.isEmpty { return nil }
            tokens.append(token)
            token = ""
            index = text.index(after: index)
        } else if isWhitespaceCharacter(character) {
            guard tokens.count >= 2, !token.isEmpty else { return nil }
            var bodyStart = index
            while bodyStart < text.endIndex, isWhitespaceCharacter(text[bodyStart]) {
                bodyStart = text.index(after: bodyStart)
            }
            let body = String(text[bodyStart...])
            guard !body.isEmpty else { return nil }
            return (body, tokens.joined(separator: ":") + ":\(token)")
        } else {
            return nil
        }
    }
    return nil
}

private func matchHyphenatedProvenance(_ text: String) -> (text: String, provenanceLabel: String?)? {
    guard let colon = text.firstIndex(of: ":") else { return nil }
    let label = String(text[..<colon])
    var rest = String(text[text.index(after: colon)...])
    guard rest.hasPrefix(" ") else { return nil }
    while rest.hasPrefix(" ") { rest = String(rest.dropFirst(1)) }
    guard !rest.isEmpty else { return nil }
    // Label grammar: [a-z0-9]+(-[a-z0-9]+){2,}, case-insensitive.
    let hyphens = label.filter { $0 == "-" }.count
    guard hyphens >= 2 else { return nil }
    for group in label.split(separator: "-", omittingEmptySubsequences: false) {
        let groupOK = !group.isEmpty
            && group.unicodeScalars.allSatisfy { scalar in
                (scalar.value >= 0x30 && scalar.value <= 0x39)
                    || (scalar.value >= 0x61 && scalar.value <= 0x7A)
                    || (scalar.value >= 0x41 && scalar.value <= 0x5A)
            }
        guard groupOK else { return nil }
    }
    return (rest, label)
}

public func loadMemories(
    _ transport: BackendTransport, cursor: String? = nil
) async throws -> DomainRead<MemoryProjection> {
    if await transport.apiContract() == .omi {
        return try await loadOmiMemories(transport, cursor: cursor)
    }
    if let cursor, cursor.isEmpty || cursor.count > 16384 {
        throw ReadClientError.malformed("Memory cursor is malformed")
    }
    let path =
        cursor == nil
        ? "/v1/memories?limit=50"
        : "/v1/memories?limit=50&cursor=\(encodeQueryComponent(cursor!))"
    let validated = try validatePage(
        try await read(transport, id: "desktop-memories-read", path: path),
        "Memories response", "recall-completeness-v1")
    var ids = Set<String>()
    let items = try validated.items.enumerated().map { index, item -> MemoryProjection in
        let id = try requireString(item["id"], "Memory \(index) id")
        if ids.contains(id) {
            throw ReadClientError.malformed("Memory IDs are duplicated")
        }
        ids.insert(id)
        let text = try requireString(item["text"], "Memory \(index) text")
        let parsedText = parseMemoryText(text)
        let citations = try requireStringArray(
            item["citations"], "Memory \(index) citations")
        let provenance = try requireObject(
            item["provenance"], "Memory \(index) provenance")
        let synthesisVersion = try requireString(
            provenance["synthesisVersion"], "Memory \(index) synthesisVersion")
        let inputDigest = try requireString(
            provenance["inputDigest"], "Memory \(index) inputDigest")
        let outputDigest = try requireString(
            provenance["outputDigest"], "Memory \(index) outputDigest")
        var timestamp: Int64?
        let timestampValue = item["updatedAt"] ?? item["createdAt"]
        if timestampValue != nil {
            timestamp = try requireInteger(timestampValue!, "Memory \(index) timestamp")
        }
        return MemoryProjection(
            id: id, title: parsedText.text, summary: parsedText.text,
            searchableText: "\(parsedText.text)\n\(citations.joined(separator: "\n"))",
            citations: citations, timestamp: timestamp,
            provenance: MemoryProvenance(
                label: parsedText.provenanceLabel, synthesisVersion: synthesisVersion,
                inputDigest: inputDigest, outputDigest: outputDigest)
        )
    }
    return DomainRead(items: items, page: validated.page)
}

// MARK: - Tasks

public func loadTasks(
    _ transport: BackendTransport, cursor: String? = nil
) async throws -> TaskRead {
    if await transport.apiContract() == .omi {
        return try await loadOmiTasks(transport, cursor: cursor)
    }
    if let cursor, cursor.isEmpty || cursor.count > 16384 {
        throw ReadClientError.malformed("Task cursor is malformed")
    }
    let path = "/v1/tasks" + (cursor == nil ? "" : "?cursor=\(encodeQueryComponent(cursor!))")
    let value = try await read(transport, id: "desktop-tasks-read", path: path)
    let envelope = try requireObject(value, "Tasks response")
    let accountEpoch = envelope["accountEpoch"] == nil
        ? nil : try requireInteger(envelope["accountEpoch"], "Tasks response accountEpoch")
    let validated = try validatePage(value, "Tasks response", "tasks-completeness-v1")
    let items = try validated.items.enumerated().map { index, item -> TaskProjection in
        let id = try requireString(item["id"], "Task \(index) id")
        let description = try requireString(item["description"], "Task \(index) description")
        let completed = try requireBool(item["completed"], "Task \(index) completed")
        let completedAt = try requireNullableInteger(
            item["completedAt"], "Task \(index) completedAt")
        let dueAt = try requireNullableInteger(item["dueAt"], "Task \(index) dueAt")
        guard isNullValue(item["owner"]) || item["owner"]?.stringValue != nil else {
            throw ReadClientError.malformed("Task \(index) owner is malformed")
        }
        let owner = item["owner"]?.stringValue
        let source = try requireString(item["source"], "Task \(index) source")
        let provenance = try requireStringArray(
            item["provenance"], "Task \(index) provenance")
        let sortOrder = try requireFinite(item["sortOrder"], "Task \(index) sortOrder")
        let indentLevel = try requireInteger(item["indentLevel"], "Task \(index) indentLevel")
        if indentLevel < 0 {
            throw ReadClientError.malformed("Task \(index) indentLevel is malformed")
        }
        let createdAt = try requireInteger(item["createdAt"], "Task \(index) createdAt")
        let updatedAt = try requireInteger(item["updatedAt"], "Task \(index) updatedAt")
        let revision =
            isNullValue(item["revision"])
            ? nil : try requireString(item["revision"], "Task \(index) revision")
        return TaskProjection(
            id: id, title: description,
            summary: completed
                ? "Completed" : dueAt == nil ? "Pending" : "Due \(dueAt!)",
            searchableText: description, completed: completed,
            completedAt: completedAt, dueAt: dueAt, owner: owner, source: source,
            provenance: provenance, sortOrder: Int(sortOrder),
            indentLevel: Int(indentLevel), createdAt: createdAt,
            updatedAt: updatedAt, revision: revision
        )
    }
    if Set(items.map { $0.id }).count != items.count {
        throw ReadClientError.malformed("Task IDs are duplicated")
    }
    return TaskRead(
        apiContract: nil, items: items, page: validated.page, accountEpoch: accountEpoch)
}

public func loadDesktopReads(
    _ transport: BackendTransport
) async -> DesktopReadOutcomes {
    func run<Value>(_ body: () async throws -> Value) async -> ReadOutcome<Value> {
        do {
            return .success(try await body())
        } catch {
            return .error(desktopReadErrorCopy(error))
        }
    }
    let conversations = await run { try await loadConversations(transport) }
    let memories = await run { try await loadMemories(transport) }
    let tasks = await run { try await loadTasks(transport) }
    return DesktopReadOutcomes(
        conversations: conversations, memories: memories, tasks: tasks)
}
