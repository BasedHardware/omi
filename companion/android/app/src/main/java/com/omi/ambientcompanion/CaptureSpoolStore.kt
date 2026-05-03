package com.omi.ambientcompanion

import android.content.Context
import android.os.StatFs
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant
import java.time.format.DateTimeFormatter
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec

class CaptureSpoolStore(private val context: Context) {
    private val prefs = AppPrefs(context)
    private val audit = AuditLog(context)
    private val dir = File(context.filesDir, "ambient_spool").apply { mkdirs() }
    private val metaDir = File(context.filesDir, "ambient_spool_meta").apply { mkdirs() }
    private var currentFile: File? = null
    private var currentStartedAt: Instant? = null
    private var currentSessionId: String? = null
    private var currentBytes: Long = 0
    private var part = 0

    @Synchronized
    fun startSession() {
        if (currentFile != null) return
        currentSessionId = UUID.randomUUID().toString()
        currentStartedAt = Instant.now()
        currentBytes = 0
        part += 1
        val stamp = DateTimeFormatter.ISO_INSTANT.format(currentStartedAt).replace(':', '-')
        currentFile = File(dir, "ambient_companion_pcm16_16000_1_${stamp}_${part}.bin")
        audit.record("spool_session_started", mapOf("session_id" to currentSessionId, "file" to currentFile?.absolutePath))
    }

    @Synchronized
    fun writeChunk(pcm: ByteArray): SpoolWriteResult {
        if (!hasStorageFor(pcm.size)) return SpoolWriteResult(false, "storage_limit")
        if (currentFile == null) startSession()
        val file = currentFile ?: return SpoolWriteResult(false, "spool_unavailable")
        val encrypted = encryptLengthPrefixedChunk(pcm)
        file.appendBytes(intLe(encrypted.size) + encrypted)
        currentBytes += pcm.size
        writeMetadata(status = "pending")
        return SpoolWriteResult(true, "ok")
    }

    @Synchronized
    fun closeSession(status: String = "pending") {
        if (currentFile != null) {
            writeMetadata(status)
            audit.record("spool_session_closed", mapOf("session_id" to currentSessionId, "bytes" to currentBytes))
        }
        currentFile = null
        currentStartedAt = null
        currentSessionId = null
        currentBytes = 0
    }

    fun list(status: String? = null): List<SpoolMetadata> {
        return metaDir.listFiles { file -> file.extension == "json" }
            ?.mapNotNull { file -> runCatching { metadataFromJson(JSONObject(file.readText())) }.getOrNull() }
            ?.filter { status == null || it.status == status }
            ?.sortedBy { it.startedAt }
            ?: emptyList()
    }

    fun readPlainChunks(meta: SpoolMetadata): Sequence<ByteArray> = sequence {
        val file = File(meta.filePath)
        if (!file.exists()) return@sequence
        val bytes = file.readBytes()
        var offset = 0
        while (offset + 4 <= bytes.size) {
            val encryptedLen = ByteBuffer.wrap(bytes, offset, 4).order(ByteOrder.LITTLE_ENDIAN).int
            offset += 4
            if (encryptedLen <= 0 || offset + encryptedLen > bytes.size) break
            val decrypted = decryptChunk(bytes.copyOfRange(offset, offset + encryptedLen))
            offset += encryptedLen
            if (decrypted.size < 4) continue
            val pcmLen = ByteBuffer.wrap(decrypted, 0, 4).order(ByteOrder.LITTLE_ENDIAN).int
            if (pcmLen > 0 && 4 + pcmLen <= decrypted.size) {
                yield(decrypted.copyOfRange(4, 4 + pcmLen))
            }
        }
    }

    fun markStatus(paths: List<String>, status: String) {
        val wanted = paths.toSet()
        metaDir.listFiles { file -> file.extension == "json" }?.forEach { file ->
            val json = JSONObject(file.readText())
            if (wanted.contains(json.optString("file_path"))) {
                json.put("status", status)
                file.writeText(json.toString())
            }
        }
    }

    fun updateMetadata(filePath: String, updates: Map<String, Any?>) {
        metaDir.listFiles { file -> file.extension == "json" }?.forEach { file ->
            val json = JSONObject(file.readText())
            if (json.optString("file_path") == filePath) {
                updates.forEach { (key, value) -> json.put(key, value) }
                file.writeText(json.toString())
            }
        }
    }

    fun deleteByStatus(status: String?) {
        list(status).forEach { meta ->
            File(meta.filePath).delete()
            File(metaDir, meta.sessionId + ".json").delete()
        }
    }

    fun stats(): Map<String, Any> {
        val items = list()
        return mapOf(
            "pending_count" to items.count { it.status == "pending" },
            "synced_count" to items.count { it.status == "synced" },
            "bytes" to items.sumOf { it.bytes },
            "max_storage_mb" to prefs.maxStorageMb,
            "min_free_storage_mb" to prefs.minFreeStorageMb,
        )
    }

    private fun hasStorageFor(nextBytes: Int): Boolean {
        val total = list().sumOf { it.bytes } + currentBytes + nextBytes
        if (total > prefs.maxStorageMb.toLong() * 1024L * 1024L) return false
        val stat = StatFs(dir.absolutePath)
        val free = stat.availableBytes
        return free > prefs.minFreeStorageMb.toLong() * 1024L * 1024L
    }

    private fun writeMetadata(status: String) {
        val sessionId = currentSessionId ?: return
        val startedAt = currentStartedAt ?: return
        val file = currentFile ?: return
        val seconds = currentBytes.toDouble() / (16_000.0 * 2.0)
        val meta = SpoolMetadata(sessionId, startedAt, file.absolutePath, currentBytes, seconds, status)
        File(metaDir, "$sessionId.json").writeText(meta.toJson().toString())
    }

    private fun metadataFromJson(json: JSONObject): SpoolMetadata = SpoolMetadata(
        sessionId = json.optString("session_id"),
        startedAt = Instant.parse(json.optString("started_at")),
        filePath = json.optString("file_path"),
        bytes = json.optLong("bytes"),
        durationEstimateSeconds = json.optDouble("duration_estimate"),
        status = json.optString("status"),
        localSttStatus = json.optString("local_stt_status").ifBlank { null },
    )

    private fun encryptLengthPrefixedChunk(pcm: ByteArray): ByteArray {
        val plain = intLe(pcm.size) + pcm
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, KeystoreAes.getOrCreate(SPOOL_KEY_ALIAS))
        return cipher.iv + cipher.doFinal(plain)
    }

    private fun decryptChunk(encrypted: ByteArray): ByteArray {
        val iv = encrypted.copyOfRange(0, 12)
        val data = encrypted.copyOfRange(12, encrypted.size)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, KeystoreAes.getOrCreate(SPOOL_KEY_ALIAS), GCMParameterSpec(128, iv))
        return cipher.doFinal(data)
    }

    private fun intLe(value: Int): ByteArray = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array()

    companion object {
        private const val SPOOL_KEY_ALIAS = "omi_ambient_companion_spool"
    }
}

data class SpoolWriteResult(val ok: Boolean, val reason: String)
