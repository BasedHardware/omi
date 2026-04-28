package com.friend.ios

import android.content.Context
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject

class AmbientPolicyClient(private val context: Context) {
    private val client = OkHttpClient()

    fun fetchPolicy(policyUrl: String, bearerToken: String? = null): String {
        val builder = Request.Builder().url(policyUrl)
        if (!bearerToken.isNullOrBlank()) builder.header("Authorization", "Bearer $bearerToken")
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
                val publicKey = envelope.optString(
                    "public_key",
                    prefs.getString("flutter.ambient_capture_controller_public_key", "") ?: "",
                )
                val result = AmbientPolicyVerifier.verify(
                    mapOf(
                        "payload" to policyJson,
                        "signature" to signature,
                        "publicKey" to publicKey,
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
                AmbientCaptureMethodChannel.emitTelemetry(
                    mapOf(
                        "type" to "policy_rejected",
                        "reason" to e.javaClass.simpleName,
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
