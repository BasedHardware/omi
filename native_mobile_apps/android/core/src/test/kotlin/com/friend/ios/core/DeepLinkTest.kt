package com.friend.ios.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

/** Port of `DeepLinkTests.swift`: every link form the app accepts. */
class DeepLinkTest {
    @Test fun omiUrls() {
        assertEquals(DeepLink.Conversation("abc"), DeepLink.fromUrl("omi://conversation/abc"))
        assertEquals(DeepLink.Task("t1"), DeepLink.fromUrl("omi://task/t1"))
        assertEquals(DeepLink.Tasks, DeepLink.fromUrl("omi://tasks"))
        assertEquals(DeepLink.NewTask, DeepLink.fromUrl("omi://tasks/new"))
        assertEquals(DeepLink.SharedTasks("tok"), DeepLink.fromUrl("omi://tasks/tok"))
        assertEquals(DeepLink.Recap("2026-10-07"), DeepLink.fromUrl("omi://recap/2026-10-07"))
        assertEquals(DeepLink.Chat, DeepLink.fromUrl("omi://chat"))
        assertEquals(DeepLink.ChatDraft("what's up"), DeepLink.fromUrl("omi://chat/omi?q=what's%20up"))
        assertEquals(DeepLink.Memories, DeepLink.fromUrl("omi://memories"))
        assertEquals(DeepLink.Memory("m1"), DeepLink.fromUrl("omi://memory/m1"))
        assertEquals(DeepLink.Home, DeepLink.fromUrl("omi://home"))
        assertEquals(DeepLink.Device, DeepLink.fromUrl("omi://device"))
        assertEquals(DeepLink.Folder("f1"), DeepLink.fromUrl("omi://folder/f1"))
        assertEquals(DeepLink.Record, DeepLink.fromUrl("omi://record"))
        assertEquals(DeepLink.Account, DeepLink.fromUrl("omi://settings/account"))
        assertEquals(DeepLink.App("app1"), DeepLink.fromUrl("omi://apps/app1"))
        assertEquals(DeepLink.SharedTasks("tok"), DeepLink.fromUrl("https://h.omi.me/tasks/tok"))
    }

    @Test fun callbacksAndUnknownAreNotLinks() {
        assertNull(DeepLink.fromUrl("omi://auth/callback?code=1"))
        assertNull(DeepLink.fromUrl("omi://todoist/callback"))
        assertNull(DeepLink.fromUrl("omi://wrapped/2025"))
        assertNull(DeepLink.fromUrl("https://example.com/tasks/x"))
        assertNull(DeepLink.fromUrl("omi://conversation"))
        assertNull(DeepLink.fromUrl("omi://settings/privacy"))
    }

    @Test fun routes() {
        assertEquals(DeepLink.Conversation("abc"), DeepLink.fromRoute("/conversation/abc?share=1"))
        assertEquals(DeepLink.Recap("s1"), DeepLink.fromRoute("/daily-summary/s1"))
        assertEquals(DeepLink.Chat, DeepLink.fromRoute("/chat/omi"))
        assertEquals(DeepLink.Memories, DeepLink.fromRoute("/facts"))
        assertEquals(DeepLink.Tasks, DeepLink.fromRoute("action-items"))
        assertEquals(DeepLink.NewTask, DeepLink.fromRoute("/action-items/new"))
        assertEquals(DeepLink.Device, DeepLink.fromRoute("/settings/device"))
        assertNull(DeepLink.fromRoute("/wrapped/2025"))
    }

    @Test fun everyLinkRoundTripsThroughItsRouteAndUrl() {
        val links = listOf(
            DeepLink.Conversation("a b/c"), DeepLink.Task("t"), DeepLink.Tasks, DeepLink.SharedTasks("tok"),
            DeepLink.Recap("2026-10-07"), DeepLink.Chat, DeepLink.Memories, DeepLink.Home, DeepLink.Device,
            DeepLink.Memory("m"), DeepLink.Folder("f"), DeepLink.NewTask, DeepLink.Record,
            DeepLink.ChatDraft("Wie spät ist es? & mehr"), DeepLink.Account, DeepLink.App("x"),
        )
        for (link in links) {
            // The memory route opens the Memories tab; its id survives the round trip.
            assertEquals(link.toString(), link, DeepLink.fromRoute(link.route))
            assertEquals(link.toString(), link, DeepLink.fromUrl(link.url))
        }
    }

