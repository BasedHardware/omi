package com.friend.ios.raybanmeta

import android.app.Application
import com.friend.ios.FlutterError
import com.friend.ios.RayBanMetaFlutterAPI
import io.flutter.plugin.common.BinaryMessenger
import java.nio.ByteBuffer
import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

/**
 * Compiled only for the raybanDat flavor (src/testRaybanDat), which links the
 * Meta Wearables toolkit through src/raybanDat. Covers the paths that need no
 * paired glasses: the build reports full mode, and camera calls made before a
 * session exists fail with a typed error instead of touching the toolkit.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], manifest = Config.NONE, application = Application::class)
class RayBanMetaHostApiImplDatTest {

    private object NoopMessenger : BinaryMessenger {
        override fun send(channel: String, message: ByteBuffer?) {}
        override fun send(channel: String, message: ByteBuffer?, callback: BinaryMessenger.BinaryReply?) {}
        override fun setMessageHandler(channel: String, handler: BinaryMessenger.BinaryMessageHandler?) {}
    }

    private val context = RuntimeEnvironment.getApplication()

    private fun hostApi() = RayBanMetaHostApiImpl(context, RayBanMetaFlutterAPI(NoopMessenger)) { null }

    @Test
    fun `toolkit flavor reports full mode`() {
        assertEquals("full", hostApi().getAvailabilityMode())
    }

    @Test
    fun `photo capture before the camera starts fails with a typed error`() {
        try {
            hostApi().capturePhoto()
            fail("expected FlutterError(camera_not_started)")
        } catch (e: FlutterError) {
            assertEquals("camera_not_started", e.code)
        }
    }

    @Test
    fun `stopping the camera with no session is a no-op`() {
        hostApi().stopCamera()
    }
}
