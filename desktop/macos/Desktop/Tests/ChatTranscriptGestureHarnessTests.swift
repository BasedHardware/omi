import AppKit
import ObjectiveC
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Reader-ownership harness for the real transcript.
///
/// The other scroll suites exercise the detector coordinators in isolation
/// against a hand-built `NSScrollView`. They therefore stay green while the
/// mounted transcript still moves a reader who owns the viewport, because the
/// thing that moves the reader is `ChatMessagesView`'s own `@State` and its
/// `ScrollViewReader` — neither of which those tests instantiate.
///
/// This harness mounts the real `ChatMessagesView` in an `NSHostingView`,
/// finds the `NSScrollView` SwiftUI actually built, and drives it with real
/// `NSEvent` scroll wheels dispatched through `NSApplication.sendEvent` — the
/// exact call that feeds `UserScrollDetector`'s local event monitor, carrying
/// the window identity and in-bounds location the production guards check.
///
/// Harness limitation, deliberately explicit: a test process is never the
/// active application, and SwiftUI's `ScrollView` does not apply synthetic
/// scroll deltas under that condition (a plain `NSScrollView` in the same
/// process does). The gesture therefore moves the clip view itself, in
/// lockstep with the events, the way AppKit would, and posts the same
/// `willStartLiveScroll` / `didEndLiveScroll` notifications AppKit emits.
/// What is real here is everything the regression lives in: the mounted view,
/// its state machine, the event-monitor path, the resulting bounds changes,
/// and the streaming/layout updates racing against them.
@MainActor
final class ChatTranscriptGestureHarnessTests: XCTestCase {

