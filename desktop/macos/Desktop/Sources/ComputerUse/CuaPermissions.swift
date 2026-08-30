import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

/// The four grants computer use needs, kept apart because macOS keeps them apart.
///
/// The mistake this type exists to prevent: treating "Accessibility" as one
/// switch. It is two TCC services that happen to share a pane in System Settings.
/// `kTCCServiceAccessibility` is what `AXIsProcessTrusted` answers for and what
/// reading another app's UI tree needs; `kTCCServicePostEvent` is what
/// `CGPreflightPostEventAccess` answers for and what *synthesising* a click or a
/// keystroke needs. A process can hold either without the other, so gating input
/// on `AXIsProcessTrusted` both refuses work it could do and — worse — permits
/// clicks that the window server silently discards, which reads to a model as a
/// click that worked.
///
/// Screen Recording and Apple Events are their own services again, and Apple
/// Events is granted per target app rather than once.
enum CuaPermission: String, CaseIterable, Sendable {
  /// `kTCCServicePostEvent` — synthesising mouse and keyboard input.
  case postEvents
  /// `kTCCServiceAccessibility` — reading and acting on another app's UI tree.
  case accessibility
  /// `kTCCServiceScreenCapture` — screenshots.
  case screenRecording
  /// `kTCCServiceAppleEvents` — scripting another app. Granted per target.
  case appleEvents

  var title: String {
    switch self {
    case .postEvents, .accessibility: return "Accessibility"
    case .screenRecording: return "Screen Recording"
    case .appleEvents: return "Automation"
    }
  }

  /// What a refused tool tells the model, in terms of what the user must do.
  var refusalMessage: String {
    switch self {
    case .postEvents:
      return
        "Omi cannot post input events yet. macOS asks for this separately from reading the screen; approve Omi under System Settings ▸ Privacy & Security ▸ Accessibility, then try again."
    case .accessibility:
      return
        "Omi cannot read other apps' controls yet. Approve Omi under System Settings ▸ Privacy & Security ▸ Accessibility, then try again."
    case .screenRecording:
      return
        "Omi cannot capture the screen yet. Approve Omi under System Settings ▸ Privacy & Security ▸ Screen Recording, then try again."
    case .appleEvents:
      return
        "Omi is not allowed to script that app yet. Approve it under System Settings ▸ Privacy & Security ▸ Automation, then try again."
    }
  }

  /// Grants this process has been *observed* to hold. A grant is not taken away
  /// mid-session, and re-deciding it every call is what produced the bug this
  /// state exists for: the app kept asking for a permission the user had already
  /// given.
  @MainActor private static var observed: Set<CuaPermission> = []

  /// Permissions macOS has already been asked about in this process. TCC shows
  /// its dialog once and silently ignores every later request, so asking again
  /// cannot help — it only lets a caller loop.
  @MainActor private static var requested: Set<CuaPermission> = []

  /// Whether the grant is in place. Never prompts.
  ///
  /// **Reads live, not cached.** `AXIsProcessTrusted` answers from a per-process
  /// cache populated on its first call, so a user who ticks Omi in System
  /// Settings while it is running keeps being told the permission is missing
  /// until the next launch. A real accessibility call against another process
  /// starts succeeding the moment the box is ticked, so the probe is the
  /// authority and the cached flag is only a fast path.
  ///
  /// `appleEvents` has no process-wide answer — permission is per target app —
  /// so it reports true here and is checked at the call, where the target is
  /// known.
  @MainActor
  func isGranted() -> Bool {
    if Self.observed.contains(self) { return true }
    let granted: Bool
    switch self {
    case .postEvents:
      // The Accessibility checkbox grants both `kTCCServiceAccessibility` and
      // `kTCCServicePostEvent`, so the preflight is the direct answer here and
      // `refreshLiveGrants` supplies the other half when the checkbox was ticked
      // after launch.
      granted = CGPreflightPostEventAccess()
    case .accessibility:
      granted = AXIsProcessTrusted()
    case .screenRecording:
      granted = ScreenCaptureService.checkPermission()
    case .appleEvents:
      return true
    }
    if granted { Self.observed.insert(self) }
    return granted
  }

