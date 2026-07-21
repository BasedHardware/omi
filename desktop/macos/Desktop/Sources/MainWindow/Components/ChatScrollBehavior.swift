import AppKit
import OmiTheme
import SwiftUI

/// The narrow distance from the live edge that means the reader has actually
/// returned to it. A generous threshold makes a deliberate small upward scroll
/// look like "follow the stream" and pulls the reader back down on the next token.
enum ChatScrollLiveEdge {
  static let intentEpsilon: CGFloat = 2

  static func isAtBottom(visibleMaxY: CGFloat, documentHeight: CGFloat) -> Bool {
    visibleMaxY >= documentHeight - intentEpsilon
  }
}

/// Detects scroll position changes by observing the underlying NSScrollView.
struct ScrollPositionDetector: NSViewRepresentable {
  let onScrollPositionChange: (Bool) -> Void  // true if at bottom

  func makeNSView(context: Context) -> NSView {
    let view = NSView()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
      context.coordinator.setupScrollObserver(for: view)
    }
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {}

  func makeCoordinator() -> Coordinator {
    Coordinator(onScrollPositionChange: onScrollPositionChange)
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    let onScrollPositionChange: (Bool) -> Void
    private var scrollView: NSScrollView?
    private var observation: NSObjectProtocol?
    private var coalesceWorkItem: DispatchWorkItem?
    private var lastReportedValue: Bool?

    init(onScrollPositionChange: @escaping (Bool) -> Void) {
      self.onScrollPositionChange = onScrollPositionChange
    }

    func setupScrollObserver(for view: NSView) {
      MainActor.assumeIsolated {
        var current: NSView? = view
        while let v = current {
          if let sv = v as? NSScrollView {
            scrollView = sv
            break
          }
          current = v.superview
        }

        guard let scrollView else { return }
        let clipView = scrollView.contentView
        clipView.postsBoundsChangedNotifications = true
        observation = NotificationCenter.default.addObserver(
          forName: NSView.boundsDidChangeNotification,
          object: clipView,
          queue: .main
        ) { [weak self] _ in
          self?.checkScrollPosition()
        }

        checkScrollPosition()
      }
    }

    func checkScrollPosition() {
      MainActor.assumeIsolated {
        guard let scrollView, let documentView = scrollView.documentView else { return }

        let clipBounds = scrollView.contentView.bounds
        let documentHeight = documentView.frame.height
        let visibleMaxY = clipBounds.origin.y + clipBounds.height
        let isAtBottom = ChatScrollLiveEdge.isAtBottom(
          visibleMaxY: visibleMaxY,
          documentHeight: documentHeight
        )
        guard isAtBottom != lastReportedValue else { return }

        coalesceWorkItem?.cancel()
        let workItem = DispatchWorkItem { [weak self] in
          self?.lastReportedValue = isAtBottom
          self?.onScrollPositionChange(isAtBottom)
        }
        coalesceWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.06, execute: workItem)
      }
    }

    deinit {
      coalesceWorkItem?.cancel()
      if let observation {
        NotificationCenter.default.removeObserver(observation)
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
    let view = NSView()
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
      context.coordinator.install(for: view)
    }
    return view
  }

  func updateNSView(_ nsView: NSView, context: Context) {}

  func makeCoordinator() -> Coordinator {
    Coordinator(onUserScroll: onUserScroll, onScrollSettledAtBottom: onScrollSettledAtBottom)
  }

  final class Coordinator: NSObject, @unchecked Sendable {
    let onUserScroll: () -> Void
    let onScrollSettledAtBottom: () -> Void
    private var monitor: Any?

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

    func install(for view: NSView) {
      MainActor.assumeIsolated {
        var scrollView: NSScrollView?
        var current: NSView? = view
        while let v = current {
          if let sv = v as? NSScrollView {
            scrollView = sv
            break
          }
          current = v.superview
        }
        let targetScrollView = scrollView

        let handler: @MainActor (NSEvent) -> NSEvent? = { [weak self] event in
          guard let self, let targetScrollView else { return event }
          guard event.window == targetScrollView.window else { return event }

          if event.type == .keyDown {
            guard Self.scrollNavigationKeyCodes.contains(event.keyCode) else { return event }
            guard Self.isScrollViewKeyboardTarget(in: event.window, scrollView: targetScrollView) else { return event }
            self.onUserScroll()
          } else {
            let locationInScrollView = targetScrollView.convert(event.locationInWindow, from: nil)
            guard targetScrollView.bounds.contains(locationInScrollView) else { return event }
            if event.type == .scrollWheel {
              if event.scrollingDeltaY != 0 || event.scrollingDeltaX != 0 {
                self.onUserScroll()
              }
            } else {
              self.onUserScroll()
            }
          }
          self.scheduleSettledBottomChecks(for: targetScrollView)
          return event
        }
        monitor = NSEvent.addLocalMonitorForEvents(
          matching: [.scrollWheel, .leftMouseDown, .leftMouseDragged, .keyDown], handler: handler)
      }
    }

    private static func isScrollViewKeyboardTarget(in window: NSWindow?, scrollView: NSScrollView) -> Bool {
      MainActor.assumeIsolated {
        guard let window, let firstResponderView = window.firstResponder as? NSView else { return false }
        return firstResponderView === scrollView || firstResponderView.isDescendant(of: scrollView)
      }
    }

    private func scheduleSettledBottomChecks(for scrollView: NSScrollView) {
      for delay in [0.12, 0.36] {
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self, weak scrollView] in
          guard let self, let scrollView, Self.isAtBottom(scrollView) else { return }
          self.onScrollSettledAtBottom()
        }
      }
    }

    private static func isAtBottom(_ scrollView: NSScrollView) -> Bool {
      MainActor.assumeIsolated {
        guard let documentView = scrollView.documentView else { return false }
        let clipBounds = scrollView.contentView.bounds
        let documentHeight = documentView.frame.height
        let visibleMaxY = clipBounds.origin.y + clipBounds.height
        return ChatScrollLiveEdge.isAtBottom(
          visibleMaxY: visibleMaxY,
          documentHeight: documentHeight
        )
      }
    }

    deinit {
      if let monitor {
        NSEvent.removeMonitor(monitor)
      }
    }
  }
}

/// Explicit scroll intent model for streaming follow behavior.
enum ChatScrollMode: Equatable {
  case followingBottom
  case freeScrolling
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
    ZStack {
      ScrollPositionDetector { atBottom in
        if atBottom && scrollMode == .freeScrolling {
          cancelAllPendingScrolls()
          userIsScrolling = false
          scrollMode = .followingBottom
          hasActivityBelow = false
        }
      }
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
        guard scrollMode == .freeScrolling else { return }
        cancelAllPendingScrolls()
        userIsScrolling = false
        scrollMode = .followingBottom
        hasActivityBelow = false
      }
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
