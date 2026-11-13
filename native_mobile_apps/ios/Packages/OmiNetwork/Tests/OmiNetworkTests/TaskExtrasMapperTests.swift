import Foundation
@testable import OmiNetwork
import Testing

struct TaskExtrasMapperTests {
    /// Captured from the local backend (`GET v1/action-items/pending-sync` after a sync-batch), trimmed.
    static let synced = """
    {"id": "h02tHO2WvaXVxKLJf4mn", "description": "parity-tasks probe A", "status": "active", "completed": false,
     "owner": "user", "due_at": null, "sort_order": 1000, "indent_level": 1,
     "created_at": "2026-10-07T16:08:30.165874Z", "updated_at": "2026-10-07T16:09:02.120001Z",
     "exported": true, "export_date": null, "export_platform": "apple_reminders", "apple_reminder_id": "FAKE-REM-1"}
    """

    @Test func mapsSubtaskAndExportFields() throws {
        let dto = try JSONDecoder().decode(OmiAPI.ActionItemResponse.self, from: Data(Self.synced.utf8))
        let task = TaskMapper.map(dto)
        #expect(task.indentLevel == 1)
        #expect(task.sortOrder == 1000)
        #expect(task.exportPlatform == "apple_reminders")
        #expect(task.appleReminderID == "FAKE-REM-1")
        #expect(task.updatedAt != nil)
    }

    @Test func notExportedMeansNoPlatform() throws {
        let json = #"{"id": "t", "description": "x", "completed": false, "exported": false, "export_platform": "todoist"}"#
        let task = TaskMapper.map(try JSONDecoder().decode(OmiAPI.ActionItemResponse.self, from: Data(json.utf8)))
        #expect(task.exportPlatform == nil)
        #expect(task.indentLevel == 0)
    }

    /// `POST v1/goals` response from the local backend, trimmed.
    @Test func mapsNumericGoals() throws {
        let json = """
        {"id": "goal_f31b842c5c05", "goal_id": "goal_f31b842c5c05", "title": "parity probe goal", "status": "background",
         "metric": {"type": "numeric", "current": 2.0, "target": 10.0, "min": 0.0, "max": 10.0, "unit": null},
         "created_at": "2026-10-07T16:09:17.329300Z", "goal_type": "GoalType.numeric", "target_value": 10.0,
         "current_value": 2.0, "min_value": 0.0, "max_value": 10.0, "unit": null, "is_active": true}
        """
        let object = try #require(try JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        let goal = try #require(GoalMapper.map(object))
        #expect(goal.id == "goal_f31b842c5c05")
        #expect(goal.current == 2)
        #expect(goal.target == 10)
        #expect(goal.progress == 0.2)
        #expect(goal.createdAt != nil)
    }
}
