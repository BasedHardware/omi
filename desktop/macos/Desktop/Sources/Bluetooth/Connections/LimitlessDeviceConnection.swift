import Combine
import CoreBluetooth
import Foundation
import os.log

/// Device connection implementation for Limitless Pendant devices
/// Uses protobuf-like message encoding with fragment reassembly
/// Supports both batch mode (stored recordings) and real-time streaming
/// Ported from: omi/app/lib/services/devices/limitless_connection.dart
final class LimitlessDeviceConnection: BaseDeviceConnection {

    // MARK: - Constants

    private enum ButtonEvent: Int {
        case notPressed = 0
        case shortPress = 1
        case longPress = 2
        case doublePress = 3
    }

    // MARK: - Private Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "LimitlessDeviceConnection")

    private var messageIndex = 0
    private var requestId = 0

    private var audioStreamSubject = PassthroughSubject<Data, Error>()
    private var flashPageSubject = PassthroughSubject<[String: Any], Never>()
    private var buttonStreamSubject = PassthroughSubject<[UInt8], Never>()

    private var rxSubscription: Task<Void, Never>?
    private var rawDataBuffer = [UInt8]()

    /// Fragment reassembly: index -> {seq -> payload}
    private var fragmentBuffer: [Int: [Int: [UInt8]]] = [:]

    /// Completed flash pages from batch mode
    private var completedFlashPages: [[String: Any]] = []

    private var isInitialized = false
    private var isBatchMode = false

    private var highestReceivedIndex = -1
    private var lastAcknowledgedIndex = -1

    private var firstFlashPageTimestampMs: Int64?
    private var storageState: [String: Int]?
    private var storageStateCompletion: CheckedContinuation<[String: Int]?, Never>?
    private var lastLedBrightness: Int?

    // MARK: - Initialization

    override init(device: BtDevice, transport: DeviceTransport) {
        super.init(device: device, transport: transport)
    }

    // MARK: - Connection

    override func connect() async throws {
        try await super.connect()
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        startRxListener()

        try? await Task.sleep(nanoseconds: 1_000_000_000)

        try await initialize()
    }

    override func disconnect() async {
        rxSubscription?.cancel()
        rxSubscription = nil
        audioStreamSubject.send(completion: .finished)
        isBatchMode = false
        await super.disconnect()
    }

    override func unpair() async {
        await unpairWithoutReset()
        await super.unpair()
    }

    // MARK: - Initialization

    private func initialize() async throws {
        // Command 1: Time sync
        let timeSyncCmd = encodeSetCurrentTime(Date().millisecondsSince1970)
        try await transport.writeCharacteristic(
            data: Data(timeSyncCmd),
            serviceUUID: DeviceUUIDs.Limitless.service,
            characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
            withResponse: true
        )
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        // Command 2: Enable data streaming
        let dataStreamCmd = encodeEnableDataStream()
        try await transport.writeCharacteristic(
            data: Data(dataStreamCmd),
            serviceUUID: DeviceUUIDs.Limitless.service,
            characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
            withResponse: true
        )
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        isInitialized = true
    }

    // MARK: - RX Listener

    private func startRxListener() {
        let stream = transport.getCharacteristicStream(
            serviceUUID: DeviceUUIDs.Limitless.service,
            characteristicUUID: DeviceUUIDs.Limitless.rxCharacteristic
        )

        rxSubscription = Task { [weak self] in
            do {
                for try await data in stream {
                    self?.handleNotification(Array(data))
                }
            } catch {
                self?.logger.debug("RX stream ended")
            }
        }
    }

