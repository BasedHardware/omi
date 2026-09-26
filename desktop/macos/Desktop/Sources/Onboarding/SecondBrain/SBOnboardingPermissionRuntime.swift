import AppKit
@preconcurrency import ApplicationServices
import Foundation

// MARK: - Grants this process cannot use

/// Which onboarding permission rows can be blocked by a grant this process is
/// unable to act on, however real it is in System Settings.
///
/// macOS evaluates the Screen Recording grant once per window-server
/// connection — at launch. A grant that lands while Omi is running is on in
/// System Settings and dead here: capture cannot produce a frame until the app
/// relaunches. Marking the row "on" from the preflight and advancing (what this
/// flow used to do) walks the user straight into the live screen demo, which
/// then claims "I can see it" over a capture path that is silently dead.
enum SBPermissionRelaunchGate {
  static func needsRelaunch(
    key: String,
    screenRecordingNeedsRelaunch: Bool,
    systemAudioTapDenied: Bool
  ) -> Bool {
    switch key {
    case "screen_recording":
      return screenRecordingNeedsRelaunch
    case "system_audio":
      // A Core Audio process tap has its own consent, so a refused tap is not
      // on its own a relaunch problem. It is one when the Screen Recording
      // prerequisite only arrived after launch: every retry in this process
      // then fails identically, and the Allow button no longer even opens
      // Settings once the preflight reads true — an escape-less loop.
      return screenRecordingNeedsRelaunch && systemAudioTapDenied
    default:
      // Everything else — including Full Disk Access, which tccd evaluates per
      // file operation — applies to the running process the moment it is given.
      return false
    }
  }
}

/// What a permission step's primary button does right now.
enum SBPermissionStepAction: Equatable {
  /// Nothing has been asked yet. The user's click is what asks — never a poll.
  case allow
  /// macOS has already been asked. Re-probe instead of asking again.
  case recheck
  /// Granted and usable by this process.
  case proceed
  /// Granted, but only a fresh launch can use it.
  case reopen
}

// MARK: - Automation (Apple Events) consent

/// The Automation TCC request, isolated so it can be swapped in tests and so
/// the blocking call has one owner.
enum SBAutomationConsent {
  static let systemEventsBundleID = "com.apple.systemevents"

  /// What the request observed, and by which mechanism.
  struct Outcome: Sendable, Equatable {
    /// `noErr` granted, `-1743` denied, `-1744` still undetermined,
    /// `-600` the target never started.
    var status: OSStatus
    /// The documented request path did not determine anything, so the raw
    /// Apple Event send was used instead. Reported as fallback telemetry.
    var usedAppleEventFallback = false
  }

  /// **Blocking.** Raises the Automation prompt for System Events and reports
  /// the resulting status. Never call this on the main actor: it does not
  /// return until the user answers the modal.
  ///
  /// `AEDeterminePermissionToAutomateTarget(askUserIfNeeded: true)` is the
  /// documented request path and — unlike `NSAppleScript`, which this flow used
  /// to send a throwaway "who is frontmost" event with, and which is only safe
  /// to drive from a single known thread — it is a plain C call with no
  /// main-thread requirement. It also *returns* the answer, so the grant is
  /// adopted from the prompt itself instead of from a second probe racing it.
  static func requestSystemEventsConsent() -> Outcome {
    // Already answered? Asking again is what makes a spent prompt feel dead:
    // macOS will not re-show it, so the click would do nothing visible.
    let known = currentSystemEventsPermission()
    if known == noErr || known == -1743 { return Outcome(status: known) }

    launchSystemEventsIfNeeded()
    var status = determinePermission(askUserIfNeeded: true)
    if status == -600 {
      // TCC has nothing to attribute the request to while the target is
      // stopped. Give the launch one more chance rather than reporting a
      // permission answer nobody was asked for.
      launchSystemEventsIfNeeded()
      status = determinePermission(askUserIfNeeded: true)
    }
    guard status == -1744 else { return Outcome(status: status) }

    // Nothing was determined, so the user was never actually asked. Fall back
    // to the mechanism this app has always used: a real Apple Event to System
    // Events, whose *send* is what registers us with TCC and surfaces the
    // prompt. Same thread as everything else here — off the main actor.
    sendProbeAppleEvent()
    return Outcome(status: determinePermission(askUserIfNeeded: false), usedAppleEventFallback: true)
  }

