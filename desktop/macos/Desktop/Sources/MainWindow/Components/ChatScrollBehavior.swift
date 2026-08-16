import AppKit
import OmiTheme
import SwiftUI

extension Notification.Name {
  static let chatVerticalWheelPassthrough = Notification.Name("chatVerticalWheelPassthrough")
}

/// The narrow distance from the live edge that means the reader has actually
/// returned to it. A generous threshold makes a deliberate small upward scroll
/// look like "follow the stream" and pulls the reader back down on the next token.
enum ChatScrollLiveEdge {
  static let intentEpsilon: CGFloat = 2
  /// A jump button fires before SwiftUI has necessarily finished laying out a
  /// newly expanded final row. Repeating the bottom-anchor scroll on the next
  /// turn makes the explicit intent land at the true live edge.
  static let explicitJumpSettlingDelay: TimeInterval = 0.05
  /// The initial history restore can span several SwiftUI layout turns. A
  /// single early scrollTo may resolve against the pre-history document and
  /// leave a long transcript at its top, so settle the live edge again after
  /// the first layout has materialized the lazy rows.
  static let initialRestoreSettlingDelays: [TimeInterval] = [0.05, 0.2, 0.5, 1.0]

  static func isAtBottom(visibleMaxY: CGFloat, documentHeight: CGFloat) -> Bool {
    visibleMaxY >= documentHeight - intentEpsilon
  }

  /// Converts AppKit's document-space clip origin into one stable coordinate:
  /// zero at the visual top, increasing toward the live edge. SwiftUI-hosted
  /// document views are not guaranteed to be flipped, so reading `origin.y`
  /// directly reverses the scroll direction on those views and can classify
  /// the visual top as the bottom.
  static func topBasedScrollOffset(
    clipOriginY: CGFloat,
    viewportHeight: CGFloat,
    documentHeight: CGFloat,
    isDocumentFlipped: Bool
  ) -> CGFloat {
    let maximum = max(documentHeight - viewportHeight, 0)
    let raw =
      isDocumentFlipped
      ? clipOriginY
      : documentHeight - (clipOriginY + viewportHeight)
    return min(max(raw, 0), maximum)
  }

  enum FollowResumeSource: Equatable {
    case passivePosition
    case settledUserScroll
  }

  /// Only a completed physical scroll at the live edge may hand transcript
  /// ownership back to auto-follow. AppKit also emits bottom-position samples
  /// after programmatic prompt jumps and layout changes; treating those as
  /// reader intent makes the viewport snap away from selected history.
  static func canResumeFollowing(
    source: FollowResumeSource,
    isAtBottom: Bool,
    userIsScrolling: Bool
  ) -> Bool {
    source == .settledUserScroll && isAtBottom && !userIsScrolling
  }
}

/// **How often a following transcript re-reaches the live edge while an answer
/// streams.** A rate limiter, not a quiet period.
///
/// The previous implementation cancelled its pending scroll on every content
/// change and rescheduled it 80 ms out. That is a trailing debounce wearing a
/// throttle's name, and it has one behaviour that matters here: while the input
/// keeps arriving faster than the window, the scroll never runs at all.
/// `ChatProvider` flushes streamed text every 35 ms
/// (`ChatStreamingBuffer(flushInterval: 0.035)`), which is exactly that case —
/// so a following reader was abandoned for the entire answer and then snapped
/// back the instant the stream stopped. Measured on the mounted transcript, the
/// live edge ran 387 pt past a 600 pt viewport and never once caught up.
///
/// A throttle instead: the first request runs immediately, and any request
/// inside the window queues **one** run at the window's end without pushing that
/// deadline back. Continuous streaming therefore follows at a steady ~12 Hz.
enum ChatScrollFollowThrottle {
  /// One follow per frame-ish. Small enough that the live edge never visibly
  /// falls behind, large enough that a token burst cannot saturate the main
  /// thread with `scrollTo` + layout.
  static let interval: TimeInterval = 0.08

  enum Decision: Equatable {
    /// Run the scroll on this turn.
    case now
    /// A run is already queued for this window — adding another would be the
    /// debounce again.
    case alreadyScheduled
    /// Queue exactly one run this far ahead.
    case schedule(after: TimeInterval)
  }

