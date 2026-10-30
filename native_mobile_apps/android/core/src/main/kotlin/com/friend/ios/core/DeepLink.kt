package com.friend.ios.core

import java.net.URI
import java.net.URLDecoder
import java.net.URLEncoder
import java.time.Instant

/**
 * Port of `DeepLink.swift`: a place in the app a notification or an `omi://` link opens. Parsed
 * from the backend's FCM data (`navigate_to` routes such as `/conversation/<id>`, plus the typed
 * payloads that carry no route) and from `omi://conversation/<id>`, `omi://task/<id>`,
 * `omi://recap/<id or yyyy-MM-dd>`, `omi://chat`, plus task share links (`omi://tasks/<token>`,
 * `https://h.omi.me/tasks/<token>`).
 */
sealed interface DeepLink {
    data class Conversation(val id: String) : DeepLink
    /** A task; when Omi worked on it, its run (Omi's finished work). */
    data class Task(val id: String) : DeepLink
    data object Tasks : DeepLink
    /** Tasks someone shared by link; opens the sheet to add them (Flutter `AcceptSharedTasksSheet`). */
    data class SharedTasks(val token: String) : DeepLink
    /** A daily recap by summary id or local date (`yyyy-MM-dd`). */
    data class Recap(val key: String) : DeepLink
    data object Chat : DeepLink
    data object Memories : DeepLink
    data object Home : DeepLink
    /** My Devices (the backend's capture-recovery nudge). */
    data object Device : DeepLink
    /** One memory: the Memories tab. */
    data class Memory(val id: String) : DeepLink
    /** A conversation folder: Home showing only that folder. */
    data class Folder(val id: String) : DeepLink
    /** The Tasks tab with a new task being written (the "Add task" quick action). */
    data object NewTask : DeepLink
    /** Starts recording with the phone (the "Start recording" quick action). */
    data object Record : DeepLink
    /** The chat with a question waiting in the composer. */
    data class ChatDraft(val text: String) : DeepLink
    /** Settings > Account, where the plans are (`h.omi.me/unlimited`). */
    data object Account : DeepLink
    /** One app's page (`h.omi.me/apps/<id>`, Flutter `AppDetailPage`). */
    data class App(val id: String) : DeepLink

    /** The route form (`/task/<id>`) stored in local notifications so a tap parses like a push. */
    val route: String
        get() = when (this) {
            is Conversation -> "/conversation/${encode(id)}"
            is Task -> "/task/${encode(id)}"
            Tasks -> "/action-items"
            is SharedTasks -> "/tasks/${encode(token)}"
            is Recap -> "/daily-summary/${encode(key)}"
            Chat -> "/chat/omi"
            Memories -> "/memories"
            Home -> "/conversations"
            Device -> "/settings/device"
            is Memory -> "/memory/${encode(id)}"
            is Folder -> "/folder/${encode(id)}"
            NewTask -> "/tasks/new"
            Record -> "/record"
            is ChatDraft -> "/chat/omi?q=${encode(text)}"
            Account -> "/settings/account"
            is App -> "/apps/${encode(id)}"
        }

    /** The `omi://` form (`omi://conversation/<id>`): shortcuts and widgets carry it. */
    val url: String get() = "omi:/$route"