  /// **Blocking.** Report the current Automation status for System Events
  /// without ever raising a prompt. This is the read every passive status probe
  /// wants — the Permissions page, onboarding re-checks, the chat permission
  /// tool.
  ///
  /// `AEDeterminePermissionToAutomateTarget` answers `-600` (procNotFound)
  /// whenever the target is not running, and System Events is a background-only
  /// app that exits as soon as it goes idle. So on any Mac that is not
  /// currently being scripted — which is the normal state — a bare probe cannot
  /// tell a real grant from no grant at all, and the caller is left projecting
  /// `-600` onto whatever it happened to believe before. From a cold launch
  /// that belief is the `false` default, so a permission the user granted
  /// months ago reads "Not Granted" for the whole session, on every refresh.
  ///
  /// Starting the target is what makes the question answerable. LaunchServices
  /// sends no Apple Event, and `askUserIfNeeded: false` cannot raise a dialog,
  /// so this stays silent: it is still a status read, not a request.
  ///
  /// `determine` and `launch` are injection seams for tests; production passes
  /// neither and gets the real Apple Event and LaunchServices calls.
  static func currentSystemEventsPermission(
    determine: ((Bool) -> OSStatus)? = nil,
    launch: (() -> Void)? = nil
  ) -> OSStatus {
    let read = determine ?? { determinePermission(askUserIfNeeded: $0) }
    let start = launch ?? { launchSystemEventsIfNeeded() }

    let status = read(false)
    guard status == -600 else { return status }
    start()
    return read(false)
  }

  private static func sendProbeAppleEvent() {
    var error: NSDictionary?
    NSAppleScript(
      source: "tell application \"System Events\" to return name of first process whose frontmost is true"
    )?.executeAndReturnError(&error)
  }

  /// System Events is a background-only app; launching it with LaunchServices
  /// sends no Apple Event, so it cannot itself trip a TCC prompt — neither the
  /// one the request path raises deliberately, nor any at all on the silent
  /// status read.
  private static func launchSystemEventsIfNeeded() {
    guard
      NSRunningApplication.runningApplications(withBundleIdentifier: systemEventsBundleID).isEmpty,
      let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: systemEventsBundleID)
    else { return }
    let configuration = NSWorkspace.OpenConfiguration()
    configuration.activates = false
    configuration.addsToRecentItems = false
    let launched = DispatchSemaphore(value: 0)
    NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, _ in
      launched.signal()
    }
    _ = launched.wait(timeout: .now() + 5)
  }

  private static func determinePermission(askUserIfNeeded: Bool) -> OSStatus {
    var addressDesc = AEAddressDesc()
    return systemEventsBundleID.withCString { cString in
      AECreateDesc(typeApplicationBundleID, cString, strlen(cString), &addressDesc)
      let result = AEDeterminePermissionToAutomateTarget(
        &addressDesc,
        typeWildCard,
        typeWildCard,
        askUserIfNeeded
      )
      AEDisposeDesc(&addressDesc)
      return result
    }
  }
}

// MARK: - Model wiring

extension SBOnboardingModel {
  /// True when `key`'s grant exists but this process cannot act on it.
  func permissionNeedsRelaunch(_ key: String) -> Bool {
    SBPermissionRelaunchGate.needsRelaunch(
      key: key,
      screenRecordingNeedsRelaunch: appState.screenRecordingNeedsRelaunch,
      systemAudioTapDenied: appState.systemAudioPermissionStatus == .denied)
  }

  /// What the step's primary button must do. The view renders from this, so the
  /// escape hatches are a property of the model rather than of a layout.
  func permissionPrimaryAction(_ key: String) -> SBPermissionStepAction {
    Self.permissionPrimaryAction(
      state: permState(key),
      needsRelaunch: permissionNeedsRelaunch(key))
  }

  static func permissionPrimaryAction(
    state: PermState,
    needsRelaunch: Bool
  ) -> SBPermissionStepAction {
    // A grant this process cannot use outranks everything: neither "Continue"
    // (it would advance over dead capture) nor "Allow" (it would fail
    // identically, forever) is a real option on that row.
    if needsRelaunch { return .reopen }
    switch state {
    case .on: return .proceed
    case .waiting: return .recheck
    case .ask: return .allow
    }
  }

  /// The relaunch the user accepts from a permission step.
  ///
  /// Persists the step to resume at **before** handing the process over —
  /// otherwise the relaunched app comes back on this same row, re-detects the
  /// same unusable grant, and offers the reopen again.
  @discardableResult
  func acceptPermissionRelaunch(
    _ key: String,
    needsRelaunch: Bool,
    restart: () -> Void
  ) -> Bool {
    guard needsRelaunch else { return false }
    let resume = Step(rawValue: step.rawValue + 1) ?? step
    UserDefaults.standard.set(resume.rawValue, forKey: Self.resumeStepKey)
    restart()
    return true
  }

  func acceptPermissionRelaunch(_ key: String) {
    let appState = self.appState
    acceptPermissionRelaunch(key, needsRelaunch: permissionNeedsRelaunch(key)) {
      appState.restartApp()
    }
  }