  static func decide(now: TimeInterval, lastRun: TimeInterval?, hasQueuedRun: Bool) -> Decision {
    guard !hasQueuedRun else { return .alreadyScheduled }
    guard let lastRun else { return .now }
    let elapsed = now - lastRun
    // A clock that went backwards (or an unchanged timestamp) must not strand
    // the transcript in a window that never expires.
    guard elapsed >= 0, elapsed < interval else { return .now }
    return .schedule(after: interval - elapsed)
  }
}

/// A stable representable host that tells its coordinator when SwiftUI moves it
/// between transcript hierarchies. The enclosing NSScrollView is not guaranteed
/// to survive a lazy document replacement, especially during a fast gesture.
private final class ScrollDetectorHostView: NSView {
  var onHierarchyChange: (() -> Void)?

  override func viewDidMoveToSuperview() {
    super.viewDidMoveToSuperview()
    onHierarchyChange?()
  }

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    onHierarchyChange?()
  }
}

/// Detects user scroll-wheel / trackpad gestures, mouse interactions, and
/// keyboard scroll-navigation on the enclosing NSScrollView.
struct UserScrollDetector: NSViewRepresentable {
  let onUserScroll: () -> Void
  var onScrollSettledAtBottom: () -> Void = {}

  func makeNSView(context: Context) -> NSView {
    let view = ScrollDetectorHostView()
    view.onHierarchyChange = { [weak coordinator = context.coordinator, weak view] in
      guard let coordinator, let view else { return }
      coordinator.scheduleAttachment(for: view)
    }
    context.coordinator.scheduleAttachment(for: view)
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {
    // Keep the event monitor attached to the current transcript scroll view
    // when SwiftUI rebuilds the lazy document hierarchy.
    context.coordinator.install(for: nsView)
  }

  static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
    coordinator.stop()
  }

