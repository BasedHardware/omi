package com.friend.ios.raybanmeta

import android.Manifest
import android.app.Application
import com.friend.ios.FlutterError
import com.friend.ios.RayBanMetaFlutterAPI
import io.flutter.plugin.common.BinaryMessenger
import java.nio.ByteBuffer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * Compiled only for the dev/prod flavors (src/testNoDat), which link the
 * toolkit-free src/noDat factory, so this pins the labeled audio-only
 * contract the shared Dart layer relies on: no toolkit, no faked camera, and
 * never a phone-mic fallback when the glasses' HFP input is absent.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], manifest = Config.NONE, application = Application::class)
class RayBanMetaHostApiImplTest {

    private object NoopMessenger : BinaryMessenger {
        override fun send(channel: String, message: ByteBuffer?) {}
        override fun send(channel: String, message: ByteBuffer?, callback: BinaryMessenger.BinaryReply?) {}
        override fun setMessageHandler(channel: String, handler: BinaryMessenger.BinaryMessageHandler?) {}
    }

    private val context = RuntimeEnvironment.getApplication()

    private fun hostApi() = RayBanMetaHostApiImpl(context, RayBanMetaFlutterAPI(NoopMessenger)) { null }

    private fun expectFlutterError(code: String, block: () -> Unit) {
        try {
            block()
            fail("expected FlutterError($code)")
        } catch (e: FlutterError) {
            assertEquals(code, e.code)
        }
    }

    @Test
    fun `default flavor reports audio-only with no registration`() {
        val api = hostApi()
        assertEquals("audio_only", api.getAvailabilityMode())
        assertEquals("unavailable", api.getRegistrationState())
        expectFlutterError("dat_unavailable") { api.startRegistration() }
    }

    @Test
    fun `camera calls report unavailable instead of faking a camera`() {
        val api = hostApi()
        var permission: String? = null
        api.getCameraPermissionStatus { permission = it.getOrNull() }
        assertEquals("unavailable", permission)
        api.requestCameraPermission { permission = it.getOrNull() }
        assertEquals("unavailable", permission)
        var glasses: Int? = null
        api.getAvailableGlasses { glasses = it.getOrNull()?.size }
        assertEquals(0, glasses)
        var startError: Throwable? = null
        api.startCamera { startError = it.exceptionOrNull() }
        assertEquals("camera_unavailable", (startError as? FlutterError)?.code)
        expectFlutterError("camera_unavailable") { api.capturePhoto() }
    }

    @Test
    fun `audio capture without microphone permission fails before touching the route`() {
        val api = hostApi()
        expectFlutterError("audio_start_failed") { api.startAudioCapture(null) }
        assertNull(shadowOf(context).nextStartedService)
    }

    @Test
    fun `audio capture never falls back to the phone mic when no HFP input is connected`() {
        shadowOf(context).grantPermissions(Manifest.permission.RECORD_AUDIO)
        val api = hostApi()
        assertTrue(api.getBluetoothHfpInputs().isEmpty())
        expectFlutterError("audio_start_failed") { api.startAudioCapture("AA:BB:CC:DD:EE:FF") }
        expectFlutterError("audio_start_failed") { api.startAudioCapture(null) }
        assertEquals(false, api.isGlassesAudioRouteActive())
        assertEquals("disconnected", api.getConnectionState())
        assertNull(shadowOf(context).nextStartedService)
    }
}
