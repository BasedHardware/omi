import XCTest

@testable import Omi_Computer

/// The desktop sampler must request the same candidate set the backend would sample itself
/// (backend/utils/media/video_frames.py): at most 48 frames, at most 4 per second.
final class ChatVideoSamplerTests: XCTestCase {
  func testShortClipSamplesFourPerSecond() {
    XCTAssertEqual(ChatVideoSampler.sampleTimes(duration: 2), [0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 1.75])
  }

  func testLongClipCapsAtFortyEightEvenlySpacedFrames() {
    let times = ChatVideoSampler.sampleTimes(duration: 600)
    XCTAssertEqual(times.count, 48)
    XCTAssertEqual(times.first, 0)
    XCTAssertEqual(times[1], 12.5, accuracy: 0.01)
    XCTAssertLessThan(times.last ?? 600, 600)
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
}
