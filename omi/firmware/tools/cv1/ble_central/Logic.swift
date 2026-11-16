import Foundation

// Foundation only. Wire contracts are pinned and explained in README.md.
enum Command: String, Codable { case scan, session, audio
    case imageState = "image-state", imageUpload = "image-upload"
    var isSMP: Bool { self == .imageState || self == .imageUpload }
}
enum Outcome: String, Codable, CaseIterable {
    case permissionDenied = "permission_denied", bluetoothOff = "bluetooth_off"
    case noAdvertisement = "no_advertisement", connectFailed = "connect_failed"
    case gattFailed = "gatt_failed", audioFailed = "audio_failed", interrupted, passed
}
enum InputError: Error, CustomStringConvertible {
    case invalid(String)
    var description: String { switch self { case .invalid(let text): return text } }
}
struct Options {
    let command: Command
    let seconds: Double
    let prefix: String
    let output: String
    let keepAudio: String?
    let expectSerial: String?
    let expectPeripheral: String?
    let upload: UploadImage?
    let mode: String?
    let noReset: Bool
    // Audio setup includes the entire session and its one reconnect.
    var deadlineSeconds: Double { command == .audio ? 32 + seconds : seconds }

    static func parse(_ args: [String]) throws -> Options {
        guard let first = args.first, let command = Command(rawValue: first) else {
            throw InputError.invalid("Expected scan, session, audio, image-state, or image-upload")
        }
        var flags: [String: String] = [:]
        var index = 1
        while index < args.count {
            let key = args[index]
            if key == "--no-reset" {
                guard flags[key] == nil else { throw InputError.invalid("Repeated --no-reset") }
                flags[key] = "true"; index += 1; continue
            }
            guard ["--file", "--mode", "--seconds", "--name-prefix", "--output", "--keep-audio", "--expect-serial", "--expect-peripheral"].contains(key),
                  flags[key] == nil, index + 1 < args.count, !args[index + 1].hasPrefix("--") else {
                throw InputError.invalid("Unknown, repeated, or incomplete option: \(key)")
            }
            flags[key] = args[index + 1]
            index += 2
        }
        guard let text = flags["--seconds"], let seconds = Double(text), seconds.isFinite,
              seconds > 0, seconds <= (command == .audio ? 3 : (command == .imageUpload ? 3600 : 120)) else {
            throw InputError.invalid("--seconds must be finite, > 0, and <= \(command == .audio ? 3 : (command == .imageUpload ? 3600 : 120))")
        }
        guard let output = flags["--output"], !output.isEmpty else {
            throw InputError.invalid("--output requires a new receipt path")
        }
        let prefix = flags["--name-prefix"] ?? "Omi"
        guard !prefix.isEmpty, !prefix.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else {
            throw InputError.invalid("--name-prefix must be nonempty and contain no controls")
        }
        if flags["--keep-audio"] != nil && command != .audio {
            throw InputError.invalid("--keep-audio is only valid for audio")
        }
        let expectSerial = flags["--expect-serial"]
        if let serial = expectSerial {
            guard command != .scan, !serial.isEmpty,
                  !serial.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else {
                throw InputError.invalid("--expect-serial requires a nonempty value without controls, for session, audio, image-state or image-upload")
            }
        }
        var expectPeripheral: String?
        if let text = flags["--expect-peripheral"] {
            guard command != .scan, let uuid = UUID(uuidString: text) else {
                throw InputError.invalid("--expect-peripheral requires a CoreBluetooth peripheral UUID, for session, audio, image-state or image-upload")
            }
            expectPeripheral = uuid.uuidString
        }
        if (command == .audio || command == .imageUpload) && expectSerial == nil && expectPeripheral == nil {
            throw InputError.invalid("\(command.rawValue) requires --expect-serial or --expect-peripheral before Bluetooth can start")
        }
        if let keep = flags["--keep-audio"], keep.isEmpty || URL(fileURLWithPath: keep).standardizedFileURL == URL(fileURLWithPath: output).standardizedFileURL {
            throw InputError.invalid("Audio and receipt paths must be distinct and nonempty")
        }
        if command != .imageUpload && ["--file", "--mode", "--no-reset"].contains(where: { flags[$0] != nil }) {
            throw InputError.invalid("--file, --mode and --no-reset are only valid for image-upload")
        }
        var upload: UploadImage?
        if command == .imageUpload {
            guard let path = flags["--file"], !path.isEmpty else { throw InputError.invalid("image-upload requires --file") }
            guard let mode = flags["--mode"], ["test", "confirm"].contains(mode) else { throw InputError.invalid("image-upload requires --mode test|confirm") }
            guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)), !data.isEmpty else {
                throw InputError.invalid("--file must be a readable, nonempty image")
            }
            upload = try UploadImage(data: data)
        }
        // Advisory rejection here; exclusiveFile remains the race-safe authority at reservation.
        if (try? FileManager.default.attributesOfItem(atPath: output)) != nil {
            throw InputError.invalid("--output already exists")
        }
        return Options(command: command, seconds: seconds, prefix: prefix, output: output,
                       keepAudio: flags["--keep-audio"], expectSerial: expectSerial, expectPeripheral: expectPeripheral, upload: upload, mode: flags["--mode"], noReset: flags["--no-reset"] != nil)
    }
}

