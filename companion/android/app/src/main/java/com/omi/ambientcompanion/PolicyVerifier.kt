package com.omi.ambientcompanion

import android.util.Base64
import org.json.JSONObject
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.time.Instant

class PolicyVerifier(private val prefs: AppPrefs) {
    fun verify(envelope: JSONObject): PolicyVerifyResult {
        val payloadJson = envelope.optString("payload")
        val signature = envelope.optString("signature")
        val keyId = envelope.optString("key_id")
        if (payloadJson.isBlank() || signature.isBlank()) return PolicyVerifyResult(false, "missing_payload")
        if (keyId != prefs.controllerKeyId) return PolicyVerifyResult(false, "wrong_key_id")
        if (prefs.controllerPublicKey.isBlank()) return PolicyVerifyResult(false, "missing_pinned_key")
        if (!verifySignature(payloadJson, signature, prefs.controllerPublicKey)) {
            return PolicyVerifyResult(false, "signature_invalid")
        }
        val payload = JSONObject(payloadJson)
        if (payload.optString("plugin_id") != PLUGIN_ID) return PolicyVerifyResult(false, "wrong_plugin")
        if (payload.optString("scope") != "ambient_capture_controller") return PolicyVerifyResult(false, "wrong_scope")
        if (payload.optString("user_id") != prefs.omiUserId) return PolicyVerifyResult(false, "wrong_user")
        if (payload.optString("device_id") != prefs.deviceId) return PolicyVerifyResult(false, "wrong_device")
        val sequence = payload.optLong("sequence", 0)
        if (sequence <= prefs.lastAcceptedSequence) return PolicyVerifyResult(false, "replayed_sequence")
        val now = Instant.now()
        val issuedAt = Instant.parse(payload.optString("issued_at"))
        val validUntil = Instant.parse(payload.optString("valid_until"))
        if (validUntil <= now) return PolicyVerifyResult(false, "expired")
        if (issuedAt.isAfter(now.plusSeconds(300))) return PolicyVerifyResult(false, "issued_in_future")
        prefs.silenceDetectionSeconds = payload.optInt("silence_detection_seconds", prefs.silenceDetectionSeconds)
        prefs.rmsSilenceDbfsThreshold = payload.optDouble(
            "rms_silence_dbfs_threshold",
            prefs.rmsSilenceDbfsThreshold.toDouble(),
        ).toFloat()
        prefs.zeroFrameThreshold = payload.optDouble("zero_frame_threshold", prefs.zeroFrameThreshold.toDouble()).toFloat()
        prefs.allowAudioUpload = payload.optBoolean("allow_audio_upload", prefs.allowAudioUpload)
        prefs.allowLocalSttFallback = payload.optBoolean("allow_local_stt_fallback", prefs.allowLocalSttFallback)
        prefs.allowCaptionFallback = payload.optBoolean("allow_caption_fallback", prefs.allowCaptionFallback)
        prefs.lastAcceptedSequence = sequence
        return PolicyVerifyResult(true, "ok", payload)
    }

    private fun verifySignature(payloadJson: String, signatureB64Url: String, publicKeyB64: String): Boolean {
        return try {
            val publicBytes = Base64.decode(publicKeyB64, Base64.DEFAULT)
            val key = KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(publicBytes))
            val verifier = Signature.getInstance("Ed25519")
            verifier.initVerify(key)
            verifier.update(payloadJson.toByteArray(Charsets.UTF_8))
            verifier.verify(b64UrlDecode(signatureB64Url))
        } catch (_: Throwable) {
            false
        }
    }

    private fun b64UrlDecode(value: String): ByteArray {
        val padded = value + "=".repeat((4 - value.length % 4) % 4)
        return Base64.decode(padded, Base64.URL_SAFE or Base64.NO_WRAP)
    }

    companion object {
        const val PLUGIN_ID = "ambient_second_brain_controller"
    }
}

data class PolicyVerifyResult(
    val accepted: Boolean,
    val reason: String,
    val payload: JSONObject? = null,
)
