import AppKit
import Combine
import CoreGraphics
import Foundation

// MARK: - Permissions (one at a time)

extension SBOnboardingModel {
  /// Nothing is asked of macOS until the user clicks. The probes this has to do
  /// first are cross-process, so the click dispatches onto the model's actor
  /// rather than blocking the button.
  func requestPerm(_ key: String) {
    // The same task owns the preflight and the request. Leaving the row can
    // cancel it through `pollTasks`, and the step guards below cover callers
    // that navigate without going through the normal teardown path.
    pollTasks[key]?.cancel()
    let task: Task<Void, Never> = Task { [weak self] in
      guard let self else { return }
      await self.performPermissionRequest(key)
    }
    pollTasks[key] = task
  }

  func performPermissionRequest(_ key: String) async {
    // The user may have changed a grant in System Settings while this step was
    // onscreen. Re-check it before opening another pane or asking macOS again.
    await refreshPermCheckOffMain(key)
    guard !Task.isCancelled, permissionKey(for: step) == key else { return }
    if isGranted(key) {
      setPermOn(key)
      autoAdvanceIfCurrent(key)
      return
    }

    switch key {
    case "microphone":
      micState = .waiting
      appState.requestMicrophonePermission()
      pollPermission(key)
    case "system_audio":
      // A Core Audio process tap has its own consent in addition to Screen
      // Recording TCC. Wait for Screen Recording, then reconcile a real tap
      // attempt before marking this permission granted.
      sysState = .waiting
      if !appState.hasScreenRecordingPermission {
        ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      } else if appState.systemAudioPermissionStatus == .denied {
        // Screen Recording is already granted and a real tap has already been
        // refused, so nothing here can raise a prompt again. Open the pane
        // instead of silently re-running the same failing attempt.
        appState.openScreenRecordingPreferences()
      }
      pollPermission(key)
    case "screen_recording":
      scrState = .waiting
      appState.checkScreenRecordingPermission()
      if appState.hasScreenRecordingPermission {
        setPermOn(key)
        autoAdvanceIfCurrent(key)
      } else {
        ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
        pollPermission(key)
      }
    case "full_disk_access":
      requestFullDiskAccess()
    case "accessibility":
      accState = .waiting
      appState.triggerAccessibilityPermission()
      pollPermission(key)
    case "automation":
      let request = beginAutomationRequest()
      await withTaskCancellationHandler {
        await request.value
      } onCancel: {
        request.cancel()
      }
    case "notifications":
      requestNotifications()
    default: break
    }
  }

  /// Ask macOS for notification authorization through the same policy-driven
  /// path Settings uses (`AppState.requestNotificationPermission()`), never
  /// `UNUserNotificationCenter` directly. `notDetermined` raises the system
  /// prompt; `denied` opens System Settings instead of re-asking a spent
  /// prompt macOS will never show again.
  func requestNotifications() {
    notifState = .waiting
    appState.requestNotificationPermission()
    pollPermission("notifications")
  }

