import Foundation

// Capture session state machine: open capture → packet batching → journal
// handoff. The rules live in the shared C++ middleware (`omi_device`):
// sequence-index dedupe, stream-restart baselines, stage transitions, and
// codec validation through the 0xAA 0x55 + CRC32 codec — all mirroring the
// upstream native packet accounting in `app/ios/Runner/Ble/OmiBleManager.swift`
// (`recordAudioPacket`). This file only maps the C outcomes onto the Swift
// vocabulary OmiKit consumes; nothing here re-derives a rule.

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

/// Running packet assembly accounting for one device's audio stream.
/// A handle over the C++ `AudioPacketAssembler`; classify is single-owner.
public final class AudioPacketAssembler: @unchecked Sendable {
    private let handle: Int64

    public init() {
        handle = Policy.deviceAssemblerCreate()
    }

    deinit {
        Policy.deviceAssemblerDestroy(handle)
    }

    /// Clears the sequence baseline (used when a capture opens).
    public func reset() {
        Policy.deviceAssemblerReset(handle)
    }

    /// Classifies a raw audio characteristic value:
    /// `[seqLo, seqHi, 0xAA, 0x55, payload..., crc32 big-endian]`.
    public func classify(_ raw: [UInt8]) -> PacketDecision {
        let decision = Policy.deviceAssemblerClassify(handle, raw: raw)
        switch decision.kind {
        case 0: return .accepted(index: decision.index, payload: decision.payload)
        case 1: return .duplicate
        case 2: return .shortFrame
        default: return .invalid(status: decision.codecStatus)
        }
    }
}

/// State machine for one capture on one device connection. Lifecycle:
/// `open` (idle → waiting) → ingest accepted packets (waiting → active on
/// the first) → `handoff` (→ completed). A capture opened before the codec
/// + audio notifications are ready stays in `waiting` — first-audio
/// readiness keeps the BLE link and session intact while no packets have
/// arrived (docs/hardware-device-parity.md); silence is not a broken link.
/// A handle over the C++ `CaptureMachine`; single-owner per connection.
public final class CaptureSessionMachine: @unchecked Sendable {
    private let handle: Int64

    /// Identity of the open capture, mirrored from `open` for the journal
    /// handoff (the rules stay in C++; this is retained identity only).
    public private(set) var deviceId: String = ""
    public private(set) var deviceName: String?
    public private(set) var codec: Int = 0
    public private(set) var startedAtMs: Int64?

    public init() {
        handle = Policy.deviceCaptureCreate()
    }

    deinit {
        Policy.deviceCaptureDestroy(handle)
    }

    public var stage: CaptureStage {
        switch Policy.deviceCaptureStage(handle) {
        case 1: return .waiting
        case 2: return .active
        case 3: return .completed
        case 4: return .failed
        default: return .idle
        }
    }

    public var isCapturing: Bool { Policy.deviceCaptureIsCapturing(handle) }
    public var chunkCount: Int { Policy.deviceCaptureBatchCount(handle) }
    public var byteCount: Int { Policy.deviceCaptureBatchByteCount(handle) }

    /// Opens a capture. `codec` comes from the connection's readiness —
    /// connection success and recording require a codec plus confirmed
    /// audio notifications.
    public func open(
        deviceId: String, deviceName: String?, codec: Int, nowMs: Int64
    ) {
        precondition(!deviceId.isEmpty, "capture requires a device identity")
        guard Policy.deviceCaptureOpen(
            handle, deviceId: deviceId, deviceName: deviceName,
            codec: Int32(codec), nowMs: nowMs)
        else { return }
        self.deviceId = deviceId
        self.deviceName = deviceName
        self.codec = codec
        startedAtMs = nowMs
    }

    /// Feeds a raw audio notification through the C++ assembler. Returns the
    /// packet index when the packet was accepted into the batch, else nil.
    @discardableResult
    public func ingest(_ raw: [UInt8], receivedAtMs: Int64) -> UInt16? {
        let accepted = Policy.deviceCaptureIngest(
            handle, raw: raw, receivedAtMs: receivedAtMs)
        guard accepted >= 0 else { return nil }
        return UInt16(accepted)
    }

    /// Marks the capture failed (link loss / retirement). Terminal.
    public func fail() {
        Policy.deviceCaptureFail(handle)
    }

    /// Performs the journal handoff: returns the batch for
    /// `RecordingJournalStoring.createRecordingJournal` + appends, and
    /// completes the capture. Nil when no audio was batched (the journal
    /// is only created for real audio) or the capture was not open.
    public func handoff(nowMs: Int64) -> CaptureHandoff? {
        guard let handoff = Policy.deviceCaptureHandoff(handle, nowMs: nowMs)
        else { return nil }
        let input = RecordingJournalInput(
            deviceId: deviceId, deviceName: deviceName, codec: codec)
        let packets = handoff.packets.map {
            CaptureBatchPacket(
                index: $0.index, payload: $0.payload,
                receivedAtMs: $0.receivedAtMs)
        }
        return CaptureHandoff(
            input: input, packets: packets, byteCount: handoff.byteCount,
            startedAtMs: handoff.startedAtMs, endedAtMs: handoff.endedAtMs)
    }
}
