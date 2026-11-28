import Foundation
import OmiCore

/// One frame of the `POST v2/messages` stream (backend `routers/chat.py`, `utils/retrieval/agentic.py`).
/// Frames are single lines `<prefix><payload>`; newlines inside payloads arrive as `__CRLF__`.
public enum ChatStreamEvent: Sendable, Equatable {
    /// Canned failure texts the agent streams as ordinary answer text
    /// (backend `utils/retrieval/agentic.py:247-248, 1080, 1272, 1340`, and the safety guard's
    /// tool-call, loop and context limits in `utils/retrieval/safety.py`).
    public static let serviceFailureTexts = [
        "Sorry, I encountered an error. Please try again.",
        "Unable to complete the response. Please try again.",
        "The response took too long. Please try again.",
        "I'm having trouble finding all the information you need. "
            + "Could you try asking a simpler question or breaking this into separate questions?",
        "I seem to be stuck trying to answer your question. Could you rephrase it in a different way?",
        "That's a lot of information to process at once! Could you narrow down your request? "
            + "Try asking about a smaller time period or being more specific about what you're looking for.",
    ]

    public static func isServiceFailure(_ text: String) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return serviceFailureTexts.contains(trimmed)
    }

    case step(String)
    case delta(String)
    case memorySaved
    case failed(String)
    case done(ChatMessage)
    /// A `tool:` frame: the agent waits until the app posts this call's result (only sent when
    /// the request declared `device_tools`).
    case deviceTool(DeviceToolRequest)

    static func parse(_ line: String) -> ChatStreamEvent? {
        func payload(_ prefix: String) -> String? {
            line.hasPrefix(prefix) ? String(line.dropFirst(prefix.count)).replacingOccurrences(of: "__CRLF__", with: "\n") : nil
        }
        if let text = payload("data: ") { return .delta(text) }
        if let text = payload("think: ") {
            // Strip the optional "|app_id:<id>" suffix.
            return .step(text.components(separatedBy: "|app_id:").first ?? text)
        }
        if line.hasPrefix("memory:") { return .memorySaved }
        if let text = payload("error: ") {
            if let data = text.data(using: .utf8),
               let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let message = object["message"] as? String
            {
                return .failed(message)
            }
            return .failed(text)
        }
        if line.hasPrefix("tool: ") {
            return DeviceToolFrame.parse(String(line.dropFirst("tool: ".count))).map(ChatStreamEvent.deviceTool)
        }
        if let encoded = payload("done: "),
           let data = Data(base64Encoded: encoded),
           let message = ChatMessageMapper.message(fromJSON: data)
        {
            return .done(message)
        }
        return nil
    }
}

enum ChatMessageMapper {
    static func message(fromJSON data: Data) -> ChatMessage? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return message(from: object)
    }

    static func message(from object: [String: Any]) -> ChatMessage? {
        guard let id = object["id"] as? String else { return nil }
        let references = (object["memories"] as? [[String: Any]] ?? []).compactMap { memory -> ChatMessage.Reference? in
            guard let id = memory["id"] as? String else { return nil }
            let structured = memory["structured"] as? [String: Any]
            return .init(
                conversationID: id, title: structured?["title"] as? String ?? "", emoji: structured?["emoji"] as? String,
                createdAt: BackendDate.parse(memory["created_at"] as? String)
            )
        }
        let message = ChatMessage(
            id: id,
            text: object["text"] as? String ?? "",
            sender: (object["sender"] as? String) == "human" ? .user : .omi,
            createdAt: BackendDate.parse(object["created_at"] as? String) ?? .now,
            references: references
        )
        return withExtras(message, from: object)
    }
}

public extension APIClient {
    /// `POST v2/messages`: streams the agent's answer. Tools run server-side; `step` frames say which.
    func sendMessage(_ text: String, context: ChatContext?, sessionID: String?) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var body: [String: Any] = ["text": text, "file_ids": [String](), "time_zone": TimeZone.current.identifier]
                    if let context { body["context"] = ["type": context.kind.rawValue, "id": context.id, "title": context.title] }
                    let query = sessionID.map { [URLQueryItem(name: "chat_session_id", value: $0)] } ?? []
                    let request = try await request(
                        .post, "v2/messages", query: query, body: .json(JSONSerialization.data(withJSONObject: body))
                    )
                    var streaming = request
                    streaming.setValue("1", forHTTPHeaderField: "X-Omi-Chat-Failure-Protocol")
                    streaming.timeoutInterval = 180
                    let (bytes, response) = try await session.bytes(for: streaming)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200 ..< 300).contains(status) else { throw APIError.http(status: status, body: "") }
                    for try await line in bytes.lines where !line.isEmpty && !line.hasPrefix(":") {
                        if let event = ChatStreamEvent.parse(line) { continuation.yield(event) }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// `GET v2/messages` (newest first on the wire; returned oldest first).
    func chatHistory(limit: Int, sessionID: String?) async throws -> [ChatMessage] {
        var query = [URLQueryItem(name: "limit", value: String(limit))]
        if let sessionID { query.append(URLQueryItem(name: "chat_session_id", value: sessionID)) }
        let data = try await data(.get, "v2/messages", query: query)
        let array = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
        return array.compactMap(ChatMessageMapper.message(from:)).reversed()
    }

    /// `POST v2/chat-sessions`: a separate thread, so agent runs never land in the main chat.
    func createChatSession(title: String) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["title": String(title.prefix(120))])
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v2/chat-sessions", body: .json(body))) as? [String: Any]
        guard let id = object?["id"] as? String else { throw APIError.decoding("chat session without id") }
        return id
    }

    /// `GET v2/chat-sessions` (newest first): ids and titles.
    func chatSessions() async throws -> [(id: String, title: String)] {
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v2/chat-sessions")) as? [[String: Any]] ?? []
        return array.compactMap { item in (item["id"] as? String).map { ($0, item["title"] as? String ?? "") } }
    }
}
