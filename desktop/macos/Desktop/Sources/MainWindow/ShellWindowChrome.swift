//
//  ShellWindowChrome.swift — what the main window is, now that it has no ground and is summoned.
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
//    Controls, text fields and scroll views consume their own drags and are unaffected. Views that own
//    their own drags opt out with `mouseDownCanMoveWindow` (see `RewindTrackNSView`).
//
//  ## The two presentations, and why there are two
//
//  A surface with no visible chrome is not a conventional managed application window any more; it is a
//  thing you summon. `.summoned` says so to AppKit — floating level, so it comes up over whatever you were
//  reading and *stays* in front of it. `ShellSummon` owns where it lands.
//
//  ## Why it does not hide itself when it loses focus
//
//  It used to. `hidesOnDeactivate` is genuinely half of what makes a spotlight-style panel feel like
//  one — you press a chord, it appears; you click away, it is gone and you are back in your work — and
//  click-outside dismissal came free with it, with no click monitor to maintain.
//
//  It is the wrong half for this surface, because this shell is somewhere you *work*, not a launcher
//  you fire and forget. An answer streams into it, you go to the browser to check the thing it just
//  told you, you come back. With auto-hide, every one of those round trips deleted the window
//  mid-answer: click a browser, get a notification, switch to a terminal, and the panel evaporates.
//
//  And it did not merely disappear — it moved. A hidden window reports `isVisible == false`, which is
//  the exact input `ShellSummonPlacement.shouldReposition` reads to decide whether a summon should
//  re-land the shell. So the click that brought it back re-landed it, and a panel the user had dragged
//  somewhere snapped to the middle of the screen. Whether it did depended on whether AppKit had
//  finished restoring the window before `applicationDidBecomeActive` ran, so the same gesture moved the
//  window sometimes and not others. Non-deterministic placement is worse than either placement.
//
//  So `dress` writes `hidesOnDeactivate = false` in **both** presentations, and writes it rather than
//  leaving the property alone: this runs repeatedly on a window an earlier pass may already have hidden,
//  and a shell that vanishes mid-answer has no runtime signal whatsoever. Dismissal is explicit now —
//  `⌘W`, the menu bar item, or Escape (`ShellSummon`'s header has that route).
//
//  `.anchored` is the same window before the user has an account and a completed setup, and what
//  separates it is still behavioural rather than cosmetic. A first run sends people to System Settings
//  for microphone, screen recording and accessibility; a `.floating` window sits on top of the Settings
//  pane and covers the control the user was just told to click. So onboarding stays at `.normal` and
//  takes a Space of its own (`.fullScreenPrimary`), and the shell only becomes summonable once
//  `ShellSummon` can see a signed-in, onboarded user — with `dress` idempotent so the switch is a
//  re-dress, not a rebuild.
//
//  Brand: nothing here picks a colour at all (INV-UI-1).
//

import AppKit
import OmiTheme

/// The main window's chrome: transparent, light-pinned, and without the system's window buttons.
@MainActor
enum ShellWindowChrome {
  /// Whether the shell is a thing you summon, or a window that stays where you left it.
  ///
  /// Behavioural, not cosmetic — the two differ only in the AppKit properties that decide whether the
  /// window survives losing focus. See this file's header for why a first run needs the second.
  enum Presentation: Equatable, CaseIterable, Sendable {
    /// Steady state: floats over other apps and stays there until you put it away.
    case summoned
    /// Onboarding, sign-in and permission-granting: an ordinary window that keeps out of System
    /// Settings' way and can take a Space of its own.
    case anchored
  }

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

  /// The glass this window wears — **one kind, in both presentations.**
  ///
  /// It used to be `.titled` when anchored, and that was right for exactly as long as
  /// `ShellGlassGround` made the whole window one slab of glass: a titled window's frame *is* the
  /// panel's edge, so AppKit's window shadow is the correct one and the only one.
  ///
  /// The ground is gone. In **both** presentations the window is now a transparent rectangle
  /// noticeably larger than the panels floating inside it, which is precisely the case
  /// `WindowGlass.Kind.summoned` was written for — AppKit's shadow traces empty air. On the first-run
  /// window it did, and it is the most visible thing on the screen: a large rounded rectangle hanging
  /// on the wallpaper around a 540 × 640 onboarding card, reading as a second sheet of glass that the
  /// desktop is supposed to show through untouched.
  ///
  /// A constant rather than a function of the presentation, because that parameter had one job and no
  /// longer has it. `Presentation` is behavioural — level, Spaces, whether the window survives losing
  /// focus — and what a window's frame draws is not one of those.
  static let glassKind: WindowGlass.Kind = .summoned

  /// How the window joins Spaces.
  ///
  /// A summoned surface is `.fullScreenAuxiliary` — it comes up *over* whatever app is full-screen,
  /// which is the whole point of summoning it. An anchored one is `.fullScreenPrimary` so onboarding
  /// can take a Space of its own. The two are mutually exclusive, so a re-dress must subtract the
  /// other rather than only add its own; a window that accumulated both loses full-screen entirely.
  static func collectionBehavior(
    for presentation: Presentation,
    current: NSWindow.CollectionBehavior
  ) -> NSWindow.CollectionBehavior {
    var behavior = current
    behavior.insert(.moveToActiveSpace)
    if presentation == .summoned {
      behavior.remove(.fullScreenPrimary)
      behavior.insert(.fullScreenAuxiliary)
    } else {
      behavior.remove(.fullScreenAuxiliary)
      behavior.insert(.fullScreenPrimary)
    }
    return behavior
  }

  /// Puts the window into the state the shell needs, and nothing else.
  ///
  /// Idempotent, because all three call sites run more than once: launch applies it, a summon
  /// re-applies it to a window that may have outlived the launch pass, and completing onboarding
  /// re-applies it to switch presentations. Every step here is a property assignment, so a second pass
  /// re-asserts rather than accumulating.
  static func dress(_ window: NSWindow, as presentation: Presentation = .summoned) {
    WindowGlass.wear(window, as: glassKind)
    // Before hiding the buttons, never after: a window that lost the bits would otherwise spend the
    // window between the two calls with no way to be closed at all.
    window.styleMask.formUnion(keyboardWindowCommands)
    hideStandardButtons(in: window)
    window.isMovableByWindowBackground = true
    window.level = presentation == .summoned ? .floating : .normal
    // Always `false`, in both presentations, and asserted rather than omitted — see this file's
    // header. A shell that ordered itself out whenever another app took focus deleted the window
    // mid-answer and re-landed it on the way back; neither failure has any runtime signal.
    window.hidesOnDeactivate = false
    window.collectionBehavior = collectionBehavior(for: presentation, current: window.collectionBehavior)
  }

  /// Split from `dress` so a test can drive it against a real `NSWindow` and read the buttons back.
  static func hideStandardButtons(in window: NSWindow) {
    for button in hiddenStandardButtons {
      window.standardWindowButton(button)?.isHidden = true
    }
  }
}
