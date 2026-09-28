import XCTest

@testable import OmiKit

// Unit tests for the pure device-layer logic: connection/capture state
// transitions, Device Information identity parsing (invalid/absent →
// Unknown → per docs/auth-and-sessions.md "Device identity"), discovery
// naming, packet assembly order and dedupe. Packet normalization delegates
// to the real C++ middleware in `native-core/` through `Policy` — framing
// errors must return the nonzero `OMI_STATUS_*` codes, never a Swift
// reimplementation.

final class DevicesTests: XCTestCase {
    // MARK: - Device identity (BleDeviceInfoParsing)

    func testCharacteristicTextAcceptsValidUtf8() {
        XCTAssertEqual(BleDeviceInfoParsing.characteristicText([0x4F, 0x6D, 0x69]), "Omi")
        // Multi-byte UTF-8 (e.g. "Révue") survives.
        let text = "Rév"
        XCTAssertEqual(
            BleDeviceInfoParsing.characteristicText(Array(text.utf8)), text
        )
    }

    func testCharacteristicTextTrimsAsciiWhitespace() {
        XCTAssertEqual(
            BleDeviceInfoParsing.characteristicText([0x20, 0x76, 0x35, 0x20]), "v5"
        )
        XCTAssertEqual(
            BleDeviceInfoParsing.characteristicText([0x09, 0x61, 0x62, 0x0A]), "ab"
        )
    }

