@preconcurrency import CoreBluetooth
import Foundation

public extension OmiGATT {
    /// Offline storage (firmware `lib/core/storage.c`). `storageControl` takes commands and notifies
    /// replies and audio; `storageStatus` is a 16-byte read.
    static let storageService = CBUUID(string: "30295780-4301-eabd-2904-2849adfeae43")
    static let storageControl = CBUUID(string: "30295781-4301-eabd-2904-2849adfeae43")
    static let storageStatus = CBUUID(string: "30295782-4301-eabd-2904-2849adfeae43")
    /// Time sync (firmware `transport.c`): the Omi records to storage only once its clock is set.
    static let timeSyncService = CBUUID(string: "19b10030-e8f2-537e-4f6c-d104768a1214")
    static let timeSyncWrite = CBUUID(string: "19b10031-e8f2-537e-4f6c-d104768a1214")
}

/// The Omi's SD ring buffer: what it recorded while the phone was away. One record is
/// `[timestamp u32 BE][440 audio bytes]`; the audio bytes are packed `[size u8][frame]…`
/// (firmware `transport.c` `write_to_storage`). Sequence numbers count records.
public enum OmiStorage {
    public static let recordSize = 444
    public static let payloadSize = 440
    /// Custody firmware marks a timestamp taken while the clock was unset (seconds since boot).
    static let uptimeFlag: UInt32 = 0x8000_0000

    public enum Command: Equatable, Sendable {
        case info
        /// `count` nil streams everything from `start`.
        case read(start: UInt64, count: UInt32?)
        /// Frees every record below `seq`.
        case advance(to: UInt64)
        case stop

        public var bytes: Data {
            switch self {
            case .info: Data([0x10])
            case let .read(start, count):
                Data([0x11]) + start.bigEndianBytes + (count.map { $0.bigEndianBytes } ?? Data())
            case let .advance(seq): Data([0x12]) + seq.bigEndianBytes
            case .stop: Data([0x03])
            }
        }
    }

    public enum AckStatus {
        public static let ok: UInt8 = 0
        public static let notReady: UInt8 = 9
        public static let seqOutOfRange: UInt8 = 10
    }

    /// `NOTIFY_INFO`. Custody firmware appends capabilities, a contract version and a ring id
    /// (`app/lib/services/wals/PENDANT_RING_CUSTODY.md` §1c); a ring id changes whenever sequence
    /// numbers restart, so a saved position is only meaningful for the same ring id.
    public struct Info: Equatable, Sendable {
        public var readSeq: UInt64
        public var writeSeq: UInt64
        public var capacity: UInt32
        public var dropped: UInt64
        public var ringID: UInt64?

        public init(readSeq: UInt64, writeSeq: UInt64, capacity: UInt32 = 0, dropped: UInt64 = 0, ringID: UInt64? = nil) {
            self.readSeq = readSeq
            self.writeSeq = writeSeq
            self.capacity = capacity
            self.dropped = dropped
            self.ringID = ringID
        }

        public var unread: UInt64 {
            writeSeq > readSeq ? writeSeq - readSeq : 0
        }
    }

    /// The status read: four little-endian `u32`s.
    public struct Status: Equatable, Sendable {
        public var usedBytes: UInt32
        public var unreadRecords: UInt32
        public var freeBytes: UInt32
        public var clockValid: Bool

        public init?(_ value: Data) {
            let bytes = [UInt8](value)
            guard bytes.count >= 16 else { return nil }
            usedBytes = bytes.littleEndianU32(at: 0)
            unreadRecords = bytes.littleEndianU32(at: 4)
            freeBytes = bytes.littleEndianU32(at: 8)
            clockValid = bytes.littleEndianU32(at: 12) != 0
        }
    }

    public enum Notification: Equatable, Sendable {
        case ack(UInt8)
        case info(Info)
        /// Raw record bytes, not aligned to records.
        case data(Data)
        case done(status: UInt8, nextSeq: UInt64)
        case readBegin(start: UInt64, count: UInt32)
        case other(UInt8)

