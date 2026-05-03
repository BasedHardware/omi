package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.Instant

class AuditLog(context: Context) {
    private val file = File(context.filesDir, "ambient_audit.jsonl")

    @Synchronized
    fun record(type: String, fields: Map<String, Any?> = emptyMap()) {
        val json = JSONObject()
            .put("type", type)
            .put("timestamp", Instant.now().toString())
        fields.forEach { (key, value) -> json.put(key, value) }
        file.parentFile?.mkdirs()
        file.appendText(json.toString() + "\n")
    }

    fun tail(limit: Int = 100): List<String> {
        if (!file.exists()) return emptyList()
        return file.readLines().takeLast(limit)
    }
}
