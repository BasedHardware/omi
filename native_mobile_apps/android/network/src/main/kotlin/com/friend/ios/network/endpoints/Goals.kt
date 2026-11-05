package com.friend.ios.network.endpoints

import com.friend.ios.core.BackendDate
import com.friend.ios.core.models.Goal
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/** Port of `APIClient+Goals.swift`: numeric goals, as Flutter's goals widget uses them (`backend/routers/goals.py`). */
interface GoalsAPI {
    /** `GET v1/goals/all`: the active goals. */
    suspend fun goals(): List<Goal>

    /** `POST v1/goals` with the released numeric fields (`goal_type: numeric`, min 0). */
    suspend fun createGoal(title: String, current: Double, target: Double): Goal

    /** `PATCH v1/goals/{id}`: title, current and target. */
    suspend fun updateGoal(id: String, title: String, current: Double, target: Double): Goal

    /** `PATCH v1/goals/{id}/progress?current_value=`. */
    suspend fun setGoalProgress(id: String, current: Double): Goal

    /** `DELETE v1/goals/{id}` (the backend abandons it and keeps its links). */
    suspend fun deleteGoal(id: String)
}

internal class GoalsEndpoints(private val http: HttpCore) : GoalsAPI {
    override suspend fun goals(): List<Goal> {
        val array = http.decode(JsonElement.serializer(), http.data(Method.GET, "v1/goals/all")) as? JsonArray
        return array.orEmpty().mapNotNull { (it as? JsonObject)?.let(GoalMapper::map) }
    }

    override suspend fun createGoal(title: String, current: Double, target: Double): Goal = goal(
        Method.POST, "v1/goals",
        buildJsonObject {
            put("title", title)
            put("goal_type", "numeric")
            put("current_value", current)
            put("target_value", target)
            put("min_value", 0)
            put("max_value", maxOf(target, 0.0))
        },
    )

    override suspend fun updateGoal(id: String, title: String, current: Double, target: Double): Goal = goal(
        Method.PATCH, "v1/goals/$id",
        buildJsonObject {
            put("title", title)
            put("current_value", current)
            put("target_value", target)
        },
    )

    override suspend fun setGoalProgress(id: String, current: Double): Goal {
        val text = http.data(Method.PATCH, "v1/goals/$id/progress", query = listOf("current_value" to "$current"))
        return (http.decode(JsonElement.serializer(), text) as? JsonObject)?.let(GoalMapper::map) ?: throw APIError.Decoding("goal")
    }

    override suspend fun deleteGoal(id: String) {
        http.data(Method.DELETE, "v1/goals/$id")
    }

    private suspend fun goal(method: Method, path: String, fields: JsonObject): Goal {
        val text = http.data(method, path, body = Body.Json(fields.toString()))
        return (http.decode(JsonElement.serializer(), text) as? JsonObject)?.let(GoalMapper::map) ?: throw APIError.Decoding("goal")
    }
}

/** `GoalMapper`. */
internal object GoalMapper {
    fun map(json: JsonObject): Goal? {
        val id = json.string("id") ?: return null
        val title = json.string("title") ?: return null
        val metric = json["metric"] as? JsonObject
        return Goal(
            id = id, title = title,
            current = number(json["current_value"]) ?: number(metric?.get("current")) ?: 0.0,
            target = number(json["target_value"]) ?: number(metric?.get("target")) ?: 0.0,
            unit = json.string("unit"),
            createdAt = BackendDate.parse(json.string("created_at")),
        )
    }

    private fun number(value: JsonElement?): Double? = (value as? JsonPrimitive)?.doubleOrNull
}
