package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONObject
import java.io.File

class FallbackSegmentQueue(context: Context) {
    private val file = File(context.filesDir, "fallback_segments.jsonl")
    private val seen = LinkedHashSet<String>()

    @Synchronized
    fun enqueue(segment: FallbackSegment) {
        val key = "${segment.source}:${segment.text.trim().lowercase()}:${segment.start.epochSecond / 30}"
        if (key in seen) return
        seen.add(key)
        file.parentFile?.mkdirs()
        file.appendText(segment.toJson().put("dedupe_key", key).toString() + "\n")
    }

    @Synchronized
    fun pending(): List<FallbackSegment> {
        if (!file.exists()) return emptyList()
        return file.readLines()
            .filter { it.isNotBlank() }
            .mapNotNull { runCatching { FallbackSegment.fromJson(JSONObject(it)) }.getOrNull() }
            .filter { !it.uploaded }
    }

    @Synchronized
    fun clearUploaded(uploadedIds: Set<String>) {
        if (!file.exists()) return
        val kept = file.readLines().mapNotNull { line ->
            val json = runCatching { JSONObject(line) }.getOrNull() ?: return@mapNotNull null
            val id = json.optString("id")
            if (uploadedIds.contains(id)) null else line
        }
        file.writeText(kept.joinToString(separator = "\n", postfix = if (kept.isEmpty()) "" else "\n"))
    }
}