  /// Catch up with a grant the user gave while Omi was running.
  ///
  /// `AXIsProcessTrusted` answers from a per-process cache populated on its first
  /// call, so ticking Omi in System Settings changes nothing the running app can
  /// see and it keeps asking for a permission that has already been given. A real
  /// accessibility call against another process starts succeeding immediately, so
  /// that is what settles it — and because the Accessibility checkbox grants
  /// posting as well as reading, one working call clears both.
  ///
  /// Off the main actor on purpose: an accessibility read is IPC, and an
  /// unresponsive target holds the reply until the messaging timeout. On the
  /// main thread that is a visible hang; the whole reason this is a background
  /// refresh rather than part of the check.
  static func refreshLiveGrants(_ permissions: [CuaPermission]) async {
    let wanted: Set<CuaPermission> = [.accessibility, .postEvents]
    guard !wanted.isDisjoint(with: permissions) else { return }
    let alreadyKnown = await MainActor.run { observed.isSuperset(of: wanted) }
    guard !alreadyKnown else { return }

    let targets = AppState.accessibilityProbeTargets()
    let works = await Task.detached { AppState.axProbeResult(targets: targets) == .working }.value
    guard works else { return }
    await MainActor.run {
      observed.formUnion(wanted)
    }
  }

  /// Record a grant proven by an operation that actually succeeded. A capture
  /// that returned an image is better evidence than any preflight.
  @MainActor
  static func markGranted(_ permission: CuaPermission) {
    observed.insert(permission)
  }

  /// Ask macOS for the grant, which shows the system prompt the first time and
  /// does nothing on later calls (TCC only prompts once per service per app).
  ///
  /// Returns whether the grant is in place afterwards. It is normally false on
  /// the first call even when the user says yes: Accessibility and Screen
  /// Recording are read from a per-process cache that does not refresh until the
  /// next launch, which is why the caller reports "approve it, then try again"
  /// rather than waiting.
  @MainActor
  @discardableResult
  func request() -> Bool {
    Self.requested.insert(self)
    switch self {
    case .postEvents:
      return CGRequestPostEventAccess()
    case .accessibility:
      // `kAXTrustedCheckOptionPrompt` is an imported global var and so not
      // Sendable; its value is a documented constant string.
      let options = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
      return AXIsProcessTrustedWithOptions(options)
    case .screenRecording:
      return CGRequestScreenCaptureAccess()
    case .appleEvents:
      return true
    }
  }

  /// The System Settings pane that grants this, for the case where the prompt
  /// has already been answered once and will never appear again.
  var settingsURL: URL? {
    let pane: String
    switch self {
    case .postEvents, .accessibility: pane = "Privacy_Accessibility"
    case .screenRecording: pane = "Privacy_ScreenCapture"
    case .appleEvents: pane = "Privacy_Automation"
    }
    return URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)")
  }

  @MainActor
  func openSettings() {
    guard let settingsURL else { return }
    NSWorkspace.shared.open(settingsURL)
  }

  /// The grant if it is there, or a refusal that has already asked for it.
  ///
  /// "Use what Omi already has, ask for the rest" in one call: a tool never has
  /// to decide whether to prompt, and a user who has not been asked yet gets the
  /// system dialog instead of a sentence telling them to go find a checkbox.
  @MainActor
  static func ensure(_ permissions: [CuaPermission]) -> CuaPermission? {
    for permission in permissions where !permission.isGranted() {
      // Once per process. macOS shows the dialog on the first request and
      // ignores the rest, so a second ask is invisible to the user and merely
      // lets a tool loop on it.
      if !requested.contains(permission) {
        permission.request()
        // `CGRequestPostEventAccess` returns the live answer, so a grant given
        // in this very session is usable without a relaunch.
        if permission.isGranted() { continue }
      }
      return permission
    }
    return nil
  }
}
