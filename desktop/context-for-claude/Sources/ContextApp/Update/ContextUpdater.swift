import AppKit
import Combine
import Foundation
import Sparkle

/// The app's auto-updater: scheduled checks, background download and an explicit install/relaunch
/// action.
///
/// It is Sparkle, the same mechanism `desktop/macos` uses, and that is where the resemblance is meant
/// to stop. Sparkle draws its sheet from the host bundle — the name, the icon, the current version —
/// and its release notes from the feed, so an update prompt here says "Context for Claude", shows
/// this app's icon, and lists this app's changes. Nothing in this file hardcodes a product name for
/// exactly that reason: the day one is added is the day a user of this app is shown Omi's.
///
/// **Nothing starts unless ``UpdatePolicy`` says so, and the ordering is not stylistic.**
/// `SPUStandardUpdaterController(startingUpdater: true, …)` calls `abort()` — a process kill, not an
/// error — when the bundle it is started in cannot support an updater, and the placeholder
/// `SUPublicEDKey` this repository ships makes this such a bundle. So the policy is evaluated first,
/// its answer is passed as `startingUpdater:`, and every entry point re-asks. A developer who builds
/// this package and never fills in a key gets an app that says so in Settings, not one that dies on
/// launch.
///
/// **Airgap Mode governs this like every other remote client.** An updater quietly asking GitHub for
/// a feed every six hours while a switch labelled "Stops this app from reaching the network" is on
/// would be the exact broken promise `Backend/NetworkEgress.swift` was written to end — that file
/// exists because Airgap Mode once meant "no favicons" while the app uploaded the user's screen. So
/// `.updateCheck` names itself in `NetworkEgress.Client` and is enforced in two places: Sparkle's own
/// permission gate, which fires before the feed is fetched and is the only seam the *background*
/// checker has, and ``checkForUpdates()``, which explains itself rather than silently doing nothing.
@MainActor
final class ContextUpdater: ObservableObject {

  static let shared = ContextUpdater()

  /// Why the updater is off, or `nil` when it is running. Drives the Settings row.
  let refusal: UpdatePolicy.Refusal?

  /// Whether Sparkle is idle enough to accept a check initiated from Settings. Always `false` when
  /// the updater did not start, so a button bound to it is disabled rather than dead.
  @Published private(set) var canCheckForUpdates: Bool = false

  /// Set when a check finished with nothing to install, or could not run at all. The Settings row
  /// shows it verbatim, so it is a whole sentence rather than a status code.
  @Published private(set) var lastCheckSummary: String?

  private let controller: SPUStandardUpdaterController?
  private let events = UpdaterEvents()

  private init() {
    let decision = UpdatePolicy.current()
    refusal = decision.refusal

    guard decision.isAllowed else {
      // No controller at all. Constructing one with `startingUpdater: false` would work too,
      // but then every method here would have to remember not to use it; an optional makes the
      // compiler remember instead.
      controller = nil
      lastCheckSummary = refusal.map(UpdatePolicy.explanation)
      return
    }

    let controller = SPUStandardUpdaterController(
      startingUpdater: true,
      updaterDelegate: events,
      userDriverDelegate: nil)
    self.controller = controller

    // `SUEnableAutomaticChecks` and `SUScheduledCheckInterval` in Info.plist are the defaults;
    // these lines are what the running app actually obeys, set explicitly so a plist that drifts
    // cannot quietly change the update contract. Sparkle may download and verify in the
    // background, but the delegate below holds installation behind an explicit relaunch prompt.
    controller.updater.automaticallyChecksForUpdates = true
    controller.updater.automaticallyDownloadsUpdates = UpdatePolicy.automaticallyDownloadsUpdates

    events.owner = self
    controller.updater.publisher(for: \.canCheckForUpdates)
      .receive(on: DispatchQueue.main)
      .assign(to: &$canCheckForUpdates)
  }

