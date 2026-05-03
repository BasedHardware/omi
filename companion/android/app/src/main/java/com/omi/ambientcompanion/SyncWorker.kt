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
        val client = PluginClient(context)
        val fallbackQueue = FallbackSegmentQueue(context)
        val pendingSegments = fallbackQueue.pending()
        if (client.uploadFallbackSegments(pendingSegments)) {
            fallbackQueue.clearUploaded(pendingSegments.map { it.id }.toSet())
        }
        val spool = CaptureSpoolStore(context)
        val uploaded = mutableListOf<String>()
        spool.list("pending").forEach { meta ->
            if (client.uploadAudioFile(meta, spool.readPlainChunks(meta))) uploaded.add(meta.filePath)
        }
        if (uploaded.isNotEmpty()) spool.markStatus(uploaded, "synced")
    }

    private fun networkAvailable(context: Context): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