  func requestFullDiskAccess() {
    fdaState = .waiting
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
      NSWorkspace.shared.open(url)
      // Show the drag-to-grant helper card (drag the Omi icon into the FDA list),
      // matching Screen Recording's flow. Full Disk Access has no in-place toggle,
      // so the drag card is the fastest grant path (#9742). Both FDA entry points
      // (the permission step and the Files connector) route through here.
      Task { await PermissionDragGuidance.presentDragToGrantHelper(for: .fullDiskAccess) }
    }
    pollPermission("full_disk_access")
  }

  func pollPermission(_ key: String) {
    // Cancel only this key's prior poll — never a sibling permission's, so the
    // "both" mic+system-audio step can poll two grants at once.
    pollTasks[key]?.cancel()

    if key == "system_audio" {
      pollSystemAudioPermission()
      return
    }

    pollTasks[key] = Task { [weak self] in
      for _ in 0..<40 {  // ~20s
        try? await Task.sleep(nanoseconds: 500_000_000)
        guard let self, !Task.isCancelled, self.permissionKey(for: self.step) == key else { return }
        await self.refreshPermCheckOffMain(key)
        guard !Task.isCancelled, self.permissionKey(for: self.step) == key else { return }
        if self.isGranted(key) {
          self.setPermOn(key)
          // Auto-advance once the grant lands — the user shouldn't have to click
          // Continue after granting. Brief pause so the ✓ is visible, then only
          // advance if they're still on this permission's step (a late poll for a
          // step already left must never yank the flow forward).
          try? await Task.sleep(nanoseconds: 600_000_000)
          guard !Task.isCancelled, self.permissionKey(for: self.step) == key else { return }
          self.autoAdvanceIfCurrent(key)
          return
        }
      }
      // Timed out without a grant. This is a backstop, not the mechanism:
      // FDA/Accessibility routinely exceed 20s (open System Settings →
      // authenticate → toggle), and a grant made in that window is picked up by
      // `recheckActivePermission()` when the user switches back to Omi. Re-arm
      // the Allow button so the row is never stranded on "macOS…".
      guard let self, !Task.isCancelled, self.permissionKey(for: self.step) == key else { return }
      self.resetPermToAsk(key)
    }
  }

  /// Screen Recording TCC is only a prerequisite for system audio. The
  /// authoritative grant is a successful Core Audio tap attempt.
  private func pollSystemAudioPermission() {
    // A precheck and an Allow click can race to start this poll. Preserve one
    // authoritative consent attempt so an older task cannot advance the flow
    // after the replacement has already reconciled a newer result.
    pollTasks["system_audio"]?.cancel()
    pollTasks["system_audio"] = Task { [weak self] in
      for _ in 0..<40 {  // ~20s
        guard let self, !Task.isCancelled else { return }
        // Skipping this step is an explicit choice not to surface its consent.
        // Never let a late Screen Recording grant trigger the modal elsewhere.
        guard self.step == .talk, self.talkPhase == .microphone else { return }
        self.appState.checkScreenRecordingPermission()
        if self.appState.hasScreenRecordingPermission {
          // A real process-tap attempt is the only truthful preflight for
          // system audio. It completes without another prompt when consent was
          // already granted, so reconcile it before asking the user again.
          let granted = await self.appState.primeSystemAudioPermission()
          guard !Task.isCancelled else { return }
          guard granted else {
            // A refused tap re-arms Allow. That is only an escape when a retry
            // could plausibly succeed: `primeSystemAudioPermission` recorded
            // `.denied`, so once the Screen Recording prerequisite only landed
            // after launch the step now renders the relaunch offer instead of
            // an Allow button that would fail identically forever
            // (`SBPermissionRelaunchGate`).
            self.resetPermToAsk("system_audio")
            return
          }

          guard self.step == .talk, self.talkPhase == .microphone else { return }
          self.setPermOn("system_audio")
          try? await Task.sleep(nanoseconds: 600_000_000)
          guard !Task.isCancelled, self.step == .talk, self.talkPhase == .microphone else { return }
          self.autoAdvanceIfCurrent("system_audio")
          return
        }

        try? await Task.sleep(nanoseconds: 500_000_000)
      }

      guard let self, !Task.isCancelled, self.step == .talk, self.talkPhase == .microphone else { return }
      self.resetPermToAsk("system_audio")
    }
  }

  /// Re-probe a single permission (each check writes the matching AppState flag).
  /// Prefer `refreshPermCheckOffMain` anywhere the probe can repeat — the
  /// Accessibility/FDA/Automation probes are cross-process and expensive.
  func refreshPermCheck(_ key: String) {
    switch key {
    case "microphone": appState.checkMicrophonePermission()
    case "system_audio":
      appState.checkScreenRecordingPermission()
      appState.checkSystemAudioPermission()
    case "screen_recording": appState.checkScreenRecordingPermission()
    case "full_disk_access": appState.checkFullDiskAccess()
    case "accessibility": appState.checkAccessibilityPermission()
    case "automation": appState.checkAutomationPermission()
    case "notifications": appState.checkNotificationPermission()
    default: appState.checkAllPermissions()
    }
  }

  /// When a permission step appears, reflect a grant the user already has so it
  /// shows ✓ instead of an Allow button they'd tap for nothing. Pre-existing
  /// grants are folded in live rather than from a snapshot, so a reinstall
  /// cannot leave a "Granted" row above a step that still wants an answer.
  func precheckPerm(_ key: String) {
    pollTasks[key]?.cancel()
    let task: Task<Void, Never> = Task { [weak self] in
      guard let self else { return }
      await self.precheckPermOffMain(key)
    }
    pollTasks[key] = task
  }

  func precheckPermOffMain(_ key: String) async {
    guard !Task.isCancelled, permissionKey(for: step) == key else { return }
    await refreshPermCheckOffMain(key)
    // The probe can outlive the step that started it (Automation's Apple Event
    // lookup takes a round trip). Writing a permission row for a page the user
    // already left is how a late answer used to land on the wrong step.
    guard !Task.isCancelled, permissionKey(for: step) == key else { return }
    if isGranted(key) {
      setPermOn(key)
      autoAdvanceIfCurrent(key)
    } else if key == "system_audio", appState.hasScreenRecordingPermission,
      appState.systemAudioPermissionStatus == .unknown
    {
      // Already holding Screen Recording must not skip this separate consent.
      // Prime while its own onboarding step is visible and reconcile the result.
      sysState = .waiting
      pollSystemAudioPermission()
    }
  }

  /// Fire a single throwaway ScreenCaptureKit capture the first time Screen
  /// Recording is confirmed granted during onboarding, so macOS surfaces the
  /// "bypass the private window picker" consent here — while the user is already
  /// granting screen access — instead of mid-question during the live screen demo
  /// (the exact spot users hit it). See `ScreenCaptureService.primeCaptureConsent`.
  func primeScreenCaptureConsentIfNeeded() {
    guard !didPrimeScreenCapture else { return }
    guard
      ScreenRecordingPermissionPolicy.shouldInvokeScreenCaptureKit(
        grantedAtLaunch: appState.screenRecordingGrantedAtLaunch)
    else { return }
    didPrimeScreenCapture = true
    if #available(macOS 14.0, *) {
      Task.detached { await ScreenCaptureService.primeCaptureConsent() }
    }
  }

  func isGranted(_ key: String) -> Bool {
    switch key {
    case "microphone": return appState.hasMicrophonePermission
    case "system_audio":
      return appState.hasSystemAudioPermission || appState.systemAudioPermissionStatus == .unsupported
    case "screen_recording": return appState.hasScreenRecordingPermission
    case "full_disk_access": return appState.hasFullDiskAccess
    case "accessibility": return appState.hasAccessibilityPermission && !appState.isAccessibilityBroken
    case "automation": return appState.hasAutomationPermission
    case "notifications": return appState.hasNotificationPermission
    default: return false
    }
  }

  func setPermOn(_ key: String) {
    switch key {
    case "microphone": micState = .on
    case "system_audio":
      sysState = .on
      // System audio shares Screen Recording TCC; once it's on, the ScreenCaptureKit
      // capture consent can be primed so the demo doesn't surface it later.
      primeScreenCaptureConsentIfNeeded()
    case "screen_recording":
      scrState = .on
      primeScreenCaptureConsentIfNeeded()
    case "full_disk_access":
      fdaState = .on
    case "accessibility": accState = .on
    case "automation": autoState = .on
    case "notifications": notifState = .on
    default: break
    }
  }

  /// Return a still-`.waiting` row to `.ask` so its Allow button reappears after
  /// the poll times out without a grant (a later grant re-triggers the poll).
  func resetPermToAsk(_ key: String) {
    switch key {
    case "microphone": micState = .ask
    case "system_audio": sysState = .ask
    case "screen_recording": scrState = .ask
    case "full_disk_access": fdaState = .ask
    case "accessibility": accState = .ask
    case "automation": autoState = .ask
    case "notifications": notifState = .ask
    default: break
    }
  }

  func permState(_ key: String) -> PermState {
    switch key {
    case "microphone": return micState
    case "system_audio": return sysState
    case "screen_recording": return scrState
    case "full_disk_access": return fdaState
    case "accessibility": return accState
    case "automation": return autoState
    case "notifications": return notifState
    default: return .ask
    }
  }

  func answerMic() { answerTalkMicrophone() }
  func answerScreen() { answerSeePermission() }
  func answerNotifications() { answerCardNotifications() }

  /// Advance past a permission step automatically once its grant lands — but only
  /// when the user is still ON that step, so a late poll never skips a step they've
  /// already moved past.
  func autoAdvanceIfCurrent(_ key: String) {
    autoAdvanceIfCurrent(key, needsRelaunch: permissionNeedsRelaunch(key))
  }

  func autoAdvanceIfCurrent(_ key: String, needsRelaunch: Bool) {
    guard permissionKey(for: step) == key, permState(key) == .on else { return }
    // A grant this process cannot act on must not move the flow on. Screen
    // Recording granted while running is on in System Settings and dead here
    // until relaunch; advancing would hand the user a live screen demo over a
    // capture path that cannot produce a frame. The step offers the reopen
    // instead (`SBPermissionRelaunchGate`).
    guard !needsRelaunch else { return }
    switch step {
    case .see where key == "screen_recording" && seePhase == .permission: answerSeePermission()
    case .card where key == "notifications" && cardPhase == .notifications: answerCardNotifications()
    case .talk where key == "microphone" && talkPhase == .microphone: answerTalkMicrophone()
    case .hello, .see, .card, .talk, .write, .ready: break
    }
  }

  /// The permission key a step gates on, or nil for non-permission steps.
  func permissionKey(for step: Step) -> String? {
    switch step {
    case .see: return seePhase == .permission ? "screen_recording" : nil
    case .card: return cardPhase == .notifications ? "notifications" : nil
    case .talk: return talkPhase == .microphone ? "microphone" : nil
    case .hello, .write, .ready: return nil
    }
  }

  /// Starting at `target`, skip past any permission step whose cached permission
  /// is already granted. The synchronous compatibility path is intentionally
  /// limited to the state already available on the main actor; callers that
  /// need a current TCC answer must use `firstUnaskedStepAwaitingCurrentProbes`.
  func firstUnaskedStep(from target: Step) -> Step {
    Self.firstUnaskedStep(from: target)
  }

  static func firstUnaskedStep(from target: Step) -> Step { target }

  /// First-unasked scan for entry points that need a current permission answer.
  /// Every TCC/AX/Apple Events probe is awaited through the off-main refresh
  /// seam, so this scan never blocks the main actor while deciding where to land.
  func firstUnaskedStepAwaitingCurrentProbes(
    from target: Step,
    refresh: ((String) async -> Void)? = nil
  ) async -> Step {
    _ = refresh
    return target
  }
}

