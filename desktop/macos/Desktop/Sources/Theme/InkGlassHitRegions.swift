//
//  InkGlassHitRegions.swift — where the visible glass actually is, for windows that are mostly air.
//
//  The main shell window is a transparent rectangle noticeably larger than the panels floating
//  inside it (`ShellWindowChrome`). The window server routes a click to the window under the
//  cursor regardless of what is drawn there, so every transparent region of that rectangle is an
//  invisible click sink over other apps — the "dead zone" class of bug first fixed for the notch
//  panel in PR #11372. The only working pass-through mechanism is `NSWindow.ignoresMouseEvents`,
//  and deciding when to set it needs one fact: is the pointer over visible content or over air?
//
//  This registry answers that with zero per-page wiring. Every glass surface in the product is
//  built from the two `InkGlass` primitives (`inkGlassPanel` / `InkGlassView` — "one glass"), so
//  those primitives register their extent here and a window-level policy can ask whether a point
//  lands on any of them. Pull-based on purpose: rects are read live from the AppKit views at
//  query time, so there is no stale-frame bookkeeping to drift during resizes or animations.
//
//  A surface that is *not* glass but must own the pointer (a modal barrier) mounts an
//  `InkGlassHitRegionReporter` explicitly — the marker is about interactivity, not material.
//

import AppKit
import SwiftUI

/// Registry of the views whose extent counts as visible, interactive content inside an otherwise
/// transparent window. Weakly held; querying skips views that left the window or are hidden.
@MainActor
package final class InkGlassHitRegions {
  package static let shared = InkGlassHitRegions()

  private let views = NSHashTable<NSView>.weakObjects()

  package func register(_ view: NSView) {
    views.add(view)
  }

  package func unregister(_ view: NSView) {
    views.remove(view)
  }

  /// Whether `pointInWindow` (window base coordinates, bottom-left origin) lies on any visible
  /// registered surface belonging to `window`.
  package func containsPoint(_ pointInWindow: NSPoint, in window: NSWindow) -> Bool {
    for view in views.allObjects {
      guard view.window === window,
        !view.isHiddenOrHasHiddenAncestor,
        view.alphaValue > 0
      else { continue }
      if view.convert(view.bounds, to: nil).contains(pointInWindow) {
        return true
      }
    }
    return false
  }
}

/// Zero-drawing marker view: its own extent is reported as interactive content. Never intercepts
/// events itself — it exists only so `InkGlassHitRegions` can read its live frame.
package final class InkGlassHitRegionView: NSView {
  package override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    if window == nil {
      InkGlassHitRegions.shared.unregister(self)
    } else {
      InkGlassHitRegions.shared.register(self)
    }
  }

  package override func hitTest(_ point: NSPoint) -> NSView? { nil }
}

/// SwiftUI mount for the marker. Attach as a `.background` so it spans exactly the surface that
/// should own the pointer.
package struct InkGlassHitRegionReporter: NSViewRepresentable {
  package init() {}

  package func makeNSView(context: Context) -> InkGlassHitRegionView {
    InkGlassHitRegionView(frame: .zero)
  }

  package func updateNSView(_ view: InkGlassHitRegionView, context: Context) {}
}
