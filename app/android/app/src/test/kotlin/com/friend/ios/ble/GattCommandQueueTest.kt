package com.friend.ios.ble

import org.junit.Assert.*
import org.junit.Test
import com.friend.ios.ble.GattCommandQueue.Kind

class GattCommandQueueTest {
    private class World {
        val posted = ArrayDeque<() -> Unit>()
        data class Deadline(val task: () -> Unit, var cancelled: Boolean = false)
        val deadlines = mutableListOf<Deadline>()
        val events = mutableListOf<String>()
        val queue = GattCommandQueue<Any>(
            post = { posted.addLast(it) },
            schedule = { _, task ->
                val deadline = Deadline(task)
                deadlines.add(deadline)
                val cancel: () -> Unit = { deadline.cancelled = true }
                cancel
            },
        )
        fun command(owner: Any, name: String, kind: Kind = Kind.DESCRIPTOR, key: String = "audio",
                    execute: (() -> Unit)? = null) = GattCommandQueue.Command(owner, kind, key,
            execute ?: { events.add("start:$name"); Unit }, { events.add("fail:$name") })
        fun runPosted() { while (posted.isNotEmpty()) posted.removeFirst()() }
        fun subscribe(owner: Any, name: String) {
            queue.enqueue(command(owner, name), 15000) {
                events.add("retire:$name")
                queue.cancelOwner(owner, IllegalStateException("subscription timeout"))
            }
        }
    }

    @Test fun `missing descriptor callback retires owner and frees another connection`() {
        val w = World(); val old = Any(); val other = Any()
        w.subscribe(old, "old")
        w.queue.enqueue(w.command(other, "other"))
        w.runPosted()
        assertEquals(listOf("start:old"), w.events)
        w.deadlines.single().task()
        w.runPosted()
        assertEquals(listOf("start:old", "retire:old", "fail:old", "start:other"), w.events)
        assertFalse(w.queue.complete(old, Kind.DESCRIPTOR, "audio"))
        assertTrue(w.queue.matches(other, Kind.DESCRIPTOR, "audio"))
        w.deadlines.single().task() // already retired: no duplicate completion/retry
        assertEquals(1, w.events.count { it == "fail:old" })
    }

    @Test fun `success cancels deadline and stale timer cannot retire a later request`() {
        val w = World(); val owner = Any()
        w.subscribe(owner, "one"); w.runPosted()
        assertTrue(w.queue.complete(owner, Kind.DESCRIPTOR, "audio") { w.events.add("ok:one") })
        assertTrue(w.deadlines.single().cancelled)
        w.subscribe(owner, "two"); w.runPosted()
        w.deadlines.first().task()
        assertTrue(w.queue.matches(owner, Kind.DESCRIPTOR, "audio"))
        assertFalse(w.events.any { it.startsWith("retire:") })
    }

    @Test fun `queued subscription deadline preserves another owners active command`() {
        val w = World(); val other = Any(); val owner = Any()
        w.queue.enqueue(w.command(other, "read", Kind.READ, "battery"))
        w.subscribe(owner, "queued"); w.runPosted()
        w.deadlines.single().task(); w.runPosted()
        assertTrue(w.queue.matches(other, Kind.READ, "battery"))
        assertFalse(w.events.contains("start:queued"))
        assertEquals(1, w.events.count { it == "fail:queued" })
    }

    @Test fun `wrong callback owner kind or characteristic cannot advance the queue`() {
        val w = World(); val owner = Any()
        w.queue.enqueue(w.command(owner, "audio")); w.runPosted()
        assertFalse(w.queue.complete(Any(), Kind.DESCRIPTOR, "audio"))
        assertFalse(w.queue.complete(owner, Kind.READ, "audio"))
        assertFalse(w.queue.complete(owner, Kind.DESCRIPTOR, "storage"))
        assertTrue(w.queue.complete(owner, Kind.DESCRIPTOR, "audio"))
    }

    @Test fun `late old connection callback cannot finish the replacement subscription`() {
        val w = World(); val old = Any(); val replacement = Any()
        w.subscribe(old, "old"); w.runPosted()
        w.deadlines.single().task()
        w.subscribe(replacement, "new"); w.runPosted()
        assertFalse(w.queue.complete(old, Kind.DESCRIPTOR, "audio"))
        assertTrue(w.queue.matches(replacement, Kind.DESCRIPTOR, "audio"))
        assertTrue(w.queue.complete(replacement, Kind.DESCRIPTOR, "audio"))
    }