    private func handleNotification(_ data: [UInt8]) {
        guard !data.isEmpty else { return }

        tryParseButtonStatus(data)
        tryParseDeviceStatus(data)

        // Parse BLE packet for fragmentation
        guard let packet = parseBlePacket(data) else {
            if isBatchMode {
                logger.debug("Batch mode - packet parse failed, data=\(data.count)b")
            }
            rawDataBuffer.append(contentsOf: data)
            return
        }

        let index = packet.index
        let seq = packet.seq
        let numFrags = packet.numFrags
        let payload = packet.payload

        // Track highest received index for acknowledgment
        if index > highestReceivedIndex {
            highestReceivedIndex = index
        }

        // Fragment reassembly
        if fragmentBuffer[index] == nil {
            fragmentBuffer[index] = [:]
        }
        fragmentBuffer[index]![seq] = payload

        if fragmentBuffer[index]!.count == numFrags {
            var completePayload = [UInt8]()
            for i in 0..<numFrags {
                if let fragment = fragmentBuffer[index]![i] {
                    completePayload.append(contentsOf: fragment)
                }
            }
            fragmentBuffer.removeValue(forKey: index)

            if isBatchMode {
                handlePendantMessage(completePayload)
            } else {
                handleRealTimePayload(completePayload)
            }
        }
    }

    /// Handle reassembled payload in real-time mode
    private func handleRealTimePayload(_ payload: [UInt8]) {
        let frames = extractOpusFramesFromFlashPage(payload)

        if !frames.isEmpty {
            for frame in frames {
                audioStreamSubject.send(Data(frame))
            }
        } else {
            let (extractedFrames, _) = extractOpusFrames(payload)
            for frame in extractedFrames {
                audioStreamSubject.send(Data(frame))
            }
        }
    }

    private func handlePendantMessage(_ payload: [UInt8]) {
        var pos = 0

        while pos < payload.count {
            let tag = payload[pos]
            let fieldNum = Int(tag >> 3)
            let wireType = Int(tag & 0x07)
            pos += 1

            if wireType == 2 {
                // Length-delimited field
                let (length, newPos) = decodeVarint(payload, pos)
                pos = newPos

                let fieldData = Array(payload[pos..<min(pos + length, payload.count)])
                pos += length

                if fieldNum == 2 {
                    handleStorageBuffer(fieldData)
                }
            } else if wireType == 0 {
                let (_, newPos) = decodeVarint(payload, pos)
                pos = newPos
            } else {
                pos += 1
            }
        }
    }

    private func handleStorageBuffer(_ storageData: [UInt8]) {
        var pos = 0
        var session: Int?
        var seq: Int?
        var index: Int?
        var flashPageData: [UInt8]?

        while pos < storageData.count {
            let tag = storageData[pos]
            let fieldNum = Int(tag >> 3)
            let wireType = Int(tag & 0x07)
            pos += 1

            if wireType == 0 {
                let (value, newPos) = decodeVarint(storageData, pos)
                pos = newPos

                switch fieldNum {
                case 2: session = value
                case 4: seq = value
                case 5: index = value
                default: break
                }
            } else if wireType == 2 {
                let (length, newPos) = decodeVarint(storageData, pos)
                pos = newPos

                if fieldNum == 6 {
                    flashPageData = Array(storageData[pos..<min(pos + length, storageData.count)])
                }
                pos += length
            } else {
                pos += 1
            }
        }

        if let pageData = flashPageData, !pageData.isEmpty {
            let pageInfo = parseFlashPageInfo(pageData)
            let opusFrames = extractOpusFramesFromFlashPage(pageData)

            if !opusFrames.isEmpty {
                let flashPage: [String: Any] = [
                    "opus_frames": opusFrames,
                    "timestamp_ms": pageInfo["timestamp_ms"] ?? Date().millisecondsSince1970,
                    "session": session as Any,
                    "seq": seq as Any,
                    "index": index as Any,
                    "did_start_session": pageInfo["did_start_session"] ?? false,
                    "did_stop_session": pageInfo["did_stop_session"] ?? false,
                    "did_start_recording": pageInfo["did_start_recording"] ?? false,
                    "did_stop_recording": pageInfo["did_stop_recording"] ?? false
                ]

                completedFlashPages.append(flashPage)

                if firstFlashPageTimestampMs == nil {
                    if let timestamp = pageInfo["timestamp_ms"] as? Int64, timestamp > 1577836800000 {
                        firstFlashPageTimestampMs = timestamp
                    }
                }

                flashPageSubject.send(flashPage)
            }
        }
    }

