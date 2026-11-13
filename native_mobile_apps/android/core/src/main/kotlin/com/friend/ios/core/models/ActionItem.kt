package com.friend.ios.core.models

import java.time.Instant

/** Port of `ActionItem.swift`: a task (the backend still calls them action items). Mirrors `ActionItemResponse`. */
data class ActionItem(
    val id: String,
    val description: String,
    val isCompleted: Boolean,
    val dueAt: Instant?,
    val conversationID: String?,
    val owner: Owner,
    /** Set when an agent workstream works on this task (PLAN.md §4.4, wired in P4). */
    val workstreamID: String?,
    val createdAt: Instant?,
    /**
     * Subtask depth 0...3: a row is the child of the nearest row above it with a smaller level
     * (`indent_level`, as in Flutter's Tasks page).
     */
    val indentLevel: Int = 0,
    /** Manual order inside a bucket; 0 means "not placed by hand" (`sort_order`). */
    val sortOrder: Int = 0,
    /** The task app it was sent to (`todoist`, `apple_reminders`, ...); null when not exported. */
    val exportPlatform: String? = null,
    /** The `EKReminder.calendarItemIdentifier` it is linked to (Apple Reminders sync). */
    val appleReminderID: String? = null,
    val updatedAt: Instant? = null,
    val status: Status = if (isCompleted) Status.Completed else Status.Active,
    /** The task this one was merged into (`status == .superseded`). */
    val supersededBy: String? = null,
    val priority: Priority? = null,
    /** How sure the backend is about `dueAt` (0...1); null when set by hand. */
    val dueConfidence: Double? = null,
    val provenance: List<Evidence> = emptyList(),
    val goalID: String? = null,
) {
    /** Who has to do it. `Other` means someone else committed to it ("waiting on"). */
    enum class Owner(val rawValue: String) { User("user"), Other("other"), Unknown("unknown") }

    /**
     * The backend's canonical state. `Cancelled` ("Not a task") and `Superseded` (merged into
     * `supersededBy`) are gone for the user, though the list still returns them.
     */
    enum class Status(val rawValue: String) { Active("active"), Completed("completed"), Cancelled("cancelled"), Superseded("superseded") }

    enum class Priority(val rawValue: String) {
        High("high"), Medium("medium"), Low("low");

        companion object {
            fun from(raw: String?): Priority? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    /** Where the task was heard (`EvidenceRef`: kind `conversation`, `chat_message` ...). */
    data class Evidence(val kind: String, val id: String)

    /** Ticking a task off (or back on) moves `status` with it, as the backend does (Swift `didSet`). */
    fun withCompleted(completed: Boolean): ActionItem = copy(
        isCompleted = completed,
        status = if (status == Status.Active || status == Status.Completed) (if (completed) Status.Completed else Status.Active) else status,
    )

    val isExported: Boolean get() = exportPlatform != null

    /** Still something to do: not completed, not cancelled, not merged into another task. */
    val isOpen: Boolean get() = !isCompleted && status == Status.Active
}
