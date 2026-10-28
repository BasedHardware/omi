package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DiscoveryFailureRetireTest {

    private class Harness(failDisconnect: Boolean = false) {
        val owned = mutableSetOf<Any>()
        val events = mutableListOf<String>()
        val retire = DiscoveryFailureRetire<Any>(
            releaseTrackedLink = { owned.remove(it) },
            cleanupPeripheral = { events.add("cleanup:$it") },
            disconnectLink = {
                if (failDisconnect) throw IllegalStateException("stack refused") else events.add("disconnect")
            },
            closeLink = { events.add("close") },
            onTeardownError = { stage, e -> events.add("error:$stage:${e.message}") },
            notifyDisconnected = { address, gattHash, status -> events.add("notify:$address:$gattHash:$status") },
        )
    }

    @Test
    fun `terminal discovery failure retires the owned link once, teardown before notify`() {
        val h = Harness()
        val gatt = Any()
        h.owned.add(gatt)

        h.retire.onDiscoveryFailed(gatt, "AA:BB:CC:DD:EE:FF", 7, 133)

        assertEquals(
            listOf(
                "cleanup:AA:BB:CC:DD:EE:FF",
                "disconnect",
                "close",
                "notify:AA:BB:CC:DD:EE:FF:7:133",
            ),
            h.events,
        )
        assertFalse(h.owned.contains(gatt))
    }

    @Test
    fun `late duplicate failure callback for the retired link is ignored`() {
        val h = Harness()
        val gatt = Any()
        h.owned.add(gatt)

        h.retire.onDiscoveryFailed(gatt, "AA:BB:CC:DD:EE:FF", 7, 133)
        h.retire.onDiscoveryFailed(gatt, "AA:BB:CC:DD:EE:FF", 7, 133)

        assertEquals(1, h.events.count { it.startsWith("notify:") })
        assertEquals(1, h.events.count { it == "disconnect" })
    }

    @Test
    fun `failure from an untracked or already-disconnected link never tears down or notifies`() {
        val h = Harness()

        h.retire.onDiscoveryFailed(Any(), "AA:BB:CC:DD:EE:FF", 7, 133)

        assertTrue(h.events.isEmpty())
    }

    @Test
    fun `a replacement link stays eligible after the previous one retired`() {
        val h = Harness()
        val first = Any()
        h.owned.add(first)
        h.retire.onDiscoveryFailed(first, "AA:BB:CC:DD:EE:FF", 7, 133)

        val second = Any()
        h.owned.add(second)
        h.retire.onDiscoveryFailed(second, "AA:BB:CC:DD:EE:FF", 9, 257)

        assertEquals(
            listOf(
                "cleanup:AA:BB:CC:DD:EE:FF", "disconnect", "close", "notify:AA:BB:CC:DD:EE:FF:7:133",
                "cleanup:AA:BB:CC:DD:EE:FF", "disconnect", "close", "notify:AA:BB:CC:DD:EE:FF:9:257",
            ),
            h.events,
        )
    }

    @Test
    fun `a throwing disconnect still closes and notifies`() {
        val h = Harness(failDisconnect = true)
        val gatt = Any()
        h.owned.add(gatt)

        h.retire.onDiscoveryFailed(gatt, "AA:BB:CC:DD:EE:FF", 7, 133)

        assertEquals(
            listOf(
                "cleanup:AA:BB:CC:DD:EE:FF",
                "error:disconnect:stack refused",
                "close",
                "notify:AA:BB:CC:DD:EE:FF:7:133",
            ),
            h.events,
        )
    }
}
