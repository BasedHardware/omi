package com.omi.ambientcompanion

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

class NotificationContextService : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        sbn ?: return
        val extras = sbn.notification.extras
        val title = extras.getCharSequence("android.title")?.toString().orEmpty()
        val text = extras.getCharSequence("android.text")?.toString().orEmpty()
        val subText = extras.getCharSequence("android.subText")?.toString().orEmpty()
        val bigText = extras.getCharSequence("android.bigText")?.toString().orEmpty()
        ContextSignals.triggerFromNotification(this, sbn.packageName, title, text, subText, bigText)
    }

    override fun onListenerConnected() {
        AuditLog(this).record("notification_listener_connected")
    }

    override fun onListenerDisconnected() {
        AuditLog(this).record("notification_listener_disconnected")
    }
}
