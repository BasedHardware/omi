import AppKit
import OmiTheme
import SwiftUI

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
  static let initialRestoreSettlingDelays: [TimeInterval] = [0.05, 0.2, 0.5]

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

/// Detects scroll position changes by observing the underlying NSScrollView.
struct ScrollPositionDetector: NSViewRepresentable {
  let onScrollPositionChange: (ChatScrollPosition) -> Void

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
    // SwiftUI can replace the underlying NSScrollView while a long LazyVStack
    // is being laid out. Re-check the hierarchy on every update so scrolling
    // does not remain wired to a detached clip view.
    context.coordinator.setupScrollObserver(for: nsView)
  }

  static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
    coordinator.stop()
  }

  func makeCoordinator() -> Coordinator {
    Coordinator(onScrollPositionChange: onScrollPositionChange)
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    /// `RunLoop.Mode.common` is not guaranteed to include AppKit's event
    /// tracking mode. Trackpad and wheel gestures run there, so an update
    /// queued only in common modes can leave `deliveryScheduled` latched until
    /// the gesture returns to the default run loop.
    private static let eventTrackingRunLoopMode = RunLoop.Mode("NSEventTrackingRunLoopMode")

    let onScrollPositionChange: (ChatScrollPosition) -> Void
    private var scrollView: NSScrollView?
    private weak var observedClipView: NSClipView?
    private weak var observedDocumentView: NSView?
    private var boundsObservation: NSObjectProtocol?
    private var documentFrameObservation: NSObjectProtocol?
    private var lastReportedPosition: ChatScrollPosition?
    private var pendingPosition: ChatScrollPosition?
    private var deliveryScheduled = false
    private var deliveryGeneration = 0

    init(onScrollPositionChange: @escaping (ChatScrollPosition) -> Void) {
      self.onScrollPositionChange = onScrollPositionChange
    }

    func scheduleAttachment(for view: NSView) {
      // The representable can be created before SwiftUI inserts it into the
      // document hierarchy, and a fast LazyVStack replacement can briefly
      // detach it. Retry on common run-loop turns so a temporary absence does
      // not leave the detector attached to a dead scroll view.
      for delay in [0.0, 0.05, 0.2] {
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self, weak view] in
          guard let self, let view else { return }
          self.setupScrollObserver(for: view)
        }
      }
    }

    func setupScrollObserver(for view: NSView) {
      MainActor.assumeIsolated {
        guard let targetScrollView = Self.enclosingScrollView(for: view) else {
          // Do not keep reporting from an old clip view while SwiftUI is
          // replacing the transcript hierarchy. The host view will retry when
          // it is inserted into the replacement scroll view.
          stop()
          return
        }
        let clipView = targetScrollView.contentView
        let documentView = targetScrollView.documentView

        if scrollView === targetScrollView,
          observedClipView === clipView,
          observedDocumentView === documentView
        {
          checkScrollPosition()
          return
        }

        stop()
        scrollView = targetScrollView
        observedClipView = clipView
        observedDocumentView = documentView
        clipView.postsBoundsChangedNotifications = true
        boundsObservation = NotificationCenter.default.addObserver(
          forName: NSView.boundsDidChangeNotification,
          object: clipView,
          queue: .main
        ) { [weak self] _ in
          self?.checkScrollPosition()
        }

        // Document growth is just as important as reader movement: it is how
        // the rail learns that a streaming final response changed the true live
        // edge. Observe it from AppKit rather than feeding SwiftUI geometry
        // measurements back into the transcript's own layout pass.
        if let documentView {
          documentView.postsFrameChangedNotifications = true
          documentFrameObservation = NotificationCenter.default.addObserver(
            forName: NSView.frameDidChangeNotification,
            object: documentView,
            queue: .main
          ) { [weak self] _ in
            self?.checkScrollPosition()
          }
        }

        checkScrollPosition()
      }
    }

    func stop() {
      MainActor.assumeIsolated {
        deliveryGeneration &+= 1
        deliveryScheduled = false
        pendingPosition = nil
        lastReportedPosition = nil
        if let boundsObservation {
          NotificationCenter.default.removeObserver(boundsObservation)
        }
        boundsObservation = nil
        if let documentFrameObservation {
          NotificationCenter.default.removeObserver(documentFrameObservation)
        }
        documentFrameObservation = nil
        scrollView = nil
        observedClipView = nil
        observedDocumentView = nil
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

    func checkScrollPosition() {
      MainActor.assumeIsolated {
        guard let scrollView, let documentView = scrollView.documentView else { return }

        let clipBounds = scrollView.contentView.bounds
        let documentHeight = documentView.frame.height
        let scrollTop = ChatScrollLiveEdge.topBasedScrollOffset(
          clipOriginY: clipBounds.origin.y,
          viewportHeight: clipBounds.height,
          documentHeight: documentHeight,
          isDocumentFlipped: documentView.isFlipped
        )
        let visibleMaxY = scrollTop + clipBounds.height
        let position = ChatScrollPosition(
          isAtBottom: ChatScrollLiveEdge.isAtBottom(
            visibleMaxY: visibleMaxY,
            documentHeight: documentHeight),
          scrollTop: scrollTop,
          viewportHeight: clipBounds.height,
          documentHeight: documentHeight
        )
        let hasPendingDelivery = pendingPosition != nil
        guard hasPendingDelivery || shouldReport(position) else { return }
        pendingPosition = position
        guard !deliveryScheduled else { return }

        deliveryScheduled = true
        let generation = deliveryGeneration
        // Deliver in the mode that is actually servicing the gesture as well
        // as the ordinary/common modes. The block is one-shot, so listing the
        // modes does not duplicate a callback when the run loop changes mode.
        RunLoop.main.perform(
          inModes: [.common, .default, Self.eventTrackingRunLoopMode]
        ) { [weak self] in
          MainActor.assumeIsolated {
            guard let self, self.deliveryGeneration == generation else { return }
            self.deliveryScheduled = false
            guard let pendingPosition = self.pendingPosition else { return }
            self.pendingPosition = nil
            self.lastReportedPosition = pendingPosition
            self.onScrollPositionChange(pendingPosition)
          }
        }
      }
    }

    private func shouldReport(_ position: ChatScrollPosition) -> Bool {
      guard let lastReportedPosition else { return true }
      return position.isAtBottom != lastReportedPosition.isAtBottom
        || abs(position.scrollTop - lastReportedPosition.scrollTop) >= 4
        || abs(position.viewportHeight - lastReportedPosition.viewportHeight) >= 4
        || abs(position.documentHeight - lastReportedPosition.documentHeight) >= 4
    }

    deinit {
      MainActor.assumeIsolated {
        stop()
      }
    }
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

/// An AppKit-owned snapshot of the transcript viewport. Sending this through
/// the scroll detector keeps scroll/layout measurement out of the SwiftUI
/// `LazyVStack`, which otherwise risks an AttributeGraph feedback loop.
struct ChatScrollPosition: Equatable {
  let isAtBottom: Bool
  let scrollTop: CGFloat
  let viewportHeight: CGFloat
  let documentHeight: CGFloat
}

/// Reports a user prompt's document position after AppKit has completed its
/// layout. SwiftUI geometry actions inside the transcript's `LazyVStack` used
/// to feed those measurements back into the same layout transaction and could
/// pin the main thread in AttributeGraph. This bridge keeps the prompt rail's
/// exact ordering without reintroducing that feedback edge.
struct ChatPromptRowAnchorReporter: NSViewRepresentable {
  let markID: String
  let geometry: ChatTranscriptGeometry

  func makeNSView(context: Context) -> NSView {
    let view = NSView()
    context.coordinator.configure(view: view, markID: markID, geometry: geometry)
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {
    context.coordinator.configure(view: nsView, markID: markID, geometry: geometry)
  }

  static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
    coordinator.stop()
  }

  func makeCoordinator() -> Coordinator {
    Coordinator()
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    private weak var view: NSView?
    private weak var geometry: ChatTranscriptGeometry?
    private var markID = ""
    private var frameObservation: NSObjectProtocol?
    private var reportWorkItem: DispatchWorkItem?

    func configure(view: NSView, markID: String, geometry: ChatTranscriptGeometry) {
      MainActor.assumeIsolated {
        let isNewAnchor = self.view !== view || self.markID != markID || self.geometry !== geometry
        guard isNewAnchor else { return }
        stop()
        self.view = view
        self.markID = markID
        self.geometry = geometry
        view.postsFrameChangedNotifications = true
        frameObservation = NotificationCenter.default.addObserver(
          forName: NSView.frameDidChangeNotification,
          object: view,
          queue: .main
        ) { [weak self] _ in
          self?.scheduleReport()
        }
        scheduleReport()
      }
    }

    func stop() {
      MainActor.assumeIsolated {
        reportWorkItem?.cancel()
        reportWorkItem = nil
        if let frameObservation {
          NotificationCenter.default.removeObserver(frameObservation)
        }
        frameObservation = nil
        view = nil
        geometry = nil
      }
    }

    private func scheduleReport() {
      MainActor.assumeIsolated {
        reportWorkItem?.cancel()
        let work = DispatchWorkItem { [weak self] in
          MainActor.assumeIsolated {
            guard let self, let view = self.view, let geometry = self.geometry else { return }
            guard let documentView = Self.enclosingScrollView(for: view)?.documentView else { return }
            let origin = view.convert(view.bounds.origin, to: documentView)
            let offset =
              documentView.isFlipped
              ? origin.y
              : documentView.bounds.height - origin.y - view.bounds.height
            geometry.setRowOffset(offset, for: self.markID)
          }
        }
        reportWorkItem = work
        DispatchQueue.main.async(execute: work)
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

    deinit {
      MainActor.assumeIsolated {
        stop()
      }
    }
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

  private func throttledScrollToBottom(proxy: ScrollViewProxy) {
    guard !userIsScrolling else { return }
    scrollThrottleWorkItem?.cancel()
    let workItem = DispatchWorkItem {
      scrollToBottom(proxy: proxy, animated: true)
    }
    scrollThrottleWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.08, execute: workItem)
  }

  private func cancelAllPendingScrolls() {
    scrollThrottleWorkItem?.cancel()
    scrollThrottleWorkItem = nil
    userScrollEndWorkItem?.cancel()
    userScrollEndWorkItem = nil
    for item in settleWorkItems {
      item.cancel()
    }
    settleWorkItems.removeAll()
  }
}
