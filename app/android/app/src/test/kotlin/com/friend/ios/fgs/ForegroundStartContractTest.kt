package com.friend.ios.fgs

import android.os.Build
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ForegroundStartContractTest {

    @Test
    fun `android 14 and newer must promote shortService before stop`() {
        assertFalse(ForegroundStartContract.mustPromoteShortServiceBeforeStop(Build.VERSION_CODES.TIRAMISU))
        assertTrue(ForegroundStartContract.mustPromoteShortServiceBeforeStop(Build.VERSION_CODES.UPSIDE_DOWN_CAKE))
        assertTrue(ForegroundStartContract.mustPromoteShortServiceBeforeStop(Build.VERSION_CODES.VANILLA_ICE_CREAM))
    }

    @Test
    fun `missing application icon does not reach startForeground as zero`() {
        assertEquals(42, ForegroundStartContract.notificationIcon(42))
        assertEquals(
            android.R.drawable.stat_notify_sync,
            ForegroundStartContract.notificationIcon(0),
        )
    }
}
