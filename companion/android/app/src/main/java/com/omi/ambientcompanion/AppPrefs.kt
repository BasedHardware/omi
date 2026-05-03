package com.omi.ambientcompanion

import android.content.Context
import java.util.UUID

class AppPrefs(context: Context) {
    private val prefs = context.getSharedPreferences("ambient_companion", Context.MODE_PRIVATE)

    var pluginBaseUrl: String
        get() = prefs.getString("plugin_base_url", "") ?: ""
        set(value) = prefs.edit().putString("plugin_base_url", value.trimEnd('/')).apply()

    var omiUserId: String
        get() = prefs.getString("omi_user_id", "") ?: ""
        set(value) = prefs.edit().putString("omi_user_id", value).apply()

    var appInstallId: String
        get() {
            val existing = prefs.getString("app_install_id", "") ?: ""
            if (existing.isNotBlank()) return existing
            val created = UUID.randomUUID().toString()
            prefs.edit().putString("app_install_id", created).apply()
            return created
        }
        set(value) = prefs.edit().putString("app_install_id", value).apply()

    var deviceId: String
        get() = prefs.getString("device_id", "") ?: ""
        set(value) = prefs.edit().putString("device_id", value).apply()

    var controllerKeyId: String
        get() = prefs.getString("controller_key_id", "") ?: ""
        set(value) = prefs.edit().putString("controller_key_id", value).apply()

    var controllerPublicKey: String
        get() = prefs.getString("controller_public_key", "") ?: ""
        set(value) = prefs.edit().putString("controller_public_key", value).apply()

    var policyUrl: String
        get() = prefs.getString("policy_url", "") ?: ""
        set(value) = prefs.edit().putString("policy_url", value).apply()

    var telemetryUrl: String
        get() = prefs.getString("telemetry_url", "") ?: ""
        set(value) = prefs.edit().putString("telemetry_url", value).apply()

    var fallbackSegmentsUrl: String
        get() = prefs.getString("fallback_segments_url", "") ?: ""
        set(value) = prefs.edit().putString("fallback_segments_url", value).apply()

    var lastAcceptedSequence: Long
        get() = prefs.getLong("last_accepted_sequence", 0)
        set(value) = prefs.edit().putLong("last_accepted_sequence", value).apply()

    var explicitSessionStarted: Boolean
        get() = prefs.getBoolean("explicit_session_started", false)
        set(value) = prefs.edit().putBoolean("explicit_session_started", value).apply()

    var maxStorageMb: Int
        get() = prefs.getInt("max_storage_mb", 1024)
        set(value) = prefs.edit().putInt("max_storage_mb", value).apply()

    var minFreeStorageMb: Int
        get() = prefs.getInt("min_free_storage_mb", 512)
        set(value) = prefs.edit().putInt("min_free_storage_mb", value).apply()
}
