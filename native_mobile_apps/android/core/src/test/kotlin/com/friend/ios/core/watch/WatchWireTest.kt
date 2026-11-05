package com.friend.ios.core.watch

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException

/** Port of `WatchMessageTests` (WatchTests.swift), plus the Data Layer bytes and the channel framing. */
class WatchWireTest {
    @Test
    fun decodesTheIOSWatchAppsDictionaries() {
        val pcm = ByteArray(48000) { 3 }
        val chunk = mapOf("method" to "sendAudioChunk", "audioChunk" to pcm, "chunkIndex" to 4, "isLast" to false, "sampleRate" to 16000.0)
        assertEquals(WatchMessage.AudioChunk(WatchAudioChunk(pcm, 4, false)), WatchMessage.from(chunk))
        assertEquals(WatchMessage.StartRecording, WatchMessage.from(mapOf("method" to "startRecording")))
        assertEquals(WatchMessage.StopRecording(null), WatchMessage.from(mapOf("method" to "stopRecording")))
        // The watch reports `batteryLevel * 100` as a Float.
        assertEquals(WatchMessage.BatteryUpdate(85.0, 2), WatchMessage.from(mapOf("method" to "batteryUpdate", "batteryLevel" to 85f, "batteryState" to 2)))
        val info = mapOf("method" to "watchInfoUpdate", "name" to "Anna's Watch", "model" to "Watch", "systemVersion" to "11.2", "localizedModel" to "Apple Watch")
        assertEquals(WatchMessage.WatchInfoUpdate(WatchInfo("Anna's Watch", "Watch", "11.2", "Apple Watch")), WatchMessage.from(info))
    }

    @Test
    fun rejectsUnknownOrIncompleteMessages() {
        assertNull(WatchMessage.from(mapOf("method" to "somethingNew")))
        assertNull(WatchMessage.from(mapOf("audioChunk" to ByteArray(0))))
        assertNull(WatchMessage.from(mapOf("method" to "sendAudioChunk", "chunkIndex" to 1)))
    }

    private val everyMessage: List<WatchMessage> = listOf(
        WatchMessage.StartRecording, WatchMessage.StopRecording(null), WatchMessage.StopRecording(WatchStopReason.Busy),
        WatchMessage.AudioChunk(WatchAudioChunk(byteArrayOf(1, 2, 3, 4), 2, true)),
        WatchMessage.RecordingError("Microphone permission denied"), WatchMessage.RequestMicrophonePermission,
        WatchMessage.MicrophonePermissionResult(true), WatchMessage.RequestBattery, WatchMessage.BatteryUpdate(40.0, 1),
        WatchMessage.RequestWatchInfo, WatchMessage.WatchInfoUpdate(WatchInfo("W", "M", "11", "L")),
    )

    @Test
    fun everyMessageSurvivesTheRoundTrip() {
        for (message in everyMessage) {
            assertEquals(message, WatchMessage.from(message.payload))
            // ... and the trip through the Data Layer's bytes.
            assertEquals(message, WatchWire.message(WatchWire.encode(message)))
        }
        assertEquals(1, WatchMessage.StopRecording(null).payload.size)
        val state = WatchPhoneState(WatchPhoneState.Capture.Omi, 72)
        assertEquals(state, WatchPhoneState.from(state.payload))
        assertEquals(state, WatchWire.phoneState(WatchWire.encode(state.payload)))
        assertNull(WatchPhoneState.from(WatchPhoneState(WatchPhoneState.Capture.Idle, null).payload)?.omiBattery)
        // The phone's state is not a message, and a message is not the phone's state.
        assertNull(WatchWire.message(WatchWire.encode(state.payload)))
        assertNull(WatchWire.phoneState(WatchWire.encode(WatchMessage.StartRecording)))
    }

    @Test
    fun bytesKeepEveryValueType() {
        val payload = mapOf(
            "s" to "Grüße", "t" to true, "i" to 7, "l" to Long.MAX_VALUE, "f" to 1.5f, "d" to 0.25,
            "b" to byteArrayOf(0, -1, 127), "n" to null, "empty" to "",
        )
        val decoded = WatchWire.decode(WatchWire.encode(payload))!!
        assertEquals(listOf("s", "t", "i", "l", "f", "d", "b", "n", "empty"), decoded.keys.toList())
        assertEquals("Grüße", decoded["s"])
        assertEquals(true, decoded["t"])
        assertEquals(7L, decoded["i"])
        assertEquals(Long.MAX_VALUE, decoded["l"])
        assertEquals(1.5, decoded["f"])
        assertArrayEquals(byteArrayOf(0, -1, 127), decoded["b"] as ByteArray)
        assertNull(decoded["n"])
        assertTrue("n" in decoded)
    }

    @Test
    fun brokenBytesAreNotAMessage() {
        val bytes = WatchWire.encode(WatchMessage.RequestBattery)
        assertNull(WatchWire.decode(bytes.copyOf(bytes.size - 1)))
        assertNull(WatchWire.decode(bytes + byteArrayOf(0)))
        assertNull(WatchWire.decode(byteArrayOf(9) + bytes.copyOfRange(1, bytes.size)))
        assertNull(WatchWire.decode(ByteArray(0)))
    }

    @Test
    fun aRecordingIsOneStreamOfFramesInOrder() {
        val recording = listOf(WatchMessage.StartRecording) +
            (0 until 3).map { WatchMessage.AudioChunk(WatchAudioChunk(ByteArray(WatchAudioChunk.BYTES_PER_CHUNK) { i -> (i + it).toByte() }, it, false)) } +
            WatchMessage.AudioChunk(WatchAudioChunk(ByteArray(0), 3, true)) + WatchMessage.StopRecording(null)
        val stream = ByteArrayOutputStream()
        recording.forEach { WatchWire.writeFrame(stream, it) }
        val input = ByteArrayInputStream(stream.toByteArray())
        val read = generateSequence { WatchWire.readFrame(input) }.toList()
        assertEquals(recording, read)
        // A frame is the 4-byte length and the dictionary.
        assertEquals(4 + WatchWire.encode(WatchMessage.StartRecording).size, frame(WatchMessage.StartRecording).size)
    }

    @Test
    fun framesItCannotReadAreSkippedAndATruncatedStreamThrows() {
        val stream = ByteArrayOutputStream()
        // A frame from a newer watch app: a dictionary with an unknown method.
        val unknown = WatchWire.encode(mapOf("method" to "somethingNew"))
        stream.write(byteArrayOf(0, 0, 0, unknown.size.toByte()))
        stream.write(unknown)
        WatchWire.writeFrame(stream, WatchMessage.StopRecording(WatchStopReason.Failed))
        val input = ByteArrayInputStream(stream.toByteArray())
        assertEquals(WatchMessage.StopRecording(WatchStopReason.Failed), WatchWire.readFrame(input))
        assertNull(WatchWire.readFrame(input))

        val audio = frame(WatchMessage.AudioChunk(WatchAudioChunk(ByteArray(3200), 0, false)))
        expectIOException { WatchWire.readFrame(ByteArrayInputStream(audio.copyOf(audio.size - 10))) }
        expectIOException { WatchWire.readFrame(ByteArrayInputStream(byteArrayOf(0x7f, 0, 0, 0))) }
    }

    private fun frame(message: WatchMessage): ByteArray = ByteArrayOutputStream().also { WatchWire.writeFrame(it, message) }.toByteArray()

    private fun expectIOException(block: () -> Unit) {
        try {
            block()
            fail("expected an IOException")
        } catch (_: IOException) {
        }
    }
}
