package com.omi.ambientcompanion

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import kotlin.concurrent.thread

object SyncWorker {
    private var running = false

    @Synchronized
    fun drainAsync(context: Context) {
        if (running) return
        running = true
        thread(name = "ambient-sync") {
            try {
                drain(context.applicationContext)
            } finally {
                running = false
            }
        }
    }

    fun drain(context: Context) {
        if (!networkAvailable(context)) return
        val audit = AuditLog(context)
        val prefs = AppPrefs(context)
        val client = PluginClient(context)
        val fallbackQueue = FallbackSegmentQueue(context)
        val pendingSegments = fallbackQueue.pending()
        if (client.uploadFallbackSegments(pendingSegments)) {
            fallbackQueue.clearUploaded(pendingSegments.map { it.id }.toSet())
            if (pendingSegments.isNotEmpty()) audit.record("fallback_segments_uploaded", mapOf("count" to pendingSegments.size))
        }
        val spool = CaptureSpoolStore(context)
        val uploaded = mutableListOf<String>()
        if (prefs.allowAudioUpload) {
            spool.list("pending").forEach { meta ->
                if (client.uploadAudioFile(meta, spool.readPlainChunks(meta))) {
                    uploaded.add(meta.filePath)
                    audit.record("spool_audio_uploaded", mapOf("session_id" to meta.sessionId, "bytes" to meta.bytes))
                }
            }
        } else {
            audit.record("spool_audio_upload_skipped", mapOf("reason" to "policy_or_local_setting_disabled"))
        }
        if (uploaded.isNotEmpty()) {
            spool.markStatus(uploaded, "synced")
            if (prefs.deleteSyncedAudio) spool.deleteByStatus("synced")
        }
    }

    private fun networkAvailable(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