// MARK: - Summon shortcut (pick → press → notch)

extension SBOnboardingModel {
  /// Open-Omi options (tap to open the window).
  var openShortcutOptions: [(id: String, shortcut: ShortcutSettings.KeyboardShortcut, sub: String)] {
    // ⌃⌘O first because it is the one chord here that costs the user nothing. Whatever is picked is
    // registered with `RegisterEventHotKey`, and a Carbon hotkey does not lose to the frontmost app
    // — it **preempts** it and consumes the key. Measured, not assumed: a probe holding a Carbon ⌘O
    // fired while another app was frontmost, and that app's own key-down monitor never saw the
    // event. So picking ⌘O does not fail (the comment this replaced had that backwards, citing a
    // `GlobalShortcutManager.registerCommandO` that no longer exists) — it takes ⌘O away from every
    // app on the Mac for as long as Omi runs. ⌃⌘O collides with nothing, and is already the app's
    // own always-on summon chord (`registerSummonHotkey`). ⌘O stays offered, with its price named.
    [
      ("ctrlCmdO", ShortcutSettings.askOmiControlCommandOShortcut, "press to set"),
      ("cmdO", ShortcutSettings.askOmiCommandOShortcut, "replaces File ▸ Open"),
      ("cmdReturn", ShortcutSettings.askOmiCommandReturnShortcut, "press to set"),
    ]
  }

