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

  // MARK: - Following a stream

  func testTheFirstFollowRequestRunsImmediately() {
    XCTAssertEqual(
      ChatScrollFollowThrottle.decide(now: 100, lastRun: nil, hasQueuedRun: false),
      .now
    )
  }

  /// The defect this replaced: the provider flushes streamed text every 35 ms,
  /// and a trailing debounce cancelled its pending scroll on each flush, so a
  /// continuous stream never scrolled at all. A throttle must keep answering
  /// `.alreadyScheduled` — never "cancel and start the window again".
  func testAStreamFasterThanTheWindowStillGetsExactlyOneQueuedFollow() {
    let flushInterval: TimeInterval = 0.035
    var lastRun: TimeInterval? = 100
    var hasQueuedRun = false
    var queuedRuns = 0

    for flush in 1...10 {
      let now = 100 + Double(flush) * flushInterval
      switch ChatScrollFollowThrottle.decide(now: now, lastRun: lastRun, hasQueuedRun: hasQueuedRun) {
      case .now:
        lastRun = now
      case .schedule(let after):
        queuedRuns += 1
        hasQueuedRun = true
        XCTAssertEqual(after, ChatScrollFollowThrottle.interval - (now - 100), accuracy: 0.0001)
      case .alreadyScheduled:
        continue
      }
    }

    XCTAssertEqual(
      queuedRuns, 1,
      "a burst inside one window must queue one follow, not re-arm the window on every token")
  }

  func testAFollowRunsAgainOnceTheWindowHasElapsed() {
    XCTAssertEqual(
      ChatScrollFollowThrottle.decide(now: 100.2, lastRun: 100, hasQueuedRun: false),
      .now
    )
    guard
      case .schedule(let after) = ChatScrollFollowThrottle.decide(
        now: 100.04, lastRun: 100, hasQueuedRun: false)
    else {
      return XCTFail("a request inside the window must queue one follow")
    }
    XCTAssertEqual(after, ChatScrollFollowThrottle.interval - 0.04, accuracy: 0.0001)
  }

  /// A clock that does not advance must not park the transcript in a window that
  /// never expires — the failure mode is a transcript that silently stops
  /// following for the rest of its life.
  func testANonAdvancingClockStillFollows() {
    XCTAssertEqual(
      ChatScrollFollowThrottle.decide(now: 100, lastRun: 200, hasQueuedRun: false),
      .now
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

/// Whether viewport movement observed during a press is the reader's doing.
final class ChatPressPromotionPolicyTests: XCTestCase {
  private let epsilon: CGFloat = 1

  func testMovementNobodyClaimedBelongsToTheReader() {
    XCTAssertEqual(
      ChatPressPromotionPolicy.classify(
        movement: 40, epsilon: epsilon, now: 100, lastProgrammaticScrollAt: nil),
      .promotesPress,
      "with no follow-scroll to account for it, a moved viewport is the reader's doing")
  }

  func testTheTranscriptsOwnFollowScrollDoesNotClaimTheViewportForTheReader() {
    XCTAssertEqual(
      ChatPressPromotionPolicy.classify(
        movement: 40, epsilon: epsilon, now: 100.05, lastProgrammaticScrollAt: 100),
      .rebaselines,
      "a streamed answer re-reaching the live edge under an open press is not a drag")
  }

  func testMovementLongAfterTheLastFollowScrollIsStillTheReaders() {
    XCTAssertEqual(
      ChatPressPromotionPolicy.classify(
        movement: 40,
        epsilon: epsilon,
        now: 100 + ChatPressPromotionPolicy.programmaticScrollGrace + 0.01,
        lastProgrammaticScrollAt: 100),
      .promotesPress,
      "the grace window covers one runloop hop, not the rest of the press")
  }

  func testAStationaryViewportMeansNothingEitherWay() {
    XCTAssertEqual(
      ChatPressPromotionPolicy.classify(
        movement: 0.4, epsilon: epsilon, now: 100, lastProgrammaticScrollAt: nil),
      .ignores,
      "a click that moved nothing is still just a click")
  }

  func testABackwardsClockCannotDiscountReaderMovementForever() {
    XCTAssertEqual(
      ChatPressPromotionPolicy.classify(
        movement: 40, epsilon: epsilon, now: 99, lastProgrammaticScrollAt: 100),
      .promotesPress,
      "a clock that went backwards must not leave the reader unable to take the viewport")
  }

  func testTheSignalStartsWithNothingToAccountFor() {
    let signal = ChatProgrammaticScrollSignal()
    XCTAssertNil(signal.lastScrollAt)
    signal.markProgrammaticScroll(at: 42)
    XCTAssertEqual(signal.lastScrollAt, 42)
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
    NonintrusiveTestWindow.orderIn(window)
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
    var userScrollEnds = 0
    var settledAtBottom = 0
    let coordinator = UserScrollDetector.Coordinator(
      onUserScroll: { userScrollStarts += 1 },
      onUserScrollEnded: { userScrollEnds += 1 },
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
    XCTAssertEqual(userScrollEnds, 0, "reader ownership must remain active until AppKit ends live scroll")
    NotificationCenter.default.post(
      name: NSScrollView.didEndLiveScrollNotification,
      object: scrollView
    )
    drainMainQueue()

    XCTAssertEqual(userScrollStarts, 1, "native live scroll must immediately give the reader ownership")
    XCTAssertEqual(userScrollEnds, 1, "native live-scroll completion must release reader ownership")
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
