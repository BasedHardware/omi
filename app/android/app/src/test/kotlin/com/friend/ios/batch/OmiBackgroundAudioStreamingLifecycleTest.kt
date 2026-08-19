package com.friend.ios.batch

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OmiBackgroundAudioStreamingLifecycleTest {
    @Test
    fun policyDisabledAtOpenClearsQueuedFramesAndSendsNothing() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val session = lifecycle.beginSession()
        lifecycle.queueFrame(byteArrayOf(1, 2))
        lifecycle.queueFrame(byteArrayOf(3, 4))

        val drained = lifecycle.drainOnOpen(session, policyAllowsStreaming = false)

        assertTrue(drained.isEmpty())
        assertEquals(0, lifecycle.pendingFrameCount)
        assertTrue(!lifecycle.isCurrent(session))
    }

    @Test
    fun allowedOpenDrainsQueuedFramesInOrder() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val session = lifecycle.beginSession()
        lifecycle.queueFrame(byteArrayOf(1, 2))
        lifecycle.queueFrame(byteArrayOf(3, 4))

        val drained = lifecycle.drainOnOpen(session, policyAllowsStreaming = true)

        assertEquals(2, drained.size)
        assertArrayEquals(byteArrayOf(1, 2), drained[0])
        assertArrayEquals(byteArrayOf(3, 4), drained[1])
        assertEquals(0, lifecycle.pendingFrameCount)
    }

    @Test
    fun pendingQueueKeepsOnlyTheNewestFramesAndCopiesInput() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 2)
        val session = lifecycle.beginSession()
        val first = byteArrayOf(1)
        lifecycle.queueFrame(first)
        first[0] = 9
        lifecycle.queueFrame(byteArrayOf(2))
        lifecycle.queueFrame(byteArrayOf(3))

        val drained = lifecycle.drainOnOpen(session, policyAllowsStreaming = true)

        assertEquals(2, drained.size)
        assertArrayEquals(byteArrayOf(2), drained[0])
        assertArrayEquals(byteArrayOf(3), drained[1])
    }

    @Test
    fun staleCallbackCannotQueueAfterPolicyDisable() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val staleSession = lifecycle.beginSession()
        lifecycle.invalidateSession()

        assertTrue(!lifecycle.isCurrent(staleSession))
        assertTrue(!lifecycle.queueFrameIfCurrent(staleSession, byteArrayOf(9)))
        assertEquals(0, lifecycle.pendingFrameCount)
    }

    @Test
    fun staleCallbackCannotQueueIntoAReenabledSession() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val staleSession = lifecycle.beginSession()
        val staleGeneration = lifecycle.currentGeneration()
        lifecycle.invalidateSession()
        val reenabledSession = lifecycle.beginSession()

        assertTrue(!lifecycle.isGenerationCurrent(staleGeneration))
        assertTrue(!lifecycle.queueFrameIfCurrent(staleSession, byteArrayOf(1)))
        assertTrue(lifecycle.queueFrameIfCurrent(reenabledSession, byteArrayOf(2)))
        val drained = lifecycle.drainOnOpen(reenabledSession, policyAllowsStreaming = true)

        assertEquals(1, drained.size)
        assertArrayEquals(byteArrayOf(2), drained.single())
    }

    @Test
    fun staleOpenCannotInvalidateNewerSession() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val staleSession = lifecycle.beginSession()
        lifecycle.invalidateSession()
        val currentSession = lifecycle.beginSession()

        assertTrue(lifecycle.drainOnOpen(staleSession, policyAllowsStreaming = false).isEmpty())
        assertTrue(lifecycle.queueFrameIfCurrent(currentSession, byteArrayOf(2)))
    }

    @Test
    fun failedSessionQueueIsClearedBeforeAReenableSessionStarts() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val failedSession = lifecycle.beginSession()
        lifecycle.queueFrameIfCurrent(failedSession, byteArrayOf(1))
        lifecycle.invalidateSession()

        val reenabledSession = lifecycle.beginSession()
        lifecycle.queueFrameIfCurrent(reenabledSession, byteArrayOf(2))
        val drained = lifecycle.drainOnOpen(reenabledSession, policyAllowsStreaming = true)

        assertTrue(!lifecycle.isCurrent(failedSession))
        assertEquals(1, drained.size)
        assertArrayEquals(byteArrayOf(2), drained.single())
    }

    @Test
    fun closedSessionQueueIsInvalidatedBeforeSameConfigReconnects() {
        val lifecycle = OmiBackgroundAudioStreamingLifecycle(maxPendingFrames = 3)
        val closedSession = lifecycle.beginSession()
        lifecycle.queueFrameIfCurrent(closedSession, byteArrayOf(1))
        lifecycle.invalidateSession()

        val reconnectSession = lifecycle.beginSession()
        assertTrue(!lifecycle.queueFrameIfCurrent(closedSession, byteArrayOf(9)))
        assertTrue(lifecycle.drainOnOpen(reconnectSession, policyAllowsStreaming = true).isEmpty())
    }
}
