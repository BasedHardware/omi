import Foundation
@testable import OmiCore
import Testing

/// Payloads exactly as the backend builds them (`NotificationMessage.get_message_as_dict`,
/// `utils/notifications.py`, `utils/proactivity.push_payload`, `services/capture_wedge.py`).
struct DeepLinkPushTests {
    @Test func dailySummaryOpensItsRecap() {
        let payload: [AnyHashable: Any] = [
            "id": "msg-1", "created_at": "2026-10-07T20:00:00+00:00", "sender": "ai", "from_integration": "false",
            "type": "day_summary", "notification_type": "daily_summary", "text": "You shipped push.",
            "navigate_to": "/daily-summary/sum-42", "content_blocks": #"[{"type":"memory_review"}]"#,
        ]
        #expect(DeepLink(notification: payload) == .recap("sum-42"))
    }

    @Test func newMemoriesOpenMemories() {
        let payload: [AnyHashable: Any] = [
            "type": "text", "notification_type": "new_fact", "from_integration": "false", "navigate_to": "/facts",
        ]
        #expect(DeepLink(notification: payload) == .memories)
    }

    @Test func appAndMainChatMessagesOpenChat() {
        let app: [AnyHashable: Any] = [
            "notification_type": "plugin", "plugin_id": "app-1", "from_integration": "true", "navigate_to": "/chat/app-1",
        ]
        let main: [AnyHashable: Any] = ["notification_type": "plugin", "navigate_to": "/chat/omi"]
        #expect(DeepLink(notification: app) == .chat)
        #expect(DeepLink(notification: main) == .chat)
    }

    @Test func chatAnswerPushOpensChat() {
        let payload: [AnyHashable: Any] = [
            "push_type": "chat_answer", "title": "Omi says", "text": "Done.", "notification_type": "plugin",
            "navigate_to": "/chat/omi", "id": "msg-3",
        ]
        #expect(DeepLink(notification: payload) == .chat)
    }

    @Test func proactivityOpensItsTarget() {
        let conversation: [AnyHashable: Any] = [
            "notification_type": "proactivity_v2", "item_id": "i1", "target_kind": "conversation", "target_id": "c9",
        ]
        let task: [AnyHashable: Any] = [
            "notification_type": "proactivity_v2", "item_id": "i2", "target_kind": "action_item", "target_id": "t9",
        ]
        let mentor: [AnyHashable: Any] = [
            "notification_type": "proactivity_v2", "item_id": "i3", "target_kind": "conversation", "target_id": "c1",
            "navigate_to": "/chat/mentor",
        ]
        let unknown: [AnyHashable: Any] = [
            "notification_type": "proactivity_v2", "item_id": "i4", "target_kind": "recording", "target_id": "r1",
        ]
        #expect(DeepLink(notification: conversation) == .conversation(id: "c9"))
        #expect(DeepLink(notification: task) == .task(id: "t9"))
        #expect(DeepLink(notification: mentor) == .chat)
        #expect(DeepLink(notification: unknown) == nil)
    }

    @Test func importantConversationIgnoresTheShareFlag() {
        let payload: [AnyHashable: Any] = [
            "type": "important_conversation", "conversation_id": "c7", "navigate_to": "/conversation/c7?share=1",
        ]
        #expect(DeepLink(notification: payload) == .conversation(id: "c7"))
    }

    @Test func captureRecoveryOpensMyDevices() {
        #expect(DeepLink(notification: ["push_type": "capture_recovery", "action": "repair_device"]) == .device)
        #expect(DeepLink(notification: ["push_type": "capture_recovery"]) == nil)
    }

    @Test func mergeCompletedOpensTheMergedConversation() {
        let payload: [AnyHashable: Any] = [
            "type": "merge_completed", "merged_conversation_id": "c1", "removed_conversation_ids": "c2,c3",
        ]
        #expect(DeepLink(notification: payload) == .conversation(id: "c1"))
    }

    @Test func taskReminderAndAgentNotificationsOpenTheTask() {
        let reminder: [AnyHashable: Any] = ["type": "action_item_reminder", "action_item_id": "t1", "due_at": "2026-10-08T09:00:00Z"]
        #expect(DeepLink(notification: reminder) == .task(id: "t1"))
        // Local notifications (Omi finished, task reminders) carry the route form.
        #expect(DeepLink(notification: ["navigate_to": DeepLink.task(id: "t/2 x").route]) == .task(id: "t/2 x"))
        #expect(DeepLink(notification: ["navigate_to": "/action-items"]) == .tasks)
    }