    // MARK: - Flash Page Parsing

    private func parseFlashPageInfo(_ flashPageData: [UInt8]) -> [String: Any] {
        var result: [String: Any] = [
            "timestamp_ms": Int64(0),
            "did_start_session": false,
            "did_stop_session": false,
            "did_start_recording": false,
            "did_stop_recording": false
        ]

        var pos = 0

        // Field 1 (0x08) = timestamp_ms
        if pos < flashPageData.count && flashPageData[pos] == 0x08 {
            pos += 1
            let (timestamp, newPos) = decodeVarint(flashPageData, pos)
            result["timestamp_ms"] = Int64(timestamp)
            pos = newPos
        }

        while pos < flashPageData.count - 2 {
            if flashPageData[pos] == 0x1a {
                pos += 1
                let (chunkLength, chunkPos) = decodeVarint(flashPageData, pos)
                pos = chunkPos
                let chunkEnd = pos + chunkLength

                while pos < chunkEnd - 1 {
                    let marker = flashPageData[pos]

                    // Storage status (0x62)
                    if marker == 0x62 {
                        pos += 1
                        let (statusLength, statusPos) = decodeVarint(flashPageData, pos)
                        pos = statusPos
                        let statusEnd = pos + statusLength

                        while pos < statusEnd {
                            let statusMarker = flashPageData[pos]
                            pos += 1

                            if statusMarker == 0x08 && pos < statusEnd {
                                result["did_start_session"] = flashPageData[pos] != 0
                                pos += 1
                            } else if statusMarker == 0x10 && pos < statusEnd {
                                result["did_stop_session"] = flashPageData[pos] != 0
                                pos += 1
                            }
                        }
                        continue
                    }

                    // Audio data (0x12)
                    if marker == 0x12 {
                        pos += 1
                        let (audioLength, audioPos) = decodeVarint(flashPageData, pos)
                        pos = audioPos
                        let audioEnd = pos + audioLength

                        while pos < audioEnd - 1 {
                            let audioMarker = flashPageData[pos]
                            pos += 1

                            if audioMarker == 0x40 && pos < audioEnd {
                                result["did_start_recording"] = flashPageData[pos] != 0
                                pos += 1
                            } else if audioMarker == 0x48 && pos < audioEnd {
                                result["did_stop_recording"] = flashPageData[pos] != 0
                                pos += 1
                            }
                        }
                        pos = audioEnd
                        continue
                    }

                    pos += 1
                }
                pos = chunkEnd
            } else {
                pos += 1
            }
        }

        return result
    }

    // MARK: - Opus Extraction

    private func extractOpusFramesFromFlashPage(_ flashPageData: [UInt8]) -> [[UInt8]] {
        var frames = [[UInt8]]()
        var pos = 0

        // Skip timestamp (0x08) if present
        if pos < flashPageData.count && flashPageData[pos] == 0x08 {
            pos += 1
            let (_, newPos) = decodeVarint(flashPageData, pos)
            pos = newPos
        }

        // Skip 0x10 if present
        if pos < flashPageData.count && flashPageData[pos] == 0x10 {
            pos += 1
            let (_, newPos) = decodeVarint(flashPageData, pos)
            pos = newPos
        }

        // Process audio wrappers (0x1a)
        while pos < flashPageData.count - 2 {
            if flashPageData[pos] == 0x1a {
                pos += 1
                let (wrapperLength, wrapperPos) = decodeVarint(flashPageData, pos)
                pos = wrapperPos
                let wrapperEnd = pos + wrapperLength

                if wrapperEnd > flashPageData.count { break }

                while pos < wrapperEnd - 1 {
                    let marker = flashPageData[pos]

                    // Offset (0x08) - skip
                    if marker == 0x08 {
                        pos += 1
                        let (_, newPos) = decodeVarint(flashPageData, pos)
                        pos = newPos
                        continue
                    }

                    // Audio data (0x12)
                    if marker == 0x12 {
                        pos += 1
                        let (audioLength, audioPos) = decodeVarint(flashPageData, pos)
                        pos = audioPos
                        let audioEnd = pos + audioLength

                        if audioEnd > flashPageData.count {
                            pos = wrapperEnd
                            break
                        }

                        extractOpusRecursive(flashPageData, start: pos, end: audioEnd, frames: &frames)
                        pos = audioEnd
                        continue
                    }

                    // Skip other wire types
                    let wireType = marker & 0x07
                    pos += 1
                    if wireType == 0 {
                        let (_, newPos) = decodeVarint(flashPageData, pos)
                        pos = newPos
                    } else if wireType == 2 {
                        let (length, newPos) = decodeVarint(flashPageData, pos)
                        pos = newPos + length
                    }
                }
                pos = wrapperEnd
            } else {
                pos += 1
            }
        }

        return frames
    }

