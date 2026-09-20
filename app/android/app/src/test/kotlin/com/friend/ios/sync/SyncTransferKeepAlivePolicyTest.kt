package com.friend.ios.sync

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SyncTransferKeepAlivePolicyTest {

    @Test
    fun `blank notification text falls back to syncing recordings`() {
        assertEquals(
            SyncTransferKeepAlivePolicy.DEFAULT_NOTIFICATION_TEXT,
            SyncTransferKeepAlivePolicy.resolveNotificationText(null),
        )
        assertEquals(
            SyncTransferKeepAlivePolicy.DEFAULT_NOTIFICATION_TEXT,
            SyncTransferKeepAlivePolicy.resolveNotificationText("   "),
        )
        assertEquals(
            "Uploading 3 files",
            SyncTransferKeepAlivePolicy.resolveNotificationText("Uploading 3 files"),
        )
    }

    @Test
    fun `partial wake lock is held only while the transfer service is started`() {
        assertFalse(SyncTransferKeepAlivePolicy.shouldHoldPartialWakeLock(false))
        assertTrue(SyncTransferKeepAlivePolicy.shouldHoldPartialWakeLock(true))
    }

    @Test
    fun `keep-alive uses a dedicated dataSync notification and wake-lock tag`() {
        assertEquals(2003, SyncTransferKeepAlivePolicy.NOTIFICATION_ID)
        assertEquals("omi:sync-transfer", SyncTransferKeepAlivePolicy.WAKE_LOCK_TAG)
        assertEquals("com.friend.ios/sync_transfer", SyncTransferKeepAlivePolicy.METHOD_CHANNEL)
    }
}
