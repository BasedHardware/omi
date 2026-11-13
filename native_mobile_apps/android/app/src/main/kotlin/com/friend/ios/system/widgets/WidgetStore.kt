package com.friend.ios.system.widgets

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/** Port of `SharedStore.swift`: the widgets the app offers; the app updates one kind when its snapshot changes. */
enum class WidgetKind { Battery, UpNext, Latest }

/** The Omi as the battery widget shows it. */
data class DeviceSnapshot(val name: String, val connected: Boolean, val battery: Int?) {
    companion object {
        /** At or under this the widget marks the level as low. */
        const val LOW_MARK = 20
    }
}

/** The next open tasks, as the Up next widget lists them. */
data class UpNextSnapshot(val tasks: List<Task>, val open: Int) {
    data class Task(val id: String, val title: String, val due: Instant?)
}

/** The newest conversation, for the Latest widget. */
data class LatestSnapshot(val id: String, val title: String, val at: Instant, val taskCount: Int, val duration: Double?)

/**
 * JSON documents in the app's own preferences (no App Group on Android: widgets run in the app's
 * process): the app writes them, the widgets read them.
 */
class WidgetStore(private val prefs: SharedPreferences) {
    constructor(context: Context) : this(context.getSharedPreferences(FILE, Context.MODE_PRIVATE))

    enum class Key(val rawValue: String, val widget: WidgetKind) {
        Device("omi.widget.device", WidgetKind.Battery),
        UpNext("omi.widget.upNext", WidgetKind.UpNext),
        Latest("omi.widget.latest", WidgetKind.Latest),
    }

    /** Whether the app has published this document at least once (null documents included). */
    fun isKnown(key: Key): Boolean = prefs.contains(key.rawValue)

    fun device(): DeviceSnapshot? = json(Key.Device)?.let {
        DeviceSnapshot(it.getString("name"), it.getBoolean("connected"), if (it.has("battery")) it.getInt("battery") else null)
    }

    fun upNext(): UpNextSnapshot? = json(Key.UpNext)?.let { json ->
        val tasks = json.getJSONArray("tasks")
        UpNextSnapshot(
            (0 until tasks.length()).map { index ->
                val task = tasks.getJSONObject(index)
                UpNextSnapshot.Task(task.getString("id"), task.getString("title"), if (task.has("due")) Instant.ofEpochSecond(task.getLong("due")) else null)
            },
            json.getInt("open"),
        )
    }

    fun latest(): LatestSnapshot? = json(Key.Latest)?.let {
        LatestSnapshot(
            it.getString("id"), it.getString("title"), Instant.ofEpochSecond(it.getLong("at")), it.getInt("taskCount"),
            if (it.has("duration")) it.getDouble("duration") else null,
        )
    }

    /** Stores the document (null clears it but marks it published); true when it changed. */
    fun write(device: DeviceSnapshot?): Boolean = write(Key.Device, device?.let {
        JSONObject().put("name", it.name).put("connected", it.connected).apply { it.battery?.let { level -> put("battery", level.coerceIn(0, 100)) } }
    })

    fun write(upNext: UpNextSnapshot?): Boolean = write(Key.UpNext, upNext?.let { snapshot ->
        JSONObject().put("open", snapshot.open).put(
            "tasks",
            JSONArray(snapshot.tasks.map { task -> JSONObject().put("id", task.id).put("title", task.title).apply { task.due?.let { put("due", it.epochSecond) } } }),
        )
    })

    fun write(latest: LatestSnapshot?): Boolean = write(Key.Latest, latest?.let {
        JSONObject().put("id", it.id).put("title", it.title).put("at", it.at.epochSecond).put("taskCount", it.taskCount)
            .apply { it.duration?.let { seconds -> put("duration", seconds) } }
    })

    /** Signing out removes everything, so widgets show nothing of the previous account. */
    fun clear(): List<WidgetKind> = Key.entries.filter { prefs.contains(it.rawValue) }.map { key ->
        prefs.edit().remove(key.rawValue).apply()
        key.widget
    }

    private fun json(key: Key): JSONObject? = prefs.getString(key.rawValue, null)?.takeIf { it.isNotEmpty() }?.let { runCatching { JSONObject(it) }.getOrNull() }

    private fun write(key: Key, value: JSONObject?): Boolean {
        val text = value?.toString() ?: ""
        if (prefs.contains(key.rawValue) && prefs.getString(key.rawValue, null) == text) return false
        prefs.edit().putString(key.rawValue, text).apply()
        return true
    }

    companion object {
        const val FILE = "omi.widgets"
    }
}

/**
 * Port of `UpNextPicker`: what the Up next widget shows, as Flutter's `HomeWidgetsPayload.pickUpNext`:
 * dated tasks soonest first (overdue on top), then undated ones in the app's order.
 */
object UpNextPicker {
    data class Candidate(val id: String, val title: String, val due: Instant?, val isOpen: Boolean)

    fun snapshot(candidates: List<Candidate>, limit: Int = 3): UpNextSnapshot {
        val open = candidates.filter { it.isOpen && it.title.isNotBlank() }
        val dated = open.filter { it.due != null }.sortedBy { it.due }
        val undated = open.filter { it.due == null }
        val shown = (dated + undated).take(limit).map { UpNextSnapshot.Task(it.id, it.title.trim(), it.due) }
        return UpNextSnapshot(shown, open.size)
    }
}
