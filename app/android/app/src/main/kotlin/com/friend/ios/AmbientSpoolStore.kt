package com.friend.ios

import android.content.Context
import android.os.StatFs
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

data class AmbientSpoolWriteResult(
    val written: Boolean,
    val reason: String = "ok",
    val metadata: Map<String, Any?> = emptyMap(),
)

class AmbientSpoolStore(private val context: Context) {
    private val spoolDir = File(context.filesDir, "ambient_capture_spool")
    private val metadataFile = File(spoolDir, "metadata.json")
    private val metadataLock = Any()
    private var sessionId: String = ""
    private var sessionStartSeconds: Long = 0
    private var part = 0
    private var currentFile: File? = null
    private var output: FileOutputStream? = null
    private var bytesInPart = 0L

    fun startSession() {
        synchronized(metadataLock) {
            spoolDir.mkdirs()
            sessionId = UUID.randomUUID().toString()
            sessionStartSeconds = System.currentTimeMillis() / 1000
            part = nextPartForSession(sessionStartSeconds)
            openPart()
        }
    }

    fun closeSession() {
        synchronized(metadataLock) {
            closePart()
            sessionId = ""
            bytesInPart = 0
        }
    }

    fun writeChunk(bytes: ByteArray): AmbientSpoolWriteResult {
        synchronized(metadataLock) {
            if (sessionId.isBlank() || output == null) startSession()
            val guard = storageGuard(bytes.size + 4L)
            if (!guard.written) return guard
            if (bytesInPart >= MAX_PART_BYTES) rotatePart()

            val target = currentFile ?: return AmbientSpoolWriteResult(false, "spool_file_missing")
            val lengthPrefix = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(bytes.size).array()
            output?.write(lengthPrefix)
            output?.write(bytes)
            output?.flush()
            bytesInPart += bytes.size + 4L
            val meta = updateMetadata(target, bytes.size + 4L)
            return AmbientSpoolWriteResult(true, metadata = meta)
        }
    }

