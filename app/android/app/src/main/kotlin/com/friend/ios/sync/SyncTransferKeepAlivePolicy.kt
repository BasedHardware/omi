package com.friend.ios.sync

/**
 * Constants and pure policy for the recording-transfer keep-alive.
 *
 * The service holds a dataSync FGS + PARTIAL_WAKE_LOCK only while Dart reports
 * an in-flight BLE/cloud transfer (#5221). Lifetime decisions live here so
 * they can be unit-tested without Robolectric.
 */
internal object SyncTransferKeepAlivePolicy {
    const val METHOD_CHANNEL = "com.friend.ios/sync_transfer"
    const val NOTIFICATION_CHANNEL_ID = "omi_sync_transfer_channel"
    const val NOTIFICATION_CHANNEL_NAME = "Omi Recording Sync"
    const val NOTIFICATION_ID = 2003 // BLE 2001, phone-mic 2002
    const val WAKE_LOCK_TAG = "omi:sync-transfer"
    const val DEFAULT_NOTIFICATION_TITLE = "Omi"
    const val DEFAULT_NOTIFICATION_TEXT = "Syncing recordings"

    fun resolveNotificationText(requested: String?): String {
        val trimmed = requested?.trim().orEmpty()
        return trimmed.ifEmpty { DEFAULT_NOTIFICATION_TEXT }
    }

    /** CPU stay-awake tracks the service itself, not Activity foreground. */
    fun shouldHoldPartialWakeLock(serviceStarted: Boolean): Boolean = serviceStarted
}
