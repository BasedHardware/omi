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
    STORAGE_LIMIT_REACHED,
    SERVICE_RUNNING_BUT_NO_FLUTTER_LISTENER,
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
    private var lastAudioChunkAtMs = 0L
    private var lastEmittedState: AmbientHealthState? = null
    private var lastHeartbeatAtMs = 0L
    private var watchdog: Runnable? = null
    var silenceThresholdSeconds = 12
    var rmsSilenceDbfsThreshold = -75.0
    var zeroFrameThreshold = 0.98
    var communicationMode = "detect_only"
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
        lastAudioChunkAtMs = System.currentTimeMillis()
        lowSignalSinceMs = null
        setState(AmbientHealthState.UNKNOWN_DEGRADED, "monitor_started")
        startWatchdog()
        evaluate("monitor_started")
    }

    fun stop() {
        audioManager.unregisterAudioRecordingCallback(callback)
        watchdog?.let { mainHandler.removeCallbacks(it) }
        watchdog = null
    }

    fun updateFlutterState(socketConnected: Boolean?, networkAvailable: Boolean?, walQueueDepth: Int?) {
        if (socketConnected != null) this.socketConnected = socketConnected
        if (networkAvailable != null) this.networkAvailable = networkAvailable
        if (walQueueDepth != null) this.walQueueDepth = walQueueDepth
        evaluate("flutter_state")
    }

    fun updateAudioLevel(dbfs: Double, zeroRatio: Double) {
        lastAudioChunkAtMs = System.currentTimeMillis()
        lastDbfs = dbfs
        lastZeroRatio = zeroRatio
        evaluate("audio_level")
    }

    fun setPrivateMode() = setState(AmbientHealthState.PRIVATE_MODE, "private_mode")
    fun setPaused() = setState(AmbientHealthState.PAUSED_BY_USER, "paused_by_user")
    fun setPermissionMissing() = setState(AmbientHealthState.PERMISSION_MISSING, "permission_missing")
    fun setServiceKilled() = setState(AmbientHealthState.SERVICE_KILLED, "service_killed")
    fun setPolicyDisabled(reason: String) = setState(AmbientHealthState.POLICY_DISABLED, reason)
    fun setStorageLimitReached(reason: String) = setState(AmbientHealthState.STORAGE_LIMIT_REACHED, reason)
    fun setNoFlutterListener() =
        setState(AmbientHealthState.SERVICE_RUNNING_BUT_NO_FLUTTER_LISTENER, "native_spool_no_flutter_listener")

    fun applyPolicy(policy: Map<String, Any?>) {
        silenceThresholdSeconds = (policy["silence_detection_seconds"] as? Number)?.toInt() ?: silenceThresholdSeconds
        rmsSilenceDbfsThreshold =
            (policy["rms_silence_dbfs_threshold"] as? Number)?.toDouble() ?: rmsSilenceDbfsThreshold
        zeroFrameThreshold = (policy["zero_frame_threshold"] as? Number)?.toDouble() ?: zeroFrameThreshold
        communicationMode = policy["communication_mode"]?.toString() ?: communicationMode
        val apps = policy["high_risk_apps"] as? List<*>
        if (apps != null) highRiskApps = apps.mapNotNull { it?.toString() }.toSet()
        evaluate("policy_applied")
    }

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

        if (communicationMode != "off" && (mode == AudioManager.MODE_IN_CALL || mode == AudioManager.MODE_IN_COMMUNICATION)) {
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
        val now = System.currentTimeMillis()
        val shouldEmit = next != lastEmittedState || now - lastHeartbeatAtMs >= HEARTBEAT_MS
        if (!shouldEmit) return
        lastEmittedState = next
        lastHeartbeatAtMs = now
        onHealth(currentMap() + mapOf("reason" to reason))
    }

    private fun startWatchdog() {
        watchdog?.let { mainHandler.removeCallbacks(it) }
        watchdog = Runnable {
            val ageMs = System.currentTimeMillis() - lastAudioChunkAtMs
            if (ageMs > NO_AUDIO_WATCHDOG_MS) {
                setState(AmbientHealthState.RECOVERY_NEEDED, "no_audio_chunks_received")
            } else {
                evaluate("watchdog")
            }
            watchdog?.let { mainHandler.postDelayed(it, WATCHDOG_INTERVAL_MS) }
        }
        watchdog?.let { mainHandler.postDelayed(it, WATCHDOG_INTERVAL_MS) }
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

    companion object {
        private const val HEARTBEAT_MS = 20_000L
        private const val WATCHDOG_INTERVAL_MS = 5_000L
        private const val NO_AUDIO_WATCHDOG_MS = 15_000L
    }
}
