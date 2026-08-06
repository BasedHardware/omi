//
//  ShellWindowChrome.swift — what the main window is, now that it has no ground.
//
//  This file replaces `ShellGlassGround`, and the reason it replaces it rather than extends it is the
//  whole shape of the shell.
//
//  The ground was an `InkGlassView` installed as the window's `contentView`, so the entire window was
//  one full-bleed slab of glass and every panel floated *on that slab*. It was the right answer to the
//  bug it was written for — a SwiftUI `.background { … }` is laid out inside the hosting view's safe
//  area, and `.hiddenTitleBar` reports `safeAreaInsets.top == 32`, so a SwiftUI ground starts 32 pt down
//  and the top strip shows the backdrop straight through. AppKit ownership fixed that. But it answered
//  the wrong question: the product wants **no ground at all**. What is behind a panel is the user's
//  wallpaper, the way it is behind the surfaces this design system was ported from.
//
//  So the window is now genuinely transparent (`WindowGlass.wear`, which is `isOpaque = false` plus a
//  clear `backgroundColor`) and every surface positions and grounds itself: the top bar, Home's two
//  panels, and `PageGlassLane` for every other destination. **Do not reintroduce a full-bleed SwiftUI
//  background here** — that is the 32 pt seam, drawn again.
//
//  ## The chrome that had to go with it
//
//  A window with no ground still had three coloured circles hanging on the wallpaper at its top-left:
//  the traffic lights, drawn by AppKit over whatever happened to be behind the window, attached to
//  nothing. They read as a rendering fault rather than as controls. So they are hidden, and the two
//  things they were the only visible affordance for are guaranteed another way:
//
//  - **Closing and minimising are style-mask facts, not button facts.** `⌘W` and `⌘M` are routed by
//    AppKit from `.closable` / `.miniaturizable`; hiding `standardWindowButton(_:)` hides a view and
//    changes no behaviour. `dress` re-asserts both bits so a future window-construction change cannot
//    strand a user in a window with no visible close control *and* no keyboard one.
//  - **Moving has two handles, deliberately.** `.hiddenTitleBar` keeps a real (transparent) title bar
//    over the top band, which still drags — that band is why the shell reserves
//    `GlassShell.titlebarClearance` and draws nothing in it. `isMovableByWindowBackground` adds the
//    second: on a window that is mostly desktop, the parts that are not a control drag it too, which is
//    how the bar this file's chrome sits in becomes a drag handle without any view knowing it is one.
//    Controls, text fields and scroll views consume their own drags and are unaffected.
//
//  Brand: nothing here picks a colour at all (INV-UI-1).
//

import AppKit
import OmiTheme

/// The main window's chrome: transparent, light-pinned, and without the system's window buttons.
@MainActor
enum ShellWindowChrome {
  /// The style-mask bits `⌘W` and `⌘M` are routed by.
  ///
  /// Named rather than written inline because the whole safety argument for hiding the buttons is that
  /// these two survive, and a claim a test can read is worth more than a comment saying so.
  static let keyboardWindowCommands: NSWindow.StyleMask = [.closable, .miniaturizable]

  /// The buttons that stop being drawn. All three: a lone close button on a chrome-less window reads
  /// as a stray more strongly than three do.
  static let hiddenStandardButtons: [NSWindow.ButtonType] = [
    .closeButton, .miniaturizeButton, .zoomButton,
  ]

  /// Puts the window into the state the shell needs, and nothing else.
  ///
  /// Idempotent, because both call sites run more than once: launch applies it, and a summon re-applies
  /// it to a window that may have outlived the launch pass. Every step here is a property assignment,
  /// so a second pass re-asserts rather than accumulating.
  static func dress(_ window: NSWindow) {
    WindowGlass.wear(window, as: .titled)
    // Before hiding the buttons, never after: a window that lost the bits would otherwise spend the
    // window between the two calls with no way to be closed at all.
    window.styleMask.formUnion(keyboardWindowCommands)
    hideStandardButtons(in: window)
    window.isMovableByWindowBackground = true
  }

  /// Split from `dress` so a test can drive it against a real `NSWindow` and read the buttons back.
  static func hideStandardButtons(in window: NSWindow) {
    for button in hiddenStandardButtons {
      window.standardWindowButton(button)?.isHidden = true
    }
  }
}
