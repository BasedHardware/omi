package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.SharedTasks
import com.friend.ios.core.models.TaskLayout
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

/**
 * Port of `APIClient+TaskExtras.swift`: bulk delete, subtasks, export to task apps and share links
 * (contracts from `backend/routers/action_items.py` and `task_integrations.py`). The Apple Reminders
 * sync calls have no Android counterpart.
 */
interface TaskExtrasAPI {
    /** `POST v1/action-items/batch-delete`; returns the ids the backend deleted. */
    suspend fun deleteActionItems(ids: List<String>): List<String>

    /** `PATCH v1/action-items/batch`: order and indent level (0...3) of many rows at once. */
    suspend fun setTaskLayout(entries: List<TaskLayout>)

    /**
     * `POST v1/task-integrations/{app}/tasks`: the backend creates it with the stored OAuth tokens.
     * Throws when the app refuses (`success: false`), so the task is not marked exported.
     */
    suspend fun createIntegrationTask(app: String, title: String, dueAt: Instant?)

    /** `PATCH v1/action-items/{id}` with `exported`, `export_date`, `export_platform` (and the reminder id). */
    suspend fun markActionItemExported(id: String, platform: String, appleReminderID: String?)

    /** `POST v1/action-items/share`: the public link (`https://h.omi.me/tasks/<token>`). */
    suspend fun shareActionItems(ids: List<String>): String

    /** `GET v1/action-items/shared/{token}` (public): who shared what. */
    suspend fun sharedActionItems(token: String): SharedTasks

    /** `POST v1/action-items/accept`: copies the shared tasks into this account; returns how many. */
    suspend fun acceptSharedActionItems(token: String): Int
}

internal class TaskExtrasEndpoints(private val http: HttpCore) : TaskExtrasAPI {
    override suspend fun deleteActionItems(ids: List<String>): List<String> {
        val body = buildJsonObject { put("ids", buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } }) }
        val json = JsonAccess.obj(http.data(Method.POST, "v1/action-items/batch-delete", body = Body.Json(body.toString())))
        return if (json.array("deleted_ids") != null) json.strings("deleted_ids") else ids
    }

    override suspend fun setTaskLayout(entries: List<TaskLayout>) {
        val body = buildJsonObject {
            put(
                "items",
                buildJsonArray {
                    entries.forEach { entry ->
                        add(
                            buildJsonObject {
                                put("id", entry.id)
                                entry.sortOrder?.let { put("sort_order", it) }
                                entry.indentLevel?.let { put("indent_level", it) }
                            },
                        )
                    }
                },
            )
        }
        http.data(Method.PATCH, "v1/action-items/batch", body = Body.Json(body.toString()))
    }

    override suspend fun createIntegrationTask(app: String, title: String, dueAt: Instant?) {
        val body = buildJsonObject {
            put("title", title)
            put("description", "From Omi")
            dueAt?.let { put("due_date", iso(it)) }
        }
        val json = JsonAccess.obj(http.data(Method.POST, "v1/task-integrations/$app/tasks", body = Body.Json(body.toString())))
        if (json.bool("success") != true) throw APIError.Http(502, json.string("error") ?: "export failed")
    }

    override suspend fun markActionItemExported(id: String, platform: String, appleReminderID: String?) {
        val body = buildJsonObject {
            put("exported", true)
            put("export_date", iso(Instant.now()))
            put("export_platform", platform)
            appleReminderID?.let { put("apple_reminder_id", it) }
        }
        http.data(Method.PATCH, "v1/action-items/$id", body = Body.Json(body.toString()))
    }

    override suspend fun shareActionItems(ids: List<String>): String {
        val body = buildJsonObject { put("task_ids", buildJsonArray { ids.forEach { add(JsonPrimitive(it)) } }) }
        return JsonAccess.obj(http.data(Method.POST, "v1/action-items/share", body = Body.Json(body.toString()))).string("url")
            ?: throw APIError.Decoding("no share url")
    }

    override suspend fun sharedActionItems(token: String): SharedTasks {
        val json = JsonAccess.obj(http.data(Method.GET, "v1/action-items/shared/$token", authenticated = false))
        val tasks = json.objects("tasks").map { SharedTasks.Item(it.string("description") ?: "", BackendDate.parse(it.string("due_at"))) }
        return SharedTasks(token, json.string("sender_name"), tasks)
    }

    override suspend fun acceptSharedActionItems(token: String): Int {
        val body = buildJsonObject { put("token", token) }
        return JsonAccess.obj(http.data(Method.POST, "v1/action-items/accept", body = Body.Json(body.toString()))).int("count") ?: 0
    }

    /** `ISO8601DateFormatter().string(from:)`: UTC, no fractions. */
    private fun iso(date: Instant): String = DateTimeFormatter.ISO_INSTANT.format(date.truncatedTo(ChronoUnit.SECONDS))
}