// A baseline session may omit serial. An explicitly requested identity must pass before reconnect/audio.
// A peripheral pin (CoreBluetooth's per-host identifier) is for images without a DIS serial, such as 3.0.21.
// Discovery never connects to another identifier; connected(to:) records and re-checks it.
struct IdentityCheck: Codable {
    enum Status: String, Codable { case notRequested = "not_requested", pending, matched, wrong, absent }
    let expectedSerial: String?
    let expectedPeripheral: String?
    private(set) var checked = false
    private(set) var peripheralMismatch = false
    private(set) var status: Status
    init(expectedSerial: String?, expectedPeripheral: String? = nil) {
        self.expectedSerial = expectedSerial
        self.expectedPeripheral = expectedPeripheral
        status = expectedSerial == nil && expectedPeripheral == nil ? .notRequested : .pending
    }
    mutating func connected(to identifier: String) {
        guard let expectedPeripheral, status == .pending else { return }
        checked = true
        if identifier != expectedPeripheral { peripheralMismatch = true; status = .wrong }
        else if expectedSerial == nil { status = .matched }
    }
    mutating func evaluate(serial: String?) {
        guard let expectedSerial, status == .pending else { return }
        checked = true
        guard let serial, !serial.isEmpty else { status = .absent; return }
        status = serial == expectedSerial ? .matched : .wrong
    }
    var allowsContinuation: Bool { status == .notRequested || status == .matched }
    var failureDetail: String? {
        switch status {
        case .wrong: return peripheralMismatch ? "Identity check failed: peripheral identifier was wrong" : "Identity check failed: DIS serial was wrong"
        case .absent: return "Identity check failed: DIS serial was absent"
        default: return nil
        }
    }
}

