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

  /// Whether `window` has any registered surface at all. A window with none has nothing to judge
  /// a click against, so its caller must keep the window interactive rather than turn the whole
  /// thing into a pass-through hole (Reduce Transparency mounts no backdrop).
  package func hasSurfaces(in window: NSWindow) -> Bool {
    surfaceCount(in: window) > 0
  }

  /// Registered, visible surfaces for `window`. Exposed so the `debug_hit_probe` bridge action can
  /// say whether a pass-through verdict came from the geometry or from the empty-registry fallback.
  package func surfaceCount(in window: NSWindow) -> Int {
    views.allObjects.filter { isVisibleSurface($0, in: window) }.count
  }

  /// The one visibility rule, shared by the count and the point test. A faded-out panel that
  /// answered the count but owned no points would send the window down the geometry path with
  /// nothing in it, turning the whole shell click-through.
  private func isVisibleSurface(_ view: NSView, in window: NSWindow) -> Bool {
    view.window === window && !view.isHiddenOrHasHiddenAncestor && view.alphaValue > 0
  }

  /// Whether `pointInWindow` (window base coordinates, bottom-left origin) lies on any visible
  /// registered surface belonging to `window`.
  package func containsPoint(_ pointInWindow: NSPoint, in window: NSWindow) -> Bool {
    for view in views.allObjects {
      guard isVisibleSurface(view, in: window) else { continue }
      let local = view.convert(pointInWindow, from: nil)
      if InkGlassHitRegions.roundedRectContains(
        point: local,
        bounds: view.bounds,
        cornerRadius: (view as? InkGlassHitRegionView)?.cornerRadius ?? 0)
      {
        return true
      }
    }
    return false
  }

  /// A panel is a squircle, not a rectangle, so its corner cut-outs are desktop like any other air.
  /// Testing the bare bounds let each corner swallow clicks aimed at whatever is behind the window.
  package static func roundedRectContains(point: NSPoint, bounds: NSRect, cornerRadius: CGFloat)
    -> Bool
  {
    guard bounds.contains(point) else { return false }
    let radius = min(cornerRadius, min(bounds.width, bounds.height) / 2)
    guard radius > 0 else { return true }

    let insetX = min(max(point.x, bounds.minX + radius), bounds.maxX - radius)
    let insetY = min(max(point.y, bounds.minY + radius), bounds.maxY - radius)
    // Only corner points differ from their clamped position on both axes.
    let dx = point.x - insetX
    let dy = point.y - insetY
    guard dx != 0, dy != 0 else { return true }
    return (dx * dx + dy * dy) <= radius * radius
  }
}

/// Zero-drawing marker view: its own extent is reported as interactive content. Never intercepts
/// events itself — it exists only so `InkGlassHitRegions` can read its live frame.
package final class InkGlassHitRegionView: NSView {
  /// The panel's corner radius, so the registry can exclude the squircle's corner cut-outs.
  package var cornerRadius: CGFloat = 0

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

/// SwiftUI mount for the marker. Mount it inside the surface's own background stack so it spans
/// exactly the surface that should own the pointer.
package struct InkGlassHitRegionReporter: NSViewRepresentable {
  package var cornerRadius: CGFloat

  package init(cornerRadius: CGFloat = 0) {
    self.cornerRadius = cornerRadius
  }

  package func makeNSView(context: Context) -> InkGlassHitRegionView {
    let view = InkGlassHitRegionView(frame: .zero)
    view.cornerRadius = cornerRadius
    return view
  }

  package func updateNSView(_ view: InkGlassHitRegionView, context: Context) {
    view.cornerRadius = cornerRadius
  }
}