  /// Touching this is what starts the scheduled checker, because the controller is built in `init`.
  /// Called once from `ContextAppDelegate.applicationDidFinishLaunching`; safe to call again, and
  /// safe to call in a build where the policy refused.
  func start() {
    guard controller != nil else {
      if let refusal {
        ContextLog.info("updater not started: \(refusal.rawValue)", "update")
      }
      return
    }
    ContextLog.info("scheduled update checks are running", "update")
  }

  /// The user asked. Shows Sparkle's own UI — the sheet with this app's name and icon on it.
  ///
  /// Reports through ``lastCheckSummary`` rather than throwing, because every caller is a button and
  /// the answer belongs in the row underneath it.
  func checkForUpdates() {
    guard let controller else {
      lastCheckSummary = refusal.map(UpdatePolicy.explanation)
      return
    }
    guard !NetworkEgress.isSuppressed(.updateCheck) else {
      lastCheckSummary = NetworkEgress.explanation(.updateCheck)
      NetworkEgress.recordSuppression(.updateCheck, outcome: .degraded)
      return
    }
    lastCheckSummary = nil
    controller.checkForUpdates(nil)
  }

  /// The version this bundle is, for the row the button sits in.
  ///
  /// Deliberately `AppVersion`'s answer rather than a second reading of the same two Info.plist
  /// keys: the version the Updates row shows and the version the About row shows are the same
  /// claim, and two copies of it is two places for it to become wrong.
  var currentVersionDescription: String { AppVersion.display }

  /// When the last check ran, or `nil` if it never has.
  var lastCheckDate: Date? { controller?.updater.lastUpdateCheckDate }

  fileprivate func report(_ summary: String?) {
    lastCheckSummary = summary
  }

  fileprivate func presentRelaunchPrompt(
    for version: String,
    completion: @escaping (Bool) -> Void
  ) {
    lastCheckSummary = UpdatePolicy.RelaunchState.required(version: version).message

    let alert = NSAlert()
    alert.messageText = UpdatePolicy.relaunchPromptTitle
    alert.informativeText = UpdatePolicy.relaunchPromptMessage(for: version)
    alert.alertStyle = .informational
    alert.addButton(withTitle: "Install and Relaunch")
    alert.addButton(withTitle: "Later")
    NSApp.activate(ignoringOtherApps: true)

    let approved = alert.runModal() == .alertFirstButtonReturn
    completion(approved)
  }
}

/// Sparkle's delegate, kept separate because Sparkle requires an `NSObject` and calls back on its own
/// schedule — including from `willInstallUpdate:`, moments before it terminates the process.
@MainActor
private final class UpdaterEvents: NSObject, SPUUpdaterDelegate {

  /// Weak: Sparkle holds the delegate for the life of the updater, and the updater is owned by the
  /// object this points back at.
  weak var owner: ContextUpdater?

  /// Sparkle's automatic driver has prepared the update but has not been given permission to
  /// install it. The closure is retained only until the native prompt is answered.
  private var pendingInstallation: (() -> Void)?
  private var installationWasApproved = false

  /// Sparkle's permission gate, called before the feed is fetched on every check — scheduled or
  /// manual. Throwing here is how Airgap Mode is enforced against the *background* checker, which
  /// has no other seam: nobody calls it, so nobody can guard it at a call site.
  func updater(_ updater: SPUUpdater, mayPerform updateCheck: SPUUpdateCheck) throws {
    guard NetworkEgress.isSuppressed(.updateCheck) else { return }
    NetworkEgress.recordSuppression(.updateCheck, outcome: .degraded)
    throw NSError(
      domain: "com.omi.context-for-claude.update",
      code: 1,
      userInfo: [NSLocalizedDescriptionKey: NetworkEgress.explanation(.updateCheck)])
  }

  /// A downloaded update is extracted in the background. This state/message is also reflected in
  /// Settings, while the automatic driver's install-on-quit hook below supplies the actual prompt.
  func updater(_ updater: SPUUpdater, didExtractUpdate item: SUAppcastItem) {
    owner?.report(UpdatePolicy.RelaunchState.required(version: item.displayVersionString).message)
  }

