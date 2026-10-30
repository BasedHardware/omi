import Foundation
import OmiCore

public extension APIClient {
    /// `POST v1/conversations/search` (backend `routers/conversations.py`): Typesense over titles and
    /// overviews, plus spoken-word hits on page 1, newest first. Hits are full conversations.
    func searchConversations(query: String, page: Int, perPage: Int) async throws -> [Conversation] {
        let body = try JSONSerialization.data(withJSONObject: [
            "query": query, "page": page, "per_page": perPage, "include_discarded": false,
        ])
        let data = try await data(.post, "v1/conversations/search", body: .json(body))
        return try decode(SearchPage.self, from: data).items.map(ConversationMapper.map)
    }

    /// `GET v2/messages` with `offset` (counted in visible messages, newest first on the wire;
    /// returned oldest first). A page shorter than `limit` is the start of the chat.
    func chatHistory(limit: Int, offset: Int, sessionID: String?) async throws -> [ChatMessage] {
        var query = [URLQueryItem(name: "limit", value: String(limit)), URLQueryItem(name: "offset", value: String(offset))]
        if let sessionID { query.append(URLQueryItem(name: "chat_session_id", value: sessionID)) }
        let data = try await data(.get, "v2/messages", query: query)
        let array = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
        return array.compactMap(ChatMessageMapper.message(from:)).reversed()
    }
}

/// `SearchConversationsResponse`; `total_pages` only says whether another page might exist.
private struct SearchPage: Decodable {
    let items: [OmiAPI.Conversation]
}
