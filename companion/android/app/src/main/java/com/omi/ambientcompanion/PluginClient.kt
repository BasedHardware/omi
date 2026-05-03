package com.omi.ambientcompanion

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.Instant

class PluginClient(private val context: Context) {
    private val prefs = AppPrefs(context)
    private val secureStore = SecureStore(context)
    private val audit = AuditLog(context)

    fun registerDevice(pluginBaseUrl: String, omiUserId: String, label: String = "Pixel Ambient Companion"): Boolean {
        prefs.pluginBaseUrl = pluginBaseUrl
        prefs.omiUserId = omiUserId
        val deviceId = prefs.deviceId.ifBlank { "ambient-${prefs.appInstallId}" }
        prefs.deviceId = deviceId
        val body = JSONObject()
            .put("omi_user_id", omiUserId)
            .put("device_id", deviceId)
            .put("device_label", label)
            .put("app_install_id", prefs.appInstallId)
        val response = request("POST", "${prefs.pluginBaseUrl}/device/register", body.toString(), emptyMap())
        if (response.status !in 200..299) {
            audit.record("controller_registration_failed", mapOf("status" to response.status, "body" to response.body.take(200)))
            return false
        }
        val json = JSONObject(response.body)
        prefs.policyUrl = json.optString("policy_url")
        prefs.telemetryUrl = json.optString("telemetry_url")
        prefs.fallbackSegmentsUrl = json.optString("fallback_segments_url")
        prefs.audioSpoolUrl = json.optString("audio_spool_url", "${prefs.pluginBaseUrl}/capture/audio-spool")
        prefs.controllerPublicKey = json.optString("plugin_public_key")
        prefs.controllerKeyId = json.optString("key_id")
        secureStore.putSecret("device_token", json.optString("device_token"))
        audit.record("controller_registered", mapOf("key_id" to prefs.controllerKeyId, "device_id" to deviceId))
        audit.record("controller_key_pinned", mapOf("key_id" to prefs.controllerKeyId))
        return true
    }

    fun fetchPolicy(): PolicyVerifyResult {
        val token = secureStore.getSecret("device_token")
        if (token.isBlank()) return PolicyVerifyResult(false, "missing_device_token")
        if (prefs.policyUrl.isBlank()) return PolicyVerifyResult(false, "missing_policy_url")
        val headers = mapOf(
            "Authorization" to "Bearer $token",
            "X-Omi-User-Id" to prefs.omiUserId,
            "X-Omi-Device-Id" to prefs.deviceId,
            "X-Omi-App-Id" to PolicyVerifier.PLUGIN_ID,
            "X-Last-Policy-Sequence" to prefs.lastAcceptedSequence.toString(),
        )
        val response = request("GET", prefs.policyUrl, null, headers)
        if (response.status !in 200..299) return PolicyVerifyResult(false, "policy_http_${response.status}")
        val result = PolicyVerifier(prefs).verify(JSONObject(response.body))
        audit.record(if (result.accepted) "policy_applied" else "policy_rejected", mapOf("reason" to result.reason))
        return result
    }

    fun sendTelemetry(type: String, health: HealthEvent? = null, metadata: JSONObject = JSONObject()) {
        if (prefs.telemetryUrl.isBlank()) return
        val body = JSONObject()
            .put("omi_user_id", prefs.omiUserId)
            .put("device_id", prefs.deviceId)
            .put("event_type", type)
            .put("timestamp", Instant.now().toString())
            .put("capture_state", health?.state?.name)
            .put("health_state", health?.state?.name)
            .put("foreground_app", health?.foregroundPackage)
            .put("metadata", metadata)
        request("POST", prefs.telemetryUrl, body.toString(), authHeaders())
    }

    fun uploadFallbackSegments(segments: List<FallbackSegment>): Boolean {
        if (segments.isEmpty() || prefs.fallbackSegmentsUrl.isBlank()) return false
        val arr = JSONArray()
        segments.forEach { segment -> arr.put(segment.toJson()) }
        val body = JSONObject()
            .put("omi_user_id", prefs.omiUserId)
            .put("device_id", prefs.deviceId)
            .put("session_id", prefs.appInstallId)
            .put("segments", arr)
        val response = request("POST", prefs.fallbackSegmentsUrl, body.toString(), authHeaders())
        return response.status in 200..299
    }

    fun uploadAudioFile(meta: SpoolMetadata, chunks: Sequence<ByteArray>): Boolean {
        val url = prefs.audioSpoolUrl.ifBlank { prefs.pluginBaseUrl.ifBlank { return false } + "/capture/audio-spool" }
        val bytes = chunks.fold(ByteArrayOutputStream()) { out, chunk ->
            out.write(intLe(chunk.size))
            out.write(chunk)
            out
        }.toByteArray()
        if (bytes.isEmpty()) return false
        val filename = "ambient_android_pcm16_16000_1_${meta.startedAt.toEpochMilli()}_1.bin"
        val body = JSONObject()
            .put("omi_user_id", prefs.omiUserId)
            .put("device_id", prefs.deviceId)
            .put("session_id", meta.sessionId)
            .put("filename", filename)
            .put("started_at", meta.startedAt.toString())
            .put("duration_estimate", meta.durationEstimateSeconds)
            .put("sample_rate", 16000)
            .put("channels", 1)
            .put("codec", "pcm16")
            .put("format", "length_prefixed_pcm")
            .put("audio_base64", android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP))
        val response = request("POST", url, body.toString(), authHeaders())
        return response.status in 200..299
    }

    private fun authHeaders(): Map<String, String> {
        val token = secureStore.getSecret("device_token")
        return if (token.isBlank()) {
            emptyMap()
        } else {
            mapOf(
                "Authorization" to "Bearer $token",
                "X-Omi-User-Id" to prefs.omiUserId,
                "X-Omi-Device-Id" to prefs.deviceId,
                "X-Omi-App-Id" to PolicyVerifier.PLUGIN_ID,
                "X-Last-Policy-Sequence" to prefs.lastAcceptedSequence.toString(),
            )
        }
    }

    private fun intLe(value: Int): ByteArray = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(value).array()

    private fun request(method: String, url: String, body: String?, headers: Map<String, String>): HttpResponse {
        return try {
            val conn = (URL(url).openConnection() as HttpURLConnection)
            conn.requestMethod = method
            conn.connectTimeout = 10_000
            conn.readTimeout = 20_000
            conn.setRequestProperty("Content-Type", "application/json")
            headers.forEach { (k, v) -> conn.setRequestProperty(k, v) }
            if (body != null) {
                conn.doOutput = true
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            HttpResponse(status, stream?.bufferedReader()?.readText().orEmpty())
        } catch (e: Throwable) {
            HttpResponse(599, e.toString())
        }
    }
}

data class HttpResponse(val status: Int, val body: String)
