import Foundation

/// Pure packet-level codec for the Limitless pendant's protobuf-over-BLE protocol,
/// ported 1:1 from the Android `LimitlessProtocol.kt` (itself ported from the Dart
/// connector `limitless_connection.dart`). Foundation only — no other dependencies.
///
/// Wire shape: every RX notification is a "BLE wrapper" protobuf
/// (1=index, 2=seq, 3=num_frags, 4=payload); payloads can span fragments.
/// In download mode the reassembled payload is a PendantMessage whose field 2 is a
/// StorageBuffer (2=session, 4=seq, 5=index, 6=flash page data); a flash page holds
/// a pendant-clock timestamp (field 1) and 0x1a audio wrappers containing opus frames.
///
/// All `Data` inputs must be zero-based (fresh `Data` / `subdata(in:)` results).
enum LimitlessProtocol {

    struct BlePacket {
        let index: Int
        let seq: Int
        let numFrags: Int
        let payload: Data
    }

    struct FlashPage {
        let index: Int?
        let session: Int?
        let timestampMs: Int64
        let opusFrames: [Data]
    }

    struct StorageState {
        let oldestFlashPage: Int
        let newestFlashPage: Int
        let currentStorageSession: Int
        let freeCapturePages: Int
        let totalCapturePages: Int
    }

    // MARK: - Varint

    static func encodeVarint(_ value: Int64) -> Data {
        var v = value
        var out = Data()
        while v > 0x7f {
            out.append(UInt8((v & 0x7f) | 0x80))
            v >>= 7
        }
        out.append(UInt8(v & 0x7f))
        return out
    }

    /// Returns (value, nextPos).
    static func decodeVarint(_ data: Data, _ startPos: Int) -> (Int64, Int) {
        var result: Int64 = 0
        var shift: Int64 = 0
        var pos = startPos
        while pos >= 0, pos < data.count {
            let byte = Int(data[pos])
            pos += 1
            result |= (Int64(byte) & 0x7f) &<< shift
            if byte & 0x80 == 0 { break }
            shift += 7
        }
        return (result, pos)
    }

    // MARK: - Field encoders

    private static func encodeField(_ fieldNum: Int, _ wireType: Int, _ value: Data) -> Data {
        let tag = (fieldNum << 3) | wireType
        return encodeVarint(Int64(tag)) + value
    }

    private static func encodeBytesField(_ fieldNum: Int, _ data: Data) -> Data {
        return encodeField(fieldNum, 2, encodeVarint(Int64(data.count)) + data)
    }

    private static func encodeMessage(_ fieldNum: Int, _ msgBytes: Data) -> Data {
        return encodeBytesField(fieldNum, msgBytes)
    }

    private static func encodeIntField(_ fieldNum: Int, _ value: Int64) -> Data {
        return encodeField(fieldNum, 0, encodeVarint(value))
    }

    /// BLE wrapper (1=messageIndex, 2=0, 3=1, 4=payload). Caller owns the index counter.
    static func encodeBleWrapper(messageIndex: Int, payload: Data) -> Data {
        return encodeIntField(1, Int64(messageIndex))
            + encodeIntField(2, 0)
            + encodeIntField(3, 1)
            + encodeBytesField(4, payload)
    }

    /// RequestData trailer (msg 30). Caller owns the requestId counter.
    static func encodeRequestData(requestId: Int64) -> Data {
        let msg = encodeIntField(1, requestId) + encodeField(2, 0, Data([0x00]))
        return encodeMessage(30, msg)
    }

    /// msg 6 — pendant clock time-sync.
    static func encodeSetCurrentTime(messageIndex: Int, requestId: Int64, timestampMs: Int64) -> Data {
        return encodeBleWrapper(
            messageIndex: messageIndex,
            payload: encodeMessage(6, encodeIntField(1, timestampMs)) + encodeRequestData(requestId: requestId)
        )
    }

    /// msg 8 — device mode: {batchMode, realTime}. {1,0}=download flash, {0,1}=live stream, {0,0}=record-to-flash.
    static func encodeDownloadFlashPages(messageIndex: Int, requestId: Int64, batchMode: Bool, realTime: Bool) -> Data {
        let msg = encodeField(1, 0, Data([batchMode ? 0x01 : 0x00]))
            + encodeField(2, 0, Data([realTime ? 0x01 : 0x00]))
        return encodeBleWrapper(
            messageIndex: messageIndex,
            payload: encodeMessage(8, msg) + encodeRequestData(requestId: requestId)
        )
    }