  func makeCoordinator() -> Coordinator {
    Coordinator(onUserScroll: onUserScroll, onScrollSettledAtBottom: onScrollSettledAtBottom)
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    let onUserScroll: () -> Void
    let onScrollSettledAtBottom: () -> Void
    private var monitor: Any?
    private weak var installedScrollView: NSScrollView?
    private var settleWorkItem: DispatchWorkItem?
    /// Where the viewport sat when the current press began, so movement can be
    /// told apart from a click that never moved anything.
    private var pressOriginScrollTop: CGFloat?
    private var pressCandidateOwnsViewport = false
    private var pressBoundsObservation: NSObjectProtocol?
    private static let dragMovementEpsilon: CGFloat = 1
    /// AppKit may route dozens of wheel deltas through one trackpad gesture.
    /// Reader ownership crosses into SwiftUI once per gesture, not once per
    /// delta, so a long lazy transcript is not invalidated while AppKit is
    /// still delivering momentum to its current scroll view.
    private var wheelGestureOwnsViewport = false
    private var willStartLiveScrollObservation: NSObjectProtocol?
    private var didEndLiveScrollObservation: NSObjectProtocol?
    private var verticalWheelPassthroughObservation: NSObjectProtocol?

    private static let settledBottomDelay: TimeInterval = 0.36

    private static let scrollNavigationKeyCodes: Set<UInt16> = [
      125,  // Down arrow
      126,  // Up arrow
      116,  // Page Up
      121,  // Page Down
      115,  // Home
      119,  // End
    ]

    init(onUserScroll: @escaping () -> Void, onScrollSettledAtBottom: @escaping () -> Void) {
      self.onUserScroll = onUserScroll
      self.onScrollSettledAtBottom = onScrollSettledAtBottom
    }

    func scheduleAttachment(for view: NSView) {
      for delay in [0.0, 0.05, 0.2] {
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self, weak view] in
          guard let self, let view else { return }
          self.install(for: view)
        }
      }
    }

    func install(for view: NSView) {
      MainActor.assumeIsolated {
        guard let targetScrollView = Self.enclosingScrollView(for: view) else {
          stop()
          return
        }
        guard installedScrollView !== targetScrollView else { return }
        stop()
        installedScrollView = targetScrollView

        // AppKit owns the lifecycle of a trackpad/wheel gesture, including
        // momentum. A wall-clock debounce can fire during a brief gap in a
        // fast gesture and incorrectly decide that the reader settled at the
        // live edge. That re-arms follow mode and the next streaming/layout
        // update snaps the transcript back to the bottom. Observe the native
        // live-scroll boundary instead, so ownership cannot return until
        // AppKit says the complete gesture (momentum included) has ended.
        willStartLiveScrollObservation = NotificationCenter.default.addObserver(
          forName: NSScrollView.willStartLiveScrollNotification,
          object: targetScrollView,
          queue: .main
        ) { [weak self] _ in
          self?.beginUserScroll()
        }
        didEndLiveScrollObservation = NotificationCenter.default.addObserver(
          forName: NSScrollView.didEndLiveScrollNotification,
          object: targetScrollView,
          queue: .main
        ) { [weak self, weak targetScrollView] _ in
          guard let self, let targetScrollView else { return }
          self.finishUserScroll(on: targetScrollView)
        }
        verticalWheelPassthroughObservation = NotificationCenter.default.addObserver(
          forName: .chatVerticalWheelPassthrough,
          object: targetScrollView,
          queue: .main
        ) { [weak self, weak targetScrollView] notification in
          guard let self, let targetScrollView else { return }
          self.beginUserScroll()
          if let event = notification.userInfo?["event"] as? NSEvent,
            event.phase.isEmpty, event.momentumPhase.isEmpty
          {
            self.scheduleUnphasedWheelEnd(for: targetScrollView)
          }
        }

        let handler: @MainActor (NSEvent) -> NSEvent? = { [weak self] event in
          guard let self else { return event }
          guard event.window == targetScrollView.window else { return event }

          if event.type == .keyDown {
            guard Self.scrollNavigationKeyCodes.contains(event.keyCode) else { return event }
            guard Self.isScrollViewKeyboardTarget(in: event.window, scrollView: targetScrollView) else { return event }
            self.onUserScroll()
            self.scheduleDiscreteInputSettledBottomCheck(for: targetScrollView)
          } else {
            switch event.type {
            case .scrollWheel:
              let wheelLocation = targetScrollView.convert(event.locationInWindow, from: nil)
              guard targetScrollView.bounds.contains(wheelLocation) else { break }
              if event.scrollingDeltaY != 0 || event.scrollingDeltaX != 0 {
                self.beginUserScroll()
                if event.phase.isEmpty, event.momentumPhase.isEmpty {
                  self.scheduleUnphasedWheelEnd(for: targetScrollView)
                }
              }
            case .leftMouseDown:
              // A press is not viewport movement. Clicking inside the transcript
              // to focus the window, select text, or hit a control used to claim
              // scroll ownership outright, which cancelled the one-shot launch
              // placement and left a freshly opened chat stranded at the top of
              // its history. Open a candidate instead; only real displacement of
              // this clip view promotes it to ownership.
              let locationInScrollView = targetScrollView.convert(event.locationInWindow, from: nil)
              guard targetScrollView.bounds.contains(locationInScrollView) else { break }
              self.beginPressCandidate(on: targetScrollView)
            case .leftMouseUp:
              self.endPressCandidate(on: targetScrollView)
            default:
              // Deliberately not bounds-checked: a scrollbar drag and a
              // selection autoscroll both leave the transcript's bounds while
              // still moving it, and dropping those events lost the reader's
              // ownership exactly when they were moving fastest.
              self.promotePressCandidateIfMoved(on: targetScrollView)
            }
          }
          return event
        }
        monitor = NSEvent.addLocalMonitorForEvents(
          matching: [.scrollWheel, .leftMouseDown, .leftMouseDragged, .leftMouseUp, .keyDown],
          handler: handler)
      }
    }

    func stop() {
      MainActor.assumeIsolated {
        settleWorkItem?.cancel()
        settleWorkItem = nil
        if let pressBoundsObservation {
          NotificationCenter.default.removeObserver(pressBoundsObservation)
        }
        pressBoundsObservation = nil
        pressOriginScrollTop = nil
        pressCandidateOwnsViewport = false
        wheelGestureOwnsViewport = false
        if let willStartLiveScrollObservation {
          NotificationCenter.default.removeObserver(willStartLiveScrollObservation)
        }
        willStartLiveScrollObservation = nil
        if let didEndLiveScrollObservation {
          NotificationCenter.default.removeObserver(didEndLiveScrollObservation)
        }
        didEndLiveScrollObservation = nil
        if let verticalWheelPassthroughObservation {
          NotificationCenter.default.removeObserver(verticalWheelPassthroughObservation)
        }
        verticalWheelPassthroughObservation = nil
        if let monitor {
          NSEvent.removeMonitor(monitor)
        }
        monitor = nil
        installedScrollView = nil
      }
    }

    @MainActor
    private static func enclosingScrollView(for view: NSView) -> NSScrollView? {
      var current: NSView? = view
      while let candidate = current {
        if let scrollView = candidate as? NSScrollView {
          return scrollView
        }
        current = candidate.superview
      }
      return nil
    }

    private static func isScrollViewKeyboardTarget(in window: NSWindow?, scrollView: NSScrollView) -> Bool {
      MainActor.assumeIsolated {
        guard let window, let firstResponderView = window.firstResponder as? NSView else { return false }
        return firstResponderView === scrollView || firstResponderView.isDescendant(of: scrollView)
      }
    }

    @MainActor
    private func beginPressCandidate(on scrollView: NSScrollView) {
      pressOriginScrollTop = Self.scrollTop(of: scrollView)
      pressCandidateOwnsViewport = false
      // A scrollbar track click repositions the viewport during mouse-down and
      // may never produce a drag event, so watch the clip view rather than
      // waiting for one.
      scrollView.contentView.postsBoundsChangedNotifications = true
      pressBoundsObservation = NotificationCenter.default.addObserver(
        forName: NSView.boundsDidChangeNotification,
        object: scrollView.contentView,
        queue: .main
      ) { [weak self, weak scrollView] _ in
        guard let self, let scrollView else { return }
        MainActor.assumeIsolated { self.promotePressCandidateIfMoved(on: scrollView) }
      }
    }

    @MainActor
    private func promotePressCandidateIfMoved(on scrollView: NSScrollView) {
      guard let origin = pressOriginScrollTop, !pressCandidateOwnsViewport else { return }
      guard abs(Self.scrollTop(of: scrollView) - origin) >= Self.dragMovementEpsilon else { return }
      pressCandidateOwnsViewport = true
      onUserScroll()
    }

    @MainActor
    private func endPressCandidate(on scrollView: NSScrollView) {
      let ownedViewport = pressCandidateOwnsViewport
      if let observation = pressBoundsObservation {
        NotificationCenter.default.removeObserver(observation)
      }
      pressBoundsObservation = nil
      pressOriginScrollTop = nil
      pressCandidateOwnsViewport = false
      guard ownedViewport else { return }
      scheduleDiscreteInputSettledBottomCheck(for: scrollView)
    }

    private func beginUserScroll() {
      settleWorkItem?.cancel()
      settleWorkItem = nil
      guard !wheelGestureOwnsViewport else { return }
      wheelGestureOwnsViewport = true
      onUserScroll()
    }

    private func finishUserScroll(on scrollView: NSScrollView) {
      settleWorkItem?.cancel()
      settleWorkItem = nil
      wheelGestureOwnsViewport = false
      // The notification is delivered at the end of AppKit's live-scroll
      // transaction. Read the final clip bounds on the next main turn, after
      // the scroll view has committed its terminal position.
      let workItem = DispatchWorkItem { [weak self, weak scrollView] in
        guard let self, let scrollView, Self.isAtBottom(scrollView) else { return }
        self.onScrollSettledAtBottom()
        self.settleWorkItem = nil
      }
      settleWorkItem = workItem
      DispatchQueue.main.async(execute: workItem)
    }

    private func scheduleUnphasedWheelEnd(for scrollView: NSScrollView) {
      // Detent wheels and synthetic classic-wheel events do not always emit
      // AppKit's live-scroll start/end notifications. Debounce only that
      // unphased path. Trackpad and momentum events use didEndLiveScroll and
      // never depend on this wall-clock fallback.
      settleWorkItem?.cancel()
      let workItem = DispatchWorkItem { [weak self, weak scrollView] in
        guard let self else { return }
        self.wheelGestureOwnsViewport = false
        guard let scrollView, Self.isAtBottom(scrollView) else {
          self.settleWorkItem = nil
          return
        }
        self.onScrollSettledAtBottom()
        self.settleWorkItem = nil
      }
      settleWorkItem = workItem
      DispatchQueue.main.asyncAfter(
        deadline: .now() + Self.settledBottomDelay,
        execute: workItem
      )
    }

    private func scheduleDiscreteInputSettledBottomCheck(for scrollView: NSScrollView) {
      // Keyboard navigation and scrollbar mouse interaction do not reliably
      // participate in the live-scroll notification lifecycle. Keep a bounded
      // fallback for those discrete inputs only; wheel/trackpad gestures must
      // never use this timer because momentum can outlive it.
      settleWorkItem?.cancel()
      let workItem = DispatchWorkItem { [weak self, weak scrollView] in
        guard let self, let scrollView, Self.isAtBottom(scrollView) else { return }
        self.onScrollSettledAtBottom()
        self.settleWorkItem = nil
      }
      settleWorkItem = workItem
      DispatchQueue.main.asyncAfter(
        deadline: .now() + Self.settledBottomDelay,
        execute: workItem
      )
    }

    private static func scrollTop(of scrollView: NSScrollView) -> CGFloat {
      MainActor.assumeIsolated {
        guard let documentView = scrollView.documentView else { return 0 }
        let clipBounds = scrollView.contentView.bounds
        return ChatScrollLiveEdge.topBasedScrollOffset(
          clipOriginY: clipBounds.origin.y,
          viewportHeight: clipBounds.height,
          documentHeight: documentView.frame.height,
          isDocumentFlipped: documentView.isFlipped
        )
      }
    }

    private static func isAtBottom(_ scrollView: NSScrollView) -> Bool {
      MainActor.assumeIsolated {
        guard let documentView = scrollView.documentView else { return false }
        let clipBounds = scrollView.contentView.bounds
        let visibleMaxY = scrollTop(of: scrollView) + clipBounds.height
        return ChatScrollLiveEdge.isAtBottom(
          visibleMaxY: visibleMaxY,
          documentHeight: documentView.frame.height
        )
      }
    }

    deinit {
      settleWorkItem?.cancel()
      MainActor.assumeIsolated {
        stop()
      }
    }
  }
}

