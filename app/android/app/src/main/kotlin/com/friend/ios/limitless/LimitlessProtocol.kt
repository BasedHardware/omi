package com.friend.ios.limitless

/**
 * Pure packet-level codec for the Limitless pendant's protobuf-over-BLE protocol,
 * ported 1:1 from the Dart connector (`limitless_connection.dart`). No Android
 * dependencies so it is unit-testable against the shared golden fixtures in
 * `app/test/fixtures/limitless_golden/` (which pin the Dart parser's output).
 *
 * Wire shape: every RX notification is a "BLE wrapper" protobuf
 * (1=index, 2=seq, 3=num_frags, 4=payload); payloads can span fragments.
 * In download mode the reassembled payload is a PendantMessage whose field 2 is a
 * StorageBuffer (2=session, 4=seq, 5=index, 6=flash page data); a flash page holds
 * a pendant-clock timestamp (field 1) and 0x1a audio wrappers containing opus frames.
 */
object LimitlessProtocol {

    data class BlePacket(val index: Int, val seq: Int, val numFrags: Int, val payload: ByteArray)

    data class FlashPage(val index: Int?, val session: Int?, val timestampMs: Long, val opusFrames: List<ByteArray>)

    data class StorageState(
        val oldestFlashPage: Int,
        val newestFlashPage: Int,
        val currentStorageSession: Int,
        val freeCapturePages: Int,
        val totalCapturePages: Int,
    )

    // ── Varint ──

    fun encodeVarint(value: Long): ByteArray {
        var v = value
        val out = mutableListOf<Byte>()
        while (v > 0x7f) {
            out.add(((v and 0x7f) or 0x80).toByte())
            v = v ushr 7
        }
        out.add((v and 0x7f).toByte())
        return out.toByteArray()
    }

    /** Returns (value, nextPos). */
    fun decodeVarint(data: ByteArray, startPos: Int): Pair<Long, Int> {
        var result = 0L
        var shift = 0
        var pos = startPos
        while (pos < data.size) {
            val byte = data[pos].toInt() and 0xFF
            pos++
            result = result or ((byte.toLong() and 0x7f) shl shift)
            if (byte and 0x80 == 0) break
            shift += 7
        }
        return result to pos
    }

    // ── Field encoders (mirror _encodeField/_encodeBytesField/_encodeMessage) ──

    private fun encodeField(fieldNum: Int, wireType: Int, value: ByteArray): ByteArray {
        val tag = (fieldNum shl 3) or wireType
        return encodeVarint(tag.toLong()) + value
    }

    private fun encodeBytesField(fieldNum: Int, data: ByteArray): ByteArray =
        encodeField(fieldNum, 2, encodeVarint(data.size.toLong()) + data)

    private fun encodeMessage(fieldNum: Int, msgBytes: ByteArray): ByteArray = encodeBytesField(fieldNum, msgBytes)

    private fun encodeIntField(fieldNum: Int, value: Long): ByteArray = encodeField(fieldNum, 0, encodeVarint(value))

    /** BLE wrapper (1=messageIndex, 2=0, 3=1, 4=payload). Caller owns the index counter. */
    fun encodeBleWrapper(messageIndex: Int, payload: ByteArray): ByteArray {
        return encodeIntField(1, messageIndex.toLong()) +
            encodeIntField(2, 0) +
            encodeIntField(3, 1) +
            encodeBytesField(4, payload)
    }

    /** RequestData trailer (msg 30). Caller owns the requestId counter. */
    fun encodeRequestData(requestId: Long): ByteArray {
        val msg = encodeIntField(1, requestId) + encodeField(2, 0, byteArrayOf(0x00))
        return encodeMessage(30, msg)
    }

    /** msg 6 — pendant clock time-sync. */
    fun encodeSetCurrentTime(messageIndex: Int, requestId: Long, timestampMs: Long): ByteArray =
        encodeBleWrapper(messageIndex, encodeMessage(6, encodeIntField(1, timestampMs)) + encodeRequestData(requestId))

    /** msg 8 — device mode: {batchMode, realTime}. {1,0}=download flash, {0,1}=live stream, {0,0}=record-to-flash. */
    fun encodeDownloadFlashPages(messageIndex: Int, requestId: Long, batchMode: Boolean, realTime: Boolean): ByteArray {
        val msg = encodeField(1, 0, byteArrayOf(if (batchMode) 0x01 else 0x00)) +
            encodeField(2, 0, byteArrayOf(if (realTime) 0x01 else 0x00))
        return encodeBleWrapper(messageIndex, encodeMessage(8, msg) + encodeRequestData(requestId))
    }

