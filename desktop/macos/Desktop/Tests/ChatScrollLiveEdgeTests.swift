import AppKit
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
    XCTAssertEqual(ChatScrollLiveEdge.initialRestoreSettlingDelays, [0.05, 0.2, 0.5])
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

@MainActor
final class ScrollPositionDetectorTests: XCTestCase {
  func testCoordinatorNormalizesANonFlippedDocumentBeforeClassifyingTheLiveEdge() {
    let scrollView = makeScrollView(isDocumentFlipped: false)
    let hostView = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 100))
    scrollView.documentView?.addSubview(hostView)

    var positions: [ChatScrollPosition] = []
    let coordinator = ScrollPositionDetector.Coordinator { positions.append($0) }
    coordinator.setupScrollObserver(for: hostView)
    drainMainRunLoop(mode: .default)
    XCTAssertEqual(positions.last?.scrollTop, 700)
    XCTAssertEqual(positions.last?.isAtBottom, true)

    scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: 700))
    NotificationCenter.default.post(
      name: NSView.boundsDidChangeNotification,
      object: scrollView.contentView
    )
    drainMainRunLoop(mode: .default)
    XCTAssertEqual(positions.last?.scrollTop, 0)
    XCTAssertEqual(positions.last?.isAtBottom, false)
  }

  func testCoordinatorRebindsWhenSwiftUIReplacesTheTranscriptScrollView() async {
    let firstScrollView = makeScrollView()
    let hostView = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 100))
    firstScrollView.documentView?.addSubview(hostView)

    var positions: [ChatScrollPosition] = []
    let replacementPositionExpectation = expectation(description: "replacement scroll position")
    let coordinator = ScrollPositionDetector.Coordinator { position in
      positions.append(position)
      if abs(position.scrollTop - 40) < 0.1 {
        replacementPositionExpectation.fulfill()
      }
    }
    coordinator.setupScrollObserver(for: hostView)

    let replacementScrollView = makeScrollView()
    hostView.removeFromSuperview()
    replacementScrollView.documentView?.addSubview(hostView)
    coordinator.setupScrollObserver(for: hostView)
    positions.removeAll()

    replacementScrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: 40))
    NotificationCenter.default.post(
      name: NSView.boundsDidChangeNotification,
      object: replacementScrollView.contentView
    )
    await fulfillment(of: [replacementPositionExpectation], timeout: 1)

    guard let observedScrollTop = positions.last?.scrollTop else {
      return XCTFail("Expected the replacement scroll view to report its position")
    }
    XCTAssertEqual(observedScrollTop, 40, accuracy: 0.1)
  }

  func testCoordinatorStopsReportingFromAStaleScrollViewAfterDetachment() async {
    let scrollView = makeScrollView()
    let hostView = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 100))
    scrollView.documentView?.addSubview(hostView)

    var positions: [ChatScrollPosition] = []
    let initialPosition = expectation(description: "initial scroll position")
    let coordinator = ScrollPositionDetector.Coordinator { position in
      positions.append(position)
      initialPosition.fulfill()
    }
    coordinator.setupScrollObserver(for: hostView)
    await fulfillment(of: [initialPosition], timeout: 1)
    positions.removeAll()

    // SwiftUI can call update while the representable is between the old and
    // replacement document hierarchies. No callback may escape from the old
    // clip view during that gap.
    hostView.removeFromSuperview()
    coordinator.setupScrollObserver(for: hostView)

    let stalePosition = expectation(description: "stale scroll position")
    stalePosition.isInverted = true
    scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: 40))
    NotificationCenter.default.post(
      name: NSView.boundsDidChangeNotification,
      object: scrollView.contentView
    )
    await fulfillment(of: [stalePosition], timeout: 0.1)

    XCTAssertTrue(positions.isEmpty, "detached detectors must not report the old scroll view")
  }

  func testCoordinatorDeliversTheLatestPositionFromARapidScrollBurst() async {
    let scrollView = makeScrollView()
    let hostView = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 100))
    scrollView.documentView?.addSubview(hostView)

    var positions: [ChatScrollPosition] = []
    let initialPosition = expectation(description: "initial scroll position")
    let finalPosition = expectation(description: "latest scroll position")
    var receivedInitialPosition = false
    let coordinator = ScrollPositionDetector.Coordinator { position in
      positions.append(position)
      if !receivedInitialPosition {
        receivedInitialPosition = true
        initialPosition.fulfill()
      } else if abs(position.scrollTop - 240) < 0.1 {
        finalPosition.fulfill()
      }
    }
    coordinator.setupScrollObserver(for: hostView)
    await fulfillment(of: [initialPosition], timeout: 1)
    positions.removeAll()

    // Post several live samples before the common-mode delivery turn runs.
    // The rail should receive one current snapshot, not a backlog of stale
    // intermediate callbacks.
    for scrollTop in [60.0, 120.0, 180.0, 240.0] {
      scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: scrollTop))
      NotificationCenter.default.post(
        name: NSView.boundsDidChangeNotification,
        object: scrollView.contentView
      )
    }
    await fulfillment(of: [finalPosition], timeout: 1)

    XCTAssertEqual(positions.count, 1)
    XCTAssertEqual(positions[0].scrollTop, 240, accuracy: 0.1)
  }

  func testCoordinatorDeliversMonotonicScrollBurstDuringEventTracking() {
    let scrollView = makeScrollView()
    let hostView = NSView(frame: NSRect(x: 0, y: 0, width: 300, height: 100))
    scrollView.documentView?.addSubview(hostView)

    var positions: [ChatScrollPosition] = []
    let coordinator = ScrollPositionDetector.Coordinator { position in
      positions.append(position)
    }
    coordinator.setupScrollObserver(for: hostView)
    drainMainRunLoop(mode: .default)
    positions.removeAll()

    // A fast upward gesture produces a monotonic sequence while AppKit is in
    // NSEventTrackingRunLoopMode. The latest sample must reach the timeline
    // before the gesture returns to the default mode.
    for scrollTop in Array(stride(from: 80.0, through: 640.0, by: 80.0)) + [700.0] {
      scrollView.contentView.setBoundsOrigin(NSPoint(x: 0, y: scrollTop))
      NotificationCenter.default.post(
        name: NSView.boundsDidChangeNotification,
        object: scrollView.contentView
      )
    }

    drainMainRunLoop(mode: RunLoop.Mode("NSEventTrackingRunLoopMode"))

    guard let finalPosition = positions.last else {
      return XCTFail("Expected the event-tracking scroll sample to be delivered")
    }
    XCTAssertEqual(finalPosition.scrollTop, 700, accuracy: 0.1)
  }

  private func makeScrollView(isDocumentFlipped: Bool = true) -> NSScrollView {
    let scrollView = NSScrollView(frame: NSRect(x: 0, y: 0, width: 300, height: 300))
    let frame = NSRect(x: 0, y: 0, width: 300, height: 1_000)
    let documentView: NSView =
      isDocumentFlipped
      ? FlippedScrollDocumentView(frame: frame)
      : NSView(frame: frame)
    scrollView.documentView = documentView
    return scrollView
  }

  private func drainMainRunLoop(mode: RunLoop.Mode) {
    // omi-test-quality: wall-clock-wait -- this drives the AppKit run-loop mode under test; the callback normally executes immediately.
    _ = RunLoop.main.run(mode: mode, before: Date().addingTimeInterval(0.1))
  }

}

private final class FlippedScrollDocumentView: NSView {
  override var isFlipped: Bool { true }
}
