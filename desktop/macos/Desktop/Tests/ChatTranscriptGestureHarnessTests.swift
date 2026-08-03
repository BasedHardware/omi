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
    harness.pump(1.0)

    XCTAssertTrue(
      harness.isAtBottom,
      "a re-presented transcript starts at the live edge "
        + "(scrollTop=\(harness.scrollTop) of \(harness.maximumScrollTop))")
  }

  func testPromptRailKeepsTrackingThroughARapidBurst() throws {
    let harness = try makeHarness()
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    let geometry = ChatTranscriptGeometry()
    geometry.setMessages(harness.model.messages)
    geometry.setViewport(CGSize(width: 900, height: 600), columnWidth: 760)

    var deliveries: [CGFloat] = []
    let detector = ScrollPositionDetector.Coordinator { position in
      geometry.setContent(height: position.documentHeight, scrollTop: position.scrollTop)
      deliveries.append(position.scrollTop)
    }
    detector.setupScrollObserver(for: harness.probeView)
    defer { detector.stop() }

    harness.performUpwardGesture(events: 30, pumpPerEvent: 0.004)
    harness.pump(0.2)

    XCTAssertGreaterThanOrEqual(
      deliveries.count, 3,
      "the rail must keep receiving positions throughout a rapid gesture")
    XCTAssertEqual(
      deliveries.last ?? -1, harness.scrollTop, accuracy: 4,
      "the rail's last known position must be where the reader actually is")
  }

  func testRepeatedFastBurstsKeepTheMountedTranscriptAndPromptRailResponsive() throws {
    let harness = try makeHarness(messageCount: 120)
    defer { harness.tearDown() }
    harness.settleInitialPlacement()

    var deliveredScrollTop: CGFloat = -1
    let detector = ScrollPositionDetector.Coordinator { position in
      deliveredScrollTop = position.scrollTop
    }
    detector.setupScrollObserver(for: harness.probeView)
    defer { detector.stop() }

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

    XCTAssertEqual(
      deliveredScrollTop,
      harness.scrollTop,
      accuracy: 4,
      "the prompt rail stopped tracking before the repeated burst sequence ended"
    )
  }

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
      "materializing off-screen rows during a fast gesture must not re-estimate "
        + "the transcript document height (observed \(minimumHeight)...\(maximumHeight))"
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

  // MARK: - Harness

  private func makeHarness(messageCount: Int = 60) throws -> Harness {
    try Harness(messageCount: messageCount)
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

    init(messageCount: Int, startsLoading: Bool = false, pendingMessageCount: Int = 0) throws {
      model = TranscriptModel(messages: Self.makeMessages(count: messageCount))
      model.isLoadingInitial = startsLoading
      self.pendingMessages = Self.makeMessages(count: pendingMessageCount)
      hostingView = NSHostingView(rootView: HarnessChatHost(model: model))
      hostingView.frame = NSRect(x: 0, y: 0, width: 900, height: 600)
      window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 900, height: 600),
        styleMask: [.titled], backing: .buffered, defer: false)
      window.contentView = hostingView

      window.orderFrontRegardless()
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

    // MARK: Gestures

    /// Outlives every delay in `ChatScrollLiveEdge.initialRestoreSettlingDelays`.
    func settleInitialPlacement() { pump(1.0) }

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

    // MARK: Content mutation

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

    /// Removes the transcript from the hierarchy and puts it back, the way
    /// Home's stage transition does.
    func togglePresentation() {
      model.isPresented = false
      pump(0.2)
      model.isPresented = true
      pump(0.2)
      if let discovered = Self.firstScrollView(in: hostingView) { scrollView = discovered }
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

    private static func makeMessages(count: Int) -> [ChatMessage] {
      (0..<count).map { index in
        index.isMultiple(of: 2)
          ? ChatMessage(
            id: "user-\(index)",
            text: "Reader question number \(index) about the desktop transcript.",
            createdAt: Date(timeIntervalSince1970: 1_700_000_000 + Double(index)),
            sender: .user)
          : ChatMessage(
            id: "assistant-\(index)",
            text: String(
              repeating: "Assistant answer \(index) with enough prose to make the row tall. ",
              count: 6),
            createdAt: Date(timeIntervalSince1970: 1_700_000_000 + Double(index)),
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
  @Published var localSendToken: LocalSendToken?
  @Published var isPresented: Bool = true

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
          hasMoreMessages: false,
          isLoadingMoreMessages: false,
          isLoadingInitial: model.isLoadingInitial,
          app: nil,
          onLoadMore: {},
          onRate: { _, _ in },
          localSendToken: model.localSendToken,
          horizontalContentPadding: 0,
          contentColumnWidth: 760,
          timelineTrailingInset: 0,
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