    func testCharacteristicTextRejectsAbsentEmptyAndControlBytes() {
        XCTAssertNil(BleDeviceInfoParsing.characteristicText(nil))
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([]))
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0x20, 0x20]))  // whitespace only
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0x00]))  // NUL padding
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0x76, 0x00, 0x35]))
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0x01, 0x02]))
    }

    func testCharacteristicTextRejectsInvalidUtf8() {
        // Lone continuation byte / truncated sequence is invalid.
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0xC3]))
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0x41, 0x80, 0x42]))
        // Overlong garbage: replacement char re-encodes differently.
        XCTAssertNil(BleDeviceInfoParsing.characteristicText([0xFF, 0xFE]))
    }

    func testDeviceInfoSnapshotDefaultsToUnknownForMissingFields() {
        let info = BleDeviceInfo()
        for field in DeviceInfoField.allCases {
            XCTAssertEqual(info.displayValue(for: field), "Unknown")
        }
    }

    func testDeviceInfoSnapshotParsesReadsAndUnknownForInvalid() {
        let info = BleDeviceInfoParsing.deviceInfo(reads: [
            .model: Array("Omi DV1".utf8),
            .firmware: [0x00],  // invalid → nil → Unknown
            .hardware: Array("rev-c".utf8),
            .manufacturer: nil,  // absent read → Unknown
            .serial: Array("SN-0007".utf8),
        ])
        XCTAssertEqual(info.model, "Omi DV1")
        XCTAssertEqual(info.displayValue(for: .firmware), "Unknown")
        XCTAssertEqual(info.hardware, "rev-c")
        XCTAssertEqual(info.displayValue(for: .manufacturer), "Unknown")
        XCTAssertEqual(info.serial, "SN-0007")
    }

    func testDeviceInfoFieldCharacteristicUuids() {
        // Bluetooth SIG assigned numbers for the Device Information service.
        XCTAssertEqual(DeviceInfoField.model.characteristicUuid, "2A24")
        XCTAssertEqual(DeviceInfoField.serial.characteristicUuid, "2A25")
        XCTAssertEqual(DeviceInfoField.firmware.characteristicUuid, "2A26")
        XCTAssertEqual(DeviceInfoField.hardware.characteristicUuid, "2A27")
        XCTAssertEqual(DeviceInfoField.manufacturer.characteristicUuid, "2A29")
    }

    // MARK: - Discovery naming (OmiBleDiscoveryNaming)

    func testDiscoveryNamingPrefersAdvertisedThenCachedName() {
        XCTAssertEqual(
            OmiBleDiscoveryNaming.discoveredName(
                advertisedLocalName: "Omi", cachedName: "Stale", manufacturerData: nil
            ),
            "Omi"
        )
        XCTAssertEqual(
            OmiBleDiscoveryNaming.discoveredName(
                advertisedLocalName: nil, cachedName: "Omi", manufacturerData: nil
            ),
            "Omi"
        )
        XCTAssertEqual(
            OmiBleDiscoveryNaming.discoveredName(
                advertisedLocalName: "  ", cachedName: nil, manufacturerData: nil
            ),
            ""
        )
    }

    func testDiscoveryNamingNotePinFallbackFromManufacturerData() {
        // PLAUD id 93 (0x5D) little-endian + NotePin payload.
        let data: [UInt8] = [93, 0x00, 0x04, 0x56, 0xCF, 0x00]
        XCTAssertEqual(
            OmiBleDiscoveryNaming.discoveredName(
                advertisedLocalName: nil, cachedName: nil, manufacturerData: data
            ),
            "NotePin"
        )
        XCTAssertTrue(OmiBleDiscoveryNaming.isNotePinAdvertisement(data))
        // Wrong payload or short data → no fallback.
        XCTAssertFalse(
            OmiBleDiscoveryNaming.isNotePinAdvertisement([93, 0x00, 0x04, 0x56, 0x00, 0x00])
        )
        XCTAssertFalse(OmiBleDiscoveryNaming.isNotePinAdvertisement(nil))
        XCTAssertEqual(
            OmiBleDiscoveryNaming.discoveredName(
                advertisedLocalName: nil, cachedName: nil, manufacturerData: [93, 0x00]
            ),
            ""
        )
    }

    func testOmiLikeFilter() {
        XCTAssertTrue(OmiDiscoveryFilter.isOmiLike("Omi"))
        XCTAssertTrue(OmiDiscoveryFilter.isOmiLike("NotePin"))
        XCTAssertTrue(OmiDiscoveryFilter.isOmiLike("notepin s"))
        XCTAssertFalse(OmiDiscoveryFilter.isOmiLike("JBL Flip"))
    }

    // MARK: - Packet assembly (AudioPacketAssembler + Policy/C++)

    /// Builds a real 0xAA 0x55 framed body the same way the C++ test suite
    /// does: sync bytes + payload + CRC32 (big endian) computed by the
    /// middleware itself.
    private func framedBody(payload: [UInt8]) -> [UInt8] {
        let crc = Policy.packetChecksum(payload)
        return [0xAA, 0x55] + payload + [
            UInt8((crc >> 24) & 0xFF), UInt8((crc >> 16) & 0xFF),
            UInt8((crc >> 8) & 0xFF), UInt8(crc & 0xFF),
        ]
    }

    private func rawPacket(index: UInt16, payload: [UInt8]) -> [UInt8] {
        [UInt8(index & 0xFF), UInt8(index >> 8)] + framedBody(payload: payload)
    }

    func testPacketChecksumDelegatesToCpp() {
        // CRC32 of "test" via the real C++ (checked against zlib CRC32).
        XCTAssertEqual(Policy.packetChecksum(Array("test".utf8)), 0xD87F7E0C)
        XCTAssertEqual(Policy.packetChecksum([]), 0)
    }

    func testAssemblerAcceptsValidFramedPacketsInOrder() {
        var assembler = AudioPacketAssembler()
        let first = assembler.classify(rawPacket(index: 0, payload: [1, 2, 3]))
        XCTAssertEqual(first, .accepted(index: 0, payload: [1, 2, 3]))
        let second = assembler.classify(rawPacket(index: 1, payload: [4]))
        XCTAssertEqual(second, .accepted(index: 1, payload: [4]))
    }

    func testAssemblerDropsDuplicates() {
        var assembler = AudioPacketAssembler()
        _ = assembler.classify(rawPacket(index: 7, payload: [9]))
        XCTAssertEqual(
            assembler.classify(rawPacket(index: 7, payload: [9])), .duplicate
        )
    }

    func testAssemblerRejectsBadFramingThroughCppStatus() {
        var assembler = AudioPacketAssembler()
        // Wrong sync bytes → OMI_STATUS_ERR_SYNC_BYTES (-2).
        var badSync = rawPacket(index: 0, payload: [1])
        badSync[2] = 0x00
        if case .invalid(let status) = assembler.classify(badSync) {
            XCTAssertEqual(status, -2)
        } else {
            XCTFail("expected invalid status for bad sync bytes")
        }
        // Corrupt CRC → OMI_STATUS_ERR_CHECKSUM (-3).
        var assembler2 = AudioPacketAssembler()
        var badCrc = rawPacket(index: 0, payload: [1, 2])
        badCrc[badCrc.count - 1] ^= 0xFF
        if case .invalid(let status) = assembler2.classify(badCrc) {
            XCTAssertEqual(status, -3)
        } else {
            XCTFail("expected invalid status for bad CRC")
        }
    }

    func testAssemblerHandlesSequenceWrapAndShortFrames() {
        var assembler = AudioPacketAssembler()
        _ = assembler.classify(rawPacket(index: 65_535, payload: [1]))
        // Wrap to 0 is a normal one-step delta (mod 65536), accepted.
        let wrapped = assembler.classify(rawPacket(index: 0, payload: [2]))
        XCTAssertEqual(wrapped, .accepted(index: 0, payload: [2]))
        XCTAssertEqual(assembler.classify([0x01]), .shortFrame)
        XCTAssertEqual(assembler.classify([]), .shortFrame)
    }

    func testAssemblerStreamRestartAfterLargeGap() {
        // Delta > 4096 is a stream restart: accepted as a new baseline
        // (upstream OmiBleManager rule), not dropped.
        var assembler = AudioPacketAssembler()
        _ = assembler.classify(rawPacket(index: 0, payload: [1]))
        let restarted = assembler.classify(rawPacket(index: 10_000, payload: [2]))
        XCTAssertEqual(restarted, .accepted(index: 10_000, payload: [2]))
        // And duplicates against the new baseline still drop.
        XCTAssertEqual(
            assembler.classify(rawPacket(index: 10_000, payload: [2])), .duplicate
        )
    }

    // MARK: - Capture session state machine

    func testCaptureOpenWaitsForFirstPacketThenActivates() {
        var capture = CaptureSessionMachine()
        XCTAssertFalse(capture.isCapturing)
        capture.open(deviceId: "dev-1", deviceName: "Omi", codec: 1, nowMs: 1_000)
        XCTAssertEqual(capture.stage, .waiting)
        XCTAssertTrue(capture.isCapturing)
        // Ingest while waiting activates on first accepted packet.
        XCTAssertEqual(
            capture.ingest(rawPacket(index: 0, payload: [1, 2, 3]), receivedAtMs: 1_050),
            0
        )
        XCTAssertEqual(capture.stage, .active)
        XCTAssertEqual(capture.chunkCount, 1)
        XCTAssertEqual(capture.byteCount, 3)
    }

    func testCaptureIgnoresRejectedPacketsAndCountsOnlyAccepted() {
        var capture = CaptureSessionMachine()
        capture.open(deviceId: "dev-1", deviceName: nil, codec: 1, nowMs: 0)
        XCTAssertEqual(capture.ingest(rawPacket(index: 0, payload: [5]), receivedAtMs: 1), 0)
        XCTAssertNil(capture.ingest(rawPacket(index: 0, payload: [5]), receivedAtMs: 2))  // duplicate
        XCTAssertNil(capture.ingest([0x01], receivedAtMs: 3))  // short frame
        XCTAssertEqual(capture.chunkCount, 1)
        XCTAssertEqual(capture.byteCount, 1)
    }

    func testCaptureHandoffProducesJournalInputAndCompletes() {
        var capture = CaptureSessionMachine()
        capture.open(deviceId: "dev-9", deviceName: "NotePin", codec: 3, nowMs: 100)
        _ = capture.ingest(rawPacket(index: 0, payload: [1]), receivedAtMs: 110)
        _ = capture.ingest(rawPacket(index: 1, payload: [2, 2]), receivedAtMs: 120)
        let handoff = capture.handoff(nowMs: 200)
        XCTAssertNotNil(handoff)
        XCTAssertEqual(handoff?.input.deviceId, "dev-9")
        XCTAssertEqual(handoff?.input.deviceName, "NotePin")
        XCTAssertEqual(handoff?.input.codec, 3)
        XCTAssertEqual(handoff?.packets.map { $0.index }, [0, 1])
        XCTAssertEqual(handoff?.byteCount, 3)
        XCTAssertEqual(handoff?.startedAtMs, 100)
        XCTAssertEqual(handoff?.endedAtMs, 200)
        XCTAssertEqual(capture.stage, .completed)
        XCTAssertFalse(capture.isCapturing)
        // Terminal: further ingest is a no-op.
        XCTAssertNil(capture.ingest(rawPacket(index: 2, payload: [9]), receivedAtMs: 300))
    }

    func testCaptureHandoffWithoutAudioYieldsNilJournal() {
        // First-audio readiness: an open capture with no packets completes
        // without creating a journal (journals are only created for real
        // audio).
        var capture = CaptureSessionMachine()
        capture.open(deviceId: "dev-1", deviceName: nil, codec: 1, nowMs: 10)
        XCTAssertNil(capture.handoff(nowMs: 20))
        XCTAssertEqual(capture.stage, .completed)
    }

    func testCaptureFailureIsTerminal() {
        var capture = CaptureSessionMachine()
        capture.open(deviceId: "dev-1", deviceName: nil, codec: 1, nowMs: 10)
        capture.fail()
        XCTAssertEqual(capture.stage, .failed)
        XCTAssertNil(capture.ingest(rawPacket(index: 0, payload: [1]), receivedAtMs: 20))
        XCTAssertNil(capture.handoff(nowMs: 30))
    }

    func testCaptureReopenResetsBatch() {
        var capture = CaptureSessionMachine()
        capture.open(deviceId: "a", deviceName: nil, codec: 1, nowMs: 0)
        _ = capture.ingest(rawPacket(index: 0, payload: [1]), receivedAtMs: 1)
        _ = capture.handoff(nowMs: 2)
        capture.open(deviceId: "b", deviceName: "Omi", codec: 2, nowMs: 10)
        XCTAssertEqual(capture.chunkCount, 0)
        XCTAssertEqual(capture.byteCount, 0)
        XCTAssertEqual(capture.stage, .waiting)
        // Sequence baseline was reset: index 0 accepted again.
        XCTAssertEqual(capture.ingest(rawPacket(index: 0, payload: [7]), receivedAtMs: 11), 0)
    }

    // MARK: - Energy policy (retained upstream rule)

    func testBatteryPersistenceRule() {
        XCTAssertTrue(OmiBleEnergyPolicy.shouldPersistBatteryReading(
            previousLevel: nil, previousTimestampMs: nil, level: 80, nowMs: 0
        ))
        XCTAssertFalse(OmiBleEnergyPolicy.shouldPersistBatteryReading(
            previousLevel: 80, previousTimestampMs: 0, level: 80, nowMs: 1_000
        ))
        XCTAssertTrue(OmiBleEnergyPolicy.shouldPersistBatteryReading(
            previousLevel: 80, previousTimestampMs: 0, level: 79, nowMs: 1_000
        ))
        XCTAssertTrue(OmiBleEnergyPolicy.shouldPersistBatteryReading(
            previousLevel: 80, previousTimestampMs: 0, level: 80,
            nowMs: OmiBleEnergyPolicy.batteryHistoryMinimumIntervalMs
        ))
    }
}