    @Test fun `cleanup fails active and queued completions exactly once`() {
        val w = World(); val owner = Any()
        w.subscribe(owner, "one"); w.subscribe(owner, "two"); w.runPosted()
        w.queue.cancelOwner(owner, IllegalStateException("disconnect"))
        w.queue.cancelOwner(owner, IllegalStateException("disconnect"))
        w.runPosted()
        assertEquals(listOf("start:one", "fail:one", "fail:two"), w.events)
        assertTrue(w.deadlines.all { it.cancelled })
        assertFalse(w.queue.complete(owner, Kind.DESCRIPTOR, "audio"))
    }

    @Test fun `cleanup before posted operation runs prevents radio side effects`() {
        val w = World(); val owner = Any()
        w.subscribe(owner, "one")
        w.queue.cancelOwner(owner, IllegalStateException("disconnect"))
        w.runPosted()
        assertEquals(listOf("fail:one"), w.events)
    }

    @Test fun `synchronous native exception fails request and releases queue`() {
        val w = World(); val owner = Any()
        w.queue.enqueue(w.command(owner, "throws", execute = { throw SecurityException("permission revoked") }))
        w.queue.enqueue(w.command(owner, "next"))
        w.runPosted()
        assertEquals(listOf("fail:throws", "start:next"), w.events)
    }

    @Test fun `completion delivery cannot start a reentrant command before releasing its slot`() {
        val w = World(); val owner = Any()
        w.subscribe(owner, "one"); w.runPosted()
        w.queue.complete(owner, Kind.DESCRIPTOR, "audio") {
            w.queue.enqueue(w.command(owner, "two"))
            assertTrue(w.posted.isEmpty())
        }
        w.runPosted()
        assertEquals(listOf("start:one", "start:two"), w.events)
    }

    @Test fun `throwing cancellation callback does not strand remaining requests`() {
        val w = World(); val owner = Any(); val other = Any()
        w.queue.enqueue(GattCommandQueue.Command(owner, Kind.READ, "a", {}, { throw IllegalStateException("engine gone") }))
        w.queue.enqueue(w.command(owner, "queued"))
        w.queue.enqueue(w.command(other, "other"))
        w.queue.cancelOwner(owner, IllegalStateException("disconnect")); w.runPosted()
        assertEquals(listOf("fail:queued", "start:other"), w.events)
    }
    @Test fun `throwing result delivery does not cancel a reentrant same-key request`() {
        val w = World(); val owner = Any()
        w.subscribe(owner, "one"); w.runPosted()
        w.queue.complete(owner, Kind.DESCRIPTOR, "audio") {
            w.queue.enqueue(w.command(owner, "two"))
            throw IllegalStateException("engine gone")
        }
        w.runPosted()
        assertTrue(w.queue.matches(owner, Kind.DESCRIPTOR, "audio"))
        assertEquals(listOf("start:one", "start:two"), w.events)
    }

    @Test fun `deadline teardown runs without holding the queue monitor`() {
        val w = World(); val owner = Any()
        var held = false
        w.queue.enqueue(w.command(owner, "one"), 15000) {
            held = Thread.holdsLock(w.queue)
            w.queue.cancelOwner(owner, IllegalStateException("timeout"))
        }
        w.runPosted(); w.deadlines.single().task()
        assertFalse("service teardown must not invert its locks with the queue", held)
    }

    @Test fun `throwing timeout handler still frees the queue and fails requests once`() {
        val w = World(); val owner = Any(); val other = Any()
        w.queue.enqueue(w.command(owner, "one"), 15000) { throw IllegalStateException("bond callback failed") }
        w.queue.enqueue(w.command(owner, "two"))
        w.queue.enqueue(w.command(other, "other"))
        w.runPosted(); w.deadlines.single().task(); w.runPosted()
        assertEquals(listOf("start:one", "fail:one", "fail:two", "start:other"), w.events)
        w.deadlines.single().task()
        assertEquals(1, w.events.count { it == "fail:one" })
    }

    @Test fun `missing MTU callback falls back once and permits following subscription`() {
        val w = World(); val owner = Any()
        var ready = 0
        val finish = OnceCompletion<Unit> { ready++ }
        w.queue.enqueue(GattCommandQueue.Command(owner, Kind.MTU, "", {}, { finish(Unit) }), 15000)
        w.queue.enqueue(w.command(owner, "subscribe"))
        w.runPosted(); w.deadlines.single().task(); w.runPosted()
        assertEquals(1, ready)
        assertTrue(w.queue.matches(owner, Kind.DESCRIPTOR, "audio"))
        assertFalse(w.queue.complete(owner, Kind.MTU) { finish(Unit) })
        w.deadlines.single().task()
        assertEquals(1, ready)
    }

