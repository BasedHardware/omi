@preconcurrency import AVFoundation
import Opus

/// Decodes the Omi wearable's opus frames (16 kHz mono, 20 ms) to PCM buffers, so the device's
/// audio can be transcribed on the iPhone. Same decoder as upstream `sdks/swift` (swift-opus).
public final class OpusFrameDecoder: @unchecked Sendable {
    private let decoder: Opus.Decoder
    private let floatFormat: AVAudioFormat
    private let converter: AVAudioConverter

    public init(sampleRate: Double = 16000) throws {
        guard let opusFormat = AVAudioFormat(opusPCMFormat: .int16, sampleRate: .opus16khz, channels: 1),
              let floatFormat = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1),
              let converter = AVAudioConverter(from: opusFormat, to: floatFormat)
        else {
            throw PhoneMicCapture.CaptureError.converterUnavailable
        }
        decoder = try Opus.Decoder(format: opusFormat)
        self.floatFormat = floatFormat
        self.converter = converter
    }

    /// One opus packet → a float PCM buffer (what Apple speech recognition prefers).
    public func decode(_ packet: Data) -> AVAudioPCMBuffer? {
        guard let int16 = try? decoder.decode(packet),
              let output = AVAudioPCMBuffer(pcmFormat: floatFormat, frameCapacity: int16.frameLength) else { return nil }
        do {
            try converter.convert(to: output, from: int16)
        } catch {
            return nil
        }
        return output
    }
}
