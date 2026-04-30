package com.friend.ios

import android.content.Context
import org.json.JSONObject
import java.io.File

object AmbientCaptureAudit {
    private const val AUDIT_FILE = "ambient_capture_audit.jsonl"

    fun record(context: Context?, eventType: String, details: Map<String, Any?> = emptyMap()) {
        val appContext = context?.applicationContext ?: return
        try {
            val event = JSONObject()
                .put("event_type", eventType)
                .put("timestamp", System.currentTimeMillis())
                .put("details", JSONObject(details))
            File(appContext.filesDir, AUDIT_FILE).appendText(event.toString() + "\n")
        } catch (_: Exception) {
            // Audit must never crash capture or policy verification.
        }
    }
}
