//
//  ShellSummon.swift — where the shell lands when you call it, and where it goes when you don't.
//
//  `ShellWindowChrome` says *what* the shell is: transparent, buttonless, and an ordinary application
//  window that stays where you left it. This says *where*, and it is a separate file because "where"
//  is the half that is per-display state rather than per-window properties.
//
//  ## Why per-display, and not one remembered frame
//
//  One remembered frame is the naive implementation and it is wrong on exactly the setup most people
//  have. Summon the shell on the laptop, put it where you want it; summon it later on the 5K and it
//  arrives at laptop coordinates — off the edge, or covering the thing you summoned it to look at.
//  Clamping into the new screen "fixes" it by throwing the placement away, so the shell drifts to a
//  different spot every time you switch displays and never settles anywhere.
//
//  So the frame is remembered against the display it was left on, the way the surfaces this shell is
//  modelled on do it. Which display that is comes from `ActiveDisplay` — the key window's, then the
//  frontmost window's, then the focused one, and only then the pointer. Its header carries the
//  argument; the short version is that a pointer parked on an idle monitor is not where the user is
//  looking, and every surface in the app has to agree on the answer or they land apart.
//
//  ## What a summon does not do
//
//  It does not move a shell you are already using. Repositioning on every route into this function
//  would make the notch's "Continue in Omi" and a Dock click yank the window across the desktop for
//  no reason. `shouldReposition` is the whole rule: land it if it is not up, or if you called it from
//  a different display than the one it is on.
//
//  ## Dismissal
//
//  Putting the shell away is always something the user asks for — it does not happen because focus
//  moved, which is what made the window unreachable from any switcher (see `ShellWindowChrome`).
//  `⌘O` toggles it; `⌘W` and Escape are explicit alternatives.
//  Escape is `WindowEscapeKeyMonitor` at `.shell` — the lowest priority there is, so it fires only
//  after every modal, editor, page and navigation handler has declined it. Escape on a page still goes
//  Home; Escape on Home, where nothing else wants it, puts the shell away.
//
//  Brand: nothing here picks a colour (INV-UI-1).
//

import AppKit
import Foundation

/// The geometry half, with no window and no defaults in it, so every placement decision is a claim a
/// hermetic test can hold. Multi-display placement is the part that breaks in the field and the part
/// that is impossible to exercise on a single-screen CI runner, so none of it may live inside AppKit
/// callbacks.
enum ShellSummonPlacement {
  /// The size a shell that has never been placed on this display arrives at.
  ///
  /// Deliberately smaller than the old managed-window default: a surface you summon over your work
  /// should read as a panel you called up, not as an application you switched to. Width is the
  /// hugged glass (readable lane + page margins), so a 5K display still gets a panel, not a sheet.
  /// It stays above `DesktopWindowLayoutPolicy.minimumContentSize`, which is the floor the
  /// destinations lay out to.
  static let defaultSize = NSSize(
    width: ChatComposerLayout.contentLaneMaxWidth, height: 700)

  /// Where the shell lands on a given display.
  ///
  /// A remembered frame wins, shrunk and nudged until it fits — a display can get smaller (resolution
  /// change, a scaled mode, a menu bar appearing) and a frame restored past the edge is a shell with
  /// its query field off-screen. Width is also clamped to the hug max so a frame remembered from the
  /// pre-hug oversized window cannot restore the invisible border. With nothing remembered it is
  /// centred, which is where a summoned surface belongs the first time you ask for it.
  static func frame(remembered: NSRect?, visibleFrame: NSRect, defaultSize: NSSize = defaultSize) -> NSRect {
    guard let remembered, remembered.width > 1, remembered.height > 1 else {
      return centered(defaultSize, in: visibleFrame)
    }
    return clamped(
      NSRect(origin: remembered.origin, size: fitted(remembered.size, in: visibleFrame)),
      into: visibleFrame)
  }

