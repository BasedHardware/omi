package com.friend.ios

import android.content.Context
import android.util.Base64
import org.json.JSONObject
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.time.Instant

object AmbientPolicyVerifier {
    private var appContext: Context? = null

    fun configure(context: Context, args: Map<*, *>) {
        appContext = context.applicationContext
        val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        val editor = prefs.edit()
        fun putString(arg: String, pref: String) {
            args[arg]?.toString()?.takeIf { it.isNotBlank() }?.let { editor.putString(pref, it) }
        }
        putString("activePluginId", "flutter.ambient_capture_active_controller_app_id")
        putString("publicKey", "flutter.ambient_capture_controller_public_key")
        putString("keyId", "flutter.ambient_capture_controller_key_id")
        putString("policyUrl", "flutter.ambient_capture_policy_url")
        putString("userId", "flutter.uid")
        putString("deviceId", "flutter.ambient_capture_registered_device_id")
        if (args["revoked"] is Boolean) {
            editor.putBoolean("flutter.ambient_capture_controller_revoked", args["revoked"] as Boolean)
        }
        editor.apply()
    }

    fun verify(args: Map<*, *>): Map<String, Any?> {
        return try {
            val context = appContext ?: return reject("context_missing")
            val prefs = context.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            val payload = args["payload"] as? String ?: return reject("missing_payload")
            val signatureB64 = args["signature"] as? String ?: return reject("missing_signature")
            val publicKeyB64 = (args["publicKey"] as? String)?.takeIf { it.isNotBlank() }
                ?: prefs.getString("flutter.ambient_capture_controller_public_key", "")
                ?: return reject("missing_public_key")
            if (publicKeyB64.isBlank()) return reject("missing_public_key")

            val policy = JSONObject(payload)
            val algorithm = args["algorithm"]?.toString() ?: policy.optString("alg", "Ed25519")
            val valid = if (algorithm == "ES256") {
                verifyEs256(payload.toByteArray(Charsets.UTF_8), signatureB64, publicKeyB64)
            } else {
                verifyEd25519(payload.toByteArray(Charsets.UTF_8), signatureB64, publicKeyB64)
            }
            if (!valid) return reject("signature_invalid")

            val now = Instant.now()
            val validUntil = policy.optString("valid_until", "")
            if (validUntil.isBlank() || Instant.parse(validUntil).isBefore(now)) return reject("expired")
            val issuedAt = policy.optString("issued_at", "")
            if (issuedAt.isBlank() || Instant.parse(issuedAt).isAfter(now.plusSeconds(300))) {
                return reject("issued_in_future")
            }
            if (policy.optString("scope") != "ambient_capture_controller") return reject("missing_scope")
            if (
                policy.optString("plugin_id") != prefs.getString(
                    "flutter.ambient_capture_active_controller_app_id",
                    "",
                )
            ) {
                return reject("wrong_plugin")
            }
            if (policy.optString("user_id") != prefs.getString("flutter.uid", "")) return reject("wrong_user")
            val expectedDevice = prefs.getString("flutter.ambient_capture_registered_device_id", "") ?: ""
            if (expectedDevice.isNotBlank() && policy.optString("device_id") != expectedDevice) {
                return reject("wrong_device")
            }
            val sequence = policy.optLong("sequence", 0L)
            if (sequence <= prefs.getLong("flutter.ambient_capture_last_accepted_sequence", 0L)) {
                return reject("replayed_sequence")
            }
            if (!prefs.getBoolean("flutter.advanced_ambient_capture_enabled", false)) return reject("master_disabled")
            if (!prefs.getBoolean("flutter.ambient_capture_plugin_control_enabled", false)) {
                return reject("plugin_control_disabled")
            }
            if (prefs.getBoolean("flutter.ambient_capture_controller_revoked", false)) {
                return reject("controller_revoked")
            }
            if (AmbientCaptureForegroundService.statusMap()["privateMode"] == true) return reject("private_mode_active")
            if (policy.optBoolean("allow_accessibility_mode", false) &&
                (
                    !prefs.getBoolean("flutter.ambient_capture_accessibility_mode_enabled", false) ||
                        !AmbientAccessibilityService.isEnabled
                    )
            ) {
                return reject("accessibility_not_granted")
            }
            if (policy.optBoolean("allow_audio_upload", false) &&
                !prefs.getBoolean("flutter.ambient_capture_raw_audio_upload_enabled", false)
            ) {
                return reject("raw_audio_upload_disabled")
            }
            prefs.edit().putLong("flutter.ambient_capture_last_accepted_sequence", sequence).apply()
            mapOf("accepted" to true, "reason" to "ok", "sequence" to sequence)
        } catch (e: Exception) {
            reject(e.javaClass.simpleName)
        }
    }

    private fun verifyEd25519(payload: ByteArray, signatureB64: String, publicKeyB64: String): Boolean {
        val keyBytes = decodeBase64(publicKeyB64)
        val signatureBytes = decodeBase64(signatureB64)
        val key = KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(keyBytes))
        val verifier = Signature.getInstance("Ed25519")
        verifier.initVerify(key)
        verifier.update(payload)
        return verifier.verify(signatureBytes)
    }

    private fun verifyEs256(payload: ByteArray, signatureB64: String, publicKeyB64: String): Boolean {
        val keyBytes = decodeBase64(publicKeyB64)
        val signatureBytes = decodeBase64(signatureB64)
        val derSignature = if (signatureBytes.size == 64) joseToDer(signatureBytes) else signatureBytes
        val key = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(keyBytes))
        val verifier = Signature.getInstance("SHA256withECDSA")
        verifier.initVerify(key)
        verifier.update(payload)
        return verifier.verify(derSignature)
    }

    private fun decodeBase64(value: String): ByteArray {
        return try {
            Base64.decode(value, Base64.DEFAULT)
        } catch (_: IllegalArgumentException) {
            Base64.decode(value, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
        }
    }

    private fun joseToDer(raw: ByteArray): ByteArray {
        fun trim(bytes: ByteArray): ByteArray {
            var offset = 0
            while (offset < bytes.size - 1 && bytes[offset] == 0.toByte()) offset++
            val needsPad = bytes[offset].toInt() and 0x80 != 0
            val out = bytes.copyOfRange(offset, bytes.size)
            return if (needsPad) byteArrayOf(0) + out else out
        }
        val r = trim(raw.copyOfRange(0, 32))
        val s = trim(raw.copyOfRange(32, 64))
        val length = 2 + r.size + 2 + s.size
        return byteArrayOf(0x30, length.toByte(), 0x02, r.size.toByte()) + r + byteArrayOf(0x02, s.size.toByte()) + s
    }

    private fun reject(reason: String): Map<String, Any?> = mapOf("accepted" to false, "reason" to reason)
}
