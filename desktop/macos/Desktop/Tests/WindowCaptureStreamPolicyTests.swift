import CoreGraphics
import XCTest

@testable import Omi_Computer

/// The persistent-stream contract: `startCapture` is the only action that pays a TCC
/// authorization, so the policy must reuse or retarget the live stream in every case
/// where one exists. If any of these degrade to `.startStream`, the per-frame
/// authorization sampling — the root of the consent-re-prompt defect — comes back.
final class WindowCaptureStreamPolicyTests: XCTestCase {
  private let size = CGSize(width: 1710, height: 1072)

  func testNoRunningStreamStarts() {
    XCTAssertEqual(
      WindowCaptureStreamPolicy.action(
        runningWindowID: nil, runningConfigSize: nil,
        requestedWindowID: 42, requestedConfigSize: size),
      .startStream
    )
  }

  func testSameWindowSameSizeReuses() {
    XCTAssertEqual(
      WindowCaptureStreamPolicy.action(
        runningWindowID: 42, runningConfigSize: size,
        requestedWindowID: 42, requestedConfigSize: size),
      .reuseStream
    )
  }

  /// The frontmost window changes constantly (every app switch); each change must ride
  /// `updateContentFilter` on the live stream, never a new session.
  func testWindowSwitchUpdatesFilterInsteadOfRestarting() {
    XCTAssertEqual(
      WindowCaptureStreamPolicy.action(
        runningWindowID: 42, runningConfigSize: size,
        requestedWindowID: 43, requestedConfigSize: size),
      .updateFilter
    )
  }

  func testResizeOfSameWindowOnlyReconfigures() {
    XCTAssertEqual(
      WindowCaptureStreamPolicy.action(
        runningWindowID: 42, runningConfigSize: size,
        requestedWindowID: 42, requestedConfigSize: CGSize(width: 800, height: 600)),
      .updateConfiguration
    )
  }

  // MARK: - Idle teardown

  /// A live stream keeps the OS screen-recording indicator on; it must not outlive
  /// actual capture requests, and it must not be torn down while requests still flow
  /// (each rebuild costs an authorization sample).
  func testIdleTeardownFiresOnlyAfterTimeout() {
    let now = Date()
    XCTAssertFalse(
      WindowCaptureStreamPolicy.shouldSuspendForIdle(
        lastRequestAt: now.addingTimeInterval(-59), now: now, idleTimeout: 60))
    XCTAssertTrue(
      WindowCaptureStreamPolicy.shouldSuspendForIdle(
        lastRequestAt: now.addingTimeInterval(-60), now: now, idleTimeout: 60))
    XCTAssertTrue(
      WindowCaptureStreamPolicy.shouldSuspendForIdle(
        lastRequestAt: .distantPast, now: now, idleTimeout: 60))
  }
}
