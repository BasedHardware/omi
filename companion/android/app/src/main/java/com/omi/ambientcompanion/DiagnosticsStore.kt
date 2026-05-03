package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.Instant

class DiagnosticsStore(context: Context) {
    private val file = File(context.filesDir, "ambient_diagnostics.json")
    private val appContext = context.applicationContext

    fun write(reason: String) {
        val spoolStats = CaptureSpoolStore(appContext).stats()
        val currentSession = CaptureSessionStore(appContext).current()
        val json = JSONObject()
            .put("generated_at", Instant.now().toString())
            .put("reason", reason)
            .put("last_health_state", AmbientForegroundMicService.lastHealthState().name)
            .put("context", ContextSignals.snapshot())
            .put("spool", JSONObject(spoolStats))
            .put("current_session", currentSession)
        file.writeText(json.toString(2))
    }

    fun read(): String {
        if (!file.exists()) write("read_missing")
        return file.readText()
    }
}
