import AVFoundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for the sample-rate conversion capacity math in the real-time
/// audio IOProc/tap callbacks.
///
/// Both capture services computed `AVAudioFrameCount(ceil(frameCount * target / source))`
/// inline. When the source rate was 0 — a device reporting no rate at start, or
/// `stopCapture` zeroing the shared rate mid-callback on the lock-free `@unchecked
/// Sendable` service — the division yields `.infinity`, and `AVAudioFrameCount(.infinity)`
/// traps the process ("Double value cannot be converted to UInt32 because it is either
/// infinite or NaN"). The extracted helper returns 0 for that case so the callback bails
/// out instead of crashing.
final class AudioCaptureResampleCapacityTests: XCTestCase {
  func testMicZeroSourceRateReturnsZeroInsteadOfTrapping() {
    XCTAssertEqual(
      AudioCaptureService.resampledFrameCapacity(
        frameCount: 480, sourceSampleRate: 0, targetSampleRate: 16000),
      0)
  }

  @available(macOS 14.4, *)
  func testSystemAudioZeroSourceRateReturnsZeroInsteadOfTrapping() {
    XCTAssertEqual(
      SystemAudioCaptureService.resampledFrameCapacity(
        frameCount: 512, sourceSampleRate: 0, targetSampleRate: 16000),
      0)
    // 44.1kHz -> 16kHz rounds up (ceil) to avoid a short output buffer.
    XCTAssertEqual(
      SystemAudioCaptureService.resampledFrameCapacity(
        frameCount: 441, sourceSampleRate: 44100, targetSampleRate: 16000),
      160)
  }

  func testZeroFrameCountOrTargetReturnsZero() {
    XCTAssertEqual(
      AudioCaptureService.resampledFrameCapacity(
        frameCount: 0, sourceSampleRate: 48000, targetSampleRate: 16000),
      0)
    XCTAssertEqual(
      AudioCaptureService.resampledFrameCapacity(
        frameCount: 480, sourceSampleRate: 48000, targetSampleRate: 0),
      0)
  }

  func testDownsampleAndUpsampleRoundUp() {
    // 48kHz -> 16kHz: 480 frames -> 160.
    XCTAssertEqual(
      AudioCaptureService.resampledFrameCapacity(
        frameCount: 480, sourceSampleRate: 48000, targetSampleRate: 16000),
      160)
    // Upsample 8kHz -> 16kHz doubles the frames.
    XCTAssertEqual(
      AudioCaptureService.resampledFrameCapacity(
        frameCount: 100, sourceSampleRate: 8000, targetSampleRate: 16000),
      200)
  }
}
