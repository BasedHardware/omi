package com.friend.ios.sync

import android.app.Application
import android.content.Intent
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
        val wakeLock = ShadowPowerManager.getLatestWakeLock()
        assertTrue(wakeLock.isHeld)
        service.onStartCommand(stop, 0, 2)
        assertEquals(2, shadowOf(service).stopSelfResultId)
        controller.destroy()
        assertFalse(wakeLock.isHeld)
    }

    @Test
    fun `queued stop is scoped to its start id and a later start keeps the service promoted`() {
        val context = RuntimeEnvironment.getApplication()
        val controller = Robolectric.buildService(SyncTransferForegroundService::class.java).create()
        val service = controller.get()
        service.onStartCommand(Intent(), 0, 1)
        SyncTransferForegroundService.stop(context)
        service.onStartCommand(shadowOf(context).getNextStartedService(), 0, 2)
        assertEquals(2, shadowOf(service).stopSelfResultId)
        service.onStartCommand(Intent(), 0, 3)
        assertNotNull(shadowOf(service).lastForegroundNotification)
        assertTrue(ShadowPowerManager.getLatestWakeLock().isHeld)
        controller.destroy()
        assertFalse(ShadowPowerManager.getLatestWakeLock().isHeld)
    }
}
