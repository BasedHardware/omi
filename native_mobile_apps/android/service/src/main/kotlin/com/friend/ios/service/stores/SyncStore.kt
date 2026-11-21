package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.device.OmiGATT
import com.friend.ios.device.OmiStorage
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.service.OfflineRecordings
import com.friend.ios.service.PendingRecording
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/** The connected Omi as offline sync sees it (real: `DeviceStore`). */
interface StorageLink {
    /** The connected Omi's id; null while none is connected. */
    val storageDeviceID: String?
    val codec: OmiGATT.Codec?
    fun sendStorage(command: OmiStorage.Command)
}

/**
 * Port of `SyncStore.swift`: offline sync, what the Omi recorded while the phone was away reaches
 * the backend on its own.
 *
 * Whenever an Omi with storage is connected: ask how much it holds (INFO), read it in batches
 * alongside live audio (the firmware shares its send queue between both), write each recording to
 * disk, then let the Omi free what is safely on disk (ADVANCE). Recordings upload to
 * `v2/sync-local-files` and are deleted once the backend's job completes. The file queue and the
 * saved position survive disconnects and relaunches.
 *
 * Firmware without the custody contract frees records itself as they are delivered over
 * Bluetooth, so audio is written to disk as it arrives, not at the end of a batch.
 */