    /// msg 7 — ACK processed pages up to `upToIndex`; the pendant frees them.
    static func encodeAcknowledgeProcessedData(messageIndex: Int, requestId: Int64, upToIndex: Int) -> Data {
        return encodeBleWrapper(
            messageIndex: messageIndex,
            payload: encodeMessage(7, encodeIntField(1, Int64(upToIndex))) + encodeRequestData(requestId: requestId)
        )
    }

    /// msg 21 — GetDeviceStatus (storage state comes back on the RX stream).
    static func encodeGetDeviceStatus(messageIndex: Int, requestId: Int64) -> Data {
        return encodeBleWrapper(
            messageIndex: messageIndex,
            payload: encodeMessage(21, Data()) + encodeRequestData(requestId: requestId)
        )
    }

    // MARK: - Parsers

    /// Wrapper fields 1=index, 2=seq, 3=num_frags, 4=payload.
    static func parseBlePacket(_ data: Data) -> BlePacket? {
        var pos = 0
        var index: Int?
        var seq = 0
        var numFrags: Int?
        var payload: Data?

        while pos < data.count {
            let tag = Int(data[pos])
            let fieldNum = tag >> 3
            let wireType = tag & 0x07
            pos += 1

            if wireType == 0 {
                let (value, next) = decodeVarint(data, pos)
                pos = next
                switch fieldNum {
                case 1: index = Int(truncatingIfNeeded: value)
                case 2: seq = Int(truncatingIfNeeded: value)
                case 3: numFrags = Int(truncatingIfNeeded: value)
                default: break
                }
            } else if wireType == 2 {
                let (length, next) = decodeVarint(data, pos)
                pos = next
                // Dart parity: a past-the-end length only faults the packet when it is
                // the payload field; other fields just end the walk, keeping what parsed.
                guard length >= 0, length <= Int64(data.count - pos) else {
                    if fieldNum == 4 { return nil }
                    break
                }
                let len = Int(length)
                if fieldNum == 4 { payload = data.subdata(in: pos ..< pos + len) }
                pos += len
            } else {
                break
            }
        }

        if let index = index, let numFrags = numFrags, let payload = payload {
            return BlePacket(index: index, seq: seq, numFrags: numFrags, payload: payload)
        }
        return nil
    }

    /// Extract StorageBuffer fields (field 2) from a reassembled payload.
    static func parsePendantMessage(_ payload: Data) -> [FlashPage] {
        var pages: [FlashPage] = []
        var pos = 0
        while pos < payload.count {
            let tag = Int(payload[pos])
            let fieldNum = tag >> 3
            let wireType = tag & 0x07
            pos += 1

            if wireType == 2 {
                let (length, next) = decodeVarint(payload, pos)
                pos = next
                guard length >= 0, length <= Int64(payload.count - pos) else { break }
                let len = Int(length)
                if fieldNum == 2 {
                    if let page = parseStorageBuffer(payload.subdata(in: pos ..< pos + len)) {
                        pages.append(page)
                    }
                }
                pos += len
            } else if wireType == 0 {
                pos = decodeVarint(payload, pos).1
            } else {
                pos += 1
            }
        }
        return pages
    }

    /// StorageBuffer: 2=session, 4=seq, 5=index, 6=flash page data.
    private static func parseStorageBuffer(_ storageData: Data) -> FlashPage? {
        var pos = 0
        var session: Int?
        var index: Int?
        var flashPageData: Data?

        while pos < storageData.count {
            let tag = Int(storageData[pos])
            let fieldNum = tag >> 3
            let wireType = tag & 0x07
            pos += 1

            if wireType == 0 {
                let (value, next) = decodeVarint(storageData, pos)
                pos = next
                switch fieldNum {
                case 2: session = Int(truncatingIfNeeded: value)
                case 5: index = Int(truncatingIfNeeded: value)
                default: break
                }
            } else if wireType == 2 {
                let (length, next) = decodeVarint(storageData, pos)
                pos = next
                guard length >= 0, length <= Int64(storageData.count - pos) else { break }
                let len = Int(length)
                if fieldNum == 6 { flashPageData = storageData.subdata(in: pos ..< pos + len) }
                pos += len
            } else {
                pos += 1
            }
        }

        guard let pageData = flashPageData, !pageData.isEmpty else { return nil }
        let frames = extractOpusFramesFromFlashPage(pageData)
        // Dart parity: an audio page that yielded zero frames is a parse failure and
        // is never surfaced — ACKing past it would delete audio we failed to extract.
        // Diagnostic pages (no audio subfields) surface with zero frames so the drain
        // can advance past them.
        if frames.isEmpty, hasAudioSubfields(pageData) { return nil }
        return FlashPage(
            index: index,
            session: session,
            timestampMs: parseFlashPageTimestampMs(pageData),
            opusFrames: frames
        )
    }

