package com.friend.ios.wear

import com.friend.ios.core.watch.WatchAudioChunk
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** The microphone's audio framing: 1.5 s chunks, numbered, the rest and an empty last one at the end. */
class PcmChunkerTest {
    @Test
    fun microphoneReadsBecomeWholeChunksInOrder() {
        val chunker = PcmChunker()
        val read = ByteArray(3200) { it.toByte() }
        // 15 reads of 100 ms are exactly one 1.5 s chunk.
        val chunks = (0 until 31).flatMap { chunker.append(read) }
        assertEquals(2, chunks.size)
        assertEquals(listOf(0, 1), chunks.map { it.index })
        assertTrue(chunks.all { it.data.size == WatchAudioChunk.BYTES_PER_CHUNK && !it.isLast && it.sampleRate == 16000.0 })
        assertArrayEquals(read, chunks[0].data.copyOfRange(0, 3200))

        val end = chunker.finish()
        assertEquals(2, end.size)
        assertEquals(3200, end[0].data.size)
        assertEquals(2, end[0].index)
        assertEquals(WatchAudioChunk(ByteArray(0), 3, isLast = true), end[1])
    }

    @Test
    fun aReadLargerThanAChunkAndAPartialCountAreSplitExactly() {
        val chunker = PcmChunker(bytesPerChunk = 4)
        val chunks = chunker.append(byteArrayOf(1, 2, 3, 4, 5, 6, 7, 8, 9, 99), count = 9)
        assertEquals(listOf(listOf<Byte>(1, 2, 3, 4), listOf<Byte>(5, 6, 7, 8)), chunks.map { it.data.toList() })
        val end = chunker.finish()
        assertEquals(listOf<Byte>(9), end[0].data.toList())
        assertTrue(end[1].isLast)
    }

    @Test
    fun aRecordingWithNothingLeftEndsWithJustTheEmptyChunkAndTheNextStartsAtZero() {
        val chunker = PcmChunker(bytesPerChunk = 2)
        chunker.append(byteArrayOf(1, 2))
        assertEquals(listOf(WatchAudioChunk(ByteArray(0), 1, isLast = true)), chunker.finish())
        assertEquals(0, chunker.append(byteArrayOf(3, 4)).single().index)
    }

    @Test
    fun theTimerReadsLikeSwiftUIs() {
        assertEquals("0:00", timerText(0))
        assertEquals("0:05", timerText(5_999))
        assertEquals("12:34", timerText((12 * 60 + 34) * 1000L))
        assertEquals("1:02:03", timerText((3600 + 2 * 60 + 3) * 1000L))
    }

    @Test
    fun theBatteryGlyphPicksTheIOSLevels() {
        assertEquals(0f, batteryFill(12))
        assertEquals(0.25f, batteryFill(13))
        assertEquals(0.5f, batteryFill(62))
        assertEquals(0.75f, batteryFill(87))
        assertEquals(1f, batteryFill(88))
    }
}
