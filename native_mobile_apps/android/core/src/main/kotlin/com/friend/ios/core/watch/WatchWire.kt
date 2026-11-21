package com.friend.ios.core.watch

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream

/**
 * How the watch payloads travel over the Wear OS Data Layer (WatchConnectivity carries property
 * list dictionaries; the Data Layer carries bytes):
 * - control messages: one encoded dictionary per `MessageClient` message on [MESSAGE_PATH];
 * - a recording: one `ChannelClient` stream on [RECORDING_CHANNEL_PATH], watch to phone, carrying
 *   length-prefixed frames ([writeFrame]) in order: `startRecording`, the audio chunks, `stopRecording`.
 *   One stream keeps the stop from overtaking the last audio, which iOS gets by queueing;
 * - the phone's state: a `DataItem` on [PHONE_STATE_PATH] (iOS application context, latest only);
 * - a message the other side could not take live: a `DataItem` under [QUEUED_TO_PHONE] or
 *   [QUEUED_TO_WATCH] (iOS `transferUserInfo`: kept by the Data Layer and delivered once the other
 *   side is there; the receiver deletes it).
 */
object WatchWire {
    const val MESSAGE_PATH = "/omi/watch/message"
    const val RECORDING_CHANNEL_PATH = "/omi/watch/recording"
    const val PHONE_STATE_PATH = "/omi/watch/phone-state"
    const val QUEUED_TO_PHONE = "/omi/watch/queued/to-phone/"
    const val QUEUED_TO_WATCH = "/omi/watch/queued/to-watch/"
    /** The `DataMap` key that holds the encoded dictionary of a data item. */
    const val PAYLOAD_KEY = "payload"
    /** Capabilities (res/values/wear.xml): the phone app and the watch app announce themselves. */
    const val PHONE_CAPABILITY = "omi_phone"
    const val WATCH_CAPABILITY = "omi_watch"

    private const val VERSION = 1
    /** A frame is at most one chunk plus its keys; anything larger is a broken stream. */
    const val MAX_FRAME_BYTES = 1 shl 20

    private const val NULL = 0
    private const val STRING = 1
    private const val BOOL = 2
    private const val LONG = 3
    private const val DOUBLE = 4
    private const val BYTES = 5

    /** One dictionary as bytes. Values: null, String, Boolean, whole numbers, Float/Double, ByteArray. */
    fun encode(payload: Map<String, Any?>): ByteArray {
        val bytes = ByteArrayOutputStream()
        DataOutputStream(bytes).use { out ->
            out.writeByte(VERSION)
            out.writeShort(payload.size)
            for ((key, value) in payload) {
                out.writeUTF(key)
                when (value) {
                    null -> out.writeByte(NULL)
                    is String -> {
                        out.writeByte(STRING)
                        val utf8 = value.toByteArray(Charsets.UTF_8)
                        out.writeInt(utf8.size)
                        out.write(utf8)
                    }
                    is Boolean -> {
                        out.writeByte(BOOL)
                        out.writeBoolean(value)
                    }
                    is Byte, is Short, is Int, is Long -> {
                        out.writeByte(LONG)
                        out.writeLong((value as Number).toLong())
                    }
                    is Float, is Double -> {
                        out.writeByte(DOUBLE)
                        out.writeDouble((value as Number).toDouble())
                    }
                    is ByteArray -> {
                        out.writeByte(BYTES)
                        out.writeInt(value.size)
                        out.write(value)
                    }
                    else -> throw IllegalArgumentException("WatchWire: unsupported value for $key: ${value::class}")
                }
            }
        }
        return bytes.toByteArray()
    }

    /** The dictionary back; null for bytes this version cannot read. */
    fun decode(bytes: ByteArray): Map<String, Any?>? = try {
        DataInputStream(ByteArrayInputStream(bytes)).use { input ->
            if (input.readUnsignedByte() != VERSION) return null
            val count = input.readUnsignedShort()
            val payload = LinkedHashMap<String, Any?>(count)
            repeat(count) {
                val key = input.readUTF()
                payload[key] = when (input.readUnsignedByte()) {
                    NULL -> null
                    STRING -> String(input.readSized(), Charsets.UTF_8)
                    BOOL -> input.readBoolean()
                    LONG -> input.readLong()
                    DOUBLE -> input.readDouble()
                    BYTES -> input.readSized()
                    else -> return null
                }
            }
            if (input.read() != -1) return null
            payload
        }
    } catch (_: IOException) {
        null
    }

    fun encode(message: WatchMessage): ByteArray = encode(message.payload)

    /** A message, or null when the bytes are not one (e.g. the phone's state). */
    fun message(bytes: ByteArray): WatchMessage? = decode(bytes)?.let(WatchMessage::from)

    fun phoneState(bytes: ByteArray): WatchPhoneState? = decode(bytes)?.let(WatchPhoneState::from)

    // MARK: Frames (the recording channel)

    /** Writes one message as a frame: its length (4 bytes, big endian), then its bytes. */
    fun writeFrame(out: OutputStream, message: WatchMessage) {
        val bytes = encode(message)
        val data = DataOutputStream(out)
        data.writeInt(bytes.size)
        data.write(bytes)
        data.flush()
    }

    /**
     * The next frame's message: null at the end of the stream. A frame that is not a message is
     * skipped (a newer watch app); a truncated or oversized frame throws [IOException].
     */
    fun readFrame(input: InputStream): WatchMessage? {
        val data = DataInputStream(input)
        while (true) {
            val first = data.read()
            if (first == -1) return null
            val size = (first shl 24) or (data.readUnsignedByte() shl 16) or (data.readUnsignedByte() shl 8) or data.readUnsignedByte()
            if (size < 0 || size > MAX_FRAME_BYTES) throw IOException("WatchWire: frame of $size bytes")
            val bytes = ByteArray(size)
            data.readFully(bytes)
            message(bytes)?.let { return it }
        }
    }

    private fun DataInputStream.readSized(): ByteArray {
        val size = readInt()
        if (size < 0 || size > MAX_FRAME_BYTES) throw EOFException("WatchWire: field of $size bytes")
        return ByteArray(size).also { readFully(it) }
    }
}