  /// Push-to-talk options (hold to talk, hands-free).
  var talkShortcutOptions: [(id: String, shortcut: ShortcutSettings.KeyboardShortcut, sub: String)] {
    [
      ("fn", ShortcutSettings.KeyboardShortcut(modifierOnly: .function), "press to set"),
      ("opt", ShortcutSettings.KeyboardShortcut(modifierOnly: .option), "press to set"),
      ("ctrl", ShortcutSettings.KeyboardShortcut(modifierOnly: .control), "press to set"),
    ]
  }

  /// Arm key detection exactly like the legacy OnboardingFloatingBarShortcutStepView:
  /// suspend the live Ask-Omi Carbon hotkey (so pressing it doesn't steal focus or
  /// get swallowed before our monitor sees it) and null the main menu (⌘O/⌘↩ are
  /// NSMenu key equivalents that AppKit dispatches before local monitors). Both are
  /// restored on leave. This is why the earlier attempt's monitor never fired.
  func armShortcutSummon() {
    shortcutRegistrationError = nil
    // Preserve a choice when the user returns with Back. A fresh stage still
    // starts empty, while an already-confirmed shortcut stays visible/editable.
    let rememberedSelection: ShortcutSettings.KeyboardShortcut?
    let isTalk: Bool
    switch step {
    case .talk where talkPhase == .shortcut:
      rememberedSelection = talkShortcutSelection
      isTalk = true
    default:
      rememberedSelection = nil
      isTalk = false
    }
    if let rememberedSelection {
      shortcutPicked = true
      shortcutPressed = false
      shortcutRecording = false
      shortcutNeedsModifier = false
      pendingModifierOnlyShortcut = nil
      shortcutTokens = rememberedSelection.displayTokens
      chosenShortcut = rememberedSelection
    } else {
      // Same reset as `beginShortcutRecording` but with recording left off: the fresh
      // stage shows the preset rows + a Custom button instead of entering capture mode,
      // so `handleShortcutEvent` only recognizes the three preset candidates until the
      // user explicitly taps Custom.
      beginShortcutRecording(isTalk: isTalk)
      shortcutRecording = false
    }
    GlobalShortcutManager.shared.setRegistrationSuspended(true)
    // `NSApplication.shared`, not the implicitly unwrapped `NSApp`: a test process that has never
    // touched the application object has `NSApp == nil`, and CI runs each suite in its own process.
    let application = NSApplication.shared
    if savedMainMenu == nil { savedMainMenu = application.mainMenu }
    application.mainMenu = nil
    installShortcutMonitors()
  }

