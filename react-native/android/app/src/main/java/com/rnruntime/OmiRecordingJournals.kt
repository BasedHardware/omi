package com.rnruntime

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.system.Os
import android.system.OsConstants
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.ReadableMap
import com.facebook.react.bridge.ReadableType
import com.facebook.react.bridge.WritableArray
import com.facebook.react.bridge.WritableMap
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

internal data class OmiRecordingOwner(val ownerKey: String, val receipt: String, val origin: String, val login: String)

internal class OmiRecordingJournals(
  private val context: Context,
  private val currentLogin: () -> String?,
) {
  private data class Entry(val id: String, val owner: OmiRecordingOwner, val file: File,
    val log: OmiRecordingLog, val input: JSONObject, var sessionId: String? = null)
  private var disposed = false
  private val entries = mutableMapOf<String, Entry>()
  private val root = File(context.noBackupFilesDir, "recording-journals")
  private val uuid = Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
  private fun digest(value: String) = MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it.toInt() and 255) }
  private fun partition(owner: OmiRecordingOwner) = digest("omi-recording-partition-v1\u0000${owner.origin}\u0000${owner.ownerKey}\u0000${owner.login}")
  private fun sync(directory: File) {
    val descriptor = Os.open(directory.path, OsConstants.O_RDONLY, 0)
    try { Os.fsync(descriptor) } finally { Os.close(descriptor) }
  }
  private fun key(): SecretKey {
    val alias = "omi-v5-recording-journal"
    val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    (store.getKey(alias, null) as? SecretKey)?.let { return it }
    return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
      init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
        .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
    }.generateKey()
  }
  private fun budget(extra: Long, creating: Boolean = false) {
    val files = if (root.exists()) root.walkTopDown().filter { it.isFile }.toList() else emptyList()
    check(files.sumOf { it.length() } + extra <= 134_217_728L && (!creating || files.size < 64)) { "Recording journal storage is full" }
  }
  private fun valid(owner: OmiRecordingOwner) {
    check(!disposed) { "Recording journals are disposed" }
    check(owner.login == currentLogin()) { "Recording journal login changed" }
    require(Regex("capture-owner-v1:[0-9a-f]{64}").matches(owner.ownerKey)
      && Regex("capture1\\.[0-9a-f]{64}\\.[0-9a-f]{64}").matches(owner.receipt))
  }
  private fun open(owner: OmiRecordingOwner, id: String): OmiRecordingLog {
    val rel = OmiBackendTransport.recordingJournalRelpath(partition(owner), id)
      ?: throw IllegalArgumentException("Invalid recording journal path")
    val file = File(root, rel)
    val directory = file.parentFile ?: throw IllegalStateException("Recording journal path is unavailable")
    check(directory.mkdirs() || directory.isDirectory)
    sync(context.noBackupFilesDir)
    sync(root)
    val binding = MessageDigest.getInstance("SHA-256").digest("${partition(owner)}\u0000$id".toByteArray())
    return OmiRecordingLog(file, key(), binding, ::sync)
  }
  private fun state(entry: Entry, includeEntries: Boolean = true): WritableMap = Arguments.createMap().apply {
    putString("handle", entry.id)
    putString("captureId", entry.id)
    putString("deviceId", entry.input.getString("deviceId"))
    if (entry.input.isNull("deviceName")) putNull("deviceName") else putString("deviceName", entry.input.getString("deviceName"))
    putInt("codec", entry.input.getInt("codec"))
    OmiRecordingPolicy.capturedAt(entry.input.opt("capturedAtMs"))?.let { putDouble("capturedAtMs", it.toDouble()) }
    if (entry.sessionId == null) putNull("sessionId") else putString("sessionId", entry.sessionId)
    putArray("entries", Arguments.createArray().apply {
      for (record in if (includeEntries) entry.log.readAll() else emptyList()) if (record[0].toInt() == 0) pushString(String(record, 1, record.size - 1, Charsets.UTF_8))
    })
  }
  @Synchronized fun create(owner: OmiRecordingOwner, value: ReadableMap): WritableMap {
    valid(owner)
    val deviceId = value.getString("deviceId").orEmpty()
    val name = if (value.hasKey("deviceName")) value.getString("deviceName") else null
    val codec = value.getDouble("codec")
    require(deviceId.isNotBlank() && deviceId.length <= 256 && (name == null || name.length <= 256) && codec in 0.0..255.0 && codec % 1 == 0.0)
    val capturedAt = if (value.hasKey("capturedAtMs")) {
      require(value.getType("capturedAtMs") == ReadableType.Number)
      OmiRecordingPolicy.capturedAt(value.getDouble("capturedAtMs"))
    } else null
    budget(4096, true)
    val id = UUID.randomUUID().toString()
    val input = JSONObject().put("deviceId", deviceId).put("deviceName", name ?: JSONObject.NULL).put("codec", codec.toInt())
    if (capturedAt != null) input.put("capturedAtMs", capturedAt)
    val log = open(owner, id)
    try { log.append(byteArrayOf(1) + input.toString().toByteArray()) }
    catch (error: Exception) { log.close(); throw error }
    val entry = Entry(id, owner, File(File(root, partition(owner)), "$id.journal"), log, input)
    entries[id] = entry
    return state(entry)
  }
  @Synchronized fun list(owner: OmiRecordingOwner): WritableArray {
    valid(owner)
    for (entry in entries.values) entry.log.close()
    entries.clear()
    val directory = File(root, partition(owner))
    val files = directory.listFiles()?.filter { it.isFile && it.name.endsWith(".journal") } ?: emptyList()
    check(files.size <= 64)
    val result = Arguments.createArray()
    for (file in files.sortedBy { it.name }) {
      val id = file.name.removeSuffix(".journal")
      require(uuid.matches(id))
      val log = open(owner, id)
      try {
        val records = log.readAll()
        if (records.isEmpty()) { log.close(); check(file.delete()); sync(directory); continue }
        require(records[0][0].toInt() == 1)
        val input = JSONObject(String(records[0], 1, records[0].size - 1, Charsets.UTF_8))
        OmiRecordingPolicy.capturedAt(input.opt("capturedAtMs"))
        val entry = Entry(id, owner, file, log, input)
        for (record in records.drop(1)) {
          require(record.isNotEmpty() && (record[0].toInt() == 0 || record[0].toInt() == 2))
          if (record[0].toInt() == 2) {
            val session = String(record, 1, record.size - 1, Charsets.UTF_8)
            require(uuid.matches(session) && (entry.sessionId == null || entry.sessionId == session))
            entry.sessionId = session
          }
        }
        entries[id] = entry
        result.pushMap(state(entry, false))
      } catch (error: Exception) { log.close(); throw error }
    }
    return result
  }
  @Synchronized fun read(handle: String): WritableMap = state(entry(handle))
  private fun entry(handle: String): Entry {
    val entry = entries[handle] ?: error("Recording journal handle is unavailable")
    valid(entry.owner)
    return entry
  }
  @Synchronized fun append(handle: String, value: String): Double {
    require(value.length <= OmiRecordingLog.MAX_ENTRY_BYTES - 1)
    val entry = entry(handle)
    val data = value.toByteArray(Charsets.UTF_8)
    budget(data.size + 261L)
    return entry.log.append(byteArrayOf(0) + data).toDouble()
  }
  @Synchronized fun ownerForRequest(handle: String, request: ReadableMap): OmiRecordingOwner {
    val entry = entry(handle)
    val path = request.getString("path")
    val method = request.getString("method")
    if (path == "/v1/device-sessions" && method == "POST") {
      val body = JSONObject(request.getString("body").orEmpty())
      require(body.getString("captureId") == entry.id && body.getString("deviceId") == entry.input.getString("deviceId")
        && body.getInt("codec") == entry.input.getInt("codec")
        && OmiRecordingPolicy.capturedAtMatches(entry.input.opt("capturedAtMs"), body.opt("capturedAtMs")) && body.optString("deviceName", null) == entry.input.optString("deviceName", null))
    } else {
      require(OmiBackendTransport.recordingPathOwned(method, path, entry.sessionId))
    }
    return entry.owner
  }
  @Synchronized fun acknowledgeOpen(handle: String, request: ReadableMap, response: WritableMap) {
    val entry = entry(handle)
    if (request.getString("path") != "/v1/device-sessions" || response.getInt("status") !in 200..299) return
    val session = JSONObject(response.getString("body").orEmpty()).getJSONObject("session")
    val id = session.getString("id")
    require(uuid.matches(id) && session.getString("deviceId") == entry.input.getString("deviceId")
      && session.getInt("codec") == entry.input.getInt("codec")
      && OmiRecordingPolicy.capturedAtMatches(entry.input.opt("capturedAtMs"), session.opt("capturedAtMs")) && (entry.sessionId == null || entry.sessionId == id))
    if (entry.sessionId == null) {
      budget(512)
      entry.log.append(byteArrayOf(2) + id.toByteArray())
      entry.sessionId = id
    }
  }
  @Synchronized fun remove(handle: String) {
    val entry = entry(handle)
    entry.log.close()
    check(entry.file.delete())
    sync(entry.file.parentFile!!)
    entries.remove(handle)
  }
  @Synchronized fun dispose() {
    disposed = true
    close()
  }
  @Synchronized fun close() {
    for (entry in entries.values) entry.log.close()
    entries.clear()
  }
}
