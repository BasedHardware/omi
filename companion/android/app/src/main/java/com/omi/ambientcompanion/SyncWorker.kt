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
        val now = System.currentTimeMillis()
        if (prefs.nextSyncAfterMs > now) {
            audit.record("sync_backoff_active", mapOf("retry_after_ms" to (prefs.nextSyncAfterMs - now)))
            return
        }
        val client = PluginClient(context)
        val fallbackQueue = FallbackSegmentQueue(context)
        var attempted = false
        var succeeded = false
        val pendingSegments = fallbackQueue.pending()
        if (pendingSegments.isNotEmpty()) attempted = true
        if (client.uploadFallbackSegments(pendingSegments)) {
            fallbackQueue.clearUploaded(pendingSegments.map { it.id }.toSet())
            if (pendingSegments.isNotEmpty()) audit.record("fallback_segments_uploaded", mapOf("count" to pendingSegments.size))
            if (pendingSegments.isNotEmpty()) succeeded = true
        }
        LocalSttWorker(context).drainSpoolForLocalTranscripts()
        val spool = CaptureSpoolStore(context)
        val uploaded = mutableListOf<String>()
        if (prefs.allowAudioUpload) {
            spool.list("pending").forEach { meta ->
                attempted = true
                if (client.uploadAudioFile(meta, spool.readPlainChunks(meta))) {
                    uploaded.add(meta.filePath)
                    succeeded = true
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
        if (attempted && succeeded) {
            prefs.syncFailureCount = 0
            prefs.nextSyncAfterMs = 0
        } else if (attempted) {
            scheduleBackoff(prefs, audit)
        }
    }

    private fun scheduleBackoff(prefs: AppPrefs, audit: AuditLog) {
        val failures = (prefs.syncFailureCount + 1).coerceAtMost(8)
        val delayMs = (30_000L * (1 shl (failures - 1))).coerceAtMost(30 * 60_000L)
        prefs.syncFailureCount = failures
        prefs.nextSyncAfterMs = System.currentTimeMillis() + delayMs
        audit.record("sync_backoff_scheduled", mapOf("failures" to failures, "delay_ms" to delayMs))
    }

    private fun networkAvailable(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
