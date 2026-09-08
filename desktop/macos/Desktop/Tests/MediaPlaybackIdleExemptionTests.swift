import XCTest

@testable import Omi_Computer

final class MediaPlaybackIdleExemptionTests: XCTestCase {
  /// The regression this exists for: an hour of movie-watching (no HID input) must not
  /// read as "user away" while something is holding the display awake for them.
  func testMediaPlaybackPinsIdleToZero() {
    XCTAssertEqual(
      MediaPlaybackIdlePolicy.effectiveIdleSeconds(
        hidIdleSeconds: 3600, isDisplaySleepPrevented: true),
      0)
  }

  func testWithoutPlaybackHIDIdlePassesThrough() {
    XCTAssertEqual(
      MediaPlaybackIdlePolicy.effectiveIdleSeconds(
        hidIdleSeconds: 90, isDisplaySleepPrevented: false),
      90)
  }

  /// The gate-facing wrapper mirrors the pure policy and logs once per episode; its
  /// idle arithmetic must match the policy exactly.
  func testDetectorEffectiveIdleMatchesPolicy() {
    let playing = MediaPlaybackDetector(cacheTTL: 10) { true }
    XCTAssertEqual(playing.effectiveIdleSeconds(hidIdleSeconds: 3600, threshold: 60), 0)
    let silent = MediaPlaybackDetector(cacheTTL: 10) { false }
    XCTAssertEqual(silent.effectiveIdleSeconds(hidIdleSeconds: 90, threshold: 60), 90)
  }

  /// The capture loop polls every second; the IOKit assertion table must not be
  /// walked on every tick.
  func testDetectorCachesProbeWithinTTL() {
    var probeCalls = 0
    var playbackActive = true
    let detector = MediaPlaybackDetector(cacheTTL: 10) {
      probeCalls += 1
      return playbackActive
    }
    let t0 = Date(timeIntervalSince1970: 1_000_000)
    XCTAssertTrue(detector.isDisplaySleepPrevented(now: t0))
    XCTAssertTrue(detector.isDisplaySleepPrevented(now: t0.addingTimeInterval(5)))
    XCTAssertEqual(probeCalls, 1)
    // TTL elapsed and playback stopped: the next read re-probes and sees the change.
    playbackActive = false
    XCTAssertFalse(detector.isDisplaySleepPrevented(now: t0.addingTimeInterval(11)))
    XCTAssertEqual(probeCalls, 2)
  }
}
