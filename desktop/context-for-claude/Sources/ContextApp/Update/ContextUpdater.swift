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
/// `.updateCheck` names itself in `NetworkEgress.Client` and is enforced at every point Sparkle will
/// let it be — see ``UpdateEgress`` — plus ``checkForUpdates()``, which explains itself rather than
/// silently doing nothing.
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

/// Every moment Sparkle reaches the network on this app's behalf, and the one switch all of them ask.
///
/// **A check and its download are two requests, and they were guarded as one.** `mayPerform` fires
/// before the appcast is fetched, and with `automaticallyDownloadsUpdates` true Sparkle then goes on
/// — release notes, then the archive — without asking again. So "was the check allowed?" was the
/// only question the app ever answered, and Airgap Mode turned on between the feed coming back and
/// the archive going out still pulled tens of megabytes from a host the user had just asked this app
/// to stop talking to. Naming the steps makes the omission visible; asking at each one closes it.
///
/// The list is exhaustive for the same reason `NetworkEgress.Client` is: a step nobody enumerated is
/// a step nobody can check, and `UpdatePolicyTests` iterates ``Step/allCases``.
///
/// **What this cannot do, stated plainly.** Sparkle exposes no way to cancel a download already in
/// flight — there is no delegate callback during one and no public cancel on `SPUUpdater` — so a
/// switch flipped *mid-archive* is obeyed on the next step, not on the current byte. Every point
/// Sparkle offers is used here; the remaining window is Sparkle's, not this app's.
enum UpdateEgress {

  /// The three callbacks, in the order Sparkle invokes them.
  ///
  /// Raw values are the slugs a refusal is recorded under, so they are fixed and carry no user text.
  enum Step: String, CaseIterable, Sendable {
    /// `updater(_:mayPerform:)` — before the appcast is fetched. The only seam the *background*
    /// checker has: nobody calls it, so nobody can guard it at a call site.
    case feedCheck = "feed-check"
    /// `updater(_:shouldDownloadReleaseNotesForUpdate:)` — a second request, to the
    /// `<releaseNotesLink>` in the feed. Cheap, and still a request the user was told would not be
    /// made.
    case releaseNotes = "release-notes"
    /// `updater(_:shouldProceedWithUpdate:updateCheck:)` — the last callback before Sparkle
    /// downloads the archive, and the only one that can refuse it.
    case archiveDownload = "archive-download"
  }

  /// Whether `step` may reach the network right now, recording the refusal when it may not.
  ///
  /// The flag is read here rather than passed in from the step before, because the whole point is
  /// that the answer changes between steps. `isSuppressed` is injected so both answers are drivable
  /// in a test without a feed, an archive, or a running updater.
  static func permits(
    _ step: Step,
    isSuppressed: () -> Bool = { NetworkEgress.isSuppressed(.updateCheck) }
  ) -> Bool {
    guard isSuppressed() else { return true }
    ContextLog.info("update \(step.rawValue) suppressed: Airgap Mode is on", "update")
    NetworkEgress.recordSuppression(.updateCheck, outcome: .degraded)
    return false
  }

  /// What Sparkle is thrown when a step is refused. Carries the same sentence the Settings row
  /// shows, so a refusal reads the same wherever it surfaces.
  static var refusal: NSError {
    NSError(
      domain: "com.omi.context-for-claude.update",
      code: 1,
      userInfo: [NSLocalizedDescriptionKey: NetworkEgress.explanation(.updateCheck)])
  }
}

/// Sparkle's delegate, kept separate because Sparkle requires an `NSObject` and calls back on its own
/// schedule — including from `willInstallUpdate:`, moments before it terminates the process.
///
/// Internal rather than private so a test can ask the ObjC runtime whether this class actually
/// implements the callbacks Airgap Mode is enforced through. That is not ceremony: `SPUUpdaterDelegate`
/// is an all-optional protocol, Sparkle decides what to call with `-respondsToSelector:`, and a gate
/// written for a callback that is never invoked looks exactly like a gate that works. The download
/// gate below was missing for as long as this file existed, and nothing failed.
@MainActor
final class UpdaterEvents: NSObject, SPUUpdaterDelegate {

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
    guard UpdateEgress.permits(.feedCheck) else { throw UpdateEgress.refusal }
  }

  /// The release notes named by `<releaseNotesLink>` are a second request to a second URL, and
  /// Sparkle would fetch them to render its sheet. Returning `false` costs the sheet its notes and
  /// nothing else.
  func updater(_ updater: SPUUpdater, shouldDownloadReleaseNotesForUpdate item: SUAppcastItem) -> Bool {
    UpdateEgress.permits(.releaseNotes)
  }

  /// **The gate on the download itself.** Sparkle has chosen an item from the feed and is about to
  /// fetch the archive; throwing here means the user is neither shown it nor sent it.
  ///
  /// This is the callback the app did not implement, and the gap it left was not theoretical:
  /// `automaticallyDownloadsUpdates` is true, so an allowed check ran straight on into a download
  /// with no second question. Someone who turned Airgap Mode on while the appcast was in flight got
  /// the archive anyway.
  func updater(
    _ updater: SPUUpdater,
    shouldProceedWithUpdate updateItem: SUAppcastItem,
    updateCheck: SPUUpdateCheck
  ) throws {
    // Before the egress guard, because "the feed offered us a newer build" is true whether or not
    // this machine is allowed to fetch it — and an install that keeps finding updates it never
    // downloads is the exact shape of a stuck fleet, which is invisible if this is only recorded on
    // the paths that succeed.
    ContextAnalytics.record(.updateOutcome(.updateFound))
    guard UpdateEgress.permits(.archiveDownload) else { throw UpdateEgress.refusal }
  }

  /// A downloaded update is extracted in the background. This state/message is also reflected in
  /// Settings, while the automatic driver's install-on-quit hook below supplies the actual prompt.
  func updater(_ updater: SPUUpdater, didExtractUpdate item: SUAppcastItem) {
    ContextAnalytics.record(.updateOutcome(.installed))
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
    ContextAnalytics.record(.updateOutcome(.upToDate))
    Task { @MainActor in owner?.report("Context for Claude is up to date.") }
  }

  func updater(_ updater: SPUUpdater, didAbortWithError error: Error) {
    // Sparkle reports "no update found" through this path as well as through the callback above,
    // and it is not a failure. Written as the literal rather than as `SUError.noUpdateError`
    // because that enum's Swift spelling comes out of the importer's prefix-stripping rules and
    // is not worth depending on; `SUNoUpdateError = 1001` in `SUErrors.h` is.
    let nsError = error as NSError
    guard nsError.code != 1001 else { return }
    // Only after the 1001 filter: counting "no update found" as a failure would report a healthy
    // fleet as a broken one, and update health is the metric most likely to be read in a panic.
    ContextAnalytics.record(.updateOutcome(.checkFailed))
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