/// Explicit scroll intent model for streaming follow behavior.
enum ChatScrollMode: Equatable {
  case followingBottom
  case freeScrolling
}

/// Deterministic arrival policy shared by the main transcript's live edge.
/// A prompt materialized while opening Chat should be visible; the same prompt
/// arriving while the user reads history must leave their position untouched
/// and surface the existing jump-to-latest affordance instead.
enum ChatArrivalScrollPolicy {
  enum Action: Equatable {
    case restoreTail
    case followTail
    case preserveReadingPosition
    case none
  }

  static func action(oldCount: Int, newCount: Int, mode: ChatScrollMode) -> Action {
    guard newCount > oldCount else { return .none }
    if oldCount == 0 { return .restoreTail }
    return mode == .followingBottom ? .followTail : .preserveReadingPosition
  }
}

/// Keeps the same rows on screen after older messages are inserted above the
/// viewport — "Show older messages" / "Load earlier messages".
///
/// Inserting at the top of an NSScrollView leaves the clip origin at zero, which
/// is the newly loaded oldest row. Restore by the document-height delta, not by
/// hoping `scrollTo` wins a race with the click that triggered the load.
enum ChatTranscriptPrependPreservation {
  struct Snapshot: Equatable {
    let documentHeight: CGFloat
    let scrollTop: CGFloat
  }