    fun listMetadata(): List<Map<String, Any?>> {
        synchronized(metadataLock) {
            val arr = readMetadataArray()
            val result = mutableListOf<Map<String, Any?>>()
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                result.add(obj.toMap())
            }
            return result
        }
    }

    fun stats(): Map<String, Any?> {
        synchronized(metadataLock) {
            val files = listMetadata()
            val totalBytes = files.sumOf { (it["bytes"] as? Number)?.toLong() ?: 0L }
            val pending = files.count { it["status"] != "synced" && it["status"] != "imported" }
            return mapOf(
                "totalBytes" to totalBytes,
                "pendingCount" to pending,
                "fileCount" to files.size,
                "maxStorageMb" to prefs().getInt("flutter.ambient_capture_max_storage_mb", 1024),
                "minFreeStorageMb" to prefs().getInt("flutter.ambient_capture_min_free_storage_mb", 512),
            )
        }
    }

    fun markStatus(paths: List<String>, status: String) {
        synchronized(metadataLock) {
            val pathSet = paths.toSet()
            val arr = readMetadataArray()
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                if (pathSet.contains(obj.optString("file_path"))) {
                    obj.put("status", status)
                    obj.put("updated_at", System.currentTimeMillis())
                }
            }
            writeMetadataArray(arr)
            if (status == "synced" && prefs().getBoolean("flutter.ambient_capture_delete_synced_audio", true)) {
                deleteByStatus("synced")
            }
        }
    }

    fun deleteByStatus(status: String? = null) {
        synchronized(metadataLock) {
            val arr = readMetadataArray()
            val kept = JSONArray()
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                val shouldDelete = status == null || obj.optString("status") == status
                if (shouldDelete) {
                    File(obj.optString("file_path")).delete()
                } else {
                    kept.put(obj)
                }
            }
            writeMetadataArray(kept)
        }
    }

    fun enforceRetention() {
        synchronized(metadataLock) {
            val retention = prefs().getString(
                "flutter.ambient_capture_raw_audio_retention",
                "until_synced",
            ) ?: "until_synced"
            if (retention == "none") {
                deleteByStatus("synced")
                return
            }
            val maxAgeMs = when (retention) {
                "24h" -> 24L * 60L * 60L * 1000L
                "7d" -> 7L * 24L * 60L * 60L * 1000L
                else -> return
            }
            val now = System.currentTimeMillis()
            val arr = readMetadataArray()
            val kept = JSONArray()
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                val age = now - obj.optLong("started_at_ms", now)
                if (age > maxAgeMs && obj.optString("status") == "synced") {
                    File(obj.optString("file_path")).delete()
                } else {
                    kept.put(obj)
                }
            }
            writeMetadataArray(kept)
        }
    }

    private fun openPart() {
        val file = File(spoolDir, "ambient_android_pcm16_16000_1_${sessionStartSeconds}_${part}.bin")
        currentFile = file
        output = FileOutputStream(file, true)
        bytesInPart = file.length()
    }

    private fun closePart() {
        try {
            output?.flush()
            output?.close()
        } catch (_: Exception) {
        }
        output = null
        currentFile = null
    }

    private fun rotatePart() {
        closePart()
        part += 1
        openPart()
    }

    private fun nextPartForSession(startSeconds: Long): Int {
        val prefix = "ambient_android_pcm16_16000_1_${startSeconds}_"
        return (spoolDir.listFiles()?.mapNotNull { file ->
            if (!file.name.startsWith(prefix) || !file.name.endsWith(".bin")) null
            else file.name.removePrefix(prefix).removeSuffix(".bin").toIntOrNull()
        }?.maxOrNull() ?: -1) + 1
    }

    private fun storageGuard(nextBytes: Long): AmbientSpoolWriteResult {
        val prefs = prefs()
        val maxStorageBytes = prefs.getInt("flutter.ambient_capture_max_storage_mb", 1024).toLong() * 1024L * 1024L
        val minFreeBytes = prefs.getInt("flutter.ambient_capture_min_free_storage_mb", 512).toLong() * 1024L * 1024L
        val currentBytes = listMetadata().sumOf { (it["bytes"] as? Number)?.toLong() ?: 0L }
        val freeBytes = StatFs(spoolDir.absolutePath).availableBytes
        return when {
            currentBytes + nextBytes > maxStorageBytes -> AmbientSpoolWriteResult(false, "ambient_spool_quota_exceeded")
            freeBytes < minFreeBytes -> AmbientSpoolWriteResult(false, "ambient_spool_low_storage")
            else -> AmbientSpoolWriteResult(true)
        }
    }

    private fun updateMetadata(file: File, deltaBytes: Long): Map<String, Any?> {
        val arr = readMetadataArray()
        val path = file.absolutePath
        var obj: JSONObject? = null
        for (i in 0 until arr.length()) {
            val candidate = arr.getJSONObject(i)
            if (candidate.optString("file_path") == path) {
                obj = candidate
                break
            }
        }
        if (obj == null) {
            obj = JSONObject()
            obj.put("session_id", sessionId)
            obj.put("started_at", sessionStartSeconds)
            obj.put("started_at_ms", sessionStartSeconds * 1000L)
            obj.put("file_path", path)
            obj.put("bytes", 0L)
            obj.put("duration_estimate", 0.0)
            obj.put("status", "pending")
            obj.put("uploaded", false)
            obj.put("imported", false)
            arr.put(obj)
        }
        val totalBytes = obj.optLong("bytes") + deltaBytes
        obj.put("bytes", totalBytes)
        obj.put("duration_estimate", totalBytes.toDouble() / PCM_BYTES_PER_SECOND.toDouble())
        obj.put("updated_at", System.currentTimeMillis())
        writeMetadataArray(arr)
        return obj.toMap()
    }

    private fun readMetadataArray(): JSONArray {
        if (!metadataFile.exists()) return JSONArray()
        return try {
            JSONArray(metadataFile.readText())
        } catch (_: Exception) {
            JSONArray()
        }
    }

    private fun writeMetadataArray(arr: JSONArray) {
        spoolDir.mkdirs()
        metadataFile.writeText(arr.toString())
    }

    private fun prefs() = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)

    private fun JSONObject.toMap(): Map<String, Any?> {
        val result = mutableMapOf<String, Any?>()
        val keys = keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val value = get(key)
            result[key] = if (value == JSONObject.NULL) null else value
        }
        return result
    }

    companion object {
        private const val PCM_BYTES_PER_SECOND = 16000 * 2
        private const val MAX_PART_BYTES = 25L * 1024L * 1024L
    }
}
