import Foundation
import OmiCore

extension ChatMessageMapper {
    /// Rating, follow-up chip, chart and files of a stored or streamed message (backend `Message`).
    static func withExtras(_ message: ChatMessage, from object: [String: Any]) -> ChatMessage {
        var message = message
        message.serverID = message.id
        message.rating = (object["rating"] as? NSNumber)?.intValue
        message.followUp = followUp(from: object["content_blocks"])
        message.blocks = ChatBlockMapper.blocks(from: object["content_blocks"])
        message.kind = (object["type"] as? String).flatMap(ChatMessage.Kind.init(rawValue:)) ?? .text
        message.chart = (object["chart_data"] as? [String: Any]).flatMap(chart(from:))
        message.files = (object["files"] as? [[String: Any]] ?? []).compactMap(file(from:))
        let envelope = object["evidence"] as? [String: Any]
        message.evidence = (envelope?["references"] as? [[String: Any]] ?? []).compactMap(evidence(from:))
        return message
    }

    /// The one grounded next question (`followUp`, `utils/chat_followup.py`); a push sends the
    /// blocks as a JSON string.
    static func followUp(from value: Any?) -> String? {
        let blocks = (value as? [[String: Any]])
            ?? (value as? String).flatMap { try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [[String: Any]] } ?? []
        let block = blocks.first { ["followUp", "follow_up"].contains($0["type"] as? String) }
        return (block?["text"] as? String).flatMap { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $0 }
    }

    /// One source reference (backend `ChatEvidenceReference`); unknown kinds and states are kept
    /// as such, a reference without an id is dropped.
    static func evidence(from object: [String: Any]) -> ChatEvidence? {
        guard let id = (object["id"] as? String)?.trimmingCharacters(in: .whitespaces), !id.isEmpty else { return nil }
        func text(_ key: String) -> String? {
            (object[key] as? String).flatMap { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $0 }
        }
        func milliseconds(_ key: String) -> Int? {
            (object[key] as? NSNumber)?.intValue
        }
        return ChatEvidence(
            id: id,
            kind: (object["kind"] as? String).flatMap { ChatEvidence.Kind(rawValue: $0.lowercased()) } ?? .unknown,
            state: (object["state"] as? String).flatMap { ChatEvidence.State(rawValue: $0.lowercased()) } ?? .unknown,
            title: text("title"),
            summary: text("summary"),
            conversationID: text("conversation_id"),
            segmentID: text("segment_id"),
            startMs: milliseconds("start_ms"),
            endMs: milliseconds("end_ms"),
            capturedAtMs: milliseconds("captured_at_ms")
        )
    }

    static func file(from object: [String: Any]) -> ChatFile? {
        guard let id = object["id"] as? String else { return nil }
        let thumbnail = (object["thumbnail"] as? String).flatMap(URL.init(string:))
            .flatMap { $0.scheme?.hasPrefix("http") == true ? $0 : nil }
        return ChatFile(
            id: id, name: object["name"] as? String ?? "", mimeType: object["mime_type"] as? String ?? "", thumbnailURL: thumbnail
        )
    }

    static func chart(from object: [String: Any]) -> ChatChart? {
        let series = (object["datasets"] as? [[String: Any]] ?? []).compactMap { set -> ChatChart.Series? in
            let points = (set["data_points"] as? [[String: Any]] ?? []).compactMap { point -> ChatChart.Point? in
                guard let label = point["label"] as? String, let value = (point["value"] as? NSNumber)?.doubleValue else { return nil }
                return ChatChart.Point(label: label, value: value)
            }
            guard !points.isEmpty else { return nil }
            return ChatChart.Series(label: set["label"] as? String ?? "", points: points, color: set["color"] as? String)
        }
        guard !series.isEmpty else { return nil }
        return ChatChart(
            kind: (object["chart_type"] as? String).flatMap(ChatChart.Kind.init(rawValue:)) ?? .bar,
            title: object["title"] as? String ?? "",
            xLabel: object["x_label"] as? String,
            yLabel: object["y_label"] as? String,
            series: series
        )
    }
}

