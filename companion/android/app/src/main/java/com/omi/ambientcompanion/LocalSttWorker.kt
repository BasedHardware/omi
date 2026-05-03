package com.omi.ambientcompanion

import android.content.Context

class LocalSttWorker(private val context: Context) {
    fun drainSpoolForLocalTranscripts() {
        AuditLog(context).record(
            "local_stt_worker_ready",
            mapOf("engine" to "pending_on_device_model", "note" to "spooled audio is available for local STT integration"),
        )
    }
}
