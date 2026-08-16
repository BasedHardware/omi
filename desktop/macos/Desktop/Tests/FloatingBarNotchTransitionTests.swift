import CoreGraphics
import XCTest

@testable import Omi_Computer

final class FloatingBarNotchTransitionTests: XCTestCase {
  func testHiddenFrameStartsAtNotchTopCenter() {
    let target = CGRect(x: 721, y: 1073, width: 268, height: 34)
    let hidden = FloatingBarNotchTransition.hiddenFrame(for: target)

    XCTAssertEqual(hidden.width, 2)
    XCTAssertEqual(hidden.height, 1)
    XCTAssertEqual(hidden.midX, target.midX, accuracy: 0.001)
    XCTAssertEqual(hidden.maxY, target.maxY, accuracy: 0.001)
  }

  func testGrowFramesKeepNotchAnchorPinned() {
    let target = CGRect(x: 721, y: 1073, width: 268, height: 34)
    let frames = FloatingBarNotchTransition.growFrames(targetFrame: target, steps: 29)

    XCTAssertEqual(frames.count, 29)
    for frame in frames {
      XCTAssertEqual(frame.midX, target.midX, accuracy: 0.001)
      XCTAssertEqual(frame.maxY, target.maxY, accuracy: 0.001)
      XCTAssertGreaterThanOrEqual(frame.width, 2)
      XCTAssertGreaterThanOrEqual(frame.height, 1)
      XCTAssertLessThanOrEqual(frame.width, target.width)
      XCTAssertLessThanOrEqual(frame.height, target.height)
    }
    XCTAssertEqual(frames.last?.origin.x ?? 0, target.origin.x, accuracy: 0.001)
    XCTAssertEqual(frames.last?.origin.y ?? 0, target.origin.y, accuracy: 0.001)
    XCTAssertEqual(frames.last?.width ?? 0, target.width, accuracy: 0.001)
    XCTAssertEqual(frames.last?.height ?? 0, target.height, accuracy: 0.001)
  }

  func testRevealProgressIsMonotonicAndClamped() {
    XCTAssertEqual(FloatingBarNotchTransition.revealProgress(-1), 0, accuracy: 0.001)
    XCTAssertEqual(FloatingBarNotchTransition.revealProgress(0), 0, accuracy: 0.001)
    XCTAssertEqual(FloatingBarNotchTransition.revealProgress(1), 1, accuracy: 0.001)
    XCTAssertEqual(FloatingBarNotchTransition.revealProgress(2), 1, accuracy: 0.001)

    var previous: CGFloat = 0
    for step in 1...29 {
      let progress = FloatingBarNotchTransition.revealProgress(CGFloat(step) / 29)
      XCTAssertGreaterThanOrEqual(progress, previous)
      previous = progress
    }
  }

  func testFixedWindowRevealKeepsFinalFrameAtNotchForEveryVisualScale() {
    let target = CGRect(x: 721, y: 1073, width: 268, height: 34)

    for step in 1...29 {
      let visible = FloatingBarNotchTransition.growFrame(
        targetFrame: target,
        progress: CGFloat(step) / 29
      )

      XCTAssertEqual(target.origin.x, 721, accuracy: 0.001)
      XCTAssertEqual(target.origin.y, 1073, accuracy: 0.001)
      XCTAssertEqual(visible.midX, target.midX, accuracy: 0.001)
      XCTAssertEqual(visible.maxY, target.maxY, accuracy: 0.001)
    }
  }

  func testLowerRightStartingFrameWouldSlideAndFailHarnessInvariant() {
    let target = CGRect(x: 721, y: 1073, width: 268, height: 34)
    let badStart = CGRect(x: 1400, y: 820, width: 40, height: 14)
    let progress: CGFloat = 0.35
    let badInterpolated = CGRect(
      x: badStart.origin.x + (target.origin.x - badStart.origin.x) * progress,
      y: badStart.origin.y + (target.origin.y - badStart.origin.y) * progress,
      width: badStart.width + (target.width - badStart.width) * progress,
      height: badStart.height + (target.height - badStart.height) * progress
    )
    let pinned = FloatingBarNotchTransition.growFrame(targetFrame: target, progress: progress)

    XCTAssertNotEqual(badInterpolated.midX, target.midX, accuracy: 1)
    XCTAssertNotEqual(badInterpolated.maxY, target.maxY, accuracy: 1)
    XCTAssertEqual(pinned.midX, target.midX, accuracy: 0.001)
    XCTAssertEqual(pinned.maxY, target.maxY, accuracy: 0.001)
  }
}
