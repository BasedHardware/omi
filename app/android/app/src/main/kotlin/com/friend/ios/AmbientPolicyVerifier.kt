package com.friend.ios

import android.util.Base64
import java.security.KeyFactory
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.time.Instant

object AmbientPolicyVerifier {
    fun verify(args: Map<*, *>): Map<String, Any?> {
        return try {
            val payload = args["payload"] as? String ?: return reject("missing_payload")
            val signatureB64 = args["signature"] as? String ?: return reject("missing_signature")
            val publicKeyB64 = args["publicKey"] as? String ?: return reject("missing_public_key")
            val valid = verifyEd25519(payload.toByteArray(Charsets.UTF_8), signatureB64, publicKeyB64)
            if (!valid) return reject("signature_invalid")
            val validUntil = Regex("\"valid_until\"\\s*:\\s*\"([^\"]+)\"").find(payload)?.groupValues?.get(1)
            if (validUntil != null && Instant.parse(validUntil).isBefore(Instant.now())) return reject("expired")
            mapOf("accepted" to true, "reason" to "ok")
        } catch (e: Exception) {
            reject(e.javaClass.simpleName)
        }
    }

    private fun verifyEd25519(payload: ByteArray, signatureB64: String, publicKeyB64: String): Boolean {
        val keyBytes = Base64.decode(publicKeyB64, Base64.DEFAULT)
        val signatureBytes = Base64.decode(signatureB64, Base64.DEFAULT)
        val key = KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(keyBytes))
        val verifier = Signature.getInstance("Ed25519")
        verifier.initVerify(key)
        verifier.update(payload)
        return verifier.verify(signatureBytes)
    }

    private fun reject(reason: String): Map<String, Any?> = mapOf("accepted" to false, "reason" to reason)
}