// Each SMP connection must finish ordered DIS reads before subscription or request planning.
// A failed or incomplete identity never grants access, including after the reset reconnect.
struct SMPAccessGate {
    private(set) var identity: IdentityCheck
    private(set) var firmware: DecodedValue?
    private var remaining: [String]
    private var failed = false
    var nextRead: String? { failed ? nil : remaining.first }
    var allowsSMP: Bool { !failed && firmware != nil && remaining.isEmpty && identity.allowsContinuation }
    init(discovered: Set<String>, expectedSerial: String?, expectedPeripheral: String? = nil, connected: String = "") throws {
        guard discovered.contains(UUIDs.firmware) else { throw InputError.invalid("Required firmware revision characteristic absent") }
        identity = IdentityCheck(expectedSerial: expectedSerial, expectedPeripheral: expectedPeripheral)
        identity.connected(to: connected)
        if let detail = identity.failureDetail { throw InputError.invalid(detail) }
        remaining = [UUIDs.firmware, UUIDs.serial].filter { discovered.contains($0) }
    }
    mutating func consume(uuid: String, data: Data) throws {
        guard !failed, uuid == remaining.first else {
            failed = true
            throw InputError.invalid("SMP DIS reads must complete in firmware-then-serial order")
        }
        remaining.removeFirst()
        let decoded = decodeText(data)
        if uuid == UUIDs.firmware { firmware = decoded }
        if uuid == UUIDs.serial { identity.evaluate(serial: decoded.text) }
        if remaining.isEmpty && identity.status == .pending { identity.evaluate(serial: nil) }
        guard decoded.text?.isEmpty == false, identity.failureDetail == nil else {
            failed = true
            throw InputError.invalid(identity.failureDetail ?? "Invalid DIS UTF-8 or empty value")
        }
    }
}

struct FirstConnectionReads {
    let ordered: [String]
    let absentOptional: [String]
    init(discovered: Set<String>) throws {
        guard discovered.contains(UUIDs.firmware) else { throw InputError.invalid("Required firmware revision characteristic absent") }
        ordered = [UUIDs.firmware, UUIDs.serial, UUIDs.features, UUIDs.diagnostics, UUIDs.recovery].filter { discovered.contains($0) }
        absentOptional = [UUIDs.serial, UUIDs.features, UUIDs.diagnostics, UUIDs.recovery].filter { !discovered.contains($0) }
    }
}

enum UUIDs {
    static let suffix = "-E8F2-537E-4F6C-D104768A1214"
    static let audioService = "19B10000" + suffix, audioData = "19B10001" + suffix
    static let featuresService = "19B10020" + suffix, features = "19B10021" + suffix
    static let diagnosticsService = "19B10040" + suffix, diagnostics = "19B10041" + suffix
    /// Safe-mode recovery state: v1 is 16 bytes; v2 appends boot telemetry (96 bytes total).
    static let recovery = "19B10042" + suffix
    static let smpService = "8D53DC1D-1DB7-4CD3-868B-8A527460AA84"
    static let smpData = "DA2E7828-FBCE-4E01-AE9E-261174997C48"
    static let information = "180A", firmware = "2A26", serial = "2A25"
}

func matches(name: String?, prefix: String) -> Bool {
    name?.lowercased().hasPrefix(prefix.lowercased()) == true
}
func hex(_ data: Data) -> String { data.map { String(format: "%02x", $0) }.joined() }
func littleEndian(_ bytes: [UInt8], _ offset: Int, _ count: Int) -> UInt32 {
    (0..<count).reduce(0) { $0 | UInt32(bytes[offset + $1]) << (8 * $1) }
}
struct DecodedValue: Codable {
    let rawHex: String
    let layout: String
    var fields: [String: UInt32] = [:]
    var text: String? = nil
}
func decodeDiagnostics(_ data: Data) -> DecodedValue {
    let b = Array(data)
    guard b.count == 25, b[0] == 1, b[12] == 0 else {
        return DecodedValue(rawHex: hex(data), layout: "unknown; raw bytes only")
    }
    return DecodedValue(rawHex: hex(data), layout: "diagnostics_v1", fields: [
        "version": UInt32(b[0]), "reset_cause": littleEndian(b, 1, 4), "uptime_s": littleEndian(b, 5, 4),
        "battery_mv": littleEndian(b, 9, 2), "charging": UInt32(b[11]),
        "mic_overrun_count": littleEndian(b, 13, 4), "ble_tx_drop_count": littleEndian(b, 17, 4),
        "storage_error_count": littleEndian(b, 21, 4),
    ])
}
func decodeRecovery(_ data: Data) -> DecodedValue {
    DecodedValue(rawHex: hex(data), layout: data.count == 16 ? "recovery_v1; raw bytes" : "unknown; raw bytes only")
}
func decodeFeatures(_ data: Data) -> DecodedValue {
    guard data.count == 4 else { return DecodedValue(rawHex: hex(data), layout: "unknown; raw bytes only") }
    return DecodedValue(rawHex: hex(data), layout: "features_uint32_le", fields: ["bitmask": littleEndian(Array(data), 0, 4)])
}
func decodeText(_ data: Data) -> DecodedValue {
    DecodedValue(rawHex: hex(data), layout: "DIS UTF-8", text: String(data: data, encoding: .utf8))
}

