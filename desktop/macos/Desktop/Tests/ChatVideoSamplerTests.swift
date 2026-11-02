import XCTest

@testable import Omi_Computer

/// The desktop sampler must request the same candidate set the backend would sample itself
/// (backend/utils/media/video_frames.py): at most 48 frames, at most 4 per second.
final class ChatVideoSamplerTests: XCTestCase {
  func testShortClipSamplesAboutFourPerSecondToTheEnd() {
    XCTAssertEqual(ChatVideoSampler.sampleTimes(duration: 2), [0, 0.28, 0.56, 0.84, 1.11, 1.39, 1.67, 1.95])
  }

  func testSamplesNeverCloserThanAQuarterSecond() {
    for duration in [0.31, 1.01, 1.3, 2.0, 11.99, 12.06, 30.0] {
      let times = ChatVideoSampler.sampleTimes(duration: duration)
      for (a, b) in zip(times, times.dropFirst()) {
        XCTAssertGreaterThanOrEqual(b - a, 0.24, "\(duration)")  // rounding to 0.01
      }
      XCTAssertEqual(times.last ?? 0, max(0, duration - 0.05), accuracy: 0.01, "\(duration)")
    }
    XCTAssertEqual(ChatVideoSampler.sampleTimes(duration: 1.01).count, 4)
  }

  func testLongClipCapsAtFortyEightFramesCoveringTheEnd() {
    let times = ChatVideoSampler.sampleTimes(duration: 600)
    XCTAssertEqual(times.count, 48)
    XCTAssertEqual(times.first, 0)
    XCTAssertEqual(times[1], 12.77, accuracy: 0.01)
    XCTAssertEqual(times.last ?? 0, 599.95, accuracy: 0.01)
  }

  func testUnknownDurationStillAsksForTheFirstFrame() {
    XCTAssertEqual(ChatVideoSampler.sampleTimes(duration: 0), [0])
    XCTAssertEqual(ChatVideoSampler.sampleTimes(duration: .nan), [0])
  }

  func testPickedMoviesAreVideoAttachments() {
    let movie = ChatAttachment.from(url: URL(fileURLWithPath: "/tmp/clip.MOV"))
    XCTAssertEqual(movie?.mimeType, "video/quicktime")
    XCTAssertEqual(movie?.isVideo, true)
    XCTAssertNil(movie?.data)
    XCTAssertEqual(ChatAttachment.from(url: URL(fileURLWithPath: "/tmp/clip.mp4"))?.isVideo, true)
    XCTAssertEqual(ChatAttachment.from(url: URL(fileURLWithPath: "/tmp/photo.png"))?.isVideo, false)
  }

  /// macOS 14 sends 16 kHz mono PCM as WAV; the backend decoder reads it like any voice note.
  func testWavHeaderDescribesSixteenKilohertzMonoPCM() {
    let header = ChatVideoSampler.wavHeader(pcmBytes: 32_000)
    XCTAssertEqual(header.count, 44)
    XCTAssertEqual(String(decoding: header.prefix(4), as: UTF8.self), "RIFF")
    XCTAssertEqual(String(decoding: header[8..<16], as: UTF8.self), "WAVEfmt ")
    func u32(_ offset: Int) -> UInt32 {
      header[offset..<offset + 4].enumerated().reduce(0) { $0 | UInt32($1.element) << (8 * UInt32($1.offset)) }
    }
    XCTAssertEqual(u32(4), 36 + 32_000)
    XCTAssertEqual(u32(24), 16_000)
    XCTAssertEqual(u32(28), 32_000)
    XCTAssertEqual(u32(40), 32_000)
  }
}