    private func extractOpusRecursive(_ data: [UInt8], start: Int, end: Int, frames: inout [[UInt8]]) {
        var pos = start

        while pos < end - 1 {
            let tag = data[pos]
            let wireType = Int(tag & 0x07)
            pos += 1

            if wireType == 2 {
                let (length, newPos) = decodeVarint(data, pos)
                pos = newPos

                if length > 0 && pos + length <= end {
                    let fieldData = Array(data[pos..<(pos + length)])

                    if length >= 10 && length <= 200 && !fieldData.isEmpty && isValidOpusToc(fieldData[0]) {
                        frames.append(fieldData)
                    } else if length > 10 {
                        extractOpusRecursive(data, start: pos, end: pos + length, frames: &frames)
                    }
                }
                pos += length
            } else if wireType == 0 {
                let (_, newPos) = decodeVarint(data, pos)
                pos = newPos
            } else {
                break
            }
        }
    }

    private func extractOpusFrames(_ data: [UInt8]) -> ([[UInt8]], Int) {
        var frames = [[UInt8]]()
        var pos = 0
        var lastCompleteFrameEnd = 0

        while pos < data.count - 3 {
            if data[pos] == 0x22 {
                let markerPos = pos
                pos += 1

                if pos >= data.count { break }

                let (length, lengthEndPos) = decodeVarint(data, pos)

                if length >= 10 && length <= 200 {
                    let frameStartPos = lengthEndPos
                    let frameEndPos = frameStartPos + length

                    if frameEndPos <= data.count {
                        let frame = Array(data[frameStartPos..<frameEndPos])

                        if !frame.isEmpty && isValidOpusToc(frame[0]) {
                            frames.append(frame)
                            lastCompleteFrameEnd = frameEndPos
                            pos = frameEndPos
                            continue
                        } else {
                            pos = markerPos + 1
                            continue
                        }
                    } else {
                        break
                    }
                } else {
                    pos = markerPos + 1
                    continue
                }
            }
            pos += 1
        }

        return (frames, lastCompleteFrameEnd)
    }

    /// Check if byte is a valid Opus TOC byte
    private func isValidOpusToc(_ byte: UInt8) -> Bool {
        byte == 0xb8 || byte == 0x78 || byte == 0xf8 || byte == 0xb0 || byte == 0x70 || byte == 0xf0
    }

    // MARK: - Button Status