struct AudioStats: Codable {
    private(set) var notifications = 0, bytes = 0, payloadBytes = 0, frameStarts = 0
    private(set) var malformed = 0, sequenceBreaks = 0, fragmentBreaks = 0
    private(set) var firstSequence: UInt16?, lastSequence: UInt16?
    private var lastFragment: UInt8?
    // A frame may span notifications. There is no last-fragment flag on this wire format.
    mutating func consume(_ data: Data) {
        notifications += 1
        bytes += data.count
        let b = Array(data)
        guard b.count > 3 else { malformed += 1; return }
        let sequence = UInt16(b[0]) | UInt16(b[1]) << 8
        let fragment = b[2]
        if let last = lastSequence, sequence != last &+ 1 { sequenceBreaks += 1 }
        if let last = lastFragment, fragment != 0, (last == 255 || fragment != last + 1) { fragmentBreaks += 1 }
        if firstSequence == nil { firstSequence = sequence }
        lastSequence = sequence
        lastFragment = fragment
        if fragment == 0 { frameStarts += 1 }
        payloadBytes += b.count - 3
    }
    var valid: Bool { notifications > 0 && malformed == 0 && sequenceBreaks == 0 && fragmentBreaks == 0 }
}

enum Phase: String, Codable {
    case waiting, scanning, connecting, gatt, disconnectForReconnect, reconnecting
    case subscribing, audio, unsubscribing, disconnectFinal, finished
}
enum StopReason { case complete, deadline, permission, bluetooth, connection, gatt, audio, interrupted }
struct Progress: Codable {
    var command: Command
    var phase: Phase = .waiting
    var matched = false, sessionComplete = false, audioComplete = false
    var audio = AudioStats()
    var permissionPending = false
    func outcome(_ reason: StopReason) -> Outcome {
        if reason == .interrupted { return .interrupted }
        if reason == .permission || (reason == .deadline && permissionPending) { return .permissionDenied }
        if reason == .bluetooth { return .bluetoothOff }
        if reason == .connection { return .connectFailed }
        if reason == .gatt { return .gattFailed }
        if reason == .audio { return .audioFailed }
        if reason == .deadline && phase == .waiting { return .bluetoothOff }
        if command == .scan {
            if reason != .deadline && reason != .complete { return .gattFailed }
            return matched ? .passed : .noAdvertisement
        }
        if reason == .complete && sessionComplete && (command != .audio || (audioComplete && audio.valid)) { return .passed }
        if !matched { return .noAdvertisement }
        switch phase {
        case .connecting, .disconnectForReconnect, .reconnecting: return .connectFailed
        case .subscribing, .audio, .unsubscribing: return .audioFailed
        case .disconnectFinal: return command == .audio ? .audioFailed : .gattFailed
        default: return .gattFailed
        }
    }
}

