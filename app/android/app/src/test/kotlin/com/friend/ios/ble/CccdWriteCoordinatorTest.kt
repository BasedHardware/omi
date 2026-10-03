package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.ArrayDeque

class CccdWriteCoordinatorTest {

    private class Harness {
        val connected = mutableSetOf<Any>()
        val timers = mutableListOf<Runnable>()
        val retired = mutableListOf<Any>()
        val issued = mutableListOf<String>()
        val results = mutableMapOf<String, MutableList<Result<Unit>>>()
        val queue = ArrayDeque<Runnable>()
        var releases = 0
        var acknowledgements = 0
        val coordinator = CccdWriteCoordinator<Any, Any>(
            isConnected = { it in connected },
            ownsCommand = { queue.peek() === it },
            scheduleTimeout = { timers.add(it) },
            cancelTimeout = { timers.remove(it) },
            completeCommand = {
                check(queue.peek() === it)
                queue.remove()
                releases++
            },
            retireConnection = {
                connected.remove(it)
                retired.add(it)
                queue.clear()
            },
            onAcknowledged = { acknowledgements++ },
        )

        fun enqueue(gatt: Any, descriptor: Any, label: String, earlyAck: Boolean = false,
                    accepted: Boolean = true): Runnable {
            lateinit var write: CccdWriteCoordinator.Write<Any, Any>
            val command = Runnable {
                coordinator.start(write) {
                    issued.add(label)
                    if (earlyAck) {
                        assertEquals(1, timers.size)
                        coordinator.onDescriptorWrite(gatt, descriptor, Result.success(Unit))
                    }
                    accepted
                }
            }
            write = coordinator.register(gatt, descriptor, command) {
                results.getOrPut(label) { mutableListOf() }.add(it)
            }
            queue.add(command)
            return command
        }

        fun start() = queue.peek().run()
        fun ack(gatt: Any, descriptor: Any) =
            coordinator.onDescriptorWrite(gatt, descriptor, Result.success(Unit))
    }