  /// The least of a shell a person can actually use: enough visible surface to read the panel and
  /// press its controls. Anything less is a stranded window — a sliver in a corner from a frame
  /// restored across a display change (or persisted by an automation park), whose buttons exist at
  /// coordinates no screen shows. The sign-in window shipped exactly that: restored to a 24×32
  /// corner sliver, its "Continue" buttons unclickable at any version (#11374 follow-up).
  static let minimumUsableOverlap = NSSize(width: 320, height: 240)

  /// Whether a frame is meaningfully on some display — not merely intersecting an edge.
  static func isMeaningfullyOnScreen(
    _ frame: NSRect, visibleFrames: [NSRect], minimumOverlap: NSSize = minimumUsableOverlap
  ) -> Bool {
    visibleFrames.contains { visible in
      let overlap = visible.intersection(frame)
      return overlap.width >= minimumOverlap.width && overlap.height >= minimumOverlap.height
    }
  }

  /// Whether this summon should place the window at all.
  ///
  /// `false` is the interesting answer: a shell already up on the display you are on is a shell you
  /// are already using, and moving it would be the app fighting the user. Since the shell stays up
  /// when focus moves elsewhere, that is also the answer for the common case of switching back to it.
  static func shouldReposition(isVisible: Bool, windowDisplayKey: String?, cursorDisplayKey: String?) -> Bool {
    guard isVisible else { return true }
    guard let cursorDisplayKey, let windowDisplayKey else { return false }
    return windowDisplayKey != cursorDisplayKey
  }

  /// The stable per-display identity frames are filed under.
  ///
  /// `CGDirectDisplayID` rather than an index into `NSScreen.screens`, because that array reorders
  /// when a display sleeps, wakes or is unplugged — which is precisely the moment the remembered
  /// frame is about to be read.
  static func displayKey(for screen: NSScreen) -> String? {
    let number = screen.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber
    return number.map { "\($0.uint32Value)" }
  }

  static func centered(_ size: NSSize, in visibleFrame: NSRect) -> NSRect {
    let fittedSize = fitted(size, in: visibleFrame)
    return NSRect(
      x: visibleFrame.midX - fittedSize.width / 2,
      y: visibleFrame.midY - fittedSize.height / 2,
      width: fittedSize.width,
      height: fittedSize.height)
  }

  /// Points, not pixels: `visibleFrame` is already in points, and Retina scale must not change this.
  static func fitted(
    _ size: NSSize,
    in visibleFrame: NSRect,
    maxWidth: CGFloat = ChatComposerLayout.contentLaneMaxWidth
  ) -> NSSize {
    NSSize(
      width: min(size.width, visibleFrame.width, maxWidth),
      height: min(size.height, visibleFrame.height))
  }

  private static func clamped(_ rect: NSRect, into visibleFrame: NSRect) -> NSRect {
    var frame = rect
    frame.origin.x = min(max(frame.origin.x, visibleFrame.minX), visibleFrame.maxX - frame.width)
    frame.origin.y = min(max(frame.origin.y, visibleFrame.minY), visibleFrame.maxY - frame.height)
    return frame
  }
}

/// The remembered frames, as a value.
///
/// Split from the coordinator so the encode/decode round trip — the part that silently loses a
/// display's placement when it goes wrong — is testable without `UserDefaults`.
enum ShellFrameMemory {
  /// The defaults key. Named for what it holds rather than for the window, because the window is now
  /// a panel and the next rename should not orphan everybody's placements.
  static let defaultsKey = "ShellPanelFrameByDisplayID"

  static func read(from stored: [String: String], displayKey: String) -> NSRect? {
    guard let raw = stored[displayKey] else { return nil }
    let rect = NSRectFromString(raw)
    return rect.width > 1 && rect.height > 1 ? rect : nil
  }

  static func written(_ frame: NSRect, forDisplay displayKey: String, into stored: [String: String])
    -> [String: String]
  {
    var updated = stored
    updated[displayKey] = NSStringFromRect(frame)
    return updated
  }
}

/// Summoning, dismissing, and remembering — the live half, which owns the one shell window.
@MainActor
enum ShellSummon {
  enum ToggleAction: Equatable {
    case summon
    case dismiss
  }

