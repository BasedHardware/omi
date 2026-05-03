package com.omi.ambientcompanion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class RecoveryBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != Intent.ACTION_BOOT_COMPLETED) return
        AuditLog(context).record("boot_completed_cleanup")
        AppPrefs(context).explicitSessionStarted = false
    }
}
