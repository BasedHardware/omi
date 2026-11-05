package com.friend.ios.device

import java.io.ByteArrayOutputStream
import java.util.UUID

/**
 * Offline storage (firmware `lib/core/storage.c`). `storageControl` takes commands and notifies
 * replies and audio; `storageStatus` is a 16-byte read.
 */
val OmiGATT.storageService: UUID get() = UUID.fromString("30295780-4301-eabd-2904-2849adfeae43")
val OmiGATT.storageControl: UUID get() = UUID.fromString("30295781-4301-eabd-2904-2849adfeae43")
val OmiGATT.storageStatus: UUID get() = UUID.fromString("30295782-4301-eabd-2904-2849adfeae43")

/** Time sync (firmware `transport.c`): the Omi records to storage only once its clock is set. */
val OmiGATT.timeSyncService: UUID get() = UUID.fromString("19b10030-e8f2-537e-4f6c-d104768a1214")
val OmiGATT.timeSyncWrite: UUID get() = UUID.fromString("19b10031-e8f2-537e-4f6c-d104768a1214")

/**
 * Port of `OmiStorage.swift`: the Omi's SD ring buffer, what it recorded while the phone was away.
 * One record is `[timestamp u32 BE][440 audio bytes]`; the audio bytes are packed `[size u8][frame]...`
 * (firmware `transport.c` `write_to_storage`). Sequence numbers count records. Unsigned firmware
 * integers are carried as `Long`.
 */
object OmiStorage {
    const val recordSize = 444
    const val payloadSize = 440

    /** Custody firmware marks a timestamp taken while the clock was unset (seconds since boot). */
    internal const val uptimeFlag: Long = 0x8000_0000L

    sealed interface Command {
        data object Info : Command

        /** `count` null streams everything from `start`. */
        data class Read(val start: Long, val count: Long?) : Command

        /** Frees every record below `seq`. */
        data class Advance(val seq: Long) : Command
        data object Stop : Command

        val bytes: ByteArray
            get() = when (this) {
                Info -> byteArrayOf(0x10)
                is Read -> byteArrayOf(0x11) + start.bigEndianBytes(8) + (count?.bigEndianBytes(4) ?: ByteArray(0))
                is Advance -> byteArrayOf(0x12) + seq.bigEndianBytes(8)
                Stop -> byteArrayOf(0x03)
            }
    }

    object AckStatus {
        const val ok = 0
        const val notReady = 9
        const val seqOutOfRange = 10
    }

    /**
     * `NOTIFY_INFO`. Custody firmware appends capabilities, a contract version and a ring id
     * (`app/lib/services/wals/PENDANT_RING_CUSTODY.md` §1c); a ring id changes whenever sequence
     * numbers restart, so a saved position is only meaningful for the same ring id.
     */
    data class Info(
        val readSeq: Long,
        val writeSeq: Long,
        val capacity: Long = 0,
        val dropped: Long = 0,
        val ringID: Long? = null,
    ) {
        val unread: Long get() = if (writeSeq > readSeq) writeSeq - readSeq else 0
    }

    /** The status read: four little-endian `u32`s. */
    data class Status(val usedBytes: Long, val unreadRecords: Long, val freeBytes: Long, val clockValid: Boolean) {
        companion object {
            fun from(value: ByteArray): Status? {
                if (value.size < 16) return null
                return Status(
                    usedBytes = littleEndianU32(value, 0),
                    unreadRecords = littleEndianU32(value, 4),
                    freeBytes = littleEndianU32(value, 8),
                    clockValid = littleEndianU32(value, 12) != 0L,
                )
            }
        }
    }

    sealed interface Notification {
        data class Ack(val status: Int) : Notification
        data class InfoReply(val info: Info) : Notification

        /** Raw record bytes, not aligned to records. */
        class Data(val bytes: ByteArray) : Notification {
            override fun equals(other: Any?) = other is Data && other.bytes.contentEquals(bytes)
            override fun hashCode() = bytes.contentHashCode()
        }
        data class Done(val status: Int, val nextSeq: Long) : Notification
        data class ReadBegin(val start: Long, val count: Long) : Notification
        data class Other(val opcode: Int) : Notification

