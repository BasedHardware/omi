import Foundation
import OmiCore

public extension APIClient {
    /// `GET v1/conversations`, same query as the Flutter app's `getConversations`.
    func conversations(limit: Int, offset: Int) async throws -> [Conversation] {
        let data = try await data(.get, "v1/conversations", query: [
            URLQueryItem(name: "include_discarded", value: "false"),
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "statuses", value: "processing,completed"),
        ])
        return try decode([OmiAPI.Conversation].self, from: data).map(ConversationMapper.map)
    }

    /// `GET v1/conversations/{id}`
    func conversationDetail(id: String) async throws -> ConversationDetail {
        let data = try await data(.get, "v1/conversations/\(id)")
        return try ConversationMapper.detail(decode(OmiAPI.Conversation.self, from: data))
    }
}