  /// The shell window, once something has identified it. Weak: the window outlives nothing here, and
  /// a strong reference would keep a closed window alive past its scene.
  private static weak var knownShellWindow: NSWindow?
  private static var appliedPresentation: ShellWindowChrome.Presentation?
  private static var escapeRegistration: UUID?
  private static var observers: [NSObjectProtocol] = []
  /// Whether a summon has ever put the shell on screen. The gate on restoring it for the user.
  private static var hasBeenShown = false
  /// The frame captured while a native permission prompt or System Settings owns the user's
  /// attention. This is deliberately separate from ordinary dismissal: returning from a permission
  /// flow must restore the exact panel the user was looking at, not re-land it under the cursor.
  private static var permissionSuspendedFrame: NSRect?
  /// Which window the Escape route and the frame observers are currently bound to.
  ///
  /// Both are per-window — `WindowEscapeKeyMonitor` matches on window identity and the notification
  /// observers are registered with the window as their `object` — and `⌘W` does not retire the shell,
  /// it retires *this* window; the next summon asks the scene for a new one. Binding once and never
  /// checking would leave Escape and the frame memory wired to a window nobody can see again.
  private static weak var boundWindow: NSWindow?

  // MARK: - Finding the shell

  /// Whether this window is the shell and not one of the app's auxiliary windows.
  ///
  /// The exact title first, because several auxiliary windows (the chat lab, the prompt editors) also
  /// begin with "Omi" and dressing one of those as the shell would float and auto-hide it. The loose
  /// test is the fallback for a build whose title has drifted from `OMIApp.currentWindowTitle`, where
  /// wrongly identifying nothing is worse than occasionally identifying a large window.
  static func isShellWindow(_ window: NSWindow) -> Bool {
    if window.title == OMIApp.currentWindowTitle { return true }
    guard !window.title.hasPrefix("Item-"), window.title.lowercased().hasPrefix("omi") else { return false }
    return window.frame.width > 300 && window.frame.height > 200
  }

  static func shellWindow() -> NSWindow? {
    if let known = knownShellWindow, NSApp.windows.contains(where: { $0 === known }) { return known }
    let found = NSApp.windows.first(where: isShellWindow)
    knownShellWindow = found
    return found
  }

  /// The global launch shortcut is the one summon route that doubles as a dismissal gesture.
  /// Miniaturised windows are not visible to the user, so the shortcut must restore them rather
  /// than treat them as an already-open shell and order them out.
  ///
  /// `isAppActive` is what stops the chord from turning into a hide button. The shell no longer hides
  /// itself when you switch apps, so "still on screen" stopped meaning "you are looking at it" — it is
  /// usually sitting behind whatever you are working in. Pressing Open Omi from another app is a
  /// request to be shown Omi; only pressing it while Omi is the app you are already in means "put it
  /// away". It defaults to AppKit's answer so the shortcut path reads it without ceremony, and is a
  /// parameter at all so a test can state the case it is asserting.
  static func toggleAction(
    for window: NSWindow?,
    presentation: ShellWindowChrome.Presentation = .summoned,
    isAppActive: Bool = NSApp.isActive
  ) -> ToggleAction {
    guard presentation == .summoned else { return .summon }
    guard let window, window.isVisible, !window.isMiniaturized else { return .summon }
    guard isAppActive else { return .summon }
    return .dismiss
  }

  // MARK: - Presentation

  /// Summonable only once there is an account and a finished setup. See `ShellWindowChrome`'s header
  /// for why a first run may not auto-hide.
  static func presentation() -> ShellWindowChrome.Presentation {
    let onboarded = UserDefaults.standard.bool(forKey: DefaultsKey.hasCompletedOnboarding.rawValue)
    return onboarded && AuthState.shared.isSignedIn ? .summoned : .anchored
  }

  /// Dress the window for the presentation it should currently have, and attach or detach the Escape
  /// route to match. Idempotent, and cheap enough to call from a defaults observer.
  static func applyPresentation(to window: NSWindow) {
    let presentation = presentation()
    if boundWindow !== window { rebind(to: window) }
    knownShellWindow = window
    ShellWindowChrome.dress(window, as: presentation)
    appliedPresentation = presentation
    if presentation == .summoned {
      registerEscapeRoute(on: window)
    } else {
      unregisterEscapeRoute()
    }
  }

