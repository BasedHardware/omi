import Foundation
import OmiCore

/// Numeric goals, as Flutter's goals widget uses them (`backend/routers/goals.py`).
public extension APIClient {
    /// `GET v1/goals/all`: the active goals.
    func goals() async throws -> [Goal] {
        let array = try await JSONSerialization.jsonObject(with: data(.get, "v1/goals/all")) as? [[String: Any]] ?? []
        return array.compactMap(GoalMapper.map)
    }

    /// `POST v1/goals` with the released numeric fields (`goal_type: numeric`, min 0).
    func createGoal(title: String, current: Double, target: Double) async throws -> Goal {
        let fields: [String: Any] = [
            "title": title, "goal_type": "numeric",
            "current_value": current, "target_value": target, "min_value": 0, "max_value": max(target, 0),
        ]
        return try await goal(.post, "v1/goals", fields: fields)
    }

    /// `PATCH v1/goals/{id}`: title, current and target.
    func updateGoal(id: String, title: String, current: Double, target: Double) async throws -> Goal {
        let fields: [String: Any] = ["title": title, "current_value": current, "target_value": target]
        return try await goal(.patch, "v1/goals/\(id)", fields: fields)
    }

    /// `PATCH v1/goals/{id}/progress?current_value=`.
    func setGoalProgress(id: String, current: Double) async throws -> Goal {
        let data = try await data(.patch, "v1/goals/\(id)/progress", query: [URLQueryItem(name: "current_value", value: String(current))])
        guard let goal = (try JSONSerialization.jsonObject(with: data) as? [String: Any]).flatMap(GoalMapper.map) else {
            throw APIError.decoding("goal")
        }
        return goal
    }

    /// `DELETE v1/goals/{id}` (the backend abandons it and keeps its links).
    func deleteGoal(id: String) async throws {
        _ = try await data(.delete, "v1/goals/\(id)")
    }

    private func goal(_ method: Method, _ path: String, fields: [String: Any]) async throws -> Goal {
        let body = try JSONSerialization.data(withJSONObject: fields)
        let object = try await JSONSerialization.jsonObject(with: data(method, path, body: .json(body))) as? [String: Any]
        guard let goal = object.flatMap(GoalMapper.map) else { throw APIError.decoding("goal") }
        return goal
    }
}

enum GoalMapper {
    static func map(_ json: [String: Any]) -> Goal? {
        guard let id = json["id"] as? String, let title = json["title"] as? String else { return nil }
        let metric = json["metric"] as? [String: Any]
        return Goal(
            id: id, title: title,
            current: number(json["current_value"]) ?? number(metric?["current"]) ?? 0,
            target: number(json["target_value"]) ?? number(metric?["target"]) ?? 0,
            unit: json["unit"] as? String,
            createdAt: BackendDate.parse(json["created_at"] as? String)
        )
    }

    private static func number(_ value: Any?) -> Double? {
        switch value {
        case let number as NSNumber: number.doubleValue
        case let string as String: Double(string)
        default: nil
        }
    }
}
