package com.friend.ios.limitless

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LimitlessAckIdempotencyTest {
    @Test
    fun failedAckDoesNotAdvanceDeletionAndRedrainDoesNotAppendTwice() {
        val watermarks = mutableMapOf<String, Int>()
        var appends = 0
        val dedupe = LimitlessPageDeduplicator(
            readWatermark = { watermarks[it] ?: Int.MIN_VALUE },
            writeWatermark = { key, value ->
                watermarks[key] = value
                true
            },
        )
        val gate = LimitlessAckCommitGate(40)
        var transportCallback: ((Boolean) -> Unit)? = null

        assertTrue(
            dedupe.appendOnce(
                "device-a/session-7",
                41,
                {
                    appends++
                    true
                },
                {},
            ),
        )
        assertEquals(
            LimitlessAckCommitGate.RequestResult.STARTED,
            gate.request(41, { true }, { _, callback -> transportCallback = callback }) { _, _ -> },
        )
        assertEquals(40, gate.lastAckedPageIndex)

        transportCallback!!(false)
        assertEquals(40, gate.lastAckedPageIndex)
        assertTrue(gate.blocked)

        val afterReconnect = LimitlessPageDeduplicator(
            readWatermark = { watermarks[it] ?: Int.MIN_VALUE },
            writeWatermark = { key, value ->
                watermarks[key] = value
                true
            },
        )
        assertTrue(
            afterReconnect.appendOnce(
                "device-a/session-7",
                41,
                {
                    appends++
                    true
                },
                {},
            ),
        )
        assertEquals(1, appends)
    }

    @Test
    fun successfulAckAdvancesOnlyAfterCompletion() {
        val gate = LimitlessAckCommitGate(9)
        var transportCallback: ((Boolean) -> Unit)? = null
        var settled = false

        gate.request(10, { true }, { _, callback -> transportCallback = callback }) { success, _ ->
            settled = success
        }
        assertEquals(9, gate.lastAckedPageIndex)
        assertTrue(gate.inFlight)

        transportCallback!!(true)
        assertEquals(10, gate.lastAckedPageIndex)
        assertFalse(gate.inFlight)
        assertTrue(settled)
    }

    @Test
    fun failedWatermarkCommitRollsBackAndRemainsRetryable() {
        var rollbacks = 0
        val dedupe = LimitlessPageDeduplicator(
            readWatermark = { Int.MIN_VALUE },
            writeWatermark = { _, _ -> false },
        )

        assertFalse(dedupe.appendOnce("device/session", 1, { true }, { rollbacks++ }))
        assertEquals(1, rollbacks)
    }

    @Test
    fun failedDurableAppendAlsoRollsBackPendingBytes() {
        var rollbacks = 0
        val dedupe = LimitlessPageDeduplicator(
            readWatermark = { Int.MIN_VALUE },
            writeWatermark = { _, _ -> true },
        )

        assertFalse(dedupe.appendOnce("device/session", 1, { false }, { rollbacks++ }))
        assertEquals(1, rollbacks)
    }
}
