import AppKit

/// While the user is recording a shortcut, every surface in this app that *acts* on one stands down.
///
/// The defect this exists for: in Settings, pressing the chord a shortcut is already bound to did not
/// rebind it — it ran it. Ask Omi is a Carbon hotkey, and a Carbon hotkey is not merely first in line,
/// it *preempts* (`GlobalShortcutManager.registerSummonHotkey` documents the measurement). The
/// recorder listens with `NSEvent.addLocalMonitorForEvents`, so for the one chord the user is most
/// likely to retype — the one they are trying to change — the monitor never saw the event at all and
/// the window toggled instead. Anything with ⌘ had a second way to lose: the main menu claims ⌘W
/// before a local monitor does, so recording over that chord closed the window.
///
/// Three owners have to stand down, and the reason they cannot be one flag is that they intercept at
/// three different layers:
///
/// * **Carbon hotkeys** are held by the window server, so they must be genuinely *unregistered* —
///   a Boolean the handler consults is checked after the event has already been taken away.
/// * **The main menu** is AppKit's, and key equivalents are matched before the responder chain.
/// * **Push-to-talk** is an `NSEvent` monitor in this process, which a Boolean does reach
///   (`PushToTalkManager.acceptsShortcutEvents`).
///
/// Onboarding had the first two inline and Settings had none of them, which is the whole bug: the
/// rule lived in one call site instead of in a type both could hold. It is here so a third recorder
/// cannot be written without it.
@MainActor
final class ShortcutCaptureSession {
  /// Whether a recorder currently owns the keyboard. Read by `PushToTalkManager` — the one stander-down
  /// that is an in-process monitor and can be gated rather than torn down.
  private(set) static var isCapturing = false

  private var savedMainMenu: NSMenu?
  private var isActive = false

  /// The two side effects, injected rather than reached for. `GlobalShortcutManager` registers
  /// system-wide hotkeys and `NSApp` does not exist in a unit-test process at all (the test bundle is
  /// required not to create one), so a session that called both directly could only be asserted by
  /// taking real chords away from the machine running the suite.
  private let suspendGlobalShortcuts: (Bool) -> Void
  private let readMainMenu: () -> NSMenu?
  private let writeMainMenu: (NSMenu?) -> Void

  init(
    suspendGlobalShortcuts: @escaping (Bool) -> Void = {
      GlobalShortcutManager.shared.setRegistrationSuspended($0)
    },
    // Optional-chained rather than force-unwrapped: `NSApp` is an implicitly unwrapped optional, and
    // reading it is a crash anywhere it is nil rather than the no-op the name suggests.
    readMainMenu: @escaping () -> NSMenu? = { NSApp?.mainMenu },
    writeMainMenu: @escaping (NSMenu?) -> Void = { NSApp?.mainMenu = $0 }
  ) {
    self.suspendGlobalShortcuts = suspendGlobalShortcuts
    self.readMainMenu = readMainMenu
    self.writeMainMenu = writeMainMenu
  }

  /// Stands the app's shortcut handlers down. Idempotent: a recorder that re-arms without disarming
  /// (Settings starts a capture by stopping the previous one) must not lose the real menu by saving
  /// the `nil` it already installed.
  func begin() {
    guard !isActive else { return }
    isActive = true
    Self.isCapturing = true
    suspendGlobalShortcuts(true)
    savedMainMenu = readMainMenu()
    writeMainMenu(nil)
  }

  /// Hands the keyboard back. Also idempotent, and safe to call on a session that never began —
  /// a recorder's teardown runs on paths where capture never started.
  func end() {
    guard isActive else { return }
    isActive = false
    Self.isCapturing = false
    if let savedMainMenu {
      writeMainMenu(savedMainMenu)
      self.savedMainMenu = nil
    }
    suspendGlobalShortcuts(false)
  }

  deinit {
    // A recorder torn down mid-capture — its view dismissed, its window closed — must not leave the
    // Mac without its menu bar and without Ask Omi. `isActive` is the session's own state and
    // `isCapturing` is the app's, so this restores both rather than assuming a caller will.
    MainActor.assumeIsolated {
      end()
    }
  }
}
