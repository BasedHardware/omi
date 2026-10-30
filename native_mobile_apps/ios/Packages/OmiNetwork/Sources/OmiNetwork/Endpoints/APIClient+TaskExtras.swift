import Foundation
import OmiCore

/// Bulk delete, subtasks, export to task apps, share links and the Apple Reminders sync.
/// Contracts from `backend/routers/action_items.py` and `task_integrations.py`.
public extension APIClient {
    /// `POST v1/action-items/batch-delete`; returns the ids the backend deleted.
    func deleteActionItems(ids: [String]) async throws -> [String] {
        let body = try JSONSerialization.data(withJSONObject: ["ids": ids])
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v1/action-items/batch-delete", body: .json(body)))
        return (object as? [String: Any])?["deleted_ids"] as? [String] ?? ids
    }

    /// `PATCH v1/action-items/batch`: order and indent level (0...3) of many rows at once.
    func setTaskLayout(_ entries: [TaskLayout]) async throws {
        let items: [[String: Any]] = entries.map { entry in
            var item: [String: Any] = ["id": entry.id]
            if let sortOrder = entry.sortOrder { item["sort_order"] = sortOrder }
            if let indentLevel = entry.indentLevel { item["indent_level"] = indentLevel }
            return item
        }
        let body = try JSONSerialization.data(withJSONObject: ["items": items])
        _ = try await data(.patch, "v1/action-items/batch", body: .json(body))
    }

    /// `POST v1/task-integrations/{app}/tasks`: the backend creates it with the stored OAuth tokens.
    /// Throws when the app refuses (`success: false`), so the task is not marked exported.
    func createIntegrationTask(app: String, title: String, dueAt: Date?) async throws {
        var fields: [String: Any] = ["title": title, "description": "From Omi"]
        if let dueAt { fields["due_date"] = ISO8601DateFormatter().string(from: dueAt) }
        let body = try JSONSerialization.data(withJSONObject: fields)
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v1/task-integrations/\(app)/tasks", body: .json(body)))
        let json = object as? [String: Any]
        guard json?["success"] as? Bool == true else {
            throw APIError.http(status: 502, body: json?["error"] as? String ?? "export failed")
        }
    }

    /// `PATCH v1/action-items/{id}` with `exported`, `export_date`, `export_platform` (and the reminder id).
    func markActionItemExported(id: String, platform: String, appleReminderID: String?) async throws {
        var fields: [String: Any] = [
            "exported": true,
            "export_date": ISO8601DateFormatter().string(from: .now),
            "export_platform": platform,
        ]
        if let appleReminderID { fields["apple_reminder_id"] = appleReminderID }
        let body = try JSONSerialization.data(withJSONObject: fields)
        _ = try await data(.patch, "v1/action-items/\(id)", body: .json(body))
    }

    /// `POST v1/action-items/share` → the public link (`https://h.omi.me/tasks/<token>`).
    func shareActionItems(ids: [String]) async throws -> URL {
        let body = try JSONSerialization.data(withJSONObject: ["task_ids": ids])
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v1/action-items/share", body: .json(body)))
        guard let string = (object as? [String: Any])?["url"] as? String, let url = URL(string: string) else {
            throw APIError.decoding("no share url")
        }
        return url
    }

    /// `GET v1/action-items/shared/{token}` (public): who shared what.
    func sharedActionItems(token: String) async throws -> SharedTasks {
        let object = try await JSONSerialization.jsonObject(with: data(.get, "v1/action-items/shared/\(token)", authenticated: false))
        let json = object as? [String: Any] ?? [:]
        let tasks = (json["tasks"] as? [[String: Any]] ?? []).map { task in
            SharedTasks.Item(description: task["description"] as? String ?? "", dueAt: BackendDate.parse(task["due_at"] as? String))
        }
        return SharedTasks(token: token, senderName: json["sender_name"] as? String, tasks: tasks)
    }

    /// `POST v1/action-items/accept`: copies the shared tasks into this account; returns how many.
    func acceptSharedActionItems(token: String) async throws -> Int {
        let body = try JSONSerialization.data(withJSONObject: ["token": token])
        let object = try await JSONSerialization.jsonObject(with: data(.post, "v1/action-items/accept", body: .json(body)))
        return (object as? [String: Any])?["count"] as? Int ?? 0
    }

    /// `PUT v1/task-integrations/{key}` `{connected: true}` and makes it the default app, as Flutter
    /// does for Apple Reminders: new tasks then come back as `sync_requested` for the phone to add.
    func connectTaskIntegration(_ key: String) async throws {
        let connected = try JSONSerialization.data(withJSONObject: ["connected": true])
        _ = try await data(.put, "v1/task-integrations/\(key)", body: .json(connected))
        let selected = try JSONSerialization.data(withJSONObject: ["app_key": key])
        _ = try await data(.put, "v1/task-integrations/default", body: .json(selected))
    }

    /// `GET v1/action-items/pending-sync?platform=apple_reminders`.
    func pendingReminderSync() async throws -> PendingTaskSync {
        let data = try await data(.get, "v1/action-items/pending-sync", query: [URLQueryItem(name: "platform", value: "apple_reminders")])
        let response = try decode(PendingSyncDTO.self, from: data)
        return PendingTaskSync(pendingExport: response.pendingExport.map(TaskMapper.map), synced: response.syncedItems.map(TaskMapper.map))
    }

    /// `PATCH v1/action-items/sync-batch` (at most 100 per call, so sent in chunks).
    func syncActionItems(_ updates: [TaskSyncUpdate]) async throws {
        for start in stride(from: 0, to: updates.count, by: 100) {
            let items = updates[start ..< min(start + 100, updates.count)].map(Self.syncItem)
            let body = try JSONSerialization.data(withJSONObject: ["items": items])
            _ = try await data(.patch, "v1/action-items/sync-batch", body: .json(body))
        }
    }

    private static func syncItem(_ update: TaskSyncUpdate) -> [String: Any] {
        var item: [String: Any] = ["id": update.id]
        if let description = update.description { item["description"] = description }
        if let completed = update.completed { item["completed"] = completed }
        if case let .set(due) = update.due {
            item["due_at"] = due.map { ISO8601DateFormatter().string(from: $0) as Any } ?? NSNull()
        }
        if let platform = update.exportPlatform {
            item["exported"] = true
            item["export_platform"] = platform
        }
        if let reminderID = update.appleReminderID { item["apple_reminder_id"] = reminderID }
        return item
    }
}

private struct PendingSyncDTO: Decodable {
    let pendingExport: [OmiAPI.ActionItemResponse]
    let syncedItems: [OmiAPI.ActionItemResponse]

    enum CodingKeys: String, CodingKey {
        case pendingExport = "pending_export"
        case syncedItems = "synced_items"
    }
}