struct Advertisement: Codable {
    let name: String
    let rssi: Int
    let advertisedServices: [String]
    let connectable: Bool?
}
struct ConnectionRecord: Codable {
    let number: Int
    var services: [String] = []
    var reads: [String: DecodedValue] = [:]
    var absentOptionalCharacteristics: [String] = []
    var maximumWriteWithResponse: Int
    var maximumWriteWithoutResponse: Int
}
struct Receipt: Encodable {
    let schema = 1
    let firmwareLayoutSource = "2810eaf332c50e4c9a6b72d1a1f9c2838e754371"
    let startedAt: String
    var completedAt: String?
    let requestedSeconds: Double
    let deadlineSeconds: Double
    var progress: Progress
    var outcome: Outcome?
    var detail = ""
    var advertisements: [Advertisement] = []
    var advertisementsOmitted = 0
    var connections: [ConnectionRecord] = []
    var subscriptionAcknowledged = false, unsubscriptionAcknowledged = false
    var disconnectsAcknowledged = 0
    var audioStored = false
    var smp: [SMPEvent] = []
    var uploadMode: String?
    var uploadFileSHA256: String?
    var uploadImageHash: String?
    var resetRequested = false, postResetStateRead = false
    var postResetFirmware: DecodedValue?
    var identity = IdentityCheck(expectedSerial: nil)
    /// CoreBluetooth's per-host identifier of the connected peripheral; private like the serial.
    var peripheralIdentifier: String?
    let limitations = "CoreBluetooth exposes maximumWriteValueLength, not raw ATT MTU or read offsets. No long-read offset or MTU claim is made."
}

// Minimal CBOR subset used by mcumgr. Bytes are hex strings in JSON receipts.
indirect enum CBOR: Equatable, Encodable {
    case uint(UInt64), negative(Int64), bytes(Data), text(String), bool(Bool)
    case array([CBOR]), map([String: CBOR])
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .uint(let v): try c.encode(v)
        case .negative(let v): try c.encode(v)
        case .bytes(let v): try c.encode(hex(v))
        case .text(let v): try c.encode(v)
        case .bool(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .map(let v): try c.encode(v)
        }
    }
    subscript(_ key: String) -> CBOR? { if case .map(let m) = self { return m[key] }; return nil }
    var unsigned: UInt64? { if case .uint(let n) = self { return n }; return nil }
    var integer: String? {
        switch self { case .uint(let n): return String(n); case .negative(let n): return String(n); default: return nil }
    }
    func encoded() -> Data {
        func head(_ major: UInt8, _ n: UInt64) -> Data {
            if n < 24 { return Data([major << 5 | UInt8(n)]) }
            let size = n <= 255 ? 1 : n <= 65535 ? 2 : n <= 0xffffffff ? 4 : 8
            return Data([major << 5 | [1: UInt8(24), 2: 25, 4: 26, 8: 27][size]!])
                + Data((0..<size).reversed().map { UInt8(truncatingIfNeeded: n >> ($0 * 8)) })
        }
        switch self {
        case .uint(let n): return head(0, n)
        case .negative(let n): precondition(n < 0); return head(1, UInt64(-(n + 1)))
        case .bytes(let b): return head(2, UInt64(b.count)) + b
        case .text(let t): let b = Data(t.utf8); return head(3, UInt64(b.count)) + b
        case .bool(let b): return Data([b ? 0xf5 : 0xf4])
        case .array(let a): return a.reduce(head(4, UInt64(a.count))) { $0 + $1.encoded() }
        case .map(let m): return m.keys.sorted().reduce(head(5, UInt64(m.count))) { $0 + CBOR.text($1).encoded() + m[$1]!.encoded() }
        }
    }
    static func decode(_ data: Data) throws -> CBOR {
        let b = Array(data); var i = 0
        func fail() -> InputError { .invalid("Malformed or unsupported CBOR") }
        func byte() throws -> UInt8 {
            guard i < b.count else { throw fail() }; defer { i += 1 }; return b[i]
        }
        func value(_ depth: Int) throws -> CBOR {
            guard depth <= 24 else { throw fail() }
            let h = try byte(), major = h >> 5, info = h & 31
            if major == 7 {
                if h == 0xf4 { return .bool(false) }; if h == 0xf5 { return .bool(true) }; throw fail()
            }
            let indefinite = info == 31
            var n: UInt64 = 0
            if info < 24 { n = UInt64(info) }
            else if (24...27).contains(info) {
                for _ in 0..<(1 << (info - 24)) { n = (n << 8) | UInt64(try byte()) }
            } else if !indefinite { throw fail() }
            if indefinite && major != 4 && major != 5 { throw fail() }
            switch major {
            case 0: return .uint(n)
            case 1:
                guard n <= UInt64(Int64.max) else { throw fail() }; return .negative(-1 - Int64(n))
            case 2, 3:
                guard n <= UInt64(b.count - i) else { throw fail() }
                let bytes = Data(b[i..<(i + Int(n))]); i += Int(n)
                if major == 2 { return .bytes(bytes) }
                guard let text = String(data: bytes, encoding: .utf8) else { throw fail() }; return .text(text)
            case 4, 5:
                guard indefinite || n <= UInt64(b.count - i) else { throw fail() }
                var a: [CBOR] = [], m: [String: CBOR] = [:], count: UInt64 = 0
                while indefinite || count < n {
                    if indefinite && i < b.count && b[i] == 0xff { i += 1; break }
                    let v = try value(depth + 1)
                    if major == 4 { a.append(v) }
                    else {
                        guard case .text(let key) = v, m[key] == nil else { throw fail() }
                        m[key] = try value(depth + 1)
                    }
                    count += 1
                }
                return major == 4 ? .array(a) : .map(m)
            default: throw fail()
            }
        }
        let result = try value(0)
        guard i == b.count else { throw fail() }; return result
    }
}

