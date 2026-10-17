package com.friend.ios.wear

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.BatteryManager
import android.os.Build
import android.os.SystemClock
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.watch.WatchInfo
import com.friend.ios.core.watch.WatchMessage
import com.friend.ios.core.watch.WatchPhoneState
import com.friend.ios.core.watch.WatchStopReason
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Port of `WatchRecorder.swift`: one recording at a time from the watch microphone, streamed to
 * the Omi phone app. The phone can also start and stop it, or refuse it (then `notice` says why).
 * Lives as long as the process (`OmiWatchApp`), on the main thread like `@MainActor`.
 */
class WatchRecorder(context: Context, private val connection: WatchConnection, private val scope: CoroutineScope) {
    sealed interface Phase {
        data object Idle : Phase
        data object Starting : Phase
        /** [sinceElapsed]: `SystemClock.elapsedRealtime()` when the microphone started. */
        data class Recording(val sinceElapsed: Long) : Phase
    }

    enum class Notice { MicrophoneDenied, MicrophoneFailed, PhoneBusy, PhoneSignedOut, PhoneFailed }

    private val context = context.applicationContext

    var phase: Phase by mutableStateOf(Phase.Idle)
        private set
    var notice: Notice? by mutableStateOf(null)
        private set
    /** What the phone reported last (capture and the Omi's battery). */
    var phone: WatchPhoneState? by mutableStateOf(null)
        private set

    /**
     * Asks for the microphone with the system dialog; set by `MainActivity` while it is on screen.
     * Without it a missing permission counts as denied (iOS asks from anywhere).
     */
    var permissionRequester: (suspend () -> Boolean)? = null

    private val microphone = WatchMicrophone { chunk -> connection.send(WatchMessage.AudioChunk(chunk)) }

    init {
        connection.activate()
        scope.launch { connection.messages.collect { handle(it) } }
        scope.launch { connection.phoneStates.collect { state -> if (state != null) phone = state } }
        scope.launch {
            sendWatchInfo()
            while (isActive) {
                sendBattery()
                delay(BATTERY_INTERVAL_MILLIS)
            }
        }
    }

    val isRecording: Boolean get() = phase != Phase.Idle

    fun toggle() {
        if (isRecording) stop(notifyPhone = true) else scope.launch { start() }
    }

    suspend fun start() {
        if (phase != Phase.Idle) return
        notice = null
        phase = Phase.Starting
        if (!microphonePermission()) {
            phase = Phase.Idle
            notice = Notice.MicrophoneDenied
            connection.send(WatchMessage.RecordingError("Microphone permission denied"))
            return
        }
        // Before any audio: the phone opens the conversation on `startRecording`.
        connection.beginRecording()
        connection.send(WatchMessage.StartRecording)
        try {
            RecordingService.start(context)
            microphone.start()
        } catch (error: Exception) {
            RecordingService.stop(context)
            phase = Phase.Idle
            notice = Notice.MicrophoneFailed
            connection.send(WatchMessage.RecordingError("Microphone unavailable"))
            connection.send(WatchMessage.StopRecording(null))
            return
        }
        phase = Phase.Recording(SystemClock.elapsedRealtime())
        play(VibrationEffect.EFFECT_HEAVY_CLICK)
    }

    /** [notifyPhone]: false when the phone itself asked to stop. */
    fun stop(notifyPhone: Boolean, reason: WatchStopReason? = null) {
        if (phase !is Phase.Recording) return
        microphone.stop()
        if (notifyPhone) connection.send(WatchMessage.StopRecording(null)) else connection.endRecording()
        RecordingService.stop(context)
        phase = Phase.Idle
        notice = reason?.let(::notice)
        play(VibrationEffect.EFFECT_DOUBLE_CLICK)
    }

    private suspend fun handle(message: WatchMessage) {
        when (message) {
            WatchMessage.StartRecording -> start()
            is WatchMessage.StopRecording -> stop(notifyPhone = false, reason = message.reason)
            WatchMessage.RequestMicrophonePermission -> {
                val granted = microphonePermission()
                connection.send(WatchMessage.MicrophonePermissionResult(granted))
            }
            WatchMessage.RequestBattery -> sendBattery()
            WatchMessage.RequestWatchInfo -> sendWatchInfo()
            is WatchMessage.AudioChunk, is WatchMessage.RecordingError, is WatchMessage.MicrophonePermissionResult,
            is WatchMessage.BatteryUpdate, is WatchMessage.WatchInfoUpdate,
            -> Unit
        }
    }

    private suspend fun microphonePermission(): Boolean {
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) return true
        return permissionRequester?.invoke() ?: false
    }

    private fun sendBattery() {
        val battery = context.getSystemService(BatteryManager::class.java) ?: return
        val level = battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        // `WKInterfaceDeviceBatteryState`: unknown 0, unplugged 1, charging 2, full 3.
        val state = when {
            level !in 0..100 -> 0
            battery.isCharging && level >= 100 -> 3
            battery.isCharging -> 2
            else -> 1
        }
        if (level in 0..100) connection.send(WatchMessage.BatteryUpdate(level.toDouble(), state))
    }

    private fun sendWatchInfo() {
        val name = Settings.Global.getString(context.contentResolver, Settings.Global.DEVICE_NAME) ?: Build.MODEL
        connection.send(WatchMessage.WatchInfoUpdate(WatchInfo(name, Build.MODEL, Build.VERSION.RELEASE, "Wear OS")))
    }

    /** `WKInterfaceDevice.play(.start / .stop)`. */
    private fun play(effect: Int) {
        runCatching { context.getSystemService(Vibrator::class.java)?.vibrate(VibrationEffect.createPredefined(effect)) }
    }

    /** Debug launch extras (`MainActivity`): show a state without a phone. */
    internal fun preview(notice: Notice?, phone: WatchPhoneState?) {
        this.notice = notice
        if (phone != null) this.phone = phone
    }

    companion object {
        /** How often the watch battery goes to the phone (Flutter: 3 minutes). */
        private const val BATTERY_INTERVAL_MILLIS = 180_000L

        private fun notice(reason: WatchStopReason): Notice = when (reason) {
            WatchStopReason.Busy -> Notice.PhoneBusy
            WatchStopReason.SignedOut -> Notice.PhoneSignedOut
            WatchStopReason.Failed -> Notice.PhoneFailed
        }
    }
}