    companion object {
        /** Hosts in the app's App Links (`h.omi.me`, `try.omi.me`). */
        val universalLinkHosts = setOf("h.omi.me", "try.omi.me")

        /**
         * From a notification's data (FCM data keys arrive at the top level), mirroring Flutter's
         * `NotificationUtil.handleFcmDataTap` and `ProactivityPush`. Null: just open the app.
         */
        fun fromNotification(data: Map<String, String?>): DeepLink? {
            fun value(key: String) = data[key]?.takeIf { it.isNotEmpty() }
            // Proactivity v2 carries only identity; mentor items keep their chat route.
            if (value("notification_type") == "proactivity_v2") {
                if (value("navigate_to") == "/chat/mentor") return Chat
                val target = value("target_id") ?: return null
                return when (value("target_kind")) {
                    "conversation" -> Conversation(target)
                    "action_item" -> Task(target)
                    else -> null
                }
            }
            if (value("push_type") == "capture_recovery") {
                return if (value("action") == "repair_device") Device else null
            }
            value("navigate_to")?.let { return fromRoute(it) }
            // Typed payloads without a route.
            val id = value("merged_conversation_id") ?: value("conversation_id")
            if (id != null) return Conversation(id)
            if (value("type")?.startsWith("action_item") == true) value("action_item_id")?.let { return Task(it) }
            return null
        }

        /** From an `omi://` URL (or an h.omi.me task share). OAuth callbacks (`omi://<key>/callback`) are not links. */
        fun fromUrl(url: String): DeepLink? {
            val uri = runCatching { URI(url) }.getOrNull() ?: return null
            val scheme = uri.scheme?.lowercase()
            if ((scheme == "https" || scheme == "http") && uri.host?.lowercase() == "h.omi.me") {
                val segments = pathSegments(uri.rawPath)
                if (segments.size != 2 || segments[0] != "tasks" || segments[1].isEmpty()) return null
                return SharedTasks(segments[1])
            }
            if (scheme != "omi") return null
            val segments = pathSegments(uri.rawPath).toMutableList()
            uri.host?.takeIf { it.isNotEmpty() }?.let { segments.add(0, it) }
            if (segments.lastOrNull() == "callback") return null
            return fromSegments(segments, query(uri.rawQuery))
        }

        /** From a backend route (`/conversation/abc?share=1`, `/daily-summary/<id>`, `/chat/<app>`, `/facts`). */
        fun fromRoute(route: String): DeepLink? {
            val path = if (route.startsWith("/")) route else "/$route"
            val uri = runCatching { URI(path) }.getOrNull() ?: return null
            return fromSegments(pathSegments(uri.rawPath), query(uri.rawQuery))
        }

        /**
         * From `https://h.omi.me/...` (`DeepLink+System.swift`): the share pages Omi builds open the
         * same thing in the app, as Flutter's `AppShell.openAppLink` does. `/wrapped` and anything
         * else is null: the app just opens.
         */
        fun fromUniversalLink(url: String): DeepLink? {
            val uri = runCatching { URI(url) }.getOrNull() ?: return null
            val scheme = uri.scheme?.lowercase()
            if (scheme != "https" && scheme != "http") return null
            if (uri.host?.lowercase() !in universalLinkHosts) return null
            val segments = pathSegments(uri.rawPath)
            val id = segments.getOrNull(1)?.takeIf { it.isNotEmpty() }
            return when (segments.firstOrNull()?.lowercase()) {
                "conversations", "conversation" -> id?.let { Conversation(it) }
                "recaps", "daily-summary" -> id?.let { Recap(it) }
                "memories" -> id?.let { Memory(it) } ?: Memories
                "unlimited" -> Account
                "apps" -> id?.let { App(it) }
                "tasks" -> id?.let { SharedTasks(it) }
                else -> null
            }
        }

        /** Any link the system hands the app: `omi://` first, then App Links. */
        fun fromAnyUrl(url: String): DeepLink? = fromUrl(url) ?: fromUniversalLink(url)

        private fun fromSegments(segments: List<String>, query: Map<String, String>): DeepLink? {
            val alias = segments.firstOrNull()?.lowercase() ?: return null
            val id = segments.getOrNull(1)?.takeIf { it.isNotEmpty() }
            return when (alias) {
                "conversation" -> id?.let { Conversation(it) }
                "conversations", "home" -> Home
                "task" -> id?.let { Task(it) }
                "tasks" -> if (id == "new") NewTask else id?.let { SharedTasks(it) } ?: Tasks
                "action-items" -> if (id == "new") NewTask else Tasks
                "daily-summary", "recap" -> id?.let { Recap(it) }
                "chat" -> query["q"]?.trim().orEmpty().let { if (it.isEmpty()) Chat else ChatDraft(it) }
                "memory" -> id?.let { Memory(it) } ?: Memories
                "facts", "memories" -> Memories
                "folder" -> id?.let { Folder(it) }
                "record" -> Record
                "device" -> Device
                "settings" -> when (id) {
                    "device" -> Device
                    "account" -> Account
                    else -> null
                }
                "apps", "app" -> id?.let { App(it) }
                // `/wrapped/2025` (Wrapped is going away) and anything unknown: the app just opens.
                else -> null
            }
        }

        private fun pathSegments(rawPath: String?): List<String> =
            rawPath.orEmpty().split("/").filter { it.isNotEmpty() }.map { decode(it) }

        private fun query(rawQuery: String?): Map<String, String> =
            rawQuery.orEmpty().split("&").filter { it.isNotEmpty() }.associate { pair ->
                val parts = pair.split("=", limit = 2)
                decode(parts[0]) to decode(parts.getOrElse(1) { "" })
            }

        private fun decode(value: String): String = runCatching { URLDecoder.decode(value.replace("+", "%2B"), "UTF-8") }.getOrDefault(value)

        /** RFC 3986 unreserved characters stay; everything else is percent-encoded. */
        internal fun encode(value: String): String = URLEncoder.encode(value, "UTF-8").replace("+", "%20").replace("*", "%2A").replace("%7E", "~")
    }
}