struct SMPHeader: Equatable, Codable {
    let op: UInt8, length: UInt16, group: UInt16, sequence: UInt8, id: UInt8
    func encoded() -> Data {
        Data([0x08 | op, 0, UInt8(length >> 8), UInt8(truncatingIfNeeded: length),
              UInt8(group >> 8), UInt8(truncatingIfNeeded: group), sequence, id])
    }
    static func decode(_ data: Data) throws -> SMPHeader {
        let b = Array(data)
        guard b.count >= 8, b[0] & 0xf8 == 0x08, b[0] & 7 <= 3, b[1] == 0 else {
            throw InputError.invalid("Invalid SMP v2 header")
        }
        return SMPHeader(op: b[0] & 7, length: UInt16(b[2]) << 8 | UInt16(b[3]),
                         group: UInt16(b[4]) << 8 | UInt16(b[5]), sequence: b[6], id: b[7])
    }
}

// Notifications may split even the SMP header. Never interpret a fragment as a new response.
struct SMPReassembler {
    private var buffer = Data()
    mutating func consume(_ data: Data) throws -> Data? {
        guard !data.isEmpty, buffer.count + data.count <= 2475 else { throw InputError.invalid("SMP response exceeds 2475 bytes or is empty") }
        buffer += data
        guard buffer.count >= 8 else { return nil }
        let header = try SMPHeader.decode(buffer)
        let total = 8 + Int(header.length)
        guard total <= 2475, buffer.count <= total else { throw InputError.invalid("Invalid SMP response length") }
        guard buffer.count == total else { return nil }
        let frame = buffer; buffer = Data(); return frame
    }
}
struct SMPRequest {
    let name: String
    let header: SMPHeader
    let body: CBOR
    var frame: Data { header.encoded() + body.encoded() }
    // Full image data is deliberately excluded; offset/count and digests remain reviewable.
    var summary: CBOR {
        guard case .map(var m) = body else { return body }
        if case .bytes(let d) = m["data"] { m["data"] = nil; m["dataBytes"] = .uint(UInt64(d.count)) }
        return .map(m)
    }
    func response(_ frame: Data) throws -> CBOR {
        let h = try SMPHeader.decode(frame)
        guard h.op == header.op + 1, h.group == header.group, h.id == header.id,
              h.sequence == header.sequence, frame.count == 8 + Int(h.length) else {
            throw InputError.invalid("SMP response does not match outstanding group=\(header.group) id=\(header.id) seq=\(header.sequence)")
        }
        let body = try CBOR.decode(Data(frame.dropFirst(8)))
        guard case .map = body else { throw InputError.invalid("SMP response must be a map") }
        return body
    }
    func checkError(_ body: CBOR) throws {
        for value in [body["rc"], body["err"]?["rc"]].compactMap({ $0 }) {
            guard let rc = value.integer else { throw InputError.invalid("Invalid SMP rc") }
            if rc != "0" {
                throw InputError.invalid("SMP group=\(header.group) id=\(header.id) rc=\(rc) err.group=\(body["err"]?["group"]?.integer ?? "absent")")
            }
        }
        if let err = body["err"], err["rc"] == nil { throw InputError.invalid("Malformed SMP err map") }
    }
}
struct SMPEvent: Encodable {
    let at: String, direction: String, name: String
    let header: SMPHeader
    let body: CBOR
}

