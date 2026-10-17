@preconcurrency import AVFoundation
@testable import OmiAudio
import Opus
import Testing

struct OpusFrameDecoderTests {
    /// One 20 ms frame like the Omi firmware sends (16 kHz mono, 320 samples) survives a round trip.
    @Test func decodesAnOmiSizedOpusFrame() throws {
        let format = try #require(AVAudioFormat(opusPCMFormat: .int16, sampleRate: .opus16khz, channels: 1))
        let pcm = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 320))
        pcm.frameLength = 320
        let samples = try #require(pcm.int16ChannelData?[0])
        for index in 0 ..< 320 {
            samples[index] = Int16(8000 * sin(Double(index) * 2 * .pi * 440 / 16000))
        }
        let encoder = try Opus.Encoder(format: format)
        var packet = Data(count: 1500)
        let size = try encoder.encode(pcm, to: &packet)
        packet = packet.prefix(size)
        #expect(size > 0 && size <= 160)

        let decoded = try #require(try OpusFrameDecoder().decode(packet))
        #expect(decoded.frameLength == 320)
        #expect(decoded.format.commonFormat == .pcmFormatFloat32)
    }
}
