package com.friend.ios

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class CaptureNotificationActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        AmbientCaptureForegroundService.command(context, action)
    }
}