  /// A click on the load-earlier control lives inside the transcript, so the
  /// content-size change that follows looks like the same press moved the clip
  /// view. That must not cancel the restore.
  static func shouldAbortRestoreBecauseUserIsScrolling(
    userIsScrolling: Bool,
    isPreservingPrepend: Bool
  ) -> Bool {
    userIsScrolling && !isPreservingPrepend
  }

  /// Restore work items clear the latch when they finish. If a later gesture
  /// cancels them first, that cleanup never runs. The load-more click still
  /// holds an anchor, so it must not be treated as a cancelled restore.
  static func shouldReleasePreserveLatchAfterCancellingRestore(
    isPreservingPrepend: Bool,
    prependAnchorId: String?
  ) -> Bool {
    isPreservingPrepend && prependAnchorId == nil
  }

  static func restoredScrollTop(
    previousDocumentHeight: CGFloat,
    previousScrollTop: CGFloat,
    newDocumentHeight: CGFloat
  ) -> CGFloat {
    previousScrollTop + max(0, newDocumentHeight - previousDocumentHeight)
  }

  /// Returns whether the clip view actually moved. Call after the new rows have
  /// been laid out so `documentView.frame.height` includes them.
  @MainActor
  @discardableResult
  static func apply(to scrollView: NSScrollView, snapshot: Snapshot) -> Bool {
    guard let documentView = scrollView.documentView else { return false }
    let newHeight = documentView.frame.height
    guard newHeight > snapshot.documentHeight + 1 else { return false }
    let newTop = restoredScrollTop(
      previousDocumentHeight: snapshot.documentHeight,
      previousScrollTop: snapshot.scrollTop,
      newDocumentHeight: newHeight
    )
    let viewportHeight = scrollView.contentView.bounds.height
    let originY =
      documentView.isFlipped
      ? newTop
      : newHeight - newTop - viewportHeight
    scrollView.contentView.scroll(to: NSPoint(x: 0, y: originY))
    scrollView.reflectScrolledClipView(scrollView.contentView)
    return true
  }
}

