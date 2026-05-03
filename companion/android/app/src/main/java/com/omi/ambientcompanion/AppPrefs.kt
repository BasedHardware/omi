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

    var audioSpoolUrl: String
        get() = prefs.getString("audio_spool_url", "") ?: ""
        set(value) = prefs.edit().putString("audio_spool_url", value).apply()

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

    var deleteSyncedAudio: Boolean
        get() = prefs.getBoolean("delete_synced_audio", true)
        set(value) = prefs.edit().putBoolean("delete_synced_audio", value).apply()

    var silenceDetectionSeconds: Int
        get() = prefs.getInt("silence_detection_seconds", 12)
        set(value) = prefs.edit().putInt("silence_detection_seconds", value).apply()

    var rmsSilenceDbfsThreshold: Float
        get() = prefs.getFloat("rms_silence_dbfs_threshold", -60f)
        set(value) = prefs.edit().putFloat("rms_silence_dbfs_threshold", value).apply()

    var zeroFrameThreshold: Float
        get() = prefs.getFloat("zero_frame_threshold", 0.98f)
        set(value) = prefs.edit().putFloat("zero_frame_threshold", value).apply()

    var allowAudioUpload: Boolean
        get() = prefs.getBoolean("allow_audio_upload", true)
        set(value) = prefs.edit().putBoolean("allow_audio_upload", value).apply()

    var allowCaptionFallback: Boolean
        get() = prefs.getBoolean("allow_caption_fallback", true)
        set(value) = prefs.edit().putBoolean("allow_caption_fallback", value).apply()

    var allowLocalSttFallback: Boolean
        get() = prefs.getBoolean("allow_local_stt_fallback", true)
        set(value) = prefs.edit().putBoolean("allow_local_stt_fallback", value).apply()

    var syncFailureCount: Int
        get() = prefs.getInt("sync_failure_count", 0)
        set(value) = prefs.edit().putInt("sync_failure_count", value).apply()

    var nextSyncAfterMs: Long
        get() = prefs.getLong("next_sync_after_ms", 0)
        set(value) = prefs.edit().putLong("next_sync_after_ms", value).apply()
}
