package com.omi.ambientcompanion

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.AudioRecordingConfiguration
import android.os.Build
import android.os.Handler
import android.os.Looper

class CommunicationStateMonitor(
    context: Context,
    private val onHealth: (HealthEvent) -> Unit,
) {
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val handler = Handler(Looper.getMainLooper())
    private val recordingCallback = object : AudioManager.AudioRecordingCallback() {
        override fun onRecordingConfigChanged(configs: MutableList<AudioRecordingConfiguration>?) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && configs?.any { it.isClientSilenced } == true) {
                onHealth(HealthEvent(AmbientHealthState.AUDIO_SILENCED_BY_SYSTEM, "android_client_silenced", ContextSignals.foregroundPackage))
            }
        }
    }

    fun start() {
        audioManager.registerAudioRecordingCallback(recordingCallback, handler)
        evaluate()
    }

    fun stop() {
        runCatching { audioManager.unregisterAudioRecordingCallback(recordingCallback) }
    }

    fun evaluate() {
        val mode = audioManager.mode
        if (mode == AudioManager.MODE_IN_CALL || mode == AudioManager.MODE_IN_COMMUNICATION) {
            onHealth(
                HealthEvent(
                    AmbientHealthState.COMMUNICATION_MODE_DEGRADED,
                    if (mode == AudioManager.MODE_IN_CALL) "mode_in_call" else "mode_in_communication",
                    ContextSignals.foregroundPackage,
                )
            )
        }
        val routed = audioManager.getDevices(AudioManager.GET_DEVICES_INPUTS + AudioManager.GET_DEVICES_OUTPUTS)
        if (routed.any { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO || it.type == AudioDeviceInfo.TYPE_BLE_HEADSET }) {
            ContextSignals.lastTriggerReason = "bluetooth_headset"
        }
    }
}