/// First-class chat scroll container used by floating/notch transcripts.
/// It follows streaming content only while the reader is at the live edge.
struct ChatScrollContainer<Content: View>: View {
  let bottomAnchorId: String
  let contentChangeToken: AnyHashable
  var showsJumpButton: Bool = true
  var scrollPaddingTrailing: CGFloat = 0
  var onContentHeightChange: ((CGFloat) -> Void)?
  @ViewBuilder var content: () -> Content

  @State private var scrollMode: ChatScrollMode = .followingBottom
  @State private var userIsScrolling = false
  @State private var hasActivityBelow = false
  @State private var scrollThrottleWorkItem: DispatchWorkItem?
  @State private var userScrollEndWorkItem: DispatchWorkItem?
  @State private var settleWorkItems: [DispatchWorkItem] = []
  @State private var lastViewportSize: CGSize = .zero
  @State private var lastFollowScrollTime: TimeInterval?
  @State private var hasQueuedFollowScroll = false

  var body: some View {
    ScrollViewReader { proxy in
      ZStack(alignment: .bottom) {
        ScrollView {
          VStack(alignment: .leading, spacing: OmiSpacing.lg) {
            content()
            Color.clear.frame(height: 1).id(bottomAnchorId)
          }
          .padding(.trailing, scrollPaddingTrailing)
          .background(contentHeightReporter)
          .background(scrollDetectors)
        }
        if showsJumpButton {
          jumpToLatestButton(proxy: proxy)
        }
      }
      .onAppear {
        scheduleSettledBottomFollow(proxy: proxy)
      }
      .onDisappear {
        cancelAllPendingScrolls()
      }
      .onChange(of: contentChangeToken) {
        handleLiveContentChange(proxy: proxy)
      }
      .background(viewportResizeDetector(proxy: proxy))
    }
  }

  private var contentHeightReporter: some View {
    GeometryReader { geometry -> Color in
      let height = geometry.size.height
      DispatchQueue.main.async {
        onContentHeightChange?(height)
      }
      return Color.clear
    }
  }

