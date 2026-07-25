package com.friend.ios.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GattOperationQueueTest {
    private class FakeScheduler {
        private data class Scheduled(val task: () -> Unit, var cancelled: Boolean = false)

        private val scheduled = mutableListOf<Scheduled>()

        fun schedule(@Suppress("UNUSED_PARAMETER") delayMillis: Long, task: () -> Unit): () -> Unit {
            val item = Scheduled(task)
            scheduled.add(item)
            return { item.cancelled = true }
        }

        fun runNext() {
            scheduled.firstOrNull { !it.cancelled }?.also {
                it.cancelled = true
                it.task()
            }
        }
    }

    private fun key(
        kind: GattOperationKind,
        target: String = "",
        address: String = "aa:bb:cc:dd:ee:ff",
    ) = GattOperationKey(address, kind, target)

    @Test
    fun writeWithResponseWinsWhenCharacteristicAdvertisesBothModes() {
        assertEquals(
            GattWriteMode.WITH_RESPONSE,
            preferredGattWriteMode(
                supportsWrite = true,
                supportsWriteWithoutResponse = true,
            ),
        )
        assertEquals(
            GattWriteMode.WITHOUT_RESPONSE,
            preferredGattWriteMode(
                supportsWrite = false,
                supportsWriteWithoutResponse = true,
            ),
        )
        assertEquals(
            null,
            preferredGattWriteMode(
                supportsWrite = false,
                supportsWriteWithoutResponse = false,
            ),
        )
    }

    @Test
    fun serializesCommandsUntilMatchingCallbackArrives() {
        val scheduler = FakeScheduler()
        val starts = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )
        val first = key(GattOperationKind.READ_CHARACTERISTIC, "battery")
        val second = key(GattOperationKind.WRITE_CHARACTERISTIC, "control")

        queue.enqueue(first, start = { starts.add("first"); true })
        queue.enqueue(second, start = { starts.add("second"); true })

        assertEquals(listOf("first"), starts)
        assertTrue(queue.complete(first))
        assertEquals(listOf("first", "second"), starts)
        assertTrue(queue.complete(second))
        assertEquals(0, queue.pendingCount())
    }

    @Test
    fun activeOperationIsDistinguishedFromQueuedDuplicate() {
        val scheduler = FakeScheduler()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )
        val discovery = key(GattOperationKind.DISCOVER_SERVICES)
        val read = key(GattOperationKind.READ_CHARACTERISTIC, "battery")

        queue.enqueue(read, start = { true })
        queue.enqueue(discovery, start = { true })

        assertTrue(queue.contains(discovery))
        assertFalse(queue.isActive(discovery))
        assertTrue(queue.complete(read))
        assertTrue(queue.isActive(discovery))
        assertTrue(queue.complete(discovery))
    }

    @Test
    fun completionCleanupRunsBeforeSameTargetSuccessorStarts() {
        val scheduler = FakeScheduler()
        val events = mutableListOf<String>()
        val operation = key(GattOperationKind.READ_CHARACTERISTIC, "battery")
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )

        queue.enqueue(operation, start = { events.add("first-start"); true })
        queue.enqueue(operation, start = { events.add("second-start"); true })

        assertTrue(queue.complete(operation) { events.add("first-cleanup") })
        assertEquals(listOf("first-start", "first-cleanup", "second-start"), events)
        assertTrue(queue.complete(operation))
    }

    @Test
    fun operationEnqueuedByCompletionWaitsUntilCompletionReturns() {
        val scheduler = FakeScheduler()
        val events = mutableListOf<String>()
        val first = key(GattOperationKind.REQUEST_MTU)
        val followUp = key(GattOperationKind.WRITE_DESCRIPTOR)
        lateinit var queue: GattOperationQueue
        queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )

        queue.enqueue(first, start = { events.add("first-start"); true })
        assertTrue(
            queue.complete(first) {
                events.add("callback-start")
                queue.enqueue(followUp, start = { events.add("follow-up-start"); true })
                events.add("callback-end")
            },
        )

        assertEquals(
            listOf("first-start", "callback-start", "callback-end", "follow-up-start"),
            events,
        )
        assertTrue(queue.complete(followUp))
    }

    @Test
    fun staleCallbackCannotCompleteNewerOperation() {
        val scheduler = FakeScheduler()
        val starts = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )
        val first = key(GattOperationKind.REQUEST_MTU)
        val newer = key(GattOperationKind.READ_RSSI)

        queue.enqueue(first, start = { starts.add("mtu"); true })
        queue.enqueue(newer, start = { starts.add("rssi"); true })

        assertTrue(queue.complete(first))
        assertEquals(listOf("mtu", "rssi"), starts)
        assertFalse(queue.complete(first))
        assertEquals(1, queue.pendingCount())
        assertTrue(queue.complete(newer))
    }

    @Test
    fun timeoutFailsCurrentAndUnblocksQueue() {
        val scheduler = FakeScheduler()
        val failures = mutableListOf<GattOperationFailure>()
        val starts = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )

        queue.enqueue(
            key(GattOperationKind.DISCOVER_SERVICES),
            start = { starts.add("discovery"); true },
            onFailure = failures::add,
        )
        queue.enqueue(key(GattOperationKind.READ_RSSI), start = { starts.add("rssi"); true })

        scheduler.runNext()

        assertEquals(listOf(GattOperationFailure.TIMED_OUT), failures)
        assertEquals(listOf("discovery", "rssi"), starts)
    }

    @Test
    fun disconnectDrainsAndFailsPendingOperationsForOnlyThatPeripheral() {
        val scheduler = FakeScheduler()
        val failures = mutableListOf<GattOperationFailure>()
        val starts = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )

        queue.enqueue(
            key(GattOperationKind.READ_CHARACTERISTIC, address = "AA:AA:AA:AA:AA:AA"),
            start = { starts.add("a1"); true },
            onFailure = failures::add,
        )
        queue.enqueue(
            key(GattOperationKind.WRITE_CHARACTERISTIC, address = "AA:AA:AA:AA:AA:AA"),
            start = { starts.add("a2"); true },
            onFailure = failures::add,
        )
        val other = key(GattOperationKind.READ_RSSI, address = "BB:BB:BB:BB:BB:BB")
        queue.enqueue(other, start = { starts.add("b"); true })

        queue.cancelAddress("aa:aa:aa:aa:aa:aa")

        assertEquals(listOf("a1", "b"), starts)
        assertEquals(
            listOf(GattOperationFailure.CANCELLED, GattOperationFailure.CANCELLED),
            failures,
        )
        assertTrue(queue.complete(other))
    }

    @Test
    fun disconnectStillFailsRemainingOperationsWhenOneCallbackThrows() {
        val scheduler = FakeScheduler()
        val failures = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )
        val address = "AA:AA:AA:AA:AA:AA"

        queue.enqueue(
            key(GattOperationKind.READ_CHARACTERISTIC, address = address),
            start = { true },
            onFailure = { throw IllegalStateException("caller failed") },
        )
        queue.enqueue(
            key(GattOperationKind.WRITE_CHARACTERISTIC, address = address),
            start = { true },
            onFailure = { failures.add("second") },
        )

        queue.cancelAddress(address)

        assertEquals(listOf("second"), failures)
        assertEquals(0, queue.pendingCount())
    }

    @Test
    fun rejectedStartFailsAndAdvancesImmediately() {
        val scheduler = FakeScheduler()
        val failures = mutableListOf<GattOperationFailure>()
        val starts = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )

        queue.enqueue(
            key(GattOperationKind.WRITE_DESCRIPTOR),
            start = { starts.add("descriptor"); false },
            onFailure = failures::add,
        )
        val next = key(GattOperationKind.READ_RSSI)
        queue.enqueue(next, start = { starts.add("rssi"); true })

        assertEquals(listOf(GattOperationFailure.REJECTED), failures)
        assertEquals(listOf("descriptor", "rssi"), starts)
        assertTrue(queue.complete(next))
    }

    @Test
    fun periodicRssiIsDeduplicatedAndCannotJumpAheadOfBulkCommands() {
        val scheduler = FakeScheduler()
        val starts = mutableListOf<String>()
        val queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )
        val bulk1 = key(GattOperationKind.WRITE_CHARACTERISTIC, "bulk-1")
        val bulk2 = key(GattOperationKind.WRITE_CHARACTERISTIC, "bulk-2")
        val rssi = key(GattOperationKind.READ_RSSI)

        queue.enqueue(bulk1, start = { starts.add("bulk-1"); true })
        queue.enqueue(bulk2, start = { starts.add("bulk-2"); true })
        repeat(100) {
            if (!queue.contains(rssi)) {
                queue.enqueue(rssi, start = { starts.add("rssi"); true })
            }
        }

        assertEquals(3, queue.pendingCount())
        assertTrue(queue.complete(bulk1))
        assertEquals(listOf("bulk-1", "bulk-2"), starts)
        assertTrue(queue.complete(bulk2))
        assertEquals(listOf("bulk-1", "bulk-2", "rssi"), starts)
        assertTrue(queue.complete(rssi))
    }

    @Test
    fun lateWriteWithoutResponseCallbackCannotReleaseLaterWrite() {
        val scheduler = FakeScheduler()
        val starts = mutableListOf<String>()
        lateinit var queue: GattOperationQueue
        queue = GattOperationQueue(
            dispatch = { it() },
            schedule = scheduler::schedule,
            timeoutMillis = 30_000,
        )
        val target = "control"
        val writeWithoutResponse = key(GattOperationKind.WRITE_WITHOUT_RESPONSE, target)
        val laterWriteWithoutResponse = key(GattOperationKind.WRITE_WITHOUT_RESPONSE, target)
        val optionalCallback = key(GattOperationKind.WRITE_CHARACTERISTIC, target)

        queue.enqueue(
            writeWithoutResponse,
            start = {
                starts.add("wnr")
                queue.complete(writeWithoutResponse)
                true
            },
        )
        queue.enqueue(laterWriteWithoutResponse, start = { starts.add("later-wnr"); true })

        assertEquals(listOf("wnr", "later-wnr"), starts)
        assertFalse(queue.complete(optionalCallback))
        assertEquals(1, queue.pendingCount())
        assertTrue(queue.complete(laterWriteWithoutResponse))
    }
}