        companion object {
            fun from(value: ByteArray): Notification? {
                if (value.isEmpty()) return null
                val opcode = value[0].toInt() and 0xFF
                return when {
                    opcode == 0x01 && value.size >= 2 -> Ack(value[1].toInt() and 0xFF)
                    opcode == 0x02 && value.size >= 31 -> InfoReply(
                        Info(
                            readSeq = bigEndianU64(value, 1),
                            writeSeq = bigEndianU64(value, 9),
                            capacity = bigEndianU32(value, 17),
                            dropped = bigEndianU64(value, 21),
                            ringID = if (value.size >= 41) bigEndianU64(value, 33) else null,
                        ),
                    )
                    opcode == 0x03 -> Data(value.copyOfRange(1, value.size))
                    opcode == 0x04 && value.size >= 10 -> Done(value[1].toInt() and 0xFF, bigEndianU64(value, 2))
                    opcode == 0x05 && value.size >= 13 -> ReadBegin(bigEndianU64(value, 1), bigEndianU32(value, 9))
                    opcode in setOf(0x01, 0x02, 0x04, 0x05) -> null
                    else -> Other(opcode)
                }
            }
        }
    }

    /** What the driver reports about storage, on its own lossless stream. */
    sealed interface Event {
        /** Notifications are on: commands can be sent. */
        data object Ready : Event
        data class StatusRead(val status: Status) : Event
        data class NotificationReceived(val notification: Notification) : Event
    }

    class Record(
        /** Epoch seconds; null when the Omi's clock was not set. */
        val timestamp: Long?,
        val frames: List<ByteArray>,
    ) {
        override fun equals(other: Any?) = other is Record && other.timestamp == timestamp &&
            other.frames.size == frames.size && other.frames.indices.all { other.frames[it].contentEquals(frames[it]) }

        override fun hashCode() = timestamp.hashCode() * 31 + frames.size

        companion object {
            fun from(record: ByteArray): Record {
                val raw = if (record.size >= 4) bigEndianU32(record, 0) else 0
                val timestamp = if (raw == 0L || raw and uptimeFlag != 0L) null else raw
                return Record(timestamp, frames(record.copyOfRange(minOf(4, record.size), record.size)))
            }
        }
    }

    /**
     * Unpacks `[size][frame]...`. A zero byte is padding. At a block boundary the firmware writes the
     * size of a frame that went to the next block and nothing after it is valid, hence `>=`
     * (same rule as upstream `ring_protocol.dart` `parseAudioPayload`).
     */
    fun frames(payload: ByteArray): List<ByteArray> {
        val frames = mutableListOf<ByteArray>()
        var offset = 0
        while (offset < payload.size - 1) {
            val size = payload[offset].toInt() and 0xFF
            if (size == 0) {
                offset += 1
                continue
            }
            if (offset + 1 + size >= payload.size) break
            frames += payload.copyOfRange(offset + 1, offset + 1 + size)
            offset += 1 + size
        }
        return frames
    }

    /** Cuts the data notifications back into records. */
    class Reassembler {
        private val buffer = ByteArrayOutputStream()
        private var pending = ByteArray(0)

        val pendingBytes: Int get() = pending.size

        fun append(bytes: ByteArray): List<Record> {
            buffer.reset()
            buffer.write(pending)
            buffer.write(bytes)
            val all = buffer.toByteArray()
            val records = mutableListOf<Record>()
            var offset = 0
            while (all.size - offset >= recordSize) {
                records += Record.from(all.copyOfRange(offset, offset + recordSize))
                offset += recordSize
            }
            pending = all.copyOfRange(offset, all.size)
            return records
        }
    }

    /** The time sync write: epoch seconds as a little-endian `u32` (Flutter `performSyncTime`). */
    fun timeSyncPayload(epochMillis: Long): ByteArray = (epochMillis / 1000).coerceIn(0, 0xFFFF_FFFFL).littleEndianBytes(4)
}
