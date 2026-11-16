package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test

class RingReadDiagnosticsTest {
    @Test
    fun snapshotsProtocolStateAtDisconnectWithoutBodiesOrCrossLinkCarryover() {
        val state = RingReadDiagnostics()
        val owner = Any()
        val characteristic = RingReadDiagnostics.CHARACTERISTIC
        val read = ByteArray(9).also { it[0] = 0x11 }
        val begin = ByteArray(13).also { it[0] = 0x05 }
        val done = ByteArray(10).also { it[0] = 0x04 }
        assertEquals(emptyMap<String, Any>(), state.disconnected("restored", 0))
        state.connected("a", owner)
        state.requested("a", owner, characteristic, read) // request is not active
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 2000))
        state.connected("a", owner)
        state.requested("a", owner, characteristic, ByteArray(6).also { it[0] = 0x11 }) // legacy READ_FILE
        state.received("a", owner, characteristic, ByteArray(83).also { it[0] = 0x05 }, 1000)
        state.received("a", owner, characteristic, begin, 1000) // unarmed legacy data
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 2000))
        state.connected("a", owner)
        state.received("a", owner, "unrelated", begin, 1000)
        state.received("a", owner, characteristic, byteArrayOf(0x05), 1000) // truncated
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 2000))
        state.connected("a", owner)
        state.requested("a", owner, characteristic, read)
        state.rejected("a", owner, characteristic, read)
        state.received("a", owner, characteristic, begin, 1000)
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 2000))
        state.connected("a", owner)
        state.requested("a", owner, characteristic, read)
        val mismatch = begin.copyOf().also { it[8] = 1 }
        state.received("a", owner, characteristic, mismatch, 1000)
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 2000))
        state.connected("a", owner)
        state.connected("b", Any())
        state.requested("a", owner, characteristic, read)
        state.received("a", owner, characteristic, begin, 1000)
        state.received("a", owner, characteristic, byteArrayOf(0x04), 2000) // truncated DONE
        val snapshot = state.disconnected("a", 5500)
        assertEquals(mapOf("ring_read_active" to true, "ring_read_age_ms" to 4500L), snapshot)
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("b", 5500))
        assertEquals(emptyMap<String, Any>(), state.disconnected("a", 6000))
        state.connected("a", owner)
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 7000))
        assertEquals(4500L, snapshot["ring_read_age_ms"]) // historical snapshot is immutable
        state.connected("a", owner)
        state.requested("a", owner, characteristic, read)
        state.received("a", Any(), characteristic, begin, 7500) // stale GATT
        assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 7800))
        state.requested("a", owner, characteristic, read)
        state.received("a", owner, characteristic, begin, 7900) // queued callback after disconnect
        assertEquals(emptyMap<String, Any>(), state.disconnected("a", 7950))
        for (status in listOf(0, 1, 2, 6)) { // DONE includes STOP/error statuses
            state.connected("a", owner)
            state.requested("a", owner, characteristic, read)
            state.received("a", owner, characteristic, begin, 8000)
            done[1] = status.toByte()
            state.received("a", owner, characteristic, done, 9000)
            assertEquals(mapOf("ring_read_active" to false), state.disconnected("a", 10000))
        }
        state.connected("a", owner)
        state.requested("a", owner, characteristic, read)
        state.received("a", owner, characteristic, begin, 1000)
        state.requested("a", owner, characteristic, read)
        state.received("a", owner, characteristic, begin, 3000) // next read has its own age
        assertEquals(2000L, state.disconnected("a", 5000)["ring_read_age_ms"])
        assertEquals(emptyMap<String, Any>(), RingReadDiagnostics().disconnected("a", 5000))
    }
}
