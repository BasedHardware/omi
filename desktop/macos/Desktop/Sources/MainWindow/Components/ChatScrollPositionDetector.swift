import AppKit
import SwiftUI

/// An AppKit-owned snapshot of the transcript viewport. Sending this through
/// the scroll detector keeps scroll/layout measurement out of the SwiftUI
/// message stack, which otherwise risks an AttributeGraph feedback loop.
struct ChatScrollPosition: Equatable {
  let isAtBottom: Bool
  let scrollTop: CGFloat
  let viewportHeight: CGFloat
  let documentHeight: CGFloat
}

/// Detects scroll position changes by observing the underlying NSScrollView.
struct ScrollPositionDetector: NSViewRepresentable {
  let onScrollPositionChange: (ChatScrollPosition) -> Void
  var onScrollViewResolved: ((NSScrollView) -> Void)? = nil

  func makeNSView(context: Context) -> NSView {
    let view = ScrollPositionDetectorHostView()
    view.onHierarchyChange = { [weak coordinator = context.coordinator, weak view] in
      guard let coordinator, let view else { return }
      coordinator.scheduleAttachment(for: view)
    }
    context.coordinator.scheduleAttachment(for: view)
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {
    context.coordinator.onScrollViewResolved = onScrollViewResolved
    // SwiftUI can replace the underlying NSScrollView while a long stack is
    // being laid out. Re-check the hierarchy on every update so scrolling
    // does not remain wired to a detached clip view.
    context.coordinator.setupScrollObserver(for: nsView)
  }

  static func dismantleNSView(_ nsView: NSView, coordinator: Coordinator) {
    coordinator.stop()
  }

  func makeCoordinator() -> Coordinator {
    Coordinator(
      onScrollPositionChange: onScrollPositionChange,
      onScrollViewResolved: onScrollViewResolved
    )
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    /// `RunLoop.Mode.common` is not guaranteed to include AppKit's event
    /// tracking mode. Trackpad and wheel gestures run there, so an update
    /// queued only in common modes can leave `deliveryScheduled` latched until
    /// the gesture returns to the default run loop.
    private static let eventTrackingRunLoopMode = RunLoop.Mode("NSEventTrackingRunLoopMode")

    let onScrollPositionChange: (ChatScrollPosition) -> Void
    var onScrollViewResolved: ((NSScrollView) -> Void)?
    private var scrollView: NSScrollView?
    private weak var observedClipView: NSClipView?
    private weak var observedDocumentView: NSView?
    private var boundsObservation: NSObjectProtocol?
    private var documentFrameObservation: NSObjectProtocol?
    private var lastReportedPosition: ChatScrollPosition?
    private var pendingPosition: ChatScrollPosition?
    private var deliveryScheduled = false
    private var deliveryGeneration = 0

    init(
      onScrollPositionChange: @escaping (ChatScrollPosition) -> Void,
      onScrollViewResolved: ((NSScrollView) -> Void)?
    ) {
      self.onScrollPositionChange = onScrollPositionChange
      self.onScrollViewResolved = onScrollViewResolved
    }

    func scheduleAttachment(for view: NSView) {
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
        onScrollViewResolved?(targetScrollView)
        clipView.postsBoundsChangedNotifications = true
        boundsObservation = NotificationCenter.default.addObserver(
          forName: NSView.boundsDidChangeNotification,
          object: clipView,
          queue: .main
        ) { [weak self] _ in
          self?.checkScrollPosition()
        }

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

private final class ScrollPositionDetectorHostView: NSView {
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
