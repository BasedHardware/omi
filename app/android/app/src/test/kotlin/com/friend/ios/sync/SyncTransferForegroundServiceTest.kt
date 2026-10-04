package com.friend.ios.sync

import android.app.Application
import android.content.Intent
import android.content.ContextWrapper
import android.content.ComponentName
import android.content.pm.ServiceInfo
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowPowerManager

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], manifest = Config.NONE, application = Application::class)
class SyncTransferForegroundServiceTest {
    @Test
    fun `immediate cancellation is queued instead of cancelling an undelivered foreground start`() {
        val context = RuntimeEnvironment.getApplication()
        assertTrue(SyncTransferForegroundService.start(context))
        val start = shadowOf(context).getNextStartedService()
        SyncTransferForegroundService.stop(context)
        val stop = shadowOf(context).getNextStartedService()
        assertEquals(start.component, stop.component)
        assertEquals("com.friend.ios.sync.STOP", stop.action)
        assertNull(shadowOf(context).getNextStoppedService())

        val controller = Robolectric.buildService(SyncTransferForegroundService::class.java).create()
        val service = controller.get()
        assertNotNull(shadowOf(service).lastForegroundNotification)
        service.onStartCommand(start, 0, 1)
        // Cancellation arrived before delivery: promote, then stop without
        // ever acquiring a transfer wake lock.
        assertNull(ShadowPowerManager.getLatestWakeLock())
        service.onStartCommand(stop, 0, 2)
        assertEquals(2, shadowOf(service).stopSelfResultId)
        controller.destroy()
        assertNull(ShadowPowerManager.getLatestWakeLock())
    }

    @Test
    fun `queued stop uses its own id when a later start was already accepted`() {
        val context = RuntimeEnvironment.getApplication()
        assertTrue(SyncTransferForegroundService.start(context))
        val firstStart = shadowOf(context).getNextStartedService()
        SyncTransferForegroundService.stop(context)
        val staleStop = shadowOf(context).getNextStartedService()
        // Android has accepted the newer start before it delivers the old stop.
        assertTrue(SyncTransferForegroundService.start(context))
        val laterStart = shadowOf(context).getNextStartedService()
        val controller = Robolectric.buildService(SyncTransferForegroundService::class.java).create()
        val service = controller.get()
        service.onStartCommand(firstStart, 0, 1)
        val unscopedStopId = shadowOf(service).stopSelfId
        service.onStartCommand(staleStop, 0, 2)
        assertEquals(2, shadowOf(service).stopSelfResultId)
        assertEquals(unscopedStopId, shadowOf(service).stopSelfId)
        assertFalse(shadowOf(service).isForegroundStopped)
        assertTrue(ShadowPowerManager.getLatestWakeLock().isHeld)
        service.onStartCommand(laterStart, 0, 3)
        assertNotNull(shadowOf(service).lastForegroundNotification)
        assertTrue(ShadowPowerManager.getLatestWakeLock().isHeld)
        // Robolectric records stop IDs; Android's ActivityManager decides whether
        // that ID is stale. The companion emulator probe verifies its real result.
        controller.destroy()
        assertFalse(ShadowPowerManager.getLatestWakeLock().isHeld)
    }

    @Test
    fun `dataSync time limit stops the service and releases the wake lock`() {
        val context = RuntimeEnvironment.getApplication()
        assertTrue(SyncTransferForegroundService.start(context))
        val start = shadowOf(context).getNextStartedService()
        val controller = Robolectric.buildService(SyncTransferForegroundService::class.java).create()
        val service = controller.get()
        service.onStartCommand(start, 0, 1)
        assertTrue(ShadowPowerManager.getLatestWakeLock().isHeld)

        service.onTimeout(1, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)

        assertTrue(shadowOf(service).isStoppedBySelf)
        assertTrue(shadowOf(service).isForegroundStopped)
        assertFalse(ShadowPowerManager.getLatestWakeLock().isHeld)
        controller.destroy()
    }

    @Test
    fun `shortService time limit stops the service`() {
        val controller = Robolectric.buildService(SyncTransferForegroundService::class.java).create()
        val service = controller.get()

        service.onTimeout(1)

        assertTrue(shadowOf(service).isStoppedBySelf)
        assertTrue(shadowOf(service).isForegroundStopped)
        controller.destroy()
    }

    @Test
    fun `rejected background stop remains cancelled until the pending start promotes`() {
        val context = RuntimeEnvironment.getApplication()
        assertTrue(SyncTransferForegroundService.start(context))
        val start = shadowOf(context).getNextStartedService()
        val rejectingContext = object : ContextWrapper(context) {
            override fun startService(intent: Intent): ComponentName? {
                throw IllegalStateException("Background service start denied")
            }
        }
        SyncTransferForegroundService.stop(rejectingContext)
        val controller = Robolectric.buildService(SyncTransferForegroundService::class.java).create()
        val service = controller.get()
        service.onStartCommand(start, 0, 1)
        assertNotNull(shadowOf(service).lastForegroundNotification)
        assertEquals(1, shadowOf(service).stopSelfResultId)
        assertNull(ShadowPowerManager.getLatestWakeLock())
        controller.destroy()
    }
}