    /** msg 7 — ACK processed pages up to [upToIndex]; the pendant frees them. */
    fun encodeAcknowledgeProcessedData(messageIndex: Int, requestId: Long, upToIndex: Int): ByteArray =
        encodeBleWrapper(messageIndex, encodeMessage(7, encodeIntField(1, upToIndex.toLong())) + encodeRequestData(requestId))

    /** msg 21 — GetDeviceStatus (storage state comes back on the RX stream). */
    fun encodeGetDeviceStatus(messageIndex: Int, requestId: Long): ByteArray =
        encodeBleWrapper(messageIndex, encodeMessage(21, ByteArray(0)) + encodeRequestData(requestId))

    // ── Parsers ──

    /** Mirror of `_parseBlePacket`: wrapper fields 1=index, 2=seq, 3=num_frags, 4=payload. */
    fun parseBlePacket(data: ByteArray): BlePacket? {
        try {
            var pos = 0
            var index: Int? = null
            var seq = 0
            var numFrags: Int? = null
            var payload: ByteArray? = null

            while (pos < data.size) {
                val tag = data[pos].toInt() and 0xFF
                val fieldNum = tag shr 3
                val wireType = tag and 0x07
                pos++

                if (wireType == 0) {
                    val (value, next) = decodeVarint(data, pos)
                    pos = next
                    when (fieldNum) {
                        1 -> index = value.toInt()
                        2 -> seq = value.toInt()
                        3 -> numFrags = value.toInt()
                    }
                } else if (wireType == 2) {
                    val (length, next) = decodeVarint(data, pos)
                    pos = next
                    // Dart parity: a past-the-end (or overflowed-negative) length only faults
                    // the packet when it is the payload field; other fields just end the walk.
                    if (length < 0 || pos + length > data.size) {
                        if (fieldNum == 4) return null
                        break
                    }
                    if (fieldNum == 4) payload = data.copyOfRange(pos, pos + length.toInt())
                    pos += length.toInt()
                } else {
                    break
                }
            }

            if (index != null && numFrags != null && payload != null) {
                return BlePacket(index, seq, numFrags, payload)
            }
        } catch (_: Exception) {
        }
        return null
    }

    /** Mirror of `_handlePendantMessage`: extract StorageBuffer fields (field 2) from a reassembled payload. */
    fun parsePendantMessage(payload: ByteArray): List<FlashPage> {
        val pages = mutableListOf<FlashPage>()
        try {
            var pos = 0
            while (pos < payload.size) {
                val tag = payload[pos].toInt() and 0xFF
                val fieldNum = tag shr 3
                val wireType = tag and 0x07
                pos++

                if (wireType == 2) {
                    val (length, next) = decodeVarint(payload, pos)
                    pos = next
                    if (length < 0 || pos + length > payload.size) break
                    if (fieldNum == 2) {
                        parseStorageBuffer(payload.copyOfRange(pos, pos + length.toInt()))?.let { pages.add(it) }
                    }
                    pos += length.toInt()
                } else if (wireType == 0) {
                    val (_, next) = decodeVarint(payload, pos)
                    pos = next
                } else {
                    pos++
                }
            }
        } catch (_: Exception) {
        }
        return pages
    }

    /** Mirror of `_handleStorageBuffer`: 2=session, 4=seq, 5=index, 6=flash page data. */
    private fun parseStorageBuffer(storageData: ByteArray): FlashPage? {
        try {
            var pos = 0
            var session: Int? = null
            var index: Int? = null
            var flashPageData: ByteArray? = null

            while (pos < storageData.size) {
                val tag = storageData[pos].toInt() and 0xFF
                val fieldNum = tag shr 3
                val wireType = tag and 0x07
                pos++

                if (wireType == 0) {
                    val (value, next) = decodeVarint(storageData, pos)
                    pos = next
                    when (fieldNum) {
                        2 -> session = value.toInt()
                        5 -> index = value.toInt()
                    }
                } else if (wireType == 2) {
                    val (length, next) = decodeVarint(storageData, pos)
                    pos = next
                    if (length < 0 || pos + length > storageData.size) break
                    if (fieldNum == 6) flashPageData = storageData.copyOfRange(pos, pos + length.toInt())
                    pos += length.toInt()
                } else {
                    pos++
                }
            }

            val pageData = flashPageData ?: return null
            if (pageData.isEmpty()) return null
            val frames = extractOpusFramesFromFlashPage(pageData)
            // Dart parity: an audio page that yielded zero frames is a parse failure and
            // is never surfaced — ACKing past it would delete audio we failed to extract.
            // Diagnostic pages (no audio subfields) surface with zero frames so the drain
            // can advance past them.
            if (frames.isEmpty() && hasAudioSubfields(pageData)) return null
            return FlashPage(
                index = index,
                session = session,
                timestampMs = parseFlashPageTimestampMs(pageData),
                opusFrames = frames,
            )
        } catch (_: Exception) {
        }
        return null
    }

