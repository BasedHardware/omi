//
//  SpineScrollLink.swift — the ribbon is the scrollbar.
//
//  The ribbon shows where the list is; wheeling over it should move the list. The tempting way to do
//  that is to give the ribbon its own scroll view and map its offset onto the list proportionally —
//  and that mapping is a lie, because spine rows are not the same height. A day of one conversation
//  and a day of forty occupy the same length of ribbon and wildly different lengths of list, so the
//  two would drift apart within a screen and the ribbon would stop being a position.
//
//  So there is exactly **one** scroll: the list's. A wheel over the ribbon is handed to the list's
//  `NSScrollView`, the list scrolls, the list reports its new top row, and the ribbon follows the way
//  it already does. Nothing to keep in sync, because nothing is second.
//

import AppKit
import SwiftUI

/// The list's scroll view, once AppKit has one. Held weakly and read on demand — nothing observes
/// this, so no publish and no redraw.
@MainActor
final class SpineScrollLink {
  /// Internal rather than `fileprivate` so the forwarding arithmetic below — direction, line
  /// conversion, clamping — is reachable by a test. Nothing outside this file assigns it.
  weak var scrollView: NSScrollView?

  /// Applies one wheel event's worth of movement to the list. `false` when there is no list to
  /// scroll yet, so the caller can fall through to normal event handling.
  ///
  /// **The offset is computed here rather than handed to `NSScrollView.scrollWheel(with:)`, and
  /// that is not a preference — forwarding does not work.** A real trackpad or Magic Mouse event
  /// carries a gesture `phase`, and AppKit routes those through responsive scrolling, which tracks
  /// the gesture against the view that was actually hit. A scroll view told to handle an event it
  /// was not hit for ignores it, so the list simply did not move. The bug hid behind the test for
  /// it: a synthetic `CGEvent` has no phase, takes the legacy path, and scrolls — so forwarding
  /// looked verified while a real two-finger swipe over the ribbon did nothing at all.
  ///
  /// Momentum is not lost by doing the arithmetic here. macOS delivers the coast after a flick as
  /// its own stream of events with decaying deltas, so applying each one as it arrives *is* the
  /// inertia; there is nothing for `NSScrollView` to add that the events do not already carry.
  @discardableResult
  func scroll(by event: NSEvent) -> Bool {
    guard let scrollView, let document = scrollView.documentView else { return false }
    let clip = scrollView.contentView
    // Precise deltas are already in points. Line-based ones (an old mouse wheel) are in lines.
    let delta = event.hasPreciseScrollingDeltas ? event.scrollingDeltaY : event.scrollingDeltaY * 16
    guard delta != 0 else { return true }
    let limit = max(0, document.frame.height - clip.bounds.height)
    var origin = clip.bounds.origin
    origin.y = min(max(0, origin.y - delta), limit)
    guard origin.y != clip.bounds.origin.y else { return true }
    clip.scroll(to: origin)
    scrollView.reflectScrolledClipView(clip)
    return true
  }
}

/// Put behind the list's content: finds the scroll view SwiftUI made and hands it to the link.
struct SpineScrollAnchor: NSViewRepresentable {
  let link: SpineScrollLink

  func makeNSView(context: Context) -> NSView { AnchorView(link: link) }

  func updateNSView(_ nsView: NSView, context: Context) {
    (nsView as? AnchorView)?.resolve()
  }

  private final class AnchorView: NSView {
    private let link: SpineScrollLink

    init(link: SpineScrollLink) {
      self.link = link
      super.init(frame: .zero)
    }

    @available(*, unavailable) required init?(coder: NSCoder) { nil }

    override func viewDidMoveToWindow() {
      super.viewDidMoveToWindow()
      resolve()
    }

    /// SwiftUI can replace the backing scroll view while a long list is laid out, so this re-reads
    /// rather than latching once — but only when what it holds has actually gone. `updateNSView`
    /// runs on every re-evaluation of the list, which during a scroll is constant, and walking the
    /// view hierarchy each time is work on the one thread the scroll needs.
    func resolve() {
      guard link.scrollView == nil || link.scrollView?.window == nil else { return }
      link.scrollView = enclosingScrollView
    }
  }
}

/// Put over the ribbon: turns a wheel there into a scroll of the list.
struct SpineWheelForwarder: NSViewRepresentable {
  let link: SpineScrollLink

  func makeNSView(context: Context) -> NSView { ForwarderView(link: link) }

  func updateNSView(_ nsView: NSView, context: Context) {}

  private final class ForwarderView: NSView {
    private let link: SpineScrollLink

    init(link: SpineScrollLink) {
      self.link = link
      super.init(frame: .zero)
    }

    @available(*, unavailable) required init?(coder: NSCoder) { nil }

    /// The wheel is the only thing this takes. It answers `hitTest` because AppKit routes scroll
    /// events through it, but it adds no click, drag or gesture — the ribbon is a scrollbar, not a
    /// scrubber.
    override func scrollWheel(with event: NSEvent) {
      if !link.scroll(by: event) { super.scrollWheel(with: event) }
    }
  }
}
