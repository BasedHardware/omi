import Foundation
import OmiCore
import OmiNetwork

/// Backend state for goals.
public final class FakeGoals: @unchecked Sendable {
    public var goals: [Goal] = []
    /// One entry per call, e.g. `create:Run 5k`, `progress:g1=3.0`, `delete:g1`.
    public internal(set) var log: [String] = []
    /// Fails just these calls (by log prefix).
    public var failing: Set<String> = []

    public init() {}
}

public extension FakeAPIClient {
    private func recordGoal(_ kind: String, _ entry: String) throws {
        try lock.withLock {
            if let _error { throw _error }
            goalsBackend.log.append("\(kind):\(entry)")
            if goalsBackend.failing.contains(kind) { throw APIError.http(status: 500, body: kind) }
        }
    }

    func goals() async throws -> [Goal] {
        try recordGoal("list", "all")
        return lock.withLock { goalsBackend.goals }
    }

    func createGoal(title: String, current: Double, target: Double) async throws -> Goal {
        try recordGoal("create", title)
        return lock.withLock {
            let goal = Goal(id: "g\(goalsBackend.goals.count + 1)", title: title, current: current, target: target, createdAt: Fixtures.now)
            goalsBackend.goals.append(goal)
            return goal
        }
    }

    func updateGoal(id: String, title: String, current: Double, target: Double) async throws -> Goal {
        try recordGoal("update", "\(id)=\(title)")
        return try changeGoal(id) { goal in
            goal.title = title
            goal.current = current
            goal.target = target
        }
    }

    func setGoalProgress(id: String, current: Double) async throws -> Goal {
        try recordGoal("progress", "\(id)=\(current)")
        return try changeGoal(id) { $0.current = current }
    }

    func deleteGoal(id: String) async throws {
        try recordGoal("delete", id)
        lock.withLock { goalsBackend.goals.removeAll { $0.id == id } }
    }

    private func changeGoal(_ id: String, _ change: (inout Goal) -> Void) throws -> Goal {
        try lock.withLock {
            guard let index = goalsBackend.goals.firstIndex(where: { $0.id == id }) else { throw APIError.http(status: 404, body: "") }
            change(&goalsBackend.goals[index])
            return goalsBackend.goals[index]
        }
    }
}