  private var scrollDetectors: some View {
    UserScrollDetector {
      scrollMode = .freeScrolling
      userIsScrolling = true
      hasActivityBelow = false
      cancelAllPendingScrolls()
      let endWork = DispatchWorkItem {
        userIsScrolling = false
      }
      userScrollEndWorkItem = endWork
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: endWork)
    } onScrollSettledAtBottom: {
      // Same contract as ChatMessagesView: the detector only reports a settle
      // once the input finished, so release the wall-clock latch here rather
      // than consulting it — it is still true on this very run-loop turn.
      userScrollEndWorkItem?.cancel()
      userScrollEndWorkItem = nil
      userIsScrolling = false
      guard
        ChatScrollLiveEdge.canResumeFollowing(
          source: .settledUserScroll,
          isAtBottom: true,
          userIsScrolling: userIsScrolling
        ), scrollMode == .freeScrolling
      else { return }
      cancelAllPendingScrolls()
      scrollMode = .followingBottom
      hasActivityBelow = false
    }
  }

  @ViewBuilder
  private func jumpToLatestButton(proxy: ScrollViewProxy) -> some View {
    if scrollMode == .freeScrolling {
      Button {
        cancelAllPendingScrolls()
        userIsScrolling = false
        scrollMode = .followingBottom
        hasActivityBelow = false
        scrollToBottom(proxy: proxy, animated: true)
      } label: {
        ZStack(alignment: .center) {
          Circle()
            .fill(Color.black.opacity(0.86))
            .frame(width: 34, height: 34)
            .shadow(color: .black.opacity(0.28), radius: 5, x: 0, y: 2)
          Image(systemName: "arrow.down.circle.fill")
            .scaledFont(size: 26)
            .foregroundColor(.white.opacity(0.86))
        }
        .overlay(
          Circle()
            .stroke(Color.white.opacity(hasActivityBelow ? 0.65 : 0), lineWidth: 1.5)
        )
        .opacity(hasActivityBelow ? 1 : 0.88)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Jump to latest message")
      .padding(.bottom, OmiSpacing.md)
      .transition(.scale.combined(with: .opacity))
    }
  }

  private func handleLiveContentChange(proxy: ScrollViewProxy) {
    if scrollMode == .followingBottom {
      throttledScrollToBottom(proxy: proxy)
      scheduleSettledBottomFollow(proxy: proxy)
    } else {
      hasActivityBelow = true
    }
  }

  private func scheduleSettledBottomFollow(proxy: ScrollViewProxy) {
    for item in settleWorkItems {
      item.cancel()
    }
    settleWorkItems.removeAll()

    for delay in [0.05, 0.16, 0.32] {
      let work = DispatchWorkItem {
        guard scrollMode == .followingBottom else { return }
        scrollToBottom(proxy: proxy, animated: false)
      }
      settleWorkItems.append(work)
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }
  }

  private func handleViewportSizeChange(_ size: CGSize, proxy: ScrollViewProxy) {
    guard size.width > 0, size.height > 0 else { return }
    guard size != lastViewportSize else { return }
    lastViewportSize = size
    guard scrollMode == .followingBottom, !userIsScrolling else { return }
    scrollToBottom(proxy: proxy, animated: false)
    scheduleSettledBottomFollow(proxy: proxy)
  }

  private func viewportResizeDetector(proxy: ScrollViewProxy) -> some View {
    GeometryReader { geometry in
      Color.clear
        .onAppear {
          handleViewportSizeChange(geometry.size, proxy: proxy)
        }
        .onChange(of: geometry.size) { _, newSize in
          handleViewportSizeChange(newSize, proxy: proxy)
        }
    }
  }

  private func scrollToBottom(proxy: ScrollViewProxy, animated: Bool) {
    guard scrollMode == .followingBottom, !userIsScrolling else { return }
    if animated {
      OmiMotion.withGated(.easeOut(duration: 0.15)) {
        proxy.scrollTo(bottomAnchorId, anchor: .bottom)
      }
    } else {
      proxy.scrollTo(bottomAnchorId, anchor: .bottom)
    }
  }

  /// Same contract and same reason as `ChatMessagesView`: this is a throttle, so
  /// a stream that never pauses still reaches the live edge every window.
  private func throttledScrollToBottom(proxy: ScrollViewProxy) {
    guard !userIsScrolling else { return }
    let now = ProcessInfo.processInfo.systemUptime
    switch ChatScrollFollowThrottle.decide(
      now: now, lastRun: lastFollowScrollTime, hasQueuedRun: hasQueuedFollowScroll)
    {
    case .alreadyScheduled:
      return
    case .now:
      lastFollowScrollTime = now
      scrollToBottom(proxy: proxy, animated: true)
    case .schedule(let delay):
      hasQueuedFollowScroll = true
      let workItem = DispatchWorkItem {
        hasQueuedFollowScroll = false
        lastFollowScrollTime = ProcessInfo.processInfo.systemUptime
        scrollToBottom(proxy: proxy, animated: true)
      }
      scrollThrottleWorkItem = workItem
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
    }
  }

  private func cancelAllPendingScrolls() {
    scrollThrottleWorkItem?.cancel()
    scrollThrottleWorkItem = nil
    if hasQueuedFollowScroll { hasQueuedFollowScroll = false }
    userScrollEndWorkItem?.cancel()
    userScrollEndWorkItem = nil
    for item in settleWorkItems {
      item.cancel()
    }
    settleWorkItems.removeAll()
  }
}
