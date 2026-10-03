package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class BleReconnectDiagnosticsTest {
    private data class Event(val timestamp: Long, val type: String, val duration: Long = 0)

    private class History {
        val diagnostics = BleReconnectDiagnostics()
        var events = emptyList<Event>()
        val retentionMs = 7 * 24 * 3600 * 1000L

        fun append(timestamp: Long, type: String, isManual: Boolean = false) {
            diagnostics.record(timestamp, type, isManual)
            events = diagnostics.retainedHistory(
                events + Event(timestamp, type), timestamp, retentionMs, 500,
            ) { it.timestamp }
        }

        fun recover(timestamp: Long, hadConnection: Boolean = true): List<Event>? = diagnostics.backfilledHistory(
            events, timestamp, hadConnection, { it.timestamp }, { event, duration -> event.copy(duration = duration) },
        )
    }

    @Test fun `retained history backfills the original outage after more than 500 failed attempts`() {
        val history = History()
        history.append(1_000, "disconnect")
        for (attempt in 1..1_000) {
            history.append(1_000 + attempt * 3_000L, "fail_to_connect")
            assertTrue(history.events.size <= 500)
        }

        val updated = history.recover(3_004_000)!!
        assertEquals(500, updated.size)
        assertEquals(Event(1_000, "disconnect", 3_003_000), updated.first())
        assertEquals((502..1_000).map { Event(1_000 + it * 3_000L, "fail_to_connect") }, updated.drop(1))
        assertNull(history.recover(3_005_000))
    }

    @Test fun `pending outage protection respects the seven day expiry boundary`() {
        val history = History()
        history.append(1_000, "disconnect")
        history.append(1_000 + history.retentionMs, "fail_to_connect")
        assertEquals(1_000L, history.events.first().timestamp)
        history.append(1_001 + history.retentionMs, "fail_to_connect")
        assertEquals(2, history.events.size)
        assertNull(history.recover(2_000 + history.retentionMs))
        assertTrue(history.events.all { it.duration == 0L })
        assertNull(history.recover(3_000 + history.retentionMs))
    }

    @Test fun `first connection consumes the protected event without backfilling`() {
        val history = History()
        for (attempt in 1..501) history.append(attempt.toLong(), "fail_to_connect")
        assertNull(history.recover(502, hadConnection = false))
        assertNull(history.recover(503))
        history.append(1_000, "disconnect")
        history.append(1_500, "fail_to_connect")
        assertEquals(Event(1_000, "disconnect", 1_000), history.recover(2_000)!!.single { it.duration > 0 })
        assertEquals(500, history.events.size)
        assertFalse(history.events.any { it.timestamp == 1L })
    }

    @Test fun `manual cancellation releases a protected outage at the count limit`() {
        val history = History()
        history.append(1_000, "disconnect")
        for (attempt in 1..500) history.append(1_000 + attempt.toLong(), "fail_to_connect")
        history.append(2_000, "disconnect", isManual = true)
        assertEquals(500, history.events.size)
        assertFalse(history.events.any { it.timestamp == 1_000L })
        assertNull(history.recover(3_000))
    }

    @Test fun `failed retries preserve the original disconnect and full recovery duration`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "disconnect", false)
        diagnostics.record(4_000, "fail_to_connect", false)
        diagnostics.record(7_000, "fail_to_connect", false)

        assertEquals(BleReconnectDiagnostics.Recovery(1_000, 10_000), diagnostics.recovered(11_000, true))
        assertNull(diagnostics.recovered(12_000, true))
    }

    @Test fun `first connection failure is consumed before a later connection loss`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "fail_to_connect", false)
        assertNull(diagnostics.recovered(3_000, false))
        assertNull(diagnostics.recovered(4_000, true))

        diagnostics.record(10_000, "disconnect", false)
        diagnostics.record(12_000, "fail_to_connect", false)
        assertEquals(BleReconnectDiagnostics.Recovery(10_000, 5_000), diagnostics.recovered(15_000, true))
    }

    @Test fun `a new established link loss replaces an earlier pending failure`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "fail_to_connect", false)
        diagnostics.record(5_000, "disconnect", false)
        assertEquals(BleReconnectDiagnostics.Recovery(5_000, 3_000), diagnostics.recovered(8_000, true))
    }

    @Test fun `manual disconnect discards pending recovery timing`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(1_000, "disconnect", false)
        diagnostics.record(4_000, "disconnect", true)
        assertNull(diagnostics.recovered(10_000, true))
    }

    @Test fun `clock rollback cannot yield a negative duration`() {
        val diagnostics = BleReconnectDiagnostics()
        diagnostics.record(5_000, "disconnect", false)
        assertEquals(BleReconnectDiagnostics.Recovery(5_000, 0), diagnostics.recovered(4_000, true))
        assertNull(diagnostics.recovered(6_000, true))
    }
}
