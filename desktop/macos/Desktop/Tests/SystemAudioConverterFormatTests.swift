import AVFoundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for the system-audio converter input format.
///
/// `handleAudioInput` down-mixes stereo source frames into a single channel and never
/// fills a second channel, so the converter input format MUST be mono. Declaring the
/// source channel count (e.g. 2) instead made the converter run its own stereo→mono
/// downmix against the unwritten channel 1, averaging real audio against silence and
/// attenuating all system audio fed to transcription by ~6 dB. This test pins the mono
/// contract at the production format factory, independent of any source channel count.
final class SystemAudioConverterFormatTests: XCTestCase {
    @available(macOS 14.4, *)
    func testConverterInputFormatIsAlwaysMono() {
        for sampleRate in [16000.0, 44100.0, 48000.0] {
            let format = SystemAudioCaptureService.makeConverterInputFormat(sampleRate: sampleRate)
            XCTAssertNotNil(format, "format factory should succeed for \(sampleRate)Hz")
            XCTAssertEqual(format?.channelCount, 1, "input format must be mono (\(sampleRate)Hz)")
            XCTAssertEqual(format?.sampleRate, sampleRate)
            XCTAssertEqual(format?.commonFormat, .pcmFormatFloat32)
        }
    }
}
