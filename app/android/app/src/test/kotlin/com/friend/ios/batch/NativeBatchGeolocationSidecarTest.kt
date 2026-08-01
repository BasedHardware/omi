package com.friend.ios.batch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class NativeBatchGeolocationSidecarTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun `copies a bounded snapshot beside explicit and automatic phone batch files`() {
        val raw = """{"latitude":37.7749,"longitude":-122.4194,"capture_source":"current_position"}"""
        for (marker in listOf("omibatchphone", "omibatchphoneauto")) {
            val audio = File(temporaryFolder.root, "audio_${marker}_opus_fs320_16000_1_fs320_1.bin")

            persistNativeBatchGeolocationSidecar(audio, raw, "test")

            val sidecar = File(audio.path + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX)
            assertTrue(sidecar.isFile)
            assertEquals(raw, sidecar.readText())
        }
    }

    @Test
    fun `malformed or oversized snapshots fail soft without a sidecar`() {
        val malformedAudio = File(temporaryFolder.root, "malformed.bin")
        persistNativeBatchGeolocationSidecar(malformedAudio, "{not-json", "test")
        assertFalse(File(malformedAudio.path + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX).exists())

        val oversizedAudio = File(temporaryFolder.root, "oversized.bin")
        persistNativeBatchGeolocationSidecar(
            oversizedAudio,
            "x".repeat(NATIVE_BATCH_GEOLOCATION_MAX_BYTES + 1),
            "test",
        )
        assertFalse(File(oversizedAudio.path + NATIVE_BATCH_GEOLOCATION_SIDECAR_SUFFIX).exists())
    }
}