    private func tryParseButtonStatus(_ data: [UInt8]) {
        guard data.count >= 10 else { return }

        var pos = 0
        while pos < data.count - 5 {
            if data[pos] == 0x22 {
                pos += 1
                guard pos < data.count else { return }

                let (payloadLength, payloadPos) = decodeVarint(data, pos)
                pos = payloadPos

                guard payloadLength >= 2, payloadLength <= data.count - pos else { return }
                guard data[pos] == 0x42 else { return }

                var innerPos = pos + 1
                guard innerPos < data.count else { return }

                let (buttonLength, buttonPos) = decodeVarint(data, innerPos)
                innerPos = buttonPos

                guard buttonLength >= 2, buttonLength <= 50, innerPos + buttonLength <= data.count else { return }

                let buttonEnd = innerPos + buttonLength
                while innerPos < buttonEnd - 1 {
                    if data[innerPos] == 0x08 {
                        innerPos += 1
                        let (eventValue, _) = decodeVarint(data, innerPos)

                        guard eventValue >= 0 && eventValue <= 4 else { return }
                        guard let event = ButtonEvent(rawValue: eventValue) else { return }

                        // Skip NOT_PRESSED, LONG_PRESS, SHORT_PRESS
                        guard event == .doublePress else { return }

                        // Double press -> pause/resume/process conversation
                        let mappedState = 2
                        let buttonBytes: [UInt8] = [
                            UInt8(mappedState & 0xFF),
                            UInt8((mappedState >> 8) & 0xFF),
                            UInt8((mappedState >> 16) & 0xFF),
                            UInt8((mappedState >> 24) & 0xFF)
                        ]
                        buttonStreamSubject.send(buttonBytes)
                        return
                    }
                    innerPos += 1
                }
                return
            }
            pos += 1
        }
    }

    // MARK: - Device Status

    private func tryParseDeviceStatus(_ data: [UInt8]) {
        guard data.count >= 20 else { return }

        var pos = 0
        while pos < data.count - 5 {
            if data[pos] == 0x22 {
                pos += 1
                guard pos < data.count else { return }

                let (payloadLength, payloadPos) = decodeVarint(data, pos)
                pos = payloadPos

                guard payloadLength >= 10, payloadLength <= data.count - pos else { return }

                let payloadEnd = pos + payloadLength
                var innerPos = pos

                while innerPos < payloadEnd - 5 {
                    if data[innerPos] == 0x2a {
                        innerPos += 1
                        guard innerPos < data.count else { return }

                        let (statusLength, statusPos) = decodeVarint(data, innerPos)
                        innerPos = statusPos

                        guard statusLength >= 5, statusLength <= 500, innerPos + statusLength <= data.count else { return }

                        if let state = parseStorageStateFromDeviceStatus(data, start: innerPos, end: innerPos + statusLength) {
                            storageState = state
                            storageStateCompletion?.resume(returning: state)
                            storageStateCompletion = nil
                        }
                        return
                    }
                    innerPos += 1
                }
                return
            }
            pos += 1
        }
    }

    private func parseStorageStateFromDeviceStatus(_ data: [UInt8], start: Int, end: Int) -> [String: Int]? {
        guard start >= 0, end <= data.count, start < end else { return nil }

        var pos = start
        var state = [String: Int]()

        while pos < end - 1 && pos < data.count {
            let fieldMarker = data[pos]

            if fieldMarker == 0x2a {
                pos += 1
                guard pos < data.count else { break }

                let (storageLength, storagePos) = decodeVarint(data, pos)
                pos = storagePos

                guard storageLength >= 0, storageLength <= 200, pos + storageLength <= data.count else { break }

                let storageEnd = pos + storageLength

                while pos < storageEnd - 1 && pos < data.count {
                    let marker = data[pos]
                    pos += 1
                    guard pos < data.count else { break }

                    if [0x08, 0x10, 0x18, 0x20, 0x28].contains(marker) {
                        let (value, valuePos) = decodeVarint(data, pos)
                        pos = valuePos

                        switch marker {
                        case 0x08: state["oldest_flash_page"] = value
                        case 0x10: state["newest_flash_page"] = value
                        case 0x18: state["current_storage_session"] = value
                        case 0x20: state["free_capture_pages"] = value
                        case 0x28: state["total_capture_pages"] = value
                        default: break
                        }
                    }
                }
                return state.isEmpty ? nil : state
            }
            pos += 1
        }
        return nil
    }

    // MARK: - Varint Encoding/Decoding

    private func encodeVarint(_ value: Int) -> [UInt8] {
        var result = [UInt8]()
        var v = value
        while v > 0x7f {
            result.append(UInt8((v & 0x7f) | 0x80))
            v >>= 7
        }
        result.append(UInt8(v & 0x7f))
        return result.isEmpty ? [0] : result
    }