    @Test fun `queued MTU deadline preserves another connection and permits following subscription`() {
        val w = World(); val other = Any(); val owner = Any()
        var ready = 0
        w.queue.enqueue(w.command(other, "read", Kind.READ, "battery"))
        w.queue.enqueue(GattCommandQueue.Command(owner, Kind.MTU, "", {}, { ready++ }), 15000)
        w.queue.enqueue(w.command(owner, "subscribe")); w.runPosted()
        w.deadlines.single().task()
        assertEquals(1, ready)
        assertTrue(w.queue.matches(other, Kind.READ, "battery"))
        w.queue.complete(other, Kind.READ, "battery"); w.runPosted()
        assertTrue(w.queue.matches(owner, Kind.DESCRIPTOR, "audio"))
    }

    @Test fun `MTU timeout fallback does not hold the queue lock during service readiness`() {
        val w = World(); val owner = Any()
        var held = true
        w.queue.enqueue(GattCommandQueue.Command(owner, Kind.MTU, "", {}, {
            held = Thread.holdsLock(w.queue)
        }), 15000)
        w.runPosted(); w.deadlines.single().task()
        assertFalse(held)
    }

    @Test fun `disconnect consumers run outside the queue monitor before successor starts`() {
        val w = World(); val owner = Any(); val other = Any()
        w.queue.enqueue(GattCommandQueue.Command(owner, Kind.READ, "", {}, {
            assertFalse(Thread.holdsLock(w.queue))
            assertTrue(w.posted.isEmpty())
        }))
        w.queue.enqueue(w.command(other, "other")); w.runPosted()
        w.queue.cancelOwner(owner, IllegalStateException("disconnect")); w.runPosted()
        assertEquals(listOf("start:other"), w.events)
    }


    // CCCD regressions from David Zhang's #20378 coordinator now execute the
    // unified production queue rather than a second command authority.
    @Test fun `inline descriptor acknowledgement observes prearmed deadline and cancels it`() {
        val w = World(); val owner = Any()
        w.queue.enqueue(w.command(owner, "inline", execute = {
            assertEquals(1, w.deadlines.size)
            assertFalse(w.deadlines.single().cancelled)
            assertTrue(w.queue.complete(owner, Kind.DESCRIPTOR, "audio") { w.events.add("ok:inline") })
        }), 15000)
        w.runPosted()
        assertEquals(listOf("ok:inline"), w.events)
        assertTrue(w.deadlines.single().cancelled)
        assertFalse(w.queue.matches(owner, Kind.DESCRIPTOR, "audio"))
    }

    @Test fun `expired ENABLE fails queued DISABLE and old ACK cannot complete replacement DISABLE`() {
        val w = World(); val old = Any(); val replacement = Any()
        w.subscribe(old, "ENABLE"); w.subscribe(old, "queued DISABLE"); w.runPosted()
        w.deadlines.first().task(); w.runPosted()
        assertEquals(1, w.events.count { it == "fail:ENABLE" })
        assertEquals(1, w.events.count { it == "fail:queued DISABLE" })
        assertFalse(w.events.contains("start:queued DISABLE"))
        w.subscribe(replacement, "new DISABLE"); w.runPosted()
        assertFalse(w.queue.complete(old, Kind.DESCRIPTOR, "audio"))
        assertTrue(w.queue.matches(replacement, Kind.DESCRIPTOR, "audio"))
        assertTrue(w.queue.complete(replacement, Kind.DESCRIPTOR, "audio"))
    }

    @Test fun `rejected descriptor write settles once and stale deadline leaves successor intact`() {
        val w = World(); val owner = Any()
        w.queue.enqueue(w.command(owner, "rejected", execute = {
            assertTrue(w.queue.complete(owner, Kind.DESCRIPTOR, "audio") { w.events.add("fail:rejected") })
        }), 15000)
        w.subscribe(owner, "next"); w.runPosted()
        val rejectedDeadline = w.deadlines.first()
        assertTrue(rejectedDeadline.cancelled)
        rejectedDeadline.task()
        assertEquals(1, w.events.count { it == "fail:rejected" })
        assertTrue(w.queue.matches(owner, Kind.DESCRIPTOR, "audio"))
        assertFalse(w.events.any { it.startsWith("retire:") })
    }

}
