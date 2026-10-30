@preconcurrency import AVFoundation
import Opus

/// A whole recording of Omi opus frames → 16 kHz mono PCM16 bytes (to play or share it as a WAV,
/// Flutter `audio_player_utils.dart`). Frames that do not decode are skipped.
public enum OpusFileDecoder {
    public static func decode(_ frames: [Data]) -> Data? {
        guard let format = AVAudioFormat(opusPCMFormat: .int16, sampleRate: .opus16khz, channels: 1),
              let decoder = try? Opus.Decoder(format: format) else { return nil }
        var pcm = Data()
        for frame in frames {
            guard let buffer = try? decoder.decode(frame), let channel = buffer.int16ChannelData else { continue }
            pcm.append(Data(bytes: channel[0], count: Int(buffer.frameLength) * MemoryLayout<Int16>.size))
        }
        return pcm
    }
}

/// Live Omi opus frames → PCM16 bytes, one frame at a time with one decoder (opus keeps state
/// across frames): the wearable's audio for a custom speech-to-text provider.
public final class OpusPCM16Decoder: @unchecked Sendable {
    private let decoder: Opus.Decoder

    public init() throws {
        guard let format = AVAudioFormat(opusPCMFormat: .int16, sampleRate: .opus16khz, channels: 1) else {
            throw PhoneMicCapture.CaptureError.converterUnavailable
        }
        decoder = try Opus.Decoder(format: format)
    }

    /// Nil for a frame that does not decode.
    public func decode(_ packet: Data) -> Data? {
        guard let buffer = try? decoder.decode(packet), let channel = buffer.int16ChannelData else { return nil }
        return Data(bytes: channel[0], count: Int(buffer.frameLength) * MemoryLayout<Int16>.size)
    }
}