    /// Mirror of `_hasAudioSubfields`: any 0x12 subfield inside a 0x1a wrapper.
    /// Anomalies return TRUE (treated as audio) so a failed extraction is never ACKed away.
    static func hasAudioSubfields(_ flashPageData: Data) -> Bool {
        var pos = 0
        if pos < flashPageData.count, flashPageData[pos] == 0x08 {
            pos += 1
            pos = decodeVarint(flashPageData, pos).1
        }
        if pos < flashPageData.count, flashPageData[pos] == 0x10 {
            pos += 1
            pos = decodeVarint(flashPageData, pos).1
        }

        while pos >= 0, pos < flashPageData.count - 2 {
            if flashPageData[pos] == 0x1a {
                pos += 1
                let (wrapperLength, afterLen) = decodeVarint(flashPageData, pos)
                pos = afterLen
                guard wrapperLength >= 0, wrapperLength <= Int64(flashPageData.count - pos) else { break }
                let wrapperEnd = pos + Int(wrapperLength)

                while pos >= 0, pos < wrapperEnd - 1 {
                    let marker = Int(flashPageData[pos])
                    if marker == 0x12 { return true }
                    let wireType = marker & 0x07
                    pos += 1
                    switch wireType {
                    case 0:
                        pos = decodeVarint(flashPageData, pos).1
                    case 2:
                        let (length, next) = decodeVarint(flashPageData, pos)
                        if length < 0 || Int64(next) + length > Int64(wrapperEnd) {
                            pos = wrapperEnd
                        } else {
                            pos = next + Int(length)
                        }
                    case 1:
                        pos += 8
                    case 5:
                        pos += 4
                    default:
                        return true
                    }
                }
                pos = wrapperEnd
            } else {
                let wireType = Int(flashPageData[pos]) & 0x07
                pos += 1
                switch wireType {
                case 0:
                    pos = decodeVarint(flashPageData, pos).1
                case 2:
                    let (length, next) = decodeVarint(flashPageData, pos)
                    if length < 0 || Int64(next) + length > Int64(flashPageData.count) { return false }
                    pos = next + Int(length)
                case 1:
                    pos += 8
                case 5:
                    pos += 4
                default:
                    return true
                }
            }
        }
        return false
    }

    /// Field 1 (0x08) at the start of the flash page = pendant-clock timestamp_ms.
    static func parseFlashPageTimestampMs(_ flashPageData: Data) -> Int64 {
        if !flashPageData.isEmpty, flashPageData[0] == 0x08 {
            return decodeVarint(flashPageData, 1).0
        }
        return 0
    }

    /// Walk 0x1a audio wrappers, 0x12 audio data, recursive extraction.
    static func extractOpusFramesFromFlashPage(_ flashPageData: Data) -> [Data] {
        var frames: [Data] = []
        var pos = 0

        if pos < flashPageData.count, flashPageData[pos] == 0x08 {
            pos += 1
            pos = decodeVarint(flashPageData, pos).1
        }
        if pos < flashPageData.count, flashPageData[pos] == 0x10 {
            pos += 1
            pos = decodeVarint(flashPageData, pos).1
        }

        while pos >= 0, pos < flashPageData.count - 2 {
            if flashPageData[pos] == 0x1a {
                pos += 1
                let (wrapperLength, afterLen) = decodeVarint(flashPageData, pos)
                pos = afterLen
                guard wrapperLength >= 0, wrapperLength <= Int64(flashPageData.count - pos) else { break }
                let wrapperEnd = pos + Int(wrapperLength)

                while pos >= 0, pos < wrapperEnd - 1 {
                    let marker = Int(flashPageData[pos])

                    if marker == 0x08 {
                        pos += 1
                        pos = decodeVarint(flashPageData, pos).1
                        continue
                    }
                    if marker == 0x12 {
                        pos += 1
                        let (audioLength, afterAudioLen) = decodeVarint(flashPageData, pos)
                        pos = afterAudioLen
                        guard audioLength >= 0, audioLength <= Int64(flashPageData.count - pos) else {
                            pos = wrapperEnd
                            break
                        }
                        let audioEnd = pos + Int(audioLength)
                        extractOpusRecursive(flashPageData, pos, audioEnd, &frames)
                        pos = audioEnd
                        continue
                    }

                    let wireType = marker & 0x07
                    pos += 1
                    if wireType == 0 {
                        pos = decodeVarint(flashPageData, pos).1
                    } else if wireType == 2 {
                        let (length, next) = decodeVarint(flashPageData, pos)
                        guard length >= 0, length <= Int64(flashPageData.count) else { break }
                        pos = next + Int(length)
                    }
                }
                pos = wrapperEnd
            } else {
                pos += 1
            }
        }
        return frames
    }