// MCUboot's SHA256 TLV is the image identity; upload SHA covers the entire supplied file.
struct UploadImage {
    let data: Data, hash: Data
    init(data: Data) throws { self.data = data; hash = try imageHash(data) }
}
func imageHash(_ data: Data) throws -> Data {
    let b = Array(data)
    func bad() -> InputError { .invalid("Invalid MCUboot header/TLV SHA256") }
    func le(_ off: Int, _ count: Int) throws -> Int {
        guard off >= 0, off + count <= b.count else { throw bad() }
        return Int(littleEndian(b, off, count))
    }
    guard b.count >= 32, try le(0, 4) == 0x96f3b83d else { throw bad() }
    let header = try le(8, 2), protected = try le(10, 2), size = try le(12, 4)
    guard header >= 32, header + size <= b.count else { throw bad() }
    var start = header + size
    if protected > 0 {
        guard protected >= 4, try le(start, 2) == 0x6908, try le(start + 2, 2) == protected,
              start + protected <= b.count else { throw bad() }
        start += protected
    }
    guard try le(start, 2) == 0x6907 else { throw bad() }
    let total = try le(start + 2, 2), end = start + total
    guard total >= 4, end <= b.count else { throw bad() }
    var pos = start + 4, hash: Data?
    while pos < end {
        guard pos + 4 <= end else { throw bad() }
        let tag = try le(pos, 2), length = try le(pos + 2, 2); pos += 4
        guard pos + length <= end else { throw bad() }
        if tag == 0x10 {
            guard length == 32, hash == nil else { throw bad() }; hash = Data(b[pos..<(pos + length)])
        }
        pos += length
    }
    guard let hash else { throw bad() }; return hash
}

func uploadBody(image: UploadImage, sha: Data, offset: Int, count: Int) -> CBOR {
    var m: [String: CBOR] = ["off": .uint(UInt64(offset)), "data": .bytes(image.data.subdata(in: offset..<(offset + count)))]
    if offset == 0 {
        m["image"] = .uint(0); m["len"] = .uint(UInt64(image.data.count)); m["sha"] = .bytes(sha)
    }
    return .map(m)
}
func uploadChunk(image: UploadImage, sha: Data, offset: Int, maximumWrite: Int) throws -> CBOR {
    guard maximumWrite > 0, offset >= 0, offset < image.data.count else { throw InputError.invalid("Invalid upload offset/write length") }
    // Use whole BLE writes up to the firmware reassembly capacity (header included).
    let budget = maximumWrite > 2475 ? 2475 : (2475 / maximumWrite) * maximumWrite
    var low = 0, high = min(image.data.count - offset, budget)
    while low < high {
        let mid = (low + high + 1) / 2
        if 8 + uploadBody(image: image, sha: sha, offset: offset, count: mid).encoded().count <= budget { low = mid }
        else { high = mid - 1 }
    }
    guard low > 0 else { throw InputError.invalid("No upload data fits SMP reassembly capacity") }
    return uploadBody(image: image, sha: sha, offset: offset, count: low)
}

