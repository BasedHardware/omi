import Foundation
import OmiCore

/// Creating and editing what Omi captured: tasks, memories, conversations, day recaps.
public extension APIClient {
    /// `POST v1/action-items`.
    func createActionItem(description: String, dueAt: Date?) async throws -> ActionItem {
        var fields: [String: Any] = ["description": description]
        if let dueAt { fields["due_at"] = ISO8601DateFormatter().string(from: dueAt) }
        let body = try JSONSerialization.data(withJSONObject: fields)
        let data = try await data(.post, "v1/action-items", body: .json(body), headers: ["Idempotency-Key": UUID().uuidString])
        return TaskMapper.map(try decode(OmiAPI.ActionItemResponse.self, from: data))
    }

    /// `PATCH v3/memories/{id}` with the new text.
    func editMemory(id: String, content: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["value": content])
        _ = try await data(.patch, "v3/memories/\(id)", body: .json(body))
    }

    /// `DELETE v3/memories/{id}`.
    func deleteMemory(id: String) async throws {
        _ = try await data(.delete, "v3/memories/\(id)")
    }

    /// `PATCH v1/conversations/{id}/title?title=`.
    func renameConversation(id: String, title: String) async throws {
        _ = try await data(.patch, "v1/conversations/\(id)/title", query: [URLQueryItem(name: "title", value: title)])
    }

    /// `DELETE v1/conversations/{id}`.
    func deleteConversation(id: String) async throws {
        _ = try await data(.delete, "v1/conversations/\(id)")
    }

    /// `GET v1/users/daily-summaries`, newest first.
    func dailySummaries(limit: Int) async throws -> [DailySummary] {
        let data = try await data(.get, "v1/users/daily-summaries", query: [URLQueryItem(name: "limit", value: String(limit))])
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return (object?["summaries"] as? [[String: Any]] ?? []).compactMap(DailySummaryMapper.map)
    }

    /// `POST v1/users/daily-summaries`: the recap for a local date, generated if there is none yet.
    func createDailySummary(date: String) async throws -> DailySummary? {
        let body = try JSONSerialization.data(withJSONObject: ["date": date])
        let data = try await data(.post, "v1/users/daily-summaries", body: .json(body))
        return (try JSONSerialization.jsonObject(with: data) as? [String: Any]).flatMap(DailySummaryMapper.map)
    }
}

enum DailySummaryMapper {
    static func map(_ json: [String: Any]) -> DailySummary? {
        guard let id = json["id"] as? String, let date = json["date"] as? String else { return nil }
        let highlights = (json["highlights"] as? [[String: Any]] ?? []).compactMap { item -> DailySummary.Highlight? in
            guard let topic = item["topic"] as? String else { return nil }
            return DailySummary.Highlight(topic: topic, emoji: item["emoji"] as? String, summary: item["summary"] as? String ?? "")
        }
        let decisions = (json["decisions_made"] as? [[String: Any]] ?? []).compactMap { $0["decision"] as? String }
        let stats = json["stats"] as? [String: Any]
        return DailySummary(
            id: id, date: date,
            headline: json["headline"] as? String ?? "",
            overview: json["overview"] as? String ?? "",
            emoji: json["day_emoji"] as? String,
            conversationCount: stats?["total_conversations"] as? Int,
            highlights: highlights, decisions: decisions
        )
    }
}
