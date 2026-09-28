import Foundation

// Capture session state machine: open capture → packet batching → journal
// handoff. Pure logic, unit-testable without hardware.
//
// Packet normalization is NOT re-derived here: framed-packet handling
// delegates to the shared C++ middleware via `Policy.normalizePacket`
// (`native-core/`, 0xAA 0x55 framing + CRC32). The sequence-index dedupe
// and stream-restart rules mirror the upstream native packet accounting in
// `app/ios/Runner/Ble/OmiBleManager.swift` (`recordAudioPacket`): duplicates
// (delta 0) drop, gaps larger than 4096 are treated as a stream restart
// baseline rather than thousands of lost packets.

/// Decision for one raw audio notification, before capture ingestion.
public enum PacketDecision: Sendable, Equatable {
    /// Normalized payload plus its sequence index — accepted into capture.
    case accepted(index: UInt16, payload: [UInt8])
    /// Repeated sequence index (already accounted).
    case duplicate
    /// Shorter than the minimum frame (index + sync bytes).
    case shortFrame
    /// The C++ codec rejected the frame (sync/CRC/buffer error) — nonzero
    /// `OMI_STATUS_*` from `omi_native_boundary.h`.
    case invalid(status: Int32)
}

/// Running packet assembly accounting for one connected device's audio
/// stream. Owns sequence-index dedupe; codec validation goes through
/// `Policy.normalizePacket` only.
public struct AudioPacketAssembler: Sendable {
    private var lastIndex: UInt16?

    public init() {}

    /// Classifies a raw audio characteristic value:
    /// `[seqLo, seqHi, 0xAA, 0x55, payload..., crc32 big-endian]`.
    public mutating func classify(_ raw: [UInt8]) -> PacketDecision {
        // Index + sync bytes minimum; the codec enforces the full framing.
        guard raw.count >= 2 + 2 else { return .shortFrame }
        let index = UInt16(raw[0]) | (UInt16(raw[1]) << 8)
        if let previous = lastIndex {
            let delta = Int(index &- previous) & 0xFFFF
            if delta == 0 { return .duplicate }
            lastIndex = index
        } else {
            lastIndex = index
        }
        let body = Array(raw[2...])
        let (status, payload) = Policy.normalizePacket(body)
        guard status == 0 else { return .invalid(status: status) }
        return .accepted(index: index, payload: payload)
    }

    public mutating func reset() {
        lastIndex = nil
    }
}

public enum CaptureStage: String, Sendable, Hashable {
    case idle
    /// Open capture, no packets yet — "Waiting for audio" in the UI.
    case waiting
    /// First nonempty packet received — "Listening".
    case active
    /// Journal handoff performed; capture complete.
    case completed
    case failed
}

/// One batched, codec-validated packet held for the journal handoff.
public struct CaptureBatchPacket: Sendable, Hashable {
    public var index: UInt16
    public var payload: [UInt8]
    public var receivedAtMs: Int64

    public init(index: UInt16, payload: [UInt8], receivedAtMs: Int64) {
        self.index = index
        self.payload = payload
        self.receivedAtMs = receivedAtMs
    }
}

/// What a completed capture hands to the recording journal
/// (`RecordingJournalStoring`, Transport.swift).
public struct CaptureHandoff: Sendable {
    public var input: RecordingJournalInput
    public var packets: [CaptureBatchPacket]
    public var byteCount: Int
    public var startedAtMs: Int64?
    public var endedAtMs: Int64
}

/// State machine for one capture on one device connection. Lifecycle:
/// `open` (idle → waiting) → ingest accepted packets (waiting → active on
/// the first) → `handoff` (→ completed). A capture opened before the codec
/// + audio notifications are ready stays in `waiting` — first-audio
/// readiness keeps the BLE link and session intact while no packets have
/// arrived (docs/hardware-device-parity.md); silence is not a broken link.
public struct CaptureSessionMachine: Sendable {
    public private(set) var stage: CaptureStage = .idle
    public private(set) var deviceId: String = ""
    public private(set) var deviceName: String?
    public private(set) var codec: Int = 0
    public private(set) var packets: [CaptureBatchPacket] = []
    public private(set) var byteCount: Int = 0
    public private(set) var startedAtMs: Int64?

    private var assembler = AudioPacketAssembler()

    public init() {}

    public var chunkCount: Int { packets.count }
    public var isCapturing: Bool { stage == .waiting || stage == .active }

    /// Opens a capture. `codec` comes from the connection's readiness —
    /// connection success and recording require a codec plus confirmed
    /// audio notifications.
    public mutating func open(
        deviceId: String, deviceName: String?, codec: Int, nowMs: Int64
    ) {
        precondition(!deviceId.isEmpty, "capture requires a device identity")
        self.deviceId = deviceId
        self.deviceName = deviceName
        self.codec = codec
        self.startedAtMs = nowMs
        self.stage = .waiting
        self.packets = []
        self.byteCount = 0
        assembler.reset()
    }

    /// Feeds a raw audio notification through the assembler. Returns the
    /// packet index when the packet was accepted into the batch, else nil.
    @discardableResult
    public mutating func ingest(
        _ raw: [UInt8], receivedAtMs: Int64
    ) -> UInt16? {
        guard isCapturing else { return nil }
        switch assembler.classify(raw) {
        case .accepted(let index, let payload):
            guard !payload.isEmpty else { return nil }
            if stage == .waiting { stage = .active }
            packets.append(
                CaptureBatchPacket(
                    index: index, payload: payload, receivedAtMs: receivedAtMs
                )
            )
            byteCount += payload.count
            return index
        case .duplicate, .shortFrame, .invalid:
            return nil
        }
    }

    /// Marks the capture failed (link loss / retirement). Terminal.
    public mutating func fail() {
        if isCapturing { stage = .failed }
    }

    /// Performs the journal handoff: returns the batch for
    /// `RecordingJournalStoring.createRecordingJournal` + appends, and
    /// completes the capture. Nil when no audio was batched (the journal
    /// is only created for real audio) or the capture was not open.
    public mutating func handoff(nowMs: Int64) -> CaptureHandoff? {
        guard isCapturing else { return nil }
        guard !packets.isEmpty, let startedAtMs else {
            stage = .completed
            return nil
        }
        let batch = packets
        let bytes = byteCount
        let input = RecordingJournalInput(
            deviceId: deviceId, deviceName: deviceName, codec: codec
        )
        stage = .completed
        packets = []
        return CaptureHandoff(
            input: input, packets: batch, byteCount: bytes,
            startedAtMs: startedAtMs, endedAtMs: nowMs
        )
    }
}
