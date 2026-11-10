import XCTest

@testable import Omi_Computer

final class CaptureStreamActivityTests: XCTestCase {
  private final class Clock: @unchecked Sendable {
    private let lock = NSLock()
    private var value: TimeInterval = 10
    func now() -> TimeInterval { lock.withLock { value } }
    func advance(_ seconds: TimeInterval) { lock.withLock { value += seconds } }
  }

  func testNoFramesAndEmptyChunksCannotCertifyAHealthyStream() {
    let activity = CaptureStreamActivity()
    XCTAssertFalse(activity.hasRecentFrames)
    activity.notePCM(byteCount: 0)
    activity.notePCM(byteCount: 1)
    XCTAssertFalse(activity.hasRecentFrames)
  }

  func testPCMIsLiveOnlyInsideMonotonicFreshnessWindow() {
    let clock = Clock()
    let activity = CaptureStreamActivity(now: { clock.now() })
    activity.notePCM(byteCount: 320)
    XCTAssertTrue(activity.hasRecentFrames)
    clock.advance(CaptureStreamActivity.freshnessWindow)
    XCTAssertTrue(activity.hasRecentFrames)
    clock.advance(0.001)
    XCTAssertFalse(activity.hasRecentFrames)
    activity.notePCM(byteCount: 320)
    XCTAssertTrue(activity.hasRecentFrames)
    activity.reset()
    XCTAssertFalse(activity.hasRecentFrames)
  }

  func testReplacementCannotInheritRetiredStreamLiveness() {
    let original = CaptureStreamActivity()
    original.notePCM(byteCount: 320)
    XCTAssertTrue(original.hasRecentFrames)
    XCTAssertFalse(CaptureStreamActivity().hasRecentFrames)
  }
}
