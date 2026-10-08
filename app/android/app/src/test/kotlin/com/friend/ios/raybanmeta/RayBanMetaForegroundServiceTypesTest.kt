package com.friend.ios.raybanmeta

import android.content.pm.ServiceInfo
import android.app.Application
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/** Flavor-independent: the service is promoted only with the types a session actually uses. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], manifest = Config.NONE, application = Application::class)
class RayBanMetaForegroundServiceTypesTest {

    private val mic = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
    private val device = ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE

    private fun types(microphone: Boolean, connectedDevice: Boolean, recordAudio: Boolean = true, btConnect: Boolean = true) =
        RayBanMetaForegroundService.serviceTypes(microphone, connectedDevice, recordAudio, btConnect)

    @Test
    fun `audio-only session claims only the microphone type`() {
        assertEquals(mic, types(microphone = true, connectedDevice = false))
    }

    @Test
    fun `camera-only session never asks for the microphone type`() {
        assertEquals(device, types(microphone = false, connectedDevice = true))
        // Even without RECORD_AUDIO, a camera-only session can still promote.
        assertEquals(device, types(microphone = false, connectedDevice = true, recordAudio = false))
    }

    @Test
    fun `audio plus camera claims both`() {
        assertEquals(mic or device, types(microphone = true, connectedDevice = true))
    }

    @Test
    fun `a type whose runtime permission is missing is dropped, leaving nothing to promote`() {
        assertEquals(0, types(microphone = true, connectedDevice = false, recordAudio = false))
        assertEquals(0, types(microphone = false, connectedDevice = true, btConnect = false))
    }
}
