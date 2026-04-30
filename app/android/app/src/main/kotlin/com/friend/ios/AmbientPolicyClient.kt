package com.friend.ios

import android.content.Context
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

class AmbientPolicyClient(private val context: Context) {
    private val client = OkHttpClient()

    fun fetchPolicy(policyUrl: String): String {
        val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        val token = AmbientSecureStore.getString(context, "controller_device_token")
        if (token.isNullOrBlank()) {
            AmbientCaptureAudit.record(context, "policy_rejected_missing_token")
            throw IllegalStateException("policy_rejected_missing_token")
        }
        val appId = prefs.getString("flutter.ambient_capture_active_controller_app_id", "") ?: ""
        val userId = prefs.getString("flutter.uid", "") ?: ""
        val deviceId = prefs.getString("flutter.ambient_capture_registered_device_id", "") ?: ""
        val lastSequence = prefs.getLong("flutter.ambient_capture_last_accepted_sequence", 0L)
        val builder = Request.Builder().url(policyUrl)
            .header("Authorization", "Bearer $token")
            .header("X-Omi-User-Id", userId)
            .header("X-Omi-Device-Id", deviceId)
            .header("X-Omi-App-Id", appId)
            .header("X-Last-Policy-Sequence", lastSequence.toString())
        return client.newCall(builder.build()).execute().use { response ->
            if (!response.isSuccessful) throw IllegalStateException("Policy fetch failed: ${response.code}")
            response.body?.string() ?: ""
        }
    }

    fun fetchVerifyAndApply(onAccepted: (Map<String, Any?>) -> Unit) {
        Thread {
            val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            if (!prefs.getBoolean("flutter.ambient_capture_plugin_control_enabled", false)) return@Thread
            val url = prefs.getString("flutter.ambient_capture_policy_url", "") ?: ""
            if (url.isBlank()) return@Thread
            try {
                val payload = fetchPolicy(url)
                val envelope = JSONObject(payload)
                val policyJson = envelope.optString("payload", payload)
                val signature = envelope.optString("signature", "")
                val result = AmbientPolicyVerifier.verify(
                    mapOf(
                        "payload" to policyJson,
                        "signature" to signature,
                        "keyId" to envelope.optString("key_id", ""),
                        "publicKey" to envelope.optString("public_key", ""),
                        "algorithm" to envelope.optString("alg", "Ed25519"),
                    ),
                )
                if (result["accepted"] == true) {
                    onAccepted(JSONObject(policyJson).toMap())
                } else {
                    if (result["reason"] == "expired") {
                        AmbientCaptureForegroundService.command(context, AmbientCaptureForegroundService.ACTION_PAUSE)
                    }
                    AmbientCaptureMethodChannel.emitTelemetry(
                        mapOf(
                            "type" to "policy_rejected",
                            "reason" to result["reason"],
                            "timestamp" to System.currentTimeMillis(),
                        ),
                    )
                }
            } catch (e: Exception) {
                Log.w("AmbientCapture", "Policy fetch/apply failed: ${e.message}")
                val reason = if (e.message == "policy_rejected_missing_token") {
                    "policy_rejected_missing_token"
                } else {
                    e.javaClass.simpleName
                }
                AmbientCaptureMethodChannel.emitTelemetry(
                    mapOf(
                        "type" to "policy_rejected",
                        "reason" to reason,
                        "message" to e.message,
                        "timestamp" to System.currentTimeMillis(),
                    ),
                )
            }
        }.start()
    }

    private fun JSONObject.toMap(): Map<String, Any?> {
        val map = mutableMapOf<String, Any?>()
        val keys = keys()
        while (keys.hasNext()) {
            val key = keys.next()
            val value = get(key)
            map[key] = if (value == JSONObject.NULL) {
                null
            } else if (value is org.json.JSONArray) {
                (0 until value.length()).map { if (value.get(it) == JSONObject.NULL) null else value.get(it) }
            } else {
                value
            }
        }
        return map
    }
}
