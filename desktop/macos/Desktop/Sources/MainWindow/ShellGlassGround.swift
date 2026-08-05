//
//  ShellGlassGround.swift — who owns the main window's ground.
//
//  The ground used to be a SwiftUI `.background { … }` at the root of `DesktopHomeView`, and that is
//  the wrong owner for a reason that is invisible in the source and obvious on a screen.
//
//  **A SwiftUI background is laid out inside the hosting view's safe area.** The main window is
//  `.hiddenTitleBar`, so its `NSHostingView` reports `safeAreaInsets.top == 32` — the band the traffic
//  lights sit in. The ground therefore started 32 pt down: measured on the real app over a solid black
//  backdrop, the top 32 pt of the window read `(0,0,0)` — the backdrop straight through, no material,
//  no scrim — and the glass only began below it. `.ignoresSafeArea()` on the content does not move it,
//  because the inset is applied to the hosting view and not to anything the content can opt out of.
//  A window whose ground begins below its own title bar has *two* grounds by definition: a transparent
//  strip and a glass one, with a seam between them.
//
//  So the ground is AppKit's, and it is the window's `contentView` rather than a layer inside it. That
//  is the shape the design system was already built for — `InkGlassView` exists to *host* content, and
//  every other glass surface in the app (the floating bar, the onboarding cards) already reaches it
//  that way. The window then has one ground by construction: there is nowhere above it for SwiftUI to
//  put a second one, no safe area to be inset by, and the panel's own autoresizing keeps it exactly the
//  size of the content view through every resize.
//
//  Pairing this with `WindowGlass.wear` in one call is deliberate. Wearing the glass without the ground
//  is a transparent window with nothing in it, and installing the ground without wearing the glass is a
//  material with an opaque window background in front of the desktop. Both render. Neither is glass.
//
//  Brand: nothing here picks a colour at all — the material, the scrim and the light pin are `InkGlass`'s
//  (INV-UI-1).
//

import AppKit
import OmiTheme

/// The main window's one ground.
@MainActor
enum ShellGlassGround {
  /// Puts the window into the glass state **and** gives it the ground, in that order.
  ///
  /// Idempotent, because both call sites run more than once: launch applies it, and a summon re-applies
  /// it to a window that may have outlived the launch pass. A second call re-asserts the window
  /// properties and returns the ground already installed rather than stacking another one — two
  /// `NSVisualEffectView`s over the same desktop is the "muddy over one wallpaper, opaque over another"
  /// failure `InkGlass` is written to prevent.
  @discardableResult
  static func dress(_ window: NSWindow) -> InkGlassView {
    WindowGlass.wear(window, as: .titled)
    return install(in: window)
  }

  /// Installs the ground as the window's content view, re-parenting whatever was there into it.
  ///
  /// Split from `dress` so a test can drive the ground alone against a real `NSWindow` and read the
  /// frames back — the claim worth holding is geometric ("the ground *is* the content view"), and that
  /// is only observable once something has actually been mounted.
  @discardableResult
  static func install(in window: NSWindow) -> InkGlassView {
    if let ground = window.contentView as? InkGlassView { return ground }

    // Held across the assignment: setting `contentView` unparents the old one.
    let hosted = window.contentView
    let ground = InkGlassView(frame: hosted?.frame ?? .zero, style: GlassShell.groundStyle)
    window.contentView = ground
    // The panel is sized by `layout()`, and `setContent` measures against `panel.bounds`. Without this
    // the hosted view is installed at zero size and only recovers on the window's next resize.
    ground.layoutSubtreeIfNeeded()
    if let hosted { ground.setContent(hosted) }
    return ground
  }
}
