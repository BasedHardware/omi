import Foundation
import OpusKit

/// Native opus encoder for batch (transcribe-later) capture. Takes the PCM16
/// little-endian mono @16kHz chunks that `PhoneMicConverterPipeline` emits and
/// produces exact 20ms opus packets, one length-prefixed frame per packet — the
/// same on-disk shape (`opus_fs320`, 50 packets/sec) the BLE batch writers use.
///
/// One instance per batch session: created at batch bring-up and kept alive
/// across file rotations *and* engine rebuilds (interruption/route/media-reset),
/// so the resampler-fed byte stream is encoded contiguously. The backend decodes
/// every file with a fresh decoder, so mid-stream file boundaries are harmless —
/// this matches how Limitless pendant files are produced.
///
/// Must only be used from a single serial queue (the controller's audio queue).
/// libopus's encoder state is stateful and not thread-safe, and the leftover
/// sub-frame buffer below is plain (unlocked) state.
final class PhoneMicOpusEncoder {
    /// 320 samples = 20ms @ 16kHz; 640 bytes as PCM16 mono. opus requires an exact
    /// frame size, so partial chunks are buffered until a whole frame is available.
    private static let frameSamples: Int32 = 320
    private static let frameBytes = Int(frameSamples) * MemoryLayout<Int16>.size
    /// A 20ms VOIP-bitrate packet is well under 1KB; 4000 is opus's recommended
    /// safe ceiling and never truncates.
    private static let maxPacketBytes = 4000
    private static let sampleRate: Int32 = 16000
    private static let bitrate: Int32 = 32000

    /// libopus's OpusEncoder is an opaque C struct, so its pointer imports as
    /// OpaquePointer.
    private let encoder: OpaquePointer
    /// Sub-frame remainder carried between encode() calls until it completes a
    /// whole 320-sample frame.
    private var carry = Data()

    init?() {
        var err: Int32 = OPUS_OK
        guard let enc = opus_encoder_create(Self.sampleRate, 1, OPUS_APPLICATION_VOIP, &err), err == OPUS_OK else {
            return nil
        }
        encoder = enc
        // opus_encoder_ctl is a C variadic function, which Swift cannot call at all
        // (not merely the OPUS_SET_BITRATE macro). The non-variadic C shim in
        // PhoneMicOpusShim.{h,m} performs the OPUS_SET_BITRATE ctl.
        _ = omi_opus_encoder_set_bitrate(UnsafeMutableRawPointer(enc), Self.bitrate)
    }

    deinit {
        opus_encoder_destroy(encoder)
    }

    /// Encode all whole 320-sample frames available once `pcm` is appended to the
    /// carry, returning one opus packet per frame. Any sub-frame tail stays buffered.
    func encode(_ pcm: Data) -> [Data] {
        carry.append(pcm)
        var packets: [Data] = []
        while carry.count >= Self.frameBytes {
            let frame = Data(carry.prefix(Self.frameBytes))
            carry.removeFirst(Self.frameBytes)
            if let packet = encodeFrame(frame) {
                packets.append(packet)
            }
        }
        return packets
    }

    /// Drop the buffered sub-frame remainder. Called on every engine teardown so
    /// pre- and post-interruption audio is never spliced across one opus frame.
    func discardPartial() {
        carry.removeAll(keepingCapacity: true)
    }

    private func encodeFrame(_ frame: Data) -> Data? {
        var out = Data(count: Self.maxPacketBytes)
        let written: Int32 = frame.withUnsafeBytes { (raw: UnsafeRawBufferPointer) -> Int32 in
            guard let pcm = raw.bindMemory(to: Int16.self).baseAddress else { return -1 }
            return out.withUnsafeMutableBytes { (rawOut: UnsafeMutableRawBufferPointer) -> Int32 in
                guard let dst = rawOut.bindMemory(to: UInt8.self).baseAddress else { return -1 }
                return opus_encode(encoder, pcm, Self.frameSamples, dst, Int32(Self.maxPacketBytes))
            }
        }
        guard written > 0 else { return nil }
        return out.subdata(in: 0 ..< Int(written))
    }
}
