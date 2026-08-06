import AppKit
import ObjectiveC
import XCTest

@testable import Omi_Computer

final class ChatScrollLiveEdgeTests: XCTestCase {
  func testTopBasedScrollOffsetNormalizesFlippedAndNonFlippedDocuments() {
    XCTAssertEqual(
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: 700,
        viewportHeight: 300,
        documentHeight: 1_000,
        isDocumentFlipped: true
      ),
      700
    )
    XCTAssertEqual(
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: 0,
        viewportHeight: 300,
        documentHeight: 1_000,
        isDocumentFlipped: false
      ),
      700,
      "A non-flipped document's zero origin is its visual bottom"
    )
    XCTAssertEqual(
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: 700,
        viewportHeight: 300,
        documentHeight: 1_000,
        isDocumentFlipped: false
      ),
      0,
      "A non-flipped document's maximum origin is its visual top"
    )
  }

  func testTopBasedScrollOffsetClampsElasticOverscroll() {
    XCTAssertEqual(
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: -80,
        viewportHeight: 300,
        documentHeight: 1_000,
        isDocumentFlipped: true
      ),
      0
    )
    XCTAssertEqual(
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: -80,
        viewportHeight: 300,
        documentHeight: 1_000,
        isDocumentFlipped: false
      ),
      700
    )
  }

  func testReaderScrollAwayFromLiveEdgeIsNotTreatedAsFollowing() {
    XCTAssertFalse(
      ChatScrollLiveEdge.isAtBottom(visibleMaxY: 950, documentHeight: 1_000),
      "A reader who scrolls up by 50 points must not be pulled down by streaming output."
    )
  }

  func testExactLiveEdgeResumesFollowing() {
    XCTAssertTrue(ChatScrollLiveEdge.isAtBottom(visibleMaxY: 1_000, documentHeight: 1_000))
  }

  func testOnlySettledPhysicalScrollCanResumeFollowing() {
    XCTAssertFalse(
      ChatScrollLiveEdge.canResumeFollowing(
        source: .passivePosition,
        isAtBottom: true,
        userIsScrolling: false
      ),
      "A passive live-edge sample after a prompt jump must not resume following."
    )
    XCTAssertTrue(
      ChatScrollLiveEdge.canResumeFollowing(
        source: .settledUserScroll,
        isAtBottom: true,
        userIsScrolling: false
      )
    )
    XCTAssertFalse(
      ChatScrollLiveEdge.canResumeFollowing(
        source: .settledUserScroll,
        isAtBottom: true,
        userIsScrolling: true
      )
    )
    XCTAssertFalse(
      ChatScrollLiveEdge.canResumeFollowing(
        source: .settledUserScroll,
        isAtBottom: false,
        userIsScrolling: false
      )
    )
  }

  func testExplicitJumpSettlesAfterTheNextLayoutTurn() {
    XCTAssertEqual(ChatScrollLiveEdge.explicitJumpSettlingDelay, 0.05)
  }

  func testInitialRestoreSettlesAcrossMultipleLayoutTurns() {
    XCTAssertEqual(ChatScrollLiveEdge.initialRestoreSettlingDelays, [0.05, 0.2, 0.5, 1.0])
  }

  func testEveryPresentationStartsAFreshBottomPlacement() {
    XCTAssertEqual(
      ChatInitialRestoreState.atPresentationStart(previous: .completed),
      .waiting,
      "a replacement SwiftUI scroll view must not inherit an old completed placement"
    )
    XCTAssertEqual(ChatInitialRestoreState.atPresentationStart(previous: .userInterrupted), .waiting)
  }

  func testPendingInitialRestoreRetriesAfterTransientViewDisappearance() {
    XCTAssertEqual(
      ChatInitialRestoreState.afterDisappear(.pending),
      .waiting,
      "A launch transition may remove the transcript before its bottom placement settles."
    )
    XCTAssertEqual(
      ChatInitialRestoreState.afterDisappear(.completed),
      .completed,
      "A completed placement must not disturb the user's later scroll position."
    )
  }

  func testUserScrollWinsOverPendingInitialRestore() {
    XCTAssertEqual(
      ChatInitialRestoreState.afterUserInteraction(.pending),
      .userInterrupted,
      "Explicit reader input must cancel launch placement and preserve the viewport."
    )
    XCTAssertFalse(ChatInitialRestoreState.userInterrupted.canStart)
  }
}

