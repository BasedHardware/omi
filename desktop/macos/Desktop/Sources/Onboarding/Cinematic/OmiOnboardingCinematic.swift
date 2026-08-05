import AppKit
import Foundation
import OmiTheme
import SwiftUI

//  The one entry point onboarding calls.
//
//  Two surfaces, and they are independent on purpose:
//
//  - `present(on:completion:)` plays the six-beat intro on a full-screen window and calls back
//    exactly once, whatever happens — completed, skipped, or the watchdog. The caller then shows
//    whatever onboarding it was going to show; this never touches that flow.
//  - `music` is the ambient bed on its own. The chat-style onboarding runs under the same bed
//    without any of the intro, so starting and stopping it has to be callable without a cinematic
//    ever existing. The bed's mute control is persisted and is the same one the intro's speaker
//    button toggles.
//
//  Nothing here can fail into a state where onboarding does not arrive: if the window cannot be
//  made, `completion` is called on the same turn.

@MainActor
enum OmiOnboardingCinematic {
  // MARK: - The intro

  /// The window the intro plays on. `nil` whenever no run is in flight.
  private static var window: NSWindow?
  private static var hosting: NSView?
  private static var director: OmiCinematicDirector?
  private static var escapeMonitor: Any?

  /// True while a run is on screen. A second `present` while one is playing is a no-op that still
  /// calls back, so a caller can never be left waiting on a completion that never comes.
  static var isPresenting: Bool { window != nil }

  /// Plays the intro on `screen` (the display under the pointer by default) and calls `completion`
  /// exactly once, on the main actor, when it ends.
  ///
  /// - Parameters:
  ///   - screen: the display to cover. Defaults to the one the pointer is on, falling back to the
  ///     main screen.
  ///   - timing: injectable so a caller — or a test — can force the reduced table. Defaults to
  ///     whichever table the machine's Reduce Motion setting selects.
  ///   - completion: the terminal outcome. Always called, always once, on the main actor —
  ///     `@MainActor` on the closure type is what lets the hand-off survive the one `@Sendable`
  ///     boundary on this path (`NSAnimationContext`'s completion handler).
  static func present(
    on screen: NSScreen? = nil,
    timing: OmiCinematicTiming = .current,
    completion: @escaping @MainActor (OmiCinematicEnd) -> Void
  ) {
    guard !isPresenting else {
      // Already playing. Whoever asked second still gets an answer rather than a hang.
      completion(.skipped(.dim))
      return
    }

    guard let target = screen ?? screenUnderPointer() else {
      logError("cinematic: no screen to present on; handing straight off to onboarding")
      completion(.expired(.dim))
      return
    }

    let frame = target.frame
    let panel = makeWindow(contentRect: frame)
    // Above `.mainMenu` (24), so the scrim covers the menu bar and the Dock. A dim with a bright
    // strip along the top is not a dim.
    panel.level = .statusBar

    let cinematic = OmiCinematicDirector(timing: timing)

    // CRITICAL: the hosting view goes *inside* a plain container and is never the window's
    // `contentView`. An `NSHostingView` that is the contentView of a borderless window negotiates
    // the window's size and can crash in `_postWindowNeedsUpdateConstraints` on recent macOS.
    let container = NSView(frame: NSRect(origin: .zero, size: frame.size))
    container.autoresizingMask = [.width, .height]

    let host = NSHostingView(rootView: OmiCinematicView(director: cinematic))
    host.frame = container.bounds
    host.autoresizingMask = [.width, .height]
    container.addSubview(host)

    panel.contentView = container
    panel.setFrame(frame, display: true)

    window = panel
    hosting = host
    director = cinematic

    panel.makeKeyAndOrderFront(nil)
    NSApp.activate(ignoringOtherApps: true)
    installEscapeMonitor(cinematic)

    cinematic.start { end in
      MainActor.assumeIsolated { land(after: end, completion: completion) }
    }
  }

  /// Tears the intro down without waiting for it. Used when something else has to take the screen;
  /// the completion the caller passed to `present` still fires, with `.skipped`.
  static func dismiss() {
    director?.skip()
  }