  // MARK: - Summon / dismiss

  /// Bring the shell up, landing it on the display under the cursor when it is not already there.
  /// Returns `false` when there is no shell window yet, which is the caller's signal to create one.
  ///
  /// `alwaysPlace` is for launch only. SwiftUI restores the scene's saved frame before this runs, so
  /// a window that is already on screen at the size it had as a managed application window would
  /// never be re-landed by the ordinary rule — and the first launch after the shell became a panel is
  /// exactly when it must be. It still reads the remembered placement first, so it only recentres a
  /// display that has never held the panel.
  @discardableResult
  static func summon(alwaysPlace: Bool = false) -> Bool {
    guard let window = shellWindow() else { return false }
    applyPresentation(to: window)
    if window.isMiniaturized { window.deminiaturize(nil) }

    // `ActiveDisplay` — the same answer the onboarding cinematic lands on, so the intro and the
    // window it hands off to can never disagree about which screen the user is on.
    let landingScreen = ActiveDisplay.screen()
    let repositions =
      alwaysPlace
      || ShellSummonPlacement.shouldReposition(
        isVisible: window.isVisible,
        windowDisplayKey: window.screen.flatMap(ShellSummonPlacement.displayKey(for:)),
        cursorDisplayKey: landingScreen.flatMap(ShellSummonPlacement.displayKey(for:)))

    if repositions, let screen = landingScreen ?? window.screen {
      // Onboarding is an anchored first-run surface, but it still needs a deterministic first
      // placement. SwiftUI may restore the shell's previous frame at launch; leaving that frame in
      // place puts a new user's onboarding card in a lower-right corner. Summoned shells keep their
      // per-display placement policy; anchored shells are centred for the launch hand-off.
      let frame =
        appliedPresentation == .summoned
        ? landingFrame(on: screen)
        : ShellSummonPlacement.centered(window.frame.size, in: screen.visibleFrame)
      window.setFrame(frame, display: true)
    } else if let screen = NSScreen.main, !screen.visibleFrame.intersects(window.frame) {
      // Anchored, or nothing to land on: the window may still be stranded on a display that went away.
      window.center()
    }

    window.makeKeyAndOrderFront(nil)
    hasBeenShown = true
    return true
  }

  /// Bring the shell back when the user activates Omi with no shell on screen — a ⌘-Tab, a click on
  /// the app in Mission Control, anything that is not the Dock icon (which has its own delegate hook).
  ///
  /// Without this, dismissing with Escape and then ⌘-Tabbing back lands you in an app with no windows
  /// and no obvious way to ask for one. Gated on the shell having been shown at least once, because
  /// the background update relaunch deliberately starts with it ordered out and must stay that way.
  static func restoreOnActivationIfNeeded() {
    if permissionSuspendedFrame != nil {
      restoreAfterPermissionPrompt()
      return
    }
    guard hasBeenShown, let window = shellWindow(), !window.isVisible else { return }
    summon()
  }

  /// Whether the shell is currently ordered out to make room for macOS permission UI.
  ///
  /// The window being gone is not the user closing it, and `applicationShouldTerminateAfterLastWindowClosed`
  /// cannot tell the difference on its own.
  static var isSuspendedForPermissionPrompt: Bool { permissionSuspendedFrame != nil }

  /// Whether losing the last window should end the process.
  ///
  /// Pure so the decision is provable without AppKit: the delegate hook it serves runs inside a
  /// live `NSApplication` during a system permission prompt, which no hermetic test can stand up.
  ///
  /// Before onboarding completes there is no menu-bar residency to fall back on, so a closed last
  /// window really does mean "quit". A permission prompt is the one case where the window is gone
  /// because *we* took it away — `suspendForPermissionPrompt` orders it out so macOS can present
  /// the dialog — and quitting there kills the app at the instant the user is granting the
  /// permission onboarding just asked for. Every one of the eight callers reaches this path.
  nonisolated static func shouldTerminateAfterLastWindowClosed(
    hasCompletedOnboarding: Bool,
    isSuspendedForPermissionPrompt: Bool
  ) -> Bool {
    guard !isSuspendedForPermissionPrompt else { return false }
    return !hasCompletedOnboarding
  }