    /** Field 1 (0x08) at the start of the flash page = pendant-clock timestamp_ms. */
    fun parseFlashPageTimestampMs(flashPageData: ByteArray): Long {
        if (flashPageData.isNotEmpty() && flashPageData[0].toInt() == 0x08) {
            val (value, _) = decodeVarint(flashPageData, 1)
            return value
        }
        return 0L
    }

    /** Mirror of `_extractOpusFramesFromFlashPage`: walk 0x1a audio wrappers, 0x12 audio data, recursive extraction. */
    fun extractOpusFramesFromFlashPage(flashPageData: ByteArray): List<ByteArray> {
        val frames = mutableListOf<ByteArray>()
        try {
            var pos = 0

            if (pos < flashPageData.size && flashPageData[pos].toInt() == 0x08) {
                pos++
                pos = decodeVarint(flashPageData, pos).second
            }
            if (pos < flashPageData.size && flashPageData[pos].toInt() == 0x10) {
                pos++
                pos = decodeVarint(flashPageData, pos).second
            }

            while (pos < flashPageData.size - 2) {
                if (flashPageData[pos].toInt() == 0x1a) {
                    pos++
                    val (wrapperLength, afterLen) = decodeVarint(flashPageData, pos)
                    pos = afterLen
                    if (wrapperLength < 0 || pos + wrapperLength > flashPageData.size) break
                    val wrapperEnd = pos + wrapperLength.toInt()

                    while (pos < wrapperEnd - 1) {
                        val marker = flashPageData[pos].toInt() and 0xFF

                        if (marker == 0x08) {
                            pos++
                            pos = decodeVarint(flashPageData, pos).second
                            continue
                        }
                        if (marker == 0x12) {
                            pos++
                            val (audioLength, afterAudioLen) = decodeVarint(flashPageData, pos)
                            pos = afterAudioLen
                            if (audioLength < 0 || pos + audioLength > flashPageData.size) {
                                pos = wrapperEnd
                                break
                            }
                            val audioEnd = pos + audioLength.toInt()
                            extractOpusRecursive(flashPageData, pos, audioEnd, frames)
                            pos = audioEnd
                            continue
                        }

                        val wireType = marker and 0x07
                        pos++
                        if (wireType == 0) {
                            pos = decodeVarint(flashPageData, pos).second
                        } else if (wireType == 2) {
                            val (length, next) = decodeVarint(flashPageData, pos)
                            if (length < 0 || next + length > wrapperEnd) break
                            pos = (next + length).toInt()
                        }
                    }
                    pos = wrapperEnd
                } else {
                    pos++
                }
            }
        } catch (_: Exception) {
        }
        return frames
    }

    private fun extractOpusRecursive(data: ByteArray, start: Int, end: Int, frames: MutableList<ByteArray>) {
        var pos = start
        while (pos < end - 1) {
            val tag = data[pos].toInt() and 0xFF
            val wireType = tag and 0x07
            pos++

            if (wireType == 2) {
                val (length, next) = decodeVarint(data, pos)
                pos = next
                if (length < 0 || pos + length > end) break
                val len = length.toInt()
                if (len > 0) {
                    val fieldData = data.copyOfRange(pos, pos + len)
                    if (len in 10..200 && isValidOpusToc(fieldData[0])) {
                        frames.add(fieldData)
                    } else if (len > 10) {
                        extractOpusRecursive(data, pos, pos + len, frames)
                    }
                }
                pos += len
            } else if (wireType == 0) {
                pos = decodeVarint(data, pos).second
            } else {
                break
            }
        }
    }