    @Test
    fun `failed descriptor ACK does not replenish recovery budget`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        h.enqueue(gatt, descriptor, "A")
        h.start()
        h.coordinator.onDescriptorWrite(gatt, descriptor, Result.failure(IllegalStateException("GATT failure")))
        assertEquals(0, h.acknowledgements)
        assertTrue(h.results.getValue("A").single().isFailure)
        assertEquals(1, h.releases)
    }

    @Test
    fun `late ACK after timeout cannot settle a replacement connection write`() {
        val h = Harness()
        val oldGatt = Any()
        val newGatt = Any()
        val descriptor = Any() // Deliberately reuse the descriptor identity.
        h.connected.add(oldGatt)
        h.enqueue(oldGatt, descriptor, "A")
        h.start()
        h.timers.single().run()

        assertEquals(listOf(oldGatt), h.retired)
        assertTrue(h.results.getValue("A").single().isFailure)
        assertEquals(0, h.releases)
        h.connected.add(newGatt)
        h.enqueue(newGatt, descriptor, "B")
        h.start()
        h.ack(oldGatt, descriptor)
        assertEquals(0, h.acknowledgements)
        assertFalse(h.results.containsKey("B"))
        assertEquals(1, h.queue.size)
        h.ack(newGatt, descriptor)
        assertEquals(1, h.acknowledgements)
        assertTrue(h.results.getValue("B").single().isSuccess)
        assertEquals(1, h.releases)
    }

    @Test
    fun `immediate ACK cancels the prearmed timer and stale timer cannot fail next owner`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        h.enqueue(gatt, descriptor, "A")
        h.start()
        val oldTimer = h.timers.single()
        h.ack(gatt, descriptor)
        assertTrue(h.timers.isEmpty())

        h.enqueue(gatt, descriptor, "B")
        h.start()
        oldTimer.run()
        assertFalse(h.results.containsKey("B"))
        assertTrue(h.retired.isEmpty())
        assertEquals(1, h.queue.size)
        h.ack(gatt, descriptor)
        assertEquals(2, h.releases)

        h.enqueue(gatt, descriptor, "inline ACK", earlyAck = true)
        h.start()
        assertTrue(h.timers.isEmpty())
        assertTrue(h.results.getValue("inline ACK").single().isSuccess)
    }

    @Test
    fun `timed out ENABLE fails queued DISABLE and old ACK cannot complete new DISABLE`() {
        val h = Harness()
        val oldGatt = Any()
        val newGatt = Any()
        val descriptor = Any()
        h.connected.add(oldGatt)
        h.enqueue(oldGatt, descriptor, "ENABLE")
        val oldDisable = h.enqueue(oldGatt, descriptor, "queued DISABLE")
        h.start()
        h.timers.single().run()
        assertTrue(h.results.getValue("queued DISABLE").single().isFailure)
        oldDisable.run() // A runnable posted before retirement must not issue a write.
        assertEquals(listOf("ENABLE"), h.issued)

        h.connected.add(newGatt)
        h.enqueue(newGatt, descriptor, "new DISABLE")
        h.start()
        h.ack(oldGatt, descriptor)
        assertFalse(h.results.containsKey("new DISABLE"))
        h.ack(newGatt, descriptor)
        assertTrue(h.results.getValue("new DISABLE").single().isSuccess)
        assertEquals(1, h.releases)
    }

    @Test
    fun `ACK and timeout cannot release a different queue owner`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        h.enqueue(gatt, descriptor, "A")
        h.start()
        val timeout = h.timers.single()
        h.queue.clear()
        h.queue.add(Runnable {})
        h.ack(gatt, descriptor)
        timeout.run()
        assertEquals(0, h.releases)
        assertEquals(1, h.queue.size)
        assertTrue(h.retired.isEmpty())
        h.coordinator.failAll(Exception("Disconnected"))
        assertEquals(1, h.results.getValue("A").size)
        assertTrue(h.timers.isEmpty())
    }

    @Test
    fun `rejected write cancels timer and completes exactly once`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        h.enqueue(gatt, descriptor, "A", accepted = false)
        h.start()
        h.ack(gatt, descriptor)
        assertEquals(1, h.results.getValue("A").size)
        assertTrue(h.results.getValue("A").single().isFailure)
        assertTrue(h.timers.isEmpty())
        assertTrue(h.retired.isEmpty())
        assertEquals(1, h.releases)
    }

    @Test
    fun `retired GATT cannot issue a later write even with the same descriptor`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        h.enqueue(gatt, descriptor, "A")
        h.start()
        h.timers.single().run()
        h.enqueue(gatt, descriptor, "B")
        h.start()
        h.ack(gatt, descriptor)
        assertEquals(listOf("A"), h.issued)
        assertTrue(h.results.getValue("B").single().isFailure)
        assertEquals(listOf(gatt), h.retired)
        assertEquals(1, h.releases)
    }

    @Test
    fun `descriptor queue claim survives from registration until its own settlement`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        val enable = h.enqueue(gatt, descriptor, "ENABLE")
        val disable = h.enqueue(gatt, descriptor, "DISABLE")
        assertTrue(h.coordinator.tracksCommand(enable))
        assertTrue(h.coordinator.tracksCommand(disable))
        assertFalse(h.coordinator.tracksCommand(Runnable {}))
        h.start()
        h.ack(gatt, descriptor)
        assertFalse(h.coordinator.tracksCommand(enable))
        assertTrue(h.coordinator.tracksCommand(disable))
        assertFalse(h.results.containsKey("DISABLE"))
        h.start()
        h.ack(gatt, descriptor)
        assertFalse(h.coordinator.tracksCommand(disable))
        assertEquals(2, h.releases)
    }

    @Test
    fun `cleanup fails pending and queued replies once without advancing cleared queue`() {
        val h = Harness()
        val gatt = Any()
        val descriptor = Any()
        h.connected.add(gatt)
        h.enqueue(gatt, descriptor, "A")
        val queued = h.enqueue(gatt, descriptor, "B")
        h.start()
        val oldTimer = h.timers.single()
        h.connected.remove(gatt)
        h.queue.clear()
        h.coordinator.failAll(Exception("Disconnected"))
        h.coordinator.failAll(Exception("Disconnected again"))
        queued.run()
        oldTimer.run()
        h.ack(gatt, descriptor)
        assertEquals(1, h.results.getValue("A").size)
        assertEquals(1, h.results.getValue("B").size)
        assertTrue(h.results.values.all { it.single().isFailure })
        assertEquals(listOf("A"), h.issued)
        assertEquals(0, h.releases)
        assertTrue(h.timers.isEmpty())
    }
}
