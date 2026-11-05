package com.friend.ios.voice

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build

/**
 * Port of `AudioRoute.isPrivate`: the phone plays into private listening (wired or Bluetooth
 * headphones), where Settings > Assistant > Spoken replies "Headphones only" reads answers aloud.
 */
object AudioRoute {
    fun isPrivate(context: Context): Boolean {
        val audio = context.getSystemService(AudioManager::class.java) ?: return false
        val private = buildSet {
            add(AudioDeviceInfo.TYPE_WIRED_HEADPHONES)
            add(AudioDeviceInfo.TYPE_WIRED_HEADSET)
            add(AudioDeviceInfo.TYPE_BLUETOOTH_A2DP)
            add(AudioDeviceInfo.TYPE_BLUETOOTH_SCO)
            add(AudioDeviceInfo.TYPE_USB_HEADSET)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) add(AudioDeviceInfo.TYPE_BLE_HEADSET)
        }
        return audio.getDevices(AudioManager.GET_DEVICES_OUTPUTS).any { it.type in private }
    }
}
