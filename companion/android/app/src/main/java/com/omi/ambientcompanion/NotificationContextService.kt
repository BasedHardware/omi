package com.omi.ambientcompanion

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

class NotificationContextService : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        sbn ?: return
        val extras = sbn.notification.extras
        val title = extras.getCharSequence("android.title")?.toString().orEmpty()
        val text = extras.getCharSequence("android.text")?.toString().orEmpty()
        ContextSignals.triggerFromNotification(this, sbn.packageName, title, text)
    }
}