/**
 * What a background action-item push asks for: the backend schedules task reminders through
 * data-only messages (`action_item_reminder` / `_update` / `_delete` / `_batch_delete`), as in
 * Flutter's `ActionItemNotificationHandler`. The reminder fires an hour before the due time.
 */
sealed interface TaskReminderChange {
    data class Schedule(val taskID: String, val description: String, val fireAt: Instant) : TaskReminderChange
    data class Cancel(val taskIDs: List<String>) : TaskReminderChange

    companion object {
        const val LEAD_SECONDS: Long = 60 * 60

        /** Null for any other payload. A reminder whose time has passed only cancels the old one. */
        fun fromNotification(data: Map<String, String?>, now: Instant = Instant.now()): TaskReminderChange? {
            fun value(key: String) = data[key]?.takeIf { it.isNotEmpty() }
            return when (value("type")) {
                "action_item_reminder", "action_item_update" -> {
                    val id = value("action_item_id") ?: return null
                    val description = value("description")
                    val due = BackendDate.parse(value("due_at"))
                    val fireAt = due?.minusSeconds(LEAD_SECONDS)
                    if (description == null || fireAt == null || !fireAt.isAfter(now)) Cancel(listOf(id)) else Schedule(id, description, fireAt)
                }
                "action_item_delete" -> value("action_item_id")?.let { Cancel(listOf(it)) }
                "action_item_batch_delete" -> {
                    val ids = value("ids").orEmpty().split(",").filter { it.isNotEmpty() }
                    if (ids.isEmpty()) null else Cancel(ids)
                }
                else -> null
            }
        }
    }
}

/**
 * The launcher shortcuts (long press on the icon), as in Flutter's `quick_actions_service`
 * (`DeepLink+System.swift`). The ids are Flutter's shortcut types.
 */
enum class QuickAction(val rawValue: String) {
    AskOmi("ask_omi"),
    AddTask("add_task"),
    StartRecording("start_recording"),
    MyOmi("device_settings");

    val link: DeepLink
        get() = when (this) {
            AskOmi -> DeepLink.Chat
            AddTask -> DeepLink.NewTask
            StartRecording -> DeepLink.Record
            MyOmi -> DeepLink.Device
        }

    val systemImage: String
        get() = when (this) {
            AskOmi -> "bubble.left.and.text.bubble.right"
            AddTask -> "checklist"
            StartRecording -> "waveform"
            MyOmi -> "dot.radiowaves.left.and.right"
        }

    companion object {
        /** Top to bottom in the menu. */
        val menuOrder = listOf(AddTask, AskOmi, StartRecording, MyOmi)

        /** Flutter's "Connect device" item opens the same place as "Device settings". */
        fun fromShortcutType(type: String): QuickAction? =
            if (type == "connect_device") MyOmi else entries.firstOrNull { it.rawValue == type }
    }
}
