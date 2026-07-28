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

  // MARK: - Frozen per-chunk rate (mid-chunk capture-rate change)

  /// `frameRate` is a live property of the battery state. When AC power is
  /// connected mid-chunk the capture interval shrinks 3x, raising the live rate.
  /// Because PTS = frameOffset / rate and frameOffset accumulates across the
  /// chunk, a raised rate makes a later frame's PTS fall below an already-appended
  /// sample's — AVAssetWriter rejects that, dropping frames and (past the failure
  /// threshold) discarding the whole chunk. Freezing the rate at chunk start keeps
  /// PTS strictly increasing regardless of live-rate changes.
  func testFrozenRateKeepsPTSMonotonicAcrossMidChunkRateChange() {
    let batteryRate = 1.0 / 9.0  // 9s interval on battery, frozen at chunk start
    let acRate = 1.0 / 3.0  // AC connected mid-chunk -> 3s interval (higher rate)

    var previous = -Double.infinity
    for offset in 0..<12 {
      // Live rate flips to AC at offset 4, but the chunk's frozen rate must win.
      let live = offset < 4 ? batteryRate : acRate
      let rate = VideoChunkEncoder.chunkPresentationFrameRate(frozen: batteryRate, live: live)
      let pts = VideoChunkEncoder.framePresentationSeconds(frameOffset: offset, frameRate: rate)
      XCTAssertGreaterThan(pts, previous, "frozen-rate PTS must stay strictly increasing at offset \(offset)")
      previous = pts
    }
  }

  /// Documents the exact pre-fix hazard: using the live rate, a mid-chunk rate
  /// increase inverts PTS (frame 4 at the AC rate lands before frame 3 at the
  /// battery rate) — which is why the rate must be frozen per chunk.
  func testLiveRateIncreaseInvertsPTSWhichFreezingPrevents() {
    let batteryRate = 1.0 / 9.0
    let acRate = 1.0 / 3.0
    let ptsBatteryOffset3 = VideoChunkEncoder.framePresentationSeconds(frameOffset: 3, frameRate: batteryRate)
    let ptsAcOffset4 = VideoChunkEncoder.framePresentationSeconds(frameOffset: 4, frameRate: acRate)
    XCTAssertLessThan(
      ptsAcOffset4, ptsBatteryOffset3,
      "live-rate PTS inverts across a rate increase — the defect freezing fixes")

    // With freezing, offset 4 correctly lands after offset 3.
    let frozen = VideoChunkEncoder.chunkPresentationFrameRate(frozen: batteryRate, live: acRate)
    XCTAssertGreaterThan(
      VideoChunkEncoder.framePresentationSeconds(frameOffset: 4, frameRate: frozen),
      ptsBatteryOffset3)
  }
}