class SyncStore(
    private val api: APIClientProtocol,
    directory: File,
    private val scope: CoroutineScope,
    private val batchRecords: Long = 600,
    private val retryDelayMillis: Long = 30_000,
    private val stallTimeoutMillis: Long = 15_000,
    /** The signed-in account; recordings are tagged with it and uploaded only to it. */
    internal val userID: () -> String? = { null },
    private val clock: () -> Long = { System.nanoTime() / 1_000_000 },
    private val nowSeconds: () -> Double = { System.currentTimeMillis() / 1000.0 },
) {
    sealed interface Status {
        /** No Omi with offline storage seen yet. */
        data object Hidden : Status
        data class Waiting(val seconds: Int) : Status
        data class Syncing(val progress: Double) : Status
        data object Synced : Status
    }

    var status: Status by mutableStateOf(Status.Hidden)
        private set

    /** The Omi's storage as last read (used and free bytes); `null` before the first read. */
    var deviceStorage: OmiStorage.Status? by mutableStateOf(null)
        private set

    /** Recordings saved here and not yet processed by the backend, oldest first. */
    var recordings: List<PendingRecording> by mutableStateOf(emptyList())
        private set

    val hasPending: Boolean get() = status is Status.Waiting || status is Status.Syncing

    var link: StorageLink? = null
    /**
     * The Omi's Opus frames as 16 kHz PCM16 (the app supplies the platform decoder, iOS
     * `OpusFileDecoder`); null leaves Omi recordings unplayable (and-askomi).
     */
    var decodeOpus: ((List<ByteArray>) -> ByteArray?)? = null
    /**
     * Background runtime held while a transfer runs ([TransferLease]); null in tests and the local
     * harness, where there is no app to be put away.
     */
    var lease: TransferLease? = null
    /**
     * Whether the device read in progress took the lease (the read goes on in batches, so this
     * keeps the take and the give-back paired).
     */
    private var holdsLease = false

    internal sealed interface Phase {
        data object Idle : Phase
        data object AwaitingInfo : Phase

        /** Records `start ..< start + received` arrived in this batch; `end` is the Omi's write position. */
        data class Reading(val start: Long, val received: Long, val end: Long, val ringID: Long?) : Phase
    }

    internal var phase: Phase = Phase.Idle
        private set
    internal val files = OfflineRecordings(directory)
    private var storageReady = false
    private var reassembler = OmiStorage.Reassembler()
    private var lastActivity = clock()
    private var restartsLeft = 3
    private var uploading = false
    private var progress: Pair<Double, Double>? = null
    private var retryJob: Job? = null
    private var watchdogJob: Job? = null
    private var restartJob: Job? = null

    init {
        refresh()
    }

    /** App launch (signed in): uploads whatever is still waiting. */
    fun start() = uploadSoon()

    internal fun uploadSoon() {
        scope.launch { uploadPending() }
    }

    fun handle(event: OmiStorage.Event) {
        lastActivity = clock()
        when (event) {
            OmiStorage.Event.Ready -> {
                storageReady = true
                restartsLeft = 3
                begin()
            }
            is OmiStorage.Event.StatusRead -> {
                deviceStorage = event.status
                if (phase == Phase.Idle) files.update { it.copy(devicePending = event.status.unreadRecords, known = true) }
                refresh()
            }
            is OmiStorage.Event.NotificationReceived -> handle(event.notification)
        }
    }

    /** The codec arrived after storage was ready. */
    fun codecKnown() = begin()

    fun deviceDisconnected() {
        storageReady = false
        (phase as? Phase.Reading)?.let { reading ->
            // Whatever arrived is safe on disk; custody firmware is told on the next connect.
            files.closeOpen()
            files.update { it.copy(durableSeq = reading.start + reading.received, ringID = reading.ringID) }
        }
        stopTransfer()
        uploadSoon()
    }

    private fun begin() {
        if (!storageReady || phase != Phase.Idle || link?.storageDeviceID == null || link?.codec == null) return
        phase = Phase.AwaitingInfo
        link?.sendStorage(OmiStorage.Command.Info)
        watch()
    }

    private fun handle(notification: OmiStorage.Notification) {
        when (notification) {
            is OmiStorage.Notification.InfoReply -> if (phase == Phase.AwaitingInfo) received(notification.info)
            is OmiStorage.Notification.ReadBegin -> {
                val reading = phase as? Phase.Reading ?: return
                if (reading.received == 0L && notification.start != reading.start) restart()
            }
            is OmiStorage.Notification.Data -> if (phase is Phase.Reading) ingest(notification.bytes)
            is OmiStorage.Notification.Done -> finishBatch(notification.status, notification.nextSeq)
            is OmiStorage.Notification.Ack ->
                // Storage not ready (SD remounting) or a refused read: ask again shortly.
                if (notification.status != OmiStorage.AckStatus.ok && notification.status != OmiStorage.AckStatus.seqOutOfRange && phase != Phase.Idle) restart()
            else -> Unit
        }
    }

    private fun received(info: OmiStorage.Info) {
        var start = info.readSeq
        val saved = files.state
        // Custody firmware frees only on ADVANCE: skip what an interrupted sync already saved.
        val durable = saved.durableSeq
        if (info.ringID != null && saved.ringID == info.ringID && durable != null && durable > start && durable <= info.writeSeq) {
            link?.sendStorage(OmiStorage.Command.Advance(durable))
            start = durable
        }
        files.update { state ->
            state.copy(
                devicePending = if (info.writeSeq > start) info.writeSeq - start else 0,
                known = true,
                // A position saved for another ring means nothing here.
                durableSeq = if (state.ringID != info.ringID) null else state.durableSeq,
                ringID = info.ringID,
            )
        }
        if (start >= info.writeSeq) {
            stopTransfer()
            uploadSoon()
            return
        }
        beginProgress()
        read(start, info.writeSeq, info.ringID)
    }

    private fun read(start: Long, end: Long, ringID: Long?) {
        takeLease()
        reassembler = OmiStorage.Reassembler()
        phase = Phase.Reading(start, 0, end, ringID)
        link?.sendStorage(OmiStorage.Command.Read(start, minOf(batchRecords, end - start)))
        refresh()
    }

    private fun ingest(bytes: ByteArray) {
        val reading = phase as? Phase.Reading ?: return
        val deviceID = link?.storageDeviceID ?: return
        val codec = link?.codec ?: return
        val records = reassembler.append(bytes)
        var closed = false
        for (record in records) {
            closed = files.append(record, deviceID, codec, userID(), nowSeconds()) || closed
        }
        phase = reading.copy(received = reading.received + records.size)
        progress = progress?.let { it.copy(first = it.first + records.size * files.state.secondsPerRecord) }
        if (closed) uploadSoon()
        refresh()
    }

    private fun finishBatch(status: Int, nextSeq: Long) {
        val reading = phase as? Phase.Reading ?: return
        files.sync()
        if (status != OmiStorage.AckStatus.ok || nextSeq != reading.start + reading.received || reassembler.pendingBytes != 0) {
            // Out of step: keep what is on disk, free nothing, read again from the Omi's position.
            restart()
            return
        }
        link?.sendStorage(OmiStorage.Command.Advance(nextSeq))
        files.update {
            it.copy(durableSeq = nextSeq, ringID = reading.ringID, devicePending = if (reading.end > nextSeq) reading.end - nextSeq else 0)
        }
        if (nextSeq < reading.end && reading.received > 0) {
            read(nextSeq, reading.end, reading.ringID)
        } else {
            files.closeOpen()
            stopTransfer()
            uploadSoon()
        }
    }

    /** Stops the transfer and asks the Omi where it stands again (a few times per connection). */
    private fun restart() {
        link?.sendStorage(OmiStorage.Command.Stop)
        files.closeOpen()
        stopTransfer()
        if (restartsLeft <= 0) return
        restartsLeft -= 1
        restartJob = scope.launch {
            delay(2_000)
            begin()
        }
    }

    private fun stopTransfer() {
        phase = Phase.Idle
        releaseLease()
        watchdogJob?.cancel()
        refresh()
    }

    /**
     * The read is about to ask the Omi for a batch: it needs the app to stay awake for it. The
     * batches of one read share one take, so a fresh batch in the middle does not stack up.
     */
    private fun takeLease() {
        if (holdsLease) return
        holdsLease = true
        lease?.acquire()
    }

    private fun releaseLease() {
        if (!holdsLease) return
        holdsLease = false
        lease?.release()
    }

    /** No reply for `stallTimeout`: the transfer is stuck. */
    private fun watch() {
        watchdogJob?.cancel()
        watchdogJob = scope.launch {
            while (isActive) {
                delay(250)
                if (phase == Phase.Idle) return@launch
                if (clock() - lastActivity > stallTimeoutMillis) {
                    restart()
                    return@launch
                }
            }
        }
    }

    // MARK: Upload

    /** Uploads every finished recording, then checks on jobs still processing. */
    suspend fun uploadPending() {
        if (uploading) return
        uploading = true
        // Files are being sent: the app stays awake for them too, not only for the read.
        lease?.acquire()
        beginProgress()
        try {
            val tried = mutableSetOf<String>()
            // Another account's recordings wait for that account (an untagged one is the current
            // user's); signed out, nothing goes anywhere.
            val account = userID()
            fun isMine(recording: PendingRecording) = account != null && (recording.owner == null || recording.owner == account)
            while (true) {
                val next = files.state.recordings.firstOrNull {
                    it.jobID == null && it.manual != true && !it.isKept && it.filename !in tried && isMine(it)
                } ?: break
                tried += next.filename
                val data = files.data(next)
                if (data == null) {
                    files.remove(next.filename)
                    continue
                }
                try {
                    val upload = api.uploadOfflineRecording(next.filename, data)
                    progress = progress?.let { it.copy(first = it.first + next.seconds) }
                    val jobID = upload.jobID
                    if (jobID != null && upload.status != "completed") files.setJob(jobID, next.filename) else files.remove(next.filename)
                } catch (e: APIError.Http) {
                    // The server will never take this file (bad time, too old, undecodable).
                    if (e.status in setOf(400, 413, 422)) {
                        files.remove(next.filename)
                    } else {
                        scheduleRetry()
                        return
                    }
                } catch (e: Exception) {
                    scheduleRetry()
                    return
                }
                refresh()
            }
            checkJobs()
        } finally {
            uploading = false
            lease?.release()
            refresh()
        }
    }

    private suspend fun checkJobs() {
        var waiting = false
        for (recording in files.state.recordings) {
            val jobID = recording.jobID ?: continue
            try {
                val job = api.syncJob(jobID)
                when {
                    job == null -> {
                        files.setJob(null, recording.filename)
                        waiting = true
                    }
                    !job.isFinished -> waiting = true
                    job.status == "completed" || job.isPermanentFailure -> files.remove(recording.filename)
                    recording.failedJobs < 2 -> {
                        files.setJob(null, recording.filename, failed = true)
                        waiting = true
                    }
                    // Failed three times: tried again on the next launch or connect, not in a loop.
                    else -> files.setJob(null, recording.filename, failed = true)
                }
            } catch (e: Exception) {
                waiting = true
            }
        }
        if (waiting) scheduleRetry()
    }

    private fun scheduleRetry() {
        retryJob?.cancel()
        retryJob = scope.launch {
            delay(retryDelayMillis)
            uploadPending()
        }
    }

    // MARK: Status

    private val waitingSeconds: Double
        get() {
            val waiting = files.state.recordings.filter { it.jobID == null && it.manual != true && !it.isKept }.sumOf { it.seconds }
            return waiting + (files.state.open?.seconds ?: 0.0) + files.state.devicePending * files.state.secondsPerRecord
        }

    internal fun refresh() {
        val active = phase != Phase.Idle || uploading
        if (!active) progress = null
        val current = progress
        val next: Status = when {
            active && current != null -> Status.Syncing(minOf(0.99, current.first / maxOf(current.second, 1.0)))
            waitingSeconds >= 1 -> Status.Waiting(Math.round(waitingSeconds).toInt())
            files.state.known || files.state.recordings.isNotEmpty() -> Status.Synced
            else -> Status.Hidden
        }
        if (next != status) status = next
        if (files.state.recordings != recordings) recordings = files.state.recordings
    }

    /** Deletes a recording that is waiting here (it never reaches the backend). */
    fun delete(filename: String) {
        files.remove(filename)
        refresh()
    }

    private fun beginProgress() {
        if (progress != null) return
        val total = files.state.recordings.filter { it.jobID == null && it.manual != true && !it.isKept }.sumOf { it.seconds } +
            files.state.devicePending * files.state.secondsPerRecord * 2
        if (total > 0) progress = 0.0 to total
    }

    companion object {
        /** `filesDir/OfflineSync` (not backed up: the manifest disables backup). */
        fun defaultDirectory(filesDir: File): File = File(filesDir, "OfflineSync").also { it.mkdirs() }
    }
}
