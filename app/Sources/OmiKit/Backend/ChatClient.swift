import Foundation

// Port of `react-native/src/chatClient.ts` — the desktop chat client over
// `BackendTransport`, covering both the ratified canonical plane (admission +
// generation SSE) and the Old plane (`/v2/messages` + terminal chat streams).
// Error taxonomy lives in BackendError.swift; the copy helpers there are the
// ported `chatErrorCopy`/`chatSessionLost`.

/// The transport refused a request because the backend/plane changed under it
/// (native `OMI_HTTP_BACKEND_CHANGED`).
public struct BackendChangedError: Error, Sendable, Equatable {
    public init() {}
}

/// Old-plane chat send capability. The TS `OmiBackend.sendOmiChat` optional
/// method has no fixed slot on `BackendTransport`, so it is an optional
/// capability probed with `as?`.
public protocol OmiChatStreaming: Sendable {
    func sendOmiChat(
        requestId: String, text: String,
        onFrame: (@Sendable (String) -> Void)?
    ) async throws -> BackendResponse
    func cancelOmiChat(requestId: String) async
}

public enum ChatClientError: Error, Sendable, Equatable {
    case malformed(String)
    case retired
    case transportUnavailable(String)
}

public typealias ChatSendResult = (human: ChatMessage, assistant: ChatMessage?)

public enum TerminalFrame: Sendable, Equatable {
    case done(message: ChatMessage)
    case cancelled(message: ChatMessage?)
    case failed(code: String, retryable: Bool)
}

// MARK: - Local message construction

private let chatMessageSequence = LockedBox(0)

public func createLocalChatMessage(_ text: String, now: Int64) -> ChatMessage {
    let sequence = chatMessageSequence.withLock { value -> Int in
        value += 1
        return value
    }
    return ChatMessage(
        id: "desktop-\(now)-\(sequence)", text: text, sender: .human,
        createdAt: now, generationOutcome: nil, localOnly: true
    )
}

public func pendingAssistantId(_ humanId: String) -> String {
    "pending:\(humanId)"
}

public func createPendingAssistantMessage(
    _ human: ChatMessage, generationId: String? = nil
) -> ChatMessage {
    ChatMessage(
        id: pendingAssistantId(human.id), text: "", sender: .ai,
        createdAt: human.createdAt, generationOutcome: nil,
        generationId: generationId ?? human.id, localOnly: true
    )
}

public func isStreamingAssistant(_ message: ChatMessage) -> Bool {
    message.sender == .ai && message.generationOutcome == nil
        && message.generationId != nil
}

// MARK: - Wire → domain mapping

func desktopChatMessage(_ message: ChatWireMessage) throws -> ChatMessage {
    guard message.sender == "human" || message.sender == "ai" else {
        throw ChatClientError.malformed("Chat message sender is unsupported")
    }
    let outcome: GenerationOutcome?
    switch message.generationOutcome {
    case "completed": outcome = .completed
    case "cancelled": outcome = .cancelled
    default: outcome = nil
    }
    return ChatMessage(
        id: message.id, text: message.text,
        sender: message.sender == "human" ? .human : .ai,
        createdAt: message.createdAt, generationOutcome: outcome
    )
}

// MARK: - History

func chatBackendError(_ response: BackendResponse) -> ChatBackendError {
    var code = "unknown"
    var retryable = false
    var action = "none"
    if let body = response.body, let parsed = JSON.parseOrNull(body), parsed.isRecord,
        let error = parsed["error"], error.isRecord
    {
        if let value = error["code"]?.stringValue { code = value }
        if let value = error["retryable"]?.boolValue { retryable = value }
        if let value = error["action"]?.stringValue { action = value }
    }
    return ChatBackendError(
        status: response.status, backendCode: code, retryable: retryable,
        action: action, retryAfterSeconds: response.retryAfterSeconds
    )
}

func requireJSON(_ body: String?) throws -> JSONValue {
    guard let body else {
        throw ChatClientError.malformed("Backend returned an empty response")
    }
    guard let parsed = JSON.parseOrNull(body) else {
        throw ChatClientError.malformed("Backend returned invalid JSON")
    }
    return parsed
}

public func mergeOlderChatHistory(
    _ current: [ChatMessage], _ older: [ChatMessage]
) -> [ChatMessage] {
    let currentIds = Set(current.map { $0.id })
    return older.filter { !currentIds.contains($0.id) } + current
}

public func reconcileCanonicalChatHistory(
    _ local: [ChatMessage], _ canonical: [ChatMessage]
) -> [ChatMessage] {
    let canonicalIds = Set(canonical.map { $0.id })
    return canonical + local.filter { !canonicalIds.contains($0.id) }
}

