import Foundation

/// Where a task app files new tasks: one level of the Asana (workspace → project) or ClickUp
/// (team → space → list) hierarchy (backend `routers/task_integrations.py`).
public enum TaskAppLevel: String, CaseIterable, Sendable {
    case asanaWorkspace, asanaProject, clickupTeam, clickupSpace, clickupList

    public static func levels(for app: String) -> [TaskAppLevel] {
        switch app {
        case "asana": [.asanaWorkspace, .asanaProject]
        case "clickup": [.clickupTeam, .clickupSpace, .clickupList]
        default: []
        }
    }

    /// The path that lists this level's choices under the parent's id.
    func path(parent: String?) -> String? {
        switch self {
        case .asanaWorkspace: "v1/task-integrations/asana/workspaces"
        case .asanaProject: parent.map { "v1/task-integrations/asana/projects/\($0)" }
        case .clickupTeam: "v1/task-integrations/clickup/teams"
        case .clickupSpace: parent.map { "v1/task-integrations/clickup/spaces/\($0)" }
        case .clickupList: parent.map { "v1/task-integrations/clickup/lists/\($0)" }
        }
    }

    /// The response's array key and the item's id key.
    var keys: (list: String, id: String) {
        switch self {
        case .asanaWorkspace: ("workspaces", "gid")
        case .asanaProject: ("projects", "gid")
        case .clickupTeam: ("teams", "id")
        case .clickupSpace: ("spaces", "id")
        case .clickupList: ("lists", "id")
        }
    }

    /// The saved fields (`TaskIntegrationData`): id and name.
    public var fields: (id: String, name: String) {
        switch self {
        case .asanaWorkspace: ("workspace_gid", "workspace_name")
        case .asanaProject: ("project_gid", "project_name")
        case .clickupTeam: ("team_id", "team_name")
        case .clickupSpace: ("space_id", "space_name")
        case .clickupList: ("list_id", "list_name")
        }
    }
}

public struct TaskAppOption: Identifiable, Hashable, Sendable, Codable {
    public let id: String
    public let name: String

    public init(id: String, name: String) {
        self.id = id
        self.name = name
    }
}

public extension APIClient {
    /// The choices of one level (`parent` is the selected id of the level above).
    func taskAppOptions(_ level: TaskAppLevel, parent: String?) async throws -> [TaskAppOption] {
        guard let path = level.path(parent: parent) else { return [] }
        let object = try await JSONSerialization.jsonObject(with: data(.get, path)) as? [String: Any]
        return (object?[level.keys.list] as? [[String: Any]] ?? []).compactMap { item in
            guard let id = item[level.keys.id] as? String else { return nil }
            return TaskAppOption(id: id, name: item["name"] as? String ?? id)
        }
    }

    /// `PUT v1/task-integrations/{app}`: merges the selection; a `nil` value clears that field.
    func saveTaskAppSelection(_ app: String, selection: [TaskAppLevel: TaskAppOption?]) async throws {
        var body: [String: Any] = ["connected": true]
        for (level, option) in selection {
            body[level.fields.id] = option?.id ?? NSNull()
            body[level.fields.name] = option?.name ?? NSNull()
        }
        _ = try await data(.put, "v1/task-integrations/\(app)", body: .json(JSONSerialization.data(withJSONObject: body)))
    }

    /// `GET v1/task-integrations/default`: the app new tasks are exported to ("" or nil when none).
    func defaultTaskApp() async throws -> String? {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/task-integrations/default")) as? [String: Any]
        return (object?["default_app"] as? String).flatMap { $0.isEmpty ? nil : $0 }
    }

    func setDefaultTaskApp(_ app: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["app_key": app])
        _ = try await data(.put, "v1/task-integrations/default", body: .json(body))
    }
}
