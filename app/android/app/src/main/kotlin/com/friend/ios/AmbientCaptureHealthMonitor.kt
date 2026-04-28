package com.friend.ios

import android.content.Context
import android.media.AudioManager
import android.media.AudioRecordingConfiguration
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Handler
import android.os.Looper

enum class AmbientHealthState {
    AUDIO_OK,
    AUDIO_SILENCED_BY_SYSTEM,
    AUDIO_LOW_SIGNAL,
    CALL_OR_COMMUNICATION_MODE,
    HIGH_RISK_APP_ACTIVE,
    NETWORK_DOWN_BUFFERING,
    TEXT_ONLY_FALLBACK,
    PRIVATE_MODE,
    PAUSED_BY_USER,
    POLICY_DISABLED,
    PERMISSION_MISSING,
    ACCESSIBILITY_DISABLED,
    SERVICE_KILLED,
    RECOVERY_NEEDED,
    UNKNOWN_DEGRADED,
}

class AmbientCaptureHealthMonitor(private val context: Context, private val onHealth: (Map<String, Any?>) -> Unit) {
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val mainHandler = Handler(Looper.getMainLooper())
    private var lastDbfs = -120.0
    private var lastZeroRatio = 1.0
    private var lowSignalSinceMs: Long? = null
    private var state = AmbientHealthState.UNKNOWN_DEGRADED
    private var networkAvailable = true
    private var socketConnected = false
    private var walQueueDepth = 0
    var silenceThresholdSeconds = 12
    var rmsSilenceDbfsThreshold = -75.0
    var zeroFrameThreshold = 0.98
    var highRiskApps = setOf(
        "com.microsoft.teams",
        "us.zoom.videomeetings",
        "com.google.android.apps.meetings",
        "com.google.android.dialer",
        "com.samsung.android.dialer",
        "com.Slack",
    )

    private val callback = object : AudioManager.AudioRecordingCallback() {
        override fun onRecordingConfigChanged(configs: MutableList<AudioRecordingConfiguration>?) {
            val silenced = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                configs?.any { it.isClientSilenced } == true
            } else {
                false
            }
            if (silenced) setState(AmbientHealthState.AUDIO_SILENCED_BY_SYSTEM, "android_audio_recording_callback")
        }
    }

    fun start() {
        audioManager.registerAudioRecordingCallback(callback, mainHandler)
        evaluate("monitor_started")
    }

    fun stop() {
        audioManager.unregisterAudioRecordingCallback(callback)
    }

    fun updateFlutterState(socketConnected: Boolean?, networkAvailable: Boolean?, walQueueDepth: Int?) {
        if (socketConnected != null) this.socketConnected = socketConnected
        if (networkAvailable != null) this.networkAvailable = networkAvailable
        if (walQueueDepth != null) this.walQueueDepth = walQueueDepth
        evaluate("flutter_state")
    }

    fun updateAudioLevel(dbfs: Double, zeroRatio: Double) {
        lastDbfs = dbfs
        lastZeroRatio = zeroRatio
        evaluate("audio_level")
    }

    fun setPrivateMode() = setState(AmbientHealthState.PRIVATE_MODE, "private_mode")
    fun setPaused() = setState(AmbientHealthState.PAUSED_BY_USER, "paused_by_user")
    fun setPermissionMissing() = setState(AmbientHealthState.PERMISSION_MISSING, "permission_missing")
    fun setServiceKilled() = setState(AmbientHealthState.SERVICE_KILLED, "service_killed")

    fun currentMap(): Map<String, Any?> = mapOf(
        "state" to state.name,
        "dbfs" to lastDbfs,
        "zeroFrameRatio" to lastZeroRatio,
        "audioMode" to audioModeName(audioManager.mode),
        "foregroundPackage" to ForegroundAppDetector.currentPackage,
        "networkAvailable" to networkAvailableNow(),
        "socketConnected" to socketConnected,
        "walQueueDepth" to walQueueDepth,
        "timestamp" to System.currentTimeMillis(),
    )

    private fun evaluate(reason: String) {
        val mode = audioManager.mode
        val foreground = ForegroundAppDetector.currentPackage
        val nowNetwork = networkAvailableNow()
        networkAvailable = nowNetwork

        if (mode == AudioManager.MODE_IN_CALL || mode == AudioManager.MODE_IN_COMMUNICATION) {
            setState(AmbientHealthState.CALL_OR_COMMUNICATION_MODE, reason)
            return
        }
        if (foreground != null && highRiskApps.contains(foreground)) {
            setState(AmbientHealthState.HIGH_RISK_APP_ACTIVE, reason)
            return
        }
        if (!nowNetwork && lastDbfs > rmsSilenceDbfsThreshold) {
            setState(AmbientHealthState.NETWORK_DOWN_BUFFERING, reason)
            return
        }
        val lowSignal = lastDbfs <= rmsSilenceDbfsThreshold || lastZeroRatio >= zeroFrameThreshold
        if (lowSignal) {
            val since = lowSignalSinceMs ?: System.currentTimeMillis().also { lowSignalSinceMs = it }
            if (System.currentTimeMillis() - since >= silenceThresholdSeconds * 1000L) {
                val degraded = if (lastZeroRatio >= zeroFrameThreshold) {
                    AmbientHealthState.AUDIO_SILENCED_BY_SYSTEM
                } else {
                    AmbientHealthState.AUDIO_LOW_SIGNAL
                }
                setState(degraded, reason)
            }
            return
        }
        lowSignalSinceMs = null
        setState(AmbientHealthState.AUDIO_OK, reason)
    }

    private fun setState(next: AmbientHealthState, reason: String) {
        state = next
        onHealth(currentMap() + mapOf("reason" to reason))
    }

    private fun networkAvailableNow(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun audioModeName(mode: Int): String = when (mode) {
        AudioManager.MODE_NORMAL -> "MODE_NORMAL"
        AudioManager.MODE_IN_CALL -> "MODE_IN_CALL"
        AudioManager.MODE_IN_COMMUNICATION -> "MODE_IN_COMMUNICATION"
        AudioManager.MODE_RINGTONE -> "MODE_RINGTONE"
        else -> "MODE_UNKNOWN"
    }
}
