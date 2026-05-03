package com.omi.ambientcompanion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sin

class VadWatchEngineTest {
    @Test
    fun silenceDoesNotTriggerSpeech() {
        val vad = VadWatchEngine(speechFramesToTrigger = 2)
        repeat(10) {
            val result = vad.accept(ByteArray(960))
            assertFalse(result.speech)
        }
        assertFalse(vad.activeSpeech)
    }

    @Test
    fun voicedFramesTriggerSpeechAndPreRoll() {
        val vad = VadWatchEngine(speechFramesToTrigger = 2)
        vad.accept(ByteArray(960))
        vad.accept(voicedFrame())
        vad.accept(voicedFrame())
        assertTrue(vad.activeSpeech)
        assertTrue(vad.drainPreRoll().isNotEmpty())
    }

    private fun voicedFrame(): ByteArray {
        val samples = 480
        val buffer = ByteBuffer.allocate(samples * 2).order(ByteOrder.LITTLE_ENDIAN)
        repeat(samples) { i ->
            val sample = (sin(i / 8.0) * 8000).toInt().toShort()
            buffer.putShort(sample)
        }
        return buffer.array()
    }
}