  /// Sparkle 2.9 calls this when an automatically downloaded update is prepared for a silent
  /// install on quit. Returning `true` makes this delegate responsible for the install decision;
  /// the immediate block is invoked only after the user chooses Install and Relaunch.
  func updater(
    _ updater: SPUUpdater,
    willInstallUpdateOnQuit item: SUAppcastItem,
    immediateInstallationBlock: @escaping () -> Void
  ) -> Bool {
    guard UpdatePolicy.requiresRelaunchConfirmation else { return false }
    // If the owner has not been attached yet, keep Sparkle's automatic driver paused. A missing
    // prompt owner must never turn into permission for a silent install/relaunch.
    guard let owner else { return true }

    pendingInstallation = immediateInstallationBlock
    owner.presentRelaunchPrompt(
      for: item.displayVersionString,
      completion: { [weak self] approved in
        guard let self else { return }
        if approved {
          self.installationWasApproved = true
          let installation = self.pendingInstallation
          self.pendingInstallation = nil
          installation?()
        } else {
          self.pendingInstallation = nil
          self.installationWasApproved = false
        }
      })
    return true
  }

  /// Sparkle calls this immediately before it asks the installer to replace the bundle. This is a
  /// second, fail-closed gate: if termination or another driver reaches installation without the
  /// explicit approval above (or a standard Sparkle Install choice), the update is aborted and the
  /// capture process is not silently terminated/restarted.
  func updaterShouldRelaunchApplication(_ updater: SPUUpdater) -> Bool {
    let approved = installationWasApproved
    installationWasApproved = false
    if !approved {
      owner?.report("A verified Context for Claude update is ready. Choose Install and Relaunch to apply it.")
    }
    return approved
  }

  /// The standard Sparkle sheet is itself an explicit user action. Record that approval so the
  /// relaunch gate permits a manually initiated install as well as the background-download prompt.
  func updater(
    _ updater: SPUUpdater,
    userDidMake choice: SPUUserUpdateChoice,
    forUpdate updateItem: SUAppcastItem,
    state: SPUUserUpdateState
  ) {
    if choice == .install {
      installationWasApproved = true
    }
  }

  /// **The reason this delegate exists at all.** The last callback before the process is replaced.
  ///
  /// `UpdateRelaunch` writes synchronously here; see that type for why an app that cannot tell "I
  /// was just updated" from "I was just installed" cannot diagnose the one failure that silently
  /// costs it every capture permission it has.
  func updater(_ updater: SPUUpdater, willInstallUpdate item: SUAppcastItem) {
    let current =
      Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
    UpdateRelaunch.note(installOf: item.displayVersionString, from: current)
    // `milestone`, not `info`: `info` lives in a memory ring buffer evicted within minutes (see
    // `Support/Log.swift`), and this is the line anybody investigating "capture died and I don't
    // know when" needs to still be able to read tomorrow. It is also, literally, the last thing
    // this process does.
    ContextLog.milestone(
      "installing \(item.displayVersionString) over \(current) — replacing this bundle",
      "update")
  }

  func updaterDidNotFindUpdate(_ updater: SPUUpdater) {
    Task { @MainActor in owner?.report("Context for Claude is up to date.") }
  }

  func updater(_ updater: SPUUpdater, didAbortWithError error: Error) {
    // Sparkle reports "no update found" through this path as well as through the callback above,
    // and it is not a failure. Written as the literal rather than as `SUError.noUpdateError`
    // because that enum's Swift spelling comes out of the importer's prefix-stripping rules and
    // is not worth depending on; `SUNoUpdateError = 1001` in `SUErrors.h` is.
    let nsError = error as NSError
    guard nsError.code != 1001 else { return }
    ContextLog.error("update check failed: \(nsError.domain) \(nsError.code)", "update")
    ContextTelemetry.recordFallback(
      area: .settings,
      from: "update-check",
      to: "failed",
      reason: "sparkle-\(nsError.domain)-\(nsError.code)",
      outcome: .degraded)
    Task { @MainActor in
      owner?.report(
        "Context for Claude couldn't check for updates. "
          + "Check your connection and try again later.")
    }
  }
}
