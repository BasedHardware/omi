package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.ActionItem
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.generated.OmiAPI
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.UUID

/**
 * Port of `APIClient+Tasks.swift`, the task call of `APIClient+Edits.swift` and
 * `APIClient+TaskAppSettings.swift` (contracts: `backend/routers/action_items.py`,
 * `task_integrations.py`). `APIClient+TaskExtras.swift` (bulk delete, layout, export, sharing) is
 * in `TaskExtras.kt`; its Apple Reminders sync is iOS only (EventKit), so Android has no such calls.
 */
interface TasksAPI {
    /** `GET v1/action-items` (open and completed; the store splits them). Offset paging, at most 500 per page. */
    suspend fun actionItems(limit: Int, offset: Int): List<ActionItem>

    /** `PATCH v1/action-items/{id}` with only the completion flag. */
    suspend fun setActionItem(id: String, completed: Boolean)

    /** `PATCH v1/action-items/{id}` with new text and due date; null clears the due date (`clear_due_at`). */
    suspend fun updateActionItem(id: String, description: String, dueAt: Instant?): ActionItem

    /**
     * `PATCH v1/action-items/{id}` with a new canonical status: `cancelled` ("Not a task", the
     * learning signal), `superseded` with the task it was merged into, `completed`. The backend
     * derives `completed` from it.
     */
    suspend fun setActionItemStatus(id: String, status: ActionItem.Status, supersededBy: String?)

    /** `DELETE v1/action-items/{id}` (204, no body). */
    suspend fun deleteActionItem(id: String)

    /** `POST v1/action-items`. */
    suspend fun createActionItem(description: String, dueAt: Instant?): ActionItem

    /** The choices of one level ([parent] is the selected id of the level above). */
    suspend fun taskAppOptions(level: TaskAppLevel, parent: String?): List<TaskAppOption>

    /** `PUT v1/task-integrations/{app}`: merges the selection; a null value clears that field. */
    suspend fun saveTaskAppSelection(app: String, selection: Map<TaskAppLevel, TaskAppOption?>)

    /** `GET v1/task-integrations/default`: the app new tasks are exported to (null when none). */
    suspend fun defaultTaskApp(): String?

    /** `PUT v1/task-integrations/default`. */
    suspend fun setDefaultTaskApp(app: String)
}

/**
 * Where a task app files new tasks: one level of the Asana (workspace, project) or ClickUp (team,
 * space, list) hierarchy (backend `routers/task_integrations.py`).
 */
enum class TaskAppLevel(val rawValue: String) {
    AsanaWorkspace("asanaWorkspace"),
    AsanaProject("asanaProject"),
    ClickupTeam("clickupTeam"),
    ClickupSpace("clickupSpace"),
    ClickupList("clickupList");

    /** The path that lists this level's choices under the parent's id. */
    fun path(parent: String?): String? = when (this) {
        AsanaWorkspace -> "v1/task-integrations/asana/workspaces"
        AsanaProject -> parent?.let { "v1/task-integrations/asana/projects/$it" }
        ClickupTeam -> "v1/task-integrations/clickup/teams"
        ClickupSpace -> parent?.let { "v1/task-integrations/clickup/spaces/$it" }
        ClickupList -> parent?.let { "v1/task-integrations/clickup/lists/$it" }
    }

    /** The response's array key and the item's id key. */
    val keys: Pair<String, String>
        get() = when (this) {
            AsanaWorkspace -> "workspaces" to "gid"
            AsanaProject -> "projects" to "gid"
            ClickupTeam -> "teams" to "id"
            ClickupSpace -> "spaces" to "id"
            ClickupList -> "lists" to "id"
        }

    /** The saved fields (`TaskIntegrationData`): id and name. */
    val fields: Pair<String, String>
        get() = when (this) {
            AsanaWorkspace -> "workspace_gid" to "workspace_name"
            AsanaProject -> "project_gid" to "project_name"
            ClickupTeam -> "team_id" to "team_name"
            ClickupSpace -> "space_id" to "space_name"
            ClickupList -> "list_id" to "list_name"
        }

    companion object {
        fun levels(app: String): List<TaskAppLevel> = when (app) {
            "asana" -> listOf(AsanaWorkspace, AsanaProject)
            "clickup" -> listOf(ClickupTeam, ClickupSpace, ClickupList)
            else -> emptyList()
        }

        fun from(rawValue: String): TaskAppLevel? = entries.firstOrNull { it.rawValue == rawValue }
    }
}

/** One place in a task app (a workspace, a project, a list ...). */
data class TaskAppOption(val id: String, val name: String)

internal class TasksEndpoints(private val http: HttpCore) : TasksAPI {
    override suspend fun actionItems(limit: Int, offset: Int): List<ActionItem> {
        val text = http.data(Method.GET, "v1/action-items", query = listOf("limit" to "$limit", "offset" to "$offset"))
        return http.decode(OmiAPI.ActionItemsResponse.serializer(), text).actionItems.map(TaskMapper::map)
    }

    override suspend fun setActionItem(id: String, completed: Boolean) {
        http.data(Method.PATCH, "v1/action-items/$id", body = Body.Json(buildJsonObject { put("completed", completed) }.toString()))
    }

