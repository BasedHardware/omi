package com.friend.ios.phonecalls

import com.friend.ios.service.phonecalls.PhoneCallAudio
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.Executor

class CallAudioCoalescerTest {
    /** Runs queued work only when the test says so (a starved audio queue). */
    private class ManualExecutor : Executor {
        val tasks = ArrayDeque<Runnable>()
        override fun execute(command: Runnable) {
            tasks.addLast(command)
        }

        fun drain() {
            while (tasks.isNotEmpty()) tasks.removeFirst().run()
        }
    }

    private val buffer10ms = 960

    @Test
    fun tenBuffersBecomeOneHundredMillisecondFramePerChannel() {
        val out = mutableListOf<PhoneCallAudio>()
        val coalescer = CallAudioCoalescer(Executor { it.run() }) { out += it }
        repeat(9) {
            coalescer.append(ByteArray(buffer10ms) { 1 }, CallAudioChannel.Microphone)
            coalescer.append(ByteArray(buffer10ms) { 2 }, CallAudioChannel.Remote)
        }
        assertTrue(out.isEmpty())
        coalescer.append(ByteArray(buffer10ms) { 1 }, CallAudioChannel.Microphone)
        assertEquals(1, out.size)
        assertEquals(PhoneCallAudio.Channel.You, out[0].channel)
        assertEquals(CallAudioCoalescer.FLUSH_BYTES, out[0].pcm16.size)
        coalescer.append(ByteArray(buffer10ms) { 2 }, CallAudioChannel.Remote)
        assertEquals(PhoneCallAudio.Channel.Them, out[1].channel)
        assertTrue(out[1].pcm16.all { it == 2.toByte() })
    }

    @Test
    fun flushSendsTheTailAndNothingAfter() {
        val out = mutableListOf<PhoneCallAudio>()
        val coalescer = CallAudioCoalescer(Executor { it.run() }) { out += it }
        coalescer.append(ByteArray(100) { 1 }, CallAudioChannel.Microphone)
        coalescer.flush()
        assertEquals(1, out.size)
        assertEquals(100, out[0].pcm16.size)
        coalescer.append(ByteArray(CallAudioCoalescer.FLUSH_BYTES), CallAudioChannel.Microphone)
        assertEquals(1, out.size)
    }

    @Test
    fun aStarvedQueueDropsNewAudioAtTheCap() {
        val out = mutableListOf<PhoneCallAudio>()
        val queue = ManualExecutor()
        val coalescer = CallAudioCoalescer(queue) { out += it }
        val chunk = CallAudioCoalescer.FLUSH_BYTES
        repeat(20) { coalescer.append(ByteArray(chunk), CallAudioChannel.Remote) }
        assertEquals(16, queue.tasks.size)
        queue.drain()
        assertEquals(16, out.size)
    }

    @Test
    fun anOverfullChannelKeepsItsNewestBytes() {
        val out = mutableListOf<PhoneCallAudio>()
        val coalescer = CallAudioCoalescer(Executor { it.run() }) { out += it }
        // One oversized buffer (more than four frames) keeps only its newest 100 ms.
        val big = ByteArray(CallAudioCoalescer.MAX_PENDING_BYTES + 10) { if (it >= CallAudioCoalescer.MAX_PENDING_BYTES + 10 - CallAudioCoalescer.FLUSH_BYTES) 9 else 0 }
        coalescer.append(big, CallAudioChannel.Microphone)
        assertEquals(1, out.size)
        assertArrayEquals(ByteArray(CallAudioCoalescer.FLUSH_BYTES) { 9 }, out[0].pcm16)
    }
}