  /// Beat 6's landing: the composition is already at zero opacity by the time a completed run gets
  /// here, so the window can simply go. An abort has *not* faded, so it gets a short one.
  private static func land(
    after end: OmiCinematicEnd,
    completion: @escaping @MainActor (OmiCinematicEnd) -> Void
  ) {
    removeEscapeMonitor()
    director = nil
    hosting?.removeFromSuperview()
    hosting = nil

    guard let panel = window else {
      completion(end)
      return
    }
    window = nil

    let duration = end.wasInterrupted && !OmiMotion.reduceMotion ? OmiCinematicTiming.crossFade : 0
    guard duration > 0 else {
      panel.orderOut(nil)
      log("cinematic handed off to onboarding (\(end))")
      completion(end)
      return
    }

    NSAnimationContext.runAnimationGroup(
      { context in
        context.duration = duration
        context.timingFunction = CAMediaTimingFunction(name: .easeOut)
        panel.animator().alphaValue = 0
      },
      completionHandler: {
        MainActor.assumeIsolated {
          panel.orderOut(nil)
          log("cinematic handed off to onboarding (\(end))")
          completion(end)
        }
      })
  }

  private static func makeWindow(contentRect: NSRect) -> NSWindow {
    let panel = NSWindow(
      contentRect: contentRect,
      styleMask: [.borderless],
      backing: .buffered,
      defer: false)
    panel.isOpaque = false
    panel.backgroundColor = .clear
    panel.hasShadow = false
    panel.isMovable = false
    panel.ignoresMouseEvents = false
    panel.collectionBehavior = [.fullScreenAuxiliary, .canJoinAllSpaces, .stationary]
    return panel
  }

  private static func screenUnderPointer() -> NSScreen? {
    let location = NSEvent.mouseLocation
    return NSScreen.screens.first { NSMouseInRect(location, $0.frame, false) } ?? NSScreen.main
  }

  /// Esc, at the AppKit level.
  ///
  /// The Skip button already carries `.keyboardShortcut(.cancelAction)`, but whether AppKit routes
  /// Esc to a SwiftUI cancel action in a borderless window depends on what holds first responder. A
  /// local monitor does not: it sees the key event before anything else in this process, which is
  /// what "Esc aborts at any point" has to mean. Removed the instant the run ends, so it can never
  /// eat an Esc that belongs to onboarding.
  private static func installEscapeMonitor(_ cinematic: OmiCinematicDirector) {
    removeEscapeMonitor()
    escapeMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
      guard event.keyCode == 53 else { return event }
      MainActor.assumeIsolated { cinematic.skip() }
      return nil
    }
  }

  private static func removeEscapeMonitor() {
    if let escapeMonitor { NSEvent.removeMonitor(escapeMonitor) }
    escapeMonitor = nil
  }

  // MARK: - The ambient bed, on its own

  /// The bed the intro rides in on, and the one the chat-style onboarding plays under.
  ///
  /// Start it when onboarding opens and stop it when onboarding closes; it is safe to call either
  /// twice, and safe to call when the user has muted it (nothing happens). The intro starts it
  /// itself, so a caller that presents the cinematic first and then starts the chat flow will find
  /// it already playing and leave it alone.
  static func startAmbientMusic(fadeIn: TimeInterval = OmiOnboardingMusic.defaultFadeIn) {
    OmiOnboardingSound.music.start(fadeIn: fadeIn)
  }

  static func stopAmbientMusic(fadeOut: TimeInterval = OmiOnboardingMusic.defaultFadeOut) {
    OmiOnboardingSound.music.stop(fadeOut: fadeOut)
  }

  static var isAmbientMusicPlaying: Bool { OmiOnboardingSound.music.isPlaying }

  /// The persisted mute control. `false` also fades out anything currently playing.
  static var isAmbientMusicEnabled: Bool {
    get { OmiOnboardingSound.music.isEnabled }
    set { OmiOnboardingSound.music.isEnabled = newValue }
  }

  /// Decode the assets ahead of time so the first cue is not the one that pays for them. Safe to
  /// call more than once and safe to call when nothing will ever play.
  static func prepareSound() {
    OmiOnboardingSound.prepare()
  }
}
