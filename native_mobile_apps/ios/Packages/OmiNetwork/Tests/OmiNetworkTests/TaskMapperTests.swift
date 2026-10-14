import Foundation
@testable import OmiNetwork
import Testing

struct TaskMapperTests {
    /// Captured from the local backend (`GET v1/action-items`), trimmed.
    static let json = """
    {"action_items": [{
      "id": "gB7zkCtrDRXSFfYB0x4l", "task_id": "gB7zkCtrDRXSFfYB0x4l",
      "description": "Send proof of income to landlord", "status": "active", "completed": false,
      "goal_id": null, "workstream_id": null, "owner": "user", "due_at": "2026-10-05T17:00:00Z",
      "source": "manual", "provenance": [], "priority": null, "sort_order": 0, "indent_level": 0,
      "created_at": "2026-10-06T17:07:56.374355Z", "updated_at": "2026-10-06T17:07:56.374356Z",
      "completed_at": null, "conversation_id": "demo-6", "is_locked": false
    }, {
      "id": "t2", "description": "Northwind sends term sheet draft", "completed": false,
      "owner": "other", "workstream_id": "ws-9", "created_at": "2026-10-06T17:07:56Z"
    }], "has_more": false}
    """

    @Test func mapsBackendTasks() throws {
        let response = try JSONDecoder().decode(OmiAPI.ActionItemsResponse.self, from: Data(Self.json.utf8))
        let tasks = response.actionItems.map(TaskMapper.map)
        #expect(tasks.count == 2)
        #expect(tasks[0].description == "Send proof of income to landlord")
        #expect(tasks[0].conversationID == "demo-6")
        #expect(tasks[0].dueAt != nil)
        #expect(tasks[0].owner == .user)
        #expect(tasks[1].owner == .other)
        #expect(tasks[1].workstreamID == "ws-9")
        // No status on the wire: completion decides.
        #expect(tasks[0].status == .active)
        #expect(tasks[1].status == .active)
        #expect(tasks[0].isOpen)
    }

    /// Merged, cancelled and prioritized rows keep what Home needs to hide and rank them.
    @Test func mapsCanonicalFields() throws {
        let json = """
        {"action_items": [{
          "id": "a", "description": "Research competitor pricing", "status": "superseded", "completed": false,
          "superseded_by": "b", "priority": "high", "due_confidence": 0.8, "goal_id": "g1",
          "provenance": [{"id": "conv-1", "kind": "conversation", "scope": "user"}]
        }, {
          "id": "c", "description": "Climb some rocks", "status": "cancelled", "completed": false
        }, {
          "id": "d", "description": "Old row", "completed": true
        }], "has_more": false}
        """
        let tasks = try JSONDecoder().decode(OmiAPI.ActionItemsResponse.self, from: Data(json.utf8)).actionItems.map(TaskMapper.map)
        #expect(tasks[0].status == .superseded)
        #expect(tasks[0].supersededBy == "b")
        #expect(tasks[0].priority == .high)
        #expect(tasks[0].dueConfidence == 0.8)
        #expect(tasks[0].goalID == "g1")
        #expect(tasks[0].provenance == [.init(kind: "conversation", id: "conv-1")])
        #expect(!tasks[0].isOpen)
        #expect(tasks[1].status == .cancelled)
        #expect(!tasks[1].isOpen)
        #expect(tasks[2].status == .completed)
    }
}
