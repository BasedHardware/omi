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

/// **The initial restore's settling passes, as a stability-seeking policy.**
///
/// A saved conversation must open at its live edge, and rich rows (Markdown
/// blocks, code, remote images) can expand across several SwiftUI layout turns
/// after the first placement, so the restore re-pins the live edge a few more
/// times before it declares itself settled. A fixed ladder long enough to cover
/// the slowest reflow made every switch pay the whole ladder even when the
/// document had already stopped changing after the first pass — the reader
/// watched a settled transcript keep "settling" for a full second.
///
/// A tighter ladder plus a stability check: a pass that measures the same
/// document height as the pass before it has nothing left to re-pin, so the
/// restore completes there and the remaining passes are cancelled. The ladder's
/// last pass still completes unconditionally, so a document that never holds
/// still for two consecutive passes reaches `.completed` exactly as before.
enum ChatInitialRestoreSettle {
  /// Tight enough that a transcript which lays out on an early pass settles in
  /// a fraction of a second; the stability check, not the ladder, owns the tail.
  static let delays: [TimeInterval] = [0.05, 0.1, 0.18, 0.3, 0.5]
  /// Sub-point drift between passes is not reflow.
  static let stabilityEpsilon: CGFloat = 0.5

  /// Whether a settling pass may complete the restore: the previous pass must
  /// have seen a laid-out document (a real height, not the pre-layout zero) and
  /// this pass must measure the same height within `stabilityEpsilon`.
  static func hasSettled(
    previousPassDocumentHeight: CGFloat?,
    currentDocumentHeight: CGFloat
  ) -> Bool {
    guard let previous = previousPassDocumentHeight, previous > 0,
      currentDocumentHeight > 0
    else { return false }
    return abs(currentDocumentHeight - previous) <= stabilityEpsilon
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
  /// The glide from one follow to the next. Shorter than `interval` so a
  /// follow always lands before the next one starts, and never a spring: the
  /// live edge has nothing to overshoot into.
  static let followDuration: TimeInterval = 0.16
  static let followAnimation: Animation = .easeOut(duration: followDuration)

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

/// **The follow glide's own clock.**
///
/// SwiftUI animation transactions and AppKit's animator proxy both advance on
/// the display cycle. A transcript mounted in a test host never reaches that
/// cycle, so when the glide rode `withAnimation`, the mounted-transcript guard
/// tests (INV-CHAT-2) watched the follow silently do nothing while the live
/// edge ran 484 pt past a 600 pt viewport — the exact abandonment this
/// surface's throttle exists to prevent, invisible to the one suite that
/// guards it. A run-loop timer is driven by the run loop itself, which the app
/// and the harness both pump, so the glide the reader feels is the glide the
/// tests measure.
///
/// Same shape as the easing it replaces (`followDuration`, ease-out): a newer
/// follow retargets the clock in flight rather than fighting it, and any
/// reader input cancels it outright.
@MainActor
final class ChatFollowGlide {
  /// 60 Hz — half of the follow throttle's own cadence, so a glide lands
  /// several steps before the next follow retargets.
  private static let stepInterval: TimeInterval = 1.0 / 60.0

  private var timer: Timer?
  private var isGliding = false

  /// True while a glide is moving the viewport. Reader input checks this the
  /// same way it checks a pending scroll.
  var isActive: Bool { isGliding }

  /// Eases `clipView` to `target` over `duration`. Returns false when there is
  /// nothing to ease — including the sub-point case, where the caller's snap
  /// path would be wasted work but is still correct.
  @discardableResult
  func glide(clipView: NSClipView, to target: NSPoint, duration: TimeInterval) -> Bool {
    cancel()
    let start = clipView.bounds.origin
    guard abs(start.y - target.y) > 0.5 else { return false }
    isGliding = true
    let began = Date()
    let step = Timer(timeInterval: Self.stepInterval, repeats: true) {
      [weak self, weak clipView] _ in
      MainActor.assumeIsolated {
        guard let self, let clipView, self.isGliding else {
          self?.cancel()
          return
        }
        let progress = Date().timeIntervalSince(began) / duration
        guard progress < 1 else {
          self.moveTo(target, in: clipView)
          self.cancel()
          return
        }
        // Ease-out cubic: fast while the reader's eye is on the arriving
        // text, settling as it reaches the live edge.
        let eased = 1 - pow(1 - progress, 3)
        var origin = start
        origin.y = start.y + (target.y - start.y) * eased
        self.moveTo(origin, in: clipView)
      }
    }
    timer = step
    RunLoop.main.add(step, forMode: .common)
    return true
  }

  /// Reader input and teardown call this; an in-flight glide must never fight
  /// the viewport's owner.
  func cancel() {
    timer?.invalidate()
    timer = nil
    isGliding = false
  }

  private func moveTo(_ origin: NSPoint, in clipView: NSClipView) {
    clipView.setBoundsOrigin(origin)
    if let scrollView = clipView.enclosingScrollView {
      scrollView.reflectScrolledClipView(clipView)
    }
  }
}

/// **Streaming tracks the live edge every tick, not every throttle window.**
///
/// A periodic follow glides toward the bottom measured when the follow fired —
/// but a paced stream grows the document every `ChatStreamingBuffer` flush
/// (35 ms), so by the time an 80 ms follow runs its target is stale: the
/// viewport decelerates into where the bottom *was*, waits while text lands
/// below it, then accelerates again. That velocity sawtooth is the jitter a
/// reader feels as up-and-down stutter. While a stream is live and the reader
/// owns the viewport, the pinner instead moves the clip view to the current
/// maximum scroll **every tick** whenever the document has grown — no target
/// math, nothing to go stale — so tracking is continuous and the only vertical
/// steps left are the text's own line wraps.
///
/// Positional tracking, not animation: it applies under Reduce Motion too.
/// Armed from the streaming follow path; disarmed by reader input, stream
/// end, scroll-mode change, conversation switch, and teardown through
/// `cancelAllPendingScrolls`. Each move is classified by the owner as the
/// app's own (the programmatic-scroll signal), so `UserScrollDetector` never
/// mistakes tracking for the reader taking the viewport.
@MainActor
final class ChatLiveEdgePinner {
  /// 60 Hz, matching the display cadence the glide's clock was built for.
  private static let tickInterval: TimeInterval = 1.0 / 60.0

  private var timer: Timer?
  private(set) var isPinning = false
  private var track: (() -> Void)?

  var isActive: Bool { isPinning }

  /// Begin (or keep) pinning. An already-armed pinner keeps its cadence and
  /// only refreshes the tracking closure — restarting the timer on every flush
  /// would reset the tick phase 28 times a second.
  func start(track: @escaping () -> Void) {
    self.track = track
    guard !isPinning else { return }
    isPinning = true
    let tick = Timer(timeInterval: Self.tickInterval, repeats: true) { [weak self] _ in
      MainActor.assumeIsolated {
        guard let self, self.isPinning else { return }
        self.track?()
      }
    }
    timer = tick
    RunLoop.main.add(tick, forMode: .common)
  }

  /// Reader input, stream end, and teardown call this; a pinner must never
  /// fight the viewport's owner.
  func cancel() {
    timer?.invalidate()
    timer = nil
    isPinning = false
    track = nil
  }
}

/// The moments the transcript moved its own viewport.
///
/// `UserScrollDetector` promotes an open mouse press to reader ownership as
/// soon as the clip view moves, because a scrollbar-track click repositions the
/// viewport without ever emitting a drag. That test could not tell the app's
/// own follow-scroll apart from the reader's: while an answer streams the
/// transcript re-reaches the live edge every
/// `ChatScrollFollowThrottle.interval`, so a press still open when one of those
/// lands reads as "the reader took the viewport" and ends follow mode for the
/// rest of the answer. Now that every content block is something you can click,
/// a press inside a streaming transcript is ordinary.
///
/// Read and written only on the main thread, like every other participant in
/// the transcript's scroll handling.
final class ChatProgrammaticScrollSignal: @unchecked Sendable {
  private(set) var lastScrollAt: TimeInterval?

  /// Call immediately *before* moving the viewport, so the bounds change AppKit
  /// posts afterwards falls inside the grace window.
  func markProgrammaticScroll(at now: TimeInterval = ProcessInfo.processInfo.systemUptime) {
    lastScrollAt = now
  }
}

/// Whether viewport movement observed during a press belongs to the reader.
enum ChatPressPromotionPolicy {
  /// How late a programmatic scroll's bounds change may still arrive. AppKit
  /// posts it on the same or the next main turn, so this only has to outlive a
  /// runloop hop — not a gesture.
  static let programmaticScrollGrace: TimeInterval = 0.2

  enum Movement: Equatable {
    /// The reader moved the viewport: the press owns it now.
    case promotesPress
    /// The transcript moved itself. Measure the reader's next movement from
    /// where it left the viewport rather than from where the press began,
    /// otherwise one follow-scroll's displacement is charged to the reader for
    /// as long as the press stays open.
    case rebaselines
    /// Nothing moved far enough to mean anything.
    case ignores
  }

  static func classify(
    movement: CGFloat,
    epsilon: CGFloat,
    now: TimeInterval,
    lastProgrammaticScrollAt: TimeInterval?
  ) -> Movement {
    guard abs(movement) >= epsilon else { return .ignores }
    guard let lastProgrammaticScrollAt else { return .promotesPress }
    let elapsed = now - lastProgrammaticScrollAt
    // A clock that went backwards must not hand the app an open-ended excuse to
    // discount reader movement.
    guard elapsed >= 0, elapsed <= programmaticScrollGrace else { return .promotesPress }
    return .rebaselines
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
  /// The transcript's own record of when it last moved the viewport. Shared so
  /// the coordinator can tell an app-driven bounds change from the reader's.
  let programmaticScroll: ChatProgrammaticScrollSignal
  let onUserScroll: () -> Void
  var onUserScrollEnded: () -> Void = {}
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
    Coordinator(
      onUserScroll: onUserScroll,
      programmaticScroll: programmaticScroll,
      onUserScrollEnded: onUserScrollEnded,
      onScrollSettledAtBottom: onScrollSettledAtBottom
    )
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    let onUserScroll: () -> Void
    let onUserScrollEnded: () -> Void
    let onScrollSettledAtBottom: () -> Void
    private let programmaticScroll: ChatProgrammaticScrollSignal
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
    private var nativeLiveScrollIsActive = false
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

    /// `programmaticScroll` defaults to a signal that has never fired — "the app
    /// has not moved the viewport" — which is what a coordinator built outside
    /// the transcript means. Production always passes the transcript's own.
    init(
      onUserScroll: @escaping () -> Void,
      programmaticScroll: ChatProgrammaticScrollSignal = ChatProgrammaticScrollSignal(),
      onUserScrollEnded: @escaping () -> Void = {},
      onScrollSettledAtBottom: @escaping () -> Void
    ) {
      self.onUserScroll = onUserScroll
      self.programmaticScroll = programmaticScroll
      self.onUserScrollEnded = onUserScrollEnded
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
          self?.beginNativeLiveScroll()
        }
        didEndLiveScrollObservation = NotificationCenter.default.addObserver(
          forName: NSScrollView.didEndLiveScrollNotification,
          object: targetScrollView,
          queue: .main
        ) { [weak self, weak targetScrollView] _ in
          guard let self, let targetScrollView else { return }
          self.finishNativeLiveScroll(on: targetScrollView)
        }
        verticalWheelPassthroughObservation = NotificationCenter.default.addObserver(
          forName: .chatVerticalWheelPassthrough,
          object: targetScrollView,
          queue: .main
        ) { [weak self, weak targetScrollView] notification in
          guard let self, let targetScrollView else { return }
          self.beginUserScroll()
          if let event = notification.userInfo?["event"] as? NSEvent,
            event.phase.isEmpty, event.momentumPhase.isEmpty,
            !self.nativeLiveScrollIsActive
          {
            self.scheduleUnphasedWheelEnd(for: targetScrollView)
          }
        }

        let handler: @MainActor (NSEvent) -> NSEvent? = { [weak self] event in
          guard let self else { return event }
          // A press must never outlive its own release. Clicking inside the
          // transcript can open something that presents in its own window — the
          // "Select Text\u{2026}" popover, a context menu — and the release is
          // then delivered there, where the same-window guard below dropped it.
          // The candidate would stay open for the life of the scroll view, and
          // the next follow-scroll promote it.
          if event.type == .leftMouseUp {
            self.endPressCandidate(on: targetScrollView)
            return event
          }
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
                if event.phase.isEmpty, event.momentumPhase.isEmpty,
                  !self.nativeLiveScrollIsActive
                {
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
        nativeLiveScrollIsActive = false
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
      // A press whose release never reached this monitor must not leave its
      // observer registered behind the new one.
      if let observation = pressBoundsObservation {
        NotificationCenter.default.removeObserver(observation)
        pressBoundsObservation = nil
      }
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
      let current = Self.scrollTop(of: scrollView)
      switch ChatPressPromotionPolicy.classify(
        movement: current - origin,
        epsilon: Self.dragMovementEpsilon,
        now: ProcessInfo.processInfo.systemUptime,
        lastProgrammaticScrollAt: programmaticScroll.lastScrollAt
      ) {
      case .ignores:
        return
      case .rebaselines:
        pressOriginScrollTop = current
      case .promotesPress:
        pressCandidateOwnsViewport = true
        onUserScroll()
      }
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

    private func beginNativeLiveScroll() {
      nativeLiveScrollIsActive = true
      beginUserScroll()
    }

    private func finishNativeLiveScroll(on scrollView: NSScrollView) {
      nativeLiveScrollIsActive = false
      finishUserScroll(on: scrollView)
    }

    private func finishUserScroll(on scrollView: NSScrollView) {
      settleWorkItem?.cancel()
      settleWorkItem = nil
      wheelGestureOwnsViewport = false
      // The notification is delivered at the end of AppKit's live-scroll
      // transaction. Read the final clip bounds on the next main turn, after
      // the scroll view has committed its terminal position.
      let workItem = DispatchWorkItem { [weak self, weak scrollView] in
        guard let self else { return }
        self.onUserScrollEnded()
        self.settleWorkItem = nil
        guard let scrollView, Self.isAtBottom(scrollView) else { return }
        self.onScrollSettledAtBottom()
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
        self.onUserScrollEnded()
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
        guard let self else { return }
        self.onUserScrollEnded()
        self.settleWorkItem = nil
        guard let scrollView, Self.isAtBottom(scrollView) else { return }
        self.onScrollSettledAtBottom()
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
  @State private var settleWorkItems: [DispatchWorkItem] = []
  @State private var lastViewportSize: CGSize = .zero
  @State private var lastFollowScrollTime: TimeInterval?
  @State private var hasQueuedFollowScroll = false
  /// Same contract as `ChatMessagesView`: a follow-scroll landing under an open
  /// press is the app moving the viewport, not the reader taking it.
  @State private var programmaticScroll = ChatProgrammaticScrollSignal()

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
    UserScrollDetector(programmaticScroll: programmaticScroll) {
      scrollMode = .freeScrolling
      userIsScrolling = true
      hasActivityBelow = false
      cancelAllPendingScrolls()
    } onUserScrollEnded: {
      userIsScrolling = false
    } onScrollSettledAtBottom: {
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
    programmaticScroll.markProgrammaticScroll()
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
    for item in settleWorkItems {
      item.cancel()
    }
    settleWorkItems.removeAll()
  }
}