public extension ChatStreamEvent {
    /// The machine-readable reason of an `error:` frame (`quota_exceeded`, `timeout`, `server_error` …).
    static func errorCode(_ line: String) -> String? {
        guard line.hasPrefix("error: "),
              let data = line.dropFirst("error: ".count).data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return object["error"] as? String
    }
}

public extension APIClient {
    /// `POST v2/messages` with photos and files (ids from `uploadChatFile`). Unlike `sendMessage`,
    /// a typed `error:` frame arrives as `.failed(<code>)`, so the chat can word it.
    func sendChatMessage(
        _ text: String, fileIDs: [String], context: ChatContext?, sessionID: String?, deviceTools: [String]
    ) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var body: [String: Any] = ["text": text, "file_ids": fileIDs, "time_zone": TimeZone.current.identifier]
                    if let context { body["context"] = ["type": context.kind.rawValue, "id": context.id, "title": context.title] }
                    if !deviceTools.isEmpty { body["device_tools"] = deviceTools }
                    let query = sessionID.map { [URLQueryItem(name: "chat_session_id", value: $0)] } ?? []
                    var streaming = try await request(
                        .post, "v2/messages", query: query, body: .json(JSONSerialization.data(withJSONObject: body))
                    )
                    streaming.setValue("1", forHTTPHeaderField: "X-Omi-Chat-Failure-Protocol")
                    // "Omi asks" waits for a person; the turn's own budget bounds it server-side.
                    streaming.timeoutInterval = deviceTools.isEmpty ? 180 : 300
                    let (bytes, response) = try await session.bytes(for: streaming)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200 ..< 300).contains(status) else { throw APIError.http(status: status, body: "") }
                    for try await line in bytes.lines where !line.isEmpty && !line.hasPrefix(":") {
                        if let code = ChatStreamEvent.errorCode(line) {
                            continuation.yield(.failed(code))
                        } else if let event = ChatStreamEvent.parse(line) {
                            continuation.yield(event)
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// `POST v2/voice-message/transcribe` (multipart `files`, the same file `v2/voice-messages` takes).
    func transcribeVoiceMessage(filename: String, audio: Data) async throws -> String {
        let data = try await data(
            .post, "v2/voice-message/transcribe",
            body: .file(field: "files", filename: filename, mimeType: "application/octet-stream", data: audio)
        )
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (object?["transcript"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// `POST v1/users/analytics/chat_message`: 1 helpful, -1 not helpful (with a reason key), 0 cleared.
    func rateChatMessage(id: String, value: Int, reason: String?) async throws {
        var query = [URLQueryItem(name: "message_id", value: id), URLQueryItem(name: "value", value: String(value))]
        if let reason, !reason.isEmpty { query.append(URLQueryItem(name: "reason", value: reason)) }
        _ = try await data(.post, "v1/users/analytics/chat_message", query: query)
    }

    /// `DELETE v2/messages?chat_session_id=`: empties that one session (it stays) and returns Omi's
    /// new greeting. Always scoped: without a session the backend deletes its "current" one.
    func clearChat(sessionID: String) async throws -> ChatMessage? {
        let data = try await data(.delete, "v2/messages", query: [URLQueryItem(name: "chat_session_id", value: sessionID)])
        return ChatMessageMapper.message(fromJSON: data)
    }

    /// `POST v2/files` (multipart `files`): one photo or document for the next message.
    func uploadChatFile(filename: String, mimeType: String, data fileData: Data) async throws -> ChatFile {
        let data = try await data(.post, "v2/files", body: .file(field: "files", filename: filename, mimeType: mimeType, data: fileData))
        let array = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
        guard let file = array.first.flatMap(ChatMessageMapper.file(from:)) else { throw APIError.decoding("upload without file") }
        return file
    }

    /// `POST v2/tts/synthesize`: MP3 of `text` (at most 5,000 characters) in the assistant voice,
    /// or in `voiceID` for a preview.
    func synthesizeSpeech(text: String, voiceID: String?) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let voiceID { body["voice_id"] = voiceID }
        return try await data(
            .post, "v2/tts/synthesize", body: .json(JSONSerialization.data(withJSONObject: body)), headers: ["Accept": "audio/mpeg"]
        )
    }
}