    private static func extractOpusRecursive(_ data: Data, _ start: Int, _ end: Int, _ frames: inout [Data]) {
        var pos = start
        while pos >= 0, pos < end - 1, pos < data.count {
            let tag = Int(data[pos])
            let wireType = tag & 0x07
            pos += 1

            if wireType == 2 {
                let (length, next) = decodeVarint(data, pos)
                pos = next
                guard length >= 0, length <= Int64(data.count) else { return }
                let len = Int(length)
                if len > 0, pos + len <= end {
                    let fieldData = data.subdata(in: pos ..< pos + len)
                    if len >= 10, len <= 200, isValidOpusToc(fieldData[0]) {
                        frames.append(fieldData)
                    } else if len > 10 {
                        extractOpusRecursive(data, pos, pos + len, &frames)
                    }
                }
                pos += len
            } else if wireType == 0 {
                pos = decodeVarint(data, pos).1
            } else {
                break
            }
        }
    }

    static func isValidOpusToc(_ byte: UInt8) -> Bool {
        return byte == 0xb8 || byte == 0x78 || byte == 0xf8 || byte == 0xb0 || byte == 0x70 || byte == 0xf0
    }

    /// DeviceStatus (0x22 → 0x2a → 0x2a struct).
    static func parseDeviceStatus(_ data: Data) -> StorageState? {
        guard data.count >= 20 else { return nil }

        var pos = 0
        while pos < data.count - 5 {
            if data[pos] == 0x22 {
                pos += 1
                if pos >= data.count { return nil }

                let (payloadLength, next) = decodeVarint(data, pos)
                pos = next
                if payloadLength < 10 || payloadLength > Int64(data.count - pos) { return nil }

                let payloadEnd = pos + Int(payloadLength)
                var innerPos = pos
                while innerPos < payloadEnd - 5 {
                    if data[innerPos] == 0x2a {
                        innerPos += 1
                        if innerPos >= data.count { return nil }

                        let (statusLength, afterLen) = decodeVarint(data, innerPos)
                        innerPos = afterLen
                        if statusLength < 5 || statusLength > 500 || statusLength > Int64(data.count - innerPos) {
                            return nil
                        }

                        return parseStorageState(data, innerPos, innerPos + Int(statusLength))
                    }
                    innerPos += 1
                }
                return nil
            }
            pos += 1
        }
        return nil
    }

    private static func parseStorageState(_ data: Data, _ start: Int, _ end: Int) -> StorageState? {
        guard start >= 0, end <= data.count, start < end else { return nil }

        var pos = start
        while pos < end - 1, pos < data.count {
            if data[pos] == 0x2a {
                pos += 1
                if pos >= data.count { break }

                let (storageLength, next) = decodeVarint(data, pos)
                pos = next
                if storageLength < 0 || storageLength > 200 || storageLength > Int64(data.count - pos) { break }

                let storageEnd = pos + Int(storageLength)
                var oldest = 0
                var newest = 0
                var session = 0
                var free = 0
                var total = 0
                var any = false

                while pos < storageEnd - 1, pos < data.count {
                    let marker = Int(data[pos])
                    pos += 1
                    if pos >= data.count { break }

                    if marker == 0x08 || marker == 0x10 || marker == 0x18 || marker == 0x20 || marker == 0x28 {
                        let (value, afterValue) = decodeVarint(data, pos)
                        pos = afterValue
                        any = true
                        switch marker {
                        case 0x08: oldest = Int(truncatingIfNeeded: value)
                        case 0x10: newest = Int(truncatingIfNeeded: value)
                        case 0x18: session = Int(truncatingIfNeeded: value)
                        case 0x20: free = Int(truncatingIfNeeded: value)
                        case 0x28: total = Int(truncatingIfNeeded: value)
                        default: break
                        }
                    }
                }

                if !any { return nil }
                return StorageState(
                    oldestFlashPage: oldest,
                    newestFlashPage: newest,
                    currentStorageSession: session,
                    freeCapturePages: free,
                    totalCapturePages: total
                )
            }
            pos += 1
        }
        return nil
    }
}
