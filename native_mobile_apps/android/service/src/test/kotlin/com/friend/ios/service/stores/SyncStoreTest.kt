package com.friend.ios.service.stores

import com.friend.ios.device.OmiGATT
import com.friend.ios.device.OmiStorage
import com.friend.ios.device.OmiStorage.Event
import com.friend.ios.device.OmiStorage.Notification
import com.friend.ios.network.endpoints.SyncJob
import com.friend.ios.network.endpoints.SyncUpload
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.OfflineRecordings
import com.friend.ios.service.fakeAPI
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class FakeStorageLink : StorageLink {
    override var storageDeviceID: String? = "AA:BB:CC:DD:EE:FF"
    override var codec: OmiGATT.Codec? = OmiGATT.Codec.OpusFS320
    val sent = mutableListOf<OmiStorage.Command>()

    override fun sendStorage(command: OmiStorage.Command) {
        sent += command
    }
}

/** Port of `SyncStoreTests`: offline sync against a fake Omi and a fake backend. */
@OptIn(ExperimentalCoroutinesApi::class)
class SyncStoreTest {
    private val start = 1_760_000_000L
    private val uploads = mutableListOf<Pair<String, ByteArray>>()
    private val jobs = mutableMapOf<String, SyncJob>()

    private fun api(): FakeAPI = fakeAPI {
        "uploadOfflineRecording" does { args ->
            uploads += (args[0] as String) to (args[1] as ByteArray)
            SyncUpload("job-${uploads.size}", "queued")
        }
        "syncJob" does { args -> jobs[args[0] as String] ?: SyncJob("processing") }
    }

    private fun directory(): File = Files.createTempDirectory("offline-sync").toFile()

    private fun TestScope.make(api: FakeAPI, link: FakeStorageLink, directory: File, batch: Long = 600, user: () -> String? = { "alice" }) =
        SyncStore(api.client, directory, backgroundScope, batchRecords = batch, retryDelayMillis = 40, userID = user).also { it.link = link }

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

    @Test fun connectListDownloadUploadAck() = runTest {
        val link = FakeStorageLink()
        val sync = make(api(), link, directory())
        assertEquals(SyncStore.Status.Hidden, sync.status)
        sync.handle(Event.Ready)
        assertEquals(listOf<OmiStorage.Command>(OmiStorage.Command.Info), link.sent)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 10, writeSeq = 13))))
        assertEquals(OmiStorage.Command.Read(10, 3), link.sent.last())
        assertTrue(sync.status is SyncStore.Status.Syncing)
        sync.handle(Event.NotificationReceived(Notification.ReadBegin(10, 3)))
        deliver((0 until 3).map { record(start + it / 10) }, sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 13)))
        assertEquals(OmiStorage.Command.Advance(13), link.sent.last())
        runCurrent()
        assertEquals(1, uploads.size)
        val (filename, data) = uploads[0]
        // Flutter's WAL name: the address without separators, codec, rate, frame samples, start.
        assertEquals("audio_aabbccddeeff_opus_fs320_16000_1_fs320_1760000000.bin", filename)
        assertEquals(15 * 84, data.size)
        assertTrue(data.copyOfRange(0, 5).contentEquals(byteArrayOf(80, 0, 0, 0, 0xA0.toByte())))
        assertEquals(SyncStore.Status.Synced, sync.status)
        // The file stays until the backend's job completes.
        assertEquals(1, sync.files.state.recordings.size)
        jobs["job-1"] = SyncJob("completed")
        advanceTimeBy(50)
        runCurrent()
        assertTrue(sync.files.state.recordings.isEmpty())
    }

    @Test fun recordingsOnlyGoToTheAccountThatWasSignedIn() = runTest {
        var user: String? = "bob"
        val link = FakeStorageLink()
        val sync = make(api(), link, directory(), user = { user })
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 10, writeSeq = 13))))
        user = "alice"
        deliver((0 until 3).map { record(start + it / 10) }, sync)
        user = "bob"
        sync.handle(Event.NotificationReceived(Notification.Done(0, 13)))
        runCurrent()
        assertTrue(uploads.isEmpty())
        assertEquals("alice", sync.files.state.recordings.first().owner)
        user = "alice"
        sync.uploadPending()
        assertEquals(1, uploads.size)
    }

    @Test fun readsInBatchesAndAdvancesAfterEach() = runTest {
        val link = FakeStorageLink()
        val sync = make(api(), link, directory(), batch = 2)
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 3))))
        assertEquals(OmiStorage.Command.Read(0, 2), link.sent.last())
        deliver(listOf(record(start), record(start)), sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 2)))
        assertEquals(listOf(OmiStorage.Command.Advance(2), OmiStorage.Command.Read(2, 1)), link.sent.takeLast(2))
        deliver(listOf(record(start + 1)), sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 3)))
        assertEquals(OmiStorage.Command.Advance(3), link.sent.last())
        assertEquals(SyncStore.Phase.Idle, sync.phase)
        assertEquals(15, sync.files.state.recordings.first().frames)
    }

    /** Custody firmware (ring id): the link drops mid-batch; after a relaunch the next connect frees what was saved. */
    @Test fun disconnectMidwayResumesAfterRelaunch() = runTest {
        val dir = directory()
        val link = FakeStorageLink()
        val first = make(api(), link, dir)
        first.handle(Event.Ready)
        first.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 4, ringID = 7))))
        deliver(listOf(record(start), record(start)), first)
        first.deviceDisconnected()
        assertEquals(2L, first.files.state.durableSeq)
        val relaunched = make(api(), link, dir)
        link.sent.clear()
        relaunched.handle(Event.Ready)
        relaunched.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 4, ringID = 7))))
        assertEquals(listOf(OmiStorage.Command.Info, OmiStorage.Command.Advance(2), OmiStorage.Command.Read(2, 2)), link.sent)
    }

    /** An out-of-step batch frees nothing and asks again. */
    @Test fun outOfStepBatchRestarts() = runTest {
        val link = FakeStorageLink()
        val sync = make(api(), link, directory())
        sync.handle(Event.Ready)
        sync.handle(Event.NotificationReceived(Notification.InfoReply(OmiStorage.Info(readSeq = 0, writeSeq = 3))))
        deliver(listOf(record(start)), sync)
        sync.handle(Event.NotificationReceived(Notification.Done(0, 3)))
        assertEquals(OmiStorage.Command.Stop, link.sent.last())
        assertTrue(link.sent.none { it is OmiStorage.Command.Advance })
        advanceTimeBy(2_100)
        assertEquals(OmiStorage.Command.Info, link.sent.last())
    }

    @Test fun validateCutsAFrameWrittenHalfway() {
        val file = File(directory(), "audio_x_opus_16000_1_fs160_1.bin")
        file.writeBytes(OfflineRecordings.littleEndian(3) + byteArrayOf(1, 2, 3) + OfflineRecordings.littleEndian(10) + byteArrayOf(1, 2))
        assertEquals(1, OfflineRecordings.validate(file))
        assertEquals(7L, file.length())
        assertEquals(1, syncFrames(file.readBytes()).size)
        assertEquals("audio_aabbcc_opus_16000_1_fs160_", OfflineRecordings.fileNamePrefix("AA:BB:CC", OmiGATT.Codec.Opus, 0.01))
    }
}
