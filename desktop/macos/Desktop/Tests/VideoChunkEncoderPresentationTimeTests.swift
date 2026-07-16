import XCTest

@testable import Omi_Computer

/// Regression coverage for the frame presentation-timestamp calculation in
/// `VideoChunkEncoder`. `AVAssetWriterInputPixelBufferAdaptor.append` requires
/// strictly increasing presentation timestamps; a stale `- 1` offset once made
/// frame 0 and frame 1 both resolve to PTS 0, so every chunk's second frame was
/// rejected and no video was ever persisted. These tests pin the contract that
/// the PTS is a strictly increasing function of the (post-increment-deferred)
/// frame offset that `addFrame` passes in.
final class VideoChunkEncoderPresentationTimeTests: XCTestCase {
  func testConsecutiveFrameOffsetsProduceStrictlyIncreasingTimestamps() {
    // frameRate for the default 3s capture interval is 1/3 fps; use a couple of
    // representative rates so the monotonicity holds regardless of cadence.
    for frameRate in [1.0 / 3.0, 0.5, 1.0, 2.0] {
      var previous = -Double.infinity
      for offset in 0..<10 {
        let pts = VideoChunkEncoder.framePresentationSeconds(frameOffset: offset, frameRate: frameRate)
        XCTAssertGreaterThan(
          pts, previous,
          "PTS must strictly increase (frameRate=\(frameRate), offset=\(offset))"
        )
        previous = pts
      }
    }
  }

  func testFirstTwoFramesDoNotCollideAtZero() {
    // The exact regression: frame 0 and frame 1 must not share PTS 0.
    let frameRate = 1.0 / 3.0
    let pts0 = VideoChunkEncoder.framePresentationSeconds(frameOffset: 0, frameRate: frameRate)
    let pts1 = VideoChunkEncoder.framePresentationSeconds(frameOffset: 1, frameRate: frameRate)
    XCTAssertEqual(pts0, 0.0, accuracy: 1e-9)
    XCTAssertNotEqual(pts1, pts0)
    XCTAssertGreaterThan(pts1, pts0)
  }

  func testOffsetMapsToItsOwnTimeSlot() {
    // Frame N sits at N / frameRate seconds — matching the real encoded sample index.
    let frameRate = 2.0
    for offset in 0..<5 {
      let pts = VideoChunkEncoder.framePresentationSeconds(frameOffset: offset, frameRate: frameRate)
      XCTAssertEqual(pts, Double(offset) / frameRate, accuracy: 1e-9)
    }
  }
}