// Pure command sequencer. The transport sends one request and waits for its matching response.
struct SMPPlan {
    enum Step { case boot, initialState, echo, upload, mark, markedState, reset, postBoot, postState, postEcho, done }
    private(set) var step: Step
    private var sequence: UInt8 = 0
    private(set) var offset = 0
    let image: UploadImage?
    let sha: Data
    let confirm: Bool, noReset: Bool
    private let expectedSerial: String?, expectedPeripheral: String?
    private(set) var access: SMPAccessGate?
    mutating func endConnection() { access = nil }
    mutating func beginConnection(discovered: Set<String>, peripheral: String = "") throws {
        access = nil
        access = try SMPAccessGate(discovered: discovered, expectedSerial: expectedSerial,
                                   expectedPeripheral: expectedPeripheral, connected: peripheral)
    }
    mutating func consumeDIS(uuid: String, data: Data) throws {
        guard access != nil else { throw InputError.invalid("SMP DIS discovery incomplete") }
        try access!.consume(uuid: uuid, data: data)
    }
    init(options: Options, sha: Data) {
        expectedSerial = options.expectSerial; expectedPeripheral = options.expectPeripheral
        image = options.upload; self.sha = sha; confirm = options.mode == "confirm"; noReset = options.noReset
        step = image == nil ? .boot : .initialState
    }
    mutating func request(maximumWrite: Int) throws -> SMPRequest? {
        guard access?.allowsSMP == true else { throw InputError.invalid("SMP blocked until DIS reads and identity check pass") }
        let op: UInt8, group: UInt16, id: UInt8, body: CBOR, name: String
        switch step {
        case .done: return nil
        case .boot, .postBoot: op = 0; group = 0; id = 8; body = .map([:]); name = step == .boot ? "bootloader-info" : "post-reset-bootloader-info"
        case .initialState, .markedState, .postState:
            op = 0; group = 1; id = 0; body = .map([:])
            name = step == .initialState ? "initial-image-state" : step == .markedState ? "marked-image-state" : "post-reset-image-state"
        case .echo, .postEcho: op = 2; group = 0; id = 0; body = .map(["d": .text("cv1-ble-central")]); name = "echo"
        case .upload:
            op = 2; group = 1; id = 1; name = "image-upload"
            body = try uploadChunk(image: image!, sha: sha, offset: offset, maximumWrite: maximumWrite)
        case .mark:
            op = 2; group = 1; id = 0; name = "mark-image"
            body = .map(["hash": .bytes(image!.hash), "confirm": .bool(confirm)])
        case .reset: op = 2; group = 0; id = 5; body = .map([:]); name = "reset"
        }
        let header = SMPHeader(op: op, length: UInt16(body.encoded().count), group: group, sequence: sequence, id: id)
        sequence &+= 1
        return SMPRequest(name: name, header: header, body: body)
    }
    mutating func accept(_ body: CBOR) throws {
        switch step {
        case .boot: step = .initialState
        case .initialState: step = image == nil ? .echo : .upload
        case .echo, .postEcho: step = .done
        case .upload:
            guard let next = body["off"]?.unsigned, next <= UInt64(image!.data.count), Int(next) != offset else {
                throw InputError.invalid("Missing, stalled or out-of-range SMP upload off")
            }
            offset = Int(next); step = offset == image!.data.count ? .mark : .upload
        case .mark: step = .markedState
        case .markedState: step = noReset ? .done : .reset
        case .reset: step = .postBoot; endConnection()
        case .postBoot: step = .postState
        case .postState: step = .postEcho
        case .done: throw InputError.invalid("Unexpected SMP response after completion")
        }
    }
}
