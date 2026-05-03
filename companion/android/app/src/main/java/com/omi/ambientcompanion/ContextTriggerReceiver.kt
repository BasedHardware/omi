package com.omi.ambientcompanion

import android.bluetooth.BluetoothAdapter
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.media.AudioManager

class ContextTriggerReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        when (intent?.action) {
            Intent.ACTION_HEADSET_PLUG -> {
                val state = intent.getIntExtra("state", -1)
                if (state == 1) ContextSignals.triggerFromAudioRoute(context, "wired_headset_connected")
            }
            BluetoothAdapter.ACTION_CONNECTION_STATE_CHANGED -> {
                val state = intent.getIntExtra(BluetoothAdapter.EXTRA_CONNECTION_STATE, BluetoothAdapter.ERROR)
                if (state == BluetoothAdapter.STATE_CONNECTED) {
                    ContextSignals.triggerFromAudioRoute(context, "bluetooth_audio_connected")
                }
            }
            AudioManager.ACTION_SCO_AUDIO_STATE_UPDATED -> {
                val state = intent.getIntExtra(AudioManager.EXTRA_SCO_AUDIO_STATE, AudioManager.SCO_AUDIO_STATE_ERROR)
                if (state == AudioManager.SCO_AUDIO_STATE_CONNECTED) {
                    ContextSignals.triggerFromAudioRoute(context, "bluetooth_sco_connected")
                }
            }
        }
    }
}