        public init?(_ value: Data) {
            let bytes = [UInt8](value)
            guard let opcode = bytes.first else { return nil }
            switch opcode {
            case 0x01 where bytes.count >= 2:
                self = .ack(bytes[1])
            case 0x02 where bytes.count >= 31:
                self = .info(Info(
                    readSeq: bytes.bigEndianU64(at: 1), writeSeq: bytes.bigEndianU64(at: 9),
                    capacity: bytes.bigEndianU32(at: 17),
                    dropped: bytes.bigEndianU64(at: 21),
                    ringID: bytes.count >= 41 ? bytes.bigEndianU64(at: 33) : nil
                ))
            case 0x03:
                self = .data(Data(bytes.dropFirst()))
            case 0x04 where bytes.count >= 10:
                self = .done(status: bytes[1], nextSeq: bytes.bigEndianU64(at: 2))
            case 0x05 where bytes.count >= 13:
                self = .readBegin(start: bytes.bigEndianU64(at: 1), count: bytes.bigEndianU32(at: 9))
            case 0x01, 0x02, 0x04, 0x05:
                return nil
            default:
                self = .other(opcode)
            }
        }
    }

    /// What the driver reports about storage, on its own lossless stream.
    public enum Event: Equatable, Sendable {
        /// Notifications are on: commands can be sent.
        case ready
        case status(Status)
        case notification(Notification)
    }

    public struct Record: Equatable, Sendable {
        /// Epoch seconds; nil when the Omi's clock was not set.
        public var timestamp: UInt32?
        public var frames: [Data]

        public init(timestamp: UInt32?, frames: [Data]) {
            self.timestamp = timestamp
            self.frames = frames
        }

        public init(_ record: Data) {
            let bytes = [UInt8](record)
            let raw = bytes.count >= 4 ? bytes.bigEndianU32(at: 0) : 0
            timestamp = raw == 0 || raw & OmiStorage.uptimeFlag != 0 ? nil : raw
            frames = OmiStorage.frames(in: Array(bytes.dropFirst(4)))
        }
    }

    /// Unpacks `[size][frame]…`. A zero byte is padding. At a block boundary the firmware writes the
    /// size of a frame that went to the next block and nothing after it is valid, hence `>=`
    /// (same rule as upstream `ring_protocol.dart` `parseAudioPayload`).
    public static func frames(in payload: [UInt8]) -> [Data] {
        var frames: [Data] = []
        var offset = 0
        while offset < payload.count - 1 {
            let size = Int(payload[offset])
            if size == 0 {
                offset += 1
                continue
            }
            if offset + 1 + size >= payload.count { break }
            frames.append(Data(payload[(offset + 1) ..< (offset + 1 + size)]))
            offset += 1 + size
        }
        return frames
    }

    /// Cuts the data notifications back into records.
    public struct Reassembler: Sendable {
        private var buffer = Data()

        public init() {}

        public var pendingBytes: Int {
            buffer.count
        }

        public mutating func append(_ bytes: Data) -> [Record] {
            buffer.append(bytes)
            var records: [Record] = []
            while buffer.count >= OmiStorage.recordSize {
                records.append(Record(buffer.prefix(OmiStorage.recordSize)))
                buffer = Data(buffer.dropFirst(OmiStorage.recordSize))
            }
            return records
        }
    }

    /// The time sync write: epoch seconds as a little-endian `u32` (Flutter `performSyncTime`).
    public static func timeSyncPayload(_ date: Date) -> Data {
        UInt32(clamping: Int64(date.timeIntervalSince1970)).littleEndianBytes
    }
}

extension FixedWidthInteger {
    var bigEndianBytes: Data {
        withUnsafeBytes(of: bigEndian) { Data($0) }
    }

    var littleEndianBytes: Data {
        withUnsafeBytes(of: littleEndian) { Data($0) }
    }
}

extension [UInt8] {
    func bigEndianU64(at index: Int) -> UInt64 {
        self[index ..< index + 8].reduce(0) { $0 << 8 | UInt64($1) }
    }

    func bigEndianU32(at index: Int) -> UInt32 {
        self[index ..< index + 4].reduce(0) { $0 << 8 | UInt32($1) }
    }

    func littleEndianU32(at index: Int) -> UInt32 {
        self[index ..< index + 4].reversed().reduce(0) { $0 << 8 | UInt32($1) }
    }
}