  // MARK: re-probing

  /// Off-main variant of `refreshPermCheck`.
  ///
  /// Accessibility, Full Disk Access and Automation are probed by cross-process
  /// round trips: `AXUIElementCopyAttributeValue` against the frontmost app and
  /// possibly Finder, `CGEvent.tapCreate`, `contentsOfDirectory` on a
  /// TCC-protected directory, and an Apple Event permission lookup. A 20s poll
  /// runs those forty times; on the main actor that is the onboarding window's
  /// entire frame budget.
  func refreshPermCheckOffMain(_ key: String) async {
    switch key {
    case "full_disk_access": await appState.refreshFullDiskAccess()
    case "accessibility": await appState.refreshAccessibilityPermission()
    case "automation": await appState.refreshAutomationPermission()
    default: refreshPermCheck(key)
    }
  }

  /// Re-probe the permission the visible step gates on. Wired to
  /// `NSApplication.didBecomeActiveNotification`.
  ///
  /// Granting in System Settings means leaving Omi and coming back, so that
  /// return is the signal a grant may have landed. The 20s poll is only a
  /// backstop for a grant made without ever switching apps — Full Disk Access
  /// and Accessibility (open Settings → authenticate → toggle) routinely
  /// outlive it, and before this the flow simply went deaf at that point.
  func recheckActivePermission() {
    guard let key = permissionKey(for: step) else { return }
    recheckPermission(key)
  }

  /// The "Waiting for macOS…" button, which used to be `.disabled` for the
  /// entire poll — a user who had already granted had no way to say so.
  func recheckPermission(_ key: String) {
    pollTasks[key]?.cancel()
    let task: Task<Void, Never> = Task { [weak self] in
      guard let self else { return }
      await self.recheckPermission(key, refresh: { await self.refreshPermCheckOffMain($0) })
    }
    pollTasks[key] = task
  }

  /// Adopt a grant that has landed. Asks macOS for nothing — the user's click
  /// already did that — so it is safe on every reactivation and every press.
  func recheckPermission(_ key: String, refresh: (String) async -> Void) async {
    guard !Task.isCancelled, permissionKey(for: step) == key else { return }
    await refresh(key)
    guard !Task.isCancelled, permissionKey(for: step) == key, isGranted(key) else { return }
    setPermOn(key)
    // `autoAdvanceIfCurrent` is the fence: a probe that finishes after the user
    // has moved on must redraw at most, never yank the flow forward.
    autoAdvanceIfCurrent(key)
  }

  // MARK: automation request

  /// Ask macOS for Automation (Apple Events) consent.
  ///
  /// The request blocks until the user answers a modal TCC dialog. It used to
  /// run inside `Task { @MainActor … }`, so the whole SwiftUI onboarding window
  /// froze behind that dialog for as long as the user took to read it. Only the
  /// state write belongs on the main actor; the request itself is detached.
  ///
  /// - Parameters:
  ///   - consent: the blocking request. Returns the resulting `OSStatus`.
  ///   - openSettings: where a *spent* prompt sends the user. `nil` uses the
  ///     real Automation privacy pane.
  @discardableResult
  func beginAutomationRequest(
    consent: @escaping @Sendable () -> SBAutomationConsent.Outcome = {
      SBAutomationConsent.requestSystemEventsConsent()
    },
    openSettings: (@MainActor () -> Void)? = nil
  ) -> Task<Void, Never> {
    autoState = .waiting
    return Task { [weak self] in
      let outcome = await Task.detached(priority: .userInitiated) { consent() }.value
      guard let self, !Task.isCancelled, self.permissionKey(for: self.step) == "automation" else {
        return
      }
      let status = outcome.status
      if outcome.usedAppleEventFallback {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "automation_bridge",
          from: "tcc_determine_permission",
          to: "apple_event_send",
          reason: "capability_mismatch",
          outcome: status == -1744 ? .exhausted : .recovered)
      }
      // The prompt's own answer is the freshest evidence there is; adopting it
      // directly is what stops the row reading a status one probe stale.
      let granted = self.appState.applyAutomationPermissionStatus(status)
      guard !granted else {
        self.setPermOn("automation")
        self.autoAdvanceIfCurrent("automation")
        return
      }
      self.resetPermToAsk("automation")
      guard status == -1743 else { return }
      // Denied: macOS will never show that prompt again, so re-arming Allow on
      // its own is a dead button. Settings is the only route left, and the
      // reactivation re-check picks the grant up when the user comes back.
      if let openSettings {
        openSettings()
      } else {
        self.appState.openAutomationPreferences()
      }
    }
  }
}
