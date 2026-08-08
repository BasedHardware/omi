//
//  ActiveDisplay.swift — the one answer to "which display is the user working on?"
//
//  Every surface that has to land somewhere asks this, and for a long time each one answered it for
//  itself. `ShellSummon` walked the key window, then the main window, then the focused display. The
//  onboarding cinematic asked where the *pointer* was. On a two-display desk those disagree
//  constantly — the pointer parks on the idle monitor while the app runs on the other one — and the
//  cinematic played its full 8.6 seconds on a screen the user was not looking at, then handed off to
//  an onboarding window that opened on the screen they were. The intro appeared never to run.
//
//  So the question is asked in exactly one place, and the ordering is the whole content of it:
//
//  1. the key window's display — the window taking keystrokes is where the user is, full stop;
//  2. the main window's display — the app's frontmost window, when nothing holds focus yet;
//  3. the focused display (`NSScreen.main`) — AppKit's own answer about keyboard focus;
//  4. the pointer's display — only once every window-derived answer has declined. The pointer is a
//     weak signal (see the failure above), but when the app has no window on screen at all it is the
//     only evidence of the user that exists, and it beats picking a display by array index;
//  5. the first attached display — nothing left to go on.
//
//  A caller that wants a *specific* display passes one; this is the default, not an override.
//
//  Brand: nothing here picks a colour (INV-UI-1).
//

import AppKit
import Foundation

/// The choice, as arithmetic over injected inputs.
///
/// Split from the live lookup on purpose: the case that breaks is a second display, and a CI runner
/// has one screen (often none). Behind `NSApp` and `NSScreen` this ordering could only ever be
/// asserted by reading the source, which is not coverage. Here it is a value a hermetic test drives.
enum ActiveDisplayPolicy {
  /// Which signal produced the answer. Logged at the point of use, so "it played on the wrong
  /// screen" is a question the log can answer rather than a screenshot argument.
  enum Source: String, Sendable, CaseIterable {
    case keyWindow
    case mainWindow
    case focused
    case pointer
    case firstAttached
  }

  struct Choice: Equatable, Sendable {
    let index: Int
    let source: Source
  }

  /// Indices into the caller's screen list, in priority order. Out-of-range indices are skipped
  /// rather than trusted: `NSScreen.screens` can change between two reads while a display sleeps or
  /// is unplugged, and a stale index is how a placement lands on nothing.
  ///
  /// Returns `nil` only when there are no displays at all.
  static func choose(
    screenCount: Int,
    keyWindowScreen: Int?,
    mainWindowScreen: Int?,
    focusedScreen: Int?,
    pointerScreen: Int?
  ) -> Choice? {
    guard screenCount > 0 else { return nil }
    let ordered: [(Int?, Source)] = [
      (keyWindowScreen, .keyWindow),
      (mainWindowScreen, .mainWindow),
      (focusedScreen, .focused),
      (pointerScreen, .pointer),
      (0, .firstAttached),
    ]
    for (index, source) in ordered {
      guard let index, index >= 0, index < screenCount else { continue }
      return Choice(index: index, source: source)
    }
    return nil
  }
}

/// The live lookup. Main-actor because every input is `NSApp`/`NSScreen` state.
@MainActor
enum ActiveDisplay {
  struct Resolved {
    let screen: NSScreen
    let source: ActiveDisplayPolicy.Source
  }

  static func resolve() -> Resolved? {
    let screens = NSScreen.screens
    guard
      let choice = ActiveDisplayPolicy.choose(
        screenCount: screens.count,
        keyWindowScreen: index(of: NSApp.keyWindow?.screen, in: screens),
        mainWindowScreen: index(of: NSApp.mainWindow?.screen, in: screens),
        focusedScreen: index(of: NSScreen.main, in: screens),
        pointerScreen: pointerIndex(in: screens))
    else { return nil }
    return Resolved(screen: screens[choice.index], source: choice.source)
  }

  /// The display to land on, when the caller does not care which signal picked it.
  static func screen() -> NSScreen? { resolve()?.screen }

  /// A display, named the way a log reader needs it: the stable id first, so two lines about two
  /// screens can be told apart, then the human name and the geometry that makes it recognisable in a
  /// screenshot.
  static func describe(_ screen: NSScreen) -> String {
    let key = ShellSummonPlacement.displayKey(for: screen) ?? "?"
    let frame = screen.frame
    return
      "#\(key) \(screen.localizedName) \(Int(frame.width))x\(Int(frame.height))"
      + "@(\(Int(frame.minX)),\(Int(frame.minY)))"
  }

  /// Identity first, then the display id. `NSWindow.screen` normally hands back the very object in
  /// `NSScreen.screens`, but the array is rebuilt on configuration changes and a window can be
  /// holding the previous instance for the same physical display.
  private static func index(of screen: NSScreen?, in screens: [NSScreen]) -> Int? {
    guard let screen else { return nil }
    if let identical = screens.firstIndex(where: { $0 === screen }) { return identical }
    guard let key = ShellSummonPlacement.displayKey(for: screen) else { return nil }
    return screens.firstIndex { ShellSummonPlacement.displayKey(for: $0) == key }
  }

  private static func pointerIndex(in screens: [NSScreen]) -> Int? {
    let location = NSEvent.mouseLocation
    return screens.firstIndex { NSMouseInRect(location, $0.frame, false) }
  }
}
