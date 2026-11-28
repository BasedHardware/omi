package com.friend.ios.service.stores

import com.friend.ios.device.OmiStorage
import com.friend.ios.device.OmiStorage.Event
import com.friend.ios.device.OmiStorage.Notification
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.endpoints.SyncUpload
import com.friend.ios.service.DebugLog
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.lang.reflect.InvocationHandler
import java.lang.reflect.Proxy
import java.nio.file.Files
import kotlin.coroutines.Continuation
import kotlin.coroutines.intrinsics.COROUTINE_SUSPENDED
import kotlin.coroutines.intrinsics.intercepted

/**
 * Port of `TransferLeaseTests.swift`: the background grant around a transfer. The app asks for
 * extra runtime while the Omi is read or a file is uploaded, and hands it back when the last
 * transfer is done.
 */
class TransferLeaseTest {
    /** A lease over a fake app: `begins` counts the grants taken, `ends` the ones handed back. */
    private class Fake {
        var begins = 0
        var ends = 0
        var admit = true
        var expire: (() -> Unit)? = null

        fun makeLease(log: DebugLog? = null) = TransferLease(
            begin = { expiration ->
                begins += 1
                if (admit) expire = expiration
                admit
            },
            end = { ends += 1 },
            log = log,
        )
    }

    @Test fun oneGrantCoversEveryTransferRunningAtOnce() {
        val app = Fake()
        val lease = app.makeLease()
        lease.acquire()
        lease.acquire()
        assertEquals(1, app.begins)
        assertTrue(lease.isHeld)
        // The first transfer is done; the second one still needs the app awake.
        lease.release()
        assertEquals(0, app.ends)
        lease.release()
        assertEquals(1, app.ends)
        assertFalse(lease.isHeld)
    }

    @Test fun aReleasedLeaseAsksAgainForTheNextTransfer() {
        val app = Fake()
        val lease = app.makeLease()
        lease.acquire()
        lease.release()
        lease.acquire()
        assertEquals(2, app.begins)
        lease.release()
        assertEquals(2, app.ends)
    }

    @Test fun aRefusedGrantLeavesTheCountBalanced() {
        val app = Fake()
        app.admit = false
        val log = DebugLog(null, Files.createTempDirectory("lease-log").toFile())
        val lease = app.makeLease(log)
        lease.acquire()
        assertEquals(1, app.begins)
        assertFalse(lease.isHeld)
        assertEquals(listOf("sync"), log.entries.map { it.source })
        // Nothing was taken, so the transfers that come after it cannot hand back more than that.
        lease.release()
        assertEquals(0, app.ends)
        app.admit = true
        lease.acquire()
        assertEquals(2, app.begins)
        assertTrue(lease.isHeld)
    }

    /**
     * The system takes the time back: whatever was running stops, the grant is gone, and the
     * release the transfers call on their way out does not end it a second time.
     */
    @Test fun theSystemTakingTheTimeBackEndsTheGrantOnce() {
        val app = Fake()
        val lease = app.makeLease()
        lease.acquire()
        lease.acquire()
        app.expire?.invoke()
        assertEquals(1, app.ends)
        assertFalse(lease.isHeld)
        lease.release()
        lease.release()
        assertEquals(1, app.ends)
    }

    @Test fun releasesWithoutAnAcquireDoNothing() {
        val app = Fake()
        val lease = app.makeLease()
        lease.release()
        assertEquals(0, app.ends)
    }
}