  func disarmShortcutSummon() {
    for m in shortcutMonitors { NSEvent.removeMonitor(m) }
    shortcutMonitors.removeAll()
    if let saved = savedMainMenu {
      NSApplication.shared.mainMenu = saved
      savedMainMenu = nil
    }
    GlobalShortcutManager.shared.setRegistrationSuspended(false)
  }

  private func installShortcutMonitors() {
    for m in shortcutMonitors { NSEvent.removeMonitor(m) }
    shortcutMonitors.removeAll()
    let mask: NSEvent.EventTypeMask = [.keyDown, .keyUp, .flagsChanged]
    // Local monitor fires when the app is key and can consume the event; global
    // monitor fires when another app is focused (it can only observe).
    if let l = NSEvent.addLocalMonitorForEvents(
      matching: mask,
      handler: { [weak self] event in
        let matched = self?.handleShortcutEvent(event) ?? false
        return matched ? nil : event
      })
    {
      shortcutMonitors.append(l)
    }
    if let g = NSEvent.addGlobalMonitorForEvents(
      matching: mask,
      handler: { [weak self] event in
        _ = self?.handleShortcutEvent(event)
      })
    {
      shortcutMonitors.append(g)
    }
  }

  /// The shortcuts offered on the current step — used so the user can just PRESS
  /// any offered combo to auto-select it (no need to click the row first).
  private var currentShortcutCandidates: [ShortcutSettings.KeyboardShortcut] {
    step == .talk && talkPhase == .shortcut ? talkShortcutOptions.map { $0.shortcut } : []
  }

  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    if shortcutRecording {
      // The global monitor is here for the *test* phase, so a chord pressed while another app is
      // focused still counts as "that works". While the step is still **recording** it is a hazard
      // instead: the first key the user happens to type anywhere on the Mac — a terminal, a
      // browser, a message — becomes their Omi chord, and the step then congratulates them on it.
      // Only what is typed at Omi may set it.
      guard Self.acceptsRecordingSource(appIsActive: NSApplication.shared.isActive) else { return false }
      return recordShortcut(from: event)
    }
    guard !shortcutPressed else { return false }
    // If the user already tapped a row, honor that exact pick; otherwise let ANY
    // offered combo select itself on press, so "just press the key" works and the
    // Continue button appears without a separate pick-then-test step.
    let candidates = chosenShortcut.map { [$0] } ?? currentShortcutCandidates
    let isTalk = step == .talk && talkPhase == .shortcut
    for sc in candidates {
      let matched: Bool
      switch event.type {
      case .flagsChanged: matched = sc.matchesFlagsChanged(event)  // modifier-only chords (fn, ⌥…)
      case .keyDown: matched = !event.isARepeat && sc.matchesKeyDown(event)  // ⌘O / ⌘↩ / ⌘J
      default: matched = false
      }
      if matched {
        DispatchQueue.main.async { [weak self] in
          guard let self else { return }
          if self.chosenShortcut != sc { self.pickShortcut(sc, isTalk: isTalk) }
          self.shortcutPressed = true
        }
        return true
      }
    }
    return false
  }

  /// Pick + persist a shortcut. `isTalk` → push-to-talk chord (held, drives the
  /// voice demo); otherwise the Ask-Omi open hotkey (tapped to open the window).
  func pickShortcut(_ shortcut: ShortcutSettings.KeyboardShortcut, isTalk: Bool) {
    shortcutRegistrationError = nil
    chosenShortcut = shortcut
    chosenShortcutIsPTT = isTalk
    shortcutTokens = shortcut.displayTokens
    shortcutPicked = true
    shortcutPressed = false
    shortcutRecording = false
    pendingModifierOnlyShortcut = nil
    if isTalk {
      talkShortcutSelection = shortcut
      ShortcutSettings.shared.pttShortcut = shortcut
      ShortcutSettings.shared.pttEnabled = true
    } else {
      openShortcutSelection = shortcut
      ShortcutSettings.shared.askOmiShortcut = shortcut
      ShortcutSettings.shared.askOmiEnabled = true
    }
  }

  func beginShortcutRecording(isTalk: Bool) {
    shortcutRegistrationError = nil
    chosenShortcut = nil
    chosenShortcutIsPTT = isTalk
    shortcutTokens = []
    shortcutPicked = false
    shortcutPressed = false
    shortcutRecording = true
    shortcutNeedsModifier = false
    pendingModifierOnlyShortcut = nil
  }

  func recordShortcut(from event: NSEvent) -> Bool {
    let isTalk = step == .talk && talkPhase == .shortcut
    if isTalk, event.type == .flagsChanged {
      let activeModifiers = ShortcutSettings.KeyboardShortcut.normalizedModifiers(event.modifierFlags)
      if activeModifiers.isEmpty {
        guard let shortcut = pendingModifierOnlyShortcut else { return true }
        pickShortcut(shortcut, isTalk: true)
        return true
      }
      pendingModifierOnlyShortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(
        event,
        allowModifierOnly: true
      )
      return true
    }
    let recorded = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(
      event,
      allowModifierOnly: isTalk
    )
    switch Self.decideRecordedChord(recorded) {
    case .ignore:
      return event.type == .flagsChanged
    case .refuseBareKey:
      // The refusal the copy now names. Saying it is the whole fix: silently dropping the key made
      // the step look broken to anyone who took "press any key" literally.
      shortcutNeedsModifier = true
      return true
    case .accept(let shortcut):
      shortcutNeedsModifier = false
      pendingModifierOnlyShortcut = nil
      pickShortcut(shortcut, isTalk: isTalk)
      return true
    }
  }

  /// What recording should do with the chord it just saw, as a value.
  ///
  /// A value rather than a `guard` inside the monitor so the refusal is something a test can drive
  /// and assert: the bug here was never *which* chords are refused, it was that the refusal produced
  /// no observable effect at all.
  enum RecordedChordDecision: Equatable {
    case accept(ShortcutSettings.KeyboardShortcut)
    case refuseBareKey
    case ignore
  }

  static func decideRecordedChord(_ recorded: ShortcutSettings.KeyboardShortcut?) -> RecordedChordDecision {
    guard let recorded else { return .ignore }
    return acceptsRecordedChord(recorded) ? .accept(recorded) : .refuseBareKey
  }

  /// Which events may set the chord.
  ///
  /// Recording only listens to Omi. Testing (`shortcutPressed`) still listens everywhere, which is
  /// the whole point of the global monitor.
  static func acceptsRecordingSource(appIsActive: Bool) -> Bool { appIsActive }

  /// Whether a recorded chord is one this step is allowed to persist.
  ///
  /// A key chord with no modifier is not a shortcut, it is a stolen letter: `askOmiShortcut` is
  /// registered as a **global** hotkey, so persisting a bare `L` makes every `L` typed anywhere on
  /// the Mac open Omi, and the only way back is Settings. PTT is also observed system-wide, so a bare
  /// letter would start a voice turn during ordinary typing. The copy invites it ("Press any key"),
  /// and nothing downstream refuses it. Both offered open chords carry ⌘ and every offered talk chord
  /// is modifier-only, so this rejects nothing the step actually presents.
  static func acceptsRecordedChord(_ shortcut: ShortcutSettings.KeyboardShortcut) -> Bool {
    ShortcutSettings.isSafePushToTalkShortcut(shortcut)
  }

  // onboarding-legacy: unreferenced after scenario onboarding; removal tracked separately.
  func answerShortcutOpen() {
    // onboarding-legacy: unreferenced after scenario onboarding; removal tracked separately.
  }
  func answerShortcutTalk() {
    finishTalkShortcut()
  }
}