  func testTranscriptOpensAtTheLiveEdge() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }

    harness.settleInitialPlacement()

    XCTAssertTrue(
      harness.isAtBottom,
      "a newly presented transcript starts at the live edge "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))")
  }

  func testCompactHomeTranscriptOpensAtTheLiveEdge() throws {
    let harness = try makeHarness(messageCount: 120, transcriptWindowPolicy: .compactHome)
    defer { harness.tearDown() }

    harness.settleInitialPlacement()

    XCTAssertTrue(
      harness.isAtBottom,
      "the compact Home transcript must open at the newest mounted message "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))"
    )
  }

  /// **The compact window has to actually bound what gets mounted.**
  ///
  /// The transcript keeps its rows eagerly mounted on purpose, so the row count
  /// *is* the cost: at 400 messages the 500-row default builds 607 native views
  /// in 910 ms, against 84 in 114 ms compact — into a panel 460 pt tall. Home
  /// asks for the compact window for that reason, and this pins that asking for
  /// it still means something.
  func testTheCompactWindowMountsAFractionOfTheHistory() throws {
    let compact = try makeHarness(messageCount: 400, transcriptWindowPolicy: .compactHome)
    defer { compact.tearDown() }
    compact.settleInitialPlacement()
    let compactHeight = compact.documentHeight

    let standard = try makeHarness(messageCount: 400, transcriptWindowPolicy: .standard)
    defer { standard.tearDown() }
    standard.settleInitialPlacement()

    XCTAssertGreaterThan(compactHeight, 0, "precondition: the compact window mounted something")
    XCTAssertGreaterThan(
      standard.documentHeight, compactHeight * 3,
      "the compact window must mount a fraction of the transcript, not all of it "
        + "(compact \(compactHeight) pt vs standard \(standard.documentHeight) pt)")
    XCTAssertTrue(compact.isAtBottom, "and it must still open at the newest mounted message")
  }

  func testStreamingDoesNotPullAFastScrollingReaderBackToTheLiveEdge() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.performUpwardGesture(events: 30)
    let readerPosition = harness.scrollTop
    XCTAssertFalse(harness.isAtBottom, "precondition: the gesture left the live edge")

    for chunk in 0..<12 {
      harness.appendStreamingText(" streamed chunk \(chunk).")
      harness.pump(0.03)
    }
    harness.pump(0.7)

    XCTAssertEqual(
      harness.scrollTop, readerPosition, accuracy: 4,
      "streaming must not move a reader who owns the viewport")
  }

  /// **A streaming answer must stay in view, not be abandoned and then snapped
  /// back.**
  ///
  /// `ChatProvider` flushes streamed text every 35 ms
  /// (`ChatStreamingBuffer(flushInterval: 0.035)`). The follow scroll used to
  /// cancel and reschedule itself 80 ms out on every one of those flushes, so it
  /// never ran while the answer was arriving: measured here, the live edge ran
  /// 387 pt past a 600 pt viewport for the whole stream and only caught up once
  /// the tokens stopped. Drift is asserted **during** the stream for that
  /// reason — a check after the stream ends passes either way.
  func testStreamingKeepsAFollowingReaderAtTheLiveEdge() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()
    XCTAssertTrue(harness.isAtBottom, "precondition: the transcript opens at the live edge")

    var worstDrift: CGFloat = 0
    for chunk in 0..<40 {
      harness.appendStreamingText(" Streamed chunk \(chunk) with enough prose to grow the row. ")
      harness.pump(0.035)
      worstDrift = max(worstDrift, harness.maximumScrollTop - harness.scrollTop)
    }

    XCTAssertLessThan(
      worstDrift, 120,
      "a reader who never touched the viewport must keep the live edge in view while it streams "
        + "(drifted \(worstDrift) pt of a \(harness.viewportHeight) pt viewport)")
  }

  func testAnArrivingTurnDoesNotPullTheReaderBack() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.performUpwardGesture(events: 30)
    let readerPosition = harness.scrollTop

    harness.appendAssistantMessage()
    harness.pump(0.7)

    XCTAssertEqual(
      harness.scrollTop, readerPosition, accuracy: 4,
      "a newly arrived turn must not move a reader who owns the viewport")
  }

  /// `isSending` flipping under a surface with no local send token must not
  /// seize a viewport the reader is actively moving.
  func testSendStartingWhileTheReaderScrollsDoesNotSeizeTheViewport() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.performUpwardGesture(events: 30, endGesture: false)
    let readerPosition = harness.scrollTop

    harness.model.isSending = true
    harness.pump(0.7)

    XCTAssertEqual(
      harness.scrollTop, readerPosition, accuracy: 4,
      "a send starting mid-gesture must not pull the reader to the live edge")
  }

  /// Tearing the surface down and presenting it again is a *new* presentation
  /// of the chat, so requirement 1 applies to it: it opens at the live edge.
  /// This pins that boundary, so a future ownership change cannot quietly turn
  /// a deliberate re-open into a restored mid-history position.
  func testRePresentingTheTranscriptOpensAtTheLiveEdgeAgain() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.performUpwardGesture(events: 30)
    XCTAssertFalse(harness.isAtBottom, "precondition: the reader left the live edge")

    harness.togglePresentation()
    // CI can run slower across multiple SwiftUI layout turns. Wait until
    // the re-presented transcript has settled back onto the live edge.
    let deadline = Date().addingTimeInterval(2.0)
    while Date() < deadline && !harness.isAtBottom {
      harness.pump(0.05)
    }

    XCTAssertTrue(
      harness.isAtBottom,
      "a re-presented transcript starts at the live edge "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))")
  }

  /// The transcript must not cap its column to reserve a gutter. The prompt
  /// rail is an overlay on the trailing edge; rows reach the same edge the
  /// composer below them uses. Measured on the mounted transcript because the
  /// inset was only ever visible as painted pixels — the view's own frame was
  /// full width the whole time.
  func testTranscriptRowsReachTheContainerEdgeWithNoReservedGutter() throws {
    let harness = try makeHarness(messageCount: 12)
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    let viewportWidth = harness.viewportWidth
    let painted = try XCTUnwrap(
      harness.rightmostPaintedColumn(), "the mounted transcript painted nothing")

    // The old cap put the column's right edge at (900 - 760) / 2 + 760 = 830.
    XCTAssertGreaterThan(
      CGFloat(painted), viewportWidth - 60,
      "transcript rows stop at x=\(painted) of \(viewportWidth), so a gutter is still reserved")
  }

  func testRepeatedFastBurstsKeepTheMountedTranscriptResponsive() throws {
    let harness = try makeHarness(messageCount: 120)
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    for cycle in 0..<20 {
      let beforeUp = harness.scrollTop
      harness.performUpwardGesture(events: 8, pumpPerEvent: 0.003)
      XCTAssertLessThan(
        harness.scrollTop,
        beforeUp - 100,
        "upward burst \(cycle) stopped moving the mounted transcript"
      )

      harness.appendStreamingText(" background stream \(cycle).")
      harness.pump(0.02)

      let beforeDown = harness.scrollTop
      harness.performDownwardGesture(events: 8, pumpPerEvent: 0.003)
      XCTAssertGreaterThan(
        harness.scrollTop,
        beforeDown + 100,
        "downward burst \(cycle) stopped moving the mounted transcript"
      )
      XCTAssertTrue(
        harness.usesOriginalScrollView,
        "wheel-driven SwiftUI state churn replaced the native scroll view during burst \(cycle)"
      )
    }
    harness.pump(0.2)

    XCTAssertTrue(
      harness.usesOriginalScrollView,
      "the transcript's native scroll view was replaced by the repeated burst sequence"
    )
  }

  /// **Nothing a traversal touches may change what the transcript measures.**
  ///
  /// The first thing this caught was not row materialization, which is what it
  /// used to claim: it was the pointer. An assistant row's hover-revealed
  /// metadata band took its intrinsic height on reveal, so a hovered row was
  /// ~16 pt taller than the same row unhovered and every row below it moved.
  /// With the physical mouse over this window the document oscillated between
  /// 7773 and 7789 pt across a traversal; with the mouse on another display
  /// every sample was 7773 and the same binary passed. The band now draws out
  /// of a zero-height frame (`ChatBubble.messageMetadataRow`), so height is
  /// hover-invariant and this measurement no longer depends on where the
  /// developer left the cursor.
  func testFastTraversalKeepsTheTranscriptDocumentHeightStable() throws {
    let harness = try makeHarness(messageCount: 120)
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    var measuredHeights = [harness.documentHeight]
    for _ in 0..<20 {
      harness.performUpwardGesture(events: 8, pumpPerEvent: 0.004)
      harness.pump(0.03)
      measuredHeights.append(harness.documentHeight)
    }

    let minimumHeight = try XCTUnwrap(measuredHeights.min())
    let maximumHeight = try XCTUnwrap(measuredHeights.max())
    XCTAssertEqual(
      maximumHeight,
      minimumHeight,
      accuracy: 4,
      "a fast gesture must not change the transcript's document height — not by "
        + "materializing off-screen rows, and not by passing the pointer over rows "
        + "whose hover reveals something (observed \(minimumHeight)...\(maximumHeight))"
    )
  }

  func testDeliberateReturnToTheLiveEdgeResumesFollowing() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.performUpwardGesture(events: 30)
    XCTAssertFalse(harness.isAtBottom)

    harness.performDownwardGestureToBottom()

    harness.appendStreamingText(" a token after the reader came back.")
    harness.pump(0.7)

    XCTAssertTrue(
      harness.isAtBottom,
      "an intentional return to the live edge resumes live following "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))")
  }

  /// Opening Home's chat panel with the mouse puts a click inside the transcript
  /// while launch placement is still settling. A click is not a scroll: it must
  /// not cancel the placement and strand the reader at the top of the history.
  func testAClickInTheTranscriptDoesNotCancelLaunchPlacement() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }

    harness.pump(0.05)
    harness.sendLeftMouseDown()
    harness.settleInitialPlacement()

    XCTAssertTrue(
      harness.isAtBottom,
      "a click during launch placement must not strand the transcript at the top "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))")
  }

  /// Dragging the scrollbar genuinely moves the viewport, so it must still take
  /// ownership away from live-follow.
  func testAMouseDragThatMovesTheViewportStillTakesOwnership() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.sendLeftMouseDown()
    harness.dragViewport(by: -1200)
    let readerPosition = harness.scrollTop
    XCTAssertFalse(harness.isAtBottom, "precondition: the drag left the live edge")

    harness.appendStreamingText(" streamed while the reader dragged away.")
    harness.pump(0.7)

    XCTAssertEqual(
      harness.scrollTop, readerPosition, accuracy: 4,
      "a drag that moved the viewport must keep the reader's position")
  }

  /// The real launch sequence: the transcript appears while the journal is still
  /// loading, the reader clicks somewhere in that region (to focus the window, to
  /// dismiss something, anything), and only then does the history arrive. A click
  /// is not a scroll, so it must not cancel the launch placement that has not even
  /// had content to place yet.
  func testAClickBeforeTheHistoryLoadsDoesNotStrandTheTranscriptAtTheTop() throws {
    let harness = try Harness(loadingWithPendingMessageCount: 60)
    defer { harness.tearDown() }

    harness.sendLeftMouseDown()
    harness.finishInitialLoad()

    XCTAssertTrue(
      harness.isAtBottom,
      "a click while the history was still loading must not strand the reader at the top "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))")
  }

  /// A scrollbar track click moves the viewport during the press and may never
  /// produce a drag event at all. It is still the reader moving the viewport, so
  /// it must take ownership — otherwise the next streamed token yanks them back.
  func testAScrollbarTrackClickThatMovesTheViewportTakesOwnership() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    harness.trackClickJump(by: -1500)
    let readerPosition = harness.scrollTop
    XCTAssertFalse(harness.isAtBottom, "precondition: the track click left the live edge")

    harness.appendStreamingText(" streamed after the track click.")
    harness.pump(0.7)

    XCTAssertEqual(
      harness.scrollTop, readerPosition, accuracy: 4,
      "a track click that moved the viewport must keep the reader's position")
  }

  /// Clicking "Load earlier messages" inserts rows above the viewport. The clip
  /// origin stays at zero unless restored, which is the newly loaded oldest
  /// row — the jump this test exists to forbid.
  func testLoadingEarlierMessagesLeavesTheReaderOnTheSameRows() throws {
    let harness = try makeHarness(messageCount: 80)
    defer { harness.tearDown() }
    harness.settleInitialPlacement()
    harness.beginLiveScroll()
    harness.scrollClipToTop()
    XCTAssertLessThan(
      harness.scrollTop, 80,
      "precondition: the reader is at the top of history (scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))"
    )
    harness.endLiveScroll()
    let heightBefore = harness.documentHeight
    let topBefore = harness.scrollTop

    harness.beginLoadMore()
    harness.prependOlderMessages(count: 40)
    harness.finishLoadMore()

    XCTAssertGreaterThan(
      harness.documentHeight, heightBefore + 200,
      "precondition: older rows actually grew the document")
    let expected = ChatTranscriptPrependPreservation.restoredScrollTop(
      previousDocumentHeight: heightBefore,
      previousScrollTop: topBefore,
      newDocumentHeight: harness.documentHeight
    )
    XCTAssertEqual(
      harness.scrollTop, expected, accuracy: 40,
      "loading earlier messages jumped the reader (scrollTop=\(harness.scrollTop), expected ~\(expected))"
    )
    XCTAssertGreaterThan(
      harness.scrollTop, 100,
      "restore left the reader at the newly loaded oldest rows (scrollTop=\(harness.scrollTop))")
  }

  // MARK: - Harness

  private func makeHarness(
    messageCount: Int = 60,
    transcriptWindowPolicy: ChatTranscriptWindow.Policy? = nil
  ) throws -> Harness {
    try Harness(messageCount: messageCount, transcriptWindowPolicy: transcriptWindowPolicy)
  }

  @MainActor
  final class Harness {
    let model: TranscriptModel
    private let window: NSWindow
    private let hostingView: NSHostingView<HarnessChatHost>
    private var pendingMessages: [ChatMessage] = []
    private(set) var scrollView: NSScrollView
    /// Parked inside the document so a detector coordinator resolves the same
    /// enclosing scroll view the production detectors bind to.
    let probeView: NSView

    convenience init(loadingWithPendingMessageCount messageCount: Int) throws {
      try self.init(messageCount: 0, startsLoading: true, pendingMessageCount: messageCount)
    }

    init(
      messageCount: Int,
      startsLoading: Bool = false,
      pendingMessageCount: Int = 0,
      transcriptWindowPolicy: ChatTranscriptWindow.Policy? = nil
    ) throws {
      model = TranscriptModel(messages: Self.makeMessages(count: messageCount))
      model.isLoadingInitial = startsLoading
      model.transcriptWindowPolicy = transcriptWindowPolicy
      self.pendingMessages = Self.makeMessages(count: pendingMessageCount)
      hostingView = NSHostingView(rootView: HarnessChatHost(model: model))
      hostingView.frame = NSRect(x: 0, y: 0, width: 900, height: 600)
      window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 900, height: 600),
        styleMask: [.titled], backing: .buffered, defer: false)
      window.contentView = hostingView

      NonintrusiveTestWindow.orderIn(window)
      Self.pumpRunLoop(0.2)
      hostingView.layoutSubtreeIfNeeded()
      Self.pumpRunLoop(0.2)
      guard let discovered = Self.firstScrollView(in: hostingView) else {
        throw XCTSkip("SwiftUI built no NSScrollView for the transcript in this environment")
      }
      scrollView = discovered
      probeView = NSView(frame: NSRect(x: 0, y: 0, width: 1, height: 1))
      (discovered.documentView ?? discovered).addSubview(probeView)
    }

    func tearDown() {
      window.orderOut(nil)
      window.contentView = nil
    }

    // MARK: Geometry

    var documentHeight: CGFloat { scrollView.documentView?.frame.height ?? 0 }
    var viewportHeight: CGFloat { scrollView.contentView.bounds.height }
    var maximumScrollTop: CGFloat { max(documentHeight - viewportHeight, 0) }

    var scrollTop: CGFloat {
      ChatScrollLiveEdge.topBasedScrollOffset(
        clipOriginY: scrollView.contentView.bounds.origin.y,
        viewportHeight: viewportHeight,
        documentHeight: documentHeight,
        isDocumentFlipped: scrollView.documentView?.isFlipped ?? true)
    }

    var isAtBottom: Bool {
      ChatScrollLiveEdge.isAtBottom(
        visibleMaxY: scrollTop + viewportHeight, documentHeight: documentHeight)
    }

    var usesOriginalScrollView: Bool {
      Self.firstScrollView(in: hostingView) === scrollView
    }

    var viewportWidth: CGFloat { scrollView.contentView.bounds.width }

    /// The rightmost column of the viewport that the transcript actually paints,
    /// or nil when it painted nothing. Read from the clip view's own bitmap: a
    /// reserved gutter is invisible to frames, because the stack stays full width
    /// and insets its contents.
    func rightmostPaintedColumn() -> Int? {
      let clipView = scrollView.contentView
      let bounds = clipView.bounds
      guard bounds.width > 0, bounds.height > 0,
        let representation = clipView.bitmapImageRepForCachingDisplay(in: bounds)
      else { return nil }
      clipView.cacheDisplay(in: bounds, to: representation)
      guard let image = representation.cgImage else { return nil }

      let width = image.width
      let height = image.height
      var pixels = [UInt8](repeating: 0, count: width * height * 4)
      guard
        let context = CGContext(
          data: &pixels,
          width: width,
          height: height,
          bitsPerComponent: 8,
          bytesPerRow: width * 4,
          space: CGColorSpaceCreateDeviceRGB(),
          bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
      else { return nil }
      context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))

      var rightmost: Int?
      for y in 0..<height {
        for x in stride(from: width - 1, through: 0, by: -1) {
          if pixels[(y * width + x) * 4 + 3] > 25 {
            rightmost = max(rightmost ?? 0, x)
            break
          }
        }
      }
      guard let rightmost else { return nil }
      // Back into the clip view's point space; the window may be backed at 2x.
      return Int((CGFloat(rightmost) * bounds.width / CGFloat(width)).rounded())
    }

    // MARK: Gestures

    /// Outlives every delay in `ChatScrollLiveEdge.initialRestoreSettlingDelays`.
    func settleInitialPlacement() {
      pump(1.2)
      if let discovered = Self.firstScrollView(in: hostingView) { scrollView = discovered }
    }

    func scrollClipToTop() {
      setClipTop(0)
    }

    func performUpwardGesture(
      events: Int, deltaPerEvent: CGFloat = 40, pumpPerEvent: TimeInterval = 0,
      endGesture: Bool = true
    ) {
      beginLiveScroll()
      for _ in 0..<events {
        sendWheel(deltaY: deltaPerEvent)
        // Positive scrollingDeltaY reveals earlier content, so the flipped clip
        // origin decreases. AppKit applies this itself for a device event.
        moveClipView(by: -deltaPerEvent)
        if pumpPerEvent > 0 { pump(pumpPerEvent) }
      }
      pump(0.05)
      if endGesture { endLiveScroll() }
    }

    func performDownwardGestureToBottom() {
      beginLiveScroll()
      var remaining = maximumScrollTop - scrollTop
      while remaining > 0 {
        let step = min(60, remaining)
        sendWheel(deltaY: -step)
        moveClipView(by: step)
        remaining -= step
      }
      // Land exactly on the live edge, the way a real gesture bottoms out.
      setClipTop(maximumScrollTop)
      pump(0.05)
      endLiveScroll()
      pump(0.3)
    }

    func performDownwardGesture(
      events: Int, deltaPerEvent: CGFloat = 40, pumpPerEvent: TimeInterval = 0,
      endGesture: Bool = true
    ) {
      beginLiveScroll()
      for _ in 0..<events {
        sendWheel(deltaY: -deltaPerEvent)
        moveClipView(by: deltaPerEvent)
        if pumpPerEvent > 0 { pump(pumpPerEvent) }
      }
      pump(0.05)
      if endGesture { endLiveScroll() }
    }

    /// The journal snapshot arrives, exactly as `ChatProvider` delivers it.
    func finishInitialLoad() {
      model.messages = pendingMessages
      model.isLoadingInitial = false
      pump(1.2)
    }

    func sendLeftMouseDown() {
      guard
        let event = NSEvent.mouseEvent(
          with: .leftMouseDown,
          location: NSPoint(x: 450, y: 300),
          modifierFlags: [],
          timestamp: ProcessInfo.processInfo.systemUptime,
          windowNumber: window.windowNumber,
          context: nil,
          eventNumber: 0,
          clickCount: 1,
          pressure: 1)
      else { return }
      NSApplication.shared.sendEvent(event)
      pump(0.02)
    }

    /// A scrollbar drag: mouse-dragged events that genuinely move the viewport.
    func dragViewport(by delta: CGFloat) {
      let steps = 12
      for _ in 0..<steps {
        moveClipView(by: delta / CGFloat(steps))
        guard
          let event = NSEvent.mouseEvent(
            with: .leftMouseDragged,
            location: NSPoint(x: 450, y: 300),
            modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: window.windowNumber,
            context: nil,
            eventNumber: 0,
            clickCount: 1,
            pressure: 1)
        else { continue }
        NSApplication.shared.sendEvent(event)
      }
      sendLeftMouseUp()
      pump(0.05)
    }

    func sendLeftMouseUp() {
      guard
        let event = NSEvent.mouseEvent(
          with: .leftMouseUp, location: NSPoint(x: 450, y: 300), modifierFlags: [],
          timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
          context: nil, eventNumber: 0, clickCount: 1, pressure: 0)
      else { return }
      NSApplication.shared.sendEvent(event)
      pump(0.02)
    }

    /// A scrollbar track click: the viewport jumps during the press itself, with
    /// no drag event at any point.
    func trackClickJump(by delta: CGFloat) {
      sendLeftMouseDown()
      moveClipView(by: delta)
      pump(0.05)
      sendLeftMouseUp()
      pump(0.05)
    }

    func beginLiveScroll() {
      NotificationCenter.default.post(
        name: NSScrollView.willStartLiveScrollNotification, object: scrollView)
    }

    func endLiveScroll() {
      NotificationCenter.default.post(
        name: NSScrollView.didEndLiveScrollNotification, object: scrollView)
      pump(0.1)
    }

    func appendStreamingText(_ suffix: String) {
      guard !model.messages.isEmpty else { return }
      model.messages[model.messages.count - 1].text += suffix
      model.messages[model.messages.count - 1].isStreaming = true
    }

    func appendAssistantMessage() {
      model.messages.append(
        ChatMessage(
          id: "assistant-arrival-\(model.messages.count)",
          text: String(repeating: "A newly arrived answer. ", count: 8),
          sender: .ai))
    }

    func beginLoadMore() {
      model.hasMoreMessages = true
      model.isLoadingMoreMessages = true
      pump(0.05)
    }

    func prependOlderMessages(count: Int) {
      let older = Self.makeMessages(count: count, idOffset: 10_000)
      model.messages = older + model.messages
    }

    func finishLoadMore() {
      model.isLoadingMoreMessages = false
      pump(0.7)
    }

    /// Removes the transcript from the hierarchy and puts it back, the way
    /// Home's stage transition does.
    ///
    /// Both halves wait on the hierarchy, not on a fixed pump. SwiftUI commits
    /// the removal on its own update turn, and on a loaded machine that turn can
    /// land after a fixed pump ends — the `false`/`true` flips then coalesce into
    /// no change at all, so nothing unmounts, `onAppear` never runs, and the
    /// caller silently measures the same transcript the reader already scrolled.
    func togglePresentation() {
      model.isPresented = false
      waitForTranscript(mounted: false)
      model.isPresented = true
      waitForTranscript(mounted: true)
      if let discovered = Self.firstScrollView(in: hostingView) { scrollView = discovered }
    }

    /// Pumps until the transcript's scroll view reaches `mounted`, then returns.
    /// On timeout it returns anyway so the caller's assertion reports the real
    /// state rather than this helper's own failure.
    private func waitForTranscript(mounted: Bool, timeout: TimeInterval = 2) {
      let deadline = Date().addingTimeInterval(timeout)
      repeat {
        pump(0.02)
        if (Self.firstScrollView(in: hostingView) != nil) == mounted { return }
      } while Date() < deadline
    }

    // MARK: Plumbing

    private func moveClipView(by delta: CGFloat) {
      setClipTop(min(max(scrollTop + delta, 0), maximumScrollTop))
    }

    private func setClipTop(_ top: CGFloat) {
      let flipped = scrollView.documentView?.isFlipped ?? true
      let originY = flipped ? top : documentHeight - top - viewportHeight
      scrollView.contentView.scroll(to: NSPoint(x: 0, y: originY))
      scrollView.reflectScrolledClipView(scrollView.contentView)
    }

    private func sendWheel(deltaY: CGFloat) {
      guard let event = makeWheelEvent(deltaY: Int32(deltaY)) else { return }
      NSApplication.shared.sendEvent(event)
    }

    /// `kCGScrollWheelEventIsContinuous`, which CoreGraphics does not surface as
    /// an enum case. A trackpad's deltas are continuous; a detent wheel's are not.
    private static let isContinuousField = CGEventField(rawValue: 88)

    func makeWheelEvent(deltaY: Int32) -> NSEvent? {
      guard
        let isContinuousField = Self.isContinuousField,
        let cgEvent = CGEvent(
          scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1,
          wheel1: deltaY, wheel2: 0, wheel3: 0)
      else { return nil }
      cgEvent.setIntegerValueField(isContinuousField, value: 1)
      guard let event = NSEvent(cgEvent: cgEvent) else { return nil }
      // A CGEvent-derived NSEvent carries no window, so production's
      // `event.window == scrollView.window` guard would drop it. Give it the
      // identity and location AppKit attaches to a real device event.
      InjectedScrollEvent.target = window
      InjectedScrollEvent.targetWindowNumber = window.windowNumber
      InjectedScrollEvent.locationInWindowOverride = NSPoint(x: 450, y: 300)
      object_setClass(event, InjectedScrollEvent.self)
      return event
    }

    func pump(_ seconds: TimeInterval) { Self.pumpRunLoop(seconds) }

    // omi-test-quality: wall-clock-wait -- drives AppKit's real run loop and SwiftUI's
    // own layout turns; there is no injectable clock at the NSHostingView boundary.
    private static func pumpRunLoop(_ seconds: TimeInterval) {
      let deadline = Date().addingTimeInterval(seconds)
      while Date() < deadline {
        _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
      }
    }

    private static func firstScrollView(in view: NSView) -> NSScrollView? {
      if let scrollView = view as? NSScrollView { return scrollView }
      for subview in view.subviews {
        if let found = firstScrollView(in: subview) { return found }
      }
      return nil
    }

    private static func makeMessages(count: Int, idOffset: Int = 0) -> [ChatMessage] {
      (0..<count).map { index in
        let identity = index + idOffset
        return identity.isMultiple(of: 2)
          ? ChatMessage(
            id: "user-\(identity)",
            text: "Reader question number \(identity) about the desktop transcript.",
            createdAt: Date(timeIntervalSince1970: 1_700_000_000 + Double(identity)),
            sender: .user)
          : ChatMessage(
            id: "assistant-\(identity)",
            text: String(
              repeating: "Assistant answer \(identity) with enough prose to make the row tall. ",
              count: 6),
            createdAt: Date(timeIntervalSince1970: 1_700_000_000 + Double(identity)),
            sender: .ai)
      }
    }
  }
}