// MARK: - Terminal parsing

public func parseTerminal(_ raw: String) throws -> TerminalFrame {
    guard let frames = parseChatGenerationEventStream(raw) else {
        throw ChatClientError.malformed("Generation stream is malformed")
    }
    for frame in frames.reversed() {
        switch frame {
        case .done(let message):
            return .done(message: try desktopChatMessage(message))
        case .cancelled(let message):
            return .cancelled(
                message: message != nil ? try desktopChatMessage(message!) : nil)
        case .failed(let code, let retryable):
            return .failed(code: code, retryable: retryable)
        case .snapshot, .delta:
            continue
        }
    }
    throw ChatClientError.malformed("Generation ended without a terminal frame")
}

func isReplayExpired(_ error: Error) -> Bool {
    if let backendError = error as? ChatBackendError { return backendError.status == 410 }
    return error is GenerationReplayExpired
}

/// Native transport `OMI_HTTP_REPLAY_EXPIRED`.
public struct GenerationReplayExpired: Error, Sendable, Equatable {}

// MARK: - Client functions

func loadOmiHistory(
    _ transport: BackendTransport, offset: Int
) async throws -> ChatHistoryPage {
    let response = try await transport.request(
        BackendRequest(
            id: "omi-chat-history", expectedApiContract: .omi, method: .GET,
            path: "/v2/messages?limit=50&offset=\(offset)"
        ))
    if response.status != 200 { throw chatBackendError(response) }
    return try LegacyOmiChat.parseHistory(response.body, offset: offset)
}

func loadChatHistoryPage(
    _ transport: BackendTransport, path: String
) async throws -> ChatHistoryPage {
    let response = try await transport.request(
        BackendRequest(
            id: "chat-history", expectedApiContract: .canonical, method: .GET,
            path: path
        ))
    if response.status != 200 { throw chatBackendError(response) }
    let envelope = wireToChatHistoryEnvelope(try requireJSON(response.body))
    guard let envelope else {
        throw ChatClientError.malformed("Chat history is malformed")
    }
    let messages = try envelope.messages.map(desktopChatMessage)
    return ChatHistoryPage(
        messages: messages, olderCursor: envelope.olderCursor,
        hasOlder: envelope.hasOlder
    )
}

public func loadNewestChatHistory(
    _ transport: BackendTransport
) async throws -> ChatHistoryPage {
    if await transport.apiContract() == .omi {
        return try await loadOmiHistory(transport, offset: 0)
    }
    return try await loadChatHistoryPage(transport, path: "/v1/chat-messages?limit=50")
}

public func loadChatHistory(
    _ transport: BackendTransport
) async throws -> [ChatMessage] {
    try await loadNewestChatHistory(transport).messages
}

public func loadOlderChatHistory(
    _ transport: BackendTransport, olderCursor: String
) async throws -> ChatHistoryPage {
    if await transport.apiContract() == .omi {
        return try await loadOmiHistory(
            transport, offset: try LegacyOmiChat.historyOffset(olderCursor))
    }
    guard !olderCursor.isEmpty else {
        throw ChatClientError.malformed("Chat history cursor is empty")
    }
    return try await loadChatHistoryPage(
        transport,
        path:
            "/v1/chat-messages?limit=50&olderCursor=\(encodeQueryComponent(olderCursor))"
    )
}

func reconcileGeneration(
    _ admission: ChatWireAdmission, _ history: [ChatMessage]
) throws -> ChatSendResult {
    let canonicalHuman = history.first { $0.id == admission.message.id }
    let assistant = history.first {
        $0.id == admission.generationId && $0.sender == .ai
    }
    guard let canonicalHuman, let assistant else {
        throw ChatClientError.malformed(
            "Generation replay expired before canonical history reconciled")
    }
    return (canonicalHuman, assistant)
}

