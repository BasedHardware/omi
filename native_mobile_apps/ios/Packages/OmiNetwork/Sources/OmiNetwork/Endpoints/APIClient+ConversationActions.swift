import Foundation
import OmiCore

/// Organizing and reworking conversations: star, folders, visibility, reprocess, merge, transcript
/// edits and audio. Contracts from `backend/routers/conversations.py`, `folders.py` and `sync.py`.
public extension APIClient {
    /// `GET v1/conversations` with `starred=true` or `folder_id=`.
    func conversations(limit: Int, offset: Int, filter: ConversationFilter) async throws -> [Conversation] {
        var query = [
            URLQueryItem(name: "include_discarded", value: "false"),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "statuses", value: "processing,completed"),
        ]
        switch filter {
        case .all: break
        case .starred: query.append(URLQueryItem(name: "starred", value: "true"))
        case let .folder(id): query.append(URLQueryItem(name: "folder_id", value: id))
        }
        let data = try await data(.get, "v1/conversations", query: query)
        return try decode([OmiAPI.Conversation].self, from: data).map(ConversationMapper.map)
    }

    /// `PATCH v1/conversations/{id}/starred?starred=`.
    func setConversationStarred(id: String, starred: Bool) async throws {
        _ = try await data(.patch, "v1/conversations/\(id)/starred", query: [URLQueryItem(name: "starred", value: String(starred))])
    }

    /// `PATCH v1/conversations/{id}/visibility?value=shared|private`.
    func setConversationVisibility(id: String, visibility: Conversation.Visibility) async throws {
        _ = try await data(.patch, "v1/conversations/\(id)/visibility", query: [URLQueryItem(name: "value", value: visibility.rawValue)])
    }

    /// `POST v1/conversations/{id}/reprocess`: summarizes again; returns the new conversation.
    func reprocessConversation(id: String) async throws -> ConversationDetail {
        let request = try await request(.post, "v1/conversations/\(id)/reprocess")
        var long = request
        // Processing runs the summary models inline.
        long.timeoutInterval = 120
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: long)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            throw APIError.http(status: status, body: String(bytes: data.prefix(500), encoding: .utf8) ?? "")
        }
        return try ConversationMapper.detail(decode(OmiAPI.Conversation.self, from: data))
    }

    /// `POST v1/conversations/merge`: starts merging in the background (the sources turn `merging`,
    /// then are replaced by one new conversation). Returns the backend's warning, if any.
    func mergeConversations(ids: [String]) async throws -> String? {
        let body = try JSONSerialization.data(withJSONObject: ["conversation_ids": ids, "reprocess": true])
        let data = try await data(.post, "v1/conversations/merge", body: .json(body))
        return try (JSONSerialization.jsonObject(with: data) as? [String: Any])?["warning"] as? String
    }

    /// `PATCH v1/conversations/{id}/segments/text`.
    func editTranscriptSegment(conversationID: String, segmentID: String, text: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["segment_id": segmentID, "text": text])
        _ = try await data(.patch, "v1/conversations/\(conversationID)/segments/text", body: .json(body))
    }

    /// `GET v1/sync/audio/{id}/urls`: the conversation's playback file when it is built.
    func conversationAudio(id: String) async throws -> ConversationAudio {
        let data = try await data(.get, "v1/sync/audio/\(id)/urls")
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        return ConversationAudioMapper.map(object)
    }

    // MARK: Folders

    /// `GET v1/folders` (the backend creates the system folders on first use).
    func folders() async throws -> [Folder] {
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v1/folders")) as? [[String: Any]] ?? []
        return array.compactMap(FolderMapper.map).sorted { $0.order < $1.order }
    }

    /// `PATCH v1/conversations/{id}/folder`; `nil` takes it out of every folder.
    func moveConversation(id: String, toFolder folderID: String?) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["folder_id": folderID.map { $0 as Any } ?? NSNull()])
        _ = try await data(.patch, "v1/conversations/\(id)/folder", body: .json(body))
    }

    /// `POST v1/folders/{id}/conversations/bulk-move`.
    func moveConversations(ids: [String], toFolder folderID: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["conversation_ids": ids])
        _ = try await data(.post, "v1/folders/\(folderID)/conversations/bulk-move", body: .json(body))
    }
}

enum FolderMapper {
    static func map(_ json: [String: Any]) -> Folder? {
        guard let id = json["id"] as? String, let name = json["name"] as? String else { return nil }
        return Folder(
            id: id, name: name,
            icon: json["icon"] as? String ?? "📁",
            color: json["color"] as? String ?? "#6B7280",
            isSystem: json["is_system"] as? Bool ?? false,
            order: json["order"] as? Int ?? 0,
            conversationCount: json["conversation_count"] as? Int ?? 0,
            description: json["description"] as? String ?? ""
        )
    }
}

enum ConversationAudioMapper {
    /// The dense conversation file first; one cached part also plays, several play in a row;
    /// anything pending is polled.
    static func map(_ json: [String: Any]) -> ConversationAudio {
        let retry = TimeInterval(json["poll_after_ms"] as? Int ?? 2000) / 1000
        if let audio = json["conversation_audio"] as? [String: Any] {
            if audio["status"] as? String == "cached", let url = (audio["signed_url"] as? String).flatMap(URL.init(string:)) {
                return .ready(url, duration: audio["duration"] as? Double)
            }
        }
        let densePending = (json["conversation_audio"] as? [String: Any])?["status"] as? String == "pending"
        let files = json["audio_files"] as? [[String: Any]] ?? []
        if files.contains(where: { $0["status"] as? String == "pending" }) { return .pending(retryAfter: retry) }
        let cached = files.compactMap { file -> AudioPart? in
            guard let id = file["id"] as? String, file["status"] as? String == "cached",
                  let url = (file["signed_url"] as? String).flatMap(URL.init(string:)) else { return nil }
            return AudioPart(
                id: id, status: .cached, url: url, duration: (file["duration"] as? NSNumber)?.doubleValue ?? 0,
                contentType: file["content_type"] as? String
            )
        }
        if cached.count == 1, let url = cached[0].url { return .ready(url, duration: cached[0].duration > 0 ? cached[0].duration : nil) }
        // Several parts (Flutter's `ConcatenatingAudioSource` path); the store orders them by start.
        if cached.count > 1 { return .parts(cached) }
        return densePending ? .pending(retryAfter: retry) : .unavailable
    }
}