/// AppKit-backed failure harness for chat scroll ownership. Unlike the
/// coordinate-only live-edge cases above, these tests drive the same native
/// live-scroll lifecycle emitted by a rapid trackpad/wheel gesture.
@MainActor
final class UserScrollDetectorTests: XCTestCase {
  func testRapidWheelBurstClaimsReaderOwnershipOnlyOncePerLiveGesture() {
    let (scrollView, hostView) = makeScrollViewAtBottom()
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 300, height: 300),
      styleMask: [.titled], backing: .buffered, defer: false)
    window.contentView = scrollView
    window.orderFrontRegardless()
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }

    var ownershipClaims = 0
    let coordinator = UserScrollDetector.Coordinator(
      onUserScroll: { ownershipClaims += 1 },
      onScrollSettledAtBottom: {}
    )
    coordinator.install(for: hostView)
    defer { coordinator.stop() }

    NotificationCenter.default.post(
      name: NSScrollView.willStartLiveScrollNotification,
      object: scrollView
    )
    for _ in 0..<40 {
      guard let event = makeWheelEvent(window: window, deltaY: 40) else {
        return XCTFail("Expected a synthetic wheel event")
      }
      NSApplication.shared.sendEvent(event)
    }

    XCTAssertEqual(
      ownershipClaims,
      1,
      "one physical gesture must not invalidate the SwiftUI transcript once per wheel delta"
    )
  }

  func testRapidLiveScrollHandsOwnershipToReaderAndDoesNotRearmAwayFromBottom() {
    let (scrollView, hostView) = makeScrollViewAtBottom()
    var userScrollStarts = 0
    var settledAtBottom = 0
    let coordinator = UserScrollDetector.Coordinator(
      onUserScroll: { userScrollStarts += 1 },
      onScrollSettledAtBottom: { settledAtBottom += 1 }
    )
    coordinator.install(for: hostView)

    NotificationCenter.default.post(
      name: NSScrollView.willStartLiveScrollNotification,
      object: scrollView
    )
    // A fast upward burst crosses most of the transcript before momentum ends.
    for scrollTop in [620.0, 400.0, 160.0] {
      scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: scrollTop))
    }
    NotificationCenter.default.post(
      name: NSScrollView.didEndLiveScrollNotification,
      object: scrollView
    )
    drainMainQueue()

    XCTAssertEqual(userScrollStarts, 1, "native live scroll must immediately give the reader ownership")
    XCTAssertEqual(
      settledAtBottom,
      0,
      "ending momentum in history must not re-arm live following or jump to the bottom"
    )
    coordinator.stop()
  }

  func testNewGestureCancelsAQueuedBottomSettlementFromThePreviousGesture() {
    let (scrollView, hostView) = makeScrollViewAtBottom()
    var settledAtBottom = 0
    let coordinator = UserScrollDetector.Coordinator(
      onUserScroll: {},
      onScrollSettledAtBottom: { settledAtBottom += 1 }
    )
    coordinator.install(for: hostView)

    NotificationCenter.default.post(
      name: NSScrollView.willStartLiveScrollNotification,
      object: scrollView
    )
    NotificationCenter.default.post(
      name: NSScrollView.didEndLiveScrollNotification,
      object: scrollView
    )
    // Before the queued terminal-position read runs, a new burst starts and
    // moves away. The stale bottom result must never reclaim ownership.
    NotificationCenter.default.post(
      name: NSScrollView.willStartLiveScrollNotification,
      object: scrollView
    )
    scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: 200))
    drainMainQueue()

    XCTAssertEqual(settledAtBottom, 0)
    coordinator.stop()
  }

  func testCompletedLiveScrollAtBottomCanResumeFollowing() {
    let (scrollView, hostView) = makeScrollViewAtBottom()
    var settledAtBottom = 0
    let coordinator = UserScrollDetector.Coordinator(
      onUserScroll: {},
      onScrollSettledAtBottom: { settledAtBottom += 1 }
    )
    coordinator.install(for: hostView)

    NotificationCenter.default.post(
      name: NSScrollView.willStartLiveScrollNotification,
      object: scrollView
    )
    NotificationCenter.default.post(
      name: NSScrollView.didEndLiveScrollNotification,
      object: scrollView
    )
    drainMainQueue()

    XCTAssertEqual(settledAtBottom, 1)
    coordinator.stop()
  }

  private func makeScrollViewAtBottom() -> (NSScrollView, NSView) {
    let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: 300, height: 300))
    let documentView = FlippedScrollDocumentView(
      frame: NSRect(x: 0, y: 0, width: 300, height: 1_000)
    )
    let hostView = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 1))
    documentView.addSubview(hostView)
    scrollView.documentView = documentView
    scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: 700))
    return (scrollView, hostView)
  }

  private func makeWheelEvent(window: NSWindow, deltaY: Int32) -> NSEvent? {
    guard
      let cgEvent = CGEvent(
        scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1,
        wheel1: deltaY, wheel2: 0, wheel3: 0),
      let event = NSEvent(cgEvent: cgEvent)
    else { return nil }
    InjectedScrollEvent.target = window
    InjectedScrollEvent.targetWindowNumber = window.windowNumber
    InjectedScrollEvent.locationInWindowOverride = NSPoint(x: 150, y: 150)
    object_setClass(event, InjectedScrollEvent.self)
    return event
  }

  private func drainMainQueue() {
    // omi-test-quality: wall-clock-wait -- drives the AppKit notification callback and its next-turn terminal bounds read.
    _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05))
  }
}

private final class FlippedScrollDocumentView: NSView {
  override var isFlipped: Bool { true }
}
