package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.UUID

class CaptureSessionStore(context: Context) {
    private val currentFile = File(context.filesDir, "ambient_current_session.json")
    private val historyFile = File(context.filesDir, "ambient_sessions.jsonl")

    @Synchronized
    fun start(reason: String): String {
        val existing = current()
        if (existing != null && existing.optString("status") == "running") return existing.optString("session_id")
        val sessionId = UUID.randomUUID().toString()
        val json = JSONObject()
            .put("session_id", sessionId)
            .put("started_at", Instant.now().toString())
            .put("last_updated_at", Instant.now().toString())
            .put("status", "running")
            .put("reason", reason)
        currentFile.writeText(json.toString())
        appendHistory(json)
        return sessionId
    }

    @Synchronized
    fun update(status: String, health: AmbientHealthState? = null) {
        val json = current() ?: return
        json.put("status", status)
            .put("last_updated_at", Instant.now().toString())
        if (health != null) json.put("health_state", health.name)
        currentFile.writeText(json.toString())
        appendHistory(json)
    }

    @Synchronized
    fun finish(status: String) {
        val json = current() ?: return
        json.put("status", status)
            .put("finished_at", Instant.now().toString())
            .put("last_updated_at", Instant.now().toString())
        appendHistory(json)
        currentFile.delete()
    }

    @Synchronized
    fun current(): JSONObject? {
        if (!currentFile.exists()) return null
        return runCatching { JSONObject(currentFile.readText()) }.getOrNull()
    }

    private fun appendHistory(json: JSONObject) {
        historyFile.parentFile?.mkdirs()
        historyFile.appendText(json.toString() + "\n")
    }
}
