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
        guard self.step == .systemAudio else { return }
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

          guard self.step == .systemAudio else { return }
          self.setPermOn("system_audio")
          try? await Task.sleep(nanoseconds: 600_000_000)
          guard !Task.isCancelled, self.step == .systemAudio else { return }
          self.autoAdvanceIfCurrent("system_audio")
          return
        }

        try? await Task.sleep(nanoseconds: 500_000_000)
      }

      guard let self, !Task.isCancelled, self.step == .systemAudio else { return }
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
      // The Files connector row shares the FDA grant; reflect it here so the row
      // flips to "on" when FDA is granted from the context step — its poll only
      // drives fdaState, unlike every other connector that writes back its own state.
      contextStates["files"] = "on"
    // Do not read Apple Notes merely because Full Disk Access changed. The
    // explicit Connect action owns the data read.
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

  /// Skip on the mic step is a durable off for the automatic listening path: write
  /// `.off` so launch/restore never tries to start (and prompt) again. Allowing
  /// undoes an earlier skip so a user who goes Back and grants isn't left dark —
  /// the capture step's explicit answer remains the final word either way.
  func answerMic() {
    let allowed = micState == .on
    if allowed {
      if AssistantSettings.shared.audioRecordingMode == .off {
        AssistantSettings.shared.audioRecordingMode = .onlyMeetings
      }
    } else {
      AssistantSettings.shared.audioRecordingMode = .off
    }
    advance(userAnswer: allowed ? "Allowed" : "Skip", to: .systemAudio)
  }

  func answerSystemAudio() {
    UserDefaults.standard.set(sysState != .on, forKey: .onboardingSystemAudioSkipped)
    advance(userAnswer: sysState == .on ? "Allowed" : "Skip", to: .screen)
  }

  /// Skip on the screen step is a durable off for screen analysis — completion and
  /// every later automatic restore read this as the user's standing intent instead
  /// of force-enabling Rewind for someone who just declined it.
  func answerScreen() {
    AssistantSettings.shared.screenAnalysisEnabled = scrState == .on
    advance(userAnswer: scrState == .on ? "Allowed" : "Skip", to: .files)
  }
  /// A granted Files step builds the local-file profile. A skipped step must
  /// not enumerate Desktop/Documents/Downloads: touching those folders can
  /// itself raise Files & Folders consent when Full Disk Access is absent.
  func answerFiles() {
    guard fdaState == .on else {
      advance(userAnswer: "Skip", to: .accessibility)
      return
    }
    switch localFileProfileState {
    case .idle:
      thread.append(Msg(isOmi: false, text: "Allowed"))
      startLocalFileScan()
    case .scanning:
      break
    case .complete, .failed:
      finishFilesStep()
    }
  }

  func startLocalFileScan() {
    guard case .idle = localFileProfileState, localFileScanTask == nil else { return }
    localFileProfileState = .scanning
    let taskID = UUID()
    localFileScanID = taskID
    localFileScanTask = Task { [weak self] in
      guard let self else { return }
      defer {
        if self.localFileScanID == taskID {
          self.localFileScanTask = nil
          self.localFileScanID = nil
        }
      }
      let result = await self.fileScanRunner(self.appState)
      guard !Task.isCancelled, self.step == .files, self.localFileScanID == taskID else { return }
      self.localFileProfileState = result
      if case .complete = result {
        UserDefaults.standard.set(true, forKey: DefaultsKey.hasCompletedFileIndexing.rawValue)
        // If the app closes before the user taps Continue, resuming at Files
        // would otherwise run the scan and import a second time. The scan is
        // complete, so resume at the next stage instead.
        UserDefaults.standard.set(Step.accessibility.rawValue, forKey: Self.resumeStepKey)
      }
    }
  }

  func retryLocalFileScan() {
    guard case .failed = localFileProfileState else { return }
    localFileProfileState = .idle
    startLocalFileScan()
  }

  func finishFilesStep() {
    guard localFileProfileState.isTerminal else { return }
    advance(userAnswer: nil, to: .accessibility)
  }
  /// Skip on accessibility is a durable "not now": the sidebar must not pulse the
  /// row as denied for a user who explicitly walked past it. macOS exposes no
  /// denied/notDetermined distinction for AX, so the onboarding decision is the
  /// only honest signal — an Allow clears it, a Skip sets it.
  func answerAccessibility() {
    UserDefaults.standard.set(accState != .on, forKey: .onboardingAccessibilitySkipped)
    advance(userAnswer: accState == .on ? "Allowed" : "Skip", to: .automation)
  }
  func answerAutomation() { advance(userAnswer: autoState == .on ? "Allowed" : "Skip", to: .notifications) }
  func answerNotifications() { advance(userAnswer: notifState == .on ? "Allowed" : "Skip", to: .shortcutOpen) }

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
    case .mic: answerMic()
    case .systemAudio: answerSystemAudio()
    case .screen: answerScreen()
    case .files: answerFiles()
    case .accessibility: answerAccessibility()
    case .automation: answerAutomation()
    case .notifications: answerNotifications()
    default: break
    }
  }

  /// The permission key a step gates on, or nil for non-permission steps.
  func permissionKey(for step: Step) -> String? {
    switch step {
    case .mic: return "microphone"
    case .systemAudio: return "system_audio"
    case .screen: return "screen_recording"
    case .files: return "full_disk_access"
    case .accessibility: return "accessibility"
    case .automation: return "automation"
    case .notifications: return "notifications"
    default: return nil
    }
  }

  /// Starting at `target`, skip past any permission step whose cached permission
  /// is already granted. The synchronous compatibility path is intentionally
  /// limited to the state already available on the main actor; callers that
  /// need a current TCC answer must use `firstUnaskedStepAwaitingCurrentProbes`.
  func firstUnaskedStep(from target: Step) -> Step {
    var step = target
    while let key = permissionKey(for: step) {
      // These probes are local/cheap. The cross-process probes intentionally
      // stay out of this synchronous compatibility path and are awaited by the
      // async entry point below.
      if ["microphone", "system_audio", "screen_recording"].contains(key) {
        refreshPermCheck(key)
      }
      // A pre-granted FDA permission must still visit Files once so this flow
      // performs the required scan and aggregate-memory formation.
      if step == .files, isGranted(key), !localFileProfileState.isTerminal {
        setPermOn(key)
        break
      }
      guard isGranted(key), let next = Step(rawValue: step.rawValue + 1) else { break }
      setPermOn(key)
      step = next
    }
    return step
  }

  /// First-unasked scan for entry points that need a current permission answer.
  /// Every TCC/AX/Apple Events probe is awaited through the off-main refresh
  /// seam, so this scan never blocks the main actor while deciding where to land.
  func firstUnaskedStepAwaitingCurrentProbes(
    from target: Step,
    refresh: ((String) async -> Void)? = nil
  ) async -> Step {
    var step = target
    while let key = permissionKey(for: step) {
      if let refresh {
        await refresh(key)
      } else {
        await refreshPermCheckOffMain(key)
      }
      guard !Task.isCancelled else { return step }

      // A pre-granted FDA permission must still visit Files once so this flow
      // performs the required scan and aggregate-memory formation.
      if step == .files, isGranted(key), !localFileProfileState.isTerminal {
        setPermOn(key)
        break
      }
      guard isGranted(key), let next = Step(rawValue: step.rawValue + 1) else { break }
      setPermOn(key)
      step = next
    }
    return step
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
    case .shortcutOpen:
      rememberedSelection = openShortcutSelection
      isTalk = false
    case .shortcutTalk:
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
    if savedMainMenu == nil { savedMainMenu = NSApp.mainMenu }
    NSApp.mainMenu = nil
    installShortcutMonitors()
  }

  func disarmShortcutSummon() {
    for m in shortcutMonitors { NSEvent.removeMonitor(m) }
    shortcutMonitors.removeAll()
    if let saved = savedMainMenu {
      NSApp.mainMenu = saved
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
    switch step {
    case .shortcutOpen: return openShortcutOptions.map { $0.shortcut }
    case .shortcutTalk: return talkShortcutOptions.map { $0.shortcut }
    default: return []
    }
  }

  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    if shortcutRecording {
      // The global monitor is here for the *test* phase, so a chord pressed while another app is
      // focused still counts as "that works". While the step is still **recording** it is a hazard
      // instead: the first key the user happens to type anywhere on the Mac — a terminal, a
      // browser, a message — becomes their Omi chord, and the step then congratulates them on it.
      // Only what is typed at Omi may set it.
      guard Self.acceptsRecordingSource(appIsActive: NSApp.isActive) else { return false }
      return recordShortcut(from: event)
    }
    guard !shortcutPressed else { return false }
    // If the user already tapped a row, honor that exact pick; otherwise let ANY
    // offered combo select itself on press, so "just press the key" works and the
    // Continue button appears without a separate pick-then-test step.
    let candidates = chosenShortcut.map { [$0] } ?? currentShortcutCandidates
    let isTalk = step == .shortcutTalk
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
    let isTalk = step == .shortcutTalk
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

  func answerShortcutOpen() {
    guard shortcutPicked, shortcutPressed else { return }
    guard GlobalShortcutManager.shared.validateAskOmiShortcutForOnboarding() == .registered else {
      shortcutRegistrationError =
        "That shortcut is already in use. Choose a different Open Omi shortcut and test it again."
      shortcutPressed = false
      return
    }
    advance(userAnswer: "Works", to: .shortcutTalk)
  }
  func answerShortcutTalk() {
    guard shortcutPicked, shortcutPressed else { return }
    UserDefaults.standard.set(true, forKey: Self.shortcutsCompletedKey)
    advance(userAnswer: "Works", to: .screenDemo)
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
    threeDoorsOpened = false
    ThreeDoorsDemoPage.activeModelNote = ThreeDoorsDemoPage.modelNote
    openDoorsObserver = NotificationCenter.default.addObserver(
      forName: .onboardingOpenDoorsRequested, object: nil, queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated { self?.openThreeDoorsPage() }
    }
    doorsCompletedObserver = NotificationCenter.default.addObserver(
      forName: .onboardingDoorsCompleted, object: nil, queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        guard let self, self.step == .screenDemo else { return }
        self.screenDemoDone = true
      }
    }
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
    guard !Task.isCancelled, step == .screenDemo else { return }
    guard bridgeReady else {
      screenDemoPTTUnavailable = true
      return
    }
    activate()
  }

  private func activateScreenDemoPTT() {
    guard step == .screenDemo,
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

  /// Open the bundled three-doors page in the default browser. Only ever user-initiated, from the
  /// step's "Open the doors" button, so the person reads the instructions before the page appears.
  func openThreeDoorsPage() {
    guard let url = ThreeDoorsDemoPage.url(pttTokens: voiceChordTokens) else {
      log("SBOnboarding: three-doors page missing from bundle; demo step shows without it")
      return
    }
    threeDoorsOpened = true
    startScreenHistoryCaptureForDemo()
    NSWorkspace.shared.open(url)
  }

  /// Rewind normally starts from the home view, i.e. only after onboarding completes. The third
  /// door asks about text that has scrolled off screen, which only screen history can answer, so
  /// the demo needs capture running from the moment the doors open. Same gates as the home view:
  /// the setting the user chose at the screen step, Screen Recording actually granted, keys loaded.
  func startScreenHistoryCaptureForDemo() {
    let plugin = ProactiveAssistantsPlugin.shared
    guard AssistantSettings.shared.screenAnalysisEnabled, !plugin.isMonitoring else { return }
    guard APIKeyService.keysAvailable else {
      log("SBOnboarding: screen history capture deferred for the demo; API keys not loaded yet")
      return
    }
    plugin.refreshScreenRecordingPermission()
    guard plugin.hasScreenRecordingPermission else {
      log("SBOnboarding: screen history capture not started for the demo; Screen Recording not granted")
      return
    }
    plugin.startMonitoring { success, error in
      log("SBOnboarding: screen history capture for the demo \(success ? "started" : "failed: \(error ?? "unknown")")")
    }
  }

  private func resetFloatingBarConversation() {
    guard let bar = FloatingControlBarManager.shared.barState else { return }
    bar.showingAIConversation = false
    bar.showingAIResponse = false
    bar.aiInputText = ""
    bar.clearViewport()
  }

  func teardownVoiceDemo() {
    ThreeDoorsDemoPage.activeModelNote = nil
    if let openDoorsObserver { NotificationCenter.default.removeObserver(openDoorsObserver) }
    openDoorsObserver = nil
    if let doorsCompletedObserver { NotificationCenter.default.removeObserver(doorsCompletedObserver) }
    doorsCompletedObserver = nil
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

  func answerScreenDemo() { advance(userAnswer: "Continue", to: .agents) }
}

// MARK: - Agents (do things for you)

extension SBOnboardingModel {
  var agentRows: [(id: String, name: String, detail: String)] {
    [
      ("openclaw", "OpenClaw", "runs tasks on your Mac"),
      ("hermes", "Hermes", "autonomous background agent"),
      ("claudeCode", "Claude Code", "codes in your repos"),
      ("codex", "Codex", "OpenAI's coding agent"),
    ]
  }

  private func agentDestination(_ id: String) -> MemoryExportDestination {
    switch id {
    case "openclaw": return .openclaw
    case "hermes": return .hermes
    case "claudeCode": return .claudeCode
    case "codex": return .codex
    default: return .openclaw
    }
  }

  /// Brand mark for a connector row (agents + context), so every row shows its
  /// real logo even when the app isn't installed (#10210). Brands without a
  /// bundled logo (openclaw/hermes/files) fall back to the icon's default glyph.
  func connectorBrand(_ id: String) -> ConnectorBrand {
    switch id {
    case "openclaw": return .openclaw
    case "hermes": return .hermes
    case "claudeCode": return .claudeCode
    case "codex": return .codex
    case "calendar": return .calendar
    case "gmail": return .gmail
    case "applenotes": return .appleNotes
    case "files": return .localFiles
    case "chatgpt": return .chatgpt
    case "claude": return .claude
    default: return .agents
    }
  }

  func refreshAgentStates() {
    // Show a "checking" placeholder up front so a not-installed agent never briefly
    // offers a "Connect" button that only flips to "not installed" after a click
    // (the async install probe below resolves each row to its real state).
    for row in agentRows where agentStates[row.id] == nil {
      agentStates[row.id] = "checking"
    }
    Task { [weak self] in
      guard let self else { return }
      for row in self.agentRows {
        // Only offer Connect for agents actually present on this Mac; otherwise
        // mark "unavailable" so the row shows "not installed" with no button.
        let installed = await Self.agentInstalled(self.agentDestination(row.id))
        guard installed else {
          self.agentStates[row.id] = "unavailable"
          continue
        }
        let connected = await MemoryExportService.shared.status(for: self.agentDestination(row.id)).hasConnection
        self.agentStates[row.id] = connected ? "on" : "idle"
      }
    }
  }

  /// Local install probe using the SAME evidence the real connect path requires,
  /// so a row never offers "Connect" and then flips to "not installed" on click
  /// (e.g. Codex: a stray `~/.codex` dir is not enough — the connector needs the
  /// `codex` binary on PATH). Delegates to `MemoryBankConnector.isInstalled`.
  private static func agentInstalled(_ destination: MemoryExportDestination) async -> Bool {
    await Task.detached { MemoryBankConnector.isInstalled(destination) }.value
  }

  func connectAgent(_ id: String) {
    guard agentStates[id] != "connecting", agentStates[id] != "checking", agentStates[id] != "on" else { return }
    agentStates[id] = "connecting"
    let dest = agentDestination(id)
    Task { [weak self] in
      do {
        _ = try await MemoryExportExecutor.run(dest)
      } catch {
        self?.agentStates[id] = "unavailable"
        return
      }
      guard let self else { return }
      let connected = await MemoryExportService.shared.status(for: dest).hasConnection
      self.agentStates[id] = connected ? "on" : "idle"
    }
  }

  func answerAgents() { advance(userAnswer: "Continue", to: .context) }
}

// MARK: - Context (connect what I can see)

extension SBOnboardingModel {
  enum ContextConnectionRoute: Equatable {
    case importConnector(String)
    case direct
  }

  struct GoogleContextResolution: Equatable {
    let state: String
    let detail: String?
    let shouldOpenSignIn: Bool
  }

  var contextRows: [(id: String, name: String, detail: String)] {
    [
      ("calendar", "Calendar", "meetings + prep"),
      ("gmail", "Gmail", "email follow-ups"),
      ("applenotes", "Apple Notes", "your notes"),
      ("files", "Files", "docs on this Mac"),
      ("chatgpt", "ChatGPT", "carry memory across"),
      ("claude", "Claude", "carry memory across"),
    ]
  }

  func refreshContextStates() {
    if appState.hasFullDiskAccess { contextStates["files"] = "on" }
    Task { [weak self] in
      guard let self else { return }
      // Do not probe browser cookies or Apple Notes just to decorate a fresh
      // onboarding row.
      // A functional probe without a completed import used to paint "on" even
      // though post-onboarding Home/Apps had no persisted connector state and
      // no imported data. Only re-check a connector that this account already
      // completed through the canonical import path; a new source stays
      // explicitly connectable until the user starts that import.
      guard self.hasPersistedGoogleImport("calendar") || self.hasPersistedGoogleImport("gmail") else {
        return
      }
      if self.hasPersistedGoogleImport("calendar") {
        let calendar = await CalendarReaderService.shared.verifyConnection()
        self.projectGoogleVerification("calendar", status: calendar)
      }
      if self.hasPersistedGoogleImport("gmail") {
        let gmail = await GmailReaderService.shared.verifyConnection()
        self.projectGoogleVerification("gmail", status: gmail)
      }
    }
  }

  private func hasPersistedGoogleImport(_ contextID: String) -> Bool {
    guard
      let statusStore = importConnectorStatusStore,
      let connector = ImportConnector.all.first(where: {
        $0.id == Self.importConnectorID(forGoogleContextID: contextID)
      })
    else { return false }
    return statusStore.snapshot(for: connector).isConnected
  }

  private func markGoogleContextImported(_ id: String) {
    contextStates[id] = "on"
    contextDetails[id] = nil
  }

  private func projectGoogleVerification(_ id: String, status: CalendarConnectionStatus) {
    switch status {
    case .connected:
      markGoogleContextImported(id)
    case .needsSignIn:
      projectGoogleContext(id, connected: false, needsSignIn: true)
    case .error:
      projectGoogleContext(id, connected: false, needsSignIn: false)
    }
  }

  private func projectGoogleVerification(_ id: String, status: GmailConnectionStatus) {
    switch status {
    case .connected:
      markGoogleContextImported(id)
    case .needsSignIn:
      projectGoogleContext(id, connected: false, needsSignIn: true)
    case .error:
      projectGoogleContext(id, connected: false, needsSignIn: false)
    }
  }

  /// ChatGPT and Claude on this surface mean importing existing memories into
  /// Omi. Live MCP exports are a separate Apps > Exports action and must never
  /// be substituted here.
  nonisolated static func contextConnectionRoute(for id: String) -> ContextConnectionRoute {
    switch id {
    case "chatgpt", "claude":
      return .importConnector(id)
    default:
      return .direct
    }
  }

  nonisolated static func importConnectorID(forGoogleContextID id: String) -> String {
    id == "gmail" ? "email" : "calendar"
  }

  nonisolated static func googleContextResolution(
    connectorID: String,
    connected: Bool,
    needsSignIn: Bool
  ) -> GoogleContextResolution {
    if connected {
      return GoogleContextResolution(state: "on", detail: nil, shouldOpenSignIn: false)
    }
    let name = connectorID == "gmail" ? "Gmail" : "Google Calendar"
    let detail =
      needsSignIn
      ? "Open \(name) in Chrome, Arc, Brave, or Edge, sign in, then retry."
      : "Couldn't verify \(name). Check your browser session and connection, then retry."
    return GoogleContextResolution(
      state: needsSignIn ? "needsSignIn" : "error",
      detail: detail,
      shouldOpenSignIn: needsSignIn
    )
  }

  /// Projects a cookie-based Google import/probe into bounded onboarding copy.
  /// Reconnect-required terminal imports open the browser separately; passive
  /// refreshes must only show an honest retry state, never steal focus.
  private func projectGoogleContext(_ id: String, connected: Bool, needsSignIn: Bool) {
    let resolution = Self.googleContextResolution(
      connectorID: id,
      connected: connected,
      needsSignIn: needsSignIn
    )
    contextStates[id] = resolution.state
    contextDetails[id] = resolution.detail
  }

  func connectContext(_ id: String) {
    guard contextStates[id] != "connecting", contextStates[id] != "on" else { return }
    // The view owns import-sheet presentation. Keep this guard so another
    // caller cannot accidentally route a memory import into the MCP exporter.
    guard Self.contextConnectionRoute(for: id) == .direct else { return }
    switch id {
    case "calendar":
      startGoogleContextImport("calendar") { progress in
        await ConnectorImportOperations.importCalendar(progress: progress)
      }
    case "gmail":
      startGoogleContextImport("gmail") { progress in
        await ConnectorImportOperations.importGmail(progress: progress)
      }
    case "applenotes":
      Task { [weak self] in
        guard let self else { return }
        // Full Disk Access covers Notes when it applies; if not, grant a
        // security-scoped folder bookmark (the real, re-sign-proof connect path).
        var status = await AppleNotesReaderService.shared.connectionStatus(userInitiated: true)
        if status.isConnected {
          self.contextStates["applenotes"] = "on"
          return
        }
        let pickedPath: String? = await MainActor.run {
          let panel = NSOpenPanel()
          panel.canChooseDirectories = true
          panel.canChooseFiles = false
          panel.allowsMultipleSelection = false
          panel.prompt = "Grant access"
          panel.message = "Pick your Notes data folder so I can read it."
          panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Group Containers/group.com.apple.notes")
          return panel.runModal() == .OK ? panel.url?.path : nil
        }
        guard let path = pickedPath else {
          self.contextStates["applenotes"] = "needsSignIn"
          return
        }
        do {
          _ = try await AppleNotesReaderService.shared.validateSelectedFolder(path: path)
          status = await AppleNotesReaderService.shared.connectionStatus(
            selectedFolderPath: path,
            userInitiated: true
          )
          self.contextStates["applenotes"] = status.isConnected ? "on" : "needsSignIn"
        } catch {
          self.contextStates["applenotes"] = "needsSignIn"
        }
      }
    case "files":
      appState.checkFullDiskAccess()
      if appState.hasFullDiskAccess {
        contextStates["files"] = "on"
      } else {
        requestFullDiskAccess()
        contextStates["files"] = "idle"
      }
    default: break
    }
  }

  /// Starts Gmail/Calendar through the exact shared importer that Apps uses.
  /// Success is deliberately a three-part predicate: the browser auth worked
  /// for a real data read, that read/import completed, and the account-scoped
  /// connector status persisted for the surface shown after onboarding.
  private func startGoogleContextImport(
    _ contextID: String,
    operation: @escaping @MainActor (ConnectorImportRunner.ProgressSink) async -> ConnectorImportOperations.Outcome
  ) {
    guard
      let statusStore = importConnectorStatusStore,
      let connector = ImportConnector.all.first(where: {
        $0.id == Self.importConnectorID(forGoogleContextID: contextID)
      })
    else {
      projectGoogleContext(contextID, connected: false, needsSignIn: false)
      return
    }

    let connectorID = connector.id
    let wasFirstSync = !statusStore.snapshot(for: connector).isConnected
    contextStates[contextID] = "connecting"
    contextDetails[contextID] = nil
    let task = ConnectorImportRunner.shared.start(
      connectorID: connectorID,
      progressTitle: "Connecting to \(connector.title)",
      progressDetail: "Reading data and saving it to your Omi memory.",
      surface: .onboarding
    ) { [self] progress in
      let outcome = await operation(progress)
      let terminal = completeGoogleContextImport(
        contextID: contextID,
        connectorID: connectorID,
        outcome: outcome,
        statusStore: statusStore,
        wasFirstSync: wasFirstSync
      )
      if case .failure(_, let metrics) = terminal,
        let failureClass = metrics.failureClass,
        IntegrationConnectTelemetry.failureRequiresReconnect(failureClass),
        let url = URL(string: contextID == "gmail" ? "https://mail.google.com" : "https://calendar.google.com")
      {
        NSWorkspace.shared.open(url)
      }
      return terminal
    }
    if task == nil {
      // A shared Apps/onboarding import is already running. Don't leave the
      // row spinning indefinitely; the persisted status is updated by that
      // authoritative run and the user can retry once it settles.
      contextStates[contextID] = "error"
      contextDetails[contextID] = "This connection is already syncing. Wait a moment, then retry."
    }
  }

  /// Applies an import terminal exactly once. Keeping this state transition in
  /// the onboarding model makes the durable Apps/Home status and the visible
  /// onboarding status change together, so one cannot report a false success.
  func completeGoogleContextImport(
    contextID: String,
    connectorID: String,
    outcome: ConnectorImportOperations.Outcome,
    statusStore: ImportConnectorStatusStore,
    wasFirstSync: Bool
  ) -> ConnectorImportRunner.RunOutcome {
    switch outcome {
    case .success(let result, let message):
      statusStore.markSynced(
        connectorID: connectorID,
        sourceCount: result.sourceCount,
        memoryCount: result.memoryCount,
        lastDeltaCount: result.newItems
      )
      markGoogleContextImported(contextID)
      return .success(
        message: message,
        metrics: ConnectorImportRunner.RunMetrics(
          sourceCount: result.sourceCount,
          memoryCount: result.memoryCount,
          wasFirstSync: wasFirstSync
        )
      )
    case .failure(let message, let failureClass):
      let reconnectRequired = failureClass.map(IntegrationConnectTelemetry.failureRequiresReconnect) ?? false
      projectGoogleContext(contextID, connected: false, needsSignIn: reconnectRequired)
      return .failure(
        message: message,
        metrics: ConnectorImportRunner.RunMetrics(
          failureClass: failureClass,
          wasFirstSync: wasFirstSync
        )
      )
    }
  }

  func markContextImportConnected(_ connectorID: String) {
    guard Self.contextConnectionRoute(for: connectorID) == .importConnector(connectorID) else { return }
    contextStates[connectorID] = "on"
    contextDetails[connectorID] = nil
  }

  /// Receives the canonical persisted connector ID from the shared import
  /// status store. Gmail's context-row ID differs from its Apps ID (`gmail`
  /// vs `email`), so translate at this one authority boundary rather than
  /// allowing a completed shared import to leave the onboarding row stale.
  func markPersistedContextConnectorConnected(_ connectorID: String) {
    switch connectorID {
    case "calendar": markGoogleContextImported("calendar")
    case "email": markGoogleContextImported("gmail")
    default: markContextImportConnected(connectorID)
    }
  }

  func answerContext() { advance(userAnswer: "Continue", to: .capture) }
}
