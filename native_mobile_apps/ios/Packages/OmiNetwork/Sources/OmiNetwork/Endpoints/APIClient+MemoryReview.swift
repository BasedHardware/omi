import Foundation
import OmiCore

/// The backend's memory review queue (`routers/memories.py` review-queue endpoints): memories
/// held back because they contradict earlier ones.
public extension APIClient {
    /// `GET v3/memories/review-queue` (pending only).
    func memoryReviewQueue() async throws -> [MemoryConflict] {
        let data = try await data(.get, "v3/memories/review-queue", query: [URLQueryItem(name: "limit", value: "100")])
        let array = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []
        return array.compactMap(MemoryConflictMapper.conflict(from:))
    }

    /// `POST v3/memories/review-queue/{id}/resolve` with `accept` or `reject`.
    func resolveMemoryConflict(id: String, decision: MemoryConflict.Decision) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["decision": decision.rawValue, "reason": "user_review"])
        let allowed = CharacterSet.urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))
        let reviewID = id.addingPercentEncoding(withAllowedCharacters: allowed) ?? id
        _ = try await data(.post, "v3/memories/review-queue/\(reviewID)/resolve", body: .json(body))
    }
}

enum MemoryConflictMapper {
    static func conflict(from object: [String: Any]) -> MemoryConflict? {
        guard let id = object["review_id"] as? String, !id.isEmpty else { return nil }
        let status = object["status"] as? String ?? "pending"
        guard status == "pending" || status == "pending_review" else { return nil }
        let candidate = object["candidate"] as? [String: Any] ?? [:]
        let content = (candidate["content"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return nil }
        return MemoryConflict(
            id: id,
            factID: object["fact_id"] as? String ?? candidate["id"] as? String ?? "",
            candidate: content,
            conflictsWith: (object["conflict_with"] as? [String] ?? []).filter { !$0.isEmpty },
            createdAt: BackendDate.parse(object["created_at"] as? String)
        )
    }
}