public func sendChatMessage(
    _ transport: BackendTransport,
    _ text: String,
    now: Int64,
    onGenerationStarted: ((String) -> Void)? = nil,
    localMessage: ChatMessage? = nil,
    onRequestStarted: ((String) -> Bool)? = nil,
    onAssistantText: (@Sendable (String) -> Void)? = nil
) async throws -> ChatSendResult {
    if await transport.apiContract() == .omi {
        guard let streaming = transport as? OmiChatStreaming else {
            throw ChatClientError.transportUnavailable(
                "Omi chat transport is unavailable")
        }
        let human = localMessage ?? createLocalChatMessage(text, now: now)
        if onRequestStarted?(human.id) == false {
            throw ChatClientError.retired
        }
        let parser = LockedBox(IncrementalOmiChatParser())
        let visible = LockedBox("")
        let response = try await streaming.sendOmiChat(
            requestId: human.id, text: text,
            onFrame: { frame in
                let events = parser.withLock { (try? $0.push(frame)) ?? [] }
                for event in events {
                    guard case .data(let chunk) = event else { continue }
                    let text = visible.withLock { value -> String in
                        value += chunk
                        return value
                    }
                    onAssistantText?(text)
                }
            }
        )
        if response.status != 200 { throw chatBackendError(response) }
        let assistant = try LegacyOmiChat.parseStream(response.body)
        return (human, assistant)
    }
    let id = (localMessage ?? createLocalChatMessage(text, now: now)).id
    let response = try await transport.request(
        BackendRequest(
            id: "admit-\(id)", expectedApiContract: .canonical, method: .POST,
            path: "/v1/chat-messages",
            body: JSON.serialize(
                JSONValue.object([
                    ("op", JSONValue.string("create")),
                    ("opId", JSONValue.string("op-\(id)")),
                    ("id", JSONValue.string(id)),
                    ("at", JSONValue.integer(now)),
                    ("text", JSONValue.string(text)),
                    ("sender", JSONValue.string("human")),
                    ("journalRevision", JSONValue.integer(1)),
                    ("type", JSONValue.string("text")),
                    ("appId", .null),
                    ("chatSessionId", .null),
                    ("messageSource", JSONValue.string("desktop_chat")),
                    ("metadata", .null),
                    ("attachmentIds", JSONValue.array([])),
                ]))
        ))
    if response.status != 200 && response.status != 201 {
        throw chatBackendError(response)
    }
    let wireAdmission = wireToChatAdmissionEnvelope(try requireJSON(response.body))
    guard let wireAdmission else {
        throw ChatClientError.malformed("Chat admission is malformed")
    }
    let admissionMessage = try desktopChatMessage(wireAdmission.message)
    onGenerationStarted?(wireAdmission.generationId)

    let parser = LockedBox(IncrementalChatGenerationParser())
    let visible = LockedBox("")
    let onFrame: @Sendable (String) -> Void = { frame in
        guard let events = try? parser.withLock({ try $0.push(frame) }) else { return }
        for event in events {
            switch event.frame {
            case .snapshot(let snapshot):
                visible.set(snapshot)
                onAssistantText?(snapshot)
            case .delta(let delta):
                let text = visible.withLock { value -> String in
                    value += delta
                    return value
                }
                onAssistantText?(text)
            default:
                break
            }
        }
    }

    let terminal: TerminalFrame
    do {
        let streamResponse = try await transport.generationEvents(
            generationId: wireAdmission.generationId, lastEventId: nil,
            onFrame: onFrame)
        if streamResponse.status != 200 { throw chatBackendError(streamResponse) }
        guard let body = streamResponse.body else {
            throw ChatClientError.malformed("Generation returned an empty stream")
        }
        terminal = try parseTerminal(body)
    } catch {
        if isCancellation(error) {
            // Native observer cancellation: reconnect once without frames for
            // the canonical terminal frame.
            do {
                let replay = try await transport.generationEvents(
                    generationId: wireAdmission.generationId, lastEventId: nil,
                    onFrame: { _ in })
                if replay.status != 200 { throw chatBackendError(replay) }
                guard let body = replay.body else {
                    throw ChatClientError.malformed(
                        "Generation returned an empty stream")
                }
                terminal = try parseTerminal(body)
            } catch {
                guard isReplayExpired(error) else { throw error }
                let history = try await loadChatHistory(transport)
                return try reconcileGeneration(wireAdmission, history)
            }
        } else {
            guard isReplayExpired(error) else { throw error }
            let history = try await loadChatHistory(transport)
            return try reconcileGeneration(wireAdmission, history)
        }
    }

    switch terminal {
    case .failed(let code, let retryable):
        return (
            admissionMessage,
            ChatMessage(
                id: "generation:\(wireAdmission.generationId)", text: "",
                sender: .ai, createdAt: admissionMessage.createdAt,
                generationOutcome: .failed,
                generationId: wireAdmission.generationId,
                generationRetryable: retryable, localOnly: true)
        )
    case .cancelled(let message):
        if let message {
            return (admissionMessage, message)
        }
        return (
            admissionMessage,
            ChatMessage(
                id: "generation:\(wireAdmission.generationId)", text: "",
                sender: .ai, createdAt: admissionMessage.createdAt,
                generationOutcome: .cancelled,
                generationId: wireAdmission.generationId, localOnly: true)
        )
    case .done(let message):
        return (admissionMessage, message)
    }
}

public func cancelChatGeneration(
    _ transport: BackendTransport, generationId: String
) async throws {
    await transport.cancelGenerationEvents(generationId: generationId)
}
