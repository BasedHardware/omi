package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RetentionProbeLifecycleTest {
    private val storageStatus = java.nio.ByteBuffer.allocate(16).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        .putInt(0).putInt(0).putInt(4096).putInt(0).array()

    @Test
    fun `missing callback times out and next probe can license escalation`() {
        val state = RetentionProbeLifecycle()
        val connection = Any()
        val probe = state.start(connection)!!
        assertTrue(state.inFlight)
        assertFlat(state)
        assertTrue(state.timeout(probe))
        assertFalse(state.inFlight)
        assertFlat(state)
        val next = state.start(connection)!!
        assertTrue(state.result(next, connection, true, storageStatus))
        assertEscalates(state)
    }

    @Test
    fun `disconnect interrupts advertised probe and only replacement GATT result licenses escalation`() {
        val state = RetentionProbeLifecycle()
        val oldGatt = Any()
        val oldProbe = state.start(oldGatt)!!
        state.interrupt()
        assertFalse(state.inFlight)
        assertFlat(state)
        val newGatt = Any()
        val newProbe = state.start(newGatt)!!
        assertFalse(state.result(oldProbe, newGatt, true, storageStatus))
        assertTrue(state.inFlight)
        assertFlat(state)
        assertTrue(state.result(newProbe, newGatt, true, storageStatus))
        assertEscalates(state)
    }

    @Test
    fun `disconnect resets previously verified retention and requires a fresh probe`() {
        val state = RetentionProbeLifecycle()
        val oldGatt = Any()
        assertTrue(state.result(state.start(oldGatt)!!, oldGatt, true, storageStatus))
        assertTrue(state.runtimeVerified)
        state.interrupt()
        assertFalse(state.inFlight)
        assertFlat(state)
        val newGatt = Any()
        assertTrue(state.result(state.start(newGatt)!!, newGatt, true, storageStatus))
        assertEscalates(state)
    }

    @Test
    fun `late result after timeout cannot verify even the same GATT or retire its new probe`() {
        val state = RetentionProbeLifecycle()
        val gatt = Any()
        val expired = state.start(gatt)!!
        assertTrue(state.timeout(expired))
        assertFalse(state.result(expired, gatt, true, storageStatus))
        assertFlat(state)
        val next = state.start(gatt)!!
        assertFalse(state.result(expired, gatt, true, storageStatus))
        assertFalse(state.timeout(expired))
        assertTrue(state.inFlight)
        assertFlat(state)
        assertTrue(state.result(next, gatt, true, storageStatus))
        assertEscalates(state)
        // A duplicate old completion must not revoke the new verification either.
        assertFalse(state.result(expired, gatt, true, null))
        assertTrue(state.runtimeVerified)
    }

    @Test
    fun `result from replaced GATT cannot verify current connection`() {
        val state = RetentionProbeLifecycle()
        val probe = state.start(Any())!!
        assertFalse(state.result(probe, Any(), true, storageStatus))
        assertFlat(state)
        assertTrue(state.timeout(probe))
        assertFalse(state.inFlight)
    }

    @Test
    fun `only one probe is allowed in flight and completed timeout is harmless`() {
        val state = RetentionProbeLifecycle()
        val gatt = Any()
        val probe = state.start(gatt)!!
        assertNull(state.start(gatt))
        assertTrue(state.result(probe, gatt, true, storageStatus))
        assertFalse(state.timeout(probe))
        assertTrue(state.runtimeVerified)
        assertNotNull(state.start(gatt))
        assertFalse(state.runtimeVerified)
    }

    @Test
    fun `failed read or missing advertisement completes without licensing escalation`() {
        for ((advertised, payload) in listOf(true to null, true to ByteArray(16), false to storageStatus)) {
            val state = RetentionProbeLifecycle()
            val gatt = Any()
            assertTrue(state.result(state.start(gatt)!!, gatt, advertised, payload))
            assertFalse(state.inFlight)
            assertFlat(state)
            assertNotNull(state.start(gatt))
        }
    }

    private fun assertFlat(state: RetentionProbeLifecycle) {
        assertFalse(state.runtimeVerified)
        val backoff = BleReconnectBackoff()
        repeat(5) { assertEquals(3_000L, backoff.delayForFailure("A", false, null, state.runtimeVerified)) }
    }

    private fun assertEscalates(state: RetentionProbeLifecycle) {
        assertTrue(state.runtimeVerified)
        val backoff = BleReconnectBackoff()
        assertEquals(listOf(3_000L, 6_000L, 12_000L, 30_000L, 60_000L),
            List(5) { backoff.delayForFailure("A", false, null, state.runtimeVerified) })
    }
}