    private func decodeVarint(_ data: [UInt8], _ startPos: Int) -> (Int, Int) {
        var result = 0
        var shift = 0
        var pos = startPos
        while pos < data.count {
            let byte = data[pos]
            pos += 1
            result |= Int(byte & 0x7f) << shift
            if (byte & 0x80) == 0 { break }
            shift += 7
        }
        return (result, pos)
    }

    // MARK: - BLE Packet Parsing

    private struct BlePacket {
        let index: Int
        let seq: Int
        let numFrags: Int
        let payload: [UInt8]
    }

    private func parseBlePacket(_ data: [UInt8]) -> BlePacket? {
        var pos = 0
        var index: Int?
        var seq = 0
        var numFrags: Int?
        var payload: [UInt8]?

        while pos < data.count {
            let tag = data[pos]
            let fieldNum = Int(tag >> 3)
            let wireType = Int(tag & 0x07)
            pos += 1

            if wireType == 0 {
                let (value, newPos) = decodeVarint(data, pos)
                pos = newPos

                switch fieldNum {
                case 1: index = value
                case 2: seq = value
                case 3: numFrags = value
                default: break
                }
            } else if wireType == 2 {
                let (length, newPos) = decodeVarint(data, pos)
                pos = newPos

                if fieldNum == 4 {
                    payload = Array(data[pos..<min(pos + length, data.count)])
                }
                pos += length
            } else {
                break
            }
        }

        guard let idx = index, let nf = numFrags, let p = payload else { return nil }
        return BlePacket(index: idx, seq: seq, numFrags: nf, payload: p)
    }

    // MARK: - Message Encoding

    private func encodeField(_ fieldNum: Int, _ wireType: Int, _ value: [UInt8]) -> [UInt8] {
        let tag = (fieldNum << 3) | wireType
        return encodeVarint(tag) + value
    }

    private func encodeBytesField(_ fieldNum: Int, _ data: [UInt8]) -> [UInt8] {
        let length = encodeVarint(data.count)
        return encodeField(fieldNum, 2, length + data)
    }

    private func encodeMessage(_ fieldNum: Int, _ msgBytes: [UInt8]) -> [UInt8] {
        encodeBytesField(fieldNum, msgBytes)
    }

    private func encodeInt64Field(_ fieldNum: Int, _ value: Int64) -> [UInt8] {
        encodeField(fieldNum, 0, encodeVarint(Int(value)))
    }

    private func encodeInt32Field(_ fieldNum: Int, _ value: Int) -> [UInt8] {
        encodeField(fieldNum, 0, encodeVarint(value))
    }

    private func encodeBleWrapper(_ payload: [UInt8]) -> [UInt8] {
        var msg = [UInt8]()
        msg.append(contentsOf: encodeInt32Field(1, messageIndex))
        msg.append(contentsOf: encodeInt32Field(2, 0))
        msg.append(contentsOf: encodeInt32Field(3, 1))
        msg.append(contentsOf: encodeBytesField(4, payload))
        messageIndex += 1
        return msg
    }

    private func encodeRequestData() -> [UInt8] {
        requestId += 1
        var msg = [UInt8]()
        msg.append(contentsOf: encodeInt64Field(1, Int64(requestId)))
        msg.append(contentsOf: encodeField(2, 0, [0x00]))
        return encodeMessage(30, msg)
    }

