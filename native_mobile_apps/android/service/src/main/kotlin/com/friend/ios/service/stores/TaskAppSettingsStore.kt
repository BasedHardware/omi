package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.TaskAppLevel
import com.friend.ios.network.endpoints.TaskAppOption
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.NativeKey
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

/**
 * Port of `TaskAppSettingsStore.swift`: per task app settings (Flutter `asana_settings_page`,
 * `clickup_settings_page`, `todoist_…`, `google_tasks_…`): which app new tasks go to, and for
 * Asana (workspace, project) and ClickUp (team, space, list) where in it. The backend does not
 * return the saved place, so it is also remembered here.
 */
class TaskAppSettingsStore(private val api: APIClientProtocol, private val preferences: Preferences) {
    var defaultApp: String? by mutableStateOf(null)
        private set
    var options: Map<TaskAppLevel, List<TaskAppOption>> by mutableStateOf(emptyMap())
        private set
    var selection: Map<String, Map<TaskAppLevel, TaskAppOption>> by mutableStateOf(decode(preferences.string(NativeKey.TaskAppSelections)))
        private set
    var loading: Set<TaskAppLevel> by mutableStateOf(emptySet())
        private set
    var failed: Boolean by mutableStateOf(false)
        private set

    /** The default app and the first level's choices (the next levels follow the saved place). */
    suspend fun load(app: String) {
        failed = false
        defaultApp = attempt { api.defaultTaskApp() }
        var parent: String? = null
        val levels = TaskAppLevel.levels(app)
        for (level in levels) {
            if (level != levels.first() && parent == null) break
            loadOptions(level, parent)
            parent = selection[app]?.get(level)?.id
        }
    }

    /**
     * Picks [option] on [level]; the levels below it are cleared (on the backend too) and their
     * choices loaded. Taken back if the backend refuses.
     */
    suspend fun select(app: String, level: TaskAppLevel, option: TaskAppOption?) {
        val levels = TaskAppLevel.levels(app)
        val index = levels.indexOf(level)
        if (index < 0) return
        val previous = selection[app].orEmpty()
        val updated = previous.toMutableMap()
        val change = mutableMapOf<TaskAppLevel, TaskAppOption?>(level to option)
        if (option != null) updated[level] = option else updated.remove(level)
        for (below in levels.drop(index + 1)) {
            updated.remove(below)
            change[below] = null
            options = options - below
        }
        selection = selection + (app to updated)
        try {
            api.saveTaskAppSelection(app, change)
            save()
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            selection = selection + (app to previous)
            failed = true
            return
        }
        if (option != null && index + 1 < levels.size) loadOptions(levels[index + 1], option.id)
    }

    /** New tasks from conversations go to this app. */
    suspend fun makeDefault(app: String) {
        val previous = defaultApp
        defaultApp = app
        try {
            api.setDefaultTaskApp(app)
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            defaultApp = previous
            failed = true
        }
    }

    /** After a disconnect: the saved place no longer applies. */
    fun forget(app: String) {
        selection = selection - app
        if (defaultApp == app) defaultApp = null
        save()
    }

    private suspend fun loadOptions(level: TaskAppLevel, parent: String?) {
        loading = loading + level
        try {
            options = options + (level to api.taskAppOptions(level, parent))
        } catch (e: Exception) {
            if (e is CancellationException) throw e
            failed = true
        } finally {
            loading = loading - level
        }
    }

    private suspend fun <T> attempt(block: suspend () -> T): T? = try {
        block()
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        null
    }

    private fun save() {
        val json = buildJsonObject {
            for ((app, levels) in selection) {
                put(
                    app,
                    buildJsonObject {
                        for ((level, option) in levels) {
                            put(level.rawValue, buildJsonObject {
                                put("id", option.id)
                                put("name", option.name)
                            })
                        }
                    },
                )
            }
        }
        preferences.set(NativeKey.TaskAppSelections, json.toString())
    }

    companion object {
        /** The saved places: `{app: {level: {id, name}}}`, as iOS stores them. */
        fun decode(json: String?): Map<String, Map<TaskAppLevel, TaskAppOption>> {
            val root = json?.let { runCatching { Json.parseToJsonElement(it) }.getOrNull() } as? JsonObject ?: return emptyMap()
            return root.mapNotNull { (app, value) ->
                val levels = (value as? JsonObject)?.mapNotNull { (key, item) ->
                    val level = TaskAppLevel.from(key) ?: return@mapNotNull null
                    val fields = item as? JsonObject ?: return@mapNotNull null
                    val id = (fields["id"] as? JsonPrimitive)?.contentOrNull ?: return@mapNotNull null
                    level to TaskAppOption(id, fields["name"]?.jsonPrimitive?.contentOrNull ?: id)
                }?.toMap() ?: return@mapNotNull null
                app to levels
            }.toMap()
        }
    }
}

/** A task app's settings page makes its store from the settings' API and preferences (`StoreFactories`). */
fun SettingsStore.makeTaskAppSettingsStore(): TaskAppSettingsStore = TaskAppSettingsStore(api, preferences)