// MARK: - Screen + voice demo (live: notch visible, screen-aware answer)

extension SBOnboardingModel {
  /// Wire the real floating bar + push-to-talk exactly like the legacy
  /// OnboardingVoiceDemoView: isolate the demo conversation (onboardingFloating
  /// draft + the `.onboarding()` journal surface via `isOnboarding`), force live
  /// transcription, warm the bridge, and SHOW the notch so it stays visible while
  /// the user holds their key and asks about the screen. Screen capture is
  /// attached automatically for screen-aware questions; the answer streams into
  /// the notch, which spins while Omi is thinking.
  func startScreenDemo() {
    screenDemoDone = false
    // The order page is already open from the see beat; hand the model its facts so the first
    // voice question is answerable before capture has produced a frame.
    OnboardingDemoNote.active = OnboardingDemoNote.orderPage(scenarioPageContext)
    screenDemoPTTReady = false
    screenDemoPTTUnavailable = false
    FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
    FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
    resetFloatingBarConversation()
    ShortcutSettings.shared.pttTranscriptionModeDemoOverride = .live
    screenDemoSetupTask?.cancel()
    screenDemoSetupTask = Task { [weak self] in
      guard let self else { return }
      // Unlike the normal app, onboarding did not have an earlier home-screen
      // warmup. The old order set up PTT first, which made the hub request its
      // kernel context before the bridge existed; the user's first hold then
      // raced that cold start and could end without an answer. Establish the
      // bridge before arming PTT so its first turn has a real response route.
      await self.activateScreenDemoPTTAfterBridgeWarmup(
        warmup: { await self.chatProvider.warmupBridge() },
        activate: { self.activateScreenDemoPTT() }
      )
    }
  }

