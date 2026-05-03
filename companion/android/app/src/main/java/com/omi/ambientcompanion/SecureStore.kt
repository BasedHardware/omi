package com.omi.ambientcompanion

import android.content.Context
import android.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec

class SecureStore(private val context: Context) {
    private val prefs = context.getSharedPreferences("ambient_secure", Context.MODE_PRIVATE)

    fun putSecret(name: String, value: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, KeystoreAes.getOrCreate(KEY_ALIAS))
        val payload = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(name, Base64.encodeToString(payload, Base64.NO_WRAP)).apply()
    }

    fun getSecret(name: String): String {
        val encoded = prefs.getString(name, "") ?: ""
        if (encoded.isBlank()) return ""
        val bytes = Base64.decode(encoded, Base64.NO_WRAP)
        if (bytes.size <= IV_BYTES) return ""
        val iv = bytes.copyOfRange(0, IV_BYTES)
        val data = bytes.copyOfRange(IV_BYTES, bytes.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, KeystoreAes.getOrCreate(KEY_ALIAS), GCMParameterSpec(TAG_BITS, iv))
        return cipher.doFinal(data).toString(Charsets.UTF_8)
    }

    companion object {
        private const val KEY_ALIAS = "omi_ambient_companion_key"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val IV_BYTES = 12
        private const val TAG_BITS = 128
    }
}