    @Test fun notifications() {
        assertEquals(DeepLink.Conversation("c"), DeepLink.fromNotification(mapOf("navigate_to" to "/conversation/c")))
        assertEquals(
            DeepLink.Task("t"),
            DeepLink.fromNotification(mapOf("notification_type" to "proactivity_v2", "target_kind" to "action_item", "target_id" to "t")),
        )
        assertEquals(
            DeepLink.Conversation("c"),
            DeepLink.fromNotification(mapOf("notification_type" to "proactivity_v2", "target_kind" to "conversation", "target_id" to "c")),
        )
        assertEquals(DeepLink.Chat, DeepLink.fromNotification(mapOf("notification_type" to "proactivity_v2", "navigate_to" to "/chat/mentor")))
        assertNull(DeepLink.fromNotification(mapOf("notification_type" to "proactivity_v2", "target_kind" to "memory", "target_id" to "m")))
        assertEquals(DeepLink.Device, DeepLink.fromNotification(mapOf("push_type" to "capture_recovery", "action" to "repair_device")))
        assertNull(DeepLink.fromNotification(mapOf("push_type" to "capture_recovery", "action" to "other")))
        assertEquals(DeepLink.Conversation("m"), DeepLink.fromNotification(mapOf("merged_conversation_id" to "m", "conversation_id" to "c")))
        assertEquals(DeepLink.Task("a"), DeepLink.fromNotification(mapOf("type" to "action_item_reminder", "action_item_id" to "a")))
        assertNull(DeepLink.fromNotification(mapOf("navigate_to" to "")))
        assertNull(DeepLink.fromNotification(emptyMap()))
    }

    @Test fun universalLinks() {
        assertEquals(DeepLink.Conversation("c"), DeepLink.fromUniversalLink("https://h.omi.me/conversations/c"))
        assertEquals(DeepLink.Recap("r"), DeepLink.fromUniversalLink("https://h.omi.me/recaps/r"))
        assertEquals(DeepLink.Memories, DeepLink.fromUniversalLink("https://h.omi.me/memories"))
        assertEquals(DeepLink.Memory("m"), DeepLink.fromUniversalLink("https://h.omi.me/memories/m"))
        assertEquals(DeepLink.Account, DeepLink.fromUniversalLink("https://h.omi.me/unlimited"))
        assertEquals(DeepLink.App("a"), DeepLink.fromUniversalLink("https://try.omi.me/apps/a"))
        assertEquals(DeepLink.SharedTasks("t"), DeepLink.fromUniversalLink("https://h.omi.me/tasks/t"))
        assertNull(DeepLink.fromUniversalLink("https://h.omi.me/wrapped"))
        assertNull(DeepLink.fromUniversalLink("https://omi.me/apps/a"))
        assertEquals(DeepLink.App("a"), DeepLink.fromAnyUrl("https://h.omi.me/apps/a"))
    }

    @Test fun quickActions() {
        assertEquals(QuickAction.MyOmi, QuickAction.fromShortcutType("connect_device"))
        assertEquals(DeepLink.Chat, QuickAction.fromShortcutType("ask_omi")?.link)
        assertEquals(DeepLink.NewTask, QuickAction.AddTask.link)
        assertEquals(DeepLink.Record, QuickAction.StartRecording.link)
        assertNull(QuickAction.fromShortcutType("nope"))
    }

    @Test fun taskReminders() {
        val now = Instant.parse("2026-10-08T10:00:00Z")
        assertEquals(
            TaskReminderChange.Schedule("a", "Call", Instant.parse("2026-10-08T14:00:00Z")),
            TaskReminderChange.fromNotification(
                mapOf("type" to "action_item_reminder", "action_item_id" to "a", "description" to "Call", "due_at" to "2026-10-08T15:00:00Z"), now,
            ),
        )
        // Due within the hour: only the old reminder goes.
        assertEquals(
            TaskReminderChange.Cancel(listOf("a")),
            TaskReminderChange.fromNotification(
                mapOf("type" to "action_item_update", "action_item_id" to "a", "description" to "Call", "due_at" to "2026-10-08T10:30:00Z"), now,
            ),
        )
        assertEquals(TaskReminderChange.Cancel(listOf("a")), TaskReminderChange.fromNotification(mapOf("type" to "action_item_delete", "action_item_id" to "a")))
        assertEquals(TaskReminderChange.Cancel(listOf("a", "b")), TaskReminderChange.fromNotification(mapOf("type" to "action_item_batch_delete", "ids" to "a,b")))
        assertNull(TaskReminderChange.fromNotification(mapOf("type" to "action_item_batch_delete", "ids" to "")))
        assertNull(TaskReminderChange.fromNotification(mapOf("type" to "other")))
    }
}
