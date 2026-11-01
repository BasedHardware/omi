package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DiscoveryReconnectPolicyTest {

    @Test
    fun `consecutive discovery failures back off exponentially to a 60 s long tail`() {
        val p = DiscoveryReconnectPolicy()
        listOf(1_000L, 2_000L, 4_000L, 8_000L, 16_000L, 32_000L, 60_000L).forEach { expected ->
            p.onDiscoveryRetirement("AA:BB")
            assertEquals(expected, p.consumeRetirementBackoffMs("AA:BB"))
        }
        // The long tail replaces the unbounded fixed 3 s loop (PR #23882): attempts
        // continue at one per minute, matching the iOS saved-reconnect cycle (#23872).
        repeat(20) {
            p.onDiscoveryRetirement("AA:BB")
            assertEquals(60_000L, p.consumeRetirementBackoffMs("AA:BB"))
        }
    }

    @Test
    fun `a successful discovery resets the ladder`() {
        val p = DiscoveryReconnectPolicy()
        repeat(5) {
            p.onDiscoveryRetirement("A")
            p.consumeRetirementBackoffMs("A")
        }
        p.onDiscoverySucceeded("A")
        p.onDiscoveryRetirement("A")
        assertEquals(1_000L, p.consumeRetirementBackoffMs("A"))
    }

    @Test
    fun `the retirement marker is consumed once so later disconnects stay ordinary`() {
        val p = DiscoveryReconnectPolicy()
        assertNull(p.consumeRetirementBackoffMs("A"))
        p.onDiscoveryRetirement("A")
        assertEquals(1_000L, p.consumeRetirementBackoffMs("A"))
        // The retried link's own radio drop is an ordinary disconnect, not a retirement.
        assertNull(p.consumeRetirementBackoffMs("A"))
    }

    @Test
    fun `a fresh connect attempt invalidates an unconsumed marker but keeps the ladder`() {
        val p = DiscoveryReconnectPolicy()
        p.onDiscoveryRetirement("A") // e.g. the service was gone; nobody consumed it
        p.onConnectAttempt("A")
        assertNull(p.consumeRetirementBackoffMs("A"))
        p.onDiscoveryRetirement("A")
        assertEquals(2_000L, p.consumeRetirementBackoffMs("A"))
    }

    @Test
    fun `success and markers are per device and addresses are case-insensitive`() {
        val p = DiscoveryReconnectPolicy()
        p.onDiscoveryRetirement("AA")
        p.onDiscoveryRetirement("BB")
        assertEquals(1_000L, p.consumeRetirementBackoffMs("aa"))
        assertEquals(1_000L, p.consumeRetirementBackoffMs("BB"))
        p.onDiscoveryRetirement("aa")
        assertEquals(2_000L, p.consumeRetirementBackoffMs("AA"))
        p.onDiscoverySucceeded("bb") // B's ladder clears; A's is untouched
        p.onDiscoveryRetirement("BB")
        assertEquals(1_000L, p.consumeRetirementBackoffMs("BB"))
        p.onDiscoveryRetirement("AA")
        assertEquals(4_000L, p.consumeRetirementBackoffMs("AA"))
    }
}