    @Test func payloadsWithoutANativeScreenJustOpenTheApp() {
        #expect(DeepLink(notification: ["type": "wrapped_ready", "year": "2025", "navigate_to": "/wrapped/2025"]) == nil)
        #expect(DeepLink(notification: ["app_id": "a1", "type": "app_review_reply", "navigate_to": "/apps/a1"]) == .app(id: "a1"))
        #expect(DeepLink(notification: ["type": "fair_use", "action": "warning"]) == nil)
        #expect(DeepLink(notification: ["navigate_to": ""]) == nil)
        #expect(DeepLink(notification: [:]) == nil)
    }

    @Test func everyRouteRoundTrips() {
        let links: [DeepLink] = [
            .conversation(id: "c1"), .task(id: "t1"), .tasks, .recap("2026-10-07"), .chat, .memories, .home, .device,
            .sharedTasks(token: "abc123"),
        ]
        for link in links {
            #expect(DeepLink(route: link.route) == link)
        }
    }
}

struct DeepLinkURLTests {
    @Test func parsesTaskShareLinks() throws {
        #expect(try DeepLink(url: #require(URL(string: "omi://tasks/abc123"))) == .sharedTasks(token: "abc123"))
        #expect(try DeepLink(url: #require(URL(string: "https://h.omi.me/tasks/abc123"))) == .sharedTasks(token: "abc123"))
        #expect(try DeepLink(url: #require(URL(string: "omi://tasks"))) == .tasks)
        #expect(try DeepLink(url: #require(URL(string: "https://h.omi.me/conversations/x"))) == nil)
        #expect(try DeepLink(url: #require(URL(string: "https://example.com/tasks/abc123"))) == nil)
    }

    @Test func parsesOmiURLs() throws {
        #expect(try DeepLink(url: #require(URL(string: "omi://conversation/demo-1"))) == .conversation(id: "demo-1"))
        #expect(try DeepLink(url: #require(URL(string: "omi://task/t1"))) == .task(id: "t1"))
        #expect(try DeepLink(url: #require(URL(string: "omi://recap/2026-10-07"))) == .recap("2026-10-07"))
        #expect(try DeepLink(url: #require(URL(string: "omi://chat"))) == .chat)
        #expect(try DeepLink(url: #require(URL(string: "omi://memories"))) == .memories)
        #expect(try DeepLink(url: #require(URL(string: "omi://conversation/a%20b"))) == .conversation(id: "a b"))
    }

    @Test func rejectsCallbacksAndOtherSchemes() throws {
        #expect(try DeepLink(url: #require(URL(string: "omi://google_calendar/callback?success=true"))) == nil)
        #expect(try DeepLink(url: #require(URL(string: "omi://auth/callback?code=1"))) == nil)
        #expect(try DeepLink(url: #require(URL(string: "omi://conversation"))) == nil)
        #expect(try DeepLink(url: #require(URL(string: "https://omi.me/conversation/c1"))) == nil)
        #expect(try DeepLink(url: #require(URL(string: "com.googleusercontent.apps.1:/oauth2redirect"))) == nil)
    }
}

struct TaskReminderChangeTests {
    let now = Date(timeIntervalSince1970: 1_791_000_000)

    @Test func schedulesAnHourBeforeTheDueTime() {
        let due = now.addingTimeInterval(3 * 3600)
        let payload: [AnyHashable: Any] = [
            "type": "action_item_reminder", "action_item_id": "t1", "description": "Call Anna",
            "due_at": ISO8601DateFormatter().string(from: due),
        ]
        #expect(TaskReminderChange(notification: payload, now: now)
            == .schedule(taskID: "t1", description: "Call Anna", fireAt: due.addingTimeInterval(-3600)))
    }

    @Test func updateWithoutAFutureReminderCancels() {
        let payload: [AnyHashable: Any] = [
            "type": "action_item_update", "action_item_id": "t1", "description": "Call Anna",
            "due_at": ISO8601DateFormatter().string(from: now.addingTimeInterval(1800)),
        ]
        #expect(TaskReminderChange(notification: payload, now: now) == .cancel(taskIDs: ["t1"]))
    }

    @Test func deletionsCancel() {
        #expect(TaskReminderChange(notification: ["type": "action_item_delete", "action_item_id": "t1"]) == .cancel(taskIDs: ["t1"]))
        #expect(TaskReminderChange(notification: ["type": "action_item_batch_delete", "ids": "t1,t2,"]) == .cancel(taskIDs: ["t1", "t2"]))
        #expect(TaskReminderChange(notification: ["type": "action_item_batch_delete", "ids": ""]) == nil)
    }

    @Test func ignoresOtherPayloads() {
        #expect(TaskReminderChange(notification: ["type": "apple_reminders_sync", "items": "[]"]) == nil)
        #expect(TaskReminderChange(notification: ["notification_type": "daily_summary"]) == nil)
    }
}