  /// Temporarily remove the main Omi surface before handing control to macOS permission UI.
  ///
  /// This does not deactivate the application: callers may be about to trigger an in-process
  /// microphone/notification prompt, and AppKit needs Omi to remain the active owner of that prompt.
  /// A second call while the flow is already suspended is intentionally a no-op.
  @discardableResult
  static func suspendForPermissionPrompt() -> Bool {
    guard let window = shellWindow(), window.isVisible else { return false }
    if permissionSuspendedFrame == nil {
      permissionSuspendedFrame = window.frame
      rememberFrame(of: window)
    }
    window.orderOut(nil)
    return true
  }

  /// Restore a shell suspended for permission UI, preserving the frame and route it had before the
  /// request. Safe to call from both a native prompt completion and app activation after System
  /// Settings closes; the first call consumes the suspension.
  static func restoreAfterPermissionPrompt() {
    guard let frame = permissionSuspendedFrame else { return }
    permissionSuspendedFrame = nil
    guard let window = shellWindow() else { return }
    applyPresentation(to: window)
    window.setFrame(frame, display: true)
    window.makeKeyAndOrderFront(nil)
    // Order-in can re-constrain a frame in some sessions (space restore, display re-layout);
    // re-asserting after it keeps "permission UI must not re-center the shell" true everywhere.
    if window.frame != frame {
      window.setFrame(frame, display: true)
    }
    hasBeenShown = true
  }

  /// Put the shell away and hand focus back to whatever the user was doing.
  ///
  /// Only deactivates when this really was the last thing the app was showing — the feedback window,
  /// the chat lab and the prompt editors are ordinary windows, and dropping the app out from under
  /// one of them because the shell closed would be a bug of its own.
  static func dismiss() {
    guard let window = shellWindow(), window.isVisible else { return }
    rememberFrame(of: window)
    window.orderOut(nil)
    let othersVisible = NSApp.windows.contains { other in
      other !== window && other.isVisible && other.canBecomeKey && !(other is NSPanel)
    }
    if !othersVisible { NSApp.deactivate() }
  }

  // MARK: - Frame memory

  static func rememberFrame(of window: NSWindow) {
    guard let screen = window.screen, let key = ShellSummonPlacement.displayKey(for: screen) else { return }
    let stored = UserDefaults.standard.dictionary(forKey: ShellFrameMemory.defaultsKey) as? [String: String] ?? [:]
    UserDefaults.standard.set(
      ShellFrameMemory.written(window.frame, forDisplay: key, into: stored),
      forKey: ShellFrameMemory.defaultsKey)
  }

  static func rememberedFrame(on screen: NSScreen) -> NSRect? {
    guard let key = ShellSummonPlacement.displayKey(for: screen) else { return nil }
    let stored = UserDefaults.standard.dictionary(forKey: ShellFrameMemory.defaultsKey) as? [String: String] ?? [:]
    return ShellFrameMemory.read(from: stored, displayKey: key)
  }

  // MARK: - Per-window attachments

