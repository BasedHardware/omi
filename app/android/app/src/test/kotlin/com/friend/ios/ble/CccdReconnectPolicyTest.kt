package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CccdReconnectPolicyTest {
    private val stored = mutableMapOf<String, Int>()
    private fun policy() = CccdReconnectPolicy(
        OmiBleManager.CCCD_TIMEOUT_RECONNECT_BUDGET,
        loadTimeouts = { stored[it] ?: 0 },
        saveTimeouts = { address, count -> stored[address] = count; true },
    )

    @Test
    fun `consecutive CCCD timeouts stop after two reconnects with backoff`() {
        val p = policy()
        assertEquals(3000L, p.reconnectDelay("A", true, 3000L))
        assertEquals(6000L, p.reconnectDelay("A", true, 3000L))
        repeat(20) { assertNull(p.reconnectDelay("A", true, 3000L)) }
        assertTrue(p.isExhausted("A"))
        assertEquals(3, stored["A"])
        assertEquals(3000L, p.reconnectDelay("B", true, 3000L))
    }

    @Test
    fun `ACK resets the budget and backoff for only its device`() {
        val p = policy()
        repeat(3) { p.reconnectDelay("A", true, 3000L) }
        repeat(3) { p.reconnectDelay("B", true, 3000L) }
        assertTrue(p.onAcknowledged("a"))
        assertFalse(p.isExhausted("A"))
        assertEquals(0, stored["A"])
        assertEquals(3000L, p.reconnectDelay("A", true, 3000L))
        assertTrue(p.isExhausted("B"))
    }

    @Test
    fun `ordinary disconnects retain their delay and do not spend or replenish CCCD budget`() {
        val p = policy()
        repeat(100) { assertEquals(3000L, p.reconnectDelay("A", false, 3000L)) }
        assertTrue(stored.isEmpty())
        repeat(3) { p.reconnectDelay("A", true, 3000L) }
        repeat(100) { assertEquals(3000L, p.reconnectDelay("A", false, 3000L)) }
        assertTrue(p.isExhausted("A"))
        assertEquals(3, stored["A"])
    }

    @Test
    fun `service or process recreation cannot replenish a spent budget`() {
        repeat(3) { policy().reconnectDelay("A", true, 3000L) }
        val restored = policy()
        assertTrue(restored.isExhausted("A"))
        assertNull(restored.reconnectDelay("A", true, 3000L))
        restored.onAcknowledged("A")
        assertFalse(policy().isExhausted("A"))
    }

    @Test
    fun `failed persistence stops recovery and invalid persisted counts fail closed`() {
        val unavailable = CccdReconnectPolicy(2, { 0 }, { _, _ -> false })
        assertNull(unavailable.reconnectDelay("A", true, 3000L))
        assertTrue(unavailable.isExhausted("A"))
        for (value in listOf(-1, Int.MAX_VALUE)) {
            stored["A"] = value
            val invalid = policy()
            assertTrue(invalid.isExhausted("A"))
            assertNull(invalid.reconnectDelay("A", true, 3000L))
        }
    }
}