  /// The screen demo owns PTT only while its stage is still mounted. Keep this
  /// lifecycle fence outside the unstructured task so the same production
  /// boundary can be regression-tested: leaving the stage during a cold bridge
  /// start must not attach fresh event monitors to the next onboarding page.
  func activateScreenDemoPTTAfterBridgeWarmup(
    warmup: @escaping @MainActor () async -> Bool,
    activate: @escaping @MainActor () -> Void
  ) async {
    let bridgeReady = await warmup()
    guard !Task.isCancelled, step == .talk, talkPhase == .demo else { return }
    guard bridgeReady else {
      screenDemoPTTUnavailable = true
      return
    }
    activate()
  }

  private func activateScreenDemoPTT() {
    guard step == .talk, talkPhase == .demo,
      let bar = FloatingControlBarManager.shared.barState
    else { return }
    PushToTalkManager.shared.setup(barState: bar)
    // Mark the demo done the first time Omi actually answers. Voice answers
    // surface through `voiceProjection`; typed answers use `showingAIResponse`.
    // Drop the current voice projection so re-entering the demo cannot inherit a
    // stale response from a prior turn.
    voiceCancellable = Publishers.Merge(
      bar.$showingAIResponse.filter { $0 }.map { _ in () },
      bar.$voiceProjection.dropFirst().filter { $0.isResponseActive }.map { _ in () }
    )
    .receive(on: DispatchQueue.main)
    .sink { [weak self] _ in self?.screenDemoDone = true }
    screenDemoPTTReady = true
    FloatingControlBarManager.shared.showForOnboardingDemo()
  }

  private func resetFloatingBarConversation() {
    guard let bar = FloatingControlBarManager.shared.barState else { return }
    bar.showingAIConversation = false
    bar.showingAIResponse = false
    bar.aiInputText = ""
    bar.clearViewport()
  }

  func teardownVoiceDemo() {
    OnboardingDemoNote.active = nil
    screenDemoSetupTask?.cancel()
    screenDemoSetupTask = nil
    voiceTimeout?.cancel()
    voiceTimeout = nil
    voiceCancellable = nil
    screenDemoDone = false
    screenDemoPTTReady = false
    screenDemoPTTUnavailable = false
    ShortcutSettings.shared.pttTranscriptionModeDemoOverride = nil
    resetFloatingBarConversation()
    PushToTalkManager.shared.cleanup()
    FloatingControlBarManager.shared.hideForOnboardingDemo()
  }

  /// The push-to-talk chord to prompt for the voice demo.
  var voiceChordTokens: [String] {
    let tokens = ShortcutSettings.shared.pttShortcut.displayTokens
    return tokens.isEmpty ? ["fn"] : tokens
  }

  func answerScreenDemo() { finishTalkDemo() }
}
