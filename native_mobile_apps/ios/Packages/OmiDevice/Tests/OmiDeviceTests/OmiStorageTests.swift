import Foundation
@testable import OmiDevice
import Testing

/// Byte fixtures built the way firmware `lib/core/storage.c` and `transport.c` lay them out.
struct OmiStorageTests {
    @Test func encodesCommands() {
        #expect(OmiStorage.Command.info.bytes == Data([0x10]))
        #expect(OmiStorage.Command.stop.bytes == Data([0x03]))
        #expect(OmiStorage.Command.read(start: 0x0102, count: nil).bytes == Data([0x11, 0, 0, 0, 0, 0, 0, 0x01, 0x02]))
        #expect(OmiStorage.Command.read(start: 7, count: 600).bytes == Data([0x11, 0, 0, 0, 0, 0, 0, 0, 7, 0, 0, 0x02, 0x58]))
        #expect(OmiStorage.Command.advance(to: 0x1_0000_0001).bytes == Data([0x12, 0, 0, 0, 1, 0, 0, 0, 1]))
    }

    /// `send_ring_info_response`: read u64, write u64, capacity u32, dropped u64, record size u16 (31 bytes).
    @Test func parsesLegacyInfo() throws {
        var value = Data([0x02])
        value += UInt64(120).bigEndianBytes + UInt64(1320).bigEndianBytes + UInt32(1_000_000).bigEndianBytes
        value += UInt64(3).bigEndianBytes + UInt16(444).bigEndianBytes
        guard case let .info(info) = try #require(OmiStorage.Notification(value)) else {
            Issue.record("expected info")
            return
        }
        #expect(info == OmiStorage.Info(readSeq: 120, writeSeq: 1320, capacity: 1_000_000, dropped: 3, ringID: nil))
        #expect(info.unread == 1200)
    }

    /// Custody contract v1: caps u8, version u8, ring id u64 appended (41 bytes).
    @Test func parsesCustodyInfoRingID() throws {
        var value = Data([0x02]) + UInt64(5).bigEndianBytes + UInt64(9).bigEndianBytes + UInt32(10).bigEndianBytes
        value += UInt64(0).bigEndianBytes + UInt16(444).bigEndianBytes + Data([0x0F, 0x01]) + UInt64(0xABCD).bigEndianBytes
        guard case let .info(info) = try #require(OmiStorage.Notification(value)) else {
            Issue.record("expected info")
            return
        }
        #expect(info.ringID == 0xABCD)
    }

    @Test func parsesControlNotifications() {
        #expect(OmiStorage.Notification(Data([0x01, 0x0A])) == .ack(10))
        #expect(OmiStorage.Notification(Data([0x04, 0x00]) + UInt64(42).bigEndianBytes) == .done(status: 0, nextSeq: 42))
        let begin = Data([0x05]) + UInt64(40).bigEndianBytes + UInt32(2).bigEndianBytes
        #expect(OmiStorage.Notification(begin) == .readBegin(start: 40, count: 2))
        #expect(OmiStorage.Notification(Data([0x03, 0xAA, 0xBB])) == .data(Data([0xAA, 0xBB])))
        #expect(OmiStorage.Notification(Data([0x04, 0x00])) == nil)
        #expect(OmiStorage.Notification(Data()) == nil)
    }

    /// `storage_read_characteristic`: used, unread, free, rtc_valid as host-order (LE) u32.
    @Test func parsesStatusRead() throws {
        let value = UInt32(888).littleEndianBytes + UInt32(2).littleEndianBytes
            + UInt32(5000).littleEndianBytes + UInt32(1).littleEndianBytes
        let status = try #require(OmiStorage.Status(value))
        #expect(status.unreadRecords == 2)
        #expect(status.clockValid)
        #expect(OmiStorage.Status(Data([1, 2])) == nil)
    }

    /// Two 80-byte Opus frames, then the overflow marker `write_to_storage` leaves at a block edge.
    @Test func unpacksRecordFrames() {
        var payload = [UInt8](repeating: 0x55, count: OmiStorage.payloadSize)
        payload[0] = 80
        payload[81] = 80
        payload[162] = 0
        payload[163] = 80
        payload[244] = 200 // a frame that went to the next block: stop here
        var record = UInt32(1_760_000_000).bigEndianBytes
        record += Data(payload)
        let parsed = OmiStorage.Record(record)
        #expect(parsed.timestamp == 1_760_000_000)
        #expect(parsed.frames.count == 3)
        #expect(parsed.frames.allSatisfy { $0.count == 80 })
    }

    /// The exact-fit case: the last frame ends one byte before the block end.
    @Test func keepsAFrameThatFillsTheBlock() {
        var payload = [UInt8](repeating: 0, count: OmiStorage.payloadSize)
        payload[0] = 200
        payload[201] = 237 // 201 + 1 + 237 = 439
        #expect(OmiStorage.frames(in: payload).map(\.count) == [200, 237])
    }

    @Test func clockNotSetMeansNoTimestamp() {
        let unset = OmiStorage.Record(Data(repeating: 0, count: OmiStorage.recordSize))
        #expect(unset.timestamp == nil)
        let uptime = OmiStorage.Record(UInt32(0x8000_0010).bigEndianBytes + Data(count: OmiStorage.payloadSize))
        #expect(uptime.timestamp == nil)
    }

    @Test func reassemblesUnalignedNotifications() {
        var reassembler = OmiStorage.Reassembler()
        let records = (0 ..< 3).map { index in
            UInt32(1_760_000_000 + index).bigEndianBytes + Data([10] + [UInt8](repeating: 1, count: 10) + [UInt8](repeating: 0, count: 429))
        }
        let stream = records.reduce(Data(), +)
        var out: [OmiStorage.Record] = []
        // 243-byte notifications: an MTU of 247 minus ATT header and opcode.
        var offset = 0
        while offset < stream.count {
            out += reassembler.append(stream.subdata(in: offset ..< min(stream.count, offset + 243)))
            offset += 243
        }
        #expect(out.map(\.timestamp) == [1_760_000_000, 1_760_000_001, 1_760_000_002])
        #expect(out.allSatisfy { $0.frames == [Data(repeating: 1, count: 10)] })
        #expect(reassembler.pendingBytes == 0)
    }

    @Test func timeSyncIsLittleEndianSeconds() {
        #expect(OmiStorage.timeSyncPayload(Date(timeIntervalSince1970: 0x6700_0102)) == Data([0x02, 0x01, 0x00, 0x67]))
    }
}
