import CoreGraphics
import XCTest

@testable import Omi_Computer

/// The frame sink's retarget protocol is the privacy boundary of the persistent-stream
/// engine. `SCContentFilter(desktopIndependentWindow:)` keeps the OS enforcing "one
/// window at a time", but the stream does not switch windows atomically: between the
/// call to `updateContentFilter` and its completion, ScreenCaptureKit keeps delivering
/// the PREVIOUS window's pixels. If the sink is already tagging frames with the new
/// window ID at that point, a caller asking for window B gets a screenshot of window A —
/// which may be a Rewind-excluded app, a filtered browser window, or anything else the
/// user switched away from. These tests pin the drop-during-retarget rule.
@available(macOS 14.0, *)
final class WindowCaptureFrameSinkTests: XCTestCase {
  private func makeImage(width: Int = 4, height: Int = 4) throws -> CGImage {
    let context = try XCTUnwrap(
      CGContext(
        data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue
          | CGBitmapInfo.byteOrder32Little.rawValue))
    return try XCTUnwrap(context.makeImage())
  }

  /// Baseline: a frame delivered for the accepted window is served, including from the
  /// cache (a static window legitimately stops producing frames).
  func testAcceptedFrameIsServedForItsWindow() async throws {
    let sink = CaptureFrameSink()
    sink.endRetarget(windowID: 42)
    sink.deliver(try makeImage())
    let frame = await sink.nextFrame(windowID: 42, timeoutNs: 50_000_000)
    XCTAssertNotNil(frame)
  }

  /// The core privacy rule: while a retarget is in flight the sink accepts NOTHING, so
  /// old-window pixels arriving mid-switch cannot be relabelled as the new window's.
  func testFrameDeliveredDuringRetargetIsDroppedNotRelabelled() async throws {
    let sink = CaptureFrameSink()
    sink.endRetarget(windowID: 42)
    sink.deliver(try makeImage())

    sink.beginRetarget()
    // This is a frame the old filter produced; the engine has not yet learned the new
    // filter is live. It must be discarded, not cached against window 43.
    sink.deliver(try makeImage())

    sink.endRetarget(windowID: 43)
    let frame = await sink.nextFrame(windowID: 43, timeoutNs: 50_000_000)
    XCTAssertNil(frame, "a frame produced before the filter change must never satisfy the new target")
  }

  /// The previous window's cached frame must not survive a retarget either.
  func testCachedFrameIsDroppedOnRetarget() async throws {
    let sink = CaptureFrameSink()
    sink.endRetarget(windowID: 42)
    sink.deliver(try makeImage())
    sink.beginRetarget()
    sink.endRetarget(windowID: 42)  // same window, e.g. a resize
    let frame = await sink.nextFrame(windowID: 42, timeoutNs: 50_000_000)
    XCTAssertNil(frame, "the pre-reconfiguration frame has the wrong dimensions and must be dropped")
  }

  /// A waiter blocked on the old target must be released with nil rather than left to
  /// receive whatever the new target produces.
  func testWaiterFromPreviousTargetIsReleasedEmpty() async throws {
    let sink = CaptureFrameSink()
    sink.endRetarget(windowID: 42)
    async let pending = sink.nextFrame(windowID: 42, timeoutNs: 5_000_000_000)
    // Yield until the waiter has actually parked. Sleeping a fixed interval instead
    // would assert against a race: on a loaded machine the retarget can land before
    // the continuation registers, and the test would pass for the wrong reason.
    while !sink.hasParkedWaiter {
      await Task.yield()
    }
    sink.beginRetarget()
    let frame = await pending
    XCTAssertNil(frame)
  }

  /// A detached sink belongs to a stream we are tearing down. It must go inert: no
  /// frames, and no stop error that could be mistaken for the NEXT stream's failure.
  func testDetachedSinkGoesInert() async throws {
    let sink = CaptureFrameSink()
    sink.endRetarget(windowID: 42)
    sink.deliver(try makeImage())
    sink.detach()
    XCTAssertNil(sink.takeStopError())
    // Post-detach traffic from the departing stream is ignored, including a retarget
    // the engine could otherwise issue against a sink it no longer owns.
    sink.endRetarget(windowID: 42)
    sink.deliver(try makeImage())
    let frame = await sink.nextFrame(windowID: 42, timeoutNs: 50_000_000)
    XCTAssertNil(frame)
  }
}