    /** Mirror of `_hasAudioSubfields`: any 0x12 subfield inside a 0x1a wrapper.
     *  Anomalies return TRUE (treated as audio) so a failed extraction is never ACKed away. */
    fun hasAudioSubfields(flashPageData: ByteArray): Boolean {
        try {
            var pos = 0
            if (pos < flashPageData.size && flashPageData[pos].toInt() == 0x08) {
                pos++
                pos = decodeVarint(flashPageData, pos).second
            }
            if (pos < flashPageData.size && flashPageData[pos].toInt() == 0x10) {
                pos++
                pos = decodeVarint(flashPageData, pos).second
            }

            while (pos < flashPageData.size - 2) {
                if (flashPageData[pos].toInt() == 0x1a) {
                    pos++
                    val (wrapperLength, afterLen) = decodeVarint(flashPageData, pos)
                    pos = afterLen
                    if (wrapperLength < 0 || pos + wrapperLength > flashPageData.size) break
                    val wrapperEnd = pos + wrapperLength.toInt()

                    while (pos < wrapperEnd - 1) {
                        val marker = flashPageData[pos].toInt() and 0xFF
                        if (marker == 0x12) return true
                        val wireType = marker and 0x07
                        pos++
                        when (wireType) {
                            0 -> pos = decodeVarint(flashPageData, pos).second
                            2 -> {
                                val (length, next) = decodeVarint(flashPageData, pos)
                                if (length < 0 || next + length > wrapperEnd) {
                                    pos = wrapperEnd
                                } else {
                                    pos = (next + length).toInt()
                                }
                            }
                            1 -> pos += 8
                            5 -> pos += 4
                            else -> return true
                        }
                    }
                    pos = wrapperEnd
                } else {
                    val wireType = flashPageData[pos].toInt() and 0x07
                    pos++
                    when (wireType) {
                        0 -> pos = decodeVarint(flashPageData, pos).second
                        2 -> {
                            val (length, next) = decodeVarint(flashPageData, pos)
                            if (length < 0 || next + length > flashPageData.size) return false
                            pos = (next + length).toInt()
                        }
                        1 -> pos += 8
                        5 -> pos += 4
                        else -> return true
                    }
                }
            }
        } catch (_: Exception) {
            return true
        }
        return false
    }

    fun isValidOpusToc(byte: Byte): Boolean {
        val b = byte.toInt() and 0xFF
        return b == 0xb8 || b == 0x78 || b == 0xf8 || b == 0xb0 || b == 0x70 || b == 0xf0
    }

    /** Mirror of `_tryParseDeviceStatus` + `_parseStorageStateFromDeviceStatus` (0x22 → 0x2a → 0x2a struct). */
    fun parseDeviceStatus(data: ByteArray): StorageState? {
        try {
            if (data.size < 20) return null

            var pos = 0
            while (pos < data.size - 5) {
                if (data[pos].toInt() == 0x22) {
                    pos++
                    if (pos >= data.size) return null

                    val (payloadLength, next) = decodeVarint(data, pos)
                    pos = next
                    if (payloadLength < 10 || payloadLength > data.size - pos) return null

                    val payloadEnd = pos + payloadLength.toInt()
                    var innerPos = pos
                    while (innerPos < payloadEnd - 5) {
                        if (data[innerPos].toInt() == 0x2a) {
                            innerPos++
                            if (innerPos >= data.size) return null

                            val (statusLength, afterLen) = decodeVarint(data, innerPos)
                            innerPos = afterLen
                            if (statusLength < 5 || statusLength > 500 || innerPos + statusLength > data.size) return null

                            return parseStorageState(data, innerPos, innerPos + statusLength.toInt())
                        }
                        innerPos++
                    }
                    return null
                }
                pos++
            }
        } catch (_: Exception) {
        }
        return null
    }

    private fun parseStorageState(data: ByteArray, start: Int, end: Int): StorageState? {
        try {
            if (start < 0 || end > data.size || start >= end) return null

            var pos = start
            while (pos < end - 1 && pos < data.size) {
                if (data[pos].toInt() == 0x2a) {
                    pos++
                    if (pos >= data.size) break

                    val (storageLength, next) = decodeVarint(data, pos)
                    pos = next
                    if (storageLength < 0 || storageLength > 200 || pos + storageLength > data.size) break

                    val storageEnd = pos + storageLength.toInt()
                    var oldest = 0
                    var newest = 0
                    var session = 0
                    var free = 0
                    var total = 0
                    var any = false

                    while (pos < storageEnd - 1 && pos < data.size) {
                        val marker = data[pos].toInt() and 0xFF
                        pos++
                        if (pos >= data.size) break

                        if (marker == 0x08 || marker == 0x10 || marker == 0x18 || marker == 0x20 || marker == 0x28) {
                            val (value, afterValue) = decodeVarint(data, pos)
                            pos = afterValue
                            any = true
                            when (marker) {
                                0x08 -> oldest = value.toInt()
                                0x10 -> newest = value.toInt()
                                0x18 -> session = value.toInt()
                                0x20 -> free = value.toInt()
                                0x28 -> total = value.toInt()
                            }
                        }
                    }

                    return if (any) StorageState(oldest, newest, session, free, total) else null
                }
                pos++
            }
        } catch (_: Exception) {
        }
        return null
    }
}