/**
 * Port of `SyncTransferLeaseTests`: the lease as the sync actually takes it, held while the Omi is
 * read or a file uploads, given back when the transfer ends, and never stacked up per batch or per
 * concurrent transfer.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SyncTransferLeaseTest {
    private val start = 1_760_000_000L

    /** What the app would have asked for, and handed back. */
    private class Counting {
        var begins = 0
        var ends = 0
    }

    private fun TestScope.make(api: APIClientProtocol, link: FakeStorageLink, counting: Counting, batch: Long = 600, retryDelayMillis: Long = 40): SyncStore {
        val directory: File = Files.createTempDirectory("lease-sync").toFile()
        return SyncStore(api, directory, backgroundScope, batchRecords = batch, retryDelayMillis = retryDelayMillis, userID = { "alice" }).also {
            it.link = link
            it.lease = TransferLease(begin = { counting.begins += 1; true }, end = { counting.ends += 1 })
        }
    }

    private fun api(uploads: MutableList<String> = mutableListOf()): FakeAPI = fakeAPI {
        "uploadOfflineRecording" does { args ->
            uploads += args[0] as String
            SyncUpload("job-${uploads.size}", "queued")
        }
        "syncJob" does { com.friend.ios.network.endpoints.SyncJob("processing") }
    }

    /** One firmware record: timestamp, then `frames` 80-byte Opus frames packed `[size][frame]`. */
    private fun record(timestamp: Long, frames: Int = 5): ByteArray {
        val payload = ByteArray(OmiStorage.payloadSize)
        for (index in 0 until frames) {
            payload[index * 81] = 80
            for (byte in 1..80) payload[index * 81 + byte] = 0xA0.toByte()
        }
        return byteArrayOf((timestamp shr 24).toByte(), (timestamp shr 16).toByte(), (timestamp shr 8).toByte(), timestamp.toByte()) + payload
    }

    /** Feeds records the way BLE does: unaligned 243-byte data notifications. */
    private fun deliver(records: List<ByteArray>, sync: SyncStore) {
        val stream = records.fold(ByteArray(0)) { acc, r -> acc + r }
        var offset = 0
        while (offset < stream.size) {
            sync.handle(Event.NotificationReceived(Notification.Data(stream.copyOfRange(offset, minOf(stream.size, offset + 243)))))
            offset += 243
        }
    }

    /** A read that spans three batches holds one grant, given back once the Omi has nothing left to send. */
    @Test fun aReadHoldsOneGrantAcrossItsBatches() = runTest {
        val counting = Counting()
        val sync = make(api().client, FakeStorageLink(), counting, batch = 2)
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 3))))
        assertEquals(1, counting.begins)
        deliver(listOf(record(start), record(start)), sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 2)))
        // The next batch is the same transfer, not a new one.
        assertEquals(1, counting.begins)
        deliver(listOf(record(start + 1)), sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 3)))
        assertEquals(SyncStore.Phase.Idle, sync.phase)
        assertEquals(1, counting.begins)
        assertEquals(1, counting.ends)
    }

    /** The link drops mid-read: the grant goes back, and the read after the reconnect takes a fresh one. */
    @Test fun aDroppedLinkHandsTheGrantBack() = runTest {
        val counting = Counting()
        val sync = make(api().client, FakeStorageLink(), counting, batch = 2)
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 3))))
        assertEquals(1, counting.begins)
        sync.deviceDisconnected()
        assertEquals(1, counting.ends)
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 3))))
        assertEquals(2, counting.begins)
    }

    /** Files going out hold the grant as well, handed back once the queue is empty. */
    @Test fun anUploadHoldsTheGrantWhileItSends() = runTest {
        val counting = Counting()
        val uploads = mutableListOf<String>()
        val sync = make(api(uploads).client, FakeStorageLink(), counting)
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 1))))
        deliver(listOf(record(start)), sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 1)))
        runCurrent()
        assertEquals(1, uploads.size)
        // The read asked first, the upload after it.
        assertEquals(2, counting.begins)
        assertEquals(2, counting.ends)
    }

    /**
     * A recording that closes while the Omi is still being read goes up right away, under the
     * read's grant: the upload takes no second one, and it is handed back once both are done.
     */
    @Test fun anUploadDuringAReadSharesTheGrant() = runTest {
        val counting = Counting()
        val gate = Gate(api().client)
        // The retry that a still-queued job schedules would take grants of its own; park it.
        val sync = make(gate.client, FakeStorageLink(), counting, batch = 10, retryDelayMillis = 60_000)
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 3))))
        assertEquals(1, counting.begins)
        // The last record is ten minutes later: that closes the recording the first two opened,
        // and the closed file goes up without waiting for the Omi to be finished.
        deliver(listOf(record(start), record(start), record(start + 600)), sync)
        assertNotEquals(SyncStore.Phase.Idle, sync.phase)
        runCurrent()
        assertTrue(gate.isEntered)
        // The read already holds the app awake, so the upload takes nothing.
        assertEquals(1, counting.begins)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 3)))
        runCurrent()
        assertEquals(SyncStore.Phase.Idle, sync.phase)
        // The app stays awake while the upload is still running.
        assertEquals(0, counting.ends)
        gate.open()
        runCurrent()
        // Handed back once both are done; one grant was taken, so exactly one is handed back.
        assertEquals(1, counting.ends)
        assertEquals(1, counting.begins)
    }

    /**
     * An API whose first upload is parked mid-request, so a test can look at the app while it is
     * in flight; the ones after it go straight through.
     */
    @Suppress("UNCHECKED_CAST")
    private class Gate(private val inner: APIClientProtocol) {
        var isEntered = false
            private set
        private var held: Continuation<Any?>? = null

        val client: APIClientProtocol = Proxy.newProxyInstance(
            APIClientProtocol::class.java.classLoader,
            arrayOf(APIClientProtocol::class.java),
            InvocationHandler { _, method, args ->
                if (method.name == "uploadOfflineRecording" && !isEntered) {
                    isEntered = true
                    held = args.last() as Continuation<Any?>
                    return@InvocationHandler COROUTINE_SUSPENDED
                }
                method.invoke(inner, *(args ?: emptyArray()))
            },
        ) as APIClientProtocol

        fun open() {
            held?.intercepted()?.resumeWith(Result.success(SyncUpload("job-gated", "queued")))
            held = null
        }
    }
}
