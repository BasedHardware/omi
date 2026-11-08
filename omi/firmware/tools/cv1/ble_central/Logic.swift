import Foundation

// Foundation only. Wire contracts are pinned and explained in README.md.
enum Command: String, Codable { case scan, session, audio }
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
    // Audio setup includes the entire session and its one reconnect.
    var deadlineSeconds: Double { command == .audio ? 32 + seconds : seconds }

    static func parse(_ args: [String]) throws -> Options {
        guard let first = args.first, let command = Command(rawValue: first) else {
            throw InputError.invalid("Expected scan, session, or audio")
        }
        var flags: [String: String] = [:]
        var index = 1
        while index < args.count {
            let key = args[index]
            guard ["--seconds", "--name-prefix", "--output", "--keep-audio", "--expect-serial"].contains(key),
                  flags[key] == nil, index + 1 < args.count, !args[index + 1].hasPrefix("--") else {
                throw InputError.invalid("Unknown, repeated, or incomplete option: \(key)")
            }
            flags[key] = args[index + 1]
            index += 2
        }
        guard let text = flags["--seconds"], let seconds = Double(text), seconds.isFinite,
              seconds > 0, seconds <= (command == .audio ? 3 : 120) else {
            throw InputError.invalid("--seconds must be finite, > 0, and <= \(command == .audio ? 3 : 120)")
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
                throw InputError.invalid("--expect-serial requires a nonempty value without controls, for session or audio")
            }
        }
        if command == .audio && expectSerial == nil {
            throw InputError.invalid("audio requires --expect-serial before Bluetooth can start")
        }
        if let keep = flags["--keep-audio"], keep.isEmpty || URL(fileURLWithPath: keep).standardizedFileURL == URL(fileURLWithPath: output).standardizedFileURL {
            throw InputError.invalid("Audio and receipt paths must be distinct and nonempty")
        }
        return Options(command: command, seconds: seconds, prefix: prefix, output: output,
                       keepAudio: flags["--keep-audio"], expectSerial: expectSerial)
    }
}

// A baseline session may omit serial. An explicitly requested identity must pass before reconnect/audio.
struct IdentityCheck: Codable {
    enum Status: String, Codable { case notRequested = "not_requested", pending, matched, wrong, absent }
    let expectedSerial: String?
    private(set) var checked = false
    private(set) var status: Status
    init(expectedSerial: String?) {
        self.expectedSerial = expectedSerial
        status = expectedSerial == nil ? .notRequested : .pending
    }
    mutating func evaluate(serial: String?) {
        guard let expectedSerial else { return }
        checked = true
        guard let serial, !serial.isEmpty else { status = .absent; return }
        status = serial == expectedSerial ? .matched : .wrong
    }
    var allowsContinuation: Bool { status == .notRequested || status == .matched }
    var failureDetail: String? {
        switch status {
        case .wrong: return "Identity check failed: DIS serial was wrong"
        case .absent: return "Identity check failed: DIS serial was absent"
        default: return nil
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
    var identity = IdentityCheck(expectedSerial: nil)
    let limitations = "CoreBluetooth exposes maximumWriteValueLength, not raw ATT MTU or read offsets. No long-read offset or MTU claim is made."
}