    private func encodeSetCurrentTime(_ timestampMs: Int64) -> [UInt8] {
        let timeMsg = encodeInt64Field(1, timestampMs)
        let cmd = encodeMessage(6, timeMsg) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    private func encodeEnableDataStream(enable: Bool = true) -> [UInt8] {
        var msg = [UInt8]()
        msg.append(contentsOf: encodeField(1, 0, [0x00]))
        msg.append(contentsOf: encodeField(2, 0, [enable ? 0x01 : 0x00]))
        let cmd = encodeMessage(8, msg) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    private func encodeGetDeviceStatus() -> [UInt8] {
        let cmd = encodeMessage(21, []) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    private func encodeDownloadFlashPages(batchMode: Bool = true, realTime: Bool = false) -> [UInt8] {
        var msg = [UInt8]()
        msg.append(contentsOf: encodeField(1, 0, [batchMode ? 0x01 : 0x00]))
        msg.append(contentsOf: encodeField(2, 0, [realTime ? 0x01 : 0x00]))
        let cmd = encodeMessage(8, msg) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    private func encodeAcknowledgeProcessedData(_ upToIndex: Int) -> [UInt8] {
        let ackMsg = encodeInt32Field(1, upToIndex)
        let cmd = encodeMessage(7, ackMsg) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    private func encodeSetLedBrightness(_ brightness: Int) -> [UInt8] {
        var msg = [UInt8]()
        msg.append(contentsOf: encodeField(1, 0, encodeVarint(max(0, min(100, brightness)))))
        let cmd = encodeMessage(26, msg) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    private func encodeUnpairBluetooth(doNotReset: Bool = true) -> [UInt8] {
        var msg = [UInt8]()
        msg.append(contentsOf: encodeField(1, 0, [doNotReset ? 0x01 : 0x00]))
        let cmd = encodeMessage(15, msg) + encodeRequestData()
        return encodeBleWrapper(cmd)
    }

    // MARK: - Public Storage Methods

    /// Get storage status
    func getStorageStatus() async -> [String: Int]? {
        guard isInitialized else { return nil }

        do {
            let statusCmd = encodeGetDeviceStatus()
            try await transport.writeCharacteristic(
                data: Data(statusCmd),
                serviceUUID: DeviceUUIDs.Limitless.service,
                characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
                withResponse: true
            )

            // Wait for response with timeout
            return await withCheckedContinuation { continuation in
                storageStateCompletion = continuation

                Task {
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                    if storageStateCompletion != nil {
                        storageStateCompletion?.resume(returning: storageState)
                        storageStateCompletion = nil
                    }
                }
            }
        } catch {
            logger.debug("Error getting storage status: \(error.localizedDescription)")
            return nil
        }
    }

    /// Get flash page count
    func getFlashPageCount() async -> Int {
        guard let status = await getStorageStatus() else { return 0 }

        let oldest = status["oldest_flash_page"] ?? 0
        let newest = status["newest_flash_page"] ?? 0

        return newest >= oldest ? newest - oldest + 1 : 0
    }

    /// Enable batch mode to download stored flash pages
    func enableBatchMode() async {
        guard isInitialized else { return }

        do {
            rawDataBuffer.removeAll()
            fragmentBuffer.removeAll()
            completedFlashPages.removeAll()
            isBatchMode = true

            let cmd = encodeDownloadFlashPages(batchMode: true, realTime: false)
            try await transport.writeCharacteristic(
                data: Data(cmd),
                serviceUUID: DeviceUUIDs.Limitless.service,
                characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
                withResponse: true
            )
        } catch {
            isBatchMode = false
            logger.debug("Error enabling batch mode: \(error.localizedDescription)")
        }
    }

    /// Disable batch mode
    func disableBatchMode() async {
        guard isInitialized else { return }

        do {
            rawDataBuffer.removeAll()
            fragmentBuffer.removeAll()
            completedFlashPages.removeAll()
            firstFlashPageTimestampMs = nil

            let cmd = encodeDownloadFlashPages(batchMode: false, realTime: true)
            try await transport.writeCharacteristic(
                data: Data(cmd),
                serviceUUID: DeviceUUIDs.Limitless.service,
                characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
                withResponse: true
            )
            isBatchMode = false
        } catch {
            isBatchMode = false
        }
    }

    /// Acknowledge processed data
    func acknowledgeProcessedData(_ upToIndex: Int) async {
        guard isInitialized else { return }

        do {
            let ackCmd = encodeAcknowledgeProcessedData(upToIndex)
            try await transport.writeCharacteristic(
                data: Data(ackCmd),
                serviceUUID: DeviceUUIDs.Limitless.service,
                characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
                withResponse: true
            )
            logger.debug("Acknowledged processed data up to index \(upToIndex)")
        } catch {
            logger.debug("Error sending acknowledgment: \(error.localizedDescription)")
        }
    }

    /// Unpair without reset
    func unpairWithoutReset() async {
        guard isInitialized else { return }

        do {
            let cmd = encodeUnpairBluetooth(doNotReset: true)
            try await transport.writeCharacteristic(
                data: Data(cmd),
                serviceUUID: DeviceUUIDs.Limitless.service,
                characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
                withResponse: true
            )
            logger.debug("Sent unpair command (without reset)")
        } catch {
            logger.debug("Error sending unpair command: \(error.localizedDescription)")
        }
    }

    // MARK: - Battery

    override func getBatteryLevel() async -> Int {
        guard await isConnected() else { return -1 }

        do {
            let data = try await transport.readCharacteristic(
                serviceUUID: DeviceUUIDs.Battery.service,
                characteristicUUID: DeviceUUIDs.Battery.level
            )
            return data.isEmpty ? -1 : Int(data[0])
        } catch {
            logger.debug("Error reading battery level: \(error.localizedDescription)")
            return -1
        }
    }

    // MARK: - Audio

    override func getAudioCodec() async -> BleAudioCodec {
        .opusFS320
    }

    override func getAudioStream() -> AsyncThrowingStream<Data, Error> {
        return AsyncThrowingStream { [weak self] continuation in
            guard let self = self else {
                continuation.finish()
                return
            }

            let cancellable = self.audioStreamSubject
                .sink(
                    receiveCompletion: { _ in continuation.finish() },
                    receiveValue: { data in continuation.yield(data) }
                )

            continuation.onTermination = { @Sendable _ in
                cancellable.cancel()
            }
        }
    }

    // MARK: - Button

    override func getButtonState() async -> [UInt8] { [] }

    override func getButtonStream() -> AsyncThrowingStream<[UInt8], Error> {
        return AsyncThrowingStream { [weak self] continuation in
            guard let self = self else {
                continuation.finish()
                return
            }

            let cancellable = self.buttonStreamSubject
                .sink(receiveValue: { value in continuation.yield(value) })

            continuation.onTermination = { @Sendable _ in
                cancellable.cancel()
            }
        }
    }

    // MARK: - Features

    override func getFeatures() async -> OmiFeatures {
        .ledDimming
    }

    override func setLedDimRatio(_ ratio: Int) async {
        guard isInitialized else { return }

        do {
            let brightness = max(0, min(100, ratio))
            let cmd = encodeSetLedBrightness(brightness)
            try await transport.writeCharacteristic(
                data: Data(cmd),
                serviceUUID: DeviceUUIDs.Limitless.service,
                characteristicUUID: DeviceUUIDs.Limitless.txCharacteristic,
                withResponse: true
            )
            lastLedBrightness = brightness
            logger.debug("Set LED brightness to \(brightness)")
        } catch {
            logger.debug("Error setting LED brightness: \(error.localizedDescription)")
        }
    }

    override func getLedDimRatio() async -> Int? {
        lastLedBrightness
    }

    // MARK: - Unsupported Features

    override func hasPhotoStreaming() async -> Bool { false }
    override func getAccelerometerStream() -> AsyncThrowingStream<AccelerometerData, Error> {
        AsyncThrowingStream { $0.finish() }
    }

    // MARK: - Device Info

    override func updateDeviceInfo() async {
        device.modelNumber = "Limitless Pendant"
        device.firmwareRevision = "1.0.0"
        device.hardwareRevision = "Unknown"
        device.manufacturerName = "Limitless"
    }
}

// MARK: - Date Extension

private extension Date {
    var millisecondsSince1970: Int64 {
        Int64(timeIntervalSince1970 * 1000)
    }
}