  /// Move every per-window attachment onto `window`, dropping whatever the previous one had.
  ///
  /// Called whenever the shell window changes identity, which is not only at launch: `⌘W` closes
  /// *this* window and the next summon asks the scene for a new one. Attachments that stayed bound to
  /// the closed window would silently stop working — Escape would dismiss nothing and the frame the
  /// user chose would never be remembered — and neither failure has any runtime signal.
  ///
  /// The move/resize observers are scoped to the window itself rather than filtered inside the
  /// callback: an observer block delivered on the main queue is still a non-isolated closure, so
  /// reading an `NSWindow` out of the notification would be a `sending` race. Passing the window as
  /// the observed object keeps the filtering in `NotificationCenter`, where it is free and safe.
  /// Re-place a visible shell whose frame no display meaningfully shows.
  ///
  /// Restored frames outlive the arrangement that produced them: a display unplugs, a resolution
  /// changes, or an automation park's corner frame gets persisted — and the next launch restores a
  /// window whose controls exist off every screen, with no affordance to recover it (the sign-in
  /// window has no rail, no hotkey and no drag handle a user can reach). Automation presentations
  /// park deliberately and are exempt; `normal` mode is the user's window and must be reachable.
  static func recoverStrandedFrameIfNeeded() {
    guard DesktopAutomationWindowPresentation.currentMode == .normal else { return }
    guard let window = shellWindow(), window.isVisible else { return }
    let visibleFrames = NSScreen.screens.map(\.visibleFrame)
    guard !visibleFrames.isEmpty,
      !ShellSummonPlacement.isMeaningfullyOnScreen(window.frame, visibleFrames: visibleFrames)
    else { return }
    guard let screen = ActiveDisplay.screen() ?? NSScreen.main ?? NSScreen.screens.first else { return }
    window.setFrame(landingFrame(on: screen), display: true)
    window.makeKeyAndOrderFront(nil)
    rememberFrame(of: window)
  }

  private static func rebind(to window: NSWindow) {
    let center = NotificationCenter.default
    for observer in observers { center.removeObserver(observer) }
    observers.removeAll()
    unregisterEscapeRoute()
    boundWindow = window
    recoverStrandedFrameIfNeeded()
    for name in [
      NSApplication.didBecomeActiveNotification,
      NSApplication.didChangeScreenParametersNotification,
    ] {
      observers.append(
        center.addObserver(forName: name, object: nil, queue: .main) { _ in
          MainActor.assumeIsolated { recoverStrandedFrameIfNeeded() }
        })
    }
    for name in [NSWindow.didMoveNotification, NSWindow.didResizeNotification] {
      observers.append(
        center.addObserver(forName: name, object: window, queue: .main) { _ in
          MainActor.assumeIsolated {
            guard let shell = shellWindow() else { return }
            rememberFrame(of: shell)
          }
        })
    }
    // Onboarding completion and sign-out are both `UserDefaults` writes, so this is the one signal
    // that covers the switch in either direction. Re-dressing only on a real change keeps it off the
    // hot path of every other `@AppStorage` write in the app.
    // `queue: nil` + explicit hop, never `queue: .main`: notification delivery to queue-based
    // observers is synchronous, so a main-queue observer makes every background
    // `UserDefaults.set` wait on the main thread — which deadlocked the app when an auth commit
    // held the session fence while posting and the main thread wanted that fence (#11374).
    observers.append(
      center.addObserver(forName: UserDefaults.didChangeNotification, object: nil, queue: nil) { _ in
        DispatchQueue.main.async {
          MainActor.assumeIsolated {
            guard let window = shellWindow(), presentation() != appliedPresentation else { return }
            applyPresentation(to: window)
          }
        }
      })
  }

  // MARK: - Private

  /// Centred on the screen, at the size it was last left.
  ///
  /// A remembered *position* is not restored. Following the cursor onto an idle second display and
  /// then restoring a frame from some earlier session put the shell somewhere the user was not
  /// looking, on a desktop with nothing behind it to blur — which reads as a black window rather
  /// than as glass. Centring is the placement a summoned surface can never get wrong: it is where
  /// the eye already is. Size still persists, because a shell the user widened should stay wide.
  private static func landingFrame(on screen: NSScreen) -> NSRect {
    let remembered = rememberedFrame(on: screen)
    let size = ShellSummonPlacement.frame(
      remembered: remembered, visibleFrame: screen.visibleFrame
    ).size
    return ShellSummonPlacement.centered(size, in: screen.visibleFrame)
  }

  private static func registerEscapeRoute(on window: NSWindow) {
    guard escapeRegistration == nil else { return }
    escapeRegistration = WindowEscapeKeyMonitor.shared.register(window: window, priority: .shell) {
      dismiss()
      return true
    }
  }

  private static func unregisterEscapeRoute() {
    guard let registration = escapeRegistration else { return }
    WindowEscapeKeyMonitor.shared.unregister(registration)
    escapeRegistration = nil
  }
}