/// Mutable transcript source, so the harness can stream into the mounted view
/// the way `ChatProvider` does.
@MainActor
final class TranscriptModel: ObservableObject {
  @Published var messages: [ChatMessage]
  @Published var conversationIdentity: String = "harness-session"
  @Published var isSending: Bool = false
  @Published var isLoadingInitial: Bool = false
  @Published var isLoadingMoreMessages: Bool = false
  @Published var hasMoreMessages: Bool = false
  @Published var localSendToken: LocalSendToken?
  @Published var isPresented: Bool = true
  var transcriptWindowPolicy: ChatTranscriptWindow.Policy?

  init(messages: [ChatMessage]) {
    self.messages = messages
  }
}

struct HarnessChatHost: View {
  @ObservedObject var model: TranscriptModel

  var body: some View {
    ZStack {
      if model.isPresented {
        ChatMessagesView(
          messages: model.messages,
          conversationIdentity: model.conversationIdentity,
          isSending: model.isSending,
          hasMoreMessages: model.hasMoreMessages,
          isLoadingMoreMessages: model.isLoadingMoreMessages,
          isLoadingInitial: model.isLoadingInitial,
          app: nil,
          onLoadMore: {},
          onRate: { _, _ in },
          localSendToken: model.localSendToken,
          horizontalContentPadding: 0,
          transcriptWindowPolicy: model.transcriptWindowPolicy,
          welcomeContent: { EmptyView() }
        )
      }
    }
    .frame(width: 900, height: 600)
  }
}

/// Gives an injected scroll event the window identity and in-window location a
/// real device event carries, so production's guards see the truth.
final class InjectedScrollEvent: NSEvent {
  nonisolated(unsafe) static var target: NSWindow?
  nonisolated(unsafe) static var targetWindowNumber: Int = 0
  nonisolated(unsafe) static var locationInWindowOverride: NSPoint = .zero

  override var window: NSWindow? { InjectedScrollEvent.target }
  override var windowNumber: Int { InjectedScrollEvent.targetWindowNumber }
  override var locationInWindow: NSPoint { InjectedScrollEvent.locationInWindowOverride }
}