    override suspend fun updateActionItem(id: String, description: String, dueAt: Instant?): ActionItem {
        val body = buildJsonObject {
            put("description", description)
            if (dueAt != null) put("due_at", iso(dueAt)) else put("clear_due_at", true)
        }
        val text = http.data(Method.PATCH, "v1/action-items/$id", body = Body.Json(body.toString()))
        return TaskMapper.map(http.decode(OmiAPI.ActionItemResponse.serializer(), text))
    }

    override suspend fun setActionItemStatus(id: String, status: ActionItem.Status, supersededBy: String?) {
        val body = buildJsonObject {
            put("status", status.rawValue)
            if (supersededBy != null) put("superseded_by", supersededBy)
        }
        http.data(Method.PATCH, "v1/action-items/$id", body = Body.Json(body.toString()))
    }

    override suspend fun deleteActionItem(id: String) {
        http.data(Method.DELETE, "v1/action-items/$id")
    }

    override suspend fun createActionItem(description: String, dueAt: Instant?): ActionItem {
        val body = buildJsonObject {
            put("description", description)
            if (dueAt != null) put("due_at", iso(dueAt))
        }
        val text = http.data(
            Method.POST, "v1/action-items", body = Body.Json(body.toString()), headers = mapOf("Idempotency-Key" to UUID.randomUUID().toString()),
        )
        return TaskMapper.map(http.decode(OmiAPI.ActionItemResponse.serializer(), text))
    }

    override suspend fun taskAppOptions(level: TaskAppLevel, parent: String?): List<TaskAppOption> {
        val path = level.path(parent) ?: return emptyList()
        val (list, idKey) = level.keys
        return JsonAccess.obj(http.data(Method.GET, path)).objects(list).mapNotNull { item ->
            val id = item.string(idKey) ?: return@mapNotNull null
            TaskAppOption(id, item.string("name") ?: id)
        }
    }

    override suspend fun saveTaskAppSelection(app: String, selection: Map<TaskAppLevel, TaskAppOption?>) {
        val body = buildJsonObject {
            put("connected", true)
            for ((level, option) in selection) {
                put(level.fields.first, option?.id)
                put(level.fields.second, option?.name)
            }
        }
        http.data(Method.PUT, "v1/task-integrations/$app", body = Body.Json(body.toString()))
    }

    override suspend fun defaultTaskApp(): String? =
        JsonAccess.obj(http.data(Method.GET, "v1/task-integrations/default")).string("default_app")?.ifEmpty { null }

    override suspend fun setDefaultTaskApp(app: String) {
        http.data(Method.PUT, "v1/task-integrations/default", body = Body.Json(buildJsonObject { put("app_key", app) }.toString()))
    }

    /** `ISO8601DateFormatter().string(from:)`: UTC, no fractions. */
    private fun iso(date: Instant): String = DateTimeFormatter.ISO_INSTANT.format(date.truncatedTo(java.time.temporal.ChronoUnit.SECONDS))
}

/** `TaskMapper`. */
internal object TaskMapper {
    fun map(dto: OmiAPI.ActionItemResponse): ActionItem = ActionItem(
        id = dto.id,
        description = dto.description_,
        isCompleted = dto.completed,
        dueAt = BackendDate.parse(dto.dueAt),
        conversationID = dto.conversationId,
        owner = owner(dto.owner),
        workstreamID = dto.workstreamId,
        createdAt = BackendDate.parse(dto.createdAt),
        indentLevel = (dto.indentLevel ?: 0).coerceIn(0, 3),
        sortOrder = dto.sortOrder ?: 0,
        exportPlatform = if (dto.exported == true) (dto.exportPlatform ?: "unknown") else null,
        appleReminderID = dto.appleReminderId,
        updatedAt = BackendDate.parse(dto.updatedAt),
        status = status(dto.status, dto.completed),
        supersededBy = dto.supersededBy,
        priority = dto.priority?.let { ActionItem.Priority.from(it.rawValue) },
        dueConfidence = dto.dueConfidence,
        provenance = dto.provenance.orEmpty().map { ActionItem.Evidence(it.kind.rawValue, it.id) },
        goalID = dto.goalId,
    )

    /** Older rows have no status: completion decides, as on the backend. */
    fun status(status: OmiAPI.TaskStatus?, completed: Boolean): ActionItem.Status = when (status) {
        OmiAPI.TaskStatus.active -> ActionItem.Status.Active
        OmiAPI.TaskStatus.completed -> ActionItem.Status.Completed
        OmiAPI.TaskStatus.cancelled -> ActionItem.Status.Cancelled
        OmiAPI.TaskStatus.superseded -> ActionItem.Status.Superseded
        OmiAPI.TaskStatus._unknown, null -> if (completed) ActionItem.Status.Completed else ActionItem.Status.Active
    }

    fun owner(owner: OmiAPI.TaskOwner?): ActionItem.Owner = when (owner) {
        OmiAPI.TaskOwner.user, null -> ActionItem.Owner.User
        OmiAPI.TaskOwner.other -> ActionItem.Owner.Other
        OmiAPI.TaskOwner.unknown, OmiAPI.TaskOwner._unknown -> ActionItem.Owner.Unknown
    }
}
