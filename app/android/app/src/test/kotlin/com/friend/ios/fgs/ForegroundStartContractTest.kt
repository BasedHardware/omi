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
    fun `cold start uses shortService before dataSync on android 14 through 17`() {
        assertEquals(null, ForegroundStartContract.coldStartType(Build.VERSION_CODES.TIRAMISU))
        for (sdkInt in 34..37) {
            assertEquals(
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_SHORT_SERVICE,
                ForegroundStartContract.coldStartType(sdkInt),
            )
        }
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
