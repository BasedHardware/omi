import Foundation

public extension APIClient {
    /// `GET v2/chat-sessions?app_id=`: one app's chat threads, newest first. The backend always
    /// filters by app, so these never include the main chat's sessions or agent runs.
    func chatSessions(appID: String) async throws -> [(id: String, title: String)] {
        let query = [URLQueryItem(name: "app_id", value: appID)]
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v2/chat-sessions", query: query)) as? [[String: Any]] ?? []
        return array.compactMap { item in (item["id"] as? String).map { ($0, item["title"] as? String ?? "") } }
    }

    /// `POST v2/chat-sessions` with `app_id`: messages sent into it are answered by that app
    /// (the backend reads the app from the session, `utils/chat_session_target.py`).
    func createChatSession(title: String, appID: String) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["title": String(title.prefix(120)), "app_id": appID])
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v2/chat-sessions", body: .json(body))) as? [String: Any]
        guard let id = object?["id"] as? String else { throw APIError.decoding("chat session without id") }
        return id
    }
}
